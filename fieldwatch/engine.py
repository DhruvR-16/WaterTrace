"""Bounded, inspectable surface-water screening, not crop-damage diagnosis.

Inputs are georeferenced, calibrated Sentinel-1 VV/VH backscatter in dB.
OpenCV operates on rasters; Rasterio/PROJ preserve geographic coordinates.
No event names, label rasters, crop labels, or expected answers enter inference.
"""
from dataclasses import dataclass
import hashlib
import math

import cv2
import numpy as np
from pyproj import Geod, Transformer
import rasterio
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from shapely.geometry import Polygon, box, mapping

MAX_BYTES = 24 * 1024 * 1024
MAX_PIXELS = 2_000_000
POLICY = "surface-water-screen-v1"
BOUNDARY_TOLERANCE_PIXELS = 1e-7  # Coordinate roundoff only, not an allowed missing-area percentage.
GEOD = Geod(ellps="WGS84")


class InvalidRaster(ValueError):
    pass


@dataclass
class Raster:
    bands: np.ndarray
    valid: np.ndarray
    transform: object
    crs: object
    sha256: str

    @property
    def dimensions(self):
        return self.bands.shape[1:]


def read_raster(raw: bytes) -> Raster:
    if not raw or len(raw) > MAX_BYTES:
        raise InvalidRaster("Choose a GeoTIFF up to 24 MiB.")
    if raw[:4] not in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"):
        raise InvalidRaster("Only GeoTIFF files are accepted, not VRTs, URLs, or archives.")
    try:
        with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_NUM_THREADS="1"):
            with MemoryFile(raw) as memory, memory.open(driver="GTiff") as dataset:
                if dataset.count != 2 or not dataset.crs:
                    raise InvalidRaster("Provide exactly two georeferenced bands: VV then VH, calibrated in dB.")
                if min(dataset.width, dataset.height) < 16 or dataset.width * dataset.height > MAX_PIXELS:
                    raise InvalidRaster("Use a raster of at least 16×16 and at most 2 million pixels.")
                t = dataset.transform
                if t.a <= 0 or t.e >= 0 or t.b != 0 or t.d != 0:
                    raise InvalidRaster("Reproject to a north-up, unrotated grid before upload.")
                bands = dataset.read(out_dtype="float32")
                valid = (dataset.read_masks() > 0).all(axis=0) & np.isfinite(bands).all(axis=0)
                valid &= ((bands > -80) & (bands < 20)).all(axis=0)
                if valid.sum() < 100:
                    raise InvalidRaster("Too few valid calibrated radar pixels; check units and NoData.")
                # Linear-power values are nonnegative: do not silently interpret as dB.
                if np.median(bands[:, valid]) >= 0:
                    raise InvalidRaster("Expected negative dB backscatter, not linear power or display RGB.")
                result = Raster(bands, valid, t, dataset.crs, hashlib.sha256(raw).hexdigest())
                bounds = geographic_bounds(result)
                if not all(math.isfinite(v) for v in bounds) or bounds[2] <= bounds[0] or bounds[3] <= bounds[1] or bounds[0] < -180 or bounds[2] > 180:
                    raise InvalidRaster("Unsupported geographic extent.")
                if bounds[2] - bounds[0] > 2 or bounds[3] - bounds[1] > 2 or min(bounds[1], bounds[3]) < -80 or max(bounds[1], bounds[3]) > 80:
                    raise InvalidRaster("Use a local study area under 2 degrees across, between 80°S and 80°N.")
                return result
    except InvalidRaster:
        raise
    except Exception:
        raise InvalidRaster("Could not decode this GeoTIFF. Check its projection and band format.") from None


def geographic_bounds(raster):
    h, w = raster.dimensions
    project = Transformer.from_crs(raster.crs, "EPSG:4326", always_xy=True)
    points = [project.transform(*(raster.transform @ p)) for p in ((0, 0), (w, 0), (w, h), (0, h))]
    return [min(p[0] for p in points), min(p[1] for p in points), max(p[0] for p in points), max(p[1] for p in points)]


def pixel_areas(raster):
    """Geodesic area per pixel, including geographic grids (never degrees² as m²).

    Compute at the row center and replicate across each short local row.
    This is an approximation for projected grids; limits bound the study extent.
    """
    h, w = raster.dimensions
    project = Transformer.from_crs(raster.crs, "EPSG:4326", always_xy=True)
    areas = []
    x = w // 2
    for y in range(h):
        points = [project.transform(*(raster.transform @ p)) for p in ((x, y), (x+1, y), (x+1, y+1), (x, y+1))]
        area, _ = GEOD.polygon_area_perimeter([p[0] for p in points], [p[1] for p in points])
        areas.append(abs(area) / 10000)
    return np.broadcast_to(np.asarray(areas)[:, None], (h, w))


def otsu_db(band, valid):
    """Fixed scale makes the threshold reproducible across images."""
    quantized = np.rint((np.clip(band[valid], -40, 5) + 40) / 45 * 255).astype(np.uint8)
    value, _ = cv2.threshold(quantized.reshape(-1, 1), 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    return float(value / 255 * 45 - 40)


def classify(raster):
    """0=uncertain/unobserved, 1=no open water detected, 2=water-like evidence.

    VV and VH must agree with a margin; disagreement is not turned into dry land.
    Threshold bounds and margin are fixed before held-out evaluation.
    """
    thresholds, filtered = [], []
    valid = raster.valid
    # Pixels adjacent to invalid input are unknown: filters must not fill holes.
    supported = cv2.erode(valid.astype(np.uint8), np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    for band, limits in zip(raster.bands, ((-22., -12.), (-30., -20.))):
        filled = np.where(valid, band, np.median(band[valid])).astype(np.float32)
        smooth = cv2.medianBlur(filled, 3)
        threshold = float(np.clip(otsu_db(smooth, valid), *limits))
        filtered.append(smooth)
        thresholds.append(threshold)
    vv, vh = filtered
    margin = 1.5
    water = (vv < thresholds[0] - margin) & (vh < thresholds[1] - margin) & supported
    land = (vv > thresholds[0] + margin) & (vh > thresholds[1] + margin) & supported
    # Tiny isolated dark components are uncertain, not confidently classified.
    n, labels, stats, _ = cv2.connectedComponentsWithStats(water.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= 9
    water = keep[labels]
    classes = np.zeros(valid.shape, np.uint8)
    classes[land] = 1
    classes[water] = 2
    return classes, {"vv_threshold_db": round(thresholds[0], 3), "vh_threshold_db": round(thresholds[1], 3),
                     "agreement_margin_db": margin, "median_kernel": 3, "minimum_water_component_pixels": 9,
                     "method": "bounded Otsu + dual-polarization agreement + connected components",
                     "warning": "Agreement is a heuristic, not a calibrated probability. Dark surfaces can mimic water; flooded vegetation can be missed."}


def compare(current, reference):
    if current.dimensions != reference.dimensions or current.crs != reference.crs or not current.transform.almost_equals(reference.transform, precision=1e-10):
        raise InvalidRaster("Earlier and current rasters must share the exact CRS, grid and dimensions. Reproject upstream.")
    now, policy = classify(current)
    before, previous_policy = classify(reference)
    return now, (now == 2) & (before == 1), (now == 2) & (before == 2), before, policy, previous_policy


def default_zones(raster):
    """Explicit survey grid, NOT inferred farms or an agricultural land-cover map."""
    h, w = raster.dimensions
    to_geo = Transformer.from_crs(raster.crs, "EPSG:4326", always_xy=True)
    features = []
    for row in range(3):
        for col in range(3):
            x0, x1, y0, y1 = col*w/3, (col+1)*w/3, row*h/3, (row+1)*h/3
            points = [to_geo.transform(*(raster.transform @ p)) for p in ((x0,y0),(x1,y0),(x1,y1),(x0,y1),(x0,y0))]
            features.append({"type": "Feature", "properties": {"id": f"sector-{row*3+col+1}", "name": f"Survey sector {row*3+col+1}", "crop": "unknown"},
                             "geometry": {"type": "Polygon", "coordinates": [points]}})
    return {"type": "FeatureCollection", "features": features}


def temporal_summary(classes, before, area, mask=None):
    """Area-weighted paired support, not flood onset or continuous duration.

    An unknown earlier pixel is neither earlier land nor earlier water. Keep
    completeness as an unrounded boolean so small gaps cannot clear a gate.
    """
    if before is None:
        return None
    if mask is not None:
        classes, before, area = classes[mask], before[mask], area[mask]
    paired = (classes != 0) & (before != 0)
    water = classes == 2
    missing = water & (before == 0)
    total = float(area.sum())
    water_area = float(area[water].sum())
    return {
        'policy': 'paired-evidence-v1',
        'paired_assessed_ha': round(float(area[paired].sum()), 3),
        'paired_uncertain_ha': round(float(area[~paired].sum()), 3),
        'paired_assessed_fraction': round(float(area[paired].sum()) / total, 4),
        'water_without_baseline_ha': round(float(area[missing].sum()), 3),
        'observed_water_baseline_fraction': round(float(area[water & (before != 0)].sum()) / water_area, 4) if water_area else None,
        'observed_water_baseline_complete': not bool(missing.any()) if water_area else None,
    }


def summarize_zones(raster, classes, collection=None, new_water=None, persistent=None, before=None):
    collection = default_zones(raster) if collection is None else collection
    if not isinstance(collection, dict) or collection.get("type") != "FeatureCollection":
        raise InvalidRaster("Zones must be a GeoJSON FeatureCollection in longitude/latitude.")
    features = collection.get("features")
    if not isinstance(features, list) or not 1 <= len(features) <= 100:
        raise InvalidRaster("Provide 1–100 review zones.")
    to_grid = Transformer.from_crs("EPSG:4326", raster.crs, always_xy=True)
    inv = ~raster.transform
    h, w = raster.dimensions
    area = pixel_areas(raster)
    scene = box(0, 0, w, h)
    tolerance = BOUNDARY_TOLERANCE_PIXELS
    scene_with_roundoff = box(-tolerance, -tolerance, w+tolerance, h+tolerance)
    rows, ids = [], set()
    for index, feature in enumerate(features):
        try:
            if not isinstance(feature, dict) or feature.get('type') != 'Feature':
                raise ValueError()
            geometry = feature["geometry"]
            rings = geometry["coordinates"]
            if geometry["type"] != "Polygon" or len(rings) != 1 or not 4 <= len(rings[0]) <= 200:
                raise ValueError()
            # Do not let NumPy coerce strings/bools into accepted coordinates:
            # the original geometry is retained in reports and geographic exports.
            if any(isinstance(value, bool) or not isinstance(value, (int, float))
                   for point in rings[0] for value in point):
                raise ValueError()
            coordinates = np.asarray(rings[0], dtype=float)
            if coordinates.ndim != 2 or coordinates.shape[1] != 2 or not np.isfinite(coordinates).all() or not np.array_equal(coordinates[0], coordinates[-1]) or np.any(np.abs(coordinates[:,0]) > 180) or np.any(np.abs(coordinates[:,1]) > 90):
                raise ValueError()
            polygon = Polygon([inv @ to_grid.transform(*p) for p in coordinates])
            if not polygon.is_valid or polygon.area <= 0 or not box(0,0,w,h).intersects(polygon):
                raise ValueError()
            properties = feature.get("properties", {})
            if not isinstance(properties, dict):
                raise ValueError()
            identifier = str(properties.get("id", f"zone-{index+1}"))[:80]
            if identifier in ids:
                raise ValueError()
            ids.add(identifier)
            name = str(properties.get("name", identifier))[:100]
            crop = str(properties.get("crop", "unknown")).strip()[:80]
            for text in (identifier, name, crop):
                text.encode('utf-8')
            # Retain the validated geometry only, not arbitrary foreign payloads.
            geometry = {'type': 'Polygon', 'coordinates': [[list(point) for point in rings[0]]]}
        except (KeyError, TypeError, ValueError, IndexError, OverflowError, RecursionError):
            raise InvalidRaster("Each zone needs a unique ID and a valid, intersecting Polygon with 4–200 lon/lat points and no holes.") from None
        clipped = polygon.intersection(scene)
        scene_clipped = not scene_with_roundoff.covers(polygon)
        spatial_support = {
            'scene_clipped': scene_clipped,
            'scene_overlap_fraction': round(min(1.0, max(0.0, clipped.area / polygon.area)), 8),
            'fraction_basis': 'planar_polygon_area_in_raster_grid',
            'boundary_tolerance_pixels': tolerance,
        }
        mask = rasterize([(mapping(clipped), 1)], out_shape=(h,w), fill=0).astype(bool)
        total = float(area[mask].sum())
        if not total:
            raise InvalidRaster("A zone contains no pixel centers. Use a larger review area.")
        values = {label: float(area[mask & (classes == code)].sum()) for code, label in enumerate(("uncertain_ha", "no_water_detected_ha", "water_observed_ha"))}
        coverage = 1 - values["uncertain_ha"] / total
        water_fraction = values["water_observed_ha"] / total
        reasons = []
        if mask.sum() < 25:
            reasons.append("Too few pixels for a field-level assessment.")
        if coverage < .7:
            reasons.append("More than 30% of this zone is uncertain or unobserved.")
        if scene_clipped:
            reasons.append("Zone extends outside the scene; estimates cover only the overlap.")
        if crop.lower() in ("rice", "paddy"):
            reasons.append("Intentional paddy inundation cannot be distinguished from flood exposure here.")
        if water_fraction >= .05:
            status = "inspect_water"
            reasons.insert(0, "Water-like evidence covers at least 5% of the observed zone footprint.")
        elif coverage < .7 or mask.sum() < 25 or reasons:
            status = "resolve_uncertainty"
        else:
            status = "no_signal"
            reasons.append("No substantial open-water signal detected; this is not a safety or crop-health assessment.")
        row = {"id": identifier, "name": name, "crop": crop, "status": status, "reasons": reasons,
               "area_ha": round(total, 3), **{k: round(v, 3) for k,v in values.items()},
               "coverage": round(coverage,4), "water_fraction": round(water_fraction,4), "pixels": int(mask.sum()),
               "spatial_support": spatial_support,
               "temporal_support": temporal_summary(classes, before, area, mask),
               "new_water_candidate_ha": round(float(area[mask & new_water].sum()),3) if new_water is not None else None,
               "repeat_water_observed_ha": round(float(area[mask & persistent].sum()),3) if persistent is not None else None,
               "pixel_geometry": mapping(clipped), "geometry": geometry}
        rows.append(row)
    # Two explicit work queues; unknown areas must not disappear below a risk score.
    return sorted(rows, key=lambda r: ({"inspect_water":0, "resolve_uncertainty":1, "no_signal":2}[r["status"]], -r["water_fraction"], r["id"]))

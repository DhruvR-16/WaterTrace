"""Report construction and visualization. Benchmark labels are never read here."""
import base64
from datetime import date, datetime, timezone
import time

import cv2
import numpy as np

from fieldwatch.engine import POLICY, InvalidRaster, classify, compare, geographic_bounds, pixel_areas, read_raster, summarize_zones
from fieldwatch.decisions import review_decision


def png(array):
    ok, encoded = cv2.imencode(".png", array)
    if not ok:
        raise RuntimeError("PNG encoding failed")
    return "data:image/png;base64," + base64.b64encode(encoded).decode("ascii")


def radar_preview(raster):
    valid_band = np.where(raster.valid, raster.bands[0], -30)
    grey = np.rint((np.clip(valid_band, -30, 0) + 30) / 30 * 255).astype(np.uint8)
    grey[~raster.valid] = 0
    return png(grey)


def overlay(classes):
    result = np.zeros((*classes.shape, 4), np.uint8)
    result[classes == 2] = (221, 169, 25, 200)  # BGRA blue
    yy, xx = np.indices(classes.shape)
    result[(classes == 0) & ((xx + yy) % 10 < 3)] = (51, 173, 230, 190)
    return png(result)


def run_analysis(raw, *, name="Radar scene", observed_on=None, reference_raw=None,
                 reference_on=None, same_orbit=False, zones=None):
    start = time.perf_counter()
    try:
        current_date = date.fromisoformat(observed_on) if observed_on else None
        reference_date = date.fromisoformat(reference_on) if reference_on else None
        if current_date and current_date > datetime.now(timezone.utc).date():
            raise ValueError()
        if reference_raw is not None and (not current_date or not reference_date or reference_date >= current_date):
            raise ValueError()
    except (ValueError, TypeError):
        raise InvalidRaster("Use valid acquisition dates; an earlier scene must predate the current scene, with neither in the future.") from None
    if reference_raw is not None and not same_orbit:
        raise InvalidRaster("Confirm both acquisitions use matching relative orbit, direction, polarization and calibration before comparison.")
    raster = read_raster(raw)
    steps = [{"action": "validate_input", "outcome": "Two georeferenced dB bands; bounded raster; invalid pixels preserved."}]
    new_water = persistent = before = previous_policy = reference = None
    if reference_raw is not None:
        reference = read_raster(reference_raw)
        classes, new_water, persistent, before, policy, previous_policy = compare(raster, reference)
        steps.append({"action": "compare_earlier_observation", "outcome": "Same-grid earlier scene available. Compare independently screened water states; do not infer continuous duration."})
    else:
        classes, policy = classify(raster)
        steps.append({"action": "withhold_change_claim", "outcome": "No earlier scene: report water-like evidence, not newly flooded area or flood duration."})
    area = pixel_areas(raster)
    total = float(area.sum())
    unknown_fraction = float(area[classes == 0].sum()) / total
    steps.append({"action": "request_human_review" if unknown_fraction > .3 else "summarize_observed_evidence",
                  "outcome": f"{unknown_fraction:.1%} of the scene is uncertain/unobserved. Unknown pixels are not classified as safe."})
    rows = summarize_zones(raster, classes, zones, new_water, persistent)
    for row in rows:
        row['decision'] = review_decision(row, reference is not None)
    steps.append({'action':'check_field_review_gates', 'outcome':f"{sum(r['decision']['level'] == 'insufficient_evidence' for r in rows)} zones lack sufficient coverage or resolution for a whole-field interpretation. Pixel measurements remain visible; field-level conclusions are withheld."})
    steps.append({"action": "prepare_separate_review_queues", "outcome": "Water-evidence and uncertainty queues are separate. No automatic interventions, field visits or insurance decisions."})
    bounds = geographic_bounds(raster)
    summary = {"scene_area_ha": round(total, 3), "water_observed_ha": round(float(area[classes == 2].sum()),3),
               "uncertain_ha": round(float(area[classes == 0].sum()),3), "assessed_fraction": round(1-unknown_fraction,4),
               "inspect_water": sum(r["status"] == "inspect_water" for r in rows),
               "resolve_uncertainty": sum(r["status"] == "resolve_uncertainty" for r in rows),
               "no_signal": sum(r["status"] == "no_signal" for r in rows)}
    result = {"schema_version": "1.0", "engine": {"name": "FieldWatch", "policy": POLICY, "opencv": cv2.__version__, "cool_verified": False},
              "generated_at": datetime.now(timezone.utc).isoformat(), "name": str(name)[:120],
              "source": {"sha256": raster.sha256, "observed_on": observed_on, "bounds": bounds,
                         "width": raster.dimensions[1], "height": raster.dimensions[0], "crs": str(raster.crs),
                         "transform": list(raster.transform)[:6]},
              "reference": {"sha256": reference.sha256, "observed_on": reference_on, "interval_days": (current_date-reference_date).days,
                            "matching_acquisition_user_confirmed": True} if reference else None,
              "zone_basis": "user-provided polygons; crop/ownership not verified" if zones is not None else "illustrative 3×3 survey grid; not farm boundaries or a cropland mask",
              "summary": summary, "zones": rows, "policy": policy, "reference_policy": previous_policy, "trace": steps,
              "limitations": ["Water-like radar evidence is not proof of flood damage, water depth, soil waterlogging, crop loss or field safety.",
                  "No crop mask, terrain shadow mask or vegetation exclusion layer is applied in this version; errors can occur outside uncertain pixels too.",
                  "Permanent water, intentional irrigation and paddy fields may produce water signals. Confirm context before acting.",
                  "Do not infer uninterrupted flooding between acquisition dates; no real-time monitoring is running.",
                  "Area uses pixel centers and row-wise geodesic pixel-area estimates; small/boundary-crossing fields require review."],
              "images": {"radar": radar_preview(raster), "evidence": overlay(classes),
                         "earlier": radar_preview(reference) if reference else None,
                         "earlier_evidence": overlay(before) if before is not None else None},
              "elapsed_ms": round((time.perf_counter()-start)*1000)}
    return result


def export_report(result):
    """Exports are potentially sensitive despite containing no raster payload."""
    return {k:v for k,v in result.items() if k != "images"}

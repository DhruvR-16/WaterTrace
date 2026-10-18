"""Keep image-boundary coverage separate from classification assessability."""
from copy import deepcopy

from affine import Affine
import numpy as np
from pyproj import Transformer
import pytest
from rasterio.io import MemoryFile

from inundra.decisions import review_decision
from inundra.engine import BOUNDARY_TOLERANCE_PIXELS, default_zones, read_raster, summarize_zones
from inundra.lab import run_case


@pytest.fixture(params=['EPSG:4326', 'EPSG:32646'])
def raster(request):
    transform = Affine(.0001, 0, 92, 0, -.0001, 26) if request.param == 'EPSG:4326' else Affine(10, 0, 400000, 0, -10, 2900000)
    data = np.empty((2, 96, 96), np.float32); data[0] = -7; data[1] = -13
    with MemoryFile() as memory:
        with memory.open(driver='GTiff', width=96, height=96, count=2, dtype='float32',
                         crs=request.param, transform=transform) as dst:
            dst.write(data)
        return read_raster(memory.read())


def zone_at(raster, bounds, class_value=1):
    left, top, right, bottom = bounds
    to_geo = Transformer.from_crs(raster.crs, 'EPSG:4326', always_xy=True)
    ring = [to_geo.transform(*(raster.transform @ point)) for point in
            ((left, top), (right, top), (right, bottom), (left, bottom), (left, top))]
    collection = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'id': 'edge', 'crop': 'unknown'},
         'geometry': {'type': 'Polygon', 'coordinates': [ring]}}]}
    return summarize_zones(raster, np.full((96, 96), class_value, np.uint8), collection)[0]


@pytest.mark.parametrize('bounds', [(-.5, 10, 86, 90), (10, -.5, 90, 86),
                                    (10, 10, 96.5, 90), (10, 10, 90, 96.5)])
def test_less_than_one_percent_outside_any_edge_withholds_whole_zone(raster, bounds):
    zone = zone_at(raster, bounds)
    support = zone['spatial_support']
    assert support['scene_clipped'] is True
    assert .99 < support['scene_overlap_fraction'] < 1
    assert zone['coverage'] == 1  # Every included pixel assessed; boundary still incomplete.
    assert zone['status'] == 'resolve_uncertainty'
    assert any('outside the scene' in reason for reason in zone['reasons'])
    assert review_decision(zone, False)['level'] == 'insufficient_evidence'


def test_touching_scene_edges_and_default_sectors_are_not_false_clipping(raster):
    zone = zone_at(raster, (0, 0, 96, 96))
    assert zone['spatial_support']['scene_clipped'] is False
    assert zone['spatial_support']['scene_overlap_fraction'] == 1
    assert review_decision(zone, False)['level'] == 'low_signal'
    zones = summarize_zones(raster, np.ones((96, 96), np.uint8), default_zones(raster))
    assert all(not row['spatial_support']['scene_clipped'] for row in zones)


def test_coordinate_roundoff_tolerance_is_not_a_missing_area_threshold(raster):
    zone = zone_at(raster, (10, 10, 96+BOUNDARY_TOLERANCE_PIXELS/10, 90))
    assert zone['spatial_support']['scene_clipped'] is False
    assert zone['spatial_support']['boundary_tolerance_pixels'] == 1e-7


def test_rounded_fraction_cannot_clear_explicit_clipping_gate(raster):
    zone = zone_at(raster, (10, 10, 96+BOUNDARY_TOLERANCE_PIXELS*2, 90))
    support = zone['spatial_support']
    assert support['scene_overlap_fraction'] == 1  # Eight-decimal display rounding.
    assert support['scene_clipped'] is True
    zone['reasons'] = []  # Gate must not depend on English message matching.
    decision = review_decision(zone, False)
    assert decision['level'] == 'insufficient_evidence'
    assert decision['policy'] == 'review-gates-v3'


def test_mostly_outside_boundary_is_not_confused_with_assessed_pixel_fraction(raster):
    zone = zone_at(raster, (-100, 10, 20, 90))
    support = zone['spatial_support']
    assert support['scene_overlap_fraction'] == pytest.approx(1/6, abs=1e-8)
    assert support['fraction_basis'] == 'planar_polygon_area_in_raster_grid'
    assert zone['coverage'] == 1 and zone['uncertain_ha'] == 0
    assert review_decision(zone, False)['level'] == 'insufficient_evidence'


def test_complete_boundary_can_still_have_no_assessable_pixels(raster):
    zone = zone_at(raster, (10, 10, 80, 80), class_value=0)
    assert zone['spatial_support']['scene_clipped'] is False
    assert zone['spatial_support']['scene_overlap_fraction'] == 1
    assert zone['coverage'] == 0 and zone['water_observed_ha'] == 0
    assert review_decision(zone, False)['level'] == 'insufficient_evidence'


def test_partial_zone_lab_uses_actual_pipeline_and_preserves_measurements():
    report = run_case('partial-zone')
    zone = report['zones'][0]
    assert report['lab']['kind'] == 'synthetic'
    assert all(check['passed'] for check in report['lab']['checks'])
    assert zone['pixels'] > 25 and zone['coverage'] > .7
    assert zone['water_observed_ha'] > 0
    assert zone['decision']['level'] == 'insufficient_evidence'
    # Human crop context cannot override a missing image edge.
    paddy = deepcopy(zone); paddy['crop'] = 'rice'
    assert review_decision(paddy, False)['level'] == 'insufficient_evidence'

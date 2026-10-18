"""Geographic handoff contracts, including browser/CLI serialization parity."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess

from affine import Affine
import numpy as np
import pytest
from rasterio.io import MemoryFile
from shapely.geometry import shape

from fieldwatch.cli import main
from fieldwatch.engine import default_zones, read_raster
from fieldwatch.exports import geojson_export
from fieldwatch.lab import run_case, synthetic_inputs
from fieldwatch.service import run_analysis


CASES = ['new-water', 'repeat-water', 'missing-earlier', 'paddy-context',
         'polarization-conflict', 'tiny-zone']


@pytest.mark.parametrize('identifier', CASES)
def test_export_preserves_measurements_and_gates_without_images(identifier):
    report = run_case(identifier)
    before = deepcopy(report)
    exported = json.loads(json.dumps(geojson_export(report), allow_nan=False))
    assert exported['type'] == 'FeatureCollection'
    assert exported['fieldwatch']['lab'] == report['lab']
    assert exported['fieldwatch']['source'] == report['source']
    assert exported['fieldwatch']['policy'] == report['policy']
    assert len(exported['features']) == len(report['zones'])
    for feature, zone in zip(exported['features'], report['zones']):
        props = feature['properties']
        assert shape(feature['geometry']).equals(shape(zone['geometry']))
        assert shape(feature['geometry']).exterior.is_ccw
        assert shape(feature['geometry']).is_valid
        assert props['scene_overlap_ha'] == zone['area_ha']
        for key in ('water_observed_ha', 'uncertain_ha', 'no_water_detected_ha',
                    'new_water_candidate_ha', 'repeat_water_observed_ha', 'pixels'):
            assert props[key] == zone[key]
        assert props['review_gate'] == zone['decision']['level']
        assert props['withheld_claims'] == zone['decision']['withheld_claims']
        assert props['source_sha256'] == report['source']['sha256']
        assert props['human_outcome'] is None
        assert props['human_review_unverified'] is True
    assert 'data:image/' not in json.dumps(exported)
    assert 'pixel_geometry' not in json.dumps(exported)
    assert report == before


def test_single_observation_keeps_missing_change_distinct_from_zero():
    raw, _ = synthetic_inputs('new-water')
    exported = geojson_export(run_analysis(raw))
    assert exported['fieldwatch']['reference'] is None
    for feature in exported['features']:
        props = feature['properties']
        assert props['observed_on'] is None
        assert props['reference_on'] is None and props['reference_sha256'] is None
        assert props['new_water_candidate_ha'] is None
        assert props['repeat_water_observed_ha'] is None


def test_annotations_are_separate_and_export_does_not_alias_report():
    report = run_case('tiny-zone')
    reviews = {'tiny': {'outcome': 'water_confirmed', 'note': '<script>unverified</script>',
                        'recorded_at': '2020-01-11T00:00:00Z'},
               'not-a-zone': {'note': 'Must not leak into export'}}
    exported = geojson_export(report, reviews)
    props = exported['features'][0]['properties']
    assert props['review_gate'] == 'insufficient_evidence'
    assert props['human_outcome'] == 'water_confirmed'
    assert props['human_note'] == reviews['tiny']['note']
    assert 'Must not leak' not in json.dumps(exported)
    exported['features'][0]['geometry']['coordinates'][0][0][0] = 0
    exported['fieldwatch']['source']['sha256'] = 'changed'
    props['withheld_claims'].clear()
    assert report['zones'][0]['geometry']['coordinates'][0][0][0] == 92.004
    assert report['source']['sha256'] != 'changed'
    assert report['zones'][0]['decision']['withheld_claims']


def test_clipped_overlapping_zones_roundtrip_without_implying_full_boundary_area():
    raw, _ = synthetic_inputs('new-water')
    # Both polygons contain the entire scene but extend beyond its west edge.
    geometry = {'type': 'Polygon', 'coordinates': [[[91.999, 26], [92.0096, 26],
                [92.0096, 25.9904], [91.999, 25.9904], [91.999, 26]]]}
    zones = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'properties': {'id': name, 'name': name, 'crop': 'unknown'},
         'geometry': deepcopy(geometry)} for name in ('overlap-a', 'overlap-b')]}
    report = run_analysis(raw, zones=zones)
    exported = geojson_export(report)
    for feature in exported['features']:
        props = feature['properties']
        assert shape(feature['geometry']).equals(shape(geometry))  # Original extent, not clipped pixels.
        assert props['review_gate'] == 'insufficient_evidence'
        assert props['scene_overlap_ha'] == report['summary']['scene_area_ha']
        assert props['area_scope'] == 'scene_overlap_pixel_centers'
        assert 'Zones may overlap' in props['area_notice']
    rerun = run_analysis(raw, zones=exported)
    for actual, original in zip(rerun['zones'], report['zones']):
        for key in original.keys() - {'geometry', 'pixel_geometry'}:
            assert actual[key] == original[key]
        assert shape(actual['geometry']).equals(shape(original['geometry']))


def test_projected_raster_exports_geographic_not_pixel_or_projected_geometry():
    data = np.empty((2, 64, 64), np.float32); data[0] = -7; data[1] = -13
    with MemoryFile() as memory:
        with memory.open(driver='GTiff', width=64, height=64, count=2, dtype='float32',
                         crs='EPSG:32646', transform=Affine(10, 0, 400000, 0, -10, 2900000)) as dst:
            dst.write(data)
        raw = memory.read()
    report = run_analysis(raw)
    exported = geojson_export(report)
    for feature in exported['features']:
        for lon, lat in feature['geometry']['coordinates'][0]:
            assert 91 < lon < 93 and 25 < lat < 27
    assert exported['fieldwatch']['source']['crs'] == 'EPSG:32646'
    assert 'crs' not in exported  # Source CRS is provenance, not a GeoJSON CRS override.


@pytest.mark.parametrize('identifier', CASES)
def test_browser_and_python_exports_match_on_actual_pipeline(identifier):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is required for cross-runtime export parity.')
    report = run_case(identifier)
    reviews = {report['zones'][0]['id']: {'outcome': 'follow_up', 'note': 'पानी? Verify locally.',
               'recorded_at': '2020-01-11T00:00:00Z'}}
    script = "const m=require('./fieldwatch/static/model.js');let s='';process.stdin.setEncoding('utf8');process.stdin.on('data',v=>s+=v);process.stdin.on('end',()=>{const x=JSON.parse(s);process.stdout.write(JSON.stringify(m.geojsonExport(x.report,x.reviews)));});"
    result = subprocess.run([node, '-e', script], input=json.dumps({'report': report, 'reviews': reviews}),
                            text=True, capture_output=True, check=True, timeout=15,
                            cwd=Path(__file__).resolve().parents[1])
    assert json.loads(result.stdout) == json.loads(json.dumps(geojson_export(report, reviews)))


@pytest.mark.parametrize('format_name', ['json', 'geojson'])
def test_cli_exports_private_file_and_never_overwrites(tmp_path, format_name):
    raw, _ = synthetic_inputs('new-water')
    source = tmp_path / 'radar.tif'; source.write_bytes(raw)
    output = tmp_path / ('handoff.' + format_name)
    args = [str(source), '--date', '2020-01-10', '--output', str(output)]
    if format_name == 'geojson':
        args += ['--format', 'geojson']
    assert main(args) == 0
    initial = output.read_bytes()
    exported = json.loads(initial)
    assert 'images' not in exported
    if format_name == 'geojson':
        assert exported['type'] == 'FeatureCollection'
        assert len(exported['features']) == 9
    else:
        assert exported['schema_version'] == '1.0'
    if os.name == 'posix':
        assert output.stat().st_mode & 0o777 == 0o600
    assert main(args) == 3
    assert output.read_bytes() == initial


def test_geojson_cli_preserves_custom_polygons_and_pair_metadata(tmp_path):
    raw, options = synthetic_inputs('missing-earlier')
    source = tmp_path / 'current.tif'; source.write_bytes(raw)
    reference = tmp_path / 'earlier.tif'; reference.write_bytes(options['reference_raw'])
    zones = default_zones(read_raster(raw))
    zones['features'] = zones['features'][:2]
    zone_file = tmp_path / 'zones.geojson'; zone_file.write_text(json.dumps(zones))
    output = tmp_path / 'handoff.geojson'
    assert main([str(source), '--date', options['observed_on'], '--reference', str(reference),
                 '--reference-date', options['reference_on'], '--same-orbit', '--zones', str(zone_file),
                 '--format', 'geojson', '--output', str(output)]) == 0
    exported = json.loads(output.read_text())
    assert len(exported['features']) == 2
    assert exported['fieldwatch']['reference']['interval_days'] == 9
    assert all(f['properties']['new_water_candidate_ha'] == 0 for f in exported['features'])

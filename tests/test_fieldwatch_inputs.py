"""Malformed geographic input fails closed across web, CLI and direct analysis."""
from copy import deepcopy
import json

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest

from fieldwatch import catalog
from fieldwatch.cli import main
from fieldwatch.engine import InvalidRaster
from fieldwatch.lab import synthetic_inputs
from fieldwatch.main import app, parse_zones
from fieldwatch.service import run_analysis
from fieldwatch.zone_input import load_zones, MAX_JSON_DEPTH, MAX_ZONE_BYTES


def document():
    return {'type': 'FeatureCollection', 'features': [{'type': 'Feature',
        'properties': {'id': 'field', 'name': 'खेत 🌾', 'crop': 'rice'},
        'geometry': {'type': 'Polygon', 'coordinates': [[[92.001, 25.999],
            [92.008, 25.999], [92.008, 25.992], [92.001, 25.992], [92.001, 25.999]]]}}]}


def malformed_documents():
    base = json.dumps(document())
    surrogate = document(); surrogate['features'][0]['properties']['name'] = '\ud800'
    huge = document(); huge['features'][0]['geometry']['coordinates'][0][0][0] = 10**400
    return {
        'surrogate-name': json.dumps(surrogate),
        'surrogate-key': base[:-1] + ',"\\ud800":0}',
        'huge-coordinate': json.dumps(huge),
        'duplicate-type': base[:-1] + ',"type":"FeatureCollection"}',
        'duplicate-property': base.replace('"id": "field"', '"id":"field","id":"other"'),
        'nan-metadata': base[:-1] + ',"extra":NaN}',
        'infinity-metadata': base[:-1] + ',"extra":Infinity}',
        'overflow-float': base[:-1] + ',"extra":1e400}',
        'deep-metadata': base[:-1] + ',"extra":' + '['*64 + '0' + ']'*64 + '}',
        'parser-recursion': '['*10000 + '0' + ']'*10000,
    }


@pytest.mark.parametrize('case', list(malformed_documents()))
def test_upload_rejects_malformed_inputs_then_accepts_next_valid_request(case):
    raw, _ = synthetic_inputs('new-water')
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/analyze', files={'current': ('scene.tif', raw)},
                               data={'zones': malformed_documents()[case]})
        assert response.status_code == 422
        assert isinstance(response.json()['detail'], str)
        assert 'Traceback' not in response.text
        valid = client.post('/api/analyze', files={'current': ('scene.tif', raw)},
                            data={'zones': json.dumps(document())})
        assert valid.status_code == 200
        assert valid.json()['zones'][0]['name'] == 'खेत 🌾'


@pytest.mark.parametrize('case', list(malformed_documents()))
def test_cli_rejects_malformed_zone_files_without_creating_output(tmp_path, capsys, case):
    raw, _ = synthetic_inputs('new-water')
    source = tmp_path/'current.tif'; source.write_bytes(raw)
    zones = tmp_path/'zones.geojson'; zones.write_text(malformed_documents()[case], encoding='utf-8')
    output = tmp_path/'report.json'
    assert main([str(source), '--date', '2020-01-10', '--zones', str(zones), '--output', str(output)]) == 2
    assert not output.exists()
    assert 'Traceback' not in capsys.readouterr().err


@pytest.mark.parametrize('payload', [b'\xff', b'{"type":"FeatureCollection","extra":"\xff"}',
                                   b'\xff\xfe' + '{"type":"FeatureCollection"}'.encode('utf-16-le')])
def test_non_utf8_inputs_rejected_by_parser_and_example_endpoint(tmp_path, monkeypatch, payload):
    with pytest.raises(InvalidRaster):
        load_zones(payload)
    monkeypatch.setattr(catalog, 'RASTERS', tmp_path)
    (tmp_path/'S1Hand').mkdir()
    raw, _ = synthetic_inputs('new-water')
    (tmp_path/'S1Hand/India_285297_S1Hand.tif').write_bytes(raw)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/examples/india/analyze', content=payload)
        assert response.status_code == 422


def test_shared_parser_preserves_legitimate_unicode_and_rejects_oversize():
    data = document()
    for ascii_only in (True, False):
        assert load_zones(json.dumps(data, ensure_ascii=ascii_only)) == data
    with pytest.raises(InvalidRaster, match='200 KB'):
        load_zones(b' '*(MAX_ZONE_BYTES+1))
    with pytest.raises(HTTPException) as exc:
        parse_zones(b' '*(MAX_ZONE_BYTES+1))
    assert exc.value.status_code == 413


def test_depth_boundary_is_explicit_and_independent_of_python_recursion_limit():
    for depth in (MAX_JSON_DEPTH-1, MAX_JSON_DEPTH):
        value = document(); nested = 0
        for _ in range(depth):
            nested = [nested]
        value['extra'] = nested
        if depth == MAX_JSON_DEPTH-1:
            assert load_zones(json.dumps(value)) == value
        else:
            with pytest.raises(InvalidRaster, match='32 levels'):
                load_zones(json.dumps(value))


@pytest.mark.parametrize('field', ['id', 'name', 'crop'])
def test_direct_analysis_rejects_nonserializable_text(field):
    raw, _ = synthetic_inputs('new-water'); zones = document()
    zones['features'][0]['properties'][field] = '\ud800'
    with pytest.raises(InvalidRaster):
        run_analysis(raw, zones=zones)


def test_direct_analysis_rejects_numeric_conversion_overflow():
    raw, _ = synthetic_inputs('new-water'); zones = document()
    zones['features'][0]['geometry']['coordinates'][0][0][0] = 10**400
    with pytest.raises(InvalidRaster):
        run_analysis(raw, zones=zones)


def test_only_validated_geometry_is_retained_without_mutating_input():
    raw, _ = synthetic_inputs('new-water'); zones = document()
    zones['features'][0]['geometry']['foreign'] = {'unrelated': 'do not forward'}
    before = deepcopy(zones)
    result = run_analysis(raw, zones=zones)
    geometry = result['zones'][0]['geometry']
    assert set(geometry) == {'type', 'coordinates'}
    assert geometry['coordinates'] == zones['features'][0]['geometry']['coordinates']
    assert zones == before
    geometry['coordinates'][0][0][0] = 0
    assert zones == before

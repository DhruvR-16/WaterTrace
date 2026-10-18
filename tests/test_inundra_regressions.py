"""Regression tests for malformed requests and recoverable example failures."""
import warnings

import numpy as np
import pytest
from affine import Affine
from fastapi.testclient import TestClient

from inundra import catalog
from inundra.engine import InvalidRaster, default_zones, read_raster
from inundra.lab import encode, synthetic_inputs
from inundra.main import app
from inundra.service import run_analysis


@pytest.mark.parametrize('origin', ['http://[', 'null', 'https://testserver', 'http://testserver/path', 'http://user@testserver'])
def test_invalid_or_cross_origin_rejected_without_server_error(origin):
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post('/api/lab/new-water/run', headers={'Origin':origin})
        assert response.status_code == 403


def test_same_origin_allowed():
    with TestClient(app) as client:
        assert client.post('/api/lab/new-water/run', headers={'Origin':'http://testserver'}).status_code == 200


@pytest.mark.parametrize('zones', ['null', 'false', '[]', '{"type":"FeatureCollection","features":[]}'])
def test_invalid_zone_payload_never_falls_back_to_demo_grid(zones):
    raw,_ = synthetic_inputs('new-water')
    with TestClient(app) as client:
        response = client.post('/api/analyze', files={'current':('scene.tif',raw)}, data={'zones':zones})
        assert response.status_code == 422


def test_paddy_whitespace_stays_in_context_queue():
    data=np.empty((2,96,96),np.float32);data[0]=-7;data[1]=-13
    raw=encode(data);zones=default_zones(read_raster(raw))
    for feature in zones['features']:feature['properties']['crop']=' Rice '
    result=run_analysis(raw,zones=zones)
    assert all(z['status']=='resolve_uncertainty' for z in result['zones'])


@pytest.mark.parametrize('mutation', ['unclosed','wrong_type','infinite'])
def test_malformed_feature_rejected(mutation):
    raw,_=synthetic_inputs('new-water');zones=default_zones(read_raster(raw))
    feature=zones['features'][0]
    if mutation=='unclosed':feature['geometry']['coordinates'][0].pop()
    if mutation=='wrong_type':feature['type']='NotAFeature'
    if mutation=='infinite':feature['geometry']['coordinates'][0][0]=(float('inf'),26)
    with pytest.raises(InvalidRaster):run_analysis(raw,zones=zones)


def test_longitude_outside_geographic_domain_rejected():
    data=np.full((2,96,96),-30,np.float32)
    with pytest.raises(InvalidRaster):read_raster(encode(data,Affine(.0001,0,292,0,-.0001,26)))


@pytest.mark.parametrize('mutation', ['numeric_strings', 'booleans'])
def test_coordinate_coercion_cannot_leave_invalid_geometry_in_reports(mutation):
    raw,_=synthetic_inputs('new-water');zones=default_zones(read_raster(raw))
    ring=zones['features'][0]['geometry']['coordinates'][0]
    ring=[list(point) for point in ring]
    if mutation=='numeric_strings':
        ring=[[str(value) for value in point] for point in ring]
    else:
        ring[0][0]=ring[-1][0]=True
    zones['features'][0]['geometry']['coordinates'][0]=ring
    with pytest.raises(InvalidRaster,match='lon/lat'):
        run_analysis(raw,zones=zones)


def test_nan_preview_does_not_emit_numeric_warning():
    data=np.full((2,96,96),-30,np.float32);data[:,30:40,30:40]=np.nan
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        run_analysis(encode(data))


def test_corrupt_optional_optical_does_not_discard_valid_radar(tmp_path,monkeypatch):
    monkeypatch.setattr(catalog,'RASTERS',tmp_path)
    (tmp_path/'S1Hand').mkdir();(tmp_path/'S2Hand').mkdir()
    raw,_=synthetic_inputs('new-water')
    (tmp_path/'S1Hand/India_285297_S1Hand.tif').write_bytes(raw)
    (tmp_path/'S2Hand/India_285297_S2Hand.tif').write_bytes(b'broken optical file')
    with TestClient(app,raise_server_exceptions=False) as client:
        response=client.post('/api/examples/india/analyze')
        assert response.status_code==200
        assert response.json()['images']['optical'] is None
        assert response.json()['context']['optical_status']=='unavailable'


def test_cli_null_zones_do_not_create_demo_report(tmp_path):
    from inundra.cli import main
    raw,_=synthetic_inputs('new-water')
    source=tmp_path/'radar.tif';source.write_bytes(raw)
    zones=tmp_path/'zones.json';zones.write_text('null')
    output=tmp_path/'report.json'
    assert main([str(source),'--date','2020-01-01','--zones',str(zones),'--output',str(output)])==2
    assert not output.exists()

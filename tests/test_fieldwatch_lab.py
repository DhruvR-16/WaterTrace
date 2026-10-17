import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from rasterio.io import MemoryFile

from fieldwatch import catalog
from fieldwatch.engine import InvalidRaster, read_raster
from fieldwatch.lab import CASES, run_case, score_labels, synthetic_inputs
from fieldwatch.main import app
from fieldwatch.decisions import review_decision


SYNTHETIC=[item['id'] for item in CASES if item['kind']=='synthetic']


@pytest.mark.parametrize('identifier',SYNTHETIC)
def test_all_contract_exercises_run_real_pipeline(identifier):
    result=run_case(identifier)
    assert result['lab']['kind']=='synthetic'
    assert all(check['passed'] for check in result['lab']['checks'])
    assert 'not real satellite' in result['lab']['notice']
    json.dumps(result,allow_nan=False)


def test_unknown_is_not_free_in_error_map():
    classes=np.array([[0,2,1,2]],np.uint8)
    truth=np.array([[1,0,0,-1]],np.int8)
    stats,images=score_labels(classes,truth)
    assert stats['missed_water_pixels']==1 and stats['unknown_water_pixels']==1
    assert stats['false_positive_pixels']==1 and stats['labeled_pixels']==3
    assert stats['recall']==0 and stats['precision']==0
    assert all(value.startswith('data:image/png;base64,') for value in images.values())


def test_no_positive_truth_has_undefined_recall():
    stats,_=score_labels(np.ones((2,2),np.uint8),np.zeros((2,2),np.int8))
    assert stats['recall'] is None and stats['precision'] is None and stats['iou'] is None


@pytest.mark.parametrize('truth',[np.zeros((2,3)),np.full((2,2),2),np.full((2,2),np.nan)])
def test_bad_reference_rejected(truth):
    with pytest.raises(InvalidRaster):score_labels(np.zeros((2,2),np.uint8),truth)


def test_missing_earlier_never_establishes_dry_baseline():
    result=run_case('missing-earlier')
    assert result['summary']['water_observed_ha']>0
    assert all(z['new_water_candidate_ha']==0 for z in result['zones'])


def test_repeat_water_is_not_permanence_proof():
    result=run_case('repeat-water')
    decisions=[z['decision'] for z in result['zones'] if z['decision']['level']=='repeat_observation']
    assert decisions and all('do not establish permanent' in d['next_step'] for d in decisions)


def test_tiny_polygon_blocks_whole_field_conclusion():
    zone=run_case('tiny-zone')['zones'][0]
    assert zone['pixels']==4 and zone['water_observed_ha']>0
    assert zone['decision']['level']=='insufficient_evidence'


def test_labels_do_not_change_inference_or_decisions(tmp_path,monkeypatch):
    monkeypatch.setattr(catalog,'RASTERS',tmp_path)
    (tmp_path/'S1Hand').mkdir();(tmp_path/'LabelHand').mkdir()
    raw,_=synthetic_inputs('new-water')
    (tmp_path/'S1Hand/India_80221_S1Hand.tif').write_bytes(raw)
    raster=read_raster(raw)
    def write_truth(value,transform=None):
        with MemoryFile() as mem:
            with mem.open(driver='GTiff',width=96,height=96,count=1,dtype='int8',crs=raster.crs,transform=transform or raster.transform,nodata=-1) as dst:
                dst.write(np.full((1,96,96),value,np.int8))
            (tmp_path/'LabelHand/India_80221_LabelHand.tif').write_bytes(mem.read())
    write_truth(0);dry=run_case('india-stronger')
    write_truth(1);wet=run_case('india-stronger')
    assert dry['zones']==wet['zones'] and dry['summary']==wet['summary']
    assert dry['images']['evidence']==wet['images']['evidence']
    assert dry['lab']['metrics']!=wet['lab']['metrics']
    assert dry['lab']['reference_sha256']!=wet['lab']['reference_sha256']
    write_truth(0, raster.transform @ raster.transform.translation(1,0))
    with pytest.raises(InvalidRaster,match='grid'):run_case('india-stronger')


def test_display_rounding_does_not_clear_coverage_gate():
    zone={'pixels':10000,'coverage':.7,'crop':'','water_fraction':.5,
          'reasons':['More than 30% of this zone is uncertain or unobserved.']}
    assert review_decision(zone,False)['level']=='insufficient_evidence'


@pytest.mark.parametrize('identifier',SYNTHETIC)
def test_lab_api(identifier):
    with TestClient(app) as client:
        response=client.post('/api/lab/'+identifier+'/run')
        assert response.status_code==200
        assert all(c['passed'] for c in response.json()['lab']['checks'])


def test_lab_rejections_do_not_leak_stale_report():
    with TestClient(app) as client:
        result=client.post('/api/lab/shifted-grid/run').json()
        assert result['kind']=='rejection_check' and 'images' not in result and 'summary' not in result
        assert client.post('/api/lab/unknown/run').status_code==404
        assert client.post('/api/lab/new-water/run',json={'path':'anything'}).status_code==422


def test_missing_lab_data_actionable(tmp_path,monkeypatch):
    monkeypatch.setattr(catalog,'RASTERS',tmp_path)
    with TestClient(app) as client:
        items=client.get('/api/lab').json()
        assert all(c['available'] for c in items if c['kind']=='synthetic')
        assert all(not c['available'] for c in items if c['kind']=='real_replay')
        result=client.post('/api/lab/india-stronger/run')
        assert result.status_code==503 and '--split lab' in result.json()['detail']

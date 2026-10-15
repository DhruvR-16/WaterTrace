import asyncio
from datetime import date
import json

from affine import Affine
import numpy as np
import pytest
import rasterio
from rasterio.io import MemoryFile
from fastapi.testclient import TestClient

from fieldwatch.engine import InvalidRaster, classify, compare, default_zones, geographic_bounds, pixel_areas, read_raster, summarize_zones
from fieldwatch.limits import RequestLimits
from fieldwatch.main import app
from fieldwatch.service import export_report, run_analysis
from scripts.evaluate_fieldwatch import evaluate, metrics, rates


def tif(*, data=None, width=96, height=96, count=2, crs="EPSG:4326", transform=None, nodata=-9999):
    if data is None:
        data=np.empty((count,height,width),np.float32)
        data[:,:,:]=np.array([-7,-13][:count])[:,None,None]
        data[:,:,:width//3]=np.array([-29,-35][:count])[:,None,None]
    with MemoryFile() as memory:
        with memory.open(driver="GTiff",width=data.shape[2],height=data.shape[1],count=data.shape[0],dtype="float32",crs=crs,
                         transform=transform or Affine(.0001,0,92,0,-.0001,26),nodata=nodata) as out:
            out.write(data)
        return memory.read()


@pytest.fixture
def raster():
    return read_raster(tif())


def test_water_land_and_unknown(raster):
    c,p=classify(raster)
    assert c[20,10]==2
    assert c[20,70]==1
    assert (c[0]==0).all()
    assert p["agreement_margin_db"]==1.5


def test_invalid_neighborhood_never_filled():
    data=np.full((2,64,64),-35,np.float32); data[:,20:30,20:30]=-9999
    c,_=classify(read_raster(tif(data=data)))
    assert (c[19:31,19:31]==0).all()


def test_polarizations_disagree():
    data=np.empty((2,64,64),np.float32);data[0]=-6;data[1]=-35
    c,_=classify(read_raster(tif(data=data)))
    assert not (c==2).any() and not (c==1).any()


@pytest.mark.parametrize("raw",[b"",b"not a tiff",b'<VRTDataset rasterXSize="96"/>',b'II*\x00broken'])
def test_non_tiff_rejected(raw):
    with pytest.raises(InvalidRaster):read_raster(raw)


@pytest.mark.parametrize("kwargs",[{"count":1},{"crs":None},{"width":10,"height":10},
    {"transform":Affine(.0001,0,92,0,.0001,26)}, {"transform":Affine(.1,0,92,0,-.1,26)}])
def test_unsupported_raster(kwargs):
    with pytest.raises(InvalidRaster):read_raster(tif(**kwargs))


def test_linear_units_rejected():
    with pytest.raises(InvalidRaster,match="dB"):
        read_raster(tif(data=np.ones((2,64,64),np.float32)))


def test_geographic_area_not_degrees_squared(raster):
    a=pixel_areas(raster)
    assert .009 < a[0,0] < .012
    assert 80 < a.sum() < 110
    assert geographic_bounds(raster)==pytest.approx([92,25.9904,92.0096,26])


def test_reference_alignment_rejected(raster):
    other=read_raster(tif(transform=Affine(.0001,0,93,0,-.0001,26)))
    with pytest.raises(InvalidRaster,match="grid"):compare(raster,other)


def test_real_change_contract(raster):
    before_data=np.full((2,96,96),-7,np.float32);before_data[1]=-13
    previous=read_raster(tif(data=before_data))
    c,new,repeat,_,_,_=compare(raster,previous)
    assert new[20,10] and not repeat.any()
    result=run_analysis(tif(),reference_raw=tif(data=before_data),observed_on="2020-01-10",reference_on="2020-01-01",same_orbit=True)
    assert result["reference"]["interval_days"]==9
    assert sum(z["new_water_candidate_ha"] for z in result["zones"])>0


@pytest.mark.parametrize("kwargs",[
    {"reference_on":"2020-01-10","observed_on":"2020-01-01","same_orbit":True},
    {"reference_on":"2020-01-01","observed_on":"2020-01-01","same_orbit":True},
    {"reference_on":"2020-01-01","observed_on":"2020-01-10","same_orbit":False},
    {"reference_on":None,"observed_on":"2020-01-10","same_orbit":True},
])
def test_invalid_pair_metadata(kwargs):
    with pytest.raises(InvalidRaster):run_analysis(tif(),reference_raw=tif(),**kwargs)


@pytest.mark.parametrize("observed_on",["not-a-date","2999-01-01"])
def test_invalid_current_date(observed_on):
    with pytest.raises(InvalidRaster):run_analysis(tif(),observed_on=observed_on)


def test_no_reference_no_flood_claim():
    result=run_analysis(tif())
    assert result["reference"] is None
    assert all(z["new_water_candidate_ha"] is None for z in result["zones"])
    assert any(t["action"]=="withhold_change_claim" for t in result["trace"])
    assert "images" not in export_report(result)
    json.dumps(result,allow_nan=False)


def test_zone_accounting(raster):
    c,_=classify(raster);rows=summarize_zones(raster,c)
    assert len(rows)==9
    assert sum(r["pixels"] for r in rows)==96*96
    for row in rows:
        assert row["area_ha"]==pytest.approx(row["water_observed_ha"]+row["uncertain_ha"]+row["no_water_detected_ha"],abs=.002)


def test_unknown_gets_own_queue(raster):
    rows=summarize_zones(raster,np.zeros(raster.dimensions,np.uint8))
    assert all(r["status"]=="resolve_uncertainty" for r in rows)


def test_paddy_context_is_flagged(raster):
    zones=default_zones(raster);zones["features"][0]["properties"]["crop"]="rice"
    rows=summarize_zones(raster,np.ones(raster.dimensions,np.uint8),zones)
    assert next(r for r in rows if r["id"]=="sector-1")["status"]=="resolve_uncertainty"


@pytest.mark.parametrize("zones",[{}, {"type":"FeatureCollection","features":[]},
    {"type":"FeatureCollection","features":[{"geometry":{"type":"Point","coordinates":[92,26]}}]}])
def test_bad_zones(raster,zones):
    with pytest.raises(InvalidRaster):summarize_zones(raster,np.zeros(raster.dimensions,np.uint8),zones)


def test_duplicate_zone_ids(raster):
    zones=default_zones(raster);zones["features"][1]["properties"]["id"]="sector-1"
    with pytest.raises(InvalidRaster):summarize_zones(raster,np.zeros(raster.dimensions,np.uint8),zones)


@pytest.mark.parametrize("properties", [None, [], "invalid", 12])
def test_bad_zone_properties_are_validation_errors(raster, properties):
    zones=default_zones(raster);zones["features"][0]["properties"]=properties
    with pytest.raises(InvalidRaster):summarize_zones(raster,np.zeros(raster.dimensions,np.uint8),zones)


def test_projected_grid_and_rectangular_preview():
    raster=read_raster(tif(width=128,height=64,crs="EPSG:32646",transform=Affine(10,0,400000,0,-10,2900000)))
    assert pixel_areas(raster).sum()==pytest.approx(81.92,rel=.002)
    classes,_=classify(raster)
    assert sum(z['pixels'] for z in summarize_zones(raster,classes))==128*64


def evaluation_fixture(tmp_path, *, rejected=False, shifted=False):
    root=tmp_path/'data/flood_events/HandLabeled'
    (root/'S1Hand').mkdir(parents=True);(root/'LabelHand').mkdir()
    raw=tif(data=np.full((2,96,96),-9999,np.float32)) if rejected else tif()
    (root/'S1Hand'/'Example_1.tif').write_bytes(raw)
    label=tif(data=np.ones((1,96,96),np.float32),transform=Affine(.0001,0,93 if shifted else 92,0,-.0001,26))
    (root/'LabelHand'/'Example_1.tif').write_bytes(label)
    (tmp_path/'test-manifest.json').write_text(json.dumps({'pairs':[['Example_1.tif','Example_1.tif']]}))


def test_rejected_scene_remains_in_benchmark_denominator(tmp_path):
    evaluation_fixture(tmp_path,rejected=True)
    report=evaluate(tmp_path,'test')
    assert report['rejected_chips']==1
    for method in report['pooled'].values():
        assert method['labeled']==96*96 and method['recall']==0 and method['assessed_fraction']==0


def test_benchmark_rejects_shifted_label_grid(tmp_path):
    evaluation_fixture(tmp_path,shifted=True)
    with pytest.raises(ValueError,match='alignment'):evaluate(tmp_path,'test')


def test_disconnected_upload_releases_admission_slot():
    async def scenario():
        async def downstream(*args):raise AssertionError('disconnected body must not reach parser')
        middleware=RequestLimits(downstream)
        async def receive():return {'type':'http.disconnect'}
        async def send(message):pass
        for _ in range(3):
            await middleware({'type':'http','method':'POST','headers':[]},receive,send)
        assert middleware.slots.acquire(False) and middleware.slots.acquire(False)
    asyncio.run(scenario())


def test_unknown_predictions_count_as_missed_water():
    truth=np.array([[1,1,0,-1]]);pred=np.zeros((1,4),bool)
    counts=metrics(pred,truth,pred)
    assert counts["fn"]==2 and counts["unknown_water"]==2
    assert rates(counts)["recall"]==0 and rates(counts)["assessed_fraction"]==0


def test_api_upload_and_security_headers():
    with TestClient(app) as client:
        r=client.post('/api/analyze',files={'current':('sample.tif',tif(),'image/tiff')},data={'observed_on':'2020-01-01'})
        assert r.status_code==200,r.text
        assert r.json()["source"]["observed_on"]=="2020-01-01"
        assert r.headers["X-Frame-Options"]=="DENY"
        assert "default-src 'self'" in r.headers["Content-Security-Policy"]


def test_api_unknown_example_and_cross_origin():
    with TestClient(app) as client:
        assert client.post('/api/examples/unknown/analyze').status_code==404
        assert client.post('/api/analyze',headers={'Origin':'https://other.invalid'}).status_code==403
        assert client.post('/api/analyze',json={}).status_code==415
        assert client.post('/api/analyze',files={'current':('bad.tif',b'no')}).status_code==422


def test_nonlocal_host_is_rejected():
    with TestClient(app) as client:
        assert client.get('/api/health',headers={'Host':'untrusted.example'}).status_code==400


def test_geojson_limit_counts_utf8_bytes():
    from fieldwatch.main import parse_zones
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:parse_zones('水'*70_000)
    assert error.value.status_code==413


def test_cli_private_no_overwrite(tmp_path):
    from fieldwatch.cli import main
    source=tmp_path/'input.tif';source.write_bytes(tif())
    destination=tmp_path/'report.json'
    args=[str(source),'--date','2020-01-01','--output',str(destination)]
    assert main(args)==0
    report=json.loads(destination.read_text())
    assert 'images' not in report and report['source']['sha256']
    import os
    if os.name=='posix':assert destination.stat().st_mode & 0o777==0o600
    original=destination.read_bytes()
    assert main(args)==3 and destination.read_bytes()==original


def test_cli_invalid_input_does_not_create_report(tmp_path):
    from fieldwatch.cli import main
    source=tmp_path/'bad.tif';source.write_bytes(b'not a raster')
    output=tmp_path/'result.json'
    assert main([str(source),'--date','2020-01-01','--output',str(output)])==2
    assert not output.exists()


def test_api_duplicate_fields():
    with TestClient(app) as client:
        r=client.post('/api/analyze',files=[('current',('a.tif',tif())),('current',('b.tif',tif()))])
        assert r.status_code==422


def test_private_errors_do_not_escape(monkeypatch):
    import fieldwatch.main as module
    def fail(*a,**kw):raise RuntimeError('secret private filesystem path')
    monkeypatch.setattr(module,'run_analysis',fail)
    with TestClient(app) as client:
        r=client.post('/api/analyze',files={'current':('private-name.tif',tif())})
        assert r.status_code==500 and 'secret' not in r.text and 'private-name' not in r.text


def test_stream_limit_and_slot_reuse():
    async def scenario():
        calls=[]
        async def downstream(scope,receive,send):calls.append(await receive())
        middleware=RequestLimits(downstream,max_body=4)
        async def request(body,headers=[]):
            sent=[]
            async def receive():return {'type':'http.request','body':body,'more_body':False}
            async def send(msg):sent.append(msg)
            await middleware({'type':'http','method':'POST','path':'/api/analyze','headers':headers},receive,send)
            return sent
        sent=await request(b'12345');assert sent[0]['status']==413 and not calls
        await request(b'1234');assert calls[-1]['body']==b'1234'
        sent=await request(b'12',[(b'content-length',b'3')]);assert sent[0]['status']==400
        sent=await request(b'',[(b'content-encoding',b'gzip')]);assert sent[0]['status']==415
    asyncio.run(scenario())

"""Smoke-test the local HTTP service using self-authored georeferenced radar."""
import time
import json
import httpx
import numpy as np
from rasterio.io import MemoryFile
from affine import Affine


def main():
    data=np.zeros((2,64,96),np.float32)
    data[0]=-7;data[1]=-13
    data[0,:,:32]=-29;data[1,:,:32]=-35
    with MemoryFile() as mem:
        with mem.open(driver='GTiff',width=96,height=64,count=2,dtype='float32',crs='EPSG:4326',
                      transform=Affine(.0001,0,92,0,-.0001,26),nodata=-9999) as dst:dst.write(data)
        raw=mem.read()
    with httpx.Client(base_url='http://127.0.0.1:8000',timeout=15,trust_env=False) as client:
        for attempt in range(15):
            try:
                health=client.get('/api/health');health.raise_for_status();break
            except (httpx.ConnectError,httpx.HTTPStatusError):
                if attempt==14:raise
                time.sleep(1)
        assert health.json()['opencv'].startswith('5.')
        assert health.json()['cool_verified'] is False
        response=client.post('/api/analyze',files={'current':('synthetic.tif',raw,'image/tiff')},data={'observed_on':'2020-01-01'})
        response.raise_for_status();result=response.json()
        assert result['source']['width']==96 and result['source']['height']==64
        assert len(result['zones'])==9 and result['summary']['water_observed_ha']>0
        assert result['reference'] is None
        assert 'default-src' in response.headers['content-security-policy']
        assert client.post('/api/analyze',files={'current':('bad.tif',b'not a raster')}).status_code==422
        zones={'type':'FeatureCollection','features':[{'type':'Feature',
            'properties':{'id':'field','name':'खेत 🌾'},'geometry':result['zones'][0]['geometry']}]}
        invalid_unicode=json.dumps(zones).replace(json.dumps('खेत 🌾'), '"\\ud800"')
        duplicate=json.dumps(zones)[:-1]+',"type":"FeatureCollection"}'
        for payload in (invalid_unicode, duplicate, '['*10000+'0'+']'*10000):
            rejected=client.post('/api/analyze',files={'current':('synthetic.tif',raw)},data={'zones':payload})
            assert rejected.status_code==422 and isinstance(rejected.json()['detail'],str)
        recovered=client.post('/api/analyze',files={'current':('synthetic.tif',raw)},data={'zones':json.dumps(zones)})
        recovered.raise_for_status()
        assert recovered.json()['zones'][0]['name']=='खेत 🌾'
        assert client.get('/api/health',headers={'Host':'untrusted.example'}).status_code==400
    print('Inundra HTTP smoke passed: raster decoding, malformed-input recovery, Unicode and host bounds.')


if __name__=='__main__':main()

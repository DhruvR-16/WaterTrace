"""Explicit evaluation-only replay. Labels are scored AFTER inference, never inputs.

Synthetic exercises demonstrate contracts, not geographic or model accuracy.
Real contrast cases were selected after inspecting the already exposed v1 test set.
"""
import hashlib
import numpy as np
from affine import Affine
from rasterio.io import MemoryFile

from fieldwatch import catalog
from fieldwatch.engine import InvalidRaster, classify, default_zones, read_raster
from fieldwatch.service import png, run_analysis

CASES = [
    {'id':'india-stronger','title':'India · stronger overlap','kind':'real_replay', 'chip':'India_80221','date':'2016-08-12',
     'question':'Why must a stronger result be shown alongside failure cases from the same region?',
     'lesson':'Selected as the highest-IoU India chip in the exposed v1 test results. This is a contrast case, not evidence that all Indian scenes perform this well.'},
    {'id':'india-false-alarm','title':'India · false alarms','kind':'real_replay', 'chip':'India_44475','date':'2016-08-12',
     'question':'What happens when dark surfaces look like water but the labeled chip contains no water?',
     'lesson':'Precision alone is undefined when nothing is predicted. Inspect false-positive pixel counts and reference-label coverage; do not infer the physical cause from this image alone.'},
    {'id':'pakistan-mixed','title':'Pakistan · weak overlap','kind':'real_replay','chip':'Pakistan_167553','date':'2017-06-28',
     'question':'Can a water-looking map still be wrong?',
     'lesson':'This selected chip has weak overlap with independent water labels. Ground context and better modeling are needed; a confident-looking overlay is not validation.'},
    {'id':'sri-lanka-missed','title':'Sri Lanka · missed water','kind':'real_replay','chip':'Sri-Lanka_534068','date':'2017-05-30',
     'question':'Does abstaining hide a large missed-water problem?',
     'lesson':'Unknown labeled water is counted as missed water. This severe recall failure is intentionally visible, not removed from evaluation.'},
    {'id':'new-water','title':'New-water candidate','kind':'synthetic', 'question':'Does a matched earlier/current pair expose a new-water candidate?', 'lesson':'Detect a change candidate, while withholding crop-damage and duration claims.'},
    {'id':'repeat-water','title':'Water at both dates','kind':'synthetic', 'question':'Can repeated water be mistaken for newly flooded land?', 'lesson':'No new-water candidate should appear. Two wet observations do not prove permanent water or continuous flooding.'},
    {'id':'missing-earlier','title':'Missing earlier pixels','kind':'synthetic', 'question':'Does an unobserved earlier area incorrectly become new flood water?', 'lesson':'Earlier unknown pixels cannot establish a change from dry land.'},
    {'id':'paddy-context','title':'Rice / paddy context','kind':'synthetic', 'question':'Does water automatically mean damaged rice?', 'lesson':'Request crop-stage and irrigation context; do not turn a water signal into a crop-loss finding.'},
    {'id':'polarization-conflict','title':'Conflicting radar bands','kind':'synthetic', 'question':'What if VV looks dry but VH looks wet?', 'lesson':'Disagreement remains unknown, and whole-zone interpretation is withheld.'},
    {'id':'tiny-zone','title':'Sub-resolution field','kind':'synthetic', 'question':'Should a four-pixel polygon receive a field-level conclusion?', 'lesson':'Keep pixel measurements inspectable, but explicitly fail the resolution gate.'},
    {'id':'shifted-grid','title':'Misaligned image pair','kind':'synthetic', 'question':'What if dates match but the pixel grids are shifted?', 'lesson':'Reject the comparison before producing a misleading change map.'},
    {'id':'nodata-scene','title':'Unusable radar scene','kind':'synthetic', 'question':'Does an all-NoData scene become a safe-looking map?', 'lesson':'Reject the observation; do not produce a no-water conclusion.'},
]


def case_by_id(identifier):
    return next((item for item in CASES if item['id']==identifier),None)


def paths(item):
    return (catalog.RASTERS/'S1Hand'/(item['chip']+'_S1Hand.tif'),
            catalog.RASTERS/'LabelHand'/(item['chip']+'_LabelHand.tif'))


def cases():
    return [{**item,'available':item['kind']=='synthetic' or all(p.is_file() for p in paths(item))} for item in CASES]


def encode(data, transform=None):
    with MemoryFile() as mem:
        with mem.open(driver='GTiff',width=data.shape[2],height=data.shape[1],count=2,dtype='float32',
                      crs='EPSG:4326',transform=transform or Affine(.0001,0,92,0,-.0001,26),nodata=-9999) as dst:
            dst.write(data)
        return mem.read()


def synthetic_inputs(identifier):
    data=np.empty((2,96,96),np.float32);data[0]=-7;data[1]=-13
    earlier=data.copy()
    data[0,16:80,16:80]=-29;data[1,16:80,16:80]=-35
    options={'observed_on':'2020-01-10'}
    if identifier in ('new-water','repeat-water','missing-earlier','shifted-grid'):
        if identifier=='repeat-water':earlier=data.copy()
        if identifier=='missing-earlier':earlier[:,10:86,10:86]=-9999
        transform=Affine(.0001,0,92.0001,0,-.0001,26) if identifier=='shifted-grid' else None
        options.update(reference_raw=encode(earlier,transform),reference_on='2020-01-01',same_orbit=True)
    if identifier=='polarization-conflict':data[0]=-7;data[1]=-35
    if identifier=='nodata-scene':data[:]=-9999
    raw=encode(data)
    if identifier=='paddy-context':
        zones=default_zones(read_raster(raw))
        for feature in zones['features']:feature['properties']['crop']='rice'
        options['zones']=zones
    if identifier=='tiny-zone':
        options['zones']={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'id':'tiny','name':'Synthetic four-pixel zone'},
            'geometry':{'type':'Polygon','coordinates':[[[92.004,25.996],[92.0042,25.996],[92.0042,25.9958],[92.004,25.9958],[92.004,25.996]]]}}]}
    return raw,options


def score_labels(classes, truth):
    if truth.shape != classes.shape or not np.isin(truth,[-1,0,1]).all():
        raise InvalidRaster('Unsupported reference labels.')
    valid=truth>=0;water=truth==1;prediction=classes==2
    tp=valid & water & prediction;fp=valid & ~water & prediction;fn=valid & water & ~prediction
    a,b,c=map(lambda mask:int(mask.sum()),(tp,fp,fn))
    metrics={'true_positive_pixels':a,'false_positive_pixels':b,'missed_water_pixels':c,
             'unknown_water_pixels':int((water & (classes==0)).sum()),'labeled_pixels':int(valid.sum()),
             'precision':a/(a+b) if a+b else None,'recall':a/(a+c) if a+c else None,'iou':a/(a+b+c) if a+b+c else None}
    # BGR: blue correct water, coral false alarm, violet missed water, grey land.
    errors=np.full((*truth.shape,3),35,np.uint8)
    errors[valid & ~water & ~prediction]=(175,181,170)
    errors[tp]=(221,169,25);errors[fp]=(100,108,240);errors[fn]=(202,98,155)
    labels=np.full((*truth.shape,3),35,np.uint8)
    labels[valid & ~water]=(175,181,170);labels[water]=(221,169,25)
    return metrics,{'reference_labels':png(labels),'errors':png(errors)}


def run_case(identifier):
    item=case_by_id(identifier)
    if item is None:raise KeyError(identifier)
    info={**item,'notice':'Synthetic contract check; not real satellite imagery or an accuracy benchmark.' if item['kind']=='synthetic' else
          'Selected replay from the exposed test split, including stronger and failure cases. Labels are evaluation-only. Not a representative or new blind accuracy estimate.'}
    if item['kind']=='real_replay':
        radar,label=paths(item)
        raw=radar.read_bytes()
        result=run_analysis(raw,name=item['title'],observed_on=item['date'])
        raster=read_raster(raw);classes,_=classify(raster)
        # Only now load reference truth. It cannot affect inference or review queues.
        label_raw=label.read_bytes()
        with MemoryFile(label_raw) as mem,mem.open() as src:
            if src.crs!=raster.crs or not src.transform.almost_equals(raster.transform,precision=1e-10):
                raise InvalidRaster('Reference label grid does not match the radar.')
            truth=src.read(1)
        info['metrics'],images=score_labels(classes,truth)
        info['reference_sha256']=hashlib.sha256(label_raw).hexdigest()
        info['reference_source']='Sen1Floods11 v1.1 / flood_test_data.csv / LabelHand'
        info['attribution']='Bonafilia, Tellman, Anderson & Issenberg (2020), Cloud to Street; contains modified Copernicus Sentinel data.'
        info['checks']=[]
        result['images'].update(images)
    else:
        raw,options=synthetic_inputs(identifier)
        try:
            result=run_analysis(raw,name='SYNTHETIC · '+item['title'],**options)
        except InvalidRaster as exc:
            if identifier not in ('shifted-grid','nodata-scene'):raise
            expected='grid' if identifier=='shifted-grid' else 'Too few valid'
            info['checks']=[{'name':'Reject unsupported input without a result','passed':expected in str(exc)}]
            return {'kind':'rejection_check','lab':info,'observed_rejection':str(exc)}
        zones=result['zones']
        checks={'new-water':('Detect new-water candidate',lambda:sum(z['new_water_candidate_ha'] for z in zones)>0),
            'repeat-water':('Do not call repeated water new',lambda:sum(z['new_water_candidate_ha'] for z in zones)==0 and sum(z['repeat_water_observed_ha'] for z in zones)>0),
            'missing-earlier':('Unknown earlier pixels do not count as previously dry',lambda:sum(z['new_water_candidate_ha'] for z in zones)==0),
            'paddy-context':('Require rice context',lambda:any(z['decision']['level']=='context_required' for z in zones)),
            'polarization-conflict':('Withhold whole-zone conclusions',lambda:all(z['decision']['level']=='insufficient_evidence' for z in zones)),
            'tiny-zone':('Withhold a sub-resolution conclusion',lambda:all(z['pixels']<25 and z['decision']['level']=='insufficient_evidence' for z in zones)),
            'shifted-grid':('Reject a shifted grid',lambda:False),'nodata-scene':('Reject missing input',lambda:False)}
        name,check=checks[identifier]
        info['checks']=[{'name':name,'passed':bool(check())},
                        {'name':'Withhold crop-damage and safety claims','passed':all('crop damage' in z['decision']['withheld_claims'] and 'field access safety' in z['decision']['withheld_claims'] for z in zones)}]
        result['zone_basis']='synthetic test geometry; not actual farms'
    result['lab']=info
    return result

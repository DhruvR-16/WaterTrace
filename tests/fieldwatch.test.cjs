const {test}=require('node:test');
const assert=require('node:assert/strict');
const model=require('../fieldwatch/static/model.js');
test('small nonzero areas are never displayed as zero hectares',()=>{
  assert.equal(model.areaLabel(.044),'<0.1');assert.equal(model.areaLabel(.001),'<0.1');
  assert.equal(model.areaLabel(0),'0');assert.equal(model.areaLabel(.1),'0.1');assert.equal(model.areaLabel(1.25),'1.3');
});
test('pixel coordinates preserve geographic transform',()=>{
  assert.deepEqual(model.pixelToGeo([10,20],{crs:'EPSG:4326',transform:[.01,0,90,0,-.01,25]}),[90.1,24.8]);
});
test('projected drawing is not falsely treated as lon/lat',()=>{
  assert.throws(()=>model.pixelToGeo([10,20],{crs:'EPSG:32643'}));
});
test('polygon closes and does not invent a crop',()=>{
  const f=model.featureFromPoints([[0,0],[20,0],[20,20]],{crs:'EPSG:4326',transform:[.01,0,90,0,-.01,25],width:100,height:100},1);
  assert.deepEqual(f.geometry.coordinates[0][0],f.geometry.coordinates[0].at(-1));assert.equal(f.properties.crop,'unknown');
});
test('drawing after an import avoids existing zone IDs',()=>{
  const f=model.featureFromPoints([[0,0],[20,0],[20,20]],{crs:'EPSG:4326',transform:[.01,0,90,0,-.01,25],width:100,height:100},2,['drawn-2','drawn-3']);
  assert.equal(f.properties.id,'drawn-4');
});
test('short or outside polygons rejected',()=>{
  assert.throws(()=>model.featureFromPoints([[0,0]],{},1));
  assert.throws(()=>model.featureFromPoints([[0,0],[20,0],[200,20]],{width:100,height:100},1));
});
test('exports exclude pixels and unrelated notes',()=>{
  const result=model.reviewExport({images:{radar:'pixels'},zones:[{id:'a'}],source:{sha256:'digest'}},{a:{note:'human'},b:{note:'unrelated'}});
  assert.equal(result.images,undefined);assert.equal(result.human_reviews.length,1);assert.equal(result.human_reviews[0].zone_id,'a');
});
test('lab exports preserve disclosure and provenance but omit all preview layers',()=>{
  const lab={kind:'real_replay',notice:'Selected exposed-test replay',reference_sha256:'b'.repeat(64),metrics:{recall:.01}};
  const result=model.reviewExport({images:{radar:'pixels',reference_labels:'labels',errors:'errors'},zones:[],lab},{});
  assert.equal(result.images,undefined);assert.deepEqual(result.lab,lab);
});
test('malformed reports rejected',()=>{
  for(const value of [null,{},[],{schema_version:'1.0'}])assert.throws(()=>model.validateResult(value));
});
test('untrusted preview URLs rejected',()=>{
  const value={schema_version:'1.0',source:{width:64,height:64,sha256:'a'.repeat(64)},images:{radar:'https://tracker.invalid/'},zones:[],summary:{},trace:[]};
  assert.throws(()=>model.validateResult(value));value.images.radar='data:image/png;base64,AA==';assert.equal(model.validateResult(value),value);
});

function reviewFixture(){
  return {schema_version:'1.0',source:{sha256:'a'.repeat(64),observed_on:'2020-01-10',crs:'EPSG:4326'},
    reference:{sha256:'b'.repeat(64),observed_on:'2020-01-01'},engine:{policy:'screen-v1'},policy:{threshold:-20},reference_policy:{threshold:-21},
    zones:[{id:'a',crop:'rice',geometry:{type:'Polygon',coordinates:[[[0,0],[1,0],[1,1],[0,0]]]},decision:{policy:'gates-v1'}}],
    images:{radar:'pixels'},generated_at:'2020-01-11T00:00:00Z'};
}
const savedReview={outcome:'follow_up',note:'Check local irrigation context.',recorded_at:'2020-01-11T00:00:00Z'};
test('draft tracking distinguishes untouched and edited notes',()=>{
  assert.equal(model.reviewChanged(undefined,'unreviewed',''),false);
  assert.equal(model.reviewChanged(undefined,'unreviewed','draft'),true);
  assert.equal(model.reviewChanged(savedReview,'follow_up',savedReview.note),false);
  assert.equal(model.reviewChanged(savedReview,'false_alarm',savedReview.note),true);
  assert.equal(model.reviewChanged(savedReview,'follow_up',''),true);
});
test('export and restoration preserve notes without mutating measurements',()=>{
  const report=reviewFixture(),before=JSON.stringify(report),exported=model.reviewExport(report,{a:savedReview});
  const restored=model.restoreReviews(report,JSON.parse(JSON.stringify(exported)));
  assert.equal(restored.a.note,savedReview.note);assert.equal(restored.a.restored_from_export,true);
  assert.equal(Object.getPrototypeOf(restored),null);assert.equal(JSON.stringify(report),before);
});
test('regeneration timestamps and JSON key ordering do not invalidate matching inputs',()=>{
  const report=reviewFixture(),exported=model.reviewExport(report,{a:savedReview});
  exported.generated_at='2026-01-01T00:00:00Z';
  exported.source={crs:'EPSG:4326',observed_on:'2020-01-10',sha256:'a'.repeat(64)};
  assert.equal(model.restoreReviews(report,exported).a.outcome,'follow_up');
});
for(const [name,change]of Object.entries({
  source:r=>r.source.sha256='c'.repeat(64),date:r=>r.source.observed_on='2020-01-09',
  reference:r=>r.reference.sha256='c'.repeat(64),policy:r=>r.engine.policy='different',
  thresholds:r=>r.policy.threshold=-19,geometry:r=>r.zones[0].geometry.coordinates[0][1][0]=2,
  crop:r=>r.zones[0].crop='wheat',gate:r=>r.zones[0].decision.policy='gates-v2',
}))test(`restoration refuses changed ${name}`,()=>{
  const report=reviewFixture(),exported=JSON.parse(JSON.stringify(model.reviewExport(report,{a:savedReview})));
  change(exported);assert.throws(()=>model.restoreReviews(report,exported),/does not match/);
});
test('restoration rejects malformed, excessive, duplicate and foreign notes',()=>{
  const report=reviewFixture(),exported=model.reviewExport(report,{a:savedReview});
  for(const human_reviews of [null,{},Array(101).fill({}),[{...savedReview,zone_id:'foreign'}],
    [{...savedReview,zone_id:'a',note:'x'.repeat(1001)}],[{...savedReview,zone_id:'a',outcome:'safe'}],
    [{...savedReview,zone_id:'a',recorded_at:'invalid'}],Array(2).fill({...savedReview,zone_id:'a'})]){
    assert.throws(()=>model.restoreReviews(report,{...exported,human_reviews}));
  }
  assert.throws(()=>model.restoreReviews(report,{...exported,images:{radar:'pixels'}}));
});
test('prototype-looking IDs and markup remain inert annotation strings',()=>{
  const report=reviewFixture();report.zones[0].id='__proto__';
  const exported=model.reviewExport(report,{['__proto__']:{...savedReview,note:'<script>not executable</script>'}});
  const restored=model.restoreReviews(report,exported);
  assert.equal(Object.getPrototypeOf(restored),null);assert.equal(restored.__proto__.note,'<script>not executable</script>');
});

// Unit-test event wiring with inert DOM doubles; this is not browser/layout QA.
async function reviewUI(){
  const vm=require('node:vm'),fs=require('node:fs');
  class Element {
    constructor(){this.value='';this.children=[];this.listeners={};this.dataset={};this.style={setProperty(){}};this.classList={add(){},remove(){}};}
    addEventListener(name,fn){this.listeners[name]=fn;}
    setAttribute(){}
    append(...items){this.children.push(...items);}
    replaceChildren(...items){this.children=items;}
    click(){return this.listeners.click?.();}
  }
  const elements=new Map(),events={},captured={confirm:false,confirmCalls:0,blob:null};
  const get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const document={getElementById:get,querySelectorAll:()=>[],createElement:()=>new Element(),createElementNS:()=>new Element(),createTextNode:text=>text};
  const context=vm.createContext({document,window:{FieldWatchModel:model,addEventListener:(n,f)=>events[n]=f,
    confirm:()=>{captured.confirmCalls++;return captured.confirm;}},
    fetch:async()=>({ok:true,json:async()=>[{id:'india',title:'India',date:'2020-01-10',available:false}]}),
    AbortController,AbortSignal,Blob,URL:{createObjectURL:blob=>{captured.blob=blob;return 'blob:test';},revokeObjectURL(){}},
    setTimeout:()=>0,clearTimeout(){}});
  vm.runInContext(fs.readFileSync(require.resolve('../fieldwatch/static/app.js'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  const report=reviewFixture();report.source.width=64;
  report.zones=['a','b'].map(id=>({id,status:'inspect_water',name:id,crop:'rice',reasons:[],coverage:1,water_fraction:.5,
    area_ha:1,water_observed_ha:.5,new_water_candidate_ha:null,geometry:{type:'Polygon',coordinates:[[[0,0],[1,0],[1,1],[0,0]]]}}));
  context.fixture=report;
  vm.runInContext("state.report=fixture;state.selected='a';state.example='original';",context);
  get('review-outcome').value='unreviewed';
  return {get,context,events,captured,run:code=>vm.runInContext(code,context)};
}
test('zone selection keeps an unsaved draft and restores it when returning',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Draft without pressing Save';
  ui.run("selectZone('b')");assert.equal(ui.run('state.reviews.a.note'),'Draft without pressing Save');
  assert.equal(ui.get('review-note').value,'');
  ui.run("selectZone('a')");assert.equal(ui.get('review-note').value,'Draft without pressing Save');
});
test('cancelled scene replacement preserves the active report and draft',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Do not lose this';
  ui.get('examples').children[0].click();
  assert.equal(ui.captured.confirmCalls,1);assert.equal(ui.run('state.example'),'original');
  assert.equal(ui.run('state.report===fixture'),true);assert.equal(ui.run('state.reviews.a.note'),'Do not lose this');
});
test('export includes the current draft and clears only the pending-export flag',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Latest typed text';
  ui.get('export-button').click();
  const saved=JSON.parse(await ui.captured.blob.text());
  assert.equal(saved.human_reviews[0].note,'Latest typed text');assert.equal(saved.images,undefined);
  assert.equal(ui.run('state.reviewsDirty'),false);assert.equal(ui.run('state.reviews.a.note'),'Latest typed text');
});
test('leaving with an edited draft requests a browser warning',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Pending';let prevented=false;
  ui.events.beforeunload({preventDefault(){prevented=true;}});
  assert.equal(prevented,true);assert.equal(ui.run('state.reviews.a.note'),'Pending');
});
test('restore control imports only annotations and keeps the active result',async()=>{
  const ui=await reviewUI(),exported=model.reviewExport(ui.run('state.report'),{a:savedReview});
  await ui.get('review-file').listeners.change({target:{files:[{size:1000,text:async()=>JSON.stringify(exported)}],value:'selected'}});
  assert.equal(ui.run('state.report===fixture'),true);assert.equal(ui.run('state.reviews.a.note'),savedReview.note);
  assert.equal(ui.get('review-note').value,savedReview.note);
});
test('failed restore leaves current draft and saved notes untouched',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Current draft';
  const exported=model.reviewExport(ui.run('state.report'),{a:savedReview});
  exported.source={...exported.source,sha256:'c'.repeat(64)};
  await ui.get('review-file').listeners.change({target:{files:[{size:1000,text:async()=>JSON.stringify(exported)}],value:'selected'}});
  assert.equal(ui.get('review-note').value,'Current draft');assert.equal(ui.run('Object.keys(state.reviews).length'),0);
  assert.match(ui.get('message').textContent,/does not match/);
});
test('GeoJSON exports geographic boundaries, provenance and separate human annotations',()=>{
  const report=reviewFixture();report.zone_basis='illustrative grid';report.lab={kind:'synthetic',notice:'Not real satellite imagery'};
  report.zones[0].pixel_geometry={type:'Polygon',coordinates:[[[0,0],[64,0],[64,64],[0,0]]]};
  report.zones[0].decision={level:'insufficient_evidence',withheld_claims:['crop damage'],policy:'gates-v1'};
  const before=JSON.stringify(report),exported=model.geojsonExport(report,{a:savedReview,b:{note:'unrelated'}});
  const feature=exported.features[0];
  assert.deepEqual(feature.geometry,report.zones[0].geometry);
  assert.equal(feature.properties.review_gate,'insufficient_evidence');
  assert.equal(feature.properties.human_note,savedReview.note);assert.equal(feature.properties.human_review_unverified,true);
  assert.equal(feature.properties.source_sha256,report.source.sha256);assert.deepEqual(exported.fieldwatch.lab,report.lab);
  assert.equal(exported.features.length,1);assert.equal(JSON.stringify(exported).includes('pixel_geometry'),false);
  assert.equal(JSON.stringify(exported).includes('pixels'),true); // Pixel count is a scalar, not a pixel payload.
  assert.equal(exported.images,undefined);assert.equal(JSON.stringify(report),before);
  feature.geometry.coordinates[0][0][0]=55;feature.properties.withheld_claims.push('modified');
  exported.fieldwatch.source.sha256='modified';assert.equal(JSON.stringify(report),before);
});
test('GeoJSON preserves absent comparison and date as null rather than zero',()=>{
  const report=reviewFixture();report.reference=null;report.source.observed_on=null;
  const props=model.geojsonExport(report).features[0].properties;
  for(const field of ['new_water_candidate_ha','repeat_water_observed_ha','reference_sha256','reference_on','observed_on','human_note'])assert.equal(props[field],null);
  assert.match(props.area_notice,/scene overlap/);assert.match(props.area_notice,/Zones may overlap/);
});
test('GeoJSON prototype-looking IDs do not pick up inherited human notes',()=>{
  const report=reviewFixture();report.zones[0].id='__proto__';
  assert.equal(model.geojsonExport(report).features[0].properties.human_note,null);
  assert.equal(model.geojsonExport(report,{['__proto__']:savedReview}).features[0].properties.human_note,savedReview.note);
});
test('GeoJSON normalizes clockwise exteriors without changing the input boundary',()=>{
  const report=reviewFixture();report.zones[0].geometry.coordinates[0].reverse();
  const before=JSON.stringify(report),exported=model.geojsonExport(report);
  assert.deepEqual(exported.features[0].geometry.coordinates[0],[[0,0],[1,0],[1,1],[0,0]]);
  assert.equal(JSON.stringify(report),before);
});
test('GeoJSON includes all queues and draft notes but keeps the backup warning',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Pending handoff';
  ui.run("state.filter='resolve_uncertainty'");ui.get('geojson-export-button').click();
  const exported=JSON.parse(await ui.captured.blob.text());
  assert.equal(ui.captured.blob.type,'application/geo+json');assert.equal(exported.features.length,2);
  assert.equal(exported.features[0].properties.human_note,'Pending handoff');
  assert.equal(ui.run('state.reviewsDirty'),true);assert.equal(ui.run('state.report===fixture'),true);
  assert.match(ui.get('message').textContent,/Use Export review/);
  assert.throws(()=>model.restoreReviews(ui.run('state.report'),exported),/review export/);
});
test('GeoJSON control produces nothing while a request is pending or no report exists',async()=>{
  const ui=await reviewUI();ui.run('state.controller={}');ui.get('geojson-export-button').click();
  assert.equal(ui.captured.blob,null);
  ui.run('state.controller=null;state.report=null');ui.get('geojson-export-button').click();assert.equal(ui.captured.blob,null);
});
test('GeoJSON keeps boundary clipping separate from pixel assessability',()=>{
  const report=reviewFixture();report.zones[0].coverage=1;
  report.zones[0].spatial_support={scene_clipped:true,scene_overlap_fraction:.995,
    fraction_basis:'planar_polygon_area_in_raster_grid',boundary_tolerance_pixels:1e-7};
  const props=model.geojsonExport(report).features[0].properties;
  assert.equal(props.assessed_fraction,1);assert.equal(props.scene_clipped,true);
  assert.equal(props.scene_overlap_fraction,.995);assert.equal(props.scene_overlap_fraction_basis,'planar_polygon_area_in_raster_grid');
  assert.equal(props.boundary_tolerance_pixels,1e-7);
});
test('older report exports do not invent full boundary coverage',()=>{
  const props=model.geojsonExport(reviewFixture()).features[0].properties;
  assert.equal(props.scene_clipped,null);assert.equal(props.scene_overlap_fraction,null);
});
test('review detail labels partial boundaries even when the stored fraction rounds to one',async()=>{
  const ui=await reviewUI();
  ui.run("state.report.zones[0].spatial_support={scene_clipped:true,scene_overlap_fraction:1};renderDetail()");
  const stats=ui.get('zone-stats').children;
  assert.equal(stats[2].children[1],'Uncertain within overlap');
  assert.equal(stats[3].children[0].textContent,'Partial');
  assert.equal(stats[3].children[1],'Boundary coverage (not pixel quality)');
});
test('new spatial support must match before old review notes can be restored',()=>{
  const report=reviewFixture(),saved=model.reviewExport(report,{a:savedReview});
  const current=JSON.parse(JSON.stringify(report));current.zones[0].spatial_support={scene_clipped:true};
  assert.throws(()=>model.restoreReviews(current,saved),/does not match/);
});

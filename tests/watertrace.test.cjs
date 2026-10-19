const {test}=require('node:test');
const assert=require('node:assert/strict');
const model=require('../watertrace/static/model.js');
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
test('brand-only rename permits matching v0.7 and v0.8 notes without changing findings',()=>{
  const report=reviewFixture();report.engine.name='WaterTrace';
  const exported=JSON.parse(JSON.stringify(model.reviewExport(report,{a:savedReview})));
  const before=JSON.stringify(report);
  for(const previousName of ['FieldWatch','Inundra']){
    exported.engine.name=previousName;
    assert.equal(model.restoreReviews(report,exported).a.note,savedReview.note);
  }
  assert.equal(JSON.stringify(report),before);
  const geographic=model.geojsonExport(report);
  assert.equal(geographic.watertrace.schema_version,'geojson-review-v3');
  assert.equal(geographic.fieldwatch,undefined);
  assert.equal(geographic.inundra,undefined);
});
test('download filenames use the new name for review and geographic handoffs',async()=>{
  const ui=await reviewUI();
  // Test the actual event handlers through their requested Blob contents.
  ui.get('geojson-export-button').click();
  const saved=JSON.parse(await ui.captured.blob.text());
  assert.equal(saved.watertrace.schema_version,'geojson-review-v3');
  assert.equal(saved.fieldwatch,undefined);
  const app=require('node:fs').readFileSync(require.resolve('../watertrace/static/app.js'),'utf8');
  assert.ok(app.includes('watertrace-review-${'));
  assert.ok(app.includes('watertrace-zones-${'));
});
function temporalFixture(){
  return {policy:'paired-evidence-v1',paired_assessed_ha:.75,paired_uncertain_ha:.25,
    paired_assessed_fraction:.75,water_without_baseline_ha:.25,
    observed_water_baseline_fraction:.5,observed_water_baseline_complete:false};
}
test('temporal export preserves false and zero and separates unavailable old metadata',()=>{
  const report=reviewFixture(),support=temporalFixture();support.water_without_baseline_ha=0;
  report.temporal_support=support;report.zones[0].temporal_support=support;
  const exported=model.geojsonExport(report,{a:savedReview}),props=exported.features[0].properties;
  assert.equal(props.observed_water_baseline_complete,false);
  assert.equal(props.water_without_baseline_ha,0);
  assert.equal(props.temporal_policy,'paired-evidence-v1');
  assert.deepEqual(exported.watertrace.temporal_support,support);
  exported.watertrace.temporal_support.paired_assessed_fraction=0;
  assert.equal(support.paired_assessed_fraction,.75);
  const old=model.geojsonExport(reviewFixture());
  assert.equal(old.features[0].properties.observed_water_baseline_complete,null);
  assert.equal(old.features[0].properties.water_without_baseline_ha,null);
  assert.equal(old.watertrace.temporal_support,null);
});
test('note restoration requires matching temporal support and rejects older context',()=>{
  const report=reviewFixture();report.zones[0].temporal_support=temporalFixture();
  const exported=JSON.parse(JSON.stringify(model.reviewExport(report,{a:savedReview})));
  assert.equal(model.restoreReviews(report,exported).a.note,savedReview.note);
  exported.zones[0].temporal_support.observed_water_baseline_complete=true;
  assert.throws(()=>model.restoreReviews(report,exported),/does not match/);
  delete exported.zones[0].temporal_support;
  assert.throws(()=>model.restoreReviews(report,exported),/does not match/);
});
test('paired detail labels missing baseline separately from current uncertainty',async()=>{
  const ui=await reviewUI();ui.context.fixture.zones[0].temporal_support=temporalFixture();
  ui.run('renderDetail()');
  const stats=ui.get('zone-stats').children;
  assert.equal(stats[2].children[0].textContent,'0%');
  assert.equal(stats[3].children[1],'Water without earlier baseline');
  assert.equal(stats[4].children[1],'Assessable at both dates');
  assert.equal(stats[4].children[0].textContent,'75%');
  assert.equal(ui.get('detail-temporal').hidden,false);
  assert.match(ui.get('detail-temporal').textContent,/does not mean no new flooding/);
});
test('rounded-zero missing baseline still displays a positive bound and warning',async()=>{
  const ui=await reviewUI(),support=temporalFixture();
  support.water_without_baseline_ha=0;support.paired_assessed_fraction=1;support.observed_water_baseline_fraction=1;
  ui.context.fixture.zones[0].temporal_support=support;
  ui.run('renderDetail()');
  assert.equal(ui.get('zone-stats').children[3].children[0].textContent,'<0.001 ha');
  assert.match(ui.get('detail-temporal').textContent,/Earlier evidence is missing/);
});
test('changing to an unpaired zone clears old temporal detail and metrics',async()=>{
  const ui=await reviewUI();ui.context.fixture.zones[0].temporal_support=temporalFixture();
  ui.run('renderDetail();selectZone("b")');
  assert.equal(ui.get('detail-temporal').hidden,true);
  assert.equal(ui.get('detail-temporal').textContent,'');
  assert.equal(ui.get('zone-stats').children.length,3);
});
test('complete baseline and no-current-water context do not claim flood onset',async()=>{
  const ui=await reviewUI(),support=temporalFixture();
  for(const complete of [true,null]){
    support.observed_water_baseline_complete=complete;support.water_without_baseline_ha=0;
    ui.context.fixture.zones[0].temporal_support=support;ui.run('renderDetail()');
    assert.match(ui.get('detail-temporal').textContent,/do not establish flood onset/);
    assert.doesNotMatch(ui.get('detail-temporal').textContent,/Earlier evidence is missing/);
  }
});
test('timeline carries scene-level paired support and baseline warning',async()=>{
  const ui=await reviewUI();ui.context.fixture.temporal_support=temporalFixture();
  ui.run('renderTimeline()');
  const row=ui.get('timeline').children[1];
  assert.equal(row.children[0].textContent,'PAIRED SUPPORT');
  assert.match(row.children[1].textContent,/75% of scene/);
  assert.match(row.children[2],/does not rule out new flooding/);
});
test('temporal detail target exists in shipped HTML',()=>{
  const html=require('node:fs').readFileSync(require.resolve('../watertrace/static/index.html'),'utf8');
  assert.match(html,/<p id="detail-temporal" hidden><\/p>/);
});
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
    constructor(){this.value='';this.children=[];this.listeners={};this.dataset={};this.attributes={};this.style={setProperty(){}};this.classList={add(){},remove(){}};}
    addEventListener(name,fn){this.listeners[name]=fn;}
    setAttribute(name,value){this.attributes[name]=value;}
    append(...items){this.children.push(...items);}
    replaceChildren(...items){this.children=items;}
    click(){return this.listeners.click?.();}
  }
  const elements=new Map(),events={},captured={confirm:false,confirmCalls:0,blob:null,timers:[]};
  const get=id=>{if(!elements.has(id)){const item=new Element();item.id=id;elements.set(id,item);}return elements.get(id);};
  const query=selector=>selector.split(',').flatMap(s=>s.startsWith('#')?[get(s.slice(1))]:s==='.example'?get('examples').children:s==='.lab-card'?get('lab-cases').children:[]);
  const document={getElementById:get,querySelectorAll:query,createElement:()=>new Element(),createElementNS:()=>new Element(),createTextNode:text=>text};
  const context=vm.createContext({document,window:{WaterTraceModel:model,addEventListener:(n,f)=>events[n]=f,
    confirm:()=>{captured.confirmCalls++;return captured.confirm;}},
    fetch:async()=>({ok:true,json:async()=>[{id:'india',title:'India',date:'2020-01-10',available:false}]}),
    AbortController,AbortSignal,Blob,FormData,URL:{createObjectURL:blob=>{captured.blob=blob;return 'blob:test';},revokeObjectURL(){}},
    setTimeout:(fn,ms)=>{captured.timers.push({fn,ms});return captured.timers.length;},clearTimeout(){}});
  vm.runInContext(fs.readFileSync(require.resolve('../watertrace/static/app.js'),'utf8'),context);
  await new Promise(resolve=>setImmediate(resolve));
  const report=reviewFixture();Object.assign(report.source,{width:64,height:64,bounds:[0,0,1,1],transform:[.01,0,0,0,-.01,1]});
  Object.assign(report,{name:'Original observation',zone_basis:'test zones',summary:{water_observed_ha:1,uncertain_ha:0,assessed_fraction:1},trace:[],elapsed_ms:1,images:{radar:'data:image/png;base64,AA==',evidence:'data:image/png;base64,AA=='}});
  report.zones=['a','b'].map(id=>({id,status:'inspect_water',name:id,crop:'rice',reasons:[],coverage:1,water_fraction:.5,
    area_ha:1,water_observed_ha:.5,new_water_candidate_ha:null,geometry:{type:'Polygon',coordinates:[[[0,0],[1,0],[1,1],[0,0]]]},pixel_geometry:{type:'Polygon',coordinates:[[[0,0],[64,0],[64,64],[0,0]]]}}));
  context.fixture=report;
  vm.runInContext("state.report=fixture;state.selected='a';state.example='original';state.acceptedInputs={example:'original',lab:null,upload:null,zones:null};",context);
  get('review-outcome').value='unreviewed';
  get('view-select').options=['radar','optical','earlier','errors','reference_labels'].map(value=>({value}));
  get('view-select').value='radar';get('zones-toggle').checked=true;
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
  assert.equal(feature.properties.source_sha256,report.source.sha256);assert.deepEqual(exported.watertrace.lab,report.lab);
  assert.equal(exported.features.length,1);assert.equal(JSON.stringify(exported).includes('pixel_geometry'),false);
  assert.equal(JSON.stringify(exported).includes('pixels'),true); // Pixel count is a scalar, not a pixel payload.
  assert.equal(exported.images,undefined);assert.equal(JSON.stringify(report),before);
  feature.geometry.coordinates[0][0][0]=55;feature.properties.withheld_claims.push('modified');
  exported.watertrace.source.sha256='modified';assert.equal(JSON.stringify(report),before);
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

for(const mode of ['server rejection','network failure','invalid response','render failure'])test(`${mode} restores the previous observation, selection and draft`,async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Keep this draft';
  ui.run("state.filter='inspect_water';state.example='replacement';state.zones={type:'FeatureCollection',features:[]}");
  if(mode==='server rejection')ui.context.fetch=async()=>({ok:false,json:async()=>({detail:'Invalid zone polygon.'})});
  if(mode==='network failure')ui.run("fetch=async()=>{throw new TypeError('offline')}");
  if(mode==='invalid response')ui.context.fetch=async()=>({ok:true,json:async()=>({bad:'response'})});
  if(mode==='render failure'){
    const broken=JSON.parse(JSON.stringify(ui.context.fixture));delete broken.source.bounds;
    ui.context.fetch=async()=>({ok:true,json:async()=>broken});
  }
  await ui.run('analyze()');
  assert.equal(ui.run('state.report===fixture'),true);assert.equal(ui.run('state.example'),'original');
  assert.equal(ui.run('state.zones'),null);assert.equal(ui.run('state.selected'),'a');
  assert.equal(ui.run('state.filter'),'inspect_water');assert.equal(ui.run('state.reviewsDirty'),true);
  assert.equal(ui.get('review-note').value,'Keep this draft');assert.equal(ui.get('scene-tag').textContent,'PREVIOUS RESULT');
  assert.match(ui.get('message').textContent,/Previous observation and session notes restored/);
  if(mode==='render failure')assert.match(ui.get('message').textContent,/response could not be displayed/);
  assert.equal(ui.get('export-button').disabled,false);assert.equal(ui.run('state.pendingReview'),null);
  ui.get('export-button').click();
  const exported=JSON.parse(await ui.captured.blob.text());
  assert.equal(exported.name,'Original observation');assert.equal(exported.human_reviews[0].note,'Keep this draft');
});

for(const mode of ['cancel','timeout'])test(`${mode} restores pending review and ignores a late successful response`,async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Unsaved during request';
  let finish;ui.context.fetch=()=>new Promise(resolve=>{finish=resolve;});
  const pending=ui.run("state.example='replacement';analyze()");
  assert.equal(ui.get('export-button').disabled,true);assert.equal(ui.get('map-stack').hidden,true);
  let prevented=false;ui.events.beforeunload({preventDefault(){prevented=true;}});assert.equal(prevented,true);
  if(mode==='cancel')ui.get('cancel-button').click();
  else ui.captured.timers.find(t=>t.ms===90000).fn();
  const incoming=JSON.parse(JSON.stringify(ui.context.fixture));incoming.name='Late result';
  finish({ok:true,json:async()=>incoming});await pending;
  assert.equal(ui.run('state.report===fixture'),true);assert.equal(ui.get('review-note').value,'Unsaved during request');
  assert.equal(ui.run('state.controller'),null);assert.equal(ui.run('state.pendingReview'),null);
  assert.match(ui.get('message').textContent,mode==='cancel'?/Stopped waiting/:/timed out/);
});

test('failed imported polygons restore original inputs and highlighted example',async()=>{
  const ui=await reviewUI();ui.captured.confirm=true;ui.get('review-note').value='Prior annotation';
  ui.run("state.example='india';state.acceptedInputs.example='india';state.acceptedInputs.zones={type:'FeatureCollection',features:[{original:true}]};state.zones=state.acceptedInputs.zones");
  ui.context.fetch=async()=>({ok:false,json:async()=>({detail:'Unsupported polygon.'})});
  await ui.get('geojson-file').listeners.change({target:{value:'chosen',files:[{size:100,text:async()=>'{"type":"FeatureCollection","features":[]}'}]}});
  assert.equal(ui.run('state.zones.features[0].original'),true);
  assert.equal(ui.get('examples').children[0].attributes['aria-pressed'],'true');
  assert.equal(ui.get('review-note').value,'Prior annotation');
});

test('failed replacement of an uploaded scene retains the original file references',async()=>{
  const ui=await reviewUI();ui.context.originalUpload={current:new Blob(['radar']),reference:new Blob(['earlier']),date:'2020-01-10',referenceDate:'2020-01-01',sameOrbit:true};
  ui.run("state.example=null;state.upload=originalUpload;state.acceptedInputs={example:null,lab:null,upload:originalUpload,zones:null};state.example='replacement';state.upload=null");
  ui.context.fetch=async()=>({ok:false,json:async()=>({detail:'Rejected.'})});
  await ui.run('analyze()');
  assert.equal(ui.run('state.upload===originalUpload'),true);assert.equal(ui.run('state.example'),null);
});

test('a successful replacement commits new inputs and releases the previous review',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Replaced with confirmation';
  const incoming=JSON.parse(JSON.stringify(ui.context.fixture));incoming.name='New observation';incoming.source.sha256='b'.repeat(64);
  ui.context.fetch=async()=>({ok:true,json:async()=>incoming});
  await ui.run("state.example='replacement';analyze()");
  assert.equal(ui.run('state.report.name'),'New observation');assert.equal(ui.run('state.acceptedInputs.example'),'replacement');
  assert.equal(ui.run('state.reviewsDirty'),false);assert.equal(ui.run('Object.keys(state.reviews).length'),0);
  assert.equal(ui.run('state.pendingReview'),null);assert.equal(ui.get('review-note').value,'');
  assert.notEqual(ui.get('scene-tag').textContent,'PREVIOUS RESULT');
});

test('an accepted lab rejection clears old evidence rather than showing a stale map',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Prior draft';
  const lab={kind:'synthetic',title:'Shifted grid',question:'Reject?',notice:'Synthetic',lesson:'Reject bad grids',checks:[]};
  ui.context.fetch=async()=>({ok:true,json:async()=>({kind:'rejection_check',lab,observed_rejection:'Shifted grid rejected.'})});
  await ui.run("state.example=null;state.lab='shifted-grid';analyze()");
  assert.equal(ui.run('state.report'),null);assert.equal(ui.run('state.pendingReview'),null);
  assert.equal(ui.get('map-stack').hidden,true);assert.equal(ui.get('export-button').disabled,true);
  assert.match(ui.get('scene-title').textContent,/Input rejected/);
});

test('failure without a previous accepted result leaves no stale report or enabled exports',async()=>{
  const ui=await reviewUI();
  ui.run('state.report=null;state.acceptedInputs=null');
  const broken=JSON.parse(JSON.stringify(ui.context.fixture));delete broken.source.bounds;
  ui.context.fetch=async()=>({ok:true,json:async()=>broken});
  await ui.run('analyze()');
  assert.equal(ui.run('state.report'),null);assert.equal(ui.get('map-stack').hidden,true);
  assert.equal(ui.get('export-button').disabled,true);assert.equal(ui.get('geojson-export-button').disabled,true);
  assert.equal(ui.get('scene-title').textContent,'No accepted analysis');
});
test('an accepted empty-string zone ID still captures its draft',async()=>{
  const ui=await reviewUI();ui.run("state.report.zones[0].id='';state.selected=''");
  ui.get('review-note').value='Annotation for this zone';ui.get('export-button').click();
  const exported=JSON.parse(await ui.captured.blob.text());
  assert.equal(exported.human_reviews[0].zone_id,'');assert.equal(exported.human_reviews[0].note,'Annotation for this zone');
});
test('rollback restores the earlier-image layer instead of silently changing the view',async()=>{
  const ui=await reviewUI();ui.run("state.report.images.earlier='data:image/png;base64,AA==';state.report.images.earlier_evidence='data:image/png;base64,AA=='");
  ui.get('view-select').value='earlier';
  ui.context.fetch=async()=>({ok:false,json:async()=>({detail:'Retry later.'})});
  await ui.run("state.example='replacement';analyze()");
  assert.equal(ui.get('view-select').value,'earlier');assert.match(ui.get('map-caption').textContent,/Earlier radar/);
  assert.equal(ui.get('scene-tag').textContent,'PREVIOUS RESULT');
});
test('repeated request failures do not overwrite the recoverable review with failed inputs',async()=>{
  const ui=await reviewUI();ui.get('review-note').value='Keep through retries';
  ui.context.fetch=async()=>({ok:false,json:async()=>({detail:'Busy.'})});
  await ui.run("state.example='first-attempt';analyze()");
  await ui.run("state.example='second-attempt';analyze()");
  assert.equal(ui.run('state.report===fixture'),true);assert.equal(ui.run('state.acceptedInputs.example'),'original');
  assert.equal(ui.get('review-note').value,'Keep through retries');assert.equal(ui.run('state.reviewsDirty'),true);
  assert.equal(ui.run('state.pendingReview'),null);
});

test('paired change view isolates categories from water and evaluation overlays',async()=>{
  const ui=await reviewUI();ui.run("state.report.images.change='change-png'");
  ui.get('view-select').value='change';ui.run('renderView()');
  assert.equal(ui.get('satellite').src,'change-png');
  assert.equal(ui.get('evidence').hidden,true);assert.equal(ui.get('evidence-toggle').disabled,true);
  assert.equal(ui.get('lab-legend').hidden,true);assert.equal(ui.get('normal-legend').hidden,true);
  assert.match(ui.get('map-caption').textContent,/without a baseline/);
  assert.match(ui.get('map-caption').textContent,/not verified flood change/);
  ui.get('view-select').value='radar';ui.run('renderView()');
  assert.equal(ui.get('evidence-toggle').disabled,false);
});

test('radar comparison is synchronized and disappears outside paired radar view',async()=>{
  const ui=await reviewUI();ui.run("state.report.images.earlier='earlier-png';state.report.reference={observed_on:'2020-01-01'}");
  ui.get('view-select').value='radar';ui.get('comparison-toggle').checked=true;
  ui.get('comparison-position').value='35';ui.run('renderView()');
  assert.equal(ui.get('comparison-controls').hidden,false);
  assert.equal(ui.get('comparison-earlier').hidden,false);
  assert.equal(ui.get('comparison-earlier').style.clipPath,'inset(0 65% 0 0)');
  assert.equal(ui.get('evidence').hidden,true);assert.equal(ui.get('evidence-toggle').disabled,true);
  assert.match(ui.get('map-caption').textContent,/Left: 2020-01-01/);
  ui.get('view-select').value='earlier';ui.run('renderView()');
  assert.equal(ui.get('comparison-controls').hidden,true);assert.equal(ui.get('comparison-earlier').hidden,true);
  ui.get('view-select').value='radar';ui.run('state.report.reference=null;state.report.images.earlier=null;renderView()');
  assert.equal(ui.get('comparison-controls').hidden,true);assert.equal(ui.get('evidence-toggle').disabled,false);
  ui.run('clearReport()');assert.equal(ui.get('comparison-controls').hidden,true);
});

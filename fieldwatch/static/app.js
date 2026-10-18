'use strict';
const $ = id => document.getElementById(id);
const M = window.FieldWatchModel;
const state = {report:null,example:null,lab:null,upload:null,zones:null,reviews:Object.create(null),reviewsDirty:false,selected:null,filter:'all',controller:null,drawing:false,points:[]};
const number = value => new Intl.NumberFormat('en',{maximumFractionDigits:1}).format(value);
const percent = value => `${Math.round(value*100)}%`;
const metricPercent = value => value===null?'N/A':`${(value*100).toFixed(1)}%`;
function element(tag, text, className) {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function svgElement(tag,attrs) {const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value]of Object.entries(attrs))el.setAttribute(key,String(value));return el;}
function message(text) {$('message').textContent=text;$('message').hidden=!text;}
function busy(active) {
  $('busy').hidden=!active;
  document.querySelectorAll('.example,.lab-card,#upload-button,#export-button,#geojson-export-button,#restore-button,#draw-button,#import-button').forEach(el=>el.disabled=active || (['export-button','geojson-export-button','restore-button','draw-button','import-button'].includes(el.id)&&!state.report));
  $('draw-button').disabled=active || !!state.lab || !state.report || state.report.source.crs!=='EPSG:4326';
  $('import-button').disabled=active || !!state.lab || !state.report;
}
function clearReport() {
  state.report=null;state.selected=null;state.reviews=Object.create(null);state.reviewsDirty=false;state.filter='all';
  $('lab-result').hidden=true;$('lab-legend').hidden=true;$('normal-legend').hidden=false;
  ['water-value','unknown-value','coverage-value','date-value'].forEach(id=>$(id).textContent='—');
  $('map-stack').hidden=true;$('map-placeholder').hidden=false;$('zone-detail').hidden=true;
  $('zone-list').replaceChildren(element('p','Analysis in progress…','empty'));$('trace').replaceChildren();$('timeline').replaceChildren();
  $('zone-count').textContent='00';$('source-caption').textContent='Awaiting analysis';$('scene-title').textContent='Inspecting observation';
  $('scene-tag').textContent='NO RESULT';$('region-code').textContent='';$('engine').textContent='No accepted analysis';
  $('map-caption').textContent='No conclusion until analysis completes.';$('coordinate-label').textContent='';
}
async function fetchJSON(url, options={}) {
  const response=await fetch(url,{...options,cache:'no-store'});
  const body=await response.json().catch(()=>null);
  if(!response.ok)throw new Error(typeof body?.detail==='string'?body.detail:'The service could not complete this request.');
  if(!body)throw new Error('The service returned an unreadable response.');
  return body;
}
async function analyze() {
  if(state.controller)return;
  stopDrawing();message('');clearReport();busy(true);
  const controller=new AbortController();state.controller=controller;
  let timedOut=false;
  const timer=setTimeout(()=>{timedOut=true;controller.abort();},90000);
  try {
    let result;
    if(state.lab){
      result=await fetchJSON(`/api/lab/${encodeURIComponent(state.lab)}/run`,{method:'POST',signal:controller.signal});
    }else if(state.example){
      result=await fetchJSON(`/api/examples/${encodeURIComponent(state.example)}/analyze`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:state.zones?JSON.stringify(state.zones):''});
    }else{
      const form=new FormData();
      form.append('current',state.upload.current);form.append('observed_on',state.upload.date);
      if(state.upload.reference){form.append('reference',state.upload.reference);form.append('reference_on',state.upload.referenceDate);form.append('same_orbit',String(state.upload.sameOrbit));}
      if(state.zones)form.append('zones',JSON.stringify(state.zones));
      result=await fetchJSON('/api/analyze',{method:'POST',body:form,signal:controller.signal});
    }
    if(controller.signal.aborted)return;
    if(state.lab&&result.kind==='rejection_check'){
      renderLab(result.lab,result.observed_rejection);$('scene-title').textContent='Input rejected — no map produced';
      $('scene-tag').textContent='SYNTHETIC TEST';$('region-code').textContent='EVIDENCE LAB';$('source-caption').textContent='Rejected test input';
      $('zone-list').replaceChildren(element('p','No inspection queue: unsupported input was rejected.','empty'));
      $('map-caption').textContent='Synthetic rejection exercise. No measured scene summary or field conclusion is available.';
      return;
    }
    state.report=M.validateResult(result);state.selected=result.zones[0]?.id;render();
  }catch(error){
    message(controller.signal.aborted?(timedOut?'Analysis timed out. The server may still finish; choose an example or submit again to retry.':'Stopped waiting. The server may still finish. No result has been accepted.'):error instanceof TypeError?'Cannot reach the local service. Start FieldWatch and retry.':error.message);
    $('zone-list').replaceChildren(element('p','No result. Retry an example or upload.','empty'));
  }finally{clearTimeout(timer);state.controller=null;busy(false);}
}
function render() {
  const r=state.report;
  $('water-value').textContent=M.areaLabel(r.summary.water_observed_ha);$('unknown-value').textContent=M.areaLabel(r.summary.uncertain_ha);
  $('coverage-value').textContent=percent(r.summary.assessed_fraction);$('date-value').textContent=r.source.observed_on||'Not supplied';
  $('source-caption').textContent=r.context?'Historical · Sentinel-1':'User-supplied acquisition';$('scene-title').textContent=r.name;
  $('scene-tag').textContent=r.context?'HISTORICAL':'UPLOADED';$('region-code').textContent=(state.example||'YOUR STUDY AREA').toUpperCase();
  if(r.lab){$('scene-tag').textContent=r.lab.kind==='synthetic'?'SYNTHETIC TEST':'REFERENCE REPLAY';$('source-caption').textContent=r.lab.kind==='synthetic'?'Synthetic test date':'Historical · evaluation replay';$('region-code').textContent='EVIDENCE LAB';renderLab(r.lab);}
  $('coordinate-label').textContent=`Latitude ${r.source.bounds[1].toFixed(3)}° to ${r.source.bounds[3].toFixed(3)}° · ${r.source.crs}`;
  $('map-placeholder').hidden=true;$('map-stack').hidden=false;
  $('satellite').width=r.source.width;$('satellite').height=r.source.height;
  for(const option of $('view-select').options)option.disabled=!r.images[option.value];
  $('view-select').value=r.images.optical?'optical':'radar';
  $('zone-svg').setAttribute('viewBox',`0 0 ${r.source.width} ${r.source.height}`);$('zone-svg').setAttribute('preserveAspectRatio','none');
  $('zone-count').textContent=String(r.zones.length).padStart(2,'0');
  renderView();renderZones();renderDetail();renderTimeline();
  $('trace').replaceChildren(...r.trace.map(step=>{const item=element('li');const body=element('div');body.append(element('strong',step.action.replaceAll('_',' ')),document.createTextNode(step.outcome));item.append(body);return item;}));
  $('engine').textContent=`OpenCV ${r.engine.opencv} · ${r.elapsed_ms} ms · ${r.engine.policy}`;
}
function renderView() {
  if(!state.report)return;
  const r=state.report,view=$('view-select').value;
  const layerNames={optical:'optical context',earlier:'earlier VV radar',radar:'current VV radar',errors:'evaluation error map',reference_labels:'independent reference labels'};
  $('satellite').src=r.images[view];$('satellite').alt=`${r.name} — ${layerNames[view]}`;
  $('evidence').src=view==='earlier'?r.images.earlier_evidence:r.images.evidence;
  const evaluationView=['errors','reference_labels'].includes(view);
  $('evidence').hidden=evaluationView||!$('evidence-toggle').checked;
  $('evidence-toggle').disabled=evaluationView;
  $('lab-legend').hidden=view!=='errors';$('normal-legend').hidden=evaluationView;
  if(evaluationView){$('map-caption').textContent=(view==='errors'?'Evaluation only: blue = correct water, coral = false alarm, violet = missed water (including unknown predictions), grey = labeled no-water without a water prediction (including unknown), dark = unlabeled.':'Independent reference labels: blue = labeled water, grey = labeled no-water, dark = excluded NoData. Labels are not supplied to inference.')+' Selected exposed-test replay; not a new accuracy estimate.';return;}
  const note=view==='optical'?`Optical context: ${r.context.optical_date}; classification uses radar from ${r.source.observed_on}. Cloud cover is not screened in this preview.`:view==='earlier'?`Earlier radar: ${r.reference.observed_on}. The inspection queue still describes the current observation.`:'VV radar backscatter shown on a fixed −30 to 0 dB scale. Dark does not always mean water.';
  $('map-caption').textContent=note+(r.context?.optical_status==='unavailable'?' Optical context is unavailable; radar analysis is unaffected.':'')+' Zones: '+r.zone_basis+'.';
}
function rings(geometry){return geometry.type==='MultiPolygon'?geometry.coordinates.map(p=>p[0]):[geometry.coordinates[0]];}
function renderZones() {
  const r=state.report;if(!r)return;
  document.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.filter===state.filter)));
  const filtered=r.zones.filter(z=>state.filter==='all'||z.status===state.filter);
  $('zone-list').replaceChildren(...filtered.map(zone=>{
    const button=element('button',undefined,'zone-card');button.dataset.status=zone.status;button.setAttribute('aria-pressed',String(zone.id===state.selected));
    const title=element('div',undefined,'zone-line');title.append(element('span',zone.name),element('span',M.statuses[zone.status],'status-label'));
    const bar=svgElement('svg',{viewBox:'0 0 100 4',height:4,width:'100%','aria-hidden':'true',class:'zone-bar'});
    bar.append(svgElement('rect',{x:0,y:0,width:100,height:4,fill:'#e8eae1'}),svgElement('rect',{x:0,y:0,width:zone.water_fraction*100,height:4,fill:'#269dc6'}),svgElement('rect',{x:zone.water_fraction*100,y:0,width:(1-zone.coverage)*100,height:4,fill:'#e7bf63'}));
    button.append(title,bar,element('small',`${M.areaLabel(zone.water_observed_ha)} ha water · ${percent(1-zone.coverage)} uncertain${state.reviews[zone.id]?' · reviewed':''}`));
    button.addEventListener('click',()=>selectZone(zone.id));return button;
  }));
  if(!filtered.length)$('zone-list').append(element('p','No zones in this queue.','empty'));
  const svg=$('zone-svg');svg.replaceChildren();
  svg.style.setProperty('--zone-label-size',`${r.source.width*11/512}px`);
  svg.style.setProperty('--zone-label-stroke',`${r.source.width*3/512}px`);
  if($('zones-toggle').checked)for(const [index,zone]of r.zones.entries()){
    for(const ring of rings(zone.pixel_geometry)){
      const poly=svgElement('polygon',{points:ring.map(p=>p.join(',')).join(' '),tabindex:0,role:'button','aria-label':`${zone.name}: ${M.statuses[zone.status]}`,class:zone.id===state.selected?'selected':''});
      poly.addEventListener('click',e=>{if(!state.drawing){e.stopPropagation();selectZone(zone.id);}});
      poly.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectZone(zone.id);}});svg.append(poly);
      const coords=ring.slice(0,-1),x=coords.reduce((s,p)=>s+p[0],0)/coords.length,y=coords.reduce((s,p)=>s+p[1],0)/coords.length;
      const label=svgElement('text',{x,y,'text-anchor':'middle'});label.textContent=zone.id.startsWith('sector-')?zone.id.slice(7).padStart(2,'0'):String(index+1).padStart(2,'0');svg.append(label);
    }
  }
  if(state.points.length)svg.append(svgElement('polygon',{points:state.points.map(p=>p.join(',')).join(' '),class:'draft'}));
}
function captureReviewDraft(){
  if(!state.report || !state.selected)return;
  const outcome=$('review-outcome').value,note=$('review-note').value.slice(0,1000);
  if(M.reviewChanged(state.reviews[state.selected],outcome,note)){
    state.reviews[state.selected]={outcome,note,recorded_at:new Date().toISOString()};state.reviewsDirty=true;
  }
}
function confirmReviewReplacement(){
  if(state.controller)return false;
  captureReviewDraft();
  return !state.reviewsDirty || window.confirm('This will clear unexported session notes, even if the next analysis fails. Cancel to export them first. Continue?');
}
window.addEventListener('beforeunload',event=>{
  captureReviewDraft();if(state.reviewsDirty){event.preventDefault();event.returnValue='';}
});
function selectZone(id){captureReviewDraft();state.selected=id;renderZones();renderDetail();}
function renderDetail(){
  const r=state.report,z=r?.zones.find(z=>z.id===state.selected);$('zone-detail').hidden=!z;if(!z)return;
  $('detail-title').textContent=z.name;$('detail-reason').textContent=z.reasons.join(' ');
  $('decision-gate').hidden=!z.decision;
  if(z.decision){$('decision-level').textContent=z.decision.level.replaceAll('_',' ').toUpperCase();$('decision-next').textContent=z.decision.next_step;$('decision-reasons').textContent=z.decision.reasons.join(' ');}
  const stats=[[M.areaLabel(z.area_ha)+' ha','Scene overlap'],[M.areaLabel(z.water_observed_ha)+' ha','Water-like evidence'],[percent(1-z.coverage),'Uncertain within overlap']];
  if(z.spatial_support)stats.push([z.spatial_support.scene_clipped?'Partial':'Within image','Boundary coverage (not pixel quality)']);
  if(z.new_water_candidate_ha!==null)stats.push([M.areaLabel(z.new_water_candidate_ha)+' ha','New water candidate'],[M.areaLabel(z.repeat_water_observed_ha)+' ha','Water at both observations']);
  $('zone-stats').replaceChildren(...stats.map(([value,label])=>{const item=element('span');item.append(element('strong',value),document.createTextNode(label));return item;}));
  const review=state.reviews[z.id];$('review-outcome').value=review?.outcome||'unreviewed';$('review-note').value=review?.note||'';
}
function renderTimeline(){
  const r=state.report,items=[];
  if(r.reference)items.push([r.reference.observed_on,'Earlier radar observation',`Compared across a ${r.reference.interval_days}-day interval. Continuous conditions between dates are unknown.`]);
  else items.push(['NO EARLIER SCENE','Flood onset not established','A single observation cannot distinguish new flooding from permanent or intentionally present water.']);
  items.push([r.source.observed_on||'DATE NOT SUPPLIED','Current radar observation',`Source digest ${r.source.sha256.slice(0,16)}… · ${r.source.width} × ${r.source.height} pixels`]);
  items.push(['HUMAN FOLLOW-UP','Confirm the local context','No field visit, alert or intervention is scheduled automatically.']);
  $('timeline').replaceChildren(...items.map(([date,title,note])=>{const item=element('div',undefined,'timeline-item');item.append(element('small',date),element('strong',title),document.createTextNode(note));return item;}));
}
function stopDrawing(){state.drawing=false;state.points=[];$('draw-controls').hidden=true;$('map-stack').classList.remove('draw-mode');if(state.report)renderZones();}
$('draw-button').addEventListener('click',()=>{state.drawing=true;state.points=[];$('draw-controls').hidden=false;$('map-stack').classList.add('draw-mode');message('Drawing replaces the illustrative grid on the first added zone. Existing session reviews are reset when zones change.');});
$('zone-svg').addEventListener('click',event=>{if(!state.drawing)return;const box=$('zone-svg').getBoundingClientRect();state.points.push([(event.clientX-box.left)/box.width*state.report.source.width,(event.clientY-box.top)/box.height*state.report.source.height]);renderZones();});
$('finish-draw').addEventListener('click',()=>{try{const features=state.zones?.features||[];if(features.length>=100)throw new Error('Use at most 100 review zones.');const feature=M.featureFromPoints(state.points,state.report.source,features.length+1,state.report.zones.map(z=>z.id));if(!confirmReviewReplacement())return;state.zones={type:'FeatureCollection',features:[...features,feature]};analyze();}catch(error){message(error.message);}});
$('cancel-draw').addEventListener('click',()=>{stopDrawing();message('');});
$('import-button').addEventListener('click',()=>$('geojson-file').click());
$('geojson-file').addEventListener('change',async event=>{const file=event.target.files[0],report=state.report;event.target.value='';if(!file)return;try{if(file.size>200000)throw new Error('Use a GeoJSON file under 200 KB.');const value=JSON.parse(await file.text());if(!value||value.type!=='FeatureCollection'||!Array.isArray(value.features))throw new Error('Import a GeoJSON FeatureCollection.');if(state.report!==report||state.controller)throw new Error('Observation changed while reading the file. Choose it again.');if(!confirmReviewReplacement())return;state.zones=value;await analyze();}catch(error){message(error.message);}});
$('save-review').addEventListener('click',()=>{captureReviewDraft();renderZones();message('Review saved in this browser session. Export it before closing. The algorithmic findings are unchanged.');});
$('export-button').addEventListener('click',()=>{if(!state.report)return;captureReviewDraft();const value=M.reviewExport(state.report,state.reviews);const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const link=element('a');link.href=url;link.download=`fieldwatch-review-${state.report.source.sha256.slice(0,12)}.json`;link.click();state.reviewsDirty=false;message('Export requested. Verify the downloaded file before leaving. Locations and human notes may be sensitive.');setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('geojson-export-button').addEventListener('click',()=>{
  if(!state.report||state.controller)return;
  captureReviewDraft();
  const value=M.geojsonExport(state.report,state.reviews);
  const url=URL.createObjectURL(new Blob([JSON.stringify(value)],{type:'application/geo+json'}));
  const link=element('a');link.href=url;link.download=`fieldwatch-zones-${state.report.source.sha256.slice(0,12)}.geojson`;link.click();
  // A GIS handoff is not a restorable review backup. Keep the unsaved-note guard.
  message('GeoJSON requested for all review zones, including hidden queues. Boundaries are not water outlines; areas cover scene overlap only. Locations and notes may be sensitive. Use Export review for a restorable notes backup.');
  setTimeout(()=>URL.revokeObjectURL(url),1000);
});
$('restore-button').addEventListener('click',()=>$('review-file').click());
$('review-file').addEventListener('change',async event=>{
  const file=event.target.files[0],report=state.report;event.target.value='';if(!file||!report)return;
  try{
    if(file.size>2*1024*1024)throw new Error('Use a review export under 2 MiB.');
    const value=JSON.parse(await file.text());
    if(state.report!==report||state.controller)throw new Error('Observation changed while reading the file. Choose it again.');
    const reviews=M.restoreReviews(report,value);
    if(!confirmReviewReplacement())return;
    state.reviews=reviews;state.reviewsDirty=false;renderZones();renderDetail();
    message(`Restored ${Object.keys(reviews).length} human reviews locally. These are unverified annotations, not authenticated findings. Measurements are unchanged.`);
  }catch(error){message(error.message);}
});
$('view-select').addEventListener('change',renderView);$('evidence-toggle').addEventListener('change',renderView);$('zones-toggle').addEventListener('change',renderZones);
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;renderZones();}));
$('cancel-button').addEventListener('click',()=>state.controller?.abort());
$('method-button').addEventListener('click',()=>$('method-dialog').showModal());$('upload-button').addEventListener('click',()=>$('upload-dialog').showModal());
document.querySelectorAll('.close-dialog').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
$('upload-form').addEventListener('submit',event=>{event.preventDefault();const current=$('current-file').files[0],reference=$('reference-file').files[0];if(!current)return;
  if([current,reference].some(file=>file&&file.size>24*1024*1024)){message('Each GeoTIFF must be at most 24 MiB.');$('upload-dialog').close();return;}
  if(reference&&(!$('reference-date').value||!$('same-orbit').checked)){message('For comparison, supply the earlier date and confirm matching acquisitions.');$('upload-dialog').close();return;}
  if(!confirmReviewReplacement())return;
  state.upload={current,reference,date:$('current-date').value,referenceDate:$('reference-date').value,sameOrbit:$('same-orbit').checked};state.example=null;state.lab=null;state.zones=null;
  document.querySelectorAll('.example').forEach(b=>b.setAttribute('aria-pressed','false'));$('upload-dialog').close();analyze();
});
async function init(){
  try{const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);let examples;try{examples=await fetchJSON('/api/examples',{signal:controller.signal});}finally{clearTimeout(timer);}
    $('examples').replaceChildren(...examples.map((item,index)=>{const button=element('button',undefined,'example');button.setAttribute('aria-pressed','false');button.append(element('span',String(index+1).padStart(2,'0'),'example-number'));const caption=element('span');caption.append(element('strong',item.title),element('small',item.date));button.append(caption);button.addEventListener('click',()=>{if(!confirmReviewReplacement())return;state.example=item.id;state.lab=null;state.upload=null;state.zones=null;document.querySelectorAll('.example').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));analyze();});return button;}));
    if(examples.some(item=>item.available))document.querySelectorAll('.example')[examples.findIndex(item=>item.available)].click();
    else message('The public demo has not been downloaded. Run: python scripts/fetch_fieldwatch_data.py --split demo. You can also upload your own calibrated radar.');
  }catch(error){message('Cannot load examples. Start the FieldWatch service and reload this page.');}
}
function renderLab(lab,rejection=''){
  $('lab-result').hidden=false;$('lab-kind').textContent=lab.kind==='synthetic'?'SYNTHETIC CONTRACT CHECK':'REAL DATA / SELECTED REPLAY';
  $('lab-title').textContent=lab.title;$('lab-question').textContent=lab.question;$('lab-notice').textContent=lab.notice;
  $('lab-lesson').textContent=lab.lesson;$('lab-rejection').textContent=rejection;
  $('lab-checks').replaceChildren(...(lab.checks||[]).map(check=>element('li',`${check.passed?'PASS':'FAIL'} · ${check.name}`,check.passed?'check-pass':'check-fail')));
  const stats=lab.metrics?[[metricPercent(lab.metrics.precision),'Water precision'],[metricPercent(lab.metrics.recall),'Water recall'],[metricPercent(lab.metrics.iou),'Water IoU'],[number(lab.metrics.false_positive_pixels),'False-alarm pixels'],[number(lab.metrics.missed_water_pixels),'Missed-water pixels'],[number(lab.metrics.unknown_water_pixels),'Of those: unknown']]:[];
  $('lab-metrics').replaceChildren(...stats.map(([value,label])=>{const item=element('div');item.append(element('strong',value),element('small',label));return item;}));
}
$('close-lab').addEventListener('click',()=>{$('lab-library').hidden=true;});
$('lab-button').addEventListener('click',async()=>{
  $('lab-library').hidden=false;
  if($('lab-cases').children.length)return;
  try{const items=await fetchJSON('/api/lab',{signal:AbortSignal.timeout(10000)});
    $('lab-cases').replaceChildren(...items.map(item=>{const button=element('button',undefined,'lab-card');
      button.append(element('small',item.kind==='synthetic'?'SYNTHETIC CONTRACT':'REGIONAL REPLAY'),element('strong',item.title),element('span',item.question));
      if(!item.available)button.append(element('small','Download required: --split lab'));
      button.disabled=!!state.controller;
      button.addEventListener('click',()=>{if(!confirmReviewReplacement())return;state.lab=item.id;state.example=null;state.upload=null;state.zones=null;$('lab-library').hidden=true;document.querySelectorAll('.example').forEach(b=>b.setAttribute('aria-pressed','false'));analyze();});return button;}));
  }catch(error){message('Cannot load the Evidence Lab. Check the local service and reopen the library.');}
});
init();

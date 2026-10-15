'use strict';
const $ = id => document.getElementById(id);
const M = window.FieldWatchModel;
const state = {report:null,example:null,upload:null,zones:null,reviews:Object.create(null),selected:null,filter:'all',controller:null,drawing:false,points:[]};
const number = value => new Intl.NumberFormat('en',{maximumFractionDigits:1}).format(value);
const percent = value => `${Math.round(value*100)}%`;
function element(tag, text, className) {const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function svgElement(tag,attrs) {const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const [key,value]of Object.entries(attrs))el.setAttribute(key,String(value));return el;}
function message(text) {$('message').textContent=text;$('message').hidden=!text;}
function busy(active) {
  $('busy').hidden=!active;
  document.querySelectorAll('.example,#upload-button,#export-button,#draw-button,#import-button').forEach(el=>el.disabled=active || (['export-button','draw-button','import-button'].includes(el.id)&&!state.report));
  $('draw-button').disabled=active || !state.report || state.report.source.crs!=='EPSG:4326';
}
function clearReport() {
  state.report=null;state.selected=null;state.reviews=Object.create(null);state.filter='all';
  ['water-value','unknown-value','coverage-value','date-value'].forEach(id=>$(id).textContent='—');
  $('map-stack').hidden=true;$('map-placeholder').hidden=false;$('zone-detail').hidden=true;
  $('zone-list').replaceChildren(element('p','Analysis in progress…','empty'));$('trace').replaceChildren();$('timeline').replaceChildren();
  $('zone-count').textContent='00';$('source-caption').textContent='Awaiting analysis';$('scene-title').textContent='Inspecting observation';
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
    if(state.example){
      result=await fetchJSON(`/api/examples/${encodeURIComponent(state.example)}/analyze`,{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:state.zones?JSON.stringify(state.zones):''});
    }else{
      const form=new FormData();
      form.append('current',state.upload.current);form.append('observed_on',state.upload.date);
      if(state.upload.reference){form.append('reference',state.upload.reference);form.append('reference_on',state.upload.referenceDate);form.append('same_orbit',String(state.upload.sameOrbit));}
      if(state.zones)form.append('zones',JSON.stringify(state.zones));
      result=await fetchJSON('/api/analyze',{method:'POST',body:form,signal:controller.signal});
    }
    if(controller.signal.aborted)return;
    state.report=M.validateResult(result);state.selected=result.zones[0]?.id;render();
  }catch(error){
    message(controller.signal.aborted?(timedOut?'Analysis timed out. The server may still finish; choose an example or submit again to retry.':'Stopped waiting. The server may still finish. No result has been accepted.'):error instanceof TypeError?'Cannot reach the local service. Start FieldWatch and retry.':error.message);
    $('zone-list').replaceChildren(element('p','No result. Retry an example or upload.','empty'));
  }finally{clearTimeout(timer);state.controller=null;busy(false);}
}
function render() {
  const r=state.report;
  $('water-value').textContent=number(r.summary.water_observed_ha);$('unknown-value').textContent=number(r.summary.uncertain_ha);
  $('coverage-value').textContent=percent(r.summary.assessed_fraction);$('date-value').textContent=r.source.observed_on||'Not supplied';
  $('source-caption').textContent=r.context?'Historical · Sentinel-1':'User-supplied acquisition';$('scene-title').textContent=r.name;
  $('scene-tag').textContent=r.context?'HISTORICAL':'UPLOADED';$('region-code').textContent=(state.example||'YOUR STUDY AREA').toUpperCase();
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
  $('satellite').src=r.images[view];$('satellite').alt=`${r.name} — ${view==='optical'?'optical context':view==='earlier'?'earlier VV radar':'current VV radar'}`;
  $('evidence').src=view==='earlier'?r.images.earlier_evidence:r.images.evidence;
  $('evidence').hidden=!$('evidence-toggle').checked;
  const note=view==='optical'?`Optical context: ${r.context.optical_date}; classification uses radar from ${r.source.observed_on}. Cloud cover is not screened in this preview.`:view==='earlier'?`Earlier radar: ${r.reference.observed_on}. The inspection queue still describes the current observation.`:'VV radar backscatter shown on a fixed −30 to 0 dB scale. Dark does not always mean water.';
  $('map-caption').textContent=note+' Zones: '+r.zone_basis+'.';
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
    button.append(title,bar,element('small',`${number(zone.water_observed_ha)} ha water · ${percent(1-zone.coverage)} uncertain${state.reviews[zone.id]?' · reviewed':''}`));
    button.addEventListener('click',()=>selectZone(zone.id));return button;
  }));
  if(!filtered.length)$('zone-list').append(element('p','No zones in this queue.','empty'));
  const svg=$('zone-svg');svg.replaceChildren();
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
function selectZone(id){state.selected=id;renderZones();renderDetail();}
function renderDetail(){
  const r=state.report,z=r?.zones.find(z=>z.id===state.selected);$('zone-detail').hidden=!z;if(!z)return;
  $('detail-title').textContent=z.name;$('detail-reason').textContent=z.reasons.join(' ');
  const stats=[[number(z.area_ha)+' ha','Scene overlap'],[number(z.water_observed_ha)+' ha','Water-like evidence'],[percent(1-z.coverage),'Uncertain']];
  if(z.new_water_candidate_ha!==null)stats.push([number(z.new_water_candidate_ha)+' ha','New water candidate'],[number(z.repeat_water_observed_ha)+' ha','Water at both observations']);
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
$('finish-draw').addEventListener('click',()=>{try{const features=state.zones?.features||[];const feature=M.featureFromPoints(state.points,state.report.source,features.length+1);state.zones={type:'FeatureCollection',features:[...features,feature]};analyze();}catch(error){message(error.message);}});
$('cancel-draw').addEventListener('click',()=>{stopDrawing();message('');});
$('import-button').addEventListener('click',()=>$('geojson-file').click());
$('geojson-file').addEventListener('change',async event=>{const file=event.target.files[0];event.target.value='';if(!file)return;try{if(file.size>200000)throw new Error('Use a GeoJSON file under 200 KB.');const value=JSON.parse(await file.text());if(value.type!=='FeatureCollection'||!Array.isArray(value.features))throw new Error('Import a GeoJSON FeatureCollection.');state.zones=value;await analyze();}catch(error){message(error.message);}});
$('save-review').addEventListener('click',()=>{if(!state.selected)return;state.reviews[state.selected]={outcome:$('review-outcome').value,note:$('review-note').value.slice(0,1000),recorded_at:new Date().toISOString()};renderZones();message('Review saved in this browser session. Export it before closing. The algorithmic findings are unchanged.');});
$('export-button').addEventListener('click',()=>{if(!state.report)return;const value=M.reviewExport(state.report,state.reviews);const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const link=element('a');link.href=url;link.download=`fieldwatch-review-${state.report.source.sha256.slice(0,12)}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
$('view-select').addEventListener('change',renderView);$('evidence-toggle').addEventListener('change',renderView);$('zones-toggle').addEventListener('change',renderZones);
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{state.filter=button.dataset.filter;renderZones();}));
$('cancel-button').addEventListener('click',()=>state.controller?.abort());
$('method-button').addEventListener('click',()=>$('method-dialog').showModal());$('upload-button').addEventListener('click',()=>$('upload-dialog').showModal());
document.querySelectorAll('.close-dialog').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
$('upload-form').addEventListener('submit',event=>{event.preventDefault();const current=$('current-file').files[0],reference=$('reference-file').files[0];if(!current)return;
  if([current,reference].some(file=>file&&file.size>24*1024*1024)){message('Each GeoTIFF must be at most 24 MiB.');$('upload-dialog').close();return;}
  if(reference&&(!$('reference-date').value||!$('same-orbit').checked)){message('For comparison, supply the earlier date and confirm matching acquisitions.');$('upload-dialog').close();return;}
  state.upload={current,reference,date:$('current-date').value,referenceDate:$('reference-date').value,sameOrbit:$('same-orbit').checked};state.example=null;state.zones=null;
  document.querySelectorAll('.example').forEach(b=>b.setAttribute('aria-pressed','false'));$('upload-dialog').close();analyze();
});
async function init(){
  try{const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);let examples;try{examples=await fetchJSON('/api/examples',{signal:controller.signal});}finally{clearTimeout(timer);}
    $('examples').replaceChildren(...examples.map((item,index)=>{const button=element('button',undefined,'example');button.setAttribute('aria-pressed','false');button.append(element('span',String(index+1).padStart(2,'0'),'example-number'));const caption=element('span');caption.append(element('strong',item.title),element('small',item.date));button.append(caption);button.addEventListener('click',()=>{state.example=item.id;state.upload=null;state.zones=null;document.querySelectorAll('.example').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));analyze();});return button;}));
    if(examples.some(item=>item.available))document.querySelectorAll('.example')[examples.findIndex(item=>item.available)].click();
    else message('The public demo has not been downloaded. Run: python scripts/fetch_fieldwatch_data.py --split demo. You can also upload your own calibrated radar.');
  }catch(error){message('Cannot load examples. Start the FieldWatch service and reload this page.');}
}
init();

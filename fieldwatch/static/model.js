(function(root) {
  'use strict';
  const statuses = {inspect_water:'Inspect water',resolve_uncertainty:'Resolve uncertainty',no_signal:'Low signal'};
  function areaLabel(value) {
    return value>0 && value<.1 ? '<0.1' : new Intl.NumberFormat('en',{maximumFractionDigits:1}).format(value);
  }
  function validateResult(value) {
    if (!value || value.schema_version !== '1.0' || !value.source || !value.images || !Array.isArray(value.zones) || !value.summary || !Array.isArray(value.trace)) throw new Error('The service returned an incomplete report.');
    if (!Number.isInteger(value.source.width) || !Number.isInteger(value.source.height) || value.source.width < 16 || value.source.height < 16 || value.source.width * value.source.height > 2000000) throw new Error('The service returned invalid image dimensions.');
    if (typeof value.source.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(value.source.sha256)) throw new Error('The report is missing a valid source digest.');
    for (const zone of value.zones) if (!statuses[zone.status] || !zone.pixel_geometry || !Array.isArray(zone.reasons)) throw new Error('The report contains an invalid review zone.');
    for (const image of Object.values(value.images)) if (image && (typeof image !== 'string' || !image.startsWith('data:image/png;base64,'))) throw new Error('The service returned an unsupported preview.');
    return value;
  }
  function reviewExport(report, reviews) {
    const {images, ...rest} = report;
    return {...rest, human_reviews: Object.entries(reviews).filter(([id]) => report.zones.some(z => z.id === id)).map(([zone_id, review]) => ({zone_id,...review})),
      review_notice:'Human notes are unverified reports, separate from algorithmic findings. Locations and notes may be sensitive.'};
  }
  function reviewChanged(existing, outcome, note) {
    return (existing?.outcome || 'unreviewed')!==outcome || (existing?.note || '')!==note;
  }
  function canonical(value, depth=0) {
    if(depth>32)throw new Error('Review export is too deeply nested.');
    if(Array.isArray(value))return value.map(v=>canonical(v,depth+1));
    if(value && typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k],depth+1)]));
    return value;
  }
  function reviewContext(report) {
    if(!report || report.schema_version!=='1.0' || !report.source?.sha256 || !report.engine?.policy || !Array.isArray(report.zones))throw new Error('Choose a FieldWatch review export.');
    return JSON.stringify(canonical({schema_version:report.schema_version,source:report.source,reference:report.reference,
      engine_policy:report.engine.policy,policy:report.policy,reference_policy:report.reference_policy,
      zones:[...report.zones].sort((a,b)=>String(a.id).localeCompare(String(b.id)))}));
  }
  function restoreReviews(report, exported) {
    if(!exported || exported.images || !Array.isArray(exported.human_reviews) || exported.human_reviews.length>100)throw new Error('Choose an image-free FieldWatch review export with at most 100 notes.');
    if(reviewContext(report)!==reviewContext(exported))throw new Error('Review does not match this observation, dates, policy and zone geometry. Load the original inputs first.');
    const reviews=Object.create(null),ids=new Set(report.zones.map(z=>z.id));
    for(const row of exported.human_reviews){
      if(!row || typeof row.zone_id!=='string' || !ids.has(row.zone_id) || Object.hasOwn(reviews,row.zone_id)
        || !['unreviewed','water_confirmed','false_alarm','follow_up'].includes(row.outcome)
        || typeof row.note!=='string' || row.note.length>1000
        || typeof row.recorded_at!=='string' || row.recorded_at.length>40 || !Number.isFinite(Date.parse(row.recorded_at)))throw new Error('Review export contains invalid, duplicate or unrelated notes.');
      // Import only human annotations; never replace measurements or inference.
      reviews[row.zone_id]={outcome:row.outcome,note:row.note,recorded_at:row.recorded_at,restored_from_export:true};
    }
    return reviews;
  }
  function pixelToGeo(point, source) {
    if (source.crs !== 'EPSG:4326') throw new Error('Drawing currently requires EPSG:4326. Import longitude/latitude GeoJSON for projected scenes.');
    const [a,b,c,d,e,f] = source.transform;
    return [a*point[0]+b*point[1]+c,d*point[0]+e*point[1]+f];
  }
  function featureFromPoints(points, source, index, existingIds=[]) {
    if (points.length < 3 || points.length > 199) throw new Error('Use 3–199 corners.');
    if (points.some(([x,y]) => !Number.isFinite(x) || !Number.isFinite(y) || x<0 || y<0 || x>source.width || y>source.height)) throw new Error('Keep every corner inside the image.');
    const ring = points.map(p => pixelToGeo(p,source)); ring.push([...ring[0]]);
    const taken=new Set(existingIds.map(String));
    while(taken.has('drawn-'+index))index++;
    return {type:'Feature',properties:{id:'drawn-'+index,name:'Drawn review zone '+index,crop:'unknown'},geometry:{type:'Polygon',coordinates:[ring]}};
  }
  const api={statuses,areaLabel,validateResult,reviewExport,reviewChanged,restoreReviews,pixelToGeo,featureFromPoints};
  if (typeof module !== 'undefined' && module.exports) module.exports=api;
  else root.FieldWatchModel=api;
})(typeof window !== 'undefined' ? window : globalThis);

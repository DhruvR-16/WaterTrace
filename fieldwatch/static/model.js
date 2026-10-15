(function(root) {
  'use strict';
  const statuses = {inspect_water:'Inspect water',resolve_uncertainty:'Resolve uncertainty',no_signal:'Low signal'};
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
  function pixelToGeo(point, source) {
    if (source.crs !== 'EPSG:4326') throw new Error('Drawing currently requires EPSG:4326. Import longitude/latitude GeoJSON for projected scenes.');
    const [a,b,c,d,e,f] = source.transform;
    return [a*point[0]+b*point[1]+c,d*point[0]+e*point[1]+f];
  }
  function featureFromPoints(points, source, index) {
    if (points.length < 3 || points.length > 199) throw new Error('Use 3–199 corners.');
    if (points.some(([x,y]) => !Number.isFinite(x) || !Number.isFinite(y) || x<0 || y<0 || x>source.width || y>source.height)) throw new Error('Keep every corner inside the image.');
    const ring = points.map(p => pixelToGeo(p,source)); ring.push([...ring[0]]);
    return {type:'Feature',properties:{id:'drawn-'+index,name:'Drawn review zone '+index,crop:'unknown'},geometry:{type:'Polygon',coordinates:[ring]}};
  }
  const api={statuses,validateResult,reviewExport,pixelToGeo,featureFromPoints};
  if (typeof module !== 'undefined' && module.exports) module.exports=api;
  else root.FieldWatchModel=api;
})(typeof window !== 'undefined' ? window : globalThis);

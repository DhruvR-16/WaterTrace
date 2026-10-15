const {test}=require('node:test');
const assert=require('node:assert/strict');
const model=require('../fieldwatch/static/model.js');
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
test('short or outside polygons rejected',()=>{
  assert.throws(()=>model.featureFromPoints([[0,0]],{},1));
  assert.throws(()=>model.featureFromPoints([[0,0],[20,0],[200,20]],{width:100,height:100},1));
});
test('exports exclude pixels and unrelated notes',()=>{
  const result=model.reviewExport({images:{radar:'pixels'},zones:[{id:'a'}],source:{sha256:'digest'}},{a:{note:'human'},b:{note:'unrelated'}});
  assert.equal(result.images,undefined);assert.equal(result.human_reviews.length,1);assert.equal(result.human_reviews[0].zone_id,'a');
});
test('malformed reports rejected',()=>{
  for(const value of [null,{},[],{schema_version:'1.0'}])assert.throws(()=>model.validateResult(value));
});
test('untrusted preview URLs rejected',()=>{
  const value={schema_version:'1.0',source:{width:64,height:64,sha256:'a'.repeat(64)},images:{radar:'https://tracker.invalid/'},zones:[],summary:{},trace:[]};
  assert.throws(()=>model.validateResult(value));value.images.radar='data:image/png;base64,AA==';assert.equal(model.validateResult(value),value);
});

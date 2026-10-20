import test from 'node:test';import assert from 'node:assert/strict';import {validateBox,interpretBox} from './boxes.mjs';
// Isolated test-only contracts, never imported into the real catalog.
const products=[{id:'test_component',title:'Verified test component',metadata:{tax_class:'exempt_unprepared_food',unit:'each'},variants:[{id:'v',inventory_items:[{inventory_item_id:'i'}]}]}];
test('box parsing matches names but preserves unknown cost',()=>{const r=interpretBox('Box: Weekly; $8; contents: 4 Verified test component',products);assert.equal(r.box.recipe[0].quantity,4);assert.equal(r.box.recipe[0].cost_minor,null);assert.ok(r.questions.some(q=>q.includes('cost')))});
test('valid recipe references shared engine inventory',()=>{const r=validateBox({name:'Weekly',price_minor:800,recipe:[{product_id:'test_component',quantity:4,cost_minor:100}]},products);assert.deepEqual(r.errors,[]);assert.equal(r.recipe[0].inventory_id,'i');assert.equal(r.cost_minor,400)});
test('missing costs and duplicate components cannot publish',()=>{const r=validateBox({name:'Weekly',price_minor:800,recipe:[{product_id:'test_component',quantity:4},{product_id:'test_component',quantity:4}]},products);assert.ok(r.errors.some(e=>e.includes('duplicate')));assert.ok(r.errors.some(e=>e.includes('cost')))});
test('allowed swap retains exact shared-inventory recipe and rejects loss-making replacement',()=>{const replacement={...products[0],id:'test_replacement',title:'Replacement',variants:[{id:'v2',inventory_items:[{inventory_item_id:'i2'}]}]};const box={name:'Weekly',price_minor:800,recipe:[{product_id:'test_component',quantity:4,cost_minor:100}],swap:{from_product_id:'test_component',to_product_id:'test_replacement',quantity:2,cost_minor:100}};const valid=validateBox(box,[...products,replacement]);assert.deepEqual(valid.errors,[]);assert.equal(valid.variants[1].recipe[0].inventory_id,'i2');assert.equal(valid.variants[1].recipe[0].quantity,2);const invalid=validateBox({...box,swap:{...box.swap,cost_minor:500}},[...products,replacement]);assert.ok(invalid.errors.some(e=>e.includes('Swap component cost')))});

test('nested boxes and ambiguous component inventory cannot publish',()=>{
 const box={name:'Weekly',price_minor:800,recipe:[{product_id:'test_component',quantity:1,cost_minor:100}]};
 for(const invalid of [
  {...products[0],metadata:{...products[0].metadata,kind:'box'}},
  {...products[0],variants:[]},
  {...products[0],variants:[{id:'v',inventory_items:[]}]},
  {...products[0],variants:[{id:'v',inventory_items:[{inventory_item_id:'i',required_quantity:2}]}]},
  {...products[0],variants:[{id:'v',inventory_items:[{inventory_item_id:'i'},{inventory_item_id:'i2'}]}]},
 ]){const result=validateBox(box,[invalid]);assert.ok(result.errors.some(e=>e.includes('individual product')));assert.equal(result.recipe.length,0);}
});
test('malformed replacement inventory is held without throwing',()=>{
 const replacement={...products[0],id:'replacement',variants:[]};
 const box={name:'Weekly',price_minor:800,recipe:[{product_id:'test_component',quantity:1,cost_minor:100}],swap:{from_product_id:'test_component',to_product_id:'replacement',quantity:1,cost_minor:100}};
 const result=validateBox(box,[...products,replacement]);assert.ok(result.errors.some(e=>e.includes('replacement must')));assert.equal(result.variants.length,1);
});

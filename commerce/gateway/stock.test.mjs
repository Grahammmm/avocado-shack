import test from 'node:test';import assert from 'node:assert/strict';import {stockTarget} from './stock.mjs';
test('online-bin movements distinguish receipts, transfers and recounts',()=>{const base={before:12,reserved:3,reason:'Recorded stock movement'};assert.equal(stockTarget({...base,action:'receipt',quantity:2}),14);assert.equal(stockTarget({...base,action:'transfer_out',quantity:4}),8);assert.equal(stockTarget({...base,action:'recount',quantity:9}),9)});
test('counter transfers and spoilage cannot consume reservations',()=>{for(const action of ['transfer_out','spoilage'])assert.throws(()=>stockTarget({action,quantity:4,before:5,reserved:2,reason:'Counter sale'}),/reserved/);assert.throws(()=>stockTarget({action:'recount',quantity:1,before:5,reserved:2,reason:'Counted'}),/reserved/)});

const MAX=Number.MAX_SAFE_INTEGER;
const ACTIONS=['receipt','transfer_in','transfer_out','spoilage','recount','correction'];
const reason='Recorded stock movement';
const REVIEW=/^Error: Inventory quantities need review\.$/;
const safe=(target,expected)=>{assert.equal(typeof target,'number');assert.ok(Number.isSafeInteger(target),`unsafe target ${target}`);assert.equal(target,expected)};

test('stock movements reject unsafe receipt totals',()=>{
 for(const action of ['receipt','transfer_in']){
  for(const quantity of [1,2]){
   assert.ok(BigInt(MAX)+BigInt(quantity)>BigInt(MAX),'exact total is past the safe range');
   assert.throws(()=>stockTarget({action,quantity,before:MAX,reserved:0,reason}),REVIEW,`${action} +${quantity}`);
  }
  assert.throws(()=>stockTarget({action,quantity:MAX,before:MAX,reserved:0,reason}),REVIEW);
  safe(stockTarget({action,quantity:2,before:MAX-2,reserved:0,reason}),MAX);
  safe(stockTarget({action,quantity:0,before:MAX,reserved:MAX,reason}),MAX);
 }
});

test('invalid source counts never pass movement validation',()=>{
 const invalid=[NaN,Infinity,-Infinity,-1,.5,MAX+1,'12','',true,false,null,undefined,{},{valueOf:()=>3}];
 for(const action of ACTIONS)for(const bad of invalid){
  assert.throws(()=>stockTarget({action,quantity:5,before:bad,reserved:0,reason}),REVIEW,`${action} before=${String(bad)}`);
  assert.throws(()=>stockTarget({action,quantity:5,before:10,reserved:bad,reason}),REVIEW,`${action} reserved=${String(bad)}`);
 }
 for(const action of ACTIONS){
  assert.throws(()=>stockTarget({action,quantity:1,reserved:0,reason}),REVIEW,`${action} missing before`);
  assert.throws(()=>stockTarget({action,quantity:1,before:1,reason}),REVIEW,`${action} missing reserved`);
 }
});

test('reservation boundaries survive numeric guards',()=>{
 safe(stockTarget({action:'transfer_out',quantity:3,before:5,reserved:2,reason}),2);
 assert.throws(()=>stockTarget({action:'spoilage',quantity:4,before:5,reserved:2,reason}),/reserved/);
 assert.throws(()=>stockTarget({action:'transfer_out',quantity:6,before:5,reserved:0,reason}),/overdraw/);
 for(const action of ['recount','correction']){
  safe(stockTarget({action,quantity:9,before:2,reserved:7,reason}),9);
  safe(stockTarget({action,quantity:7,before:2,reserved:7,reason}),7);
  assert.throws(()=>stockTarget({action,quantity:6,before:2,reserved:7,reason}),/reserved/);
  safe(stockTarget({action,quantity:0,before:0,reserved:0,reason}),0);
  safe(stockTarget({action,quantity:MAX,before:0,reserved:MAX,reason}),MAX);
 }
});

test('all supported actions preserve exact safe totals',()=>{
 const base={before:20,reserved:4,reason};
 const expected={receipt:25,transfer_in:25,transfer_out:15,spoilage:15,recount:5,correction:5};
 for(const action of ACTIONS)safe(stockTarget({...base,action,quantity:5}),expected[action]);
 for(const action of ['receipt','transfer_in','transfer_out','spoilage'])safe(stockTarget({...base,action,quantity:0}),20);
 safe(stockTarget({action:'transfer_out',quantity:MAX,before:MAX,reserved:0,reason}),0);
 safe(stockTarget({action:'spoilage',quantity:MAX-1,before:MAX,reserved:1,reason}),1);
});

test('validation remains pure and keeps existing refusals',()=>{
 const input={action:'receipt',quantity:2,before:12,reserved:3,reason};const copy={...input};
 safe(stockTarget(input),14);assert.deepEqual(input,copy);
 assert.throws(()=>stockTarget({...input,action:'restock'}),/^Error: Choose a supported stock movement\.$/);
 for(const quantity of [-1,.5,NaN,'2',MAX+1])assert.throws(()=>stockTarget({...input,quantity}),/^Error: Quantity must be a nonnegative whole selling unit\.$/);
 for(const r of [undefined,'','  '])assert.throws(()=>stockTarget({...input,reason:r}),/^Error: Give a reason for the stock movement\.$/);
 assert.throws(()=>stockTarget({...input,action:'transfer_out',quantity:10}),/^Error: This movement would consume reserved stock or overdraw the online bin\.$/);
});

import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {Pool} from 'pg';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8')),db=new Pool({connectionString:`postgres://avoshack:${cfg.databasePassword}@127.0.0.1:55432/avoshack`});
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');async function call(url,body,cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+url,{method:body?'POST':'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const boot=(await call('/bootstrap',undefined,visitor)).data,p=boot.products.find(p=>p.title==='Hass avocado');
const start=await call('/checkout',{nonce:crypto.randomUUID(),items:[{product_id:p.id,variant_id:p.variants[0].id,quantity:1}],email:'internal-late-payment@example.invalid',slot_id:boot.slots[0].id},visitor);assert.equal(start.status,200);const id=start.data.attempt_id;
assert.equal((await call('/checkout/'+id+'/cancel',{},visitor)).data.state,'canceled');
// Fault injection into the custom simulator event ledger only; no core commerce writes.
await db.query("INSERT INTO avo.events(id,provider,payload) VALUES($1,'simulator',$2)",['sim_paid_'+id,JSON.stringify({status:'paid',attempt_id:id,test_fault:'late_after_cancel'})]);
assert.equal((await call('/reconcile',{})).status,200);
assert.equal((await call('/orders/'+id,undefined,visitor)).data.state,'payment_review');
assert.ok((await call('/exceptions')).data.attempts.some(a=>a.id===id&&a.last_error.includes('refund review')));
assert.equal((await db.query('SELECT count(*)::int AS n FROM avo.tasks WHERE attempt_id=$1',[id])).rows[0].n,0);
assert.equal((await call('/simulate-payment',{attempt_id:id},visitor)).status,409);
assert.equal((await call('/checkout/'+id+'/cancel',{},visitor)).status,409);
assert.equal((await call('/reconcile',{})).status,200);
assert.equal((await db.query("SELECT count(*)::int AS n FROM avo.audit WHERE subject=$1 AND action='late_payment_review'",[id])).rows[0].n,1);
console.log('Injected late simulator payment after canceled checkout becomes visible owner/customer payment review. No packing task created. Payment completion and cancellation blocked; reconciliation replay records one audit transition. Real Stripe event/refund remains untested.');
await db.end();

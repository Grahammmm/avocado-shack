import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {Pool} from 'pg';import {packSheet} from '../gateway/packing.mjs';
await import('./checkout-smoke.mjs');
const summary=JSON.parse(await fs.readFile(new URL('../evidence/checkout-summary.json',import.meta.url),'utf8')),cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});return r.headers.get('set-cookie').split(';')[0]}
const packer=await login('packer'),owner=await login('owner');async function call(url,body,cookie=packer,method='PATCH'){const r=await fetch('http://127.0.0.1:3200/api'+url,{method:body?method:'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const start=(await call('/bootstrap')).data.tasks.find(t=>t.id===summary.task_id),snapshot=JSON.stringify(start.snapshot),url='/tasks/'+start.id;
assert.equal((await call(url,{assignee:'Internal test packer'})).status,200);assert.equal((await call(url,{state:'preparing'})).status,200);
assert.equal((await call(url,{exception:'Internal shortage check: promised item not yet packed'})).status,200);assert.equal((await call(url,{state:'ready',confirmed:true,actual_contents:packSheet(start.snapshot)})).status,409);
assert.equal((await call(url+'/resolve',{reason:'Original promised Hass avocados verified in allocated online bin'},packer,'POST')).status,200);
assert.equal((await call(url,{state:'ready'})).status,409);assert.equal((await call(url,{state:'collected'})).status,409);
assert.equal((await call(url,{state:'picked'})).status,200);assert.equal((await call(url,{state:'picked'})).status,200);
assert.equal((await call(url,{state:'packed'})).status,422);const incorrect=packSheet(start.snapshot).map(i=>({...i,quantity:i.quantity-1}));assert.equal((await call(url,{state:'packed',confirmed:true,actual_contents:incorrect})).status,422);
assert.equal((await call(url,{state:'packed',confirmed:true,actual_contents:packSheet(start.snapshot)})).status,200);assert.equal((await call(url,{state:'packed'})).status,200);
const db=new Pool({connectionString:`postgres://avoshack:${cfg.databasePassword}@127.0.0.1:55432/avoshack`});
async function clear(){await db.query('DROP TRIGGER IF EXISTS test_fulfillment_ack_failure ON avo.audit');await db.query('DROP FUNCTION IF EXISTS avo.test_fulfillment_ack_failure()')}
async function native(){return (await db.query('SELECT f.id,f.delivered_at FROM fulfillment f JOIN order_fulfillment ofl ON ofl.fulfillment_id=f.id WHERE ofl.order_id=$1 AND f.canceled_at IS NULL',[start.order_id])).rows}
try{for(const [state,before] of [['ready','packed'],['collected','ready']]){
await db.query(`CREATE FUNCTION avo.test_fulfillment_ack_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='packing_update' AND NEW.subject='${start.id}' AND NEW.after_data->>'state'='${state}' THEN RAISE EXCEPTION 'Internal fulfillment acknowledgment fault'; END IF; RETURN NEW; END $$`);
await db.query('CREATE TRIGGER test_fulfillment_ack_failure BEFORE INSERT ON avo.audit FOR EACH ROW EXECUTE FUNCTION avo.test_fulfillment_ack_failure()');
assert.equal((await call(url,{state})).status,500);assert.equal((await db.query('SELECT state FROM avo.tasks WHERE id=$1',[start.id])).rows[0].state,before);
const persisted=await native();assert.equal(persisted.length,1);if(state==='collected')assert.ok(persisted[0].delivered_at);
await clear();assert.equal((await call(url,{state})).status,200);assert.deepEqual(await native(),persisted);assert.equal((await call(url,{state})).status,200);
assert.equal((await db.query("SELECT count(*)::int AS count FROM avo.audit WHERE subject=$1 AND action='packing_update' AND after_data->>'state'=$2",[start.id,state])).rows[0].count,1);
}console.log('Native ready/collection survived lost acknowledgment; retries preserve one fulfillment and delivery timestamp, with one committed audit per stage.');}finally{await clear();await db.end()}
const after=(await call('/bootstrap')).data.tasks.find(t=>t.id===start.id);assert.equal(JSON.stringify(after.snapshot),snapshot);assert.deepEqual(after.actual_contents,packSheet(start.snapshot));assert.equal(after.assignee,'Internal test packer');assert.equal(after.state,'collected');
console.log('Assignment, shortage block, resolution, skipped-step rejection, picked/packed records, explicit actual-contents validation, state replay and collection passed. Accepted snapshot unchanged.');
assert.equal((await call(url+'/refund',{reason:'Internal completed-order test refund'},owner,'POST')).status,200);const boot=(await call('/bootstrap',undefined,owner)).data,p=boot.products.find(p=>p.title==='Hass avocado');assert.equal((await call('/stock-movements',{product_id:p.id,action:'recount',quantity:12,reason:'Restore confirmed allocation after packing test',event_id:crypto.randomUUID()},owner,'POST')).status,200);console.log('Test order refunded in simulator; online allocation restored to owner-confirmed 12.');

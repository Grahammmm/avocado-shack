import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {Pool} from 'pg';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8')),db=new Pool({connectionString:`postgres://avoshack:${cfg.databasePassword}@127.0.0.1:55432/avoshack`});
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');
async function call(path,body,cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+path,{method:body?'POST':'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const boot=(await call('/bootstrap')).data,p=boot.products.find(p=>p.title==='Hass avocado');assert.ok(p&&boot.slots[0]);
const s=(await db.query("SELECT value FROM avo.settings WHERE key='engine'")).rows[0].value;
async function stock(){const r=await fetch('http://127.0.0.1:9000/internal/stock',{method:'POST',headers:{'Content-Type':'application/json','x-avo-internal':cfg.jwtSecret},body:JSON.stringify({inventory_ids:[p.variants[0].inventory_items[0].inventory_item_id],location_id:s.location_id})});assert.equal(r.status,200);return (await r.json()).levels[0]}
const balance=await stock(),quantity=Number(balance.stocked_quantity);
const baseline={product_id:p.id,action:'recount',quantity,reason:'Internal correction-link test: preserve current count',event_id:crypto.randomUUID()};
const original=await call('/stock-movements',baseline);assert.equal(original.status,200);
const correction={product_id:p.id,action:'correction',quantity,reason:'Internal correction-link test: verify history without changing count',event_id:crypto.randomUUID(),corrects_movement_id:original.data.movement.id};
assert.equal((await call('/stock-movements',{...correction,corrects_movement_id:null})).status,422);
assert.equal((await call('/stock-movements',{...correction,corrects_movement_id:crypto.randomUUID()})).status,422);
assert.equal((await call('/stock-movements',correction,packer)).status,403);
const applied=await call('/stock-movements',correction);assert.equal(applied.status,200);assert.equal(applied.data.movement.corrects_movement_id,original.data.movement.id);
assert.equal((await call('/stock-movements',correction)).status,200);
assert.equal((await call('/stock-movements',{...correction,corrects_movement_id:null})).status,409);
assert.equal((await call('/stock-movements',{...baseline,event_id:crypto.randomUUID(),corrects_movement_id:original.data.movement.id})).status,422);
const history=await call('/stock-movements');assert.ok(history.data.movements.some(m=>m.id===applied.data.movement.id&&m.corrects_movement_id===original.data.movement.id));
assert.equal(Number((await stock()).stocked_quantity),quantity);
assert.equal((await db.query("SELECT count(*)::int AS n FROM avo.audit WHERE event_id=$1",['movement_'+applied.data.movement.id])).rows[0].n,1);
console.log('Correction requires an applied same-product movement; missing/unknown links rejected. Packer denied. Link is persisted and visible in history. Replay does not duplicate audit; changed link rejected. Non-correction link rejected. Stock count unchanged.');await db.end();

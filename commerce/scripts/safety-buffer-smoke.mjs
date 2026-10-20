import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {Pool} from 'pg';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8')),db=new Pool({connectionString:`postgres://avoshack:${cfg.databasePassword}@127.0.0.1:55432/avoshack`});
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');
async function call(path,body,cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+path,{method:body?'POST':'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const boot=(await call('/bootstrap')).data,p=boot.products.find(p=>p.title==='Hass avocado');assert.ok(p&&boot.slots[0]);
const s=(await db.query("SELECT value FROM avo.settings WHERE key='engine'")).rows[0].value;
async function stock(){const r=await fetch('http://127.0.0.1:9000/internal/stock',{method:'POST',headers:{'Content-Type':'application/json','x-avo-internal':cfg.jwtSecret},body:JSON.stringify({inventory_ids:[p.variants[0].inventory_items[0].inventory_item_id],location_id:s.location_id})});assert.equal(r.status,200);return (await r.json()).levels[0]}
let current=(await call('/safety-buffers')).data.buffers.find(b=>b.product_id===p.id);const original=current.units,balance=await stock();const free=Number(balance.stocked_quantity)-Number(balance.reserved_quantity);assert.ok(free>=2);const attempts=[];
async function save(units,cookie=owner,version=current.version){const r=await fetch('http://127.0.0.1:3200/api/safety-buffers/'+p.id,{method:'PATCH',headers:{cookie,'Content-Type':'application/json'},body:JSON.stringify({units,version,reason:'Internal safety-buffer verification; no physical stock change'})});const out={status:r.status,data:await r.json()};if(r.ok)current=out.data.buffer;return out;}
try{
 assert.equal((await save(1,packer)).status,403);assert.equal((await save(-1)).status,422);assert.equal((await save(free-1)).status,200);assert.equal((await save(0,owner,current.version-1)).status,409);
 const body={nonce:crypto.randomUUID(),items:[{product_id:p.id,quantity:1}],email:'internal-buffer@example.invalid',slot_id:boot.slots[0].id};
 const bodies=[body,{...body,nonce:crypto.randomUUID()}];const winners=await Promise.all(bodies.map(b=>call('/checkout',b,visitor)));assert.equal(winners.filter(r=>r.status===200).length,1);assert.equal(winners.filter(r=>r.status===409).length,1);const accepted=winners.find(r=>r.status===200);attempts.push(accepted.data.attempt_id);
 const acceptedBody=bodies[winners.findIndex(r=>r.status===200)];
 assert.equal((await call('/checkout',acceptedBody,visitor)).data.attempt_id,accepted.data.attempt_id);
 assert.equal(Number((await stock()).stocked_quantity),Number(balance.stocked_quantity));
 console.log('Owner versioned safety buffer passes; packer, negative and stale writes denied. Two competing one-unit baskets have one winner with one available unit. Physical stock unchanged.');
}finally{for(const id of attempts)await call('/checkout/'+id+'/cancel',{},visitor);await save(original);assert.equal(Number((await stock()).stocked_quantity),Number(balance.stocked_quantity));await db.end();}
console.log('All test checkouts canceled and original safety buffer restored.');

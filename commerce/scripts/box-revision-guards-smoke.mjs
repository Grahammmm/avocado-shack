import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {Pool} from 'pg';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8')),db=new Pool({connectionString:`postgres://avoshack:${cfg.databasePassword}@127.0.0.1:55432/avoshack`});
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');async function call(url,body,cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+url,{method:body?'POST':'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const before=(await call('/bootstrap')).data;const source=before.boxes.find(b=>b.state==='draft');assert.ok(source,'A prior private box proposal is needed for the guard check.');
const body={version:source.version,event_id:crypto.randomUUID()};
assert.equal((await call('/boxes/'+source.id+'/revise',body,packer)).status,403);
assert.equal((await call('/boxes/'+source.id+'/revise',{...body,event_id:''})).status,422);
assert.equal((await call('/boxes/'+source.id+'/revise',body)).status,409);
assert.equal((await call('/boxes/'+crypto.randomUUID()+'/revise',body)).status,409);
const after=(await call('/bootstrap')).data;assert.deepEqual(after.boxes,before.boxes);assert.equal(after.products.filter(p=>p.metadata.kind==='box').length,0);
await db.end();console.log('Revision endpoint rejects packer access, missing event reference, unpublished source and nonexistent source. No offer or catalog change. Actual published-box revision remains gated on owner recipe/cost inputs.');

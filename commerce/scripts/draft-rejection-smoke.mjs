import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {Pool} from 'pg';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8')),db=new Pool({connectionString:`postgres://avoshack:${cfg.databasePassword}@127.0.0.1:55432/avoshack`});
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');async function call(url,body,cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+url,{method:body?'POST':'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const created=await call('/drafts',{event_id:crypto.randomUUID(),message:'Hass avocado, each, $2, 12 available for online pickup.'});assert.equal(created.status,200);const d=created.data.draft;
const reject={version:d.version,reason:'Internal rejection test: do not publish this duplicate update'};
assert.equal((await call('/drafts/'+d.id+'/reject',reject,packer)).status,403);
assert.equal((await call('/drafts/'+d.id+'/reject',{...reject,version:d.version+1})).status,409);
const result=await call('/drafts/'+d.id+'/reject',reject);assert.equal(result.status,200);assert.equal(result.data.draft.state,'rejected');assert.equal(result.data.draft.evidence_id,d.evidence_id);
assert.equal((await call('/drafts/'+d.id+'/reject',reject)).status,200);
assert.equal((await call('/drafts/'+d.id+'/reject',{...reject,reason:'Different rejection'})).status,409);
assert.equal((await call('/drafts/'+d.id+'/approve',{version:d.version})).status,409);
const edit=await fetch('http://127.0.0.1:3200/api/drafts/'+d.id,{method:'PATCH',headers:{cookie:owner,'Content-Type':'application/json'},body:JSON.stringify({version:d.version,fields:d.fields})});assert.equal(edit.status,409);
assert.equal((await db.query("SELECT count(*)::int AS n FROM avo.audit WHERE subject=$1 AND action='reject_product'",[d.id])).rows[0].n,1);
assert.equal((await db.query('SELECT product_id FROM avo.drafts WHERE id=$1',[d.id])).rows[0].product_id,null);
await db.end();console.log('Owner exact-version rejection retains evidence and publishes nothing. Packer/stale rejection denied, identical replay safe, changed reason conflicts, approval/edit cannot revive rejected draft, one audit record.');

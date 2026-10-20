import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');
async function call(path,body,method='POST',cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+path,{method:body?method:'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
assert.equal((await fetch('http://127.0.0.1:3200/api/activity')).status,401);
assert.equal((await call('/activity',undefined,'GET',visitor)).status,403);assert.equal((await call('/activity',undefined,'GET',packer)).status,403);
const result=await call('/activity');assert.equal(result.status,200);assert.ok(result.data.events.length>0&&result.data.events.length<=30);
let last=Infinity;for(const event of result.data.events){assert.ok(event.id&&event.actor&&event.action);const time=new Date(event.created_at).getTime();assert.ok(time<=last);last=time;assert.ok(event.subject_name==null||typeof event.subject_name==='string');assert.equal(event.databasePassword,undefined);assert.equal(event.jwtSecret,undefined);}
console.log('Owner activity endpoint returns bounded newest-first persisted records. Unauthenticated access, visitor and packer denied. Read-only verification; no store changes.');

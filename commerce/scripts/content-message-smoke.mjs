import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');
async function call(path,body,method='POST',cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+path,{method:body?method:'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const initial=(await call('/bootstrap')).data.content;const first={message:'Change the welcome to: Internal private copy test.',event_id:crypto.randomUUID()};
try{
 const one=await call('/drafts',first);assert.equal(one.status,200);assert.equal(one.data.content.draft.welcome,'Internal private copy test.');
 const two=await call('/drafts',{message:'Website heading: Internal heading test',event_id:crypto.randomUUID()});assert.equal(two.status,200);assert.equal(two.data.content.draft.welcome,'Internal private copy test.');assert.equal(two.data.content.draft.note_heading,'Internal heading test');
 assert.equal((await call('/drafts',first)).data.content.version,two.data.content.version);
 const customer=(await call('/bootstrap',undefined,'GET',visitor)).data.content;assert.deepEqual(customer.published,initial.published);assert.equal(customer.draft,undefined);
 assert.equal((await call('/content/approve',{version:one.data.content.version})).status,409);
 assert.equal((await call('/drafts',{message:'Website note: Internal',event_id:crypto.randomUUID()},'POST',packer)).status,403);
 console.log('Two owner text destinations accumulate in one private copy draft. Event replay does not add a version. Customer copy unchanged; stale approval and packer input denied.');
}finally{
 const current=(await call('/bootstrap')).data.content;const restored=await call('/content',{version:current.version,copy:initial.draft||initial.published},'PATCH');assert.equal(restored.status,200);
 if(!initial.draft){const saved=(await call('/bootstrap')).data.content;assert.equal((await call('/content/approve',{version:saved.version})).status,200);}
 console.log('Original published copy and any prior private draft restored; internal test copy was never published.');
}

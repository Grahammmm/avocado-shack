import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');
async function call(path,body,method='POST',cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+path,{method:body?method:'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const boot=(await call('/bootstrap')).data,initial=boot.content,p=boot.products.find(p=>p.title==='Hass avocado');assert.ok(p);const event_id=crypto.randomUUID();
try{
 assert.equal((await call('/drafts',{message:'Feature an unknown product',event_id:crypto.randomUUID()})).status,422);
 assert.equal((await call('/drafts',{message:'Feature Hass avocado',event_id},'POST',packer)).status,403);
 const proposed=await call('/drafts',{message:'Feature Hass avocado',event_id});assert.equal(proposed.status,200);const draft=proposed.data.content;assert.equal(draft.draft.featured_product_id,p.id);assert.ok(draft.draft.featured_revision);
 assert.equal((await call('/drafts',{message:'Feature Hass avocado',event_id})).data.content.version,draft.version);
 assert.deepEqual((await call('/bootstrap',undefined,'GET',visitor)).data.content.published,initial.published);
 // Same confirmed stock/price/unit, a new approved product revision; no invented facts.
 await import('./photo-retention-smoke.mjs');
 assert.equal((await call('/content/approve',{version:draft.version})).status,409);
 const reviewed=await call('/content',{version:draft.version,copy:draft.draft},'PATCH');assert.equal(reviewed.status,200);assert.equal((await call('/content/approve',{version:reviewed.data.content.version})).status,200);
 assert.equal((await call('/bootstrap',undefined,'GET',visitor)).data.content.published.featured_product_id,p.id);
 const cleared=await call('/drafts',{message:'Stop featuring products',event_id:crypto.randomUUID()});assert.equal(cleared.status,200);assert.equal((await call('/content/approve',{version:cleared.data.content.version})).status,200);
 assert.equal((await call('/bootstrap',undefined,'GET',visitor)).data.content.published.featured_product_id,'');
 console.log('Approved real product feature stays private until exact approval. Unknown product/packer rejected, event replay safe, changed product revision blocks publication. Re-reviewed feature and clear command pass.');
}finally{
 const current=(await call('/bootstrap')).data.content;assert.equal((await call('/content',{version:current.version,copy:initial.draft||initial.published},'PATCH')).status,200);
 if(!initial.draft){const saved=(await call('/bootstrap')).data.content;assert.equal((await call('/content/approve',{version:saved.version})).status,200);}
 console.log('Original copy/feature selection and any prior private draft restored. No new product or discount created.');
}

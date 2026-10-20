import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');
async function call(path,body,method='POST',cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+path,{method:body?method:'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const initial=(await call('/bootstrap')).data;assert.ok(!initial.content.draft,'Do not overwrite an owner draft');const published=initial.content.published;
try{
 const proposal=await call('/drafts',{message:'Website note: '+published.note,event_id:'content_test_'+crypto.randomUUID()});assert.equal(proposal.status,200);const version=proposal.data.content.version;
 assert.equal((await call('/content/approve',{version:version-1})).status,409);
 const customer=(await call('/bootstrap',undefined,'GET',visitor)).data;assert.deepEqual(customer.content.published,published);assert.ok(!customer.content.draft);
 assert.equal((await call('/content/approve',{version},'POST',packer)).status,403);
 assert.equal((await call('/content/approve',{version})).status,200);assert.equal((await call('/content/approve',{version})).status,200);console.log('Owner text produced private copy; stale and packer approval rejected; exact approval and replay passed.');
 const slots=(await call('/pickup-slots')).data.slots,s=slots.find(s=>s.active&&new Date(s.cutoff)>new Date());assert.ok(s);const p=initial.products[0];
 const checkout=()=>call('/checkout',{nonce:crypto.randomUUID(),items:[{product_id:p.id,quantity:1}],email:'internal-editorial@example.invalid',slot_id:s.id},'POST',visitor);
 try{
 assert.equal((await call('/ordering',{paused:true},'PATCH')).status,200);assert.equal((await checkout()).status,409);assert.equal((await call('/ordering',{paused:false},'PATCH',packer)).status,403);assert.equal((await call('/ordering',{paused:false},'PATCH')).status,200);
 assert.equal((await call('/pickup-slots/'+s.id,{version:s.version,capacity:s.capacity,cutoff:s.cutoff,active:false},'PATCH')).status,200);
 assert.equal((await checkout()).status,409);assert.equal((await call('/pickup-slots/'+s.id,{version:s.version,capacity:s.capacity,cutoff:s.cutoff,active:true},'PATCH')).status,409);
 console.log('Ordering pause and closed pickup window reject checkout; stale pickup edits and packer settings changes rejected.');
 }finally{await call('/ordering',{paused:false},'PATCH');const current=(await call('/pickup-slots')).data.slots.find(x=>x.id===s.id);assert.equal((await call('/pickup-slots/'+s.id,{version:current.version,capacity:s.capacity,cutoff:s.cutoff,active:s.active},'PATCH')).status,200)}
}finally{const current=(await call('/bootstrap')).data.content;if(current.draft){assert.equal((await call('/content',{version:current.version,copy:published},'PATCH')).status,200);const newer=(await call('/bootstrap')).data.content;assert.equal((await call('/content/approve',{version:newer.version})).status,200)}}
console.log('Original factual copy, pickup settings and open ordering preserved after checks.');

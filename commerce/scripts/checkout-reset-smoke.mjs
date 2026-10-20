import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),customer=await login('visitor'),other=await login('visitor');async function call(url,body,cookie=customer){const r=await fetch('http://127.0.0.1:3200/api'+url,{method:body?'POST':'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const boot=(await call('/bootstrap')).data,p=boot.products.find(p=>p.title==='Hass avocado');
const nonce=crypto.randomUUID(),body={nonce,items:[{product_id:p.id,variant_id:p.variants[0].id,quantity:1}],email:'internal-reset@example.invalid',slot_id:boot.slots[0].id};
const start=await call('/checkout',body);assert.equal(start.status,200);const attempt=start.data.attempt_id;
assert.equal((await call('/checkout',{...body,items:[{...body.items[0],quantity:2}]})).status,409);
assert.equal((await call('/checkout/reset',{nonce},other)).data.state,'not_started');
assert.equal((await call('/orders/'+attempt)).data.state,'pending');
assert.equal((await call('/checkout/reset',{nonce})).data.state,'canceled');
assert.equal((await call('/checkout/reset',{nonce})).data.state,'canceled');
const replacement=await call('/checkout',{...body,nonce:crypto.randomUUID(),items:[{...body.items[0],quantity:2}]});assert.equal(replacement.status,200);
assert.equal((await call('/orders/'+replacement.data.attempt_id)).data.total_minor,400);
assert.equal((await call('/checkout/'+replacement.data.attempt_id+'/cancel',{})).data.state,'canceled');
const ownerBoot=(await call('/bootstrap',undefined,owner)).data,t=ownerBoot.tasks.find(t=>t.state==='refunded');assert.ok(t);
assert.equal((await call('/checkout/'+t.attempt_id+'/cancel',{},owner)).status,409);
console.log('Changed frozen basket rejected. Another session cannot reset it. Reset cancels once and replays safely. New two-unit checkout uses server total $4, then cancels. Paid/refunded order still cannot cancel. No payment or stock recount performed.');

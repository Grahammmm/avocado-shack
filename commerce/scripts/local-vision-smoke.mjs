import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
const login=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:'owner',password:cfg.ownerPassword})});assert.equal(login.status,200);const cookie=login.headers.get('set-cookie').split(';')[0];
async function call(url,body){const r=await fetch('http://127.0.0.1:3200/api'+url,{method:body?'POST':'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const before=(await call('/bootstrap')).data.products,results=[];
for(const photo of ['IMG_9707.jpg','IMG_9708.jpg','IMG_9737.jpg']){
 const event=crypto.randomUUID(),form=new FormData();form.append('event_id',event);form.append('photo',new Blob([await fs.readFile(new URL('../../inventory-intake/previews/'+photo,import.meta.url))],{type:'image/jpeg'}),photo);
 const t=Date.now(),r=await fetch('http://127.0.0.1:3200/api/drafts',{method:'POST',headers:{cookie},body:form});assert.equal(r.status,200);const d=(await r.json()).draft;
 assert.ok(d.fields._photo_review);assert.equal(d.fields.price_minor,undefined);assert.equal(d.fields.quantity,undefined);assert.equal(d.fields.stock_action,undefined);assert.equal(d.fields.stock_pool,undefined);assert.ok(d.questions.length);assert.equal((await call('/drafts/'+d.id+'/approve',{version:d.version})).status,422);
 results.push({photo,draft_id:d.id,elapsed_ms:Date.now()-t,visual:d.fields._photo_review,name:d.fields.name||null,questions:d.questions});
 assert.equal((await call('/drafts/'+d.id+'/reject',{version:d.version,reason:'Private local vision verification; owner has not confirmed a selling offer'})).status,200);console.log(photo,d.fields._photo_review.kind,Date.now()-t+'ms');
 await fs.writeFile(new URL('../evidence/local-vision-live-summary.json',import.meta.url),JSON.stringify({results,catalog_unchanged:true,automatic_identity_is_proposal_only:true},null,2));
}
assert.deepEqual((await call('/bootstrap')).data.products,before);console.log('Real supplied uploads interpreted locally. Unknown price and hidden stock stayed blank, approval blocked, test drafts rejected, public catalog unchanged.');

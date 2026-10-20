import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const config=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:config[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const owner=await login('owner'),packer=await login('packer');
async function call(path,body,cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+path,{method:body?'POST':'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const boot=(await call('/bootstrap')).data;assert.equal(boot.payment_mode,'simulator');const task=boot.tasks.find(t=>t.state==='collected')||boot.tasks.find(t=>t.state==='refunded');assert.ok(task,'A completed simulation order is required');
assert.equal((await call('/tasks/'+task.id+'/refund',{reason:'Internal refund verification'},packer)).status,403);
const first=await call('/tasks/'+task.id+'/refund',{reason:'Internal refund verification'});assert.equal(first.status,200,JSON.stringify(first.data));assert.equal(first.data.simulated,true);
assert.equal((await call('/tasks/'+task.id+'/refund',{reason:'Internal refund verification'})).status,200);
const after=(await call('/bootstrap')).data;assert.equal(after.tasks.find(t=>t.id===task.id).state,'refunded');assert.deepEqual(after.products,boot.products);
console.log('Owner simulated full refund passed through engine provider; replay returned the same refunded state. Packer refund denied. Catalog unchanged; no automatic restock or money movement.');

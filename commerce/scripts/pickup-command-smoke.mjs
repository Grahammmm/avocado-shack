import fs from 'node:fs/promises';import {Pool} from 'pg';import assert from 'node:assert/strict';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
async function login(role){const r=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role,password:cfg[role+'Password']})});assert.equal(r.status,200);return r.headers.get('set-cookie').split(';')[0]}
const db=new Pool({connectionString:`postgres://avoshack:${cfg.databasePassword}@127.0.0.1:55432/avoshack`});
const owner=await login('owner'),visitor=await login('visitor'),packer=await login('packer');
async function call(path,body,method='POST',cookie=owner){const r=await fetch('http://127.0.0.1:3200/api'+path,{method:body?method:'GET',headers:{cookie,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});return {status:r.status,data:await r.json()}}
const boot=(await call('/bootstrap')).data,p=boot.products.find(p=>p.title==='Hass avocado'),windows=(await call('/pickup-slots')).data.slots;const slot=windows.find(s=>s.active&&new Date(s.cutoff)>new Date());assert.ok(slot&&p);const date=new Date(slot.starts_at).toLocaleDateString('en-CA',{timeZone:'America/Los_Angeles'}),original=windows.filter(s=>new Date(s.starts_at).toLocaleDateString('en-CA',{timeZone:'America/Los_Angeles'})===date);let attempt;
try{
 const pending=await call('/checkout',{nonce:crypto.randomUUID(),items:[{product_id:p.id,quantity:1}],email:'internal-closure@example.invalid',slot_id:slot.id},'POST',visitor);assert.equal(pending.status,200);attempt=pending.data.attempt_id;const accepted=(await call('/orders/'+attempt,undefined,'GET',visitor)).data;
 assert.equal((await call('/drafts',{message:'Close pickup tomorrow',event_id:crypto.randomUUID()})).status,422);
 const event_id=crypto.randomUUID(),message='Close pickup on '+date;const proposed=await call('/drafts',{message,event_id});assert.equal(proposed.status,200);const stale=proposed.data.draft;assert.equal((await call('/drafts',{message,event_id})).data.draft.id,stale.id);
 assert.equal((await call('/pickup-proposals/'+stale.id+'/approve',{version:stale.version},'POST',packer)).status,403);
 assert.equal((await call('/pickup-slots/'+slot.id,{version:slot.version,capacity:slot.capacity,cutoff:slot.cutoff,active:slot.active},'PATCH')).status,200);
 assert.equal((await call('/pickup-proposals/'+stale.id+'/approve',{version:stale.version})).status,409);
 const membership=(await call('/drafts',{message,event_id:crypto.randomUUID()})).data.draft;const extra='internal_window_'+crypto.randomUUID();try{await db.query('INSERT INTO avo.slots(id,label,starts_at,ends_at,cutoff,capacity,active) SELECT $1,label,starts_at,ends_at,cutoff,capacity,active FROM avo.slots WHERE id=$2',[extra,slot.id]);assert.equal((await call('/pickup-proposals/'+membership.id+'/approve',{version:membership.version})).status,409);const unchanged=(await call('/pickup-slots')).data.slots.filter(s=>original.some(o=>o.id===s.id));assert.ok(unchanged.every(s=>s.active===original.find(o=>o.id===s.id).active));}finally{await db.query('DELETE FROM avo.slots WHERE id=$1',[extra]);}
 const fresh=(await call('/drafts',{message,event_id:crypto.randomUUID()})).data.draft;
 assert.equal((await call('/pickup-proposals/'+fresh.id+'/approve',{version:fresh.version})).status,200);assert.equal((await call('/pickup-proposals/'+fresh.id+'/approve',{version:fresh.version})).status,200);
 const closed=(await call('/pickup-slots')).data.slots.filter(s=>original.some(o=>o.id===s.id));assert.ok(closed.every(s=>!s.active));
 assert.equal((await call('/checkout',{nonce:crypto.randomUUID(),items:[{product_id:p.id,quantity:1}],email:'internal-closure-new@example.invalid',slot_id:slot.id},'POST',visitor)).status,409);
 assert.deepEqual((await call('/orders/'+attempt,undefined,'GET',visitor)).data,accepted);assert.deepEqual((await call('/bootstrap')).data.tasks.map(t=>t.snapshot),boot.tasks.map(t=>t.snapshot));assert.deepEqual((await call('/bootstrap',undefined,'GET',visitor)).data.pickup_proposals,[]);
 console.log('Text closure captures exact windows, event replay safe, packer denied, stale window version rejected. Approval replay safe; new checkout blocked while existing checkout and accepted task snapshots stay unchanged.');
}finally{
 if(attempt)assert.equal((await call('/checkout/'+attempt+'/cancel',{},'POST',visitor)).status,200);
 const current=(await call('/pickup-slots')).data.slots;for(const originalSlot of original){const s=current.find(s=>s.id===originalSlot.id);if(s.active!==originalSlot.active)assert.equal((await call('/pickup-slots/'+s.id,{version:s.version,capacity:originalSlot.capacity,cutoff:originalSlot.cutoff,active:originalSlot.active},'PATCH')).status,200);}
 await db.end();console.log('Original window availability restored, temporary membership fixture removed, and pending test hold canceled.');
}

import fs from 'node:fs/promises';import assert from 'node:assert/strict';import {Pool} from 'pg';
await import('./checkout-smoke.mjs');
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
const summary=JSON.parse(await fs.readFile(new URL('../evidence/checkout-summary.json',import.meta.url),'utf8'));
const db=new Pool({connectionString:`postgres://avoshack:${cfg.databasePassword}@127.0.0.1:55432/avoshack`});
const login=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:'packer',password:cfg.packerPassword})});assert.equal(login.status,200);const cookie=login.headers.get('set-cookie').split(';')[0];
const before=(await db.query('SELECT state,assignee FROM avo.tasks WHERE id=$1',[summary.task_id])).rows[0];
try{
 // Temporary fault only targets this labeled simulator task in the custom audit schema.
 await db.query(`CREATE OR REPLACE FUNCTION avo.test_packing_audit_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.action='packing_update' AND NEW.subject='${summary.task_id}' THEN RAISE EXCEPTION 'Internal packing audit fault'; END IF; RETURN NEW; END $$`);
 await db.query('CREATE TRIGGER test_packing_audit_failure BEFORE INSERT ON avo.audit FOR EACH ROW EXECUTE FUNCTION avo.test_packing_audit_failure()');
 const r=await fetch('http://127.0.0.1:3200/api/tasks/'+summary.task_id,{method:'PATCH',headers:{cookie,'Content-Type':'application/json'},body:JSON.stringify({assignee:'Must roll back'})});assert.equal(r.status,500);
 const after=(await db.query('SELECT state,assignee FROM avo.tasks WHERE id=$1',[summary.task_id])).rows[0];assert.deepEqual(after,before);
 console.log('Injected audit failure rolls back the staff assignment; packing state and assignee unchanged.');
}finally{
 await db.query('DROP TRIGGER IF EXISTS test_packing_audit_failure ON avo.audit');await db.query('DROP FUNCTION IF EXISTS avo.test_packing_audit_failure()');await db.end();
}
// Same checkout module is cached; this exercises and cleans up that exact simulated order.
await import('./packing-exception-smoke.mjs');
console.log('Fault removed; same order completed through packing, refund and confirmed test-allocation restoration.');

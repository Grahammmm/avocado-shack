import fs from 'node:fs/promises';import assert from 'node:assert/strict';
const cfg=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
const login=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:'packer',password:cfg.packerPassword})});assert.equal(login.status,200);
const r=await fetch('http://127.0.0.1:3200/api/bootstrap',{headers:{cookie:login.headers.get('set-cookie').split(';')[0]}});assert.equal(r.status,200);const {tasks}=await r.json();assert.ok(tasks.length);
let closed=false,lastActive=-Infinity,lastClosed=-Infinity;
for(const task of tasks){const due=new Date(task.due_at).getTime();assert.ok(Number.isFinite(due));if(['collected','refunded'].includes(task.state)){closed=true;assert.ok(due>=lastClosed);lastClosed=due;}else{assert.equal(closed,false);assert.ok(due>=lastActive);lastActive=due;}}
console.log('Authenticated packing data has pickup times, active orders before terminal orders, and ascending due times within each group. Read-only check; no order or stock changes.');

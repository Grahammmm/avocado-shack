import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {prepare} from '../scripts/setup.mjs';
async function fixture(fn){const root=await fs.mkdtemp(path.join(os.tmpdir(),'avo-setup-test-'));try{await fs.mkdir(path.join(root,'backend'));await fn(root);}finally{await fs.rm(root,{recursive:true,force:true});}}
test('fresh setup creates private role access and repeat preserves credentials and environment',()=>fixture(async root=>{
 const first=await prepare(root),file=path.join(root,'.runtime/config.json'),env=path.join(root,'backend/.env');
 assert.equal((await fs.stat(file)).mode&0o777,0o600);assert.equal((await fs.stat(env)).mode&0o777,0o600);
 const original=await fs.readFile(env,'utf8'),again=await prepare(root);assert.deepEqual(again,first);assert.equal(await fs.readFile(env,'utf8'),original);
 const access=await fs.readFile(path.join(root,'.runtime/access.txt'),'utf8');assert.ok(access.includes(first.ownerPassword));assert.ok(!access.includes(first.databasePassword));assert.ok(!access.includes(first.workerSecret));
}));
test('existing database without its original configuration refuses replacement credentials',()=>fixture(async root=>{
 await fs.mkdir(path.join(root,'.runtime/postgres'),{recursive:true});await fs.writeFile(path.join(root,'.runtime/postgres/PG_VERSION'),'18');
 await assert.rejects(prepare(root),/original config/);await assert.rejects(fs.access(path.join(root,'.runtime/config.json')),{code:'ENOENT'});
}));
test('invalid configuration remains intact and cannot generate a usable environment',()=>fixture(async root=>{
 await fs.mkdir(path.join(root,'.runtime'));const file=path.join(root,'.runtime/config.json'),original=JSON.stringify({databasePassword:'short'});await fs.writeFile(file,original);
 await assert.rejects(prepare(root),/incomplete or invalid/);assert.equal(await fs.readFile(file,'utf8'),original);await assert.rejects(fs.access(path.join(root,'backend/.env')),{code:'ENOENT'});
}));

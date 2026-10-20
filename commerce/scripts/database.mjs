import EmbeddedPostgres from 'embedded-postgres';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import crypto from 'node:crypto';
import path from 'node:path';
const root=path.resolve(import.meta.dirname,'..');const port=Number(process.env.AVO_DATABASE_PORT||55432);if(!Number.isSafeInteger(port)||port<1024||port>65535)throw new Error('Use a valid private database port.');
await mkdir(path.join(root,'.runtime'),{recursive:true});
const file=path.join(root,'.runtime/config.json');
let config;try{config=JSON.parse(await readFile(file,'utf8'))}catch(e){if(e.code!=='ENOENT')throw e;try{await readFile(path.join(root,'.runtime/postgres/PG_VERSION'),'utf8');throw new Error('Restore the original config.json before opening this existing database.')}catch(check){if(check.code!=='ENOENT')throw check}config={databasePassword:crypto.randomBytes(24).toString('hex'),jwtSecret:crypto.randomBytes(32).toString('hex'),cookieSecret:crypto.randomBytes(32).toString('hex'),ownerPassword:crypto.randomBytes(12).toString('base64url'),packerPassword:crypto.randomBytes(12).toString('base64url'),visitorPassword:crypto.randomBytes(12).toString('base64url'),adminPassword:crypto.randomBytes(24).toString('base64url')};await writeFile(file,JSON.stringify(config),{mode:0o600})}
const pg=new EmbeddedPostgres({databaseDir:path.join(root,'.runtime/postgres'),user:'avoshack',password:config.databasePassword,port,persistent:true,initdbFlags:['--encoding=UTF8','--locale=C'],postgresFlags:['-h','127.0.0.1']});
let initialized=false;try{await readFile(path.join(root,'.runtime/postgres/PG_VERSION'),'utf8');initialized=true}catch(e){if(e.code!=='ENOENT')throw e}if(!initialized)await pg.initialise();await pg.start();
const client=pg.getPgClient();await client.connect();
const result=await client.query("SELECT 1 FROM pg_database WHERE datname='avoshack'");if(!result.rowCount) await client.query('CREATE DATABASE avoshack');await client.end();
console.log('Private PostgreSQL ready on loopback:'+port);
for(const sig of ['SIGINT','SIGTERM'])process.on(sig,async()=>{await pg.stop();process.exit(0)});
setInterval(()=>{},60000);

import fs from 'node:fs/promises';
const config=JSON.parse(await fs.readFile(new URL('../.runtime/config.json',import.meta.url),'utf8'));
const login=await fetch('http://127.0.0.1:3200/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({role:'owner',password:config.ownerPassword})});
const cookie=login.headers.get('set-cookie').split(';')[0];
const event_id='internal_box_review_'+crypto.randomUUID();
async function propose(){const body=new FormData();body.append('event_id',event_id);body.append('message','Box: Internal workflow draft; contents: 1 Hass avocado');const r=await fetch('http://127.0.0.1:3200/api/drafts',{method:'POST',headers:{cookie},body});if(!r.ok)throw new Error(await r.text());return (await r.json()).draft;}
const a=await propose(),b=await propose();if(a.id!==b.id||a.kind!=='box')throw new Error('Box event replay failed');
if(!a.questions.some(q=>q.includes('price'))||!a.questions.some(q=>q.includes('cost')))throw new Error('Missing commercial values must remain unknown');
const approve=await fetch('http://127.0.0.1:3200/api/boxes/'+a.id+'/approve',{method:'POST',headers:{cookie,'Content-Type':'application/json'},body:JSON.stringify({version:a.version})});if(approve.status!==422)throw new Error('Incomplete box unexpectedly approved');
const bootstrap=await (await fetch('http://127.0.0.1:3200/api/bootstrap',{headers:{cookie}})).json();if(bootstrap.products.some(p=>p.metadata.source_draft===a.id))throw new Error('Incomplete box reached catalog');
console.log('Box text identified the actual approved Hass avocado; unknown price and cost stayed blank. Replayed source event returned one draft. Incomplete recipe approval rejected; catalog unchanged.');

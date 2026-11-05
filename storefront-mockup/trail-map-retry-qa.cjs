// Trail map retry QA: node trail-map-retry-qa.cjs <published-dir>. Loopback static server, synthetic route data,
// every request outside loopback aborted. Output goes to QA_OUT_DIR (outside the repository).
const {out}=require('./qa-env.cjs').qaEnv({preview:false});
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),http=require('http'),path=require('path'),assert=require('assert/strict');
const dir=process.argv[2]&&path.resolve(process.argv[2]);
if(!dir||!fs.existsSync(path.join(dir,'trail-explorer.js'))){console.error('usage: node trail-map-retry-qa.cjs <published-dir>');process.exit(2)}
const types={'.js':'text/javascript; charset=utf-8','.css':'text/css','.webp':'image/webp','.json':'application/json'};
const FIXTURE='<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/trail-explorer.css"><div id="host" data-trail-explorer></div><script src="/trail-explorer.js"></script>';
const server=http.createServer((req,res)=>{
 const u=new URL(req.url,'http://x').pathname,file=path.join(dir,path.normalize(u));
 if(u==='/fixture'){res.setHeader('content-type','text/html');return res.end(FIXTURE)}
 if(!file.startsWith(dir+path.sep)||!fs.existsSync(file)||fs.statSync(file).isDirectory()){res.statusCode=404;return res.end('no')}
 res.setHeader('content-type',types[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
});
// Minimal valid synthetic route (not real geography).
const profile=[0,1,2,3].map(i=>({distanceMeters:i*100,elevationMeters:10+i,lon:-120.8+i*.001,lat:35.2+i*.001}));
const DATA={distanceMeters:300,oneWayMeters:150,gainMeters:30,lossMeters:30,maxElevationMeters:13,bounds3857:[-13448000,4227000,-13447000,4228000],coordinates:profile.map(p=>[p.lon,p.lat]),profile};
const ok=r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(DATA)});
const abort=r=>r.abort('failed'),s503=r=>r.fulfill({status:503,body:'down'}),bad=r=>r.fulfill({status:200,contentType:'application/json',body:'{not json'});
const sel='#host',retry='#host [data-trail-retry]';
async function open(browser,width,steps){
 const page=await browser.newPage({viewport:{width,height:900}}),state={n:0,errors:[],observers:0};
 page.on('pageerror',e=>state.errors.push(e.message));
 await page.addInitScript(()=>{window.__ro=0;const R=window.ResizeObserver;window.ResizeObserver=class extends R{constructor(f){super(f);window.__ro++}}});
 await page.route(u=>!['127.0.0.1','localhost'].includes(new URL(u).hostname),abort);
 await page.route('**/assets/trails/point-buchon.json',r=>{const step=steps[state.n++];if(!step){state.errors.push('unexpected request');return r.abort('failed')}return step(r)});
 await page.goto(base+"/fixture");kickRaw(page);
 return {page,state};
}
const kickRaw=page=>{page.evaluate(()=>{window.AvoshackTrailExplorer.mount(document.getElementById("host"))})};
const mount=page=>page.evaluate(()=>window.AvoshackTrailExplorer.mount(document.getElementById('host')));
const kick=page=>page.evaluate(()=>{window.AvoshackTrailExplorer.mount(document.getElementById('host'));});
async function expectFallback(page,buttons=1){
 assert.equal(await page.locator(sel+' .trail-map-unavailable').count(),1);
 assert.equal(await page.locator(sel+' .trail-map-unavailable').innerText(),'The interactive map couldn’t load. View the official trail guide ↗');
 const a=page.locator(sel+' a');assert.equal(await a.getAttribute('href'),'https://www.pge.com/en/about/in-your-community/recreational-areas.html');
 assert.equal(await a.getAttribute('target'),'_blank');assert.equal(await a.getAttribute('rel'),'noopener');
 assert.equal(await page.locator(retry).count(),buttons);assert.equal(await page.locator(sel+' .trail-explorer').count(),0);
 if(buttons){const b=page.locator(retry);assert.equal(await b.innerText(),'Try loading the map again');assert.equal(await b.getAttribute('type'),'button');assert.ok(await b.isVisible()&&await b.isEnabled());assert.equal(await page.locator(sel).getAttribute('data-ready'),'error')}
}
async function expectHealthy(page,state){
 await page.locator(sel+'[data-ready=true]').waitFor();
 assert.equal(await page.locator(sel+' .trail-explorer').count(),1);assert.equal(await page.locator(retry).count(),0);assert.equal(await page.locator(sel+' .trail-map-unavailable').count(),0);
 assert.equal(await page.locator('#trail-explorer-heading').innerText(),'Follow the coastline.');
 assert.equal(await page.locator('[aria-label="Interactive Point Buchon route map"]').count(),1);
 await page.locator('.trail-distance').fill('2');assert.match(await page.locator('#trail-elevation-readout').innerText(),/ft$/);
 await page.getByRole('button',{name:'Topo',exact:true}).click();assert.equal(await page.locator('.trail-map-stage').getAttribute('data-layer'),'topo');
 assert.equal(await page.evaluate(()=>window.__ro),1);assert.deepEqual(state.errors,[]);
}
const cases={
 async rejected_fetch_can_retry_on_same_host(b,w){
  const {page,state}=await open(b,w,[abort,ok]);await page.locator(retry).waitFor();await expectFallback(page);
  await page.locator(retry).focus();await page.keyboard.press('Enter');await expectHealthy(page,state);assert.equal(state.n,2);await page.close();
 },
 async non_ok_and_invalid_json_can_retry(b,w){
  const {page,state}=await open(b,w,[s503,bad,s503,ok]);await page.locator(retry).waitFor();await expectFallback(page);
  await page.locator(retry).click();await page.locator(retry).waitFor();await expectFallback(page);assert.equal(state.n,2);
  await page.locator(retry).click();await page.locator(retry).waitFor();await expectFallback(page);assert.equal(state.n,3);
  await page.locator(retry).click();await expectHealthy(page,state);assert.equal(state.n,4);await page.close();
 },
 async rapid_retry_clicks_are_single_flight(b,w){
  let release;const gate=new Promise(r=>release=r);
  const {page,state}=await open(b,w,[abort,async r=>{await gate;return ok(r)}]);await page.locator(retry).waitFor();
  await page.locator(retry).click();assert.equal(await page.locator(retry).count(),0);assert.equal(await page.locator(sel).innerText(),'Loading the trail map…');
  await kick(page);await kick(page);await page.waitForTimeout(100);assert.equal(state.n,2);
  release();await expectHealthy(page,state);assert.equal(state.n,2);await kick(page);await page.waitForTimeout(100);assert.equal(state.n,2);assert.equal(await page.locator(sel+' .trail-explorer').count(),1);await page.close();
 },
 async healthy_and_recovered_mounts_stay_idempotent(b,w){
  const {page,state}=await open(b,w,[ok]);await mount(page);await expectHealthy(page,state);await kick(page);await mount(page);
  assert.equal(state.n,1);assert.equal(await page.locator(sel+' .trail-explorer').count(),1);assert.equal(await page.evaluate(()=>window.__ro),1);await page.close();
 },
 async detached_attempt_does_not_install_ui(b,w){
  for(const late of [ok,abort]){
   let release;const gate=new Promise(r=>release=r);
   const {page,state}=await open(b,w,[async r=>{await gate;return late(r)},ok]);await kick(page);
   await page.evaluate(()=>{window.__h=document.getElementById('host');window.__h.remove()});release();await page.waitForTimeout(300);
   assert.equal(await page.evaluate(()=>window.__h.innerHTML),'');assert.equal(await page.evaluate(()=>window.__ro),0);
   await page.evaluate(()=>document.body.append(window.__h));await mount(page);await expectHealthy(page,state);assert.equal(state.n,2);await page.close();
  }
  const {page,state}=await open(b,w,[abort]);await page.locator(retry).waitFor();
  await page.evaluate(()=>{window.__b=document.querySelector('#host [data-trail-retry]');document.getElementById('host').remove();window.__b.click()});
  await page.waitForTimeout(200);assert.equal(state.n,1);assert.deepEqual(state.errors,[]);await page.close();
 },
};
let base;
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined}),results=[];
 try{for(const w of [390,1440])for(const [name,fn] of Object.entries(cases)){await fn(browser,w);results.push(name+'@'+w)}}
 finally{await browser.close();server.close()}
 fs.writeFileSync(out+'/trail-map-retry-QA.json',JSON.stringify({checkedAt:new Date().toISOString(),results},null,2));console.log('Trail map retry passed ('+results.length+' checks)');
})().catch(e=>{console.error(e);process.exit(1)});

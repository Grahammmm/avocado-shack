// Trail map retry QA: node trail-map-retry-qa.cjs <published-dir>. Loopback static server, synthetic route data,
// every request outside loopback aborted. Output goes to QA_OUT_DIR (outside the repository).
const {out}=require('./qa-env.cjs').qaEnv({preview:false});
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),http=require('http'),path=require('path'),assert=require('assert/strict');
const dir=process.argv[2]&&path.resolve(process.argv[2]);
if(!dir||!fs.existsSync(path.join(dir,'trail-explorer.js'))){console.error('usage: node trail-map-retry-qa.cjs <published-dir>');process.exit(2)}
const {createTrailFixtureHandler}=require('./trail-map-fixture-server.cjs');
const FIXTURE='<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/trail-explorer.css"><div id="host" data-trail-explorer></div><script src="/trail-explorer.js"></script>';
// Serves /fixture from memory and only regular files that resolve inside dir (RF1345-13).
const server=http.createServer(createTrailFixtureHandler(dir,FIXTURE));
// Minimal valid synthetic route (not real geography).
const profile=[0,1,2,3].map(i=>({distanceMeters:i*100,elevationMeters:10+i,lon:-120.8+i*.001,lat:35.2+i*.001}));
const DATA={distanceMeters:300,oneWayMeters:150,gainMeters:30,lossMeters:30,maxElevationMeters:13,bounds3857:[-13448000,4227000,-13447000,4228000],coordinates:profile.map(p=>[p.lon,p.lat]),profile};
const ok=r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(DATA)});
const abort=r=>r.abort('failed'),s503=r=>r.fulfill({status:503,body:'down'}),bad=r=>r.fulfill({status:200,contentType:'application/json',body:'{not json'});
const sel='#host',retry='#host [data-trail-retry]';
const TOPO=path.join(dir,'assets/trails/point-buchon-topo.webp');
// Image fixtures: state.topo.mode / state.aerial.mode = ok | 404 | decode (HTTP 200, not an image) | abort | hold (wait for state.gate, then 404).
async function image(state,which,r){
 const s=state[which];s.hits++;
 if(s.mode==='hold'){await state.gate;return r.fulfill({status:404,body:'gone'})}
 if(s.mode==='404')return r.fulfill({status:404,body:'gone'});
 if(s.mode==='decode')return r.fulfill({status:200,contentType:'image/webp',body:'this is not an image'});
 if(s.mode==='abort')return r.abort('failed');
 return which==='topo'?r.fulfill({status:200,contentType:'image/webp',body:fs.readFileSync(TOPO)}):r.continue();
}
async function open(browser,width,steps,opts={}){
 const page=await browser.newPage({viewport:{width,height:900}}),state={n:0,errors:[],observers:0,topo:{mode:'ok',hits:0},aerial:{mode:opts.aerial||'ok',hits:0}};
 state.gate=new Promise(r=>state.release=r);
 page.on('pageerror',e=>state.errors.push(e.message));
 await page.addInitScript(()=>{window.__ro=0;const R=window.ResizeObserver;window.ResizeObserver=class extends R{constructor(f){super(f);window.__ro++}}});
 await page.route(u=>!['127.0.0.1','localhost'].includes(new URL(u).hostname),abort);
 await page.route('**/assets/trails/point-buchon-topo.webp',r=>image(state,'topo',r));
 await page.route('**/assets/trails/point-buchon-aerial.webp',r=>image(state,'aerial',r));
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
// Real image error event: arm on the mounted basemap before the layer click, then wait for the browser's own event.
const armError=page=>page.evaluate(()=>{const img=document.querySelector('.trail-basemap');window.__img=img;window.__imgErr=new Promise(r=>img.addEventListener('error',()=>r(true),{once:true}))});
const imageError=page=>page.evaluate(()=>Promise.race([window.__imgErr,new Promise((_,j)=>setTimeout(()=>j(Error('no image error event')),5000))]));
const topoClick=async page=>{await armError(page);await page.getByRole('button',{name:'Topo',exact:true}).click();await imageError(page)};
const mounted=page=>page.locator(sel).getAttribute('data-mounted');
async function mountedAerial(b,w,steps,opts){const o=await open(b,w,steps,opts);await o.page.locator(sel+'[data-ready=true]').waitFor();return o}
async function expectHealthy(page,state,ro=1){
 await page.locator(sel+'[data-ready=true]').waitFor();
 assert.equal(await page.locator(sel+' .trail-explorer').count(),1);assert.equal(await page.locator(retry).count(),0);assert.equal(await page.locator(sel+' .trail-map-unavailable').count(),0);
 assert.equal(await page.locator('#trail-explorer-heading').innerText(),'Follow the coastline.');
 assert.equal(await page.locator('[aria-label="Interactive Point Buchon route map"]').count(),1);
 await page.locator('.trail-distance').fill('2');assert.match(await page.locator('#trail-elevation-readout').innerText(),/ft$/);
 await page.getByRole('button',{name:'Topo',exact:true}).click();assert.equal(await page.locator('.trail-map-stage').getAttribute('data-layer'),'topo');
 assert.equal(await page.evaluate(()=>window.__ro),ro);assert.deepEqual(state.errors,[]);
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
 async topo_404_recovers_in_page(b,w){
  const {page,state}=await mountedAerial(b,w,[ok,ok]);
  assert.equal(await page.locator(sel+' .trail-map-unavailable').count(),0);
  state.topo.mode='404';await topoClick(page);
  await expectFallback(page);assert.equal(await mounted(page),null);assert.equal(state.n,1);
  state.topo.mode='ok';await page.locator(retry).click();
  assert.equal(await page.locator('.trail-map-stage').getAttribute('data-layer'),'aerial');
  await expectHealthy(page,state,2);assert.equal(state.n,2);assert.equal(await mounted(page),'true');await page.close();
 },
 async topo_404_while_enlarged_releases_dialog(b,w){
  const {page,state}=await mountedAerial(b,w,[ok,ok]);
  await page.evaluate(()=>{document.body.style.overflow='scroll'});
  await page.locator('[data-map-action="expand"]').click();
  assert.equal(await page.locator('dialog.trail-map-dialog[open]').count(),1);assert.equal(await page.evaluate(()=>document.body.style.overflow),'hidden');
  state.topo.mode='404';await topoClick(page);
  await expectFallback(page);
  assert.equal(await page.locator('dialog').count(),0);assert.equal(await page.locator('.trail-map-dialog').count(),0);
  assert.equal(await page.evaluate(()=>document.body.style.overflow),'scroll');assert.equal(await mounted(page),null);
  state.topo.mode='ok';await page.locator(retry).click();await expectHealthy(page,state,2);
  await page.locator('[data-map-action="expand"]').click();assert.equal(await page.locator('dialog.trail-map-dialog[open]').count(),1);
  await page.keyboard.press('Escape');await page.locator('dialog').waitFor({state:'detached'});assert.equal(await page.evaluate(()=>document.body.style.overflow),'scroll');
  assert.equal(await page.locator(sel+' .trail-explorer').count(),1);assert.deepEqual(state.errors,[]);await page.close();
 },
 async topo_decode_and_transport_failures_recover(b,w){
  for(const mode of ['decode','abort']){
   const {page,state}=await mountedAerial(b,w,[ok,ok]);
   state.topo.mode=mode;await topoClick(page);await expectFallback(page);assert.equal(await mounted(page),null);
   state.topo.mode='ok';await page.locator(retry).click();await expectHealthy(page,state,2);assert.equal(state.n,2);await page.close();
  }
 },
 async image_failure_detached_or_replaced_wrapper_is_ignored(b,w){
  for(const how of ['detached','replaced']){
   const {page,state}=await mountedAerial(b,w,[ok,ok]);
   await page.evaluate(()=>{document.body.style.overflow='scroll'});
   state.topo.mode='hold';await armError(page);await page.getByRole('button',{name:'Topo',exact:true}).click();
   await page.evaluate(h=>{window.__h=document.getElementById('host');window.__w=window.__h.firstElementChild;if(h==='detached')window.__h.remove();else{const x=document.createElement('p');x.id='other';window.__h.replaceChildren(x)}},how);
   state.release();await page.waitForTimeout(300);
   await page.evaluate(()=>window.__img.dispatchEvent(new Event('error')));await page.waitForTimeout(100);
   const seen=await page.evaluate(()=>({retry:window.__h.querySelectorAll('[data-trail-retry]').length,unavailable:window.__h.querySelectorAll('.trail-map-unavailable').length,ready:window.__h.dataset.ready,mounted:window.__h.dataset.mounted,overflow:document.body.style.overflow,dialogs:document.querySelectorAll('dialog').length,first:window.__h.firstElementChild&&window.__h.firstElementChild.id,wrapperKept:window.__h.firstElementChild===window.__w}));
   assert.equal(seen.retry,0);assert.equal(seen.unavailable,0);assert.equal(seen.ready,'true');assert.equal(seen.mounted,'true');assert.equal(seen.overflow,'scroll');assert.equal(seen.dialogs,0);
   assert.equal(seen.wrapperKept,how==='detached');if(how==='replaced')assert.equal(seen.first,'other');
   assert.equal(state.n,1);assert.deepEqual(state.errors,[]);await page.close();
  }
 },
 async supported_layers_and_retries_remain_single_flight(b,w){
  // Healthy Aerial -> Topo -> Aerial never falls back.
  const a=await mountedAerial(b,w,[ok]);
  await a.page.getByRole('button',{name:'Topo',exact:true}).click();await a.page.waitForTimeout(300);
  await a.page.getByRole('button',{name:'Aerial',exact:true}).click();await a.page.waitForTimeout(300);
  assert.equal(await a.page.locator('.trail-map-stage').getAttribute('data-layer'),'aerial');
  assert.equal(await a.page.locator(sel+' .trail-explorer').count(),1);assert.equal(await a.page.locator(retry).count(),0);assert.equal(a.state.topo.hits,1);
  assert.equal(await a.page.evaluate(()=>window.__ro),1);assert.deepEqual(a.state.errors,[]);
  // A successful enlarged map still closes through Escape and restores overflow.
  await a.page.locator('[data-map-action="expand"]').click();assert.equal(await a.page.locator('dialog[open]').count(),1);
  await a.page.keyboard.press('Escape');await a.page.locator('dialog').waitFor({state:'detached'});assert.equal(await a.page.evaluate(()=>document.body.style.overflow),'');
  assert.equal(await a.page.locator(sel+' .trail-explorer').count(),1);await a.page.close();
  // Aerial failures still recover.
  const f=await open(b,w,[ok,ok],{aerial:'404'});await f.page.locator(retry).waitFor();await expectFallback(f.page);
  f.state.aerial.mode='ok';await f.page.locator(retry).click();await expectHealthy(f.page,f.state,2);await f.page.close();
  // After a Topo failure rapid retry clicks make one request, one mount and one observer; recovered controls work.
  const {page,state}=await mountedAerial(b,w,[ok,async r=>{await state.gate;return ok(r)}]);
  state.topo.mode='404';await topoClick(page);await expectFallback(page);state.topo.mode='ok';
  await page.locator(retry).click();assert.equal(await page.locator(retry).count(),0);assert.equal(await page.locator(sel).innerText(),'Loading the trail map…');
  await kick(page);await kick(page);await page.waitForTimeout(100);assert.equal(state.n,2);
  state.release();await expectHealthy(page,state,2);assert.equal(state.n,2);await kick(page);await page.waitForTimeout(100);assert.equal(state.n,2);
  await page.locator('[data-map-action="in"]').click();assert.equal(await page.locator('.trail-map-stage').getAttribute('data-zoom'),'1.60');
  assert.equal(await page.locator(sel+' .trail-explorer').count(),1);assert.equal(await page.evaluate(()=>window.__ro),2);await page.close();
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

// Trail map observer-lifetime QA: node trail-observer-qa.cjs <published-dir>. Loopback static server, synthetic route data,
// every request outside loopback aborted. A forwarding ResizeObserver counts CURRENTLY REGISTERED targets (RF0511-13).
const {out}=require('./qa-env.cjs').qaEnv({preview:false});
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),http=require('http'),path=require('path'),assert=require('assert/strict');
const dir=process.argv[2]&&path.resolve(process.argv[2]);
if(!dir||!fs.existsSync(path.join(dir,'trail-explorer.js'))){console.error('usage: node trail-observer-qa.cjs <published-dir>');process.exit(2)}
const {createTrailFixtureHandler}=require('./trail-map-fixture-server.cjs');
const FIXTURE='<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/trail-explorer.css"><div id="host" data-trail-explorer></div><script src="/trail-explorer.js"></script>';
const server=http.createServer(createTrailFixtureHandler(dir,FIXTURE));
const profile=[0,1,2,3].map(i=>({distanceMeters:i*100,elevationMeters:10+i,lon:-120.8+i*.001,lat:35.2+i*.001}));
const DATA={distanceMeters:300,oneWayMeters:150,gainMeters:30,lossMeters:30,maxElevationMeters:13,bounds3857:[-13448000,4227000,-13447000,4228000],coordinates:profile.map(p=>[p.lon,p.lat]),profile};
const ok=r=>r.fulfill({status:200,contentType:'application/json',body:JSON.stringify(DATA)});
const abort=r=>r.abort('failed');
const sel='#host',retry='#host [data-trail-retry]';
const TOPO=path.join(dir,'assets/trails/point-buchon-topo.webp');
async function image(state,r){
 state.hits++;
 if(state.mode==='404')return r.fulfill({status:404,body:'gone'});
 if(state.mode==='decode')return r.fulfill({status:200,contentType:'image/webp',body:'this is not an image'});
 if(state.mode==='abort')return r.abort('failed');
 return r.fulfill({status:200,contentType:'image/webp',body:fs.readFileSync(TOPO)});
}
async function open(browser,width,steps){
 const page=await browser.newPage({viewport:{width,height:900}}),state={n:0,errors:[],topo:{mode:'ok',hits:0}};
 page.on('pageerror',e=>state.errors.push(e.message));
 await page.addInitScript(()=>{
  window.__obs=[];const R=window.ResizeObserver;
  window.ResizeObserver=class extends R{constructor(f){super(f);this.t=new Set();window.__obs.push(this)}
   observe(e,o){this.t.add(e);return super.observe(e,o)}unobserve(e){this.t.delete(e);return super.unobserve(e)}disconnect(){this.t.clear();return super.disconnect()}};
  window.__active=()=>window.__obs.reduce((n,o)=>n+o.t.size,0);
  window.__activeConnected=()=>window.__obs.reduce((n,o)=>n+[...o.t].filter(e=>e.isConnected).length,0);
 });
 await page.route(u=>!['127.0.0.1','localhost'].includes(new URL(u).hostname),abort);
 await page.route('**/assets/trails/point-buchon-topo.webp',r=>image(state.topo,r));
 await page.route('**/assets/trails/point-buchon.json',r=>{const step=steps[state.n++];if(!step){state.errors.push('unexpected request');return r.abort('failed')}return step(r)});
 await page.goto(base+'/fixture');
 await page.evaluate(()=>{window.AvoshackTrailExplorer.mount(document.getElementById('host'))});
 return {page,state};
}
const active=page=>page.evaluate(()=>({total:window.__active(),connected:window.__activeConnected(),ctors:window.__obs.length}));
const armError=page=>page.evaluate(()=>{const img=document.querySelector('.trail-basemap');window.__img=img;window.__imgErr=new Promise(r=>img.addEventListener('error',()=>r(true),{once:true}))});
const imageError=page=>page.evaluate(()=>Promise.race([window.__imgErr,new Promise((_,j)=>setTimeout(()=>j(Error('no image error event')),5000))]));
const topoClick=async page=>{await armError(page);await page.getByRole('button',{name:'Topo',exact:true}).click();await imageError(page)};
async function healthy(page,n=1){
 await page.locator(sel+'[data-ready=true]').waitFor({state:'attached'});
 const a=await active(page);assert.equal(a.total,1);assert.equal(a.connected,1);assert.equal(a.ctors,n);
}
async function failedState(page,ctors){
 await page.locator(retry).waitFor();
 assert.equal(await page.locator(sel+' .trail-map-unavailable').count(),1);assert.equal(await page.locator(retry).count(),1);
 assert.equal(await page.locator(sel).getAttribute('data-ready'),'error');assert.equal(await page.locator(sel).getAttribute('data-mounted'),null);
 const a=await active(page);assert.equal(a.total,0);assert.equal(a.connected,0);if(ctors)assert.equal(a.ctors,ctors);
}
const cases={
 async failed_topo_releases_registered_stage(b,w){
  const {page,state}=await open(b,w,[ok,ok]);await healthy(page);
  state.topo.mode='404';await topoClick(page);await failedState(page,1);
  state.topo.mode='ok';await page.locator(retry).click();await healthy(page,2);assert.equal(state.n,2);assert.deepEqual(state.errors,[]);await page.close();
 },
 async repeated_image_failure_retry_does_not_accumulate_targets(b,w){
  const {page,state}=await open(b,w,[ok,ok,ok]);
  for(let i=1;i<=3;i++){
   await healthy(page,i);state.topo.mode='404';await topoClick(page);await failedState(page,i);
   if(i<3){state.topo.mode='ok';await page.locator(retry).click();}
  }
  assert.equal(state.n,3);assert.deepEqual(state.errors,[]);await page.close();
 },
 async aerial_decode_and_transport_failure_release(b,w){
  for(const mode of ['decode','abort']){
   const {page,state}=await open(b,w,[ok,ok]);await healthy(page);
   state.topo.mode=mode;await topoClick(page);await failedState(page,1);
   await page.evaluate(()=>{const r=document.querySelector('[data-trail-retry]');r.click();r.click();r.click()});
   state.topo.mode='ok';await healthy(page,2);assert.equal(state.n,2);assert.deepEqual(state.errors,[]);await page.close();
  }
 },
 async enlarged_failure_releases_and_restores(b,w){
  const {page,state}=await open(b,w,[ok,ok]);await healthy(page);
  await page.evaluate(()=>{document.body.style.overflow='scroll'});
  await page.locator('[data-map-action="expand"]').click();assert.equal(await page.locator('dialog.trail-map-dialog[open]').count(),1);
  assert.equal((await active(page)).total,1);
  state.topo.mode='404';await topoClick(page);await failedState(page,1);
  assert.equal(await page.locator('dialog').count(),0);assert.equal(await page.evaluate(()=>document.body.style.overflow),'scroll');
  state.topo.mode='ok';await page.locator(retry).click();await healthy(page,2);assert.equal(state.n,2);assert.deepEqual(state.errors,[]);await page.close();
 },
 async healthy_modal_reparent_keeps_observation(b,w){
  const {page,state}=await open(b,w,[ok]);await healthy(page);
  const vb=()=>page.evaluate(()=>[document.querySelector('.trail-map-canvas').getAttribute('viewBox'),document.querySelector('.trail-profile-svg').getAttribute('viewBox')]);
  const before=await vb();
  await page.locator('[data-map-action="expand"]').click();assert.equal(await page.locator('dialog.trail-map-dialog[open]').count(),1);
  await healthy(page);await page.waitForFunction(o=>document.querySelector('.trail-map-canvas').getAttribute('viewBox')!==o,before[0]);
  await page.keyboard.press('Escape');await page.locator('dialog').waitFor({state:'detached'});await healthy(page);
  await page.waitForFunction(o=>document.querySelector('.trail-map-canvas').getAttribute('viewBox')===o,before[0]);
  const h=w===390?700:1100;await page.setViewportSize({width:w===390?320:900,height:h});
  await page.waitForFunction(o=>document.querySelector('.trail-profile-svg').getAttribute('viewBox')!==o,before[1]);
  await healthy(page);assert.equal(await page.locator(sel+' .trail-explorer').count(),1);assert.deepEqual(state.errors,[]);await page.close();
 },
 async early_request_failure_has_no_observer_to_release(b,w){
  const {page,state}=await open(b,w,[abort,ok]);await page.locator(retry).waitFor();
  const a=await active(page);assert.equal(a.ctors,0);assert.equal(a.total,0);
  await page.evaluate(()=>document.querySelector('.trail-basemap')?.dispatchEvent(new Event('error')));
  await page.locator(retry).click();await healthy(page,1);assert.equal(state.n,2);
  // late duplicate image-error event on the now-discarded failed attempt must not throw or double-release
  state.topo.mode='404';await topoClick(page);await failedState(page,1);
  await page.evaluate(()=>window.__img.dispatchEvent(new Event('error')));await page.waitForTimeout(100);
  await failedState(page,1);assert.deepEqual(state.errors,[]);await page.close();
 },
};
let base;
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined}),results=[];
 try{for(const w of [390,1440])for(const [name,fn] of Object.entries(cases)){await fn(browser,w);results.push(name+'@'+w)}}
 finally{await browser.close();server.close()}
 fs.writeFileSync(out+'/trail-observer-QA.json',JSON.stringify({checkedAt:new Date().toISOString(),results},null,2));console.log('Trail observer lifetime passed ('+results.length+' checks)');
})().catch(e=>{console.error(e);process.exit(1)});

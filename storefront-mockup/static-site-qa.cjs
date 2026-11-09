// AVO-LAUNCH-1: drive the PUBLISHED site (python3 hass/sitegen.py --publish DIR) on a plain static host:
// no /api, POST answered with an HTML 405, directories served by their index.html (as Netlify, Cloudflare Pages or
// Vercel do). Every published page is checked for commerce surface and pre-launch copy, not just the home page;
// /hike must render its sample invitation, trail map and journal from static files, and both signup forms must show
// a plain sentence instead of a parser error.
//   node storefront-mockup/static-site-qa.cjs DIR      (DIR outside the repo; QA_OUT_DIR as for the other checks)
const {out}=require('./qa-env.cjs').qaEnv({preview:false});
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const refuse=m=>{process.stderr.write('static-site QA refused: '+m+'\n');process.exit(2)};
const root=process.argv[2]&&fs.realpathSync(process.argv[2]);
if(!root||!fs.statSync(root).isDirectory())refuse('pass the folder written by sitegen.py --publish');
const repo=fs.realpathSync(path.resolve(__dirname,'..'));
if(root===repo||root.startsWith(repo+path.sep))refuse('the published folder must be outside the repository');
const TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.json':'application/json',
 '.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp'};
const page404=fs.existsSync(path.join(root,'404.html'))?fs.readFileSync(path.join(root,'404.html')):'<!doctype html><title>Not found</title><p>Not found</p>'; // a static host serves the published 404.html (status 404) for a missing path
const MISSING=['/no-such-page','/hike/nope/deeper'];
const server=http.createServer((req,res)=>{
 if(req.method!=='GET'&&req.method!=='HEAD'){res.writeHead(405,{'Content-Type':'text/html'});return res.end('<!doctype html><title>405</title>')}
 let rel=decodeURIComponent(new URL(req.url,'http://x').pathname);let file=path.join(root,rel);
 if(!file.startsWith(root)){res.writeHead(404,{'Content-Type':'text/html'});return res.end(page404)}
 try{if(fs.statSync(file).isDirectory())file=path.join(file,'index.html')}catch{}
 fs.readFile(file,(err,data)=>{if(err){res.writeHead(404,{'Content-Type':'text/html'});return res.end(page404)}
  res.writeHead(200,{'Content-Type':TYPES[path.extname(file)]||'application/octet-stream'});res.end(req.method==='HEAD'?undefined:data)});
});
const htmlPages=dir=>fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?htmlPages(path.join(dir,e.name)):e.name.endsWith('.html')?[path.join(dir,e.name)]:[]);
const COMMERCE_SELECTORS='[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail,.cart-line,.subtotal,#count';
const COMMERCE_TEXT=/\$\s?\d|\bbasket\b|\bcheck ?out\b|\bcart\b|add to (?:bag|basket|cart)|weekly box|\bmerch|pickup|online shop|\bprices?\b|stock & orders/i;
const PRELAUNCH=/sandbox|before (?:a public )?launch|during setup|not been checked|not connected|saved locally|local service|unsubscribe/i;
const RAW_ERROR=/JSON|Unexpected token|<!doctype|SyntaxError|Failed to fetch|TypeError/i;
const CLOSED='Online signup isn’t open yet, so nothing was sent or saved. Please say hello at the Shack instead.';
const UPFRONT='Online signup isn’t open yet. Please say hello at the Shack instead.';
// AV1422-07: closed up front (no typing), controls disabled; a script-forced submit still gets the CLOSED sentence and sends nothing.
const closedUpfront=async(page,form,inputs)=>{const st=page.locator(form+' .form-status');await st.filter({hasText:UPFRONT}).waitFor();assert.equal((await st.innerText()).trim(),UPFRONT);assert.doesNotMatch(await st.innerText(),RAW_ERROR);for(const i of inputs)assert.ok(await page.locator(i).isDisabled(),i+' disabled');assert.ok(await page.locator(form+' button[type=submit]').isDisabled(),form+' button disabled');assert.equal(await page.locator(form).getAttribute('aria-disabled'),'true');await page.locator(form).evaluate(f=>{f.querySelectorAll(':disabled').forEach(x=>x.disabled=false);f.noValidate=true;f.requestSubmit()});await st.filter({hasText:CLOSED}).waitFor()};
server.listen(0,'127.0.0.1',async()=>{
 const base=`http://127.0.0.1:${server.address().port}`;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const result={checkedAt:new Date().toISOString(),pages:[]};
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],bad=[];
  page.on('pageerror',e=>errors.push(e.message));
  // Without the club service the forms must not send what visitors typed: no POST at all, and no email in any URL.
  const sent=[];page.on('request',r=>{if(r.method()!=='GET'||r.postData()||r.url().includes('example.com'))sent.push(r.method()+' '+r.url())});
  page.on('response',r=>{const p=new URL(r.url()).pathname;if(r.status()>=400&&!p.startsWith('/api/')&&!(r.request().resourceType()==='document'&&MISSING.includes(p)))bad.push(r.status()+' '+r.url())});
  const routes=htmlPages(root).map(f=>'/'+path.relative(root,f).split(path.sep).join('/').replace(/index\.html$/,''));
  assert.deepEqual(routes.sort(),['/','/404.html','/hike/']);
  for(const route of [...routes,'/hike']){
   await page.goto(base+route);await page.waitForLoadState('networkidle');
   assert.equal(await page.locator(COMMERCE_SELECTORS).count(),0,route+': commerce markup');
   await page.locator('[data-policy]').click();const policy=await page.locator('#dialog-content').innerText();await page.keyboard.press('Escape');
   const text=await page.locator('body').innerText();
   assert.doesNotMatch(text,COMMERCE_TEXT,route+': commerce wording');
   assert.doesNotMatch(text+policy,PRELAUNCH,route+': pre-launch wording');
   assert.match(policy,/doesn’t use cookies/);
   const noAlt=await page.locator('img').evaluateAll(a=>a.filter(e=>!(e.getAttribute('alt')||'').trim()).length);
   assert.equal(noAlt,0,route+': image without alt text');
   result.pages.push({route,commerce:0,prelaunch:0,imagesWithoutAlt:0});
  }
  // Positive control: the same selector and wording checks see the archived commerce page in the working folder.
  const archived=fs.readFileSync(path.join(repo,'storefront-mockup/archive/commerce-preview/index.html'),'utf8');
  const control=await browser.newPage({javaScriptEnabled:false});await control.setContent(archived);
  assert.ok(await control.locator(COMMERCE_SELECTORS).count()>0);assert.match(archived,COMMERCE_TEXT);await control.close();
  assert.equal(fs.existsSync(path.join(root,'archive')),false);

  // AVO-SHOP-CLEAN-1: the shop opens on packaged goods (?view=all is every item); the three catalog notices are gone.
  await page.goto(base+'/?view=all');await page.locator('#catalog-grid article').first().waitFor();
  assert.equal((await page.locator('#catalog-count').textContent()).split(' · ')[0],'170 selections');
  assert.equal(await page.locator('.selection-checked').count(),0);
  await page.goto(base+'/');await page.locator('#catalog-grid article').first().waitFor();
  assert.equal((await page.locator('#catalog-count').textContent()).split(' · ')[0],'105 selections','default view: packaged goods');
  assert.equal(await page.locator('[data-view="packaged"]').getAttribute('aria-pressed'),'true');
  const pageText=await page.locator('body').innerText();
  for(const gone of ['names the town a producer or maker calls home','Our selection changes with the seasons','illustrations made from photos of our shelves'])assert.ok(!pageText.includes(gone),'notice gone: '+gone);
  await closedUpfront(page,'#community-newsletter',['#newsletter-email','#community-newsletter input[name=hikes]']);

  // AV1422-09: heading levels on /hike (closed dialog excluded) start h1,h2 and never jump by more than one.
  const headingOrder=async(p,when)=>{const l=await p.evaluate(()=>[...document.querySelectorAll('main h1,main h2,main h3,main h4,main h5,main h6')].filter(h=>!h.closest('dialog')).map(h=>+h.tagName[1]));assert.deepEqual(l.slice(0,2),[1,2],when+': h1 then h2');l.forEach((n,i)=>assert.ok(i===0||n-l[i-1]<=1,when+': heading jump '+l.join(',')))};
  for(const route of ['/hike','/hike/']){
   const reqs=[],on=q=>{if(/point-buchon(-aerial\.webp|\.json)/.test(q.url()))reqs.push(q.url())};page.on('request',on);
   await page.goto(base+route);await page.locator('#upcoming-hikes article').first().waitFor();await page.waitForLoadState('networkidle');
   assert.deepEqual(reqs,[],route+': no map files before the map is near');assert.match(await page.locator('[data-trail-explorer]').innerText(),/Loading the trail map/);
   await page.locator('[data-trail-explorer]').scrollIntoViewIfNeeded();await page.locator('[data-trail-explorer][data-ready=true]').waitFor();
   assert.equal(reqs.filter(u=>/aerial\.webp/.test(u)).length,1,route+': one aerial request');assert.equal(reqs.filter(u=>/\.json/.test(u)).length,1,route+': one route request');page.off('request',on);await headingOrder(page,route);
   assert.equal(await page.locator('.trail-invitation').count(),1,route+': sample invitation');
   assert.ok(await page.getByText('Sample invitation · plans to be confirmed').isVisible());
   assert.equal(await page.locator('.trail-map-canvas').count(),1,route+': trail map');
   assert.equal(await page.locator('.trail-journal-entry').count(),2,route+': trail journal');
   assert.match(await page.locator('#history-context').innerText(),/not confirmed club history/);
   assert.doesNotMatch(await page.locator('#upcoming-hikes').innerText(),/isn’t available right now/);
   await closedUpfront(page,'#hike-updates',['#hike-email']);
  }
  // AV1422-08: no IntersectionObserver mounts at once; a 404 route file still reaches the error state.
  for(const [name,init,fail] of [['no IntersectionObserver',true,false],['route file 404',false,true],['aerial image 404',false,'aerial']]){
   const ctx=await browser.newContext({viewport:{width:390,height:844}}),p=await ctx.newPage(),errs=[];p.on('pageerror',e=>errs.push(e.message));
   if(init)await p.addInitScript(()=>{delete window.IntersectionObserver});
   if(fail)await p.route(fail==='aerial'?'**/point-buchon-aerial.webp':'**/point-buchon.json',r=>r.fulfill({status:404,body:''}));
   await p.goto(base+'/hike/');await p.locator('#upcoming-hikes article').first().waitFor();
   if(fail)await p.locator('[data-trail-explorer]').scrollIntoViewIfNeeded();
   await p.locator('[data-trail-explorer][data-ready]').waitFor({state:'attached'});
   if(fail)await p.locator('[data-trail-explorer][data-ready=error]').waitFor({state:'attached'});assert.equal(await p.locator('[data-trail-explorer]').getAttribute('data-ready'),fail?'error':'true',name);if(fail){assert.equal(await p.locator('[data-trail-explorer] .trail-map-canvas').count(),0,name+': no map canvas');assert.ok(await p.locator('[data-trail-explorer] .trail-map-unavailable a[href*="pge.com"]').isVisible(),name+': official guide link');}assert.deepEqual(errs,[],name+': page errors');await ctx.close();
  }
  // AV1422-08 edge 5, delayed: the aerial fails after Enlarge map moved the map into the dialog; the dialog and page scroll lock are cleaned up, the fallback shows, and retry recovers.
  {const ctx=await browser.newContext({viewport:{width:1200,height:900}}),p=await ctx.newPage(),errs=[];p.on('pageerror',e=>errs.push(e.message));
   let release;const gate=new Promise(r=>release=r),aerial='**/point-buchon-aerial.webp';
   await p.route(aerial,async r=>{await gate;await r.fulfill({status:404,body:''});});
   await p.goto(base+'/hike/');await p.locator('[data-trail-explorer]').scrollIntoViewIfNeeded();
   await p.locator('[data-trail-explorer][data-ready=true]').waitFor({state:'attached'});
   await p.getByRole('button',{name:'Enlarge map',exact:true}).click();assert.equal(await p.locator('dialog[open]').count(),1,'enlarged: dialog open');
   release();await p.locator('[data-trail-explorer][data-ready=error]').waitFor({state:'attached'});
   assert.equal(await p.locator('dialog.trail-map-dialog').count(),0,'enlarged aerial 404: dialog removed');assert.equal(await p.evaluate(()=>document.body.style.overflow),'','enlarged aerial 404: scroll lock released');
   assert.equal(await p.locator('[data-trail-explorer] .trail-map-canvas').count(),0,'enlarged aerial 404: no canvas');assert.ok(await p.locator('[data-trail-explorer] .trail-map-unavailable a[href*="pge.com"]').isVisible(),'enlarged aerial 404: official guide link');
   await p.unroute(aerial);await p.locator('[data-trail-retry]').click();await p.locator('[data-trail-explorer][data-ready=true]').waitFor({state:'attached'});
   assert.equal(await p.locator('[data-trail-explorer] .trail-map-canvas').count(),1,'retry after enlarged aerial 404: map back');assert.equal(await p.locator('dialog.trail-map-dialog').count(),0,'retry: no stale dialog');assert.deepEqual(errs,[],'enlarged aerial 404: page errors');await ctx.close();}
  // AV1422-05: a fixed clock decides whether the sample invitation (startsAt 2026-11-08 09:00 Pacific) shows its date or "Date to be confirmed".
  const sample=JSON.parse(fs.readFileSync(path.join(root,'hiking-preview.json'),'utf8')),json=body=>({contentType:'application/json',body:JSON.stringify(body)});
  const hikeAt=async(iso,{startsAt=sample.upcoming.startsAt,events}={})=>{const ctx=await browser.newContext({viewport:{width:390,height:844}}),p=await ctx.newPage(),errs=[];p.on('pageerror',e=>errs.push(e.message));const sent=[];p.on('request',r=>{if(r.method()!=='GET'||r.postData()||/[@?]|example\.com/.test(r.url()))sent.push(r.method()+' '+r.url())});
   await p.clock.setFixedTime(new Date(iso));await p.route('**/hiking-preview.json',r=>r.fulfill(json({...sample,upcoming:{...sample.upcoming,startsAt}})));
   if(events)await p.route('**/community.json',r=>r.fulfill(json({events,routeIdeas:[]})));
   await p.goto(base+'/hike/');await p.locator('#upcoming-hikes article').first().waitFor();
   const r={errs,sent,arts:await p.locator('#upcoming-hikes article').evaluateAll(a=>a.map(x=>({t:x.querySelector('h2').innerText,txt:x.innerText,n:x.querySelectorAll('[data-confirmed-guests]').length,b:x.querySelectorAll('[data-rsvp]').length,x:x.classList.contains('hike-cancelled')}))),body:await p.locator('body').innerText(),times:await p.locator('.trail-invitation-date time').count(),dateLine:await p.locator('.trail-invitation-date').allInnerTexts(),label:await p.getByText('Sample invitation · plans to be confirmed').count()};await headingOrder(p,'hike '+iso);await ctx.close();return r};
  for(const [when,iso] of [['the day before','2026-11-07T20:00:00Z'],['the same Pacific day','2026-11-08T20:00:00Z'],['UTC next day, still the 8th in Pacific','2026-11-09T06:00:00Z']]){
   const r=await hikeAt(iso);assert.equal(r.times,1,when+': <time> shown');assert.match(r.dateLine[0],/^Sunday, November 8, 2026 · 9:00 am$/,when);assert.equal(r.label,1,when+': sample label');assert.deepEqual(r.errs,[]);}
  for(const [when,iso,startsAt] of [['next Pacific day','2026-11-09T08:30:00Z'],['garbage startsAt','2026-11-08T20:00:00Z','not a date'],['missing startsAt','2026-11-08T20:00:00Z',null]]){
   const r=await hikeAt(iso,startsAt===undefined?{}:{startsAt});assert.deepEqual(r.dateLine,['Date to be confirmed'],when);assert.equal(r.times,0,when+': no <time>');
   assert.equal(r.label,1,when+': sample label stays');assert.doesNotMatch(r.body,/Invalid Date/);assert.deepEqual(r.errs,[],when+': page errors');}
  await hikeAt('2026-11-09T08:30:00Z',{events:[{id:'next-1',title:'Next hike',status:'scheduled',startsAt:'2026-12-06T09:00:00-08:00',timezone:'America/Los_Angeles'},{id:'done-1',title:'Done hike',status:'completed',startsAt:'2026-10-04T09:00:00-07:00',timezone:'America/Los_Angeles',description:'A good day.'}]});
  const real=await hikeAt('2026-11-09T08:30:00Z',{events:[{id:'real-1',title:'Real hike',status:'scheduled',startsAt:'2026-12-06T09:00:00-08:00',timezone:'America/Los_Angeles'}]});
  assert.match(real.body,/Sunday, December 6, 2026/);assert.doesNotMatch(real.body,/Date to be confirmed/);assert.equal(real.label,0,'a real hike replaces the sample invitation');assert.deepEqual(real.errs,[]);
  // AV0007-01: the static home page names the earliest scheduled hike from the published community.json (no /api, no sample preview).
  const homeNext=async(events,{iso='2026-11-09T08:30:00Z',tz,width=390}={})=>{const ctx=await browser.newContext({viewport:{width,height:844},timezoneId:tz}),p=await ctx.newPage(),errs=[],reqs=[];p.on('pageerror',e=>errs.push(e.message));p.on('request',r=>reqs.push(r.method()+' '+new URL(r.url()).pathname));
   try{await p.clock.setFixedTime(new Date(iso));if(events!==undefined)await p.route('**/community.json',r=>events===null?r.fulfill({status:404,contentType:'text/html',body:'<p>no</p>'}):r.fulfill(json({events,routeIdeas:[]})));
    await Promise.all([p.waitForResponse('**/community.json'),p.goto(base+'/')]);await p.waitForLoadState('networkidle');
    const el=p.locator('#next-hike-line');return {errs,reqs,hidden:await el.isHidden(),n:await el.count(),links:await el.locator('a').count(),bold:await el.locator('b').count(),href:await el.locator('a').first().getAttribute('href').catch(()=>null),text:(await el.textContent()).replace(/\s+/g,' ').trim(),overflow:await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth)}}finally{await ctx.close()}};
  const nh=(id,title,startsAt,more)=>({id,title,status:'scheduled',startsAt,timezone:'America/Los_Angeles',...more});
  {const r=await homeNext([nh('h-late','Later hike','2026-12-20T09:00:00-08:00'),nh('h-x','Cancelled sooner','2026-11-20T09:00:00-08:00',{status:'cancelled'}),nh('h-1','Earlier <b>&</b> "hike"','2026-12-06T09:00:00-08:00')]);
   assert.equal(r.n,1);assert.equal(r.links,1);assert.equal(r.hidden,false);assert.equal(r.href,'/hike#upcoming-hikes');assert.equal(r.bold,0);
   assert.equal(r.text,'Next hike: Sunday, December 6, 9:00 AM - Earlier <b>&</b> "hike"');assert.deepEqual(r.errs,[]);
   assert.ok(!r.reqs.some(q=>q.includes('hiking-preview')),'home line asked for the sample preview');assert.ok(!r.reqs.some(q=>q.startsWith('POST')),'POST from home');}
  for(const [name,events] of [['empty',[]],['cancelled only',[nh('c','C','2026-12-06T09:00:00-08:00',{status:'cancelled'})]],['completed only',[nh('d','D','2026-12-06T09:00:00-08:00',{status:'completed'})]],['past day only',[nh('p','P','2026-11-08T09:00:00-08:00')]],['missing file',null],['malformed events',{bad:1}]]){
   const r=await homeNext(events);assert.equal(r.n,1,name);assert.equal(r.hidden,true,name);assert.equal(r.links,0,name);assert.equal(r.text,'',name);assert.deepEqual(r.errs,[],name);assert.ok(!r.reqs.some(q=>q.includes('hiking-preview')),name+': sample requested');}
  {const day=[nh('s','Started today','2026-11-09T07:00:00-08:00')]; // Pacific 9 Nov 07:00
   // RF0814-11: a walk that has already started is not the "next" hike, even on its own Pacific day and with the viewer in Tokyo; it stays visible as TODAY on /hike.
   let r=await homeNext(day,{iso:'2026-11-09T20:00:00Z',tz:'Asia/Tokyo'});assert.equal(r.n,1,'started only');assert.equal(r.hidden,true,'started only: hidden');assert.equal(r.links,0,'started only: no link');assert.equal(r.text,'','started only: empty');assert.deepEqual(r.errs,[]);
   r=await homeNext(day,{iso:'2026-11-10T08:30:00Z',tz:'Asia/Tokyo'});assert.equal(r.links,0,'hidden after Pacific midnight');
   r=await homeNext([nh('t','Plain hike','2026-12-06T09:00:00-08:00',{timezone:undefined}),],{width:1440});assert.equal(r.text,'Next hike: Sunday, December 6, 9:00 AM - Plain hike');
   r=await homeNext([nh('w','A very long hike title '.repeat(8),'2026-12-06T09:00:00-08:00')],{width:390});assert.equal(r.overflow,false,'long title overflows the page');}
  // RF0814-11 homeNextSkipsStartedWithFutureSibling: noon Pacific, 9am started + 3pm future (reverse input order): home names only 3pm; /hike keeps 9am as TODAY and 3pm as THE NEXT HIKE.
  {const noon='2026-11-09T20:00:00Z',nine=nh('r-9','Started morning walk','2026-11-09T09:00:00-08:00'),three=nh('r-3','Future afternoon walk','2026-11-09T15:00:00-08:00');
   let r=await homeNext([three,nine],{iso:noon});assert.equal(r.links,1,'mixed');assert.equal(r.text,'Next hike: Monday, November 9, 3:00 PM - Future afternoon walk');assert.equal(r.href,'/hike#upcoming-hikes');assert.deepEqual(r.errs,[]);assert.ok(!r.reqs.some(q=>q.startsWith('POST')),'POST from home');
   r=await homeNext([nine,three],{iso:noon,tz:'Asia/Tokyo'});assert.equal(r.text,'Next hike: Monday, November 9, 3:00 PM - Future afternoon walk','mixed, other input order, viewer in Tokyo');
   const h=await hikeAt(noon,{events:[three,nine]});const card=t=>h.arts.find(a=>a.t===t);
   assert.match(card('Started morning walk').txt,/TODAY/,'/hike keeps the started walk as TODAY');assert.match(card('Future afternoon walk').txt,/THE NEXT HIKE/,'/hike labels the future walk THE NEXT HIKE');assert.deepEqual(h.errs,[]);
   // homeNextStartBoundary: start-1ms selects it, the exact start and start+1ms do not.
   for(const [iso,shown] of [['2026-11-09T22:59:59.999Z',true],['2026-11-09T23:00:00.000Z',false],['2026-11-09T23:00:00.001Z',false]]){r=await homeNext([three],{iso});assert.equal(r.links,shown?1:0,iso);assert.equal(r.hidden,!shown,iso);assert.equal(r.text,shown?'Next hike: Monday, November 9, 3:00 PM - Future afternoon walk':'',iso);}
   // homeNextAbsoluteTimeAcrossZones: fall-back hour, same wall text 1:30 AM twice; decided by instant (PDT 08:30Z, PST 09:30Z), and equal instants keep input order.
   const pdt=nh('f-pdt','First 1:30','2026-11-01T01:30:00-07:00'),pst=nh('f-pst','Second 1:30','2026-11-01T01:30:00-08:00');
   r=await homeNext([pst,pdt],{iso:'2026-11-01T08:00:00Z',tz:'Asia/Tokyo'});assert.equal(r.text,'Next hike: Sunday, November 1, 1:30 AM - First 1:30','before both');
   r=await homeNext([pst,pdt],{iso:'2026-11-01T09:00:00Z',tz:'Asia/Tokyo'});assert.equal(r.text,'Next hike: Sunday, November 1, 1:30 AM - Second 1:30','between the two identical wall times');
   r=await homeNext([pst,pdt],{iso:'2026-11-01T09:30:00Z'});assert.equal(r.links,0,'both started');
   r=await homeNext([nh('e-2','Equal second','2026-12-06T09:00:00-08:00'),nh('e-1','Equal first','2026-12-06T09:00:00-08:00')]);assert.equal(r.text,'Next hike: Sunday, December 6, 9:00 AM - Equal second','equal starts keep input order');
   // homeNextFiltersAndFallback: invalid/missing starts and non-scheduled events are never selected next to a valid future sibling.
   r=await homeNext([nh('x1','Bad start','not a date'),nh('x2','No start',undefined,{startsAt:undefined}),nh('x3','Cancelled','2026-12-01T09:00:00-08:00',{status:'cancelled'}),nh('x4','Completed','2026-12-02T09:00:00-08:00',{status:'completed'}),nh('x5','Good sibling','2026-12-20T09:00:00-08:00')]);assert.equal(r.text,'Next hike: Sunday, December 20, 9:00 AM - Good sibling');assert.deepEqual(r.errs,[]);}
  // AV1422-09: the no-hike empty state (sample off, no events) keeps the look its h3 had: 32px/8px at desktop, 29px/8px on a phone.
  for(const [w,size] of [[1440,'32px'],[390,'29px']]){const ctx=await browser.newContext({viewport:{width:w,height:900}}),p=await ctx.newPage();
   await p.route('**/hiking-preview.json',r=>r.fulfill(json({...sample,enabled:false})));await p.route('**/community.json',r=>r.fulfill(json({events:[],routeIdeas:[]})));
   await p.goto(base+'/hike/');await p.locator('#upcoming-hikes .hike-empty h2').waitFor();
   const cs=await p.locator('#upcoming-hikes .hike-empty h2').evaluate(h=>{const c=getComputedStyle(h);return {fs:c.fontSize,mb:c.marginBottom,lh:c.lineHeight,ls:c.letterSpacing}});
   assert.deepEqual(cs,{fs:size,mb:'8px',lh:(parseFloat(size)*1.2).toFixed(1).replace(/\.0$/,'')+'px',ls:(parseFloat(size)*-.02).toFixed(3).replace(/0+$/,'').replace(/\.$/,'')+'px'},'empty hike state heading at '+w);
   await headingOrder(p,'empty hike state '+w);await ctx.close();}
  // AV1422-06: no club service, so nobody counted guests: no count, no RSVP button; synthetic titles only.
  const at='2026-12-01T09:00:00-08:00',ev=(id,title,more)=>({id,title,status:'scheduled',startsAt:at,timezone:'America/Los_Angeles',meetingPoint:'Test trailhead',...more});
  const fx=await hikeAt('2026-11-09T08:30:00Z',{events:[ev('t-on','Synthetic RSVP-on hike',{rsvpEnabled:true,confirmedGuests:7}),ev('t-off','Synthetic RSVP-off hike',{rsvpEnabled:false}),ev('t-none','Synthetic no-flag hike',{}),ev('t-x','Synthetic cancelled hike',{status:'cancelled',startsAt:'2026-11-09T12:00:00-08:00',rsvpEnabled:true})]});
  const art=t=>fx.arts.find(a=>a.t.endsWith(t)),JOIN=/To join, ask at the Shack\./,SHARED=/RSVP details will be shared when confirmed\./;
  assert.equal(fx.arts.length,4,'four fixture hikes shown');
  for(const a of fx.arts){assert.equal(a.n,0,a.t+': no guest count');assert.doesNotMatch(a.txt,/confirmed guests?/i,a.t+': no invented count');assert.equal(a.b,0,a.t+': no RSVP button')}
  assert.match(art('RSVP-on hike').txt,JOIN);assert.doesNotMatch(art('RSVP-on hike').txt,SHARED);
  for(const t of ['RSVP-off hike','no-flag hike']){assert.match(art(t).txt,SHARED,t);assert.doesNotMatch(art(t).txt,JOIN,t)}
  assert.ok(art('cancelled hike').x&&/CANCELLED/.test(art('cancelled hike').txt)&&/This hike is cancelled\./.test(art('cancelled hike').txt));assert.doesNotMatch(art('cancelled hike').txt,JOIN);assert.doesNotMatch(art('cancelled hike').txt,SHARED);
  assert.deepEqual(fx.errs,[]);assert.deepEqual(fx.sent,[],'the static hike list sent something');
  for(const missing of MISSING){ // a missing path, at any depth, gets the shop's own 404 page with its stylesheet
   const res=await page.goto(base+missing);await page.waitForLoadState('networkidle');
   assert.equal(res.status(),404,missing+': status');assert.equal(await page.locator('h1').innerText(),'That page isn’t here.',missing+': heading');
   assert.equal(await page.locator('header nav a[href="/hike/"]').count(),1,missing+': header');assert.equal(await page.locator('footer').count(),1,missing+': footer');
   assert.equal(await page.locator('head meta[name=robots][content=noindex]').count(),1,missing+': noindex');
   assert.equal(await page.locator('main a[href="/#market"]').count(),1,missing+': food link');assert.equal(await page.locator('main a[href="/hike/"]').count(),1,missing+': club link');
   assert.equal(await page.locator(COMMERCE_SELECTORS).count(),0,missing+': commerce markup');
   const t=await page.locator('body').innerText();assert.doesNotMatch(t,COMMERCE_TEXT,missing+': commerce wording');assert.doesNotMatch(t,PRELAUNCH,missing+': pre-launch wording');
   assert.ok(await page.evaluate(()=>[...document.styleSheets].some(s=>s.cssRules.length>0)),missing+': stylesheet loaded');
  }
  // AV1422-07 (review): a delayed unavailable service answers once per page, and a real submit made while that answer is pending leaves every control disabled.
  for(const [route,form,inputs,email] of [['/','#community-newsletter',['#newsletter-email'],'#newsletter-email'],['/hike/','#hike-updates',['#hike-email'],'#hike-email']]){
   const p=await browser.newPage({viewport:{width:390,height:844}});let release,hits=0,posts=0;const gate=new Promise(r=>release=r);
   p.on('request',r=>{if(r.method()==='POST')posts++});
   await p.route('**/api/community',async r=>{hits++;await gate;await r.fulfill({status:503,contentType:'application/json',body:'{}'})});
   await p.goto(base+route);await p.locator(email).fill('visitor@example.com');
   assert.equal(await p.locator(form+' button[type=submit]').isDisabled(),false,route+': enabled while the probe is pending');
   await p.locator(form+' button[type=submit]').click();await p.locator(form+' .form-status').filter({hasText:'Saving…'}).waitFor();
   release();await p.locator(form+' .form-status').filter({hasText:/Online signup isn’t open yet/}).waitFor();await p.waitForLoadState('networkidle');
   for(const i of [...inputs,form+' button[type=submit]'])assert.ok(await p.locator(i).isDisabled(),route+': '+i+' disabled after a submit raced the probe');
   assert.equal(await p.locator(form).getAttribute('aria-disabled'),'true');
   assert.equal(hits,1,route+': one GET /api/community');assert.equal(posts,0,route+': nothing posted');await p.close();
  }
  assert.deepEqual(errors,[]);assert.deepEqual(bad,[]);assert.deepEqual(sent,[],'a form sent visitor data without the club service');
  Object.assign(result,{hikeStatic:true,formsFailGracefully:true,formsSendNothing:true,noticesGone:true,defaultView:"packaged",catalog:170,errors});
  fs.writeFileSync(path.join(out,'static-site-QA.json'),JSON.stringify(result,null,1));
  console.log('Static published site passed');console.log(JSON.stringify(result));
 }finally{await browser.close();server.close()}
});

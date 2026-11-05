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
const closedUpfront=async(page,form,inputs)=>{const st=page.locator(form+' .form-status');await st.filter({hasText:UPFRONT}).waitFor();assert.equal((await st.innerText()).trim(),UPFRONT);assert.doesNotMatch(await st.innerText(),RAW_ERROR);for(const i of inputs)assert.ok(await page.locator(i).isDisabled(),i+' disabled');assert.ok(await page.locator(form+' button[type=submit]').isDisabled(),form+' button disabled');assert.equal(await page.locator(form).getAttribute('aria-disabled'),'true');await page.locator(form).evaluate(f=>{f.querySelectorAll(':disabled').forEach(x=>x.disabled=false);f.requestSubmit()});await st.filter({hasText:CLOSED}).waitFor()};
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

  await page.goto(base+'/');await page.locator('#catalog-grid article').first().waitFor();
  assert.equal((await page.locator('#catalog-count').textContent()).split(' · ')[0],'170 selections');
  assert.equal(await page.locator('.selection-checked').count(),0);
  assert.ok(await page.getByText('It isn’t a claim that every ingredient was grown there.').isVisible(),'sourcing sentence');
  await closedUpfront(page,'#community-newsletter',['#newsletter-email','#community-newsletter input[name=hikes]']);

  for(const route of ['/hike','/hike/']){
   await page.goto(base+route);await page.locator('[data-trail-explorer][data-ready=true]').waitFor();
   assert.equal(await page.locator('.trail-invitation').count(),1,route+': sample invitation');
   assert.ok(await page.getByText('Sample invitation · plans to be confirmed').isVisible());
   assert.equal(await page.locator('.trail-map-canvas').count(),1,route+': trail map');
   assert.equal(await page.locator('.trail-journal-entry').count(),2,route+': trail journal');
   assert.match(await page.locator('#history-context').innerText(),/not confirmed club history/);
   assert.doesNotMatch(await page.locator('#upcoming-hikes').innerText(),/isn’t available right now/);
   await closedUpfront(page,'#hike-updates',['#hike-email']);
  }
  // AV1422-05: a fixed clock decides whether the sample invitation (startsAt 2026-11-08 09:00 Pacific) shows its date or "Date to be confirmed".
  const sample=JSON.parse(fs.readFileSync(path.join(root,'hiking-preview.json'),'utf8')),json=body=>({contentType:'application/json',body:JSON.stringify(body)});
  const hikeAt=async(iso,{startsAt=sample.upcoming.startsAt,events}={})=>{const ctx=await browser.newContext({viewport:{width:390,height:844}}),p=await ctx.newPage(),errs=[];p.on('pageerror',e=>errs.push(e.message));const sent=[];p.on('request',r=>{if(r.method()!=='GET'||r.postData()||/[@?]|example\.com/.test(r.url()))sent.push(r.method()+' '+r.url())});
   await p.clock.setFixedTime(new Date(iso));await p.route('**/hiking-preview.json',r=>r.fulfill(json({...sample,upcoming:{...sample.upcoming,startsAt}})));
   if(events)await p.route('**/community.json',r=>r.fulfill(json({events,routeIdeas:[]})));
   await p.goto(base+'/hike/');await p.locator('#upcoming-hikes article').first().waitFor();
   const r={errs,sent,arts:await p.locator('#upcoming-hikes article').evaluateAll(a=>a.map(x=>({t:x.querySelector('h3').innerText,txt:x.innerText,n:x.querySelectorAll('[data-confirmed-guests]').length,b:x.querySelectorAll('[data-rsvp]').length,x:x.classList.contains('hike-cancelled')}))),body:await p.locator('body').innerText(),times:await p.locator('.trail-invitation-date time').count(),dateLine:await p.locator('.trail-invitation-date').allInnerTexts(),label:await p.getByText('Sample invitation · plans to be confirmed').count()};await ctx.close();return r};
  for(const [when,iso] of [['the day before','2026-11-07T20:00:00Z'],['the same Pacific day','2026-11-08T20:00:00Z'],['UTC next day, still the 8th in Pacific','2026-11-09T06:00:00Z']]){
   const r=await hikeAt(iso);assert.equal(r.times,1,when+': <time> shown');assert.match(r.dateLine[0],/^Sunday, November 8, 2026 · 9:00 am$/,when);assert.equal(r.label,1,when+': sample label');assert.deepEqual(r.errs,[]);}
  for(const [when,iso,startsAt] of [['next Pacific day','2026-11-09T08:30:00Z'],['garbage startsAt','2026-11-08T20:00:00Z','not a date'],['missing startsAt','2026-11-08T20:00:00Z',null]]){
   const r=await hikeAt(iso,startsAt===undefined?{}:{startsAt});assert.deepEqual(r.dateLine,['Date to be confirmed'],when);assert.equal(r.times,0,when+': no <time>');
   assert.equal(r.label,1,when+': sample label stays');assert.doesNotMatch(r.body,/Invalid Date/);assert.deepEqual(r.errs,[],when+': page errors');}
  const real=await hikeAt('2026-11-09T08:30:00Z',{events:[{id:'real-1',title:'Real hike',status:'scheduled',startsAt:'2026-12-06T09:00:00-08:00',timezone:'America/Los_Angeles'}]});
  assert.match(real.body,/Sunday, December 6, 2026/);assert.doesNotMatch(real.body,/Date to be confirmed/);assert.equal(real.label,0,'a real hike replaces the sample invitation');assert.deepEqual(real.errs,[]);
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
  assert.deepEqual(errors,[]);assert.deepEqual(bad,[]);assert.deepEqual(sent,[],'a form sent visitor data without the club service');
  Object.assign(result,{hikeStatic:true,formsFailGracefully:true,formsSendNothing:true,sourcingSentence:true,catalog:170,errors});
  fs.writeFileSync(path.join(out,'static-site-QA.json'),JSON.stringify(result,null,1));
  console.log('Static published site passed');console.log(JSON.stringify(result));
 }finally{await browser.close();server.close()}
});

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
const page404='<!doctype html><title>Not found</title><p>Not found</p>';
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
server.listen(0,'127.0.0.1',async()=>{
 const base=`http://127.0.0.1:${server.address().port}`;
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const result={checkedAt:new Date().toISOString(),pages:[]};
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[],bad=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400&&!new URL(r.url()).pathname.startsWith('/api/'))bad.push(r.status()+' '+r.url())});
  const routes=htmlPages(root).map(f=>'/'+path.relative(root,f).split(path.sep).join('/').replace(/index\.html$/,''));
  assert.deepEqual(routes.sort(),['/','/hike/']);
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
  await page.locator('#newsletter-email').fill('visitor@example.com');await page.locator('#community-newsletter button[type=submit]').click();
  const newsletter=page.locator('#community-newsletter .form-status');await newsletter.filter({hasText:CLOSED}).waitFor();
  assert.doesNotMatch(await newsletter.innerText(),RAW_ERROR);assert.equal(await page.locator('#newsletter-email').inputValue(),'visitor@example.com');

  for(const route of ['/hike','/hike/']){
   await page.goto(base+route);await page.locator('[data-trail-explorer][data-ready=true]').waitFor();
   assert.equal(await page.locator('.trail-invitation').count(),1,route+': sample invitation');
   assert.ok(await page.getByText('Sample invitation · plans to be confirmed').isVisible());
   assert.equal(await page.locator('.trail-map-canvas').count(),1,route+': trail map');
   assert.equal(await page.locator('.trail-journal-entry').count(),2,route+': trail journal');
   assert.match(await page.locator('#history-context').innerText(),/not confirmed club history/);
   assert.doesNotMatch(await page.locator('#upcoming-hikes').innerText(),/isn’t available right now/);
   await page.locator('#hike-email').fill('visitor@example.com');await page.locator('#hike-updates button[type=submit]').click();
   const status=page.locator('#hike-updates .form-status');await status.filter({hasText:CLOSED}).waitFor();
   assert.doesNotMatch(await status.innerText(),RAW_ERROR);
  }
  assert.deepEqual(errors,[]);assert.deepEqual(bad,[]);
  Object.assign(result,{hikeStatic:true,formsFailGracefully:true,sourcingSentence:true,catalog:170,errors});
  fs.writeFileSync(path.join(out,'static-site-QA.json'),JSON.stringify(result,null,1));
  console.log('Static published site passed');console.log(JSON.stringify(result));
 }finally{await browser.close();server.close()}
});

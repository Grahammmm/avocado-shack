const {out,base}=require('./qa-env.cjs').qaEnv({preview:true});
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined}),page=await browser.newPage();const results=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 for(const width of [390,1440]){
  await page.setViewportSize({width,height:900});
  for(const path of ['/hike','/hike/','/#hikes']){
   await page.goto(base+path);await page.waitForURL(/\/hike(?:\/|#|$)/);await page.locator('[data-trail-explorer][data-ready=true]').waitFor();
   assert.equal(await page.locator('h1').count(),1);assert.equal(await page.locator('#catalog-grid').count(),0);assert.equal(await page.locator('[data-confirmed-guests]').textContent(),'0');
   const failedImages=await page.locator('img').evaluateAll(a=>a.filter(e=>e.complete&&e.naturalWidth===0).map(e=>e.src));assert.deepEqual(failedImages,[]);
   await page.getByRole('button',{name:'Topo',exact:true}).click();assert.equal(await page.locator('.trail-map-stage').getAttribute('data-layer'),'topo');
   await page.locator('.club-intro a').click();await page.waitForTimeout(600);const top=await page.locator('#upcoming-hikes').evaluate(e=>e.getBoundingClientRect().top);assert.ok(top>=0&&top<100);
   results.push({width,path,landedAt:new URL(page.url()).pathname,map:true,guestCount:0,anchorTop:top});
  }
  await page.locator('header nav a[href="/#newsletter"]').click();await page.waitForURL(/\/#newsletter$/);await page.waitForFunction(()=>{const r=document.querySelector('#newsletter')?.getBoundingClientRect();return r&&r.top>=0&&(r.top<100||(r.bottom<=innerHeight&&scrollY>=document.documentElement.scrollHeight-innerHeight-2))},{},{timeout:5000});
  await page.locator('header nav a[href="/hike"]').click();await page.locator('#preview-hike-rsvp').waitFor();assert.equal(new URL(page.url()).pathname,'/hike');
  await page.locator('header nav a[href="/#market"]').click();await page.locator('#catalog-grid article').first().waitFor();assert.equal(await page.locator('#hikes').count(),0);
 }
 assert.deepEqual(errors,[]);fs.writeFileSync(out+'/section-navigation-QA.json',JSON.stringify({checkedAt:new Date().toISOString(),results,errors},null,2));console.log('Hiking subpage and return navigation passed');await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

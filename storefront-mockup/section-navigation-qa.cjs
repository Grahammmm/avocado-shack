const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs');
const out=process.env.QA_OUT_DIR||'storefront-mockup';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const page=await browser.newPage();const results=[];
 for(const width of [390,1440]){
  await page.setViewportSize({width,height:900});
  for(const direct of [false,true]){
   await page.goto('http://127.0.0.1:3101/'+(direct?'#hikes':''));
   await page.locator('#preview-hike-rsvp').waitFor();
   if(!direct)await page.locator('header nav a[href="#hikes"]').click();
   await page.waitForTimeout(1500);
   const measured=await page.evaluate(()=>({top:document.querySelector('#hikes').getBoundingClientRect().top,productsShown:document.querySelectorAll('#catalog-grid article').length}));
   if(measured.top<0||measured.top>100)throw Error('Hiking section moved out of view '+JSON.stringify({width,direct,...measured}));
   results.push({width,direct,...measured});
   await page.locator('.club-intro a[href="#upcoming-hikes"]').click();
   await page.waitForTimeout(800);
   const top=await page.locator('#upcoming-hikes').evaluate(e=>e.getBoundingClientRect().top);
   if(top<0||top>100)throw Error('Invitation anchor failed '+top);
  }
 }
 fs.writeFileSync(out+'/section-navigation-QA.json',JSON.stringify({checkedAt:new Date().toISOString(),results},null,2));
 console.log(JSON.stringify(results));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

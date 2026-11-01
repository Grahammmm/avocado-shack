// Hass H06 private preview capture: one Chromium page of the isolated loopback site, plus checks.
// VIEWPORT: phone (default, 390x844) or desktop (1280x900); anything else exits 1 with "bad VIEWPORT".
// env: PREVIEW_URL (http://127.0.0.1:<port>), TARGET (JSON from hass/preview.py target_for), OUT (png path),
// PLAYWRIGHT_MODULE / CHROMIUM_PATH as in the storefront QA scripts. Only GET/HEAD to the preview origin is
// allowed; every other request (any POST, anything off 127.0.0.1) is aborted. Prints {"checks": {...}}.
'use strict';
const VIEWPORTS={phone:{width:390,height:844},desktop:{width:1280,height:900}},vp=process.env.VIEWPORT||'phone';
if(!Object.hasOwn(VIEWPORTS,vp)){console.error('bad VIEWPORT');process.exit(1);}
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.PREVIEW_URL,target=JSON.parse(process.env.TARGET||'{}'),out=process.env.OUT;
const origin=new URL(base).origin;
const allowed=req=>{
  if(!['GET','HEAD'].includes(req.method()))return false;
  try{const url=new URL(req.url());return url.protocol==='data:'||(url.origin===origin&&url.hostname==='127.0.0.1');}
  catch{return false;}
};
(async()=>{
  if(!base||new URL(base).hostname!=='127.0.0.1')throw new Error('PREVIEW_URL must be a 127.0.0.1 address');
  const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
  try{
    const page=await browser.newPage({viewport:VIEWPORTS[vp]}),errors=[],blocked=[],checks={};
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>allowed(route.request())?route.continue():(blocked.push(route.request().method()),route.abort()));
    if(target.kind==='event'){
      await page.goto(base+'/hike',{waitUntil:'networkidle'});
      if(target.status==='scheduled')checks.eventShown=await page.locator('h3',{hasText:target.title}).count()>0;
    }else{
      await page.goto(base+'/',{waitUntil:'networkidle'});
      if(target.kind==='product'||target.kind==='maker'){
        await page.locator('#product-search').fill(target.name||'');
        await page.waitForTimeout(200);
        const cards=page.locator('#catalog-grid').first();
        await cards.scrollIntoViewIfNeeded();
        if(target.kind==='product'){
          const card=page.locator(`#catalog-grid article[data-product-id="${target.id}"]`);
          const count=await card.count();
          checks.productShown=count===(target.status==='active'?1:0);
          if(count===1){
            await card.scrollIntoViewIfNeeded();
            if(target.status==='active')checks.description=(await card.locator('.food-description').textContent())===target.description;
          }
        }
      }else if(target.kind==='store'){
        const lines=target.hours||[],line=page.locator('#visit .visit p').first();
        await line.scrollIntoViewIfNeeded();
        const text=await page.locator('body').innerText();
        checks.hoursShown=lines.length>0&&lines.every(l=>text.includes(l));
        const s=target.streetAddress,t=target.town;
        if(s&&t)checks.addressShown=text.includes(`${s}, ${t}`)&&text.includes(`${s} · ${t}`);
      }
    }
    await page.waitForTimeout(150);
    await page.screenshot({path:out});
    checks.noPageErrors=errors.length===0;
    checks.noPosts=!blocked.some(m=>m!=='GET'&&m!=='HEAD');
    console.log(JSON.stringify({checks,blockedRequests:blocked.length}));
  }finally{await browser.close();}
})().catch(e=>{console.error(String((e&&e.message)||e).split('\n')[0]);process.exit(1);});

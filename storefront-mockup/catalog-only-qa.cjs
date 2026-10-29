const fs=require('fs'),assert=require('assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const out=process.env.QA_OUT_DIR||'storefront-mockup',base=process.env.PREVIEW_URL||'http://127.0.0.1:3101';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/');
 assert.equal(await page.locator('[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail,#hikes').count(),0);
 assert.doesNotMatch(await page.locator('body').innerText(),/\$\d|add to basket|pickup|local delivery|weekly boxes|online shop|merchandise|Discover this food|Food & maker story/i);
 await page.locator('#product-search').fill('Cambria');const count=await page.locator('#catalog-grid article').count();assert.ok(count>0);
 assert.ok((await page.locator('#catalog-grid .origin-label').allTextContents()).every(t=>t.includes('Cambria')));
 assert.ok(await page.locator('#catalog-grid .maker-story a[href^="https://"]').count());
 // Product imagery no longer opens a separate dialog.
 await page.locator('#catalog-grid .product-image').first().click();assert.equal(await page.locator('#dialog').evaluate(e=>e.open),false);
 await page.locator('#product-search').fill('');await page.locator('[data-source="local"]').click();const localCount=await page.locator('#catalog-count').textContent();await page.locator('[data-source="organic"]').click();const organicCount=await page.locator('#catalog-count').textContent();await page.locator('[data-source="all"]').click();await page.locator('[data-filter="fruit"]').click();assert.equal(await page.locator('#catalog-grid article:not([data-category="fruit"])').count(),0);
 await page.locator('#product-search').fill('unfindablefoo');assert.equal(await page.locator('#catalog-grid article').count(),0);await page.locator('#product-search').fill('');await page.locator('[data-filter="all"]').click();
 for(let i=0;i<22;i++){await page.locator('#catalog-sentinel').scrollIntoViewIfNeeded();await page.waitForTimeout(100);}
 const all=await page.locator('#catalog-grid article').count();assert.equal(all,170);
 const content=await page.evaluate(()=>{
  const cards=[...document.querySelectorAll('#catalog-grid article')],ids=cards.map(e=>e.dataset.productId);
  return {duplicates:ids.length-new Set(ids).size,missing:cards.flatMap(card=>{const p=catalog.find(p=>p.id===card.dataset.productId),m=producers[p.producerKey];const issues=[];if(card.querySelector('.food-description').textContent!==p.description)issues.push(p.id+': food');if(m&&card.querySelector('.maker-story p')?.textContent!==m.story)issues.push(p.id+': maker');if(m&&card.querySelector('.maker-story a')?.href!==m.url)issues.push(p.id+': link');return issues;})};
 });assert.equal(content.duplicates,0);assert.deepEqual(content.missing,[]);
 const viewports=[];
 for(const width of [320,375,390,520,768,1024,1280,1440,1920]){
  await page.setViewportSize({width,height:900});
  const layout=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,background:getComputedStyle(document.body).backgroundColor,columns:getComputedStyle(document.querySelector('#catalog-grid')).gridTemplateColumns.split(' ').length}));assert.equal(layout.overflow,false,'Overflow '+width);assert.equal(layout.columns,width<520?1:width<=800?2:width<1180?3:4);viewports.push({width,...layout});
 }
 for(const width of [390,1440]){await page.setViewportSize({width,height:1000});await page.goto(base+'/');await page.locator('#brand-filter').selectOption('');await page.locator('#catalog-grid').evaluate(e=>e.scrollIntoView({behavior:'instant',block:'start'}));await page.waitForTimeout(250);await page.screenshot({path:out+`/catalog-inline-${width}.png`});await page.locator('#brand-filter').selectOption('Etto');await page.locator('#catalog-grid').evaluate(e=>e.scrollIntoView({behavior:'instant',block:'start'}));await page.screenshot({path:out+`/catalog-maker-${width}.png`});}
 await page.getByRole('button',{name:'Privacy',exact:true}).click();assert.equal(await page.locator('#dialog').evaluate(e=>e.open),true);await page.keyboard.press('Escape');
 assert.deepEqual(errors,[]);
 const result={checkedAt:new Date().toISOString(),all,duplicates:0,townSearch:count,localCount,organicCount,commerceRemoved:true,fullFoodAndMakerStoriesInline:true,producerLinksPreserved:true,productDialogRemoved:true,privacyDialogPreserved:true,viewports,errors};fs.writeFileSync(out+'/catalog-only-QA.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

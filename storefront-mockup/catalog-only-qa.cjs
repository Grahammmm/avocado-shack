const {out,base}=require('./qa-env.cjs').qaEnv({preview:true});
const fs=require('fs'),assert=require('assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/');
 assert.equal(await page.locator('.section-intro').textContent(),'An avocado from Morro Bay. A loaf from Atascadero. Cheese made in Cambria. Explore our selection and follow the flavors back to the farms, kitchens, and makers from our community.');
 assert.equal(await page.locator('[data-source],.sourcing-filters').count(),0);
 assert.equal(await page.locator('[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail,#hikes').count(),0);
 assert.doesNotMatch(await page.locator('body').innerText(),/\$\d|add to basket|pickup|local delivery|weekly boxes|online shop|merchandise|Discover this food|Food & maker story/i);
 const countText=async()=>(await page.locator('#catalog-count').textContent()).split(' \u00b7 ')[0],fullCount=await countText();assert.equal(fullCount,(await page.evaluate(()=>catalog.length))+' selections');
 await page.locator('#product-search').fill('Cambria');const count=await page.locator('#catalog-grid article').count();assert.ok(count>0);
 assert.ok((await page.locator('#catalog-grid .origin-label').allTextContents()).every(t=>t.includes('Cambria')));
 assert.ok(await page.locator('#catalog-grid .maker-story a[href^="https://"]').count());
 const story=page.locator('#catalog-grid details.maker-story').first(),summary=story.locator('summary');
 assert.equal(await story.evaluate(e=>e.open),false);assert.equal(await story.locator('p').isVisible(),false);
 await summary.focus();await page.keyboard.press('Enter');assert.equal(await story.evaluate(e=>e.open),true);assert.equal(await story.locator('p').isVisible(),true);
 await page.keyboard.press('Space');assert.equal(await story.evaluate(e=>e.open),false);
 await summary.click();assert.equal(await story.evaluate(e=>e.open),true);await summary.click();assert.equal(await story.evaluate(e=>e.open),false);
 // Product imagery no longer opens a separate dialog.
 await page.locator('#catalog-grid .product-image').first().click();assert.equal(await page.locator('#dialog').evaluate(e=>e.open),false);
 // RF1650-8: accents and curly apostrophes are folded in both the search term and the product text.
 const q=async t=>{await page.locator('#product-search').fill(t);return page.evaluate(()=>({n:filteredProducts().length,ids:filteredProducts().map(p=>p.id).sort(),cards:document.querySelectorAll('#catalog-grid article').length,names:[...document.querySelectorAll('#catalog-grid article h3')].map(e=>e.textContent)}))};
 for(const [t,want] of [['jalapenos','Jalape\u00f1os'],['JALAPE\u00d1OS','Jalape\u00f1os'],['chevre','Ch\u00e8vre'],['montana','Monta\u00f1a']]){const r=await q(t);assert.ok(r.cards>0&&r.names.some(n=>n.includes(want)),t);}
 const lion=await page.evaluate(()=>catalog.filter(p=>/lion\u2019s mane/i.test(p.name)).map(p=>p.id).sort());assert.equal(lion.length,2);
 for(const t of ["lion's",'lion\u2019s','LION\u2018S','lion\u02bcs']){const r=await q(t);assert.deepEqual(r.ids,lion,t);assert.equal(r.cards,2,t);}
 assert.equal((await q('lions')).n,0,'lions without an apostrophe stays unmatched (pinned)');
 const ca=await page.evaluate(()=>catalog.filter(p=>producers[p.producerKey]?.place.includes('California\u2019s')).map(p=>p.id));
 if(ca.length){const r=await q("california's");assert.ok(ca.every(id=>r.ids.includes(id)),"california's");}else console.log("NOTE: no catalog product's maker is placed in California\u2019s; california's check skipped");
 await page.locator('#product-search').fill('');await page.locator('[data-filter="fruit"]').click();assert.equal(await page.locator('#catalog-grid article:not([data-category="fruit"])').count(),0);
 await page.locator('#product-search').fill('unfindablefoo');assert.equal(await page.locator('#catalog-grid article').count(),0);await page.locator('#product-search').fill('');await page.locator('[data-filter="all"]').click();
 assert.equal(await countText(),fullCount,'empty term shows the full catalog count');
 for(let i=0;i<22;i++){await page.locator('#catalog-sentinel').scrollIntoViewIfNeeded();await page.waitForTimeout(100);}
 const all=await page.locator('#catalog-grid article').count();assert.equal(all,170);
 const content=await page.evaluate(()=>{
  const cards=[...document.querySelectorAll('#catalog-grid article')],ids=cards.map(e=>e.dataset.productId);
  return {duplicates:ids.length-new Set(ids).size,missing:cards.flatMap(card=>{const p=catalog.find(p=>p.id===card.dataset.productId),m=producers[p.producerKey];const issues=[];if(card.querySelector('.food-description').textContent!==p.description)issues.push(p.id+': food');if(m&&card.querySelector('.maker-story p')?.textContent!==m.story)issues.push(p.id+': maker');if(m&&card.querySelector('.maker-story a')?.href!==m.url)issues.push(p.id+': link');return issues;})};
 });assert.equal(content.duplicates,0);assert.deepEqual(content.missing,[]);
 const productFacts=await page.evaluate(()=>({knownLocations:[...document.querySelectorAll('#catalog-grid article')].filter(c=>producers[catalog.find(p=>p.id===c.dataset.productId).producerKey]).every(c=>c.querySelector('.origin-label').textContent==='Based in '+producers[catalog.find(p=>p.id===c.dataset.productId).producerKey].place),organicLabels:[...document.querySelectorAll('#catalog-grid article')].filter(c=>c.querySelector('.food-badges')).map(c=>c.dataset.productId),allStoriesCollapsed:[...document.querySelectorAll('details.maker-story')].every(e=>!e.open)}));
 assert.equal(productFacts.knownLocations,true);assert.equal(productFacts.allStoriesCollapsed,true);assert.ok(productFacts.organicLabels.length>0);assert.equal(await page.locator('.food-badges').filter({hasText:'Central Coast'}).count(),0);
 const viewports=[];
 for(const width of [320,375,390,520,768,1024,1280,1440,1920]){
  await page.setViewportSize({width,height:900});
  const layout=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,background:getComputedStyle(document.body).backgroundColor,columns:getComputedStyle(document.querySelector('#catalog-grid')).gridTemplateColumns.split(' ').length}));assert.equal(layout.overflow,false,'Overflow '+width);assert.equal(layout.columns,width<520?1:width<=800?2:width<1180?3:4);viewports.push({width,...layout});
 }
 for(const width of [390,1440]){await page.setViewportSize({width,height:1000});await page.goto(base+'/');await page.locator('#brand-filter').selectOption('');await page.locator('#catalog-grid').evaluate(e=>e.scrollIntoView({behavior:'instant',block:'start'}));await page.waitForTimeout(250);await page.screenshot({path:out+`/catalog-inline-${width}.png`});await page.locator('#brand-filter').selectOption('Etto');await page.locator('#catalog-grid').evaluate(e=>e.scrollIntoView({behavior:'instant',block:'start'}));await page.screenshot({path:out+`/catalog-maker-${width}.png`});}
 // AVB-25: shelf, search and producer live in the address (replaceState, hash and other params untouched).
 let dialogs=0;page.on('dialog',d=>{dialogs++;d.dismiss()});
 const open=async s=>{await page.goto(base+'/'+s);await page.waitForSelector('#catalog-grid article, #catalog-sentinel')};
 const addr=()=>page.evaluate(()=>({search:location.search,hash:location.hash,href:location.href,params:Object.fromEntries(new URLSearchParams(location.search))}));
 await open('?shelf=pantry&q=jam');
 assert.equal(await page.locator('[data-filter="pantry"]').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#product-search').inputValue(),'jam');
 assert.ok(await page.locator('#catalog-grid article').count()>0);assert.equal(await page.locator('#catalog-grid article:not([data-category="pantry"])').count(),0);
 await open('?shelf=nonsense&maker=Nobody');
 assert.equal(await page.locator('[data-filter="all"]').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#brand-filter').inputValue(),'');assert.equal(await countText(),fullCount);
 await open('?shelf=constructor&q=%20%20'+'a'.repeat(100)+'&maker=Etto');
 assert.equal(await page.locator('[data-filter="all"]').getAttribute('aria-pressed'),'true');assert.equal((await page.locator('#product-search').inputValue()).length,80,'q is cut to 80 characters');assert.equal(await page.locator('#brand-filter').inputValue(),'Etto');
 await open('?q=%20%20jam%20');assert.equal(await page.locator('#product-search').inputValue(),'jam','q is trimmed');
 const hostile='<img src=x onerror=alert(1)>';await open('?q='+encodeURIComponent(hostile));await page.waitForTimeout(200);
 assert.equal(await page.locator('#product-search').inputValue(),hostile);assert.equal(await page.locator('img[src="x"]').count(),0);assert.equal(dialogs,0);
 await open('');const before=await page.evaluate(()=>history.length);
 await page.locator('#product-search').fill('jam');await page.locator('[data-filter="pantry"]').click();
 let a=await addr();assert.deepEqual(a.params,{q:'jam',shelf:'pantry'});assert.equal(await page.evaluate(()=>history.length),before,'filters add no history entries');
 await open('?q=jam#visit');await page.locator('[data-filter="fruit"]').click();a=await addr();assert.equal(a.hash,'#visit');assert.deepEqual(a.params,{q:'jam',shelf:'fruit'});
 await page.evaluate(()=>{location.hash='#newsletter'});await page.waitForTimeout(400);assert.deepEqual((await addr()).params,{q:'jam',shelf:'fruit'},'section navigation keeps the filters');
 await page.locator('#brand-filter').selectOption('Etto');a=await addr();assert.equal(a.params.maker,'Etto');assert.equal(a.hash,'#newsletter');
 await open('?utm=x&q=jam&shelf=pantry&maker=Etto');
 await page.locator('#product-search').fill('');await page.locator('[data-filter="all"]').click();await page.locator('#brand-filter').selectOption('');
 a=await addr();assert.equal(a.search,'?utm=x','an unrelated param survives');
 await open('?q=jam');await page.locator('#product-search').fill('');a=await addr();assert.equal(a.search,'');assert.ok(!a.href.includes('?'),'no query string left');
 // Typed or pasted text past 80 characters is cut in the box as well, so the box, the results and the address agree, and a reload restores the same search.
 const view=()=>page.evaluate(()=>({box:document.querySelector('#product-search').value,q:new URLSearchParams(location.search).get('q'),ids:filteredProducts().map(p=>p.id)}));
 const roundTrip=async(enter,want,label)=>{await open('');await page.locator('#product-search').focus();await enter();const live=await view();
  assert.equal(live.box,want,label+': box');assert.equal(live.q,want,label+': address');
  await page.reload();await page.waitForSelector('#catalog-grid article, #catalog-sentinel');assert.deepEqual(await view(),live,label+': reload restores the same search');return live};
 const long=await page.evaluate(()=>catalog.map(p=>`${p.name} ${p.brand} ${maker(p)?.place||''}`).find(t=>[...t].length>80&&!/\s/.test([...t][79])&&!/\s/.test(t[0])));
 if(long){const head=[...long].slice(0,80).join('');assert.ok((await roundTrip(()=>page.keyboard.type(head+' and more words'),head,'typed')).ids.length>0,'typed: the first 80 characters still find the product');}
 else{console.log('NOTE: no catalog text over 80 characters; typed check uses filler');await roundTrip(()=>page.keyboard.type('a'.repeat(90)),'a'.repeat(80),'typed');}
 await roundTrip(()=>page.keyboard.insertText('  '+'\u{1f951}'.repeat(90)),'\u{1f951}'.repeat(80),'pasted');
 // AV1322-10: each card links to itself; ?item=<id> resets the filters, loads enough cards, scrolls that card into view and focuses it.
 const shown=()=>page.evaluate(()=>{const g=[...document.querySelectorAll('#catalog-grid article')],f=document.activeElement;
  return {cards:g.length,ids:g.map(e=>e.dataset.productId),focused:f?.dataset?.productId??null,tabindex:f?.getAttribute('tabindex')??null,pressed:document.querySelector('[data-filter][aria-pressed="true"]').dataset.filter,q:$('#product-search').value,maker:$('#brand-filter').value,y:scrollY}});
 const inView=id=>page.waitForFunction(id=>{const e=[...document.querySelectorAll('#catalog-grid article')].find(a=>a.dataset.productId===id),r=e?.getBoundingClientRect();return !!r&&r.top<innerHeight/2&&r.bottom>innerHeight/2},id,{timeout:5000});
 const [first,id40,fruit]=await page.evaluate(()=>[catalog[0].id,catalog[39].id,catalog.find(p=>p.category==='fruit').id]);
 for(const [width,height] of [[390,844],[1440,900]]){await page.setViewportSize({width,height});
  await open('');assert.equal(await page.locator('#catalog-grid article').first().locator('a.card-link').getAttribute('href'),'?item='+encodeURIComponent(first)+'#market');
  assert.equal(await page.locator('#catalog-grid article a.card-link').count(),12,'one link per card');
  await open('?item='+encodeURIComponent(id40)+'#market');await inView(id40);const s=await shown();
  assert.equal(s.cards,48,'40th card: 48 shown at '+width);assert.equal(s.focused,id40,'40th card focused at '+width);assert.equal(s.tabindex,'-1');}
 await page.setViewportSize({width:390,height:844});
 await open(`?item=${encodeURIComponent(fruit)}&shelf=bread&q=zzz&maker=Etto`);await inView(fruit);let s=await shown();
 assert.deepEqual([s.focused,s.pressed,s.q,s.maker],[fruit,'all','',''],'?item wins over the filters');assert.ok(s.ids.includes(fruit));
 await open('');const plain=await shown();
 for(const v of ['nope','',encodeURIComponent(id40)+'x','a'.repeat(81)]){await open('?item='+v);await page.waitForTimeout(150);s=await shown();
  assert.deepEqual(s.ids,plain.ids,'unknown item '+v.length);assert.equal(s.focused,null);assert.equal(s.y,plain.y,'nothing scrolls');}
 await open('?item=nope&shelf=pantry&q=jam');s=await shown();assert.deepEqual([s.pressed,s.q,s.focused],['pantry','jam',null],'unknown item: URL filters apply as before');
 await open('?item='+encodeURIComponent(id40)+'&utm=x');await page.locator('[data-filter="fruit"]').click();
 assert.deepEqual((await addr()).params,{utm:'x',shelf:'fruit'},'a filter change drops item');
 await open('?item='+encodeURIComponent(id40));await page.locator('#product-search').fill('jam');assert.deepEqual((await addr()).params,{q:'jam'},'typing drops item');
 // Fixture ids: one needing encoding (&, space, ?, #) round-trips through its link; an 81-character real id is ignored.
 const odd='a&b ?#c',long81='z'.repeat(81),id41=await page.evaluate(()=>catalog[40].id);
 await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text()).replace(`"id": "${id40}"`,`"id": ${JSON.stringify(odd)}`).replace(`"id": "${id41}"`,`"id": "${long81}"`)})});
 await open('?item='+encodeURIComponent(odd));await inView(odd);s=await shown();assert.equal(s.focused,odd);
 const oddHref=await page.locator('#catalog-grid article:focus a.card-link').getAttribute('href');assert.match(oddHref,/^\?item=a%26b%20%3F%23c#market$/);
 await open('');await open(oddHref);await inView(odd);assert.equal((await shown()).focused,odd,'the encoded link opens the same card');
 await open('?item='+long81);await page.waitForTimeout(150);s=await shown();assert.deepEqual(s.ids,plain.ids,'81-character id ignored');assert.equal(s.focused,null);
 await page.unroute('**/catalog-products.js');
 await page.getByRole('button',{name:'Privacy',exact:true}).click();assert.equal(await page.locator('#dialog').evaluate(e=>e.open),true);await page.keyboard.press('Escape');
 assert.deepEqual(errors,[]);
 const result={checkedAt:new Date().toISOString(),all,duplicates:0,townSearch:count,sourceFiltersRemoved:true,introductionUpdated:true,productFacts,commerceRemoved:true,fullFoodAndMakerStoriesInline:true,makerStoriesCollapsed:true,disclosureKeyboardAndClick:true,producerLinksPreserved:true,productDialogRemoved:true,privacyDialogPreserved:true,viewports,errors};fs.writeFileSync(out+'/catalog-only-QA.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

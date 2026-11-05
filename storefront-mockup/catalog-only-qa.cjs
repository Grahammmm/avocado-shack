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
// AV1222-01: search also matches the shelf name and the Organic badge, never descriptions.
 const ids=(f)=>page.evaluate(f),sameSet=(a,b)=>JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
 const orgWant=await ids(()=>catalog.filter(p=>organic(p)||/organic/i.test(`${p.name} ${p.brand} ${maker(p)?.place||''}`)).map(p=>p.id));assert.ok(orgWant.length>3);
 for(const t of ['organic','ORGANIC','Organic'])assert.ok(sameSet((await q(t)).ids,orgWant),t+' finds exactly the badged cards');
 const shelfWant=(s,w)=>page.evaluate(([s,w])=>catalog.filter(p=>p.category===s||`${p.name} ${p.brand} ${maker(p)?.place||''}`.toLowerCase().includes(w)).map(p=>p.id),[s,w]);
 assert.ok(sameSet((await q('flowers')).ids,await shelfWant('flowers','flowers')),'flowers');
 for(const [t,s] of [['dairy & cheese','dairy'],['drinks','drinks']]){const want=await shelfWant(s,t),got=(await q(t)).ids;assert.ok(want.length&&sameSet(got,want),t);}
 for(const t of ['shelves','all shelves'])assert.equal((await q(t)).n,0,t+' matches no card');
 const descOnly=await ids(()=>{const labels=[...document.querySelectorAll('[data-filter]')].map(b=>b.textContent).join(' ');const h=p=>`${p.name} ${p.brand} ${maker(p)?.place||''} ${labels} organic`.toLowerCase();return catalog.flatMap(p=>String(p.description).toLowerCase().match(/[a-z]{6,}/g)||[]).find(w=>!catalog.some(p=>h(p).includes(w)))||''});
 assert.ok(descOnly);assert.equal((await q(descOnly)).n,0,'description-only word matches nothing');
 await page.locator('#product-search').fill('');
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
  return {duplicates:ids.length-new Set(ids).size,missing:cards.flatMap(card=>{const p=catalog.find(p=>p.id===card.dataset.productId),m=producers[p.producerKey];const issues=[];if(card.querySelector('.food-description').textContent!==p.description)issues.push(p.id+': food');if(m&&card.querySelector('.maker-story p')?.textContent!==m.story)issues.push(p.id+': maker');if(m?.url&&card.querySelector('.maker-story a')?.href!==m.url)issues.push(p.id+': link');return issues;})};
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
 await roundTrip(()=>page.keyboard.type('organic'),'organic','organic');
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
 // A slow logo must not steal focus back after a filter interaction, or block item navigation indefinitely.
 for(const change of ['shelf','search','maker',null]){
  let release;const held=new Promise(resolve=>{release=resolve});
  await page.route('**/assets/logo-header.png',async route=>{await held;await route.continue()});
  await page.goto(base+'/?item='+encodeURIComponent(first)+'#market',{waitUntil:'domcontentloaded'});
  assert.notEqual(await page.evaluate(()=>document.readyState),'complete','logo is still pending');
  if(change){
   const control=page.locator(change==='shelf'?'[data-filter="all"]':change==='search'?'#product-search':'#brand-filter');
   if(change==='shelf')await control.click();else if(change==='search')await control.fill('jam');else await control.selectOption('Etto');
   await control.focus();assert.equal((await addr()).params.item,undefined);
   await page.waitForTimeout(1300);
   assert.equal(await control.evaluate(e=>document.activeElement===e),true,change+': fallback navigation cancelled');
   release();await page.waitForLoadState('load');await page.waitForTimeout(100);
   assert.equal(await control.evaluate(e=>document.activeElement===e),true,change+': deferred navigation cancelled');
  }else{
   await page.waitForFunction(id=>document.activeElement?.dataset.productId===id,first,{timeout:3000});
   assert.notEqual(await page.evaluate(()=>document.readyState),'complete','item navigation does not wait for logo');
   release();await page.waitForLoadState('load');await inView(first);
  }
  await page.unroute('**/assets/logo-header.png');
 }
 // Fixture ids: one needing encoding (&, space, ?, #) round-trips through its link; an 81-character real id is ignored.
 const odd='a&b ?#c',long81='z'.repeat(81),id41=await page.evaluate(()=>catalog[40].id);
 await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text()).replace(`"id": "${id40}"`,`"id": ${JSON.stringify(odd)}`).replace(`"id": "${id41}"`,`"id": "${long81}"`)})});
 await open('?item='+encodeURIComponent(odd));await inView(odd);s=await shown();assert.equal(s.focused,odd);
 const oddHref=await page.locator('#catalog-grid article:focus a.card-link').getAttribute('href');assert.match(oddHref,/^\?item=a%26b%20%3F%23c#market$/);
 await open('');await open(oddHref);await inView(odd);assert.equal((await shown()).focused,odd,'the encoded link opens the same card');
 await open('?item='+long81);await page.waitForTimeout(150);s=await shown();assert.deepEqual(s.ids,plain.ids,'81-character id ignored');assert.equal(s.focused,null);
 await page.unroute('**/catalog-products.js');
 // AV1102-02: maker cross-links use active-catalog counts, not the brand filter.
 // Chromium heuristically caches the id-fixture catalog above even after unroute; start again from the real catalog.
 await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache');
 await open('');assert.equal(await page.evaluate(()=>catalog[39].id),id40,'real catalog restored after the id fixture');
 const makers=await page.evaluate(()=>{const counts=new Map();catalog.forEach(p=>counts.set(p.producerKey,(counts.get(p.producerKey)||0)+1));return [...counts].filter(([k])=>Object.hasOwn(producers,k)).map(([key,n])=>({key,n,name:producers[key].name}))});
 const multi=makers.find(m=>m.n>=2),single=makers.find(m=>m.n===1);assert.ok(multi);assert.ok(single);
 const fromUrl=k=>'?from='+encodeURIComponent(k);
 const fromState=()=>page.evaluate(()=>({n:filteredProducts().length,keys:[...document.querySelectorAll('#catalog-grid article')].map(e=>catalog.find(p=>p.id===e.dataset.productId).producerKey)}));
 for(const width of [390,1440]){
  await page.setViewportSize({width,height:900});await open('?q='+encodeURIComponent(multi.name));
  // Find the maker even when its public name differs from its brand/search text.
  await page.evaluate(k=>{activeFrom='';$('#product-search').value='';$('#brand-filter').value='';selectShelf($('[data-filter="all"]'));limit=catalog.length;renderCatalog()},multi.key);
  const button=page.locator('[data-from]').filter({hasText:`See all ${multi.n} from ${multi.name}`}).first();
  await button.locator('xpath=ancestor::details').evaluate(e=>e.open=true);
  assert.equal(await button.textContent(),`See all ${multi.n} from ${multi.name}`);
  await page.locator('#product-search').fill('');await page.locator('#brand-filter').selectOption(await page.evaluate(k=>catalog.find(p=>p.producerKey===k).brand,multi.key));
  const current=page.locator('[data-from]').filter({hasText:`See all ${multi.n} from ${multi.name}`}).first();await current.locator('xpath=ancestor::details').evaluate(e=>e.open=true);
  assert.equal(await current.evaluate(e=>e.getBoundingClientRect().right<=innerWidth),true,'maker button fits');await current.click();
  assert.equal((await addr()).params.from,multi.key);assert.equal(await page.locator('#product-search').inputValue(),'');assert.equal(await page.locator('#brand-filter').inputValue(),'');
  let f=await fromState();assert.equal(f.n,multi.n);assert.ok(f.keys.length>0&&f.keys.every(k=>k===multi.key));
  await page.reload();assert.equal((await fromState()).n,multi.n);assert.equal(await page.locator('.catalog-from').isVisible(),true);assert.match(await page.locator('.catalog-from').textContent(),new RegExp('^From '));
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'maker chip fits '+width);
  await page.locator('[data-clear-from]').click();assert.equal(await countText(),fullCount);assert.equal((await addr()).params.from,undefined);assert.equal(await page.locator('.catalog-from').isVisible(),false);
 }
 await open('');await page.evaluate(()=>{limit=catalog.length;renderCatalog()});
 assert.equal(await page.locator('[data-from]').evaluateAll((els,key)=>els.filter(e=>e.dataset.from===key).length,single.key),0,'one-product maker has no button');
 assert.equal(await page.evaluate(()=>[...document.querySelectorAll('#catalog-grid article')].filter(e=>!producers[catalog.find(p=>p.id===e.dataset.productId).producerKey]).every(e=>!e.querySelector('[data-from]'))),true,'no maker has no button');
 for(const key of ['nope',single.key,'constructor','<img src=x onerror=alert(1)>','']){await open(fromUrl(key)+'&utm=x#market');assert.equal(await countText(),fullCount);assert.equal(await page.locator('.catalog-from').isVisible(),false);assert.deepEqual((await addr()).params,{utm:'x'});assert.equal((await addr()).hash,'#market');}
 const other=await page.evaluate(k=>catalog.find(p=>!catalog.some(x=>x.producerKey===k&&x.category===p.category)).category,multi.key);
 await open(fromUrl(multi.key)+'&shelf='+other);assert.equal((await fromState()).n,0);assert.equal(await page.locator('#catalog-grid article').count(),0);assert.match(await page.locator('#catalog-sentinel').textContent(),/Nothing here/);
 await open(fromUrl(multi.key)+'&q=unfindablefoo&maker=Etto');assert.equal((await fromState()).n,0,'search and brand remain AND filters');await page.locator('[data-clear-from]').click();assert.equal(await countText(),fullCount,'clear resets the combined view');
 await open(fromUrl(multi.key)+'&item='+encodeURIComponent(id40)+'#market');await inView(id40);assert.equal((await shown()).focused,id40,'item keeps its existing precedence');assert.equal(await page.locator('.catalog-from').isVisible(),false);assert.equal((await addr()).params.from,undefined);
 // AV1102-03: the Available today filter exists only when some card carries a current word.
 await open('?avail=1&utm=x');assert.equal(await page.locator('#avail-filter').count(),0,'main catalog: no control');assert.equal(await countText(),fullCount);assert.deepEqual((await addr()).params,{utm:'x'},'main catalog: ?avail=1 removed');
 // AV1622-04: the page works the words out from raw state + check dates and today's Pacific day, so the fixture sets those.
 const pacificAgo=n=>new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles'}).format(new Date(Date.now()-n*864e5));
 const fixture=async(rows,checked=pacificAgo(0))=>{await page.unroute('**/catalog-products.js').catch(()=>{});await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text())+`;catalogFreshness.selectionCheckedOn=${JSON.stringify(checked)};${JSON.stringify(rows)}.forEach(([s,o],i)=>{catalog[i].availabilityState=s;catalog[i].availabilityCheckedOn=o});`})});await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache')};
 const W=[['yes',pacificAgo(0)],['yes',pacificAgo(0)],['limited',pacificAgo(0)],['no',pacificAgo(0)],['yes',pacificAgo(3)],['yes',pacificAgo(2)]],avail=()=>page.locator('#avail-filter');
 for(const width of [390,1440]){await page.setViewportSize({width,height:900});await fixture(W);await open('');
  assert.equal(await avail().count(),1,'fixture: control shown');assert.equal(await avail().isChecked(),false);assert.equal(await countText(),fullCount);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no overflow with the control '+width);
  await avail().check();assert.equal(await countText(),'3 selections');assert.deepEqual((await addr()).params,{avail:'1'});
  const ids=await page.evaluate(()=>filteredProducts().map(p=>p.availability).sort());assert.deepEqual(ids,['Available today','Available today','Limited']);
  await page.reload();await page.waitForSelector('#catalog-grid article');assert.equal(await avail().isChecked(),true,'reload restores');assert.equal(await countText(),'3 selections');
  const empty=await page.evaluate(()=>{const have=new Set(catalog.slice(0,3).map(p=>p.category));return [...new Set(catalog.map(p=>p.category))].find(c=>!have.has(c))});assert.ok(empty);
  await page.locator(`[data-filter="${empty}"]`).click();assert.equal(await page.locator('#catalog-grid article').count(),0);assert.match(await page.locator('#catalog-sentinel').textContent(),/Nothing here/);
  await avail().uncheck();assert.ok(await page.locator('#catalog-grid article').count()>0,'unchecking restores the shelf');assert.equal((await addr()).params.avail,undefined);
  await open('?avail=yes');assert.equal(await avail().isChecked(),false);assert.equal((await addr()).params.avail,undefined,'?avail=yes rewritten');assert.equal(await countText(),fullCount);
  await open('?avail=1&item='+encodeURIComponent(await page.evaluate(()=>catalog[4].id)));assert.equal(await avail().isChecked(),false,'?item wins over avail');assert.equal((await addr()).params.avail,undefined);
 }
 await fixture(W.slice(4));await open('?avail=1');assert.equal(await avail().count(),0,'only Last confirmed words: no control');assert.equal(await countText(),fullCount);assert.equal((await addr()).params.avail,undefined);
 // AV1622-04: an old build opened today: every check is 8 days old, so every word is "Last confirmed" and nothing passes Available today.
 await fixture(W.slice(0,4).map(([s])=>[s,pacificAgo(8)]),pacificAgo(8));await open('?avail=1');assert.equal(await avail().count(),0,'8-day-old checks: no control');assert.equal(await countText(),fullCount);assert.equal((await addr()).params.avail,undefined);
 assert.match(await page.locator('#catalog-grid article .availability').first().textContent(),/^Last confirmed /);assert.equal(await page.locator('#catalog-grid .availability',{hasText:/Available today|Limited|Sold out/}).count(),0);
 // AV1222-14: Clear filters shows for any one filter, resets all five, keeps other parameters and the hash, then focuses the search box.
 const clr=page.locator('#clear-filters'),FILTERS=['shelf=pantry','q=jam','maker=Etto','from='+multi.key];
 for(const width of [390,1440]){await page.setViewportSize({width,height:900});await open('');assert.equal(await clr.isVisible(),false,'fresh: hidden');assert.equal(await countText(),fullCount);
  for(const f of FILTERS){await open('?'+f+'&utm=x#catalog');assert.equal(await clr.isVisible(),true,f);await clr.click();assert.equal(await countText(),fullCount,f);assert.deepEqual((await addr()).params,{utm:'x'},f);assert.equal((await addr()).hash,'#catalog');assert.equal(await page.evaluate(()=>document.activeElement.id),'product-search');assert.equal(await clr.isVisible(),false);}
  await open('?q=unfindablefoo');assert.match(await page.locator('#catalog-sentinel').textContent(),/Nothing here/);assert.equal(await clr.isVisible(),true);await clr.click();assert.equal(await countText(),fullCount);
  await open('?q=%20%20%20');assert.equal(await clr.isVisible(),false,'spaces are not a filter');
  await open('?shelf=pantry&q=jam');await page.locator('#product-search').focus();await page.keyboard.press('Tab');await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'clear-filters','Tab reaches it');await page.keyboard.press('Enter');assert.equal(await countText(),fullCount);assert.equal(await page.locator('#brand-filter').inputValue(),'');assert.equal(await page.locator('[data-filter="all"]').getAttribute('aria-pressed'),'true');
  await open('?q=jam');const bx=await clr.boundingBox();assert.ok(bx.height>=44,'tap target '+width);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no overflow '+width);}
 await fixture(W);await open('?avail=1');assert.equal(await clr.isVisible(),true,'avail');await clr.click();assert.equal(await avail().isChecked(),false);assert.equal(await countText(),fullCount);assert.equal((await addr()).params.avail,undefined);
// AV1052-02: a shelf with no product in the published catalog is hidden (really invisible, out of the Tab order); All shelves always shows.
 const shelfFix=async(drop,after='')=>{await page.unroute('**/catalog-products.js').catch(()=>{});await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text())+`;for(let i=catalog.length;i--;)if(${JSON.stringify(drop)}.includes(catalog[i].category))catalog.splice(i,1);${after}`})});await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache')};
 const shelves=()=>page.evaluate(()=>Object.fromEntries([...document.querySelectorAll('[data-filter]')].map(b=>[b.dataset.filter,{shown:b.getBoundingClientRect().width>0,pressed:b.getAttribute('aria-pressed')}])));
 const ALL9=['all','fruit','vegetables','dairy','eggs','meat','pantry','drinks','bread','flowers'];
 await page.setViewportSize({width:390,height:844});await open('');let sh=await shelves();assert.deepEqual(Object.keys(sh).filter(k=>sh[k].shown),ALL9,'every shelf has a product: all buttons show');
 const perShelf=await page.evaluate(()=>{const o={};catalog.forEach(p=>o[p.category]=(o[p.category]||0)+1);return o}),total=Object.values(perShelf).reduce((a,b)=>a+b,0);
 for(const width of [390,1440]){await page.setViewportSize({width,height:900});
  for(const drop of [['flowers'],['eggs'],['eggs','flowers']]){await shelfFix(drop);
   await open('?shelf=flowers&utm=synthetic#market');
   sh=await shelves();assert.deepEqual(Object.keys(sh).filter(k=>sh[k].shown),ALL9.filter(k=>!drop.includes(k)),'only the empty shelves vanish: '+drop);
   assert.equal(await page.locator('[data-filter="flowers"]').count(),1,'node kept');assert.equal(await page.getByRole('button',{name:'Flowers',exact:true}).count(),drop.includes('flowers')?0:1,'role query agrees');
   if(drop.includes('flowers')){assert.equal(sh.all.pressed,'true');assert.equal(Object.values(sh).filter(v=>v.pressed==='true').length,1);assert.equal(await countText(),(total-drop.reduce((n,d)=>n+perShelf[d],0))+' selections','falls back to All shelves');assert.deepEqual((await addr()).params,{utm:'synthetic'},'only shelf dropped');assert.equal((await addr()).hash,'#market');}
   await open('?shelf=eggs&q=a&utm=x');assert.equal((await addr()).params.shelf,drop.includes('eggs')?undefined:'eggs');if(drop.includes('eggs'))assert.deepEqual((await addr()).params,{q:'a',utm:'x'});
   await open('');await page.locator('[data-filter="pantry"]').click();await page.locator('[data-filter="all"]').click();assert.equal((await shelves()).all.pressed,'true');
   const tabbed=[];await page.locator('[data-filter="all"]').focus();for(let i=0;i<10;i++){const f=await page.evaluate(()=>document.activeElement.dataset.filter||'');if(f)tabbed.push(f);await page.keyboard.press('Tab');}
   assert.ok(drop.every(d=>!tabbed.includes(d)),'Tab skips hidden shelves '+drop);assert.deepEqual(tabbed,ALL9.filter(k=>!drop.includes(k)),'Tab visits exactly the visible shelves in order');
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no overflow');}
 }
 // Other filters and ?item survive the cleanup; an unknown shelf keeps today's behaviour; the shelf rewrite does not break invalid-from cleanup.
 await shelfFix(['flowers']);
 await open('?shelf=flowers&q=a&maker=Etto&from=nope&avail=1&utm=x#market');a=await addr();assert.deepEqual(a.params,{q:'a',maker:'Etto',utm:'x'});assert.equal(a.hash,'#market');assert.equal(await page.locator('#product-search').inputValue(),'a');assert.equal(await page.locator('#brand-filter').inputValue(),'Etto');
 const histLen=await page.evaluate(()=>history.length);await open('?shelf=flowers');assert.ok((await page.evaluate(()=>history.length))<=histLen+1,'no extra history');
 await open('?item='+encodeURIComponent(id41)+'&shelf=flowers&utm=x');s=await shown();assert.equal(s.pressed,'all');assert.equal(s.focused,null===s.focused?null:id41);assert.deepEqual((await addr()).params,{item:id41,utm:'x'},'valid item kept, empty shelf dropped');
 await open('?item=nope&shelf=flowers&q=jam');s=await shown();assert.deepEqual([s.pressed,s.q,s.focused],['all','jam',null]);
 await open('?shelf=nonsense&shelf=constructor');assert.equal((await shelves()).all.pressed,'true');
 // A populated shelf is never hidden because of the current search, and sold-out products keep their shelf.
 await shelfFix(['flowers'],`catalog.filter(p=>p.category==='eggs').forEach(p=>p.availability='Sold out');`);await open('?q=unfindablefoo');sh=await shelves();assert.equal(sh.pantry.shown,true);assert.equal(sh.eggs.shown,true,'sold-out-only shelf stays');assert.equal(sh.flowers.shown,false);
 await page.locator('#product-search').fill('');await page.locator('[data-filter="fruit"]').click();sh=await shelves();assert.equal(sh.pantry.shown,true);assert.equal(sh.flowers.shown,false,'no dynamic unhide');
 // Empty catalog: only All shows, selected, with the existing empty message; a restored product brings its shelf back on reload.
 await shelfFix(ALL9.slice(1));await open('?shelf=fruit');sh=await shelves();assert.deepEqual(Object.keys(sh).filter(k=>sh[k].shown),['all']);assert.equal(sh.all.pressed,'true');assert.equal(await countText(),'0 selections');assert.match(await page.locator('#catalog-sentinel').textContent(),/Nothing here/);
 await page.unroute('**/catalog-products.js');await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache');await open('?shelf=flowers');sh=await shelves();assert.equal(sh.flowers.shown,true);assert.equal(sh.flowers.pressed,'true','reload with the product restores the shelf');
 await page.unroute('**/catalog-products.js');await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache');await page.setViewportSize({width:390,height:844});
 // AV1352-01: one illustration note and an alt suffix while any active card is not an owner photo.
 const NOTE='Some product pictures are illustrations made from photos of our shelves, so a label or package in the store may look different.';
 const noteState=()=>page.evaluate(()=>({notes:[...document.querySelectorAll('p.catalog-note')].map(e=>e.textContent),next:document.querySelector('.catalog-controls').previousElementSibling.textContent,alts:[...document.querySelectorAll('#catalog-grid img')].map(i=>i.alt),names:[...document.querySelectorAll('#catalog-grid article')].map(a=>catalog.find(p=>p.id===a.dataset.productId).name)}));
 const imageFixture=async js=>{await page.unroute('**/catalog-products.js').catch(()=>{});await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text())+';'+js})});await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache')};
 await open('');let ns=await noteState();assert.equal(ns.notes.length,3,'real catalog: two notes plus the illustration note');assert.equal(ns.notes[2],NOTE);assert.equal(ns.next,NOTE,'note sits last, right before the controls');
 assert.ok(ns.alts.length>0&&ns.alts.every(a=>a.endsWith(' (illustration)')&&!a.endsWith(' (illustration) (illustration)')),'every generated picture is flagged');
 await page.locator('#product-search').fill('Cambria');ns=await noteState();assert.equal(ns.notes.length,3,'a filter does not add or remove the note');await page.locator('#product-search').fill('');
 await imageFixture(`catalog.forEach((p,i)=>{p.image='assets/products/photo-0123456789abcdef.'+(i%2?'jpg':'png');if(i===0)p.imageAlt='Owner photo alt'});`);await open('');ns=await noteState();
 assert.equal(ns.notes.length,2,'all owner photos: no illustration note');assert.ok(!ns.notes.includes(NOTE));assert.equal(ns.alts[0],'Owner photo alt');assert.equal(ns.alts[1],ns.names[1],'owner photo keeps its plain alt');
 await imageFixture(`catalog.forEach((p,i)=>{p.image=i===1?'assets/products/photo-0123456789abcdef.jpg':i===2?'assets/products/photo-0123456789ABCDEF.jpg':i===3?'assets/products/photo-0123456789abcdef.jpg\\n':i===4?'assets/products/photo-0123456789abcdef.jpeg':'assets/products/photo-0123456789abcdef.png'});`);await open('');ns=await noteState();
 assert.deepEqual([ns.notes.length,ns.notes[2]],[3,NOTE],'mixed: note shown');assert.deepEqual(ns.alts.slice(0,6).map((a,i)=>a.endsWith(' (illustration)')),[false,false,true,true,true,false],'only the exact installed form is exempt');
 await imageFixture(`catalog.forEach((p,i)=>{p.image=i===0?'assets/products/a.webp':'assets/products/photo-0123456789abcdef.jpg'});`);await open('');ns=await noteState();const ownerName=ns.names[5];
 await page.locator('#product-search').fill(ownerName);ns=await noteState();assert.ok(ns.alts.length>0&&ns.alts.every(a=>!a.endsWith(' (illustration)')),'filtered to owner photos only');assert.equal(ns.notes.length,3,'mixed: note persists when the view shows only owner photos');
 await imageFixture(`catalog.length=0;`);await open('');ns=await noteState();assert.equal(ns.notes.length,2,'empty catalog: no illustration note');
 await page.getByRole('button',{name:'Privacy',exact:true}).click();assert.equal(await page.locator('#dialog').evaluate(e=>e.open),true);await page.keyboard.press('Escape');
 assert.deepEqual(errors,[]);
 const result={checkedAt:new Date().toISOString(),all,duplicates:0,townSearch:count,sourceFiltersRemoved:true,introductionUpdated:true,productFacts,commerceRemoved:true,fullFoodAndMakerStoriesInline:true,makerStoriesCollapsed:true,disclosureKeyboardAndClick:true,producerLinksPreserved:true,productDialogRemoved:true,privacyDialogPreserved:true,viewports,errors};fs.writeFileSync(out+'/catalog-only-QA.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

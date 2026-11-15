const {out,base}=require('./qa-env.cjs').qaEnv({preview:true});
const fs=require('fs'),assert=require('assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/?view=all');
 assert.equal(await page.locator('.section-intro').textContent(),'An avocado from Morro Bay. A loaf from Atascadero. Cheese made in Cambria. Explore our selection and follow the flavors back to the farms, kitchens, and makers from our community.');
 assert.equal(await page.locator('[data-source],.sourcing-filters').count(),0);
 assert.equal(await page.locator('[data-add],#bag,#boxes,#merch,#owner,#order-preview,.price,[data-product],.food-detail,#hikes').count(),0);
 assert.doesNotMatch(await page.locator('body').innerText(),/\$\d|add to basket|pickup|local delivery|weekly boxes|online shop|merchandise|Discover this food|Food & maker story/i);
 const countText=async()=>(await page.locator('#catalog-count').textContent()).split(' \u00b7 ')[0],fullCount=await countText();assert.equal(fullCount,(await page.evaluate(()=>catalog.length))+' selections');
 const defaultCount=(await page.evaluate(()=>catalog.filter(p=>!['fruit','vegetables','flowers'].includes(p.category)||p.id==='photo-product-018').length))+' selections';
 // AV1052-01: description search on synthetic catalogs (served for catalog-products.js and producers.js only; no file on disk changes). Expected ids are written out, not read from filteredProducts().
 const descriptionSearchChecks=[];
 {
  const IMG='assets/products/photo-product-001.webp',dAgo=n=>{const d=new Date(new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles'}).format(new Date())+'T00:00:00Z');d.setUTCDate(d.getUTCDate()-n);return d.toISOString().slice(0,10)};
  const P=(id,name,o={})=>({id,name,brand:'Acme',category:'pantry',image:IMG,description:'Plain.',producerKey:null,...o});
  const PRODUCERS={GoatRock:{name:'Rock Dairy',place:'Goat Rock, California'},Straus:{name:'Straus',place:'Marshall, California'},ZF:{name:'Zed Farm',place:'Zorbville, California'}};
  const dropRoutes=async()=>{for(const f of ['catalog-products','producers'])await page.unroute(`**/${f}.js`).catch(()=>{});await page.unroute('**/assets/logo-header.png').catch(()=>{});await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache')};
  const serve=async(prods,fresh=null)=>{await dropRoutes();
   await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text())+`;catalog.length=0;catalog.push(...${JSON.stringify(prods)});${fresh?`catalogFreshness.selectionCheckedOn=${JSON.stringify(fresh)};`:''}`})});
   await page.route('**/producers.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text())+`;Object.assign(producers,${JSON.stringify(PRODUCERS)});`})})};
  const go=async qs=>{await page.goto(base+'/'+qs);await page.waitForSelector('#catalog-grid article, #catalog-sentinel')};
  const st=()=>page.evaluate(()=>({box:$('#product-search').value,q:new URLSearchParams(location.search).get('q'),order:filteredProducts().map(p=>p.id),cards:[...document.querySelectorAll('#catalog-grid article')].map(a=>a.dataset.productId),count:$('#catalog-count').textContent,visible:visibleCount}));
  const params=()=>page.evaluate(()=>{const o=Object.fromEntries(new URLSearchParams(location.search));delete o.view;return {params:o,hash:location.hash}});
  const same=(a,b)=>require('util').isDeepStrictEqual(a,b);
  const search=async(t,want,label)=>{await page.locator('#product-search').fill(t);const s=await st();
   assert.ok(same(s.order,want),`${label}: '${t}' wants ${want.join(',')} got ${s.order.join(',')}`);assert.ok(same(s.cards,want.slice(0,12)),`${label}: '${t}' draws the same cards in the same order`);
   assert.equal(s.count,`${want.length} selections · ${Math.min(12,want.length)} shown`,`${label}: '${t}' count line`);return s};
  // Source order interleaves description-only (s01, s05, s10), metadata-only (s02 name, s06 brand, s07 town, s08 shelf, s09 badge), both (s03) and neither (s04).
  const F1=[P('s01','Plain Loaf',{category:'bread',description:'Made with goat milk and honey.'}),P('s02','Goat Cheese',{category:'dairy',description:'Fresh and mild.'}),P('s03','Honey Goat Jar',{description:'Goat honey, gluten free.'}),P('s04','Rye',{category:'bread',description:'Seeded.'}),
   P('s05','Oat Bar',{description:'Sweet with Goat milk caramel.'}),P('s06','Butter',{brand:'Goatsbeard Farm',category:'dairy',description:'Cultured.'}),P('s07','Soap',{producerKey:'GoatRock',description:'Lavender.'}),P('s08','Cold Brew',{category:'drinks',description:'Smooth.'}),
   P('s09','Plain Milk',{category:'dairy',producerKey:'Straus',description:'Raw whole milk.'}),P('s10','Flour',{description:'Gluten-free flour mix.'})];
  const F1ALL=F1.map(p=>p.id);
  const checks={
   descriptionSearchTiers:async()=>{await serve(F1);await go('?view=all');const before=await page.evaluate(()=>JSON.stringify(catalog));
    await search('goat',['s02','s03','s06','s07','s01','s05'],'name, both, brand and town first; description-only after, each in source order');
    await search('honey',['s03','s01'],'a card in both groups appears once, in the first');
    await search('gluten',['s03','s10'],'description-only');
    await search('goatsbeard',['s06'],'brand');await search('goat rock',['s07'],'town');await search('drinks',['s08'],'shelf');await search('dairy',['s02','s06','s09'],'shelf');await search('organic',['s09'],'badge');
    await search('organic raw',[],'no match across the badge and the description');await search('coffee smooth',[],'no match across the shelf and the description');await search('zzzz',[],'unmatched');
    await search('',F1ALL,'empty term');await search('   ',F1ALL,'blank term');
    assert.ok(same(await page.evaluate(()=>JSON.stringify(catalog)),before),'the catalog records are unchanged');
    assert.ok(same(await page.evaluate(()=>catalog.map(p=>p.id)),F1ALL),'the catalog order is unchanged');
    await dropRoutes();await go('?view=all');const base0=await page.evaluate(()=>catalog.map(p=>p.id));
    for(const t of ['goat','honey','gluten']){const meta=await page.evaluate(t=>catalog.filter(p=>`${p.name} ${p.brand} ${maker(p)?.place||''}`.toLowerCase().includes(t)).map(p=>p.id),t),desc=await page.evaluate(([t,m])=>catalog.filter(p=>!m.includes(p.id)&&p.description.toLowerCase().includes(t)).map(p=>p.id),[t,meta]);
     if(t!=='gluten')assert.ok(desc.length>0,t+' has description-only cards in the real catalog');
     const want=[...base0.filter(i=>meta.includes(i)),...base0.filter(i=>desc.includes(i))];await page.locator('#product-search').fill(t);const s=await st();assert.ok(same(s.order,want),'real catalog '+t);}
    await page.locator('#product-search').fill('');},
   descriptionSearchFoldAndCap:async()=>{const A='\u{1f951}',dlg=[];const onDialog=d=>{dlg.push(d.message());d.dismiss()};page.on('dialog',onDialog);
    const F2=[P('f01','Log',{category:'dairy',description:'Tangy Ch\u00e8vre rounds, GOAT milk.'}),P('f02','Loaf',{category:'bread',description:'Baker\u2019s sourdough.'}),P('f03','Roll',{category:'bread',description:"Baker's glaze."}),(()=>{const p=P('f04','Mystery');delete p.description;return p})(),P('f05','Blank',{description:''}),
     P('f06','Pit',{description:A.repeat(80)+'z'}),P('f07','Stone',{description:A.repeat(79)+'q'}),P('f08','Glaze',{description:'<img src=x onerror=alert(1)> glaze'}),P('f09','Granola',{description:'Honey, gluten-free and GLUTEN safe.'})],ALL=F2.map(p=>p.id);
    try{await serve(F2);await go('?view=all');
     for(const t of ['chevre','CHEVRE','Ch\u00e8vre','CH\u00c8VRE'])await search(t,['f01'],'accents and case fold');await search('goat',['f01'],'case');
     for(const t of ["baker's",'baker\u2019s','BAKER\u2018S','baker\u02bcs'])await search(t,['f02','f03'],'straight and curly apostrophes fold alike');await search('bakers',[],'no apostrophe stays unmatched');
     for(const t of ['gluten','GLUTEN','Gluten-Free'])await search(t,['f09'],'case');await search('honey',['f09'],'honey');
     await search('undefined',[],'an absent description is searchable as nothing');await search('null',[],'an absent description is searchable as nothing');
     await search('',ALL,'empty term');await search('  \t ',ALL,'blank term');assert.equal(await page.locator('[data-product-id="f04"] .food-description').textContent(),'');
     await search('zzz',[],'unmatched');
     // The 80 code point limit: the box, the results and the address agree; typed, pasted and ?q= give one result.
     const live=async enter=>{await go('?view=all');await page.locator('#product-search').focus();await enter();return st()};
     const typed=await live(()=>page.keyboard.insertText(A.repeat(80)+'y'));
     assert.equal([...typed.box].length,80,'box cut to 80 code points');assert.equal(typed.q,A.repeat(80));assert.ok(same(typed.order,['f06']),'the 81st code point is ignored');
     await page.reload();await page.waitForSelector('#catalog-grid article, #catalog-sentinel');assert.ok(same(await st(),typed),'reload restores the same search');
     await go('?view=all&q='+encodeURIComponent(A.repeat(100)));{const r=await st();assert.ok(same([r.box,r.order,r.cards,r.count],[typed.box,typed.order,typed.cards,typed.count]),'?q= and typed text agree');}
     const exact=await live(()=>page.keyboard.insertText(A.repeat(79)+'q'));assert.equal([...exact.box].length,80);assert.ok(same(exact.order,['f07']),'exactly 80 code points is kept whole');
     await go('?view=all&q='+encodeURIComponent(A.repeat(79)+'q'));assert.ok(same(await st(),exact),'?q= with 80 code points agrees');
     // Hostile text is data: nothing is drawn as markup and no dialog opens.
     await go('?view=all');await search('onerror',['f08'],'hostile description');
     assert.equal(await page.locator('#catalog-grid img[src="x"]').count(),0);assert.equal(await page.locator('[data-product-id="f08"] .food-description').textContent(),'<img src=x onerror=alert(1)> glaze');
     await go('?view=all&q='+encodeURIComponent('<img src=x onerror=alert(1)>'));await page.waitForTimeout(150);assert.ok(same((await st()).order,['f08']),'hostile ?q= matches the description as text');assert.equal(await page.locator('#catalog-grid img[src="x"]').count(),0);
     assert.equal(dlg.length,0,'no dialog: '+dlg.join('|'));
    }finally{page.off('dialog',onDialog)}},
   descriptionSearchKeepsNewOrder:async()=>{const N=(id,name,ago,o={})=>P(id,name,{...(ago===null?{}:{addedOn:dAgo(ago)}),...o});
    // Source order: o1 old/name, nd1 New 3 days/description, nm1 + nm2 New 1 day/name (tie), nd2 New today/description, od1 old/description, om1 old/name.
    const F3=[N('o1','Goat Soap',null),N('nd1','Plain Jar',3,{description:'Goat milk.'}),N('nm1','Goat Fudge',1),N('nm2','Goat Butter',1),N('nd2','Plain Tin',0,{description:'Goat milk.'}),N('od1','Plain Pot',null,{description:'Goat milk.'}),N('om1','Goat Lotion',null)];
    await serve(F3);await go('?view=all');const before=await page.evaluate(()=>JSON.stringify(catalog)),src=await page.evaluate(()=>catalog.map(p=>p.id));
    await search('',['nd2','nm1','nm2','nd1','o1','od1','om1'],'New first, newest first, ties in source order');
    await search('goat',['nm1','nm2','o1','om1','nd2','nd1','od1'],'older metadata hits come before New description-only hits; New first inside each group');
    await search('milk',['nd2','nd1','od1'],'description-only group keeps New first');await search('lotion',['om1'],'metadata');
    assert.ok(same(await page.evaluate(()=>catalog.map(p=>p.id)),src),'the source array order is unchanged');assert.ok(same(await page.evaluate(()=>JSON.stringify(catalog)),before),'the records are unchanged');
    await go('?view=all&q=goat');assert.ok(same((await st()).order,['nm1','nm2','o1','om1','nd2','nd1','od1']),'?q= restores the same two groups');
    await page.locator('#product-search').fill('goat');assert.ok(same((await st()).cards,['nm1','nm2','o1','om1','nd2','nd1','od1']),'drawn in the same order');},
   descriptionSearchFiltersAndPaging:async()=>{const T=dAgo(0),G=[];
    for(let i=0;i<60;i++){const k=i%4;G.push(P('g'+String(i).padStart(2,'0'),k===0?`Honey item ${i}`:`Plain item ${i}`,{brand:i%2?'Acme':'Bolt',category:['pantry','dairy','bread'][i%3],producerKey:i%5===0?'ZF':null,description:k===3?'Salty.':`Sweet honey ${i}.`,availabilityState:i%7<3?'yes':'no',availabilityCheckedOn:T}))}
    const want=(f={})=>{const rows=G.filter(p=>(!f.shelf||p.category===f.shelf)&&(!f.brand||p.brand===f.brand)&&(!f.from||p.producerKey===f.from)&&(!f.avail||p.availabilityState==='yes'));
     return [...rows.filter(p=>p.name.toLowerCase().includes('honey')),...rows.filter(p=>!p.name.toLowerCase().includes('honey')&&p.description.toLowerCase().includes('honey'))].map(p=>p.id)};
    await serve(G,T);
    const cases=[{},{shelf:'pantry'},{brand:'Acme'},{from:'ZF'},{avail:true},{shelf:'dairy',brand:'Bolt',avail:true},{shelf:'bread',brand:'Acme',from:'ZF',avail:true}];
    assert.ok(want().length>24,'fixture: more than two pages across both groups');assert.ok(cases.some(f=>want(f).length===0)&&cases.some(f=>want(f).length>0),'fixture: a combined filter with no match, and some with matches');
    for(const f of cases){const w=want(f),label=JSON.stringify(f);
     await go('?view=all'+(f.from?'&from='+f.from:''));if(f.shelf)await page.locator(`[data-filter="${f.shelf}"]`).click();if(f.brand)await page.locator('#brand-filter').selectOption(f.brand);if(f.avail)await page.locator('#avail-filter').check();
     await page.locator('#product-search').fill('honey');let s=await st();
     assert.ok(same(s.order,w),label+': both groups, filters applied');assert.ok(same(s.cards,w.slice(0,12)),label+': first page');assert.equal(s.count,`${w.length} selections · ${Math.min(12,w.length)} shown`,label+': count line');
     while(s.visible<w.length){await page.evaluate(()=>loadMore());s=await st();assert.ok(same(s.cards,w.slice(0,s.visible)),label+': each page continues the same order');}
     assert.equal(new Set(s.cards).size,s.cards.length,label+': no duplicates');assert.ok(same(s.cards,w),label+': no gaps');assert.equal(s.count,`${w.length} selections · ${w.length} shown`,label+': all shown');
     await page.locator('#product-search').fill('zzz');s=await st();assert.equal(s.count,'0 selections · 0 shown');assert.equal(s.cards.length,0);
     await page.locator('#product-search').fill('honey');s=await st();assert.ok(same(s.cards,w.slice(0,12)),label+': a new search starts again at the first page');}},
   descriptionSearchRestoreAndItem:async()=>{await serve(F1);const GOAT=['s02','s03','s06','s07','s01','s05'];
    for(const width of [390,1440]){await page.setViewportSize({width,height:900});
     await go('?utm=x&q=goat&view=all#market');let s=await st();assert.equal(s.box,'goat');assert.ok(same(s.order,GOAT)&&same(s.cards,GOAT),width+': ?q= restores the two groups');
     assert.ok(same(await params(),{params:{utm:'x',q:'goat'},hash:'#market'}),'unrelated params and hash untouched');
     await page.reload();await page.waitForSelector('#catalog-grid article');assert.ok(same((await st()).cards,GOAT),'reload keeps the order');
     await page.locator('#product-search').fill('honey');assert.ok(same(await params(),{params:{utm:'x',q:'honey'},hash:'#market'}));assert.ok(same((await st()).cards,['s03','s01']));
     // A valid item wins over the search, exactly as before; an invalid one leaves the two-group search.
     await go('?item=s05&q=goat&view=all');await page.waitForFunction(()=>document.activeElement?.dataset?.productId==='s05',null,{timeout:5000});s=await st();assert.equal(s.box,'','a valid item clears the search');assert.ok(same(s.cards,F1ALL));
     await go('?item=nope&q=goat&view=all');s=await st();assert.ok(same(s.cards,GOAT),'an unknown item leaves the two-group search');assert.equal(await page.locator('#catalog-item-status').isVisible(),true);
     // A filter edit before the page finishes loading cancels the pending item focus.
     let release;const held=new Promise(r=>{release=r});await page.route('**/assets/logo-header.png',async route=>{await held;await route.continue()});
     await page.goto(base+'/?item=s05&view=all#market',{waitUntil:'domcontentloaded'});await page.locator('#product-search').fill('goat');release();await page.waitForLoadState('load');await page.waitForTimeout(300);
     s=await st();assert.ok(same(s.order,GOAT),'typing after an item link searches both groups');assert.equal(await page.evaluate(()=>document.activeElement?.dataset?.productId??null),null,'no deferred focus');assert.equal((await params()).params.item,undefined);
     await page.unroute('**/assets/logo-header.png');}}
  };
  try{for(const [name,check] of Object.entries(checks)){await check();descriptionSearchChecks.push(name)}}finally{await dropRoutes()}
  await page.setViewportSize({width:390,height:844});await go('?view=all');assert.equal(await countText(),fullCount,'real catalog restored after the description search fixtures');
 }
 await page.locator('#product-search').fill('Cambria');const count=await page.locator('#catalog-grid article').count();assert.ok(count>0);
 {const cam=await page.evaluate(()=>catalog.filter(p=>maker(p)?.place.includes('Cambria')).length),labels=await page.locator('#catalog-grid .origin-label').allTextContents();
  assert.ok(cam>0&&labels.slice(0,cam).every(t=>t.includes('Cambria')),'every Cambria card comes first');
  assert.ok(await page.evaluate(()=>[...document.querySelectorAll('#catalog-grid article')].slice(catalog.filter(p=>maker(p)?.place.includes('Cambria')).length).every(a=>fold(catalog.find(p=>p.id===a.dataset.productId).description).includes('cambria'))),'any card after them is there for its description');}
 assert.ok(await page.locator('#catalog-grid .maker-story a[href^="https://"]').count());
 const story=page.locator('#catalog-grid details.maker-story').first(),summary=story.locator('summary');
 assert.equal(await story.evaluate(e=>e.open),false);assert.equal(await story.locator('p').isVisible(),false);
 await summary.focus();await page.keyboard.press('Enter');assert.equal(await story.evaluate(e=>e.open),true);assert.equal(await story.locator('p').isVisible(),true);
 await page.keyboard.press('Space');assert.equal(await story.evaluate(e=>e.open),false);
 await summary.click();assert.equal(await story.evaluate(e=>e.open),true);await summary.click();assert.equal(await story.evaluate(e=>e.open),false);
 // Product imagery no longer opens a separate dialog.
 await page.locator('#catalog-grid .product-image').first().click();assert.equal(await page.locator('#dialog').evaluate(e=>e.open),false);
 // RF1650-8: accents and curly apostrophes are folded in both the search term and the product text.
 const q=async t=>{await page.locator('#product-search').fill(t);return page.evaluate(()=>({n:filteredProducts().length,ids:filteredProducts().map(p=>p.id).sort(),cards:document.querySelectorAll('#catalog-grid article').length,names:[...document.querySelectorAll('#catalog-grid article h3')].map(e=>e.textContent),order:filteredProducts().map(p=>p.id)}))};
 for(const [t,want] of [['jalapenos','Jalape\u00f1os'],['JALAPE\u00d1OS','Jalape\u00f1os'],['chevre','Ch\u00e8vre'],['montana','Monta\u00f1a']]){const r=await q(t);assert.ok(r.cards>0&&r.names.some(n=>n.includes(want)),t);}
// AV1222-01: search matches the shelf name and the Organic badge; AV1052-01: and descriptions, but only after every card whose own words match.
 const ids=(f)=>page.evaluate(f),sameSet=(a,b)=>JSON.stringify([...a].sort())===JSON.stringify([...b].sort());
 // The first tier is exactly the cards whose name, brand, town, shelf or badge match (meta); the second is exactly the other cards whose description says it.
 const tiered=async(t,meta,label)=>{const r=await q(t),n=meta.length,extra=await page.evaluate(([t,meta])=>catalog.filter(p=>!meta.includes(p.id)&&fold(p.description).includes(fold(t))).map(p=>p.id),[t,meta]);
  assert.ok(sameSet(r.order.slice(0,n),meta),label+': metadata hits come first');assert.ok(sameSet(r.order.slice(n),extra),label+': then exactly the description-only cards');assert.equal(r.cards,Math.min(12,r.order.length),label+': drawn cards');return r};
 const orgWant=await ids(()=>catalog.filter(p=>organic(p)||/organic/i.test(`${p.name} ${p.brand} ${maker(p)?.place||''}`)).map(p=>p.id));assert.ok(orgWant.length>3);
 for(const t of ['organic','ORGANIC','Organic'])await tiered(t,orgWant,t+' finds the badged cards');
 const shelfWant=(s,w)=>page.evaluate(([s,w])=>catalog.filter(p=>p.category===s||`${p.name} ${p.brand} ${maker(p)?.place||''}`.toLowerCase().includes(w)).map(p=>p.id),[s,w]);
 await tiered('flowers',await shelfWant('flowers','flowers'),'flowers');
 for(const [t,s] of [['dairy & cheese','dairy'],['drinks','drinks']]){const want=await shelfWant(s,t);assert.ok(want.length,t);await tiered(t,want,t);}
 for(const t of ['shelves','all shelves'])assert.equal((await q(t)).n,0,t+' matches no card');
 const descOnly=await ids(()=>{const labels=[...document.querySelectorAll('[data-filter]')].map(b=>b.textContent).join(' ');const h=p=>`${p.name} ${p.brand} ${maker(p)?.place||''} ${labels} organic`.toLowerCase();return catalog.flatMap(p=>String(p.description).toLowerCase().match(/[a-z]{6,}/g)||[]).find(w=>!catalog.some(p=>h(p).includes(w)))||''});
 assert.ok(descOnly);{const want=await page.evaluate(w=>catalog.filter(p=>fold(p.description).includes(w)).map(p=>p.id),descOnly),r=await q(descOnly);assert.ok(want.length>0&&sameSet(r.order,want)&&r.cards>0,'a word only in descriptions finds exactly those cards');}
 await page.locator('#product-search').fill('');
 const lion=await page.evaluate(()=>catalog.filter(p=>/lion\u2019s mane/i.test(p.name)).map(p=>p.id).sort());assert.equal(lion.length,2);
 for(const t of ["lion's",'lion\u2019s','LION\u2018S','lion\u02bcs']){const r=await tiered(t,lion,t);assert.ok(sameSet(r.order.slice(0,2),lion),t);}
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
  return {duplicates:ids.length-new Set(ids).size,missing:cards.flatMap(card=>{const p=catalog.find(p=>p.id===card.dataset.productId),m=producers[p.producerKey];const issues=[];if(card.querySelector('.food-description').textContent!==p.description)issues.push(p.id+': food');if(m){const panel=card.querySelector('details.maker-story'),story=panel?.querySelector('.maker-story-content > p:not(.maker-place)'),place=panel?.querySelector('.maker-story-content > p.maker-place');/* AV0222-10: story shows the story paragraph; link only shows the place paragraph; neither shows no panel; every maker card names its maker */if(!panel!==!(m.story||m.url))issues.push(p.id+': panel');else if(panel&&(m.story?(story?.textContent!==m.story||place):(story||place?.textContent!=='Based in '+m.place)))issues.push(p.id+': maker');if(card.dataset.makerKey!==p.producerKey||card.querySelector('.food-identity .maker-name')?.textContent!==m.name)issues.push(p.id+': identity');}if(m?.url&&card.querySelector('.maker-story a')?.href!==m.url)issues.push(p.id+': link');return issues;})};
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
 // AVO-SHOP-CLEAN-1: the shop opens on packaged goods. These older checks assume the whole catalog, so open() adds view=all unless the address already names a shelf, view, maker or item (those infer their own view); addr().params leaves view out.
 const open=async s=>{const [q,h]=s.split(/(?=#)/),sp=new URLSearchParams(q.replace(/^\?/,''));if(!['shelf','view','from','item'].some(k=>sp.has(k))){sp.set('view','all');}await page.goto(base+'/'+'?'+sp.toString()+(h||''));await page.waitForSelector('#catalog-grid article, #catalog-sentinel')};
 const addr=()=>page.evaluate(()=>({search:location.search,hash:location.hash,href:location.href,params:(()=>{const o=Object.fromEntries(new URLSearchParams(location.search));delete o.view;return o})()}));
 await open('?shelf=pantry&q=jam');
 assert.equal(await page.locator('[data-filter="pantry"]').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#product-search').inputValue(),'jam');
 assert.ok(await page.locator('#catalog-grid article').count()>0);assert.equal(await page.locator('#catalog-grid article:not([data-category="pantry"])').count(),0);
 await open('?view=all&shelf=nonsense&maker=Nobody');
 assert.equal(await page.locator('[data-filter="all"]').getAttribute('aria-pressed'),'true');assert.equal(await page.locator('#brand-filter').inputValue(),'');assert.equal(await countText(),fullCount);
 await open('?view=all&shelf=constructor&q=%20%20'+'a'.repeat(100)+'&maker=Etto');
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
 await page.goto(base+'/?q=jam');await page.waitForSelector('#catalog-grid article, #catalog-sentinel');await page.locator('#product-search').fill('');a=await addr();assert.equal(a.search,'');assert.ok(!a.href.includes('?'),'no query string left');
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
 await page.goto(base+'/');await page.waitForSelector('#catalog-grid article');const plain=await shown();
 for(const v of ['nope','',encodeURIComponent(id40)+'x','a'.repeat(81)]){await open('?item='+v);await page.waitForTimeout(150);s=await shown();
  assert.deepEqual(s.ids,plain.ids,'unknown item '+v.length);assert.equal(s.focused,null);assert.equal(s.y,plain.y,'nothing scrolls');}
 await open('?item=nope&shelf=pantry&q=jam');s=await shown();assert.deepEqual([s.pressed,s.q,s.focused],['pantry','jam',null],'unknown item: URL filters apply as before');
// AV1352-02: a nonempty id of at most 80 characters that is not listed gets one neutral status line and loses ?item; empty, 81-character and known ids behave as before.
const GONE='That item is not in our catalog right now. Here is everything else.',note=()=>page.evaluate(()=>{const n=[...document.querySelectorAll('#catalog-item-status')];return {count:n.length,text:n[0]?.textContent,hidden:n[0]?.hidden,role:n[0]?.getAttribute('role'),aboveGrid:n[0]?.nextElementSibling?.id==='catalog-grid'}});
await open('?item=gone-fixture&shelf=pantry&q=jam&utm=x&utm=y#market');let n=await note();
assert.deepEqual([n.count,n.text,n.hidden,n.role,n.aboveGrid],[1,GONE,false,'status',true],'unknown item: one status line above the cards');
a=await addr();assert.equal(a.search,'?shelf=pantry&q=jam&utm=x&utm=y','dead item dropped, other params kept');assert.equal(a.href.endsWith('#market'),true,'hash kept');
s=await shown();assert.deepEqual([s.pressed,s.q,s.focused],['pantry','jam',null],'filters apply as before');assert.ok(!(await page.content()).includes('gone-fixture</'),'id not echoed');
await page.locator('[data-filter="bread"]').click();n=await note();assert.deepEqual([n.count,n.hidden,n.text],[1,true,''],'next filter change hides the line');
await open('?item=gone-fixture');await page.evaluate(()=>scrollTo(0,300));await page.evaluate(()=>loadMore());n=await note();assert.equal(n.hidden,false,'scroll and loadMore keep the line');
await page.reload();n=await note();assert.equal(n.hidden,true,'reload has no line');
for(const v of ['','z'.repeat(81),'a'.repeat(81)]){await open('?item='+v);n=await note();assert.equal(n.hidden,true,'no line for '+v.length);assert.equal((await addr()).search,'?item='+v,'address unchanged for '+v.length)}
await open('?item='+encodeURIComponent(id40));n=await note();assert.equal(n.hidden,true,'known id: no line');assert.equal((await addr()).params.item,id40);
await open('?item='+'a'.repeat(80));assert.equal((await note()).hidden,false,'80 characters is still reported');
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
 for(const key of ['nope',single.key,'constructor','<img src=x onerror=alert(1)>','']){await open(fromUrl(key)+'&utm=x#market');assert.equal(await countText(),defaultCount,'an unusable from link opens the default view');assert.equal(await page.locator('.catalog-from').isVisible(),false);assert.deepEqual((await addr()).params,{utm:'x'});assert.equal((await addr()).hash,'#market');}
 const other=await page.evaluate(k=>catalog.find(p=>!catalog.some(x=>x.producerKey===k&&x.category===p.category)).category,multi.key);
 await open(fromUrl(multi.key)+'&shelf='+other);assert.equal((await fromState()).n,0);assert.equal(await page.locator('#catalog-grid article').count(),0);assert.match(await page.locator('#catalog-sentinel').textContent(),/Nothing here/);
 await open(fromUrl(multi.key)+'&q=unfindablefoo&maker=Etto');assert.equal((await fromState()).n,0,'search and brand remain AND filters');await page.locator('[data-clear-from]').click();assert.equal(await countText(),fullCount,'clear resets the combined view');
 await open(fromUrl(multi.key)+'&item='+encodeURIComponent(id40)+'#market');await inView(id40);assert.equal((await shown()).focused,id40,'item keeps its existing precedence');assert.equal(await page.locator('.catalog-from').isVisible(),false);assert.equal((await addr()).params.from,undefined);
 // AV1102-03: the Available today filter exists only when some card carries a current word.
 await open('?avail=1&utm=x');assert.equal(await page.locator('#avail-filter').count(),0,'main catalog: no control');assert.equal(await countText(),fullCount);assert.deepEqual((await addr()).params,{utm:'x'},'main catalog: ?avail=1 removed');
 // AV1622-04: the page works the words out from raw state + check dates and today's Pacific day, so the fixture sets those.
 // Calendar days back from today's Pacific date (subtracting n*24h crosses DST changes and can land on the wrong day).
 const pacificAgo=n=>{const d=new Date(new Intl.DateTimeFormat('en-CA',{timeZone:'America/Los_Angeles'}).format(new Date())+'T00:00:00Z');d.setUTCDate(d.getUTCDate()-n);return d.toISOString().slice(0,10)};
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
 // RF0854-13: a page left open while its shelf check ages from seven to eight days retires Available today at the next normal render,
 // exactly as a reload would (fixed clock: checked Oct 31, Pacific Nov 7 = age seven, Nov 8 = age eight). Own page per case: fresh cache and history.
 const staleAvailabilityChecks=[];
 {
  const same=require('util').isDeepStrictEqual,D7=new Date('2026-11-07T20:00:00Z'),D8=new Date('2026-11-08T20:00:00Z');let cp=null;
  const real=n=>`catalogFreshness.selectionCheckedOn="2026-10-31";catalog.slice(0,${n}).forEach(p=>{p.availabilityState="yes";p.availabilityCheckedOn="2026-10-31"});`;
  const synth=rows=>`catalogFreshness.selectionCheckedOn="2026-10-31";catalog.splice(0,catalog.length,...${JSON.stringify(rows)}.map(p=>({...catalog[0],...p,availabilityCheckedOn:"2026-10-31"})));`;
  const go=async(url,body)=>{if(cp)await cp.context().close();cp=await browser.newPage({viewport:{width:390,height:900}});cp.on('pageerror',e=>errors.push(e.message));
   await cp.clock.setFixedTime(D7);await cp.route('**/catalog-products.js',async r=>{const res=await r.fetch();await r.fulfill({response:res,body:(await res.text())+';'+body})});
   await cp.goto(base+'/'+url);await cp.waitForSelector('#catalog-sentinel');await cp.evaluate(()=>{window.__replaced=0;window.__h0=history.length;const r=history.replaceState.bind(history);history.replaceState=(...a)=>{window.__replaced++;return r(...a)}})};
  // style.css sets html{scroll-behavior:smooth}: focus()/typing start an animated scroll, so wait (in real time, outside the faked page clock) until scrollY holds still before sampling it.
  const settledY=async()=>{let last=null,same=0;for(let i=0;i<200&&same<4;i++){const y=await cp.evaluate(()=>scrollY);same=y===last?same+1:0;last=y;await new Promise(r=>setTimeout(r,50))}assert.ok(same>=4,'scroll position settles');return last};
  const st=()=>cp.evaluate(()=>({controls:Math.max(document.querySelectorAll('#avail-filter').length,document.querySelectorAll('.avail-filter').length),checked:$('#avail-filter')?.checked??null,count:$('#catalog-count').textContent,ids:filteredProducts().map(p=>p.id),cards:[...document.querySelectorAll('#catalog-grid article')].map(e=>e.dataset.productId),search:location.search,hash:location.hash,history:history.length-window.__h0,replaced:window.__replaced,focus:document.activeElement?.id||null,y:scrollY,view:activeView,shelf:activeCategory,q:searchText($('#product-search').value),brand:$('#brand-filter').value,from:activeFrom,item:linkedItem,status:$('#catalog-item-status').hidden?null:$('#catalog-item-status').textContent}));
  const settled=()=>cp.evaluate(async()=>{await document.fonts.ready;await Promise.all([...document.images].map(i=>i.complete?0:new Promise(r=>{i.onload=i.onerror=r;setTimeout(r,3000)})));let last=-1,same=0;for(let i=0;i<300&&same<10;i++){await new Promise(r=>requestAnimationFrame(r));same=scrollY===last?same+1:0;last=scrollY}});
  const reloaded=async()=>{await cp.reload();await cp.waitForSelector('#catalog-sentinel');return st()};
  const tidy=(s,label)=>{assert.equal(new Set(s.cards).size,s.cards.length,label+': unique cards');assert.ok(same(s.cards,s.ids.slice(0,s.cards.length)),label+': cards follow the ordered list');assert.equal(s.count,`${s.ids.length} selections · ${s.cards.length} shown`,label+': count')};
  // available_filter_retires_on_eighth_day_render: a normal search, view or shelf render on day eight drops the checked control and only ?avail.
  for(const [label,edit,want] of [['search',()=>cp.locator('#product-search').fill('jam'),'?view=all&utm=x&utm=y&q=jam'],['view',()=>cp.locator('[data-view="packaged"]').click(),'?utm=x&utm=y'],['shelf',()=>cp.locator('[data-filter="pantry"]').click(),'?view=all&utm=x&utm=y&shelf=pantry']]){
   await go('?view=all&avail=1&utm=x&utm=y#market',real(2));let s=await st();
   assert.deepEqual([s.controls,s.checked,s.count,s.search],[1,true,'2 selections · 2 shown','?view=all&avail=1&utm=x&utm=y'],label+': age seven keeps Available today');
   await cp.clock.setFixedTime(D8);await edit();s=await st();
   assert.deepEqual([s.controls,s.checked,s.search,s.hash,s.history],[0,null,want,'#market',0],label+': age eight retires the control and only avail');
   assert.ok(s.ids.length>0,label+': remaining filters show their own results');tidy(s,label);
   const r=await reloaded();assert.ok(same([r.controls,r.search,r.ids,r.view,r.shelf,r.q],[0,s.search,s.ids,s.view,s.shelf,s.q]),label+': same as a reload');
   staleAvailabilityChecks.push('available_filter_retires_on_eighth_day_render:'+label);
  }
  // unchecked_stale_control_retires_without_extra_history + rollover_repaint_has_no_duplicates: an unchecked control goes on a load-more
  // render with no history write; a checked paginated filter repaints the full list once, then load more continues without duplicates.
  await go('?view=all&utm=x',real(2));let s=await st();assert.deepEqual([s.controls,s.checked,s.count],[1,false,'170 selections · 12 shown']);
  await cp.clock.setFixedTime(D8);await cp.evaluate(()=>loadMore());s=await st();
  assert.deepEqual([s.controls,s.replaced,s.search,s.history,s.count],[0,0,'?view=all&utm=x',0,'170 selections · 24 shown'],'unchecked: retired with no history write');tidy(s,'unchecked');
  for(const again of [()=>cp.evaluate(()=>loadMore()),()=>cp.locator('#product-search').fill('jam'),()=>cp.locator('#clear-filters').click()]){await again();s=await st();assert.equal(s.controls,0,'repeat renders stay retired');tidy(s,'repeat')}
  staleAvailabilityChecks.push('unchecked_stale_control_retires_without_extra_history');
  await go('?view=all&avail=1&utm=x',real(14));s=await st();assert.deepEqual([s.checked,s.count],[true,'14 selections · 12 shown']);
  await cp.clock.setFixedTime(D8);await cp.evaluate(()=>loadMore());s=await st();
  assert.deepEqual([s.controls,s.replaced,s.search,s.count],[0,1,'?view=all&utm=x','170 selections · 24 shown'],'paginated: one replaceState, full repaint');tidy(s,'paginated');
  await cp.evaluate(()=>loadMore());s=await st();assert.equal(s.cards.length,36);tidy(s,'load more after retirement');
  assert.ok(same((await reloaded()).ids,s.ids),'paginated: same list as a reload');
  staleAvailabilityChecks.push('rollover_repaint_has_no_duplicates');
  // stale_filter_retirement_preserves_other_state: view, shelf, search, brand, maker, item, status, duplicate params, hash, focus and scroll.
  const ROWS=[{id:'qa-leaf',producerKey:'Jayleaf',brand:'QA maker',name:'QA leaf',category:'vegetables',availabilityState:'yes'},{id:'qa-leaf-two',producerKey:'Jayleaf',brand:'QA maker',name:'QA leaf two',category:'vegetables',availabilityState:''},
   {id:'qa-pasta',producerKey:'Etto',brand:'QA other',name:'QA pasta',category:'pantry',availabilityState:'no'},{id:'qa-jar',producerKey:'Etto',brand:'QA other',name:'QA jar',category:'pantry',availabilityState:''}];
  for(const [url,want,keep] of [['?view=produce&shelf=vegetables&q=leaf&maker=QA+maker&avail=1&utm=x&utm=y#market','?shelf=vegetables&q=leaf&maker=QA+maker&utm=x&utm=y',{view:'produce',shelf:'vegetables',q:'leaf',brand:'QA maker',from:''}],
   ['?from=Jayleaf&avail=1&utm=x&utm=y#market','?from=Jayleaf&utm=x&utm=y',{view:'all',shelf:'all',q:'',brand:'',from:'Jayleaf'}]]){
   await go(url,synth(ROWS));let s=await st();assert.ok(same(s.ids,['qa-leaf']),'age seven: filtered');
   await settled(); // the #market fragment keeps re-aligning the page while fonts and images load; measure scroll only once it holds still
   await cp.locator('#product-search').focus();await cp.keyboard.press('End');const y=await settledY();await cp.clock.setFixedTime(D8);await cp.keyboard.type(' ');await settledY();s=await st();
   assert.ok(same(s.ids,['qa-leaf','qa-leaf-two']),url+': other filters still apply');assert.deepEqual([s.controls,s.search,s.hash,s.focus,s.y,s.history],[0,want,'#market','product-search',y,0],url);
   for(const k of Object.keys(keep))assert.equal(s[k],keep[k],url+': keeps '+k);
   const r=await reloaded();assert.ok(same([r.ids,r.search,r.controls],[s.ids,s.search,0]),url+': same as a reload');
  }
  await go('?view=all',real(2));const id30=await cp.evaluate(()=>catalog[30].id);
  await go(`?item=${encodeURIComponent(id30)}&utm=x&utm=y#market`,real(2));s=await st();const n0=s.cards.length;assert.deepEqual([s.controls,s.checked,s.item],[1,false,id30]);
  await cp.clock.setFixedTime(D8);await cp.evaluate(()=>loadMore());s=await st();
  assert.deepEqual([s.controls,s.replaced,s.item,s.search,s.hash],[0,0,id30,`?item=${encodeURIComponent(id30)}&utm=x&utm=y`,'#market'],'valid item survives');assert.ok(s.cards.length>n0);tidy(s,'item');
  await go('?item=gone-fixture&utm=x#market',real(2));const gone=(await st()).status;assert.ok(gone);await cp.clock.setFixedTime(D8);await cp.evaluate(()=>loadMore());s=await st();
  assert.deepEqual([s.controls,s.replaced,s.status,s.search],[0,0,gone,'?utm=x'],'status line survives');
  staleAvailabilityChecks.push('stale_filter_retirement_preserves_other_state');
  // current_words_outside_results_keep_the_control: on day seven a current word anywhere (Sold out included, outside the shelf/search)
  // keeps the control and an intentionally empty result stays empty; Sold out never passes. Day eight retires it.
  for(const [url,rows,label] of [['?view=all&shelf=pantry&avail=1',ROWS,'current yes outside the shelf'],['?view=all&avail=1',ROWS.map(p=>({...p,availabilityState:p.availabilityState&&'no'})),'Sold out only']]){
   await go(url,synth(rows));for(const t of ['qa','qa jar']){await cp.locator('#product-search').fill(t);const s=await st();assert.deepEqual([s.controls,s.checked,s.count,new URLSearchParams(s.search).get('avail')],[1,true,'0 selections · 0 shown','1'],label+': '+t)}
   await cp.clock.setFixedTime(D8);await cp.locator('#product-search').fill('qa');const s=await st();assert.equal(s.controls,0,label+': day eight retires');assert.ok(s.ids.length>0&&!new URLSearchParams(s.search).has('avail'),label);
  }
  staleAvailabilityChecks.push('current_words_outside_results_keep_the_control');
  await cp.context().close();
 }
 // RF0814-10: maker promises include sold-out and unconfirmed rows, across both catalog views.
 const makerAvailabilityChecks=[];
 {
  const rows=[
   {id:'qa-maker-available',producerKey:'Jayleaf',brand:'QA maker',name:'QA leaf',category:'vegetables',availabilityState:'yes'},
   {id:'qa-maker-sold-out',producerKey:'Jayleaf',brand:'QA maker',name:'QA jar',category:'pantry',availabilityState:'no'},
   {id:'qa-maker-unconfirmed',producerKey:'Jayleaf',brand:'QA maker',name:'QA bunch',category:'vegetables',availabilityState:''},
   {id:'qa-other-available',producerKey:'Etto',brand:'QA other',name:'QA pasta',category:'pantry',availabilityState:'limited'},
   {id:'qa-other-unconfirmed',producerKey:'Etto',brand:'QA other',name:'QA fruit',category:'fruit',availabilityState:''}
  ],makerRows=rows.filter(p=>p.producerKey==='Jayleaf');
  const install=async(current=true)=>{
   await page.unroute('**/catalog-products.js');
   await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();await r.fulfill({response:res,body:(await res.text())+`;catalogFreshness.selectionCheckedOn=${JSON.stringify(pacificAgo(current?0:8))};catalog.splice(0,catalog.length,...${JSON.stringify(rows)}.map(p=>({...catalog[0],...p,availabilityCheckedOn:catalogFreshness.selectionCheckedOn})));`})});
   await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache');
  };
  const state=()=>page.evaluate(()=>({ids:filteredProducts().map(p=>p.id),cards:[...document.querySelectorAll('#catalog-grid article')].map(e=>e.dataset.productId),checked:$('#avail-filter')?.checked??null,search:location.search,hash:location.hash,history:history.length,q:$('#product-search').value,brand:$('#brand-filter').value,shelf:activeCategory,view:activeView,from:activeFrom}));
  const expectRows=async(want,label)=>{const st=await state();assert.ok(sameSet(st.ids,want.map(p=>p.id)),label+': filtered rows');assert.ok(sameSet(st.cards,st.ids),label+': rendered rows');assert.equal(await countText(),want.length+' selections',label+': count');return st};
  const seeAll=async()=>{const b=page.locator('[data-from="Jayleaf"]').first();await b.locator('xpath=ancestor::details').evaluate(e=>e.open=true);assert.equal(await b.textContent(),`See all ${makerRows.length} from Jayleaf`);await b.click()};
  await install();
  for(const width of [390,1440]){
   await page.setViewportSize({width,height:900});await open('?avail=1&utm=x&utm=y#market');
   let st=await expectRows(rows.filter(p=>['yes','limited'].includes(p.availabilityState)),'before maker navigation');assert.equal(st.checked,true);
   await seeAll();let after=await expectRows(makerRows,'makerNavigationClearsAvailability');
   assert.equal(after.checked,false);assert.equal(after.from,'Jayleaf');assert.equal(new URLSearchParams(after.search).get('from'),'Jayleaf');assert.equal(new URLSearchParams(after.search).has('avail'),false);assert.equal(after.history,st.history);assert.equal(after.hash,'#market');assert.equal(new URLSearchParams(after.search).getAll('utm').join(','),'x,y');
   await page.reload();await expectRows(makerRows,'maker reload');assert.equal(await avail().isChecked(),false);
   makerAvailabilityChecks.push('makerNavigationClearsAvailability:'+width);
   await open('?from=Jayleaf&avail=1&shelf=vegetables&q=leaf&maker=QA+maker&utm=x&utm=y#market');
   st=await expectRows(makerRows.filter(p=>p.availabilityState==='yes'),'before Show everything');assert.equal(st.checked,true);assert.equal(st.from,'Jayleaf');assert.equal(st.shelf,'vegetables');assert.equal(st.q,'leaf');assert.equal(st.brand,'QA maker');
   await page.locator('[data-clear-from]').click();after=await expectRows(rows,'makerShowEverythingClearsAvailability');
   assert.equal(after.checked,false);assert.equal(after.from,'');assert.equal(after.shelf,'all');assert.equal(after.q,'');assert.equal(after.brand,'');assert.equal(after.view,'all');assert.equal(after.history,st.history);assert.equal(after.hash,'#market');assert.equal(after.search,'?utm=x&utm=y&view=all');assert.equal(await page.locator('.catalog-from').isVisible(),false);
   await page.reload();await expectRows(rows,'Show everything reload');
   makerAvailabilityChecks.push('makerShowEverythingClearsAvailability:'+width);
  }
  await open('?from=Jayleaf&avail=1');await expectRows(makerRows.filter(p=>p.availabilityState==='yes'),'explicit AND');assert.equal(await avail().isChecked(),true);
  // Ordinary controls must not opt out of availability or the active maker.
  for(const edit of [()=>page.locator('#product-search').fill('QA'),()=>page.locator('#brand-filter').selectOption('QA maker'),()=>page.locator('[data-filter="vegetables"]').click(),()=>page.locator('[data-view="produce"]').click()]){
   await edit();await expectRows(makerRows.filter(p=>p.availabilityState==='yes'),'ordinary AND edit');assert.equal(await avail().isChecked(),true);assert.equal((await addr()).params.from,'Jayleaf');assert.equal((await addr()).params.avail,'1');
  }
  for(const key of ['unknown-maker','constructor','<img src=x onerror=alert(1)>']){
   const before=await state();await page.evaluate(key=>{const b=document.createElement('button');b.dataset.from=key;document.body.append(b);b.click();b.remove()},key);assert.ok(require('util').isDeepStrictEqual(await state(),before),'invalid delegated key is a complete no-op');
  }
  makerAvailabilityChecks.push('makerExplicitAndAndInvalidKey');
  for(const current of [false,null]){
   if(current===false)await install(false);
   else{await page.unroute('**/catalog-products.js');await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();await r.fulfill({response:res,body:(await res.text())+`;catalogFreshness.selectionCheckedOn=null;catalog.splice(0,catalog.length,...${JSON.stringify(rows)}.map(p=>({...catalog[0],...p,availabilityCheckedOn:null})));`})});await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache')}
   await page.goto(base+'/');await page.waitForSelector('#catalog-grid article');assert.equal(await avail().count(),0);await expectRows(rows.filter(p=>!['vegetables','fruit'].includes(p.category)),'no control default');
   // The default packaged view includes the sold-out maker row, whose link still promises all three.
   await seeAll();await expectRows(makerRows,'no control maker');await page.locator('[data-clear-from]').click();await expectRows(rows,'no control Show everything');
   await open('?from=Jayleaf&avail=1');assert.equal(await avail().count(),0);assert.equal((await addr()).params.avail,undefined);await expectRows(makerRows,'no control URL');
  }
  makerAvailabilityChecks.push('makerNavigationWithoutAvailabilityControl');
  await page.unroute('**/catalog-products.js');await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache');await open('');assert.equal(await countText(),fullCount,'real catalog restored after maker availability fixtures');
 }
 // AV1222-14: Clear filters shows for any one filter, resets all five, keeps other parameters and the hash, then focuses the search box.
 const clr=page.locator('#clear-filters'),FILTERS=['shelf=pantry','q=jam','maker=Etto','from='+multi.key];
 for(const width of [390,1440]){await page.setViewportSize({width,height:900});await page.goto(base+'/');await page.waitForSelector('#catalog-grid article');assert.equal(await clr.isVisible(),false,'fresh: hidden');assert.equal(await countText(),defaultCount);
  for(const f of FILTERS){await open('?'+f+'&utm=x#catalog');assert.equal(await clr.isVisible(),true,f);await clr.click();assert.equal(await countText(),defaultCount,f);assert.deepEqual((await addr()).params,{utm:'x'},f);assert.equal((await addr()).hash,'#catalog');assert.equal(await page.evaluate(()=>document.activeElement.id),'product-search');assert.equal(await clr.isVisible(),false);}
  await open('?q=unfindablefoo');assert.match(await page.locator('#catalog-sentinel').textContent(),/Nothing here/);assert.equal(await clr.isVisible(),true);await clr.click();assert.equal(await countText(),defaultCount);
  await page.goto(base+'/?q=%20%20%20');await page.waitForSelector('#catalog-grid article');assert.equal(await clr.isVisible(),false,'spaces are not a filter');
  await open('?shelf=pantry&q=jam');await page.locator('#product-search').focus();await page.keyboard.press('Tab');await page.keyboard.press('Tab');assert.equal(await page.evaluate(()=>document.activeElement.id),'clear-filters','Tab reaches it');await page.keyboard.press('Enter');assert.equal(await countText(),defaultCount);assert.equal(await page.locator('#brand-filter').inputValue(),'');assert.equal(await page.locator('[data-filter="all"]').getAttribute('aria-pressed'),'true');
  await open('?q=jam');const bx=await clr.boundingBox();assert.ok(bx.height>=44,'tap target '+width);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no overflow '+width);}
 await fixture(W);await open('?avail=1');assert.equal(await clr.isVisible(),true,'avail');await clr.click();assert.equal(await avail().isChecked(),false);assert.equal(await countText(),defaultCount);assert.equal((await addr()).params.avail,undefined);
// AV1052-02: a shelf with no product in the published catalog is hidden (really invisible, out of the Tab order); All shelves always shows.
 const shelfFix=async(drop,after='')=>{await page.unroute('**/catalog-products.js').catch(()=>{});await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text())+`;for(let i=catalog.length;i--;)if(${JSON.stringify(drop)}.includes(catalog[i].category))catalog.splice(i,1);${after}`})});await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache')};
 const shelves=()=>page.evaluate(()=>Object.fromEntries([...document.querySelectorAll('[data-filter]')].map(b=>[b.dataset.filter,{shown:b.getBoundingClientRect().width>0,pressed:b.getAttribute('aria-pressed')}])));
 const ALL9=['all','fruit','vegetables','dairy','eggs','meat','pantry','drinks','bread','flowers'];
 await page.setViewportSize({width:390,height:844});await open('');let sh=await shelves();assert.deepEqual(Object.keys(sh).filter(k=>sh[k].shown),ALL9,'every shelf has a product: all buttons show');
 const perShelf=await page.evaluate(()=>{const o={};catalog.forEach(p=>o[p.category]=(o[p.category]||0)+1);return o}),total=Object.values(perShelf).reduce((a,b)=>a+b,0);
 for(const width of [390,1440]){await page.setViewportSize({width,height:900});
  for(const drop of [['flowers'],['eggs'],['eggs','flowers']]){await shelfFix(drop);
   await open('?view=all&shelf=flowers&utm=synthetic#market');
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
// AV1352-01 / AVO-SHOP-CLEAN-1: the three catalog notices (Based in, seasons and deliveries, illustrations) are gone from the page; a generated picture still carries the alt suffix.
 const NOTICES=['names the town a producer or maker calls home','Our selection changes with the seasons','illustrations made from photos of our shelves','claim that every ingredient'];
 const noteState=()=>page.evaluate(()=>({body:document.body.innerText,html:document.documentElement.outerHTML,notes:[...document.querySelectorAll('p.catalog-note')].map(e=>e.textContent),alts:[...document.querySelectorAll('#catalog-grid img')].map(i=>i.alt),names:[...document.querySelectorAll('#catalog-grid article')].map(a=>catalog.find(p=>p.id===a.dataset.productId).name)}));
 const noNotices=(ns,why)=>{for(const g of NOTICES){assert.ok(!ns.body.includes(g)&&!ns.html.includes(g),why+': notice gone: '+g)}};
 const imageFixture=async js=>{await page.unroute('**/catalog-products.js').catch(()=>{});await page.route('**/catalog-products.js',async r=>{const res=await r.fetch();r.fulfill({response:res,body:(await res.text())+';'+js})});await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache')};
 await open('');let ns=await noteState();noNotices(ns,'real catalog');
 assert.ok(ns.alts.length>0&&ns.alts.every(a=>a.endsWith(' (illustration)')&&!a.endsWith(' (illustration) (illustration)')),'every generated picture is flagged');
 await page.locator('#product-search').fill('Cambria');ns=await noteState();noNotices(ns,'filtered');await page.locator('#product-search').fill('');
 await imageFixture(`catalog.forEach((p,i)=>{p.image='assets/products/photo-0123456789abcdef.'+(i%2?'jpg':'png');if(i===0)p.imageAlt='Owner photo alt'});`);await open('');ns=await noteState();
 noNotices(ns,'all owner photos');assert.equal(ns.alts[0],'Owner photo alt');assert.equal(ns.alts[1],ns.names[1],'owner photo keeps its plain alt');
 await imageFixture(`catalog.forEach((p,i)=>{p.image=i===1?'assets/products/photo-0123456789abcdef.jpg':i===2?'assets/products/photo-0123456789ABCDEF.jpg':i===3?'assets/products/photo-0123456789abcdef.jpg\\n':i===4?'assets/products/photo-0123456789abcdef.jpeg':'assets/products/photo-0123456789abcdef.png'});`);await open('');ns=await noteState();
 noNotices(ns,'mixed');assert.deepEqual(ns.alts.slice(0,6).map((a,i)=>a.endsWith(' (illustration)')),[false,false,true,true,true,false],'only the exact installed form is exempt');
 await imageFixture(`catalog.forEach((p,i)=>{p.image=i===0?'assets/products/a.webp':'assets/products/photo-0123456789abcdef.jpg'});`);await open('');ns=await noteState();const ownerName=ns.names[5];
 await page.locator('#product-search').fill(ownerName);ns=await noteState();assert.ok(ns.alts.length>0&&ns.alts.every(a=>!a.endsWith(' (illustration)')),'filtered to owner photos only');noNotices(ns,'owner photos only');
 await imageFixture(`catalog.length=0;`);await open('');ns=await noteState();noNotices(ns,'empty catalog');
 await page.unroute('**/catalog-products.js');await (await page.context().newCDPSession(page)).send('Network.clearBrowserCache');
 // AVO-SHOP-CLEAN-1: the shop opens on packaged goods. Produce = fruit, vegetables, flowers; photo-product-018 (tortilla chips, filed under vegetables) is sold in a bag, so it is packaged.
await open('');
 {const PRODUCE=['fruit','vegetables','flowers'],BAGGED='photo-product-018';
  const isProduce=(cat,id)=>PRODUCE.includes(cat)&&id!==BAGGED;
  const cards=()=>page.evaluate(()=>[...document.querySelectorAll('#catalog-grid article')].map(a=>({id:a.dataset.productId,cat:a.dataset.category})));
  const allCat=await page.evaluate(()=>catalog.map(p=>({id:p.id,cat:p.category}))),wantPack=allCat.filter(p=>!isProduce(p.cat,p.id)).length,wantProd=allCat.length-wantPack;
  assert.ok(wantPack>0&&wantProd>0&&allCat.some(p=>p.id===BAGGED&&p.cat==='vegetables'),'fixture: both views have products and the bagged item is filed under vegetables');
  const pressed=()=>page.evaluate(()=>Object.fromEntries([...document.querySelectorAll('[data-view]')].map(b=>[b.dataset.view,b.getAttribute('aria-pressed')])));
  const vis=f=>page.locator(`[data-filter="${f}"]`).isVisible();
  // First paint: the page as served already says Packaged goods and offers no produce shelf; the grid is never filled with the wrong view.
  await page.addInitScript(()=>{window.__wrong=0;document.addEventListener('DOMContentLoaded',()=>{},{once:true});new MutationObserver(()=>{const g=document.getElementById('catalog-grid');if(g&&g.querySelector('article[data-category="fruit"],article[data-category="vegetables"]:not([data-product-id="photo-product-018"]),article[data-category="flowers"]'))window.__wrong++}).observe(document,{childList:true,subtree:true})});
  const raw=await (await page.request.get(base+'/')).text();
  assert.match(raw,/<button data-view="packaged" aria-pressed="true" class="selected">Packaged goods<\/button>/,'served page: packaged goods selected');
  for(const f of PRODUCE)assert.match(raw,new RegExp(`<button data-filter="${f}" aria-pressed="false" hidden>`),'served page: no produce shelf '+f);
  await page.goto(base+'/');await page.waitForSelector('#catalog-grid article');
  assert.equal(await page.evaluate(()=>window.__wrong),0,'the wrong view is never drawn');
  assert.equal(await countText(),wantPack+' selections');assert.deepEqual(await pressed(),{packaged:'true',produce:'false',all:'false'});
  assert.ok((await cards()).every(c=>!isProduce(c.cat,c.id)),'default view: packaged goods only');assert.equal(new URL(page.url()).search,'','the default needs no address');
  for(const f of PRODUCE)assert.equal(await vis(f),false,'produce shelf hidden in packaged view: '+f);
  for(const f of ['pantry','dairy','bread'])assert.equal(await vis(f),true,'packaged shelf offered: '+f);
  // Choosing a view changes the address (shareable) and the count; the other views are one click away.
  await page.locator('[data-view="produce"]').click();assert.equal(new URL(page.url()).search,'?view=produce');assert.equal(await countText(),wantProd+' selections');assert.ok((await cards()).every(c=>isProduce(c.cat,c.id)));
  assert.equal(await vis('fruit'),true);assert.equal(await vis('pantry'),false);assert.equal(await page.locator('#clear-filters').isVisible(),true,'a non-default view can be cleared');
  await page.locator('[data-view="all"]').click();assert.equal(new URL(page.url()).search,'?view=all');assert.equal(await countText(),allCat.length+' selections');assert.equal(await vis('pantry'),true);assert.equal(await vis('fruit'),true);
  await page.locator('[data-view="packaged"]').click();assert.equal(new URL(page.url()).search,'');assert.equal(await countText(),wantPack+' selections');
  // Shared links: ?view=, explicit ?view=packaged, an older ?shelf= link, ?item= on a produce card, a maker link.
  await page.goto(base+'/?view=produce');await page.waitForSelector('#catalog-grid article');assert.equal(await countText(),wantProd+' selections');assert.equal((await pressed()).produce,'true');
  await page.goto(base+'/?view=packaged');await page.waitForSelector('#catalog-grid article');assert.equal(await countText(),wantPack+' selections');
  await page.goto(base+'/?view=all');await page.waitForSelector('#catalog-grid article');assert.equal(await countText(),allCat.length+' selections');
  await page.goto(base+'/?view=nonsense');await page.waitForSelector('#catalog-grid article');assert.equal(await countText(),wantPack+' selections');assert.equal(new URL(page.url()).search,'','a bad view is dropped');
  await page.goto(base+'/?shelf=fruit');await page.waitForSelector('#catalog-grid article');assert.equal((await pressed()).produce,'true','an older shelf link opens on its own view');assert.ok((await cards()).every(c=>c.cat==='fruit'));assert.equal(new URL(page.url()).search,'?shelf=fruit');
  await page.goto(base+'/?view=packaged&shelf=fruit');await page.waitForSelector('#catalog-grid article');assert.equal(new URL(page.url()).search,'?view=packaged','a shelf outside the view is dropped');assert.equal(await countText(),wantPack+' selections');
  const prodId=allCat.find(p=>isProduce(p.cat,p.id)).id;await page.goto(base+'/?item='+prodId);await page.waitForSelector('#catalog-grid article');assert.equal((await pressed()).all,'true','a linked produce item opens all items');assert.ok((await cards()).some(c=>c.id===prodId));
  // Search and the maker filter work inside the view; an empty result points at All items.
  await page.goto(base+'/');await page.waitForSelector('#catalog-grid article');
  await page.locator('#product-search').fill('jam');let r=await cards();assert.ok(r.length>0&&r.every(c=>!isProduce(c.cat,c.id)),'search inside packaged');assert.equal(new URL(page.url()).search,'?q=jam');
  await page.locator('#product-search').fill('jalapeno');assert.equal((await cards()).length,0,'a produce-only search finds nothing in packaged goods');assert.match(await page.locator('#catalog-sentinel').textContent(),/All items/);
  await page.locator('[data-view="all"]').click();assert.ok((await cards()).length>0,'the same search finds it under all items');await page.locator('#clear-filters').click();
  assert.equal(await countText(),wantPack+' selections','clear filters returns to packaged goods');assert.equal(new URL(page.url()).search,'');assert.equal((await pressed()).packaged,'true');
  const mk=await page.evaluate(()=>{const m={};catalog.forEach(p=>{if(p.category==='pantry')m[p.brand]=(m[p.brand]||0)+1});return Object.keys(m).sort()[0]});
  await page.locator('#brand-filter').selectOption(mk);r=await cards();assert.ok(r.length>0&&r.every(c=>!isProduce(c.cat,c.id)),'maker filter inside packaged');await page.locator('#clear-filters').click();
 }
 // AV1104-03: the sentence under the Visit hours. Real sitegen output (hass.tests.visit_hours_fixtures) is served for its own ?visitfixture= document requests only (assets stay same-origin), under fixed browser clocks and visitor zones; each expected sentence is written out here, not derived from the data.
 {const fixtures=JSON.parse(require('child_process').execFileSync('python3',['-B','-m','hass.tests.visit_hours_fixtures'],{cwd:require('path').resolve(__dirname,'..'),maxBuffer:1<<26,encoding:'utf8'}));
  const all=[];
  const open=async(name,iso,o={})=>{
   const ctx=await browser.newContext({viewport:{width:o.width||390,height:900},timezoneId:o.tz||'UTC',javaScriptEnabled:o.js!==false}),pg=await ctx.newPage(),errs=[],reqs=[];all.push(errs);
   pg.on('pageerror',e=>errs.push(e.message));pg.on('request',r=>reqs.push(r.url()));
   const html=o.edit?o.edit(fixtures[name]):fixtures[name];
   await pg.route(u=>new URL(u).searchParams.get('visitfixture')===name,r=>r.request().resourceType()==='document'?r.fulfill({status:200,contentType:'text/html; charset=utf-8',body:html}):r.continue());
   if(o.js!==false)await pg.clock.install({time:new Date(iso)});
   if(o.init)await pg.addInitScript(o.init);
   await pg.goto(base+'/?visitfixture='+name);await pg.waitForSelector('#catalog-grid article',{state:'attached',timeout:o.js===false?1:10000}).catch(()=>{});
   const state=()=>pg.evaluate(()=>{const e=document.querySelector('.visit-open-status');return e?{text:e.textContent,hidden:e.hidden,nodes:document.querySelectorAll('.visit-open-status').length}:null});
   return {ctx,pg,errs,reqs,state};
  };
  const says=async(name,iso,want,o)=>{const t=await open(name,iso,o);const s=await t.state();
   if(want===null)assert.equal(s,null,`${name} ${iso}: no status node`);
   else if(want==='')assert.ok(s&&s.hidden&&s.text==='',`${name} ${iso}: hidden and empty, got ${JSON.stringify(s)}`);
   else assert.ok(s&&!s.hidden&&s.text===want,`${name} ${iso}: want "${want}", got ${JSON.stringify(s)}`);
   await t.ctx.close();return t.errs;};
  // Boundaries on the canonical hours (Monday-Friday 9am-6pm, Saturday 9am-5pm, closed Sunday). Pacific is UTC-8 from Nov 1 2026.
  await says('main','2026-11-16T16:59:10Z','Closed now - opens Monday 9am');   // Mon 08:59
  await says('main','2026-11-16T17:00:10Z','Open now - closes 6pm');           // Mon 09:00 (opening is open)
  await says('main','2026-11-17T01:59:10Z','Open now - closes 6pm');           // Mon 17:59
  await says('main','2026-11-17T02:00:10Z','Closed now - opens Tuesday 9am');  // Mon 18:00 (closing is closed)
  await says('main','2026-11-21T02:00:10Z','Closed now - opens Saturday 9am'); // Fri 18:00
  await says('main','2026-11-21T20:00:10Z','Open now - closes 5pm');           // Sat 12:00
  await says('main','2026-11-22T01:00:10Z','Closed now - opens Monday 9am');   // Sat 17:00
  await says('main','2026-11-22T20:00:10Z','Closed now - opens Monday 9am');   // Sun 12:00
  await says('minutes','2026-11-16T17:29:10Z','Closed now - opens Monday 9:30am');
  await says('minutes','2026-11-16T17:30:10Z','Open now - closes 12pm');
  await says('minutes','2026-11-16T20:00:10Z','Closed now - opens Tuesday 9:30am');
  await says('minutes','2026-11-21T04:00:10Z','Closed now - opens Monday 9:30am'); // Fri 20:00, Saturday and Sunday closed
  // Nothing said: all closed, a day no line names (today, or between now and the next opening), a line that does not read.
  await says('all_closed','2026-11-16T20:00:10Z','');
  await says('no_sunday','2026-11-22T20:00:10Z','');
  await says('no_sunday','2026-11-21T20:00:10Z','Open now - closes 5pm');
  await says('no_saturday','2026-11-21T20:00:10Z','');
  await says('no_saturday','2026-11-21T02:00:10Z','');                         // Fri 18:00: next day unnamed
  await says('no_saturday','2026-11-20T20:00:10Z','Open now - closes 6pm');
  await says('unreadable','2026-11-16T20:00:10Z',null);                        // another line read; the page still says nothing
  await says('unreadable_first','2026-11-16T20:00:10Z',null);
  // The visitor's own zone changes nothing: the same instant, three zones; and the Pacific date, not the UTC one, picks the day.
  for(const tz of ['UTC','Asia/Tokyo','America/New_York'])await says('main','2026-11-17T04:00:10Z','Closed now - opens Tuesday 9am',{tz});  // Mon 20:00 Pacific; Tue in UTC and Tokyo
  for(const tz of ['UTC','Asia/Tokyo'])await says('main','2026-11-16T17:00:10Z','Open now - closes 6pm',{tz});
  // Pacific daylight time: Mar 9 2026 is PDT (UTC-7), Nov 2 2026 is PST (UTC-8); a fixed offset would get one of each wrong.
  await says('main','2026-03-08T00:59:10Z','Open now - closes 5pm');           // Sat Mar 7 16:59 PST
  await says('main','2026-03-09T16:00:10Z','Open now - closes 6pm');           // Mon Mar 9 09:00 PDT
  await says('main','2026-03-09T15:30:10Z','Closed now - opens Monday 9am');   // 08:30 PDT
  await says('main','2026-11-02T16:30:10Z','Closed now - opens Monday 9am');   // Mon Nov 2 08:30 PST
  await says('main','2026-10-31T23:59:10Z','Open now - closes 5pm');           // Sat Oct 31 16:59 PDT
  // A page left open: it follows the clock across closing and across Pacific midnight, with no new node or request.
  {const t=await open('main','2026-11-17T01:59:00Z');assert.equal((await t.state()).text,'Open now - closes 6pm');
   const seen=t.reqs.length;await t.pg.clock.fastForward(90000);assert.equal((await t.state()).text,'Closed now - opens Tuesday 9am');
   await t.pg.evaluate(()=>{window.dispatchEvent(new Event('pageshow'));document.dispatchEvent(new Event('visibilitychange'))});
   const s=await t.state();assert.equal(s.text,'Closed now - opens Tuesday 9am');assert.equal(s.nodes,1);assert.equal(t.reqs.length,seen,'no request after updates');await t.ctx.close();}
  // Home notice: any wording silences it on each of its days (inclusive), never before or after; an unreadable notice date silences it.
  await says('holiday_notice','2026-11-25T04:00:10Z','Closed now - opens Wednesday 9am');  // Tue 20:00, two days before
  await says('holiday_notice','2026-11-26T04:00:10Z','Closed now - opens Thursday 9am');  // Wed 20:00, the day before
  await says('holiday_notice','2026-11-26T07:59:10Z','Closed now - opens Thursday 9am');  // Wed 23:59
  await says('holiday_notice','2026-11-26T08:00:10Z','');                                  // Thu 00:00, first day
  await says('holiday_notice','2026-11-26T20:00:10Z','');                                  // Thu noon
  await says('holiday_notice','2026-11-27T07:59:10Z','');                                  // Thu 23:59, last day
  await says('holiday_notice','2026-11-27T08:00:10Z','Closed now - opens Friday 9am');     // Fri 00:00, restored
  await says('legacy_notice','2026-11-25T20:00:10Z','');                                   // notice with no first day: already started
  await says('legacy_notice','2026-11-29T07:59:10Z','');                                   // Sat 23:59, its last day
  await says('legacy_notice','2026-11-29T20:00:10Z','Closed now - opens Monday 9am');      // Sun, it has ended
  await says('bad_notice_dates','2026-11-25T20:00:10Z','');
  // Notice dates must be real days in order: an impossible day or a first day after the last silences the status, like any unreadable date (Mon Nov 16 noon Pacific, no valid notice reaches it).
  const notice=(f,u)=>({edit:h=>h.replace(/data-from="2026-11-26" data-until="2026-11-26"/,(f===null?'':`data-from="${f}" `)+`data-until="${u}"`)});
  await says('holiday_notice','2026-11-16T20:00:10Z','Open now - closes 6pm');                         // control: the real notice is days away
  await says('holiday_notice','2026-11-16T20:00:10Z','',notice('2026-11-20','2026-11-10'));          // from after until
  await says('holiday_notice','2026-11-16T20:00:10Z','',notice('2026-11-10','2026-11-31'));          // impossible last day
  await says('holiday_notice','2026-12-02T20:00:10Z','',notice('2026-11-10','2026-11-31'));          // and still silent after that day
  await says('holiday_notice','2026-11-16T20:00:10Z','',notice('2026-02-30','2026-11-20'));          // impossible first day
  await says('holiday_notice','2026-11-16T20:00:10Z','',notice(null,'2026-02-29'));                  // 2026 is not a leap year
  await says('holiday_notice','2026-11-16T20:00:10Z','',notice('2026-13-01','2026-13-02'));          // no month 13
  await says('holiday_notice','2026-11-16T20:00:10Z','Open now - closes 6pm',notice('2026-11-20','2026-11-20')); // one real day in the future: status stays
  {const t=await open('holiday_notice','2026-11-27T07:59:30Z');assert.equal((await t.state()).text,'');await t.pg.clock.fastForward(60000);
   assert.equal((await t.state()).text,'Closed now - opens Friday 9am','the notice ends at Pacific midnight and the status returns');await t.ctx.close();}
  // Without JavaScript the empty node stays hidden and the hours are untouched; a broken schedule or missing Intl hides, quietly.
  {const t=await open('main','2026-11-16T20:00:10Z',{js:false});const s=await t.state();assert.ok(s&&s.hidden&&s.text==='','no JavaScript: nothing shown');
   assert.match(await t.pg.locator('.visit').innerText(),/Monday–Friday 9am–6pm\nSaturday 9am–5pm · Closed Sunday/);await t.ctx.close();}
  await says('main','2026-11-16T20:00:10Z','',{edit:h=>h.replace(/data-weekly-hours="[^"]*"/,'data-weekly-hours="[1,2]"')});
  await says('main','2026-11-16T20:00:10Z','',{edit:h=>h.replace(/data-weekly-hours="[^"]*"/,'data-weekly-hours="[]"')});
  await says('main','2026-11-16T20:00:10Z','',{edit:h=>h.replace(/data-weekly-hours="[^"]*"/,'')});
  await says('main','2026-11-16T20:00:10Z','',{init:()=>{const D=Intl.DateTimeFormat;Intl.DateTimeFormat=function(l,o){if(o&&o.hourCycle==='h23')throw new RangeError('no formatter');return new D(l,o)}}});
  // Layout at both widths with the original lines still there.
  for(const width of [390,1440]){const t=await open('main','2026-11-16T20:00:10Z',{width});
   assert.equal((await t.state()).text,'Open now - closes 6pm');assert.match(await t.pg.locator('.visit').innerText(),/Monday–Friday 9am–6pm\nSaturday 9am–5pm · Closed Sunday\n+Open now - closes 6pm/);
   assert.equal(await t.pg.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,'no horizontal overflow at '+width);await t.ctx.close();}
  assert.ok(all.every(e=>e.length===0),'visit hours pages raise no page errors: '+JSON.stringify(all.flat()));
 }
 await page.getByRole('button',{name:'Privacy',exact:true}).click();assert.equal(await page.locator('#dialog').evaluate(e=>e.open),true);await page.keyboard.press('Escape');
 assert.deepEqual(errors,[]);
 const result={checkedAt:new Date().toISOString(),staleAvailabilityChecks,makerAvailabilityChecks,descriptionSearchChecks,all,duplicates:0,townSearch:count,sourceFiltersRemoved:true,introductionUpdated:true,productFacts,commerceRemoved:true,fullFoodAndMakerStoriesInline:true,makerStoriesCollapsed:true,disclosureKeyboardAndClick:true,producerLinksPreserved:true,productDialogRemoved:true,privacyDialogPreserved:true,viewports,errors};fs.writeFileSync(out+'/catalog-only-QA.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});

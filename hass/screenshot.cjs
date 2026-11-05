// Hass H06 private preview capture: one Chromium page of the isolated loopback site, plus checks.
// VIEWPORT: phone (default, 390x844) or desktop (1280x900); anything else exits 1 with "bad VIEWPORT".
// env: PREVIEW_URL (http://127.0.0.1:<port>), TARGET (JSON from hass/preview.py target_for), OUT (png path),
// PLAYWRIGHT_MODULE / CHROMIUM_PATH as in the storefront QA scripts. Only GET/HEAD to the preview origin is
// allowed; every other request (any POST, anything off 127.0.0.1) is aborted. Prints {"checks": {...}}.
// Maker: its place search, then all cards if none names it; card text compared (never a selector built from the name).
// hidden → makerHidden (no card names it); else makerName + makerPlace; a maker with no active card adds no maker check.
// Hike: scheduled → eventShown; completed → pastShown (+ recapShown if a recap); cancelled → rsvpGone (no RSVP button).
'use strict';
const VIEWPORTS={phone:{width:390,height:844},desktop:{width:1280,height:900}},vp=process.env.VIEWPORT||'phone';
if(!Object.hasOwn(VIEWPORTS,vp)){console.error('bad VIEWPORT');process.exit(1);}
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const base=process.env.PREVIEW_URL,target=JSON.parse(process.env.TARGET||'{}'),out=process.env.OUT;
const origin=new URL(base).origin;
// AV1104-10 operator design preview: {kind:'design',page:'home'|'hike'}; the page is a fixed enum checked before any navigation.
if(target.kind==='design'&&!['home','hike'].includes(target.page)){console.error('bad design page');process.exit(1);}
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
    if(target.kind==='design'){  // pageLoaded: HTTP 200 and the page's own heading visible; noHorizontalOverflow at this viewport
      const hike=target.page==='hike',reply=await page.goto(base+(hike?'/hike':'/'),{waitUntil:'networkidle'});
      checks.pageLoaded=reply!==null&&reply.status()===200&&await page.locator(hike?'main h1':'.hero h1').first().isVisible();
      checks.noHorizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth);
    }else if(target.kind==='event'){
      await page.goto(base+'/hike',{waitUntil:'networkidle'});
      if(target.status==='scheduled')checks.eventShown=await page.locator('h2',{hasText:target.title}).count()>0;
      else if(target.status==='completed'){  // past hike whose summary title is exactly the target's; its recap paragraph
        const recaps=await page.locator('#past-hikes .past-hike').evaluateAll((els,title)=>els.filter(d=>
          d.querySelector('summary span')?.textContent===title).map(d=>d.querySelector(':scope>p')?.textContent),target.title);
        checks.pastShown=recaps.length>0;
        if(target.recap)checks.recapShown=recaps[0]===target.recap;
      }else if(target.status==='cancelled'){  // the id is compared in page JS, never put into a selector
        checks.rsvpGone=await page.$$eval('[data-rsvp]',(els,id)=>els.filter(b=>b.dataset.rsvp===id).length,target.id||'')===0;
      }
    }else{
      await page.goto(base+'/',{waitUntil:'networkidle'});
      if(target.kind==='product'||target.kind==='maker'){
        await page.locator('#product-search').fill(target.name||'');
        await page.waitForTimeout(200);
        const cards=page.locator('#catalog-grid').first();
        await cards.scrollIntoViewIfNeeded();
        if(target.kind==='maker'){  // the place search first; if no card names the maker, every card (old place still shown)
          const count=page.locator('#catalog-count'),sentinel=page.locator('#catalog-sentinel');let places=[];
          for(const term of [target.place||'','']){
            await page.locator('#product-search').fill(term);await page.waitForTimeout(200);
            for(let i=0;i<30&&!/^(\d+) selections · \1 shown$/.test(await count.textContent());i++){
              await sentinel.scrollIntoViewIfNeeded();await page.waitForTimeout(100);
            }
            places=await page.locator('#catalog-grid article').evaluateAll((arts,label)=>arts.filter(a=>[...a.querySelectorAll(
              '.maker-story summary .sr-only')].some(s=>s.textContent===label)).map(a=>a.querySelector('.origin-label')?.textContent),
            `: ${target.name}`);
            if(places.length)break;
          }
          if(target.hidden)checks.makerHidden=places.length===0;
          else if(places.length){checks.makerName=true;checks.makerPlace=places[0]===`Based in ${target.place}`;}
          await cards.scrollIntoViewIfNeeded();
        }
        if(target.kind==='product'){
          const card=page.locator(`#catalog-grid article[data-product-id="${target.id}"]`);
          const count=await card.count();
          checks.productShown=count===(target.status==='active'?1:0);
          if(count===1){
            await card.scrollIntoViewIfNeeded();
            if(target.status==='active'){
              checks.description=(await card.locator('.food-description').textContent())===target.description;
              if('availability' in target){const a=card.locator('.availability');checks.availabilityShown=(await a.count()?await a.first().textContent():null)===target.availability;}
              if(target.image){const img=card.locator('img').first();await img.scrollIntoViewIfNeeded();
                checks.imageShown=await img.evaluate((e,src)=>e.getAttribute('src')===src&&e.complete&&e.naturalWidth>0,target.image).catch(()=>false);}
            }
          }
        }
      }else if(target.kind==='store'){
        const lines=target.hours||[],line=page.locator('#visit .visit p').first();
        await line.scrollIntoViewIfNeeded();
        const text=await page.locator('body').innerText();
        checks.hoursShown=lines.length>0&&lines.every(l=>text.includes(l));
        const s=target.streetAddress,t=target.town;
        if(s&&t)checks.addressShown=text.includes(`${s}, ${t}`)&&text.includes(`${s} · ${t}`);
        const h=target.headline||[];
        const ws=v=>String(v).replace(/\s+/g,' ').trim();  // HTML collapses runs of spaces; compare both sides the same way
        if(h.length===2){const h1=ws(await page.locator('.hero h1').innerText());checks.headlineShown=h.every(l=>h1.includes(ws(l)));}
        if('phone' in target){const a=page.locator('.visit-phone a'),d=String(target.phone||'').replace(/\D/g,'');
          checks.phoneShown=target.phone?await a.count()===1&&ws(await a.textContent())===target.phone&&await a.getAttribute('href')==='tel:+1'+d:await page.locator('.visit-phone').count()===0;}
        const intro=ws(await page.locator('.hero-intro').first().textContent());checks.introShown=intro===ws(target.intro||target.defaultIntro);
        if(target.selectionLine){checks.selectionShown=ws(await page.locator('.selection-checked').first().textContent().catch(()=>''))===ws(target.selectionLine);}
        if(typeof target.story==='string'){const p=page.locator('#visit > div > p:not(.signature):not(.label)').first();checks.storyShown=ws(await p.textContent())===ws(target.story);}
        if(typeof target.homeImage==='string'){const img=page.locator('.hero .hero-image').first();await img.scrollIntoViewIfNeeded();
          checks.homeImageShown=await img.evaluate((el,p)=>el.complete&&el.naturalWidth>0&&el.currentSrc.endsWith('/'+p),target.homeImage);}
        if(target.homeImageCleared===true){const img=page.locator('.hero .hero-image').first();await img.scrollIntoViewIfNeeded();
          checks.homeImageCleared=await img.evaluate(el=>el.complete&&el.naturalWidth>0&&el.currentSrc.endsWith('/assets/store.jpg'));}
        if(typeof target.notice==='string'){const n=page.locator('main > .home-notice');
          checks.noticeShown=await n.count()===1&&await n.isVisible()&&ws(await n.textContent())===ws(target.notice);}
      }
    }
    await page.waitForTimeout(150);
    await page.screenshot({path:out});
    checks.noPageErrors=errors.length===0;
    checks.noPosts=!blocked.some(m=>m!=='GET'&&m!=='HEAD');
    console.log(JSON.stringify({checks,blockedRequests:blocked.length}));
  }finally{await browser.close();}
})().catch(e=>{console.error(String((e&&e.message)||e).split('\n')[0]);process.exit(1);});

// Hass H06 private preview capture: one Chromium page of the isolated loopback site, plus checks.
// VIEWPORT: phone (default, 390x844) or desktop (1280x900); anything else exits 1 with "bad VIEWPORT".
// env: PREVIEW_URL (http://127.0.0.1:<port>), TARGET (JSON from hass/preview.py target_for), OUT (png path),
// PLAYWRIGHT_MODULE / CHROMIUM_PATH as in the storefront QA scripts. Only GET/HEAD to the preview origin is
// allowed; every other request (any POST, anything off 127.0.0.1) is aborted. Prints {"checks": {...}}.
// Maker: its place search, then all cards if none names it; card text compared (never a selector built from the name).
// hidden → makerHidden (no card names it); else makerName + makerPlace; a maker with no active card adds no maker check.
// Hike: scheduled → eventShown; completed → pastShown (journal entry, exact h3 title) (+ recapShown if a recap, in .trail-journal-recap); cancelled → rsvpGone (no RSVP button).
'use strict';
const VIEWPORTS={phone:{width:390,height:844},desktop:{width:1280,height:900}},vp=process.env.VIEWPORT||'phone';
if(!Object.hasOwn(VIEWPORTS,vp)){console.error('bad VIEWPORT');process.exit(1);}
const base=process.env.PREVIEW_URL,target=JSON.parse(process.env.TARGET||'{}'),out=process.env.OUT;
if(target.kind==='store'&&target.page&&!['about/index.html','getting-here/index.html','policies/index.html','faq/index.html'].includes(target.page)){console.error('bad template page');process.exit(1);}
// AV1104-10 operator design preview: {kind:'design',page:'home'|'hike'}; the page is a fixed enum checked before any navigation.
if(target.kind==='design'&&!['home','hike'].includes(target.page)){console.error('bad design page');process.exit(1);}
// AVB-19: a preview-only browser day (a future banner start), checked before the browser library is even loaded.
if(Object.hasOwn(target,'effectiveDay')){
  const d=target.effectiveDay;
  if(typeof d!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(d)||!Number.isFinite(Date.parse(d+'T12:00:00Z'))||new Date(d+'T12:00:00Z').toISOString().slice(0,10)!==d){console.error('bad effectiveDay');process.exit(1);}
}
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
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
    const page=await browser.newPage({viewport:VIEWPORTS[vp]}),errors=[],blocked=[],checks={};let unshown=false;
    if(target.effectiveDay)await page.clock.setFixedTime(new Date(target.effectiveDay+'T12:00:00-08:00'));
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>allowed(route.request())?route.continue():(blocked.push(route.request().method()),route.abort()));
    if(target.kind==='design'){  // pageLoaded: HTTP 200 and the page's own heading visible; noHorizontalOverflow at this viewport
      const hike=target.page==='hike',reply=await page.goto(base+(hike?'/hike':'/'),{waitUntil:'networkidle'});
      checks.pageLoaded=reply!==null&&reply.status()===200&&await page.locator(hike?'main h1':'.hero h1').first().isVisible();
      checks.noHorizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth);
    }else if(target.kind==='store'&&target.page){
      const reply=await page.goto(base+'/'+target.page,{waitUntil:'networkidle'});
      checks.pageLoaded=reply!==null&&reply.status()===200&&await page.locator('main h1').isVisible();
      checks.pageTitle=await page.locator('main h1').textContent()===target.pageTitle;
      checks.noHorizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth);
    }else if(target.kind==='event'){
      await page.goto(base+'/hike',{waitUntil:'networkidle'});
      if(target.status==='scheduled'){
        checks.eventShown=await page.locator('h2',{hasText:target.title}).count()>0;
        const ws=v=>String(v).replace(/\s+/g,' ').trim();  // AV1222-05: cards are read in page JS (title equal); a card's id is its RSVP button or calendar link
        const cards=await page.$$eval('.hike-event',(els,t)=>els.filter(c=>c.querySelector('h2')?.textContent===t.title).map(c=>{
          const facts={};for(const d of c.querySelectorAll('dt')){const dd=d.nextElementSibling?.cloneNode(true);dd?.querySelectorAll('a').forEach(a=>a.remove());
            (facts[d.textContent]??=[]).push(dd?dd.textContent.replace(/\s+/g,' ').replace(/\s*·\s*$/,'').trim():'');}
          return {ids:[c.id,c.querySelector('[data-rsvp]')?.dataset.rsvp,(c.querySelector('a.hike-ics')?.getAttribute('download')||'').replace(/\.ics$/,'')].filter(Boolean),
            date:c.querySelector('.hike-date')?.textContent,meet:[...c.querySelectorAll('dt')].filter(d=>d.textContent==='Meet').map(d=>d.nextElementSibling?.textContent),
            facts,places:[...c.querySelectorAll('p.club-small')].map(p=>p.textContent)};}),target);
        // identity: a card's id is its anchor (id attribute), RSVP button or calendar link; only a card naming this id counts, none is guessed
        const mine=cards.filter(c=>!!target.id&&c.ids.includes(target.id)),pool=mine;
        const LABEL={meetTime:'Meet at',meetingAddress:'Address',returnTime:'Back',walkTime:'Start'};
        // AV1109-12: the count the page was given, read GET-only from the preview origin by exact id; null when the API is silent or lacks the id.
        const seen=await page.evaluate(async id=>{try{const r=await fetch('/api/community',{cache:'no-store'});if(!r.ok)return null;const e=((await r.json()).events||[]).find(x=>x.id===id);return e?{capacity:e.capacity,remaining:e.remaining}:null}catch{return null}},target.id||'');
        const evaluate=card=>{
          const r={},when=new Date(target.startsAt),pt=o=>when.toLocaleString('en-US',{timeZone:'America/Los_Angeles',...o});
          r.dateShown=card.date===(when<=new Date()?`Today — started ${pt({hour:'numeric',minute:'2-digit'})}`:pt({weekday:'long',month:'long',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}));
          r.meetShown=target.meetingPoint?card.meet.length===1&&card.meet[0]===target.meetingPoint:card.meet.length===0;
          const n=target.capacity,open=target.rsvpEnabled&&!!target.meetingPoint&&when>new Date();  // community-server.py scheduled(): RSVPs close at startsAt
          const day=d=>d.toLocaleDateString('en-US',{timeZone:'America/Los_Angeles'}),started=when<=new Date()&&day(when)===day(new Date());  // AV1104-05 community.js: started today reads closed
          // HIKE-PAGE 3.3.1: "left" only from a count whose capacity is this hike's own (the observed API count; whole numbers, 0..capacity); a limit with no trusted count says so; never remaining inferred from capacity
          const left=seen&&Number.isInteger(n)&&seen.capacity===n&&Number.isInteger(seen.remaining)&&seen.remaining>=0&&seen.remaining<=n?seen.remaining:null;
          const want=started?'This hike has started, so RSVPs are closed.':!open?'RSVP details will be shared when confirmed.':n===null?'To join, ask at the Shack.':!Number.isInteger(n)||n<1?null
            :left===null?`Limited to ${n} people · availability unconfirmed; ask at the Shack`:left===0?'Full. Ask at the Shack to go on the waitlist.':`${left} spot${left===1?'':'s'} left`;
          r.placesShown=want!==null&&card.places.length===1&&card.places[0]===want;
          const ch=Object.entries(target.changed||{});  // each changed value must be the one under its own label
          const gone=target.cleared||[];  // a cleared field's labeled line must be absent
          if(ch.length||gone.length)r.fieldsShown=ch.every(([k,v])=>!!LABEL[k]&&(card.facts[LABEL[k]]||[]).length===1&&card.facts[LABEL[k]][0]===ws(v))&&gone.every(k=>!!LABEL[k]&&(card.facts[LABEL[k]]||[]).length===0);
          return r;
        };
        if(!pool.length)checks.eventShown=false;
        else if('startsAt' in target){  // community.js keeps hikeDate private (IIFE), so its dateLabel/hikeDate format is mirrored here
          let best=null,bestN=-1;
          for(const c of pool){const r=evaluate(c),k=Object.values(r).filter(Boolean).length;if(k>bestN){best=r;bestN=k;}}
          Object.assign(checks,best);
        }
      }
      else if(target.status==='completed'){  // AV1622-03: real journal entry (has .trail-journal-recap, so never a sample) whose h3 is exactly the target's title
        const recaps=await page.locator('#past-hikes .trail-journal-entry').evaluateAll((els,title)=>els.filter(d=>
          d.querySelector('.trail-journal-recap')&&d.querySelector('h3')?.textContent===title).map(d=>d.querySelector('.trail-journal-recap')?.textContent),target.title);
        checks.pastShown=recaps.length>0;
        if(target.recap)checks.recapShown=recaps[0]===target.recap;
      }else if(target.status==='cancelled'){  // the id is compared in page JS, never put into a selector
        checks.rsvpGone=await page.$$eval('[data-rsvp]',(els,id)=>els.filter(b=>b.dataset.rsvp===id).length,target.id||'')===0;
        if('cancelNote' in target){  // AV2152-07: one visible note paragraph for exactly this id, in a cancelled card, directly above the fixed sentence
          const notes=await page.$$eval('.hike-cancelled p.hike-cancel-note',(els,id)=>els.filter(p=>p.dataset.hikeId===id).map(p=>({text:p.textContent,
            next:p.nextElementSibling?.textContent,shown:!!(p.offsetWidth||p.offsetHeight)&&getComputedStyle(p).visibility!=='hidden'})),target.id||'');
          checks.cancelNoteShown=notes.length===1&&notes[0].shown&&notes[0].text===target.cancelNote&&notes[0].next==='This hike is cancelled. Nothing else is needed from you.';
        }
      }
    }else if(target.kind==='route'){  // AV1222-06: every place /hike shows this route (linked hike cards' Route line, the sample invitation) reads the title; compared as text in page JS
      await page.goto(base+'/hike',{waitUntil:'networkidle'});
      const got=await page.evaluate(async id=>{
        const get=async p=>{try{const r=await fetch(p,{cache:'no-store'});return r.ok&&(r.headers.get('Content-Type')||'').includes('json')?await r.json():null}catch{return null}};
        const club=(await get('/api/community'))||(await get('/community.json'))||{},pv=await get('/hiking-preview.json'),linked=(club.events||[]).filter(e=>e.trailId===id),ws=v=>String(v).replace(/\s+/g,' ').trim();
        const lines=[...document.querySelectorAll('#upcoming-hikes .hike-event')].filter(c=>{const key=[c.id,c.querySelector('[data-rsvp]')?.dataset.rsvp].filter(Boolean),h=c.querySelector('h2')?.textContent;
          return linked.some(e=>key.length?key.includes(e.id):h===e.title||h==='Cancelled: '+e.title);}).map(c=>{const r=c.querySelector('.hike-route');if(!r)return null;  // a card with no Route line stays in the list so it fails the check
          const link=r.querySelector('a');let before='';for(const n of r.childNodes){if(n===link)break;before+=n.textContent;}
          return {before:ws(before),link:!!link};});  // the title is the text before the source link, never the link text
        const t=document.querySelector('#featured-hike-title');
        // the sample archive (community.js sampleHistory) renders pv.past entries whose route idea exists, in order, only while there are no real past hikes
        const ent=[...document.querySelectorAll('#past-hikes .trail-journal-entry')],vis=(pv?.past||[]).filter(e=>(club.routeIdeas||[]).some(r=>r.id===e.trailId));
        const archive=vis.map((e,i)=>e.trailId===id&&ent.length===vis.length?ws(ent[i].querySelector('h3')?.textContent):null).filter(x=>x!==null);
        return {lines,archive,sample:t&&pv?.upcoming?.trailId===id?ws(t.childNodes[0]?.textContent):null};
      },target.id||'');
      const ws=v=>String(v).replace(/\s+/g,' ').trim(),title=ws(target.title),places=got.lines.length+got.archive.length+(got.sample===null?0:1);
      if(target.hidden)checks.routeGone=got.lines.filter(Boolean).length+got.archive.length+(got.sample===null?0:1)===0;
      else if(places>0)checks.routeShown=got.lines.every(l=>!!l&&l.before===(l.link?`Route: ${title} ·`:`Route: ${title}`))&&got.archive.every(a=>a===title)&&(got.sample===null||got.sample===title);
      else unshown=true;
    }else{
      await page.goto(base+'/?view=all',{waitUntil:'networkidle'});
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
        if(Array.isArray(target.sections)){
          const ids=await page.locator('main > section[id]').evaluateAll(els=>els.map(e=>e.id));
          checks.sectionsShown=JSON.stringify(ids)===JSON.stringify(target.sections);
        }
        if(Object.hasOwn(target,'banner')){
          const b=page.locator('div.preview[data-banner]:visible'),d=page.locator('div.preview[data-banner-default]:visible');
          if(target.banner){
            const link=b.locator('a');
            checks.bannerShown=await b.count()===1&&await b.locator('span').textContent()===target.banner.text&&await d.count()===0&&
              (target.banner.link?await link.count()===1&&await link.getAttribute('href')===target.banner.link:await link.count()===0);
          }else checks.bannerGone=await b.count()===0&&await page.locator('div.preview:visible').count()===1;
        }
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
        if(Array.isArray(target.specials)){const items=page.locator('main > .weekly-specials li:not([hidden])');  // AVO-SPECIALS-1
          const shown=await items.evaluateAll(els=>els.map(e=>[e.querySelector('h3').textContent,e.querySelector('.special-deal').textContent].map(v=>v.replace(/\s+/g,' ').trim())));
          const want=target.specials.map(s=>[s.title,s.deal].map(ws));
          checks.specialsShown=JSON.stringify(shown)===JSON.stringify(want)&&(want.length>0?await page.locator('main > .weekly-specials h2').isVisible():await page.locator('.weekly-specials').count()===0);}
        if(typeof target.notice==='string'){const n=page.locator('main > .home-notice');
          checks.noticeShown=await n.count()===1&&await n.isVisible()&&ws(await n.textContent())===ws(target.notice);}
        const w=target.noticeWindow;  // AV2152-08: a notice with its own first day: hidden before it, visible through the last day
        if(w&&typeof w==='object'){const n=page.locator('main > .home-notice'),c=await n.count();
          const same=async()=>ws(await n.textContent())===ws(w.text)&&await n.getAttribute('data-from')===w.from&&await n.getAttribute('data-until')===w.until;
          checks.noticeWindow=w.state==='ended'?(c===0||c===1&&await same()&&!await n.isVisible())
            :c===1&&await same()&&await n.isVisible()===(w.state==='active');}
      }
    }
    if(target.kind==='store'&&(Array.isArray(target.sections)||Object.hasOwn(target,'banner'))){  // AVB-19 front changes
      checks.pageLoaded=await page.locator('.hero h1').first().isVisible();
      checks.noHorizontalOverflow=await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth);
      // the picture shows what changed: the first home part for a new order, else the top strip
      if(Array.isArray(target.sections))await page.locator('main > section[id]').first().evaluate(e=>e.scrollIntoView({block:'start'}));
      else await page.evaluate(()=>window.scrollTo(0,0));
    }
    await page.waitForTimeout(150);
    await page.screenshot({path:out});
    checks.noPageErrors=errors.length===0;
    checks.noPosts=!blocked.some(m=>m!=='GET'&&m!=='HEAD');
    console.log(JSON.stringify({checks,blockedRequests:blocked.length,...(unshown?{unshown:true}:{})}));
  }finally{await browser.close();}
})().catch(e=>{console.error(String((e&&e.message)||e).split('\n')[0]);process.exit(1);});

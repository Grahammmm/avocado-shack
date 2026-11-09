// HASS-NEWITEM-1 offline preview: the new item's shelf card next to two existing cards, same page, same styles.
// Same contract as hass/screenshot.cjs (H06): one Chromium page of the isolated loopback copy of the site, only GET/HEAD to the
// preview origin, env PREVIEW_URL, TARGET (JSON), OUT (png), VIEWPORT (phone 390x844 | desktop 1280x900), PLAYWRIGHT_MODULE / CHROMIUM_PATH.
// TARGET: {kind:'compare', id, term, name, description, alt, image, maker, availability}. term is typed in the page's own
// search box so the new card and neighbours of the same kind show together; the maker story of each shown card is opened.
// Prints one last line {"checks": {...}, "cards": [...]} where checks are all booleans (preview.py reads only those).
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
    const page=await browser.newPage({viewport:VIEWPORTS[vp]}),errors=[],checks={};
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>allowed(route.request())?route.continue():route.abort());
    await page.goto(base+'/',{waitUntil:'networkidle'});
    await page.locator('#product-search').fill(target.term||'');
    await page.waitForTimeout(400);
    for(let i=0;i<40;i++){  // the page loads cards in batches as the sentinel scrolls into view: bring the new card in
      if(await page.locator(`#catalog-grid article[data-product-id="${target.id}"]`).count())break;
      await page.locator('#catalog-sentinel').scrollIntoViewIfNeeded().catch(()=>{});
      await page.waitForTimeout(120);
    }
    await page.locator(`#catalog-grid article[data-product-id="${target.id}"]`).first().waitFor({timeout:4000}).catch(()=>{});
    const cards=await page.evaluate(id=>{
      const arts=[...document.querySelectorAll('#catalog-grid article')];
      const mine=arts.find(a=>a.dataset.productId===id);
      const pick=[];
      if(mine){
        pick.push(mine);
        const at=arts.indexOf(mine);  // the cards printed right next to it: the two before, else the two after
        for(let d=1;d<arts.length&&pick.length<3;d++){
          for(const j of [at-d,at+d]){if(pick.length<3&&arts[j]&&arts[j].querySelector('img'))pick.push(arts[j]);}
        }
      }
      pick.sort((a,b)=>arts.indexOf(a)-arts.indexOf(b));
      pick.forEach(a=>{const d=a.querySelector('details');if(d)d.open=true;});
      return pick.map(a=>{
        const d=a.querySelector('details');if(d)d.open=true;
        const img=a.querySelector('img'),desc=a.querySelector('.food-description'),h=a.querySelector('h3'),meta=a.querySelector('.product-meta');
        const cs=(el,props)=>el?Object.fromEntries(props.map(p=>[p,getComputedStyle(el)[p]])):null;
        const box=el=>{const r=el.getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,w:r.width,h:r.height};};
        const av=a.querySelector('.availability');
        return {id:a.dataset.productId,mine:a.dataset.productId===id,box:box(a),img:img?{src:img.getAttribute('src'),alt:img.getAttribute('alt'),natural:[img.naturalWidth,img.naturalHeight],ok:img.complete&&img.naturalWidth>0,
          rendered:[Math.round(img.getBoundingClientRect().width),Math.round(img.getBoundingClientRect().height)],fit:getComputedStyle(img).objectFit}:null,
          desc:desc?{text:desc.textContent,style:cs(desc,['fontSize','fontFamily','color','lineHeight'])}:null,
          title:cs(h,['fontSize','fontFamily','color']),meta:meta?meta.textContent:'',name:h?h.textContent:'',
          story:d?d.querySelector('.maker-story-content p')?.textContent||'':'',summary:d?d.querySelector('summary')?.textContent||'':'',
          availability:av?av.textContent:null};
      });
    },target.id);
    const mine=cards.find(c=>c.mine),others=cards.filter(c=>!c.mine);
    checks.cardShown=!!mine;
    checks.hasNeighbours=others.length>=2;
    if(mine){
      checks.imageLoaded=!!(mine.img&&mine.img.ok);
      checks.imageSrcIsTheDraftsPhoto=!!mine.img&&mine.img.src===target.image;
      checks.imageAltShown=!!mine.img&&mine.img.alt===target.alt;
      checks.descriptionShown=!!mine.desc&&mine.desc.text===target.description;
      checks.imageBoxSameAsNeighbours=others.length>0&&others.every(o=>o.img&&mine.img&&o.img.rendered.join('x')===mine.img.rendered.join('x')&&o.img.fit===mine.img.fit);
      checks.descriptionTypeSameAsNeighbours=others.length>0&&others.every(o=>o.desc&&mine.desc&&JSON.stringify(o.desc.style)===JSON.stringify(mine.desc.style));
      checks.titleTypeSameAsNeighbours=others.length>0&&others.every(o=>JSON.stringify(o.title)===JSON.stringify(mine.title));
      checks.cardWidthSameAsNeighbours=others.length>0&&others.every(o=>Math.abs(o.box.w-mine.box.w)<=1);
      if(target.maker)checks.makerNameShown=mine.summary.includes(target.maker)&&mine.meta===target.maker;
      if(target.makerStory)checks.makerStoryShown=mine.story===target.makerStory;
      if('availability' in target)checks.availabilityShown=mine.availability===target.availability;
    }
    checks.noPageErrors=errors.length===0;
    const sel=cards;
    if(sel.length){
      const x=Math.max(0,Math.min(...sel.map(c=>c.box.x))-8),y=Math.max(0,Math.min(...sel.map(c=>c.box.y))-8);
      const x2=Math.max(...sel.map(c=>c.box.x+c.box.w))+8,y2=Math.max(...sel.map(c=>c.box.y+c.box.h))+8;
      await page.screenshot({path:out,fullPage:true,clip:{x,y,width:x2-x,height:y2-y}});
    }else await page.screenshot({path:out});
    const slim=cards.map(c=>({id:c.id,mine:c.mine,name:c.name,brand:c.meta,img:c.img&&{rendered:c.img.rendered,natural:c.img.natural,fit:c.img.fit},fontSize:c.desc&&c.desc.style.fontSize}));
    console.log(JSON.stringify({checks,cards:slim,errors}));
  }finally{await browser.close();}
})().catch(e=>{console.error(String(e&&e.stack||e));process.exit(1);});

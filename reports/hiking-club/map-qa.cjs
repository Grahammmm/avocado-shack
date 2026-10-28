const {chromium,webkit}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const base=process.env.PREVIEW_URL||'http://127.0.0.1:3103';
const out=process.env.QA_OUT_DIR||'/tmp/avoshack-map-qa';fs.mkdirSync(out,{recursive:true});
const result={checkedAt:new Date().toISOString(),base,viewports:[],interactions:[],errors:[],externalRequests:[]};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,reducedMotion:'reduce'});
 const p=await context.newPage();const posts=[];
 p.on('pageerror',e=>result.errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push(r.url());if(!r.url().startsWith(base)&&!r.url().startsWith('data:'))result.externalRequests.push(r.url());});
 await p.goto(base+'/#hikes');await p.waitForSelector('[data-trail-explorer][data-ready=true]');
 const data=await (await p.request.get(base+'/assets/trails/point-buchon.json')).json();
 assert.equal(data.profile.length,217);assert.ok(data.distanceMeters>10600&&data.distanceMeters<10800);
 let ascent=0,descent=0;for(let i=1;i<data.profile.length;i++){const delta=data.profile[i].elevationMeters-data.profile[i-1].elevationMeters;ascent+=Math.max(0,delta);descent+=Math.max(0,-delta);assert.ok(data.profile[i].distanceMeters>data.profile[i-1].distanceMeters);}
 assert.ok(Math.abs(ascent-data.gainMeters)<.01);assert.ok(Math.abs(descent-data.lossMeters)<.01);assert.ok(Math.abs(ascent-descent)<.001);
 for(const asset of ['point-buchon-aerial.webp','point-buchon-topo.webp','point-buchon-coast.webp'])assert.equal((await p.request.get(base+'/assets/trails/'+asset)).status(),200);
 const map=p.locator('.trail-map-stage'),canvas=p.locator('.trail-map-canvas');
 await p.getByRole('button',{name:'Topo',exact:true}).click();assert.equal(await map.getAttribute('data-layer'),'topo');assert.equal(await p.getByRole('button',{name:'Topo',exact:true}).getAttribute('aria-pressed'),'true');assert.match(await p.locator('.trail-basemap').getAttribute('href'),/topo.webp$/);
 await p.getByRole('button',{name:'Aerial',exact:true}).click();
 await map.scrollIntoViewIfNeeded();const before=await canvas.getAttribute('viewBox');
 await p.getByRole('button',{name:'Zoom in',exact:true}).click();assert.equal(await map.getAttribute('data-zoom'),'1.60');assert.notEqual(await canvas.getAttribute('viewBox'),before);
 let box=await map.boundingBox();let old=await canvas.getAttribute('viewBox');await p.mouse.move(box.x+box.width*.4,box.y+box.height*.5);await p.mouse.down();await p.mouse.move(box.x+box.width*.4+35,box.y+box.height*.5+45,{steps:5});await p.mouse.up();assert.notEqual(await canvas.getAttribute('viewBox'),old);
 await p.getByRole('button',{name:'Show full route'}).click();assert.equal(await map.getAttribute('data-zoom'),'1.00');
 await map.focus();await p.keyboard.press('+');assert.equal(await map.getAttribute('data-zoom'),'1.60');old=await canvas.getAttribute('viewBox');await p.keyboard.press('ArrowDown');assert.notEqual(await canvas.getAttribute('viewBox'),old);await p.keyboard.press('Home');assert.equal(await map.getAttribute('data-zoom'),'1.00');
 result.interactions.push('Aerial/topo switch; zoom; drag; fit; keyboard zoom/pan/reset');
 const slider=p.locator('#trail-distance');const start=await p.locator('.trail-position-dot').getAttribute('cx');
 await slider.fill('108');assert.match(await p.locator('#trail-elevation-readout').textContent(),/3.3 mi/);assert.notEqual(await p.locator('.trail-position-dot').getAttribute('cx'),start);
 await slider.fill('216');assert.equal(await p.locator('.trail-position-dot').getAttribute('cx'),start);assert.match(await slider.getAttribute('aria-valuetext'),/return/);await slider.focus();await p.keyboard.press('ArrowLeft');assert.equal(await slider.inputValue(),'215');
 result.interactions.push('Elevation scrub tracks mapped position; turnaround; matching return endpoint; keyboard slider');
 await p.getByRole('button',{name:'Enlarge map',exact:true}).click();assert.equal(await p.locator('dialog.trail-map-dialog').evaluate(e=>e.open),true);assert.equal(await p.locator('dialog.trail-map-dialog .trail-explorer').count(),1);await p.keyboard.press('Escape');await p.locator('dialog.trail-map-dialog').waitFor({state:'detached'});assert.equal(await p.locator('dialog.trail-map-dialog').count(),0);assert.equal(await p.getByRole('button',{name:'Enlarge map',exact:true}).evaluate(e=>e===document.activeElement),true);
 result.interactions.push('Expanded map; Escape closes; focus restored');
 // The requested sample RSVP must remain a browser-only interaction.
 await p.locator('#preview-rsvp-name').fill('Map QA');await p.locator('#preview-rsvp-email').fill('map-qa@example.invalid');await p.locator('#preview-hike-rsvp button').click();assert.match(await p.locator('#preview-hike-rsvp .form-status').innerText(),/No details were saved or sent/);assert.equal(posts.length,0);assert.deepEqual(await p.evaluate(()=>({local:localStorage.length,session:sessionStorage.length})),{local:0,session:0});
 result.interactions.push('Dummy RSVP: no POST, no storage');
 // Touch scroll at default zoom; touch drag after zooming in.
 await map.scrollIntoViewIfNeeded();await p.waitForTimeout(100);box=await map.boundingBox();const cdp=await context.newCDPSession(p);
 const touch=async()=>{const x=box.x+box.width*.45,y=box.y+box.height*.65;await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x,y}]});for(let i=1;i<=6;i++){await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x,y:y-i*18}]});await p.waitForTimeout(20);}await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await p.waitForTimeout(350);};
 let scroll=await p.evaluate(()=>scrollY);await touch();assert.ok(await p.evaluate(()=>scrollY)>scroll+25,'Page scroll was trapped by unzoomed map');
 await map.scrollIntoViewIfNeeded();await p.getByRole('button',{name:'Zoom in',exact:true}).click();box=await map.boundingBox();old=await canvas.getAttribute('viewBox');scroll=await p.evaluate(()=>scrollY);await touch();assert.notEqual(await canvas.getAttribute('viewBox'),old);assert.ok(Math.abs(await p.evaluate(()=>scrollY)-scroll)<5,'Zoomed touch pan scrolled the page');await p.getByRole('button',{name:'Show full route'}).click();
 result.interactions.push('Phone touch: scroll page normally; zoom then pan map');
 for(const width of [320,375,390,430,768,1024,1440,1920]){
  await p.setViewportSize({width,height:900});await p.waitForTimeout(100);await map.scrollIntoViewIfNeeded();
  const check=await p.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,shortControls:[...document.querySelectorAll('.trail-explorer button')].filter(e=>e.getBoundingClientRect().height<44).length,mapWidth:document.querySelector('.trail-map-stage').clientWidth,mapHeight:document.querySelector('.trail-map-stage').clientHeight}));assert.equal(check.overflow,false,'Overflow at '+width);assert.equal(check.shortControls,0,'Small controls at '+width);result.viewports.push({width,...check});
  if(width===390||width===1440){await p.locator('.trail-explorer').screenshot({path:path.join(out,`trail-aerial-${width}.png`)});await p.getByRole('button',{name:'Topo',exact:true}).click();await p.waitForTimeout(200);await p.locator('.trail-explorer').screenshot({path:path.join(out,`trail-topo-${width}.png`)});await p.getByRole('button',{name:'Aerial',exact:true}).click();}
 }
 assert.deepEqual(result.errors,[]);assert.deepEqual(result.externalRequests,[]);
 await browser.close();
 if(fs.existsSync(webkit.executablePath())){
  const safari=await webkit.launch({headless:true});const page=await safari.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});await page.goto(base+'/#hikes');await page.waitForSelector('[data-trail-explorer][data-ready=true]');await page.getByRole('button',{name:'Topo',exact:true}).click();assert.equal(await page.locator('.trail-map-stage').getAttribute('data-layer'),'topo');await page.getByRole('button',{name:'Enlarge map',exact:true}).click();await page.getByRole('button',{name:'Close map ×',exact:true}).click();await page.locator('dialog.trail-map-dialog').waitFor({state:'detached'});assert.equal(await page.locator('dialog.trail-map-dialog').count(),0);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);result.webkit='Phone-size WebKit layer and dialog smoke checks passed';await safari.close();
 }else result.webkit='Not installed; no Safari engine check performed';
 result.passed=true;fs.writeFileSync(path.join(out,'map-QA.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
})().catch(e=>{result.passed=false;result.failure=e.stack;fs.writeFileSync(path.join(out,'map-QA.json'),JSON.stringify(result,null,2));console.error(e);process.exit(1)});

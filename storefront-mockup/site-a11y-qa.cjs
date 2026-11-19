// AV1238-03: read-only WCAG 2.2 AA collector (everything except contrast, which site-contrast-qa.py covers). Takes no argument:
//   PLAYWRIGHT_MODULE=<playwright> PLAYWRIGHT_BROWSERS_PATH=<browsers> node storefront-mockup/site-a11y-qa.cjs
// It publishes the site into a fresh scratch folder (hass/sitegen.py --publish, then --check-publish), serves it on loopback only
// (every other host and every non-GET request is aborted and counted), opens /, /hike/ and /404.html at 390 and 1440 px, and prints
// ONE JSON document. The /api/community answer in the "service" state is a synthetic fixture; nothing is submitted, nothing is real.
const fs=require('fs'),os=require('os'),path=require('path'),http=require('http'),cp=require('child_process');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const repo=fs.realpathSync(path.resolve(__dirname,'..')),tmp=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'avo-a11y-'))),site=path.join(tmp,'site');
if(tmp===repo||tmp.startsWith(repo+path.sep)){process.stderr.write('a11y QA refused: scratch folder is inside the repository\n');process.exit(2)}
const py=(...a)=>cp.execFileSync('python3',['hass/sitegen.py',...a],{cwd:repo,encoding:'utf8'}).trim();
const published=py('--publish',site),checked=py('--check-publish',site),sha=cp.execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim();
const ROUTES=['/','/hike/','/404.html'],WIDTHS=[390,1440],FIXED='2026-11-05T20:00:00Z',NO_SERVICE='<meta name="club-service" content="none">';
const TYPES={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.json':'application/json','.webp':'image/webp','.png':'image/png','.jpg':'image/jpeg'};
const page404=fs.readFileSync(path.join(site,'404.html')),ideas=JSON.parse(fs.readFileSync(path.join(site,'community.json'),'utf8')).routeIdeas;
const api={acceptsSubmissions:true,routeIdeas:ideas,events:[{id:'a11y-walk',title:'Synthetic keyboard walk',status:'scheduled',startsAt:'2026-12-06T09:00:00-08:00',timezone:'America/Los_Angeles',meetingPoint:'Synthetic trailhead',trailId:'idea-point-buchon',rsvpOpen:true,rsvpEnabled:true,capacity:6,remaining:6,confirmedGuests:0}]};
const seen={nonLoopback:0,nonGet:0,hosts:[]};
const server=http.createServer((req,res)=>{let file=path.join(site,decodeURIComponent(new URL(req.url,'http://x').pathname));
 try{if(fs.statSync(file).isDirectory())file=path.join(file,'index.html')}catch{}
 fs.readFile(file,(err,d)=>{if(err||!file.startsWith(site)){res.writeHead(404,{'Content-Type':TYPES['.html']});return res.end(page404)}
  if(req.headers['x-qa-club-service']&&file.endsWith('.html'))d=Buffer.from(d.toString('utf8').replace(NO_SERVICE,''));
  res.writeHead(200,{'Content-Type':TYPES[path.extname(file)]||'application/octet-stream'});res.end(d)})});
// Page-side helpers (window.__a), injected before any page script.
const HELP=()=>{const A=window.__a={},ids=new WeakMap();let n=0;
 A.vis=e=>{const d=e.parentElement?.closest('details:not([open])');if(d&&!(e.tagName==='SUMMARY'&&e.parentElement===d))return false;return e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden'};
 A.id=e=>{if(!ids.has(e))ids.set(e,++n);return ids.get(e)};
 A.desc=e=>{const c=typeof e.className==='string'?e.className.trim().split(/\s+/)[0]:'',k=Object.keys(e.dataset||{}).find(x=>!/^a11y/.test(x)),t=(e.getAttribute('aria-label')||e.textContent||e.getAttribute('alt')||e.value||'').replace(/\s+/g,' ').trim().slice(0,28);
  return e.tagName.toLowerCase()+(e.id?'#'+e.id:c?'.'+c:'')+(k?'[data-'+k.replace(/[A-Z]/g,m=>'-'+m.toLowerCase())+']':'')+(t?' "'+t+'"':'')};
 A.kind=e=>e.tagName+'|'+(e.id||String(e.className).split(' ')[0])+'|'+(e.closest('dialog[open]')?'dialog':'page')+'|'+(e.type||'');
 A.cover=e=>{const r=e.getBoundingClientRect();let p=0,c=0,by='';for(const [fx,fy] of [[.5,.5],[.1,.1],[.9,.1],[.1,.9],[.9,.9]]){const x=r.left+r.width*fx,y=r.top+r.height*fy;if(x<0||y<0||x>=innerWidth||y>=innerHeight)continue;p++;const h=document.elementFromPoint(x,y);if(!h||!(h===e||e.contains(h)||h.contains(e))){c++;by=by||(h?A.desc(h):'nothing')}}return {p,c,by}};
 // Resolves with the focused element once the page and the open dialog have stopped scrolling (the site sets scroll-behavior:smooth).
 A.stop=()=>new Promise(res=>{let last='',k=0;const f=()=>{const e=document.activeElement,s=scrollY+':'+(e?.closest?.('dialog')?.scrollTop||0);if(s===last&&++k>2)return res(A.read());if(s!==last)k=0;last=s;requestAnimationFrame(f)};f()});
 A.read=()=>{const e=document.activeElement;if(!e||e===document.body)return {body:true};e.setAttribute('data-a11y-hit','1');const r=e.getBoundingClientRect(),cs=getComputedStyle(e),cv=A.cover(e);
  return {id:A.id(e),d:A.desc(e),kind:A.kind(e),x:r.left,y:r.top+scrollY,w:r.width,h:r.height,inView:r.bottom>0&&r.top<innerHeight,tabindex:e.getAttribute('tabindex'),dialog:!!e.closest('dialog[open]'),points:cv.p,covered:cv.c,by:cv.by,
   outline:cs.outlineStyle+' '+cs.outlineWidth+' '+cs.outlineColor,clip:{x:Math.max(0,r.left-6),y:Math.max(0,r.top-6),width:Math.min(innerWidth,r.width+12),height:Math.min(innerHeight,r.height+12)}}};
};
// Static scan of the current DOM (or of the open dialog only when one is open).
const SCAN=()=>{const A=window.__a,dlg=document.querySelector('dialog[open]'),root=dlg||document,all=s=>[...root.querySelectorAll(s)].filter(A.vis);
 const imgs=all('img'),svgs=all('svg:not(svg svg)'),rimg=all('[role=img]:not(svg)');
 const heads=[...document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role=heading]')].filter(A.vis).map(h=>({l:+(h.getAttribute('aria-level')||h.tagName[1]),t:h.textContent.trim().slice(0,30),dlg:!!h.closest('dialog')}));
 const ctl=all('input:not([type=hidden]),select,textarea').map(e=>({d:A.desc(e),labels:e.labels.length,aria:!!(e.getAttribute('aria-label')||e.getAttribute('aria-labelledby')),disabled:e.disabled,label:(e.labels[0]?.textContent||'').trim().slice(0,40),ariaLabel:e.getAttribute('aria-label'),placeholder:e.getAttribute('placeholder')}));
 const idc={};document.querySelectorAll('[id]').forEach(e=>idc[e.id]=(idc[e.id]||0)+1);
 const hi=[],hs=heads.filter(h=>!h.dlg);hs.forEach((h,i)=>{if(i&&h.l-hs[i-1].l>1)hi.push(`h${hs[i-1].l} "${hs[i-1].t}" -> h${h.l} "${h.t}"`);if(!h.t)hi.push('empty h'+h.l)});if(hs.filter(h=>h.l===1).length!==1)hi.push('h1 count '+hs.filter(h=>h.l===1).length);if(hs[0]&&hs[0].l!==1)hi.push('first heading is h'+hs[0].l);
 const dangling=[...document.querySelectorAll('label[for],[aria-labelledby],[aria-describedby]')].flatMap(e=>[e.getAttribute('for'),...(e.getAttribute('aria-labelledby')||'').split(/\s+/),...(e.getAttribute('aria-describedby')||'').split(/\s+/)].filter(Boolean).filter(i=>!document.getElementById(i)).map(i=>A.desc(e)+' -> #'+i));
 const els=[...root.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[tabindex],[role],[aria-label],[aria-labelledby],dialog')].filter(e=>A.vis(e)||e===dlg);
 els.forEach((e,i)=>e.setAttribute('data-a11y',i));
 const tg=[...root.querySelectorAll('a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button]')].filter(e=>A.vis(e)&&!e.classList.contains('sr-only')).map(e=>{const box=e.type==='checkbox'||e.type==='radio'?e.closest('label')||e:e,r=box.getBoundingClientRect();
  return {d:A.desc(e),x:r.left+scrollX,y:r.top+scrollY,w:r.width,h:r.height,inline:getComputedStyle(e).display==='inline'&&[...e.parentNode.childNodes].some(n=>n.nodeType===3&&n.textContent.trim()),disabled:!!e.disabled}});
 const fixed=[...document.querySelectorAll('*')].filter(e=>/fixed|sticky/.test(getComputedStyle(e).position)&&A.vis(e)).map(A.desc);
 return {images:{img:imgs.length,noAlt:imgs.filter(i=>!i.hasAttribute('alt')).map(A.desc),emptyAlt:imgs.filter(i=>i.getAttribute('alt')==='').length,fileAlt:imgs.filter(i=>/\.(jpe?g|png|webp)|^img_/i.test(i.getAttribute('alt')||'')).map(A.desc),
  svg:svgs.length,svgHidden:svgs.filter(s=>s.closest('[aria-hidden=true]')).length,svgUnnamed:svgs.filter(s=>!s.closest('[aria-hidden=true]')&&!s.getAttribute('aria-label')&&!s.querySelector('title')).map(A.desc),roleImg:rimg.length,roleImgUnnamed:rimg.filter(s=>!s.getAttribute('aria-label')).map(A.desc)},
  headings:heads,headingIssues:hi,cards:document.querySelectorAll('#catalog-grid article').length,outsideLandmarks:[...document.body.children].filter(c=>!/^(HEADER|MAIN|FOOTER|SCRIPT|DIALOG|A)$/.test(c.tagName)&&A.vis(c)).map(A.desc),controls:ctl,dupIds:Object.keys(idc).filter(k=>idc[k]>1),dangling,targets:tg,fixed,toast:!!document.querySelector('#toast'),
  tagged:els.map((e,i)=>({i,d:A.desc(e),tag:e.tagName.toLowerCase(),interactive:e.matches('a[href],button,input,select,textarea,summary,[tabindex],[role=button],[role=slider]'),aria:!!(e.getAttribute('aria-label')||e.getAttribute('aria-labelledby')),ariaHidden:!!e.closest('[aria-hidden=true]'),disabled:!!e.disabled,tabindex:e.getAttribute('tabindex'),hit:e.hasAttribute('data-a11y-hit')}))};};
// 2.5.8: a target under 24x24 passes if it is inline in text, or if a 24px circle on its centre touches no other target and no other undersized target's circle.
const targetFails=ts=>{const live=ts.filter(t=>!t.disabled&&t.w>0&&t.h>0),small=live.filter(t=>(t.w<24||t.h<24)&&!t.inline),cc=t=>({x:t.x+t.w/2,y:t.y+t.h/2});
 const hitRect=(c,t)=>{const dx=Math.max(t.x-c.x,0,c.x-(t.x+t.w)),dy=Math.max(t.y-c.y,0,c.y-(t.y+t.h));return dx*dx+dy*dy<144};
 const names=l=>l.map(t=>`${t.d} ${Math.round(t.w)}x${Math.round(t.h)}`),fail=small.filter(t=>live.some(o=>o!==t&&(hitRect(cc(t),o)||((o.w<24||o.h<24)&&!o.inline&&Math.hypot(cc(t).x-cc(o).x,cc(t).y-cc(o).y)<24))));
 return {measured:live.length,undersized:small.length,inline:live.filter(t=>(t.w<24||t.h<24)&&t.inline).length,smallest:names(live.slice().sort((a,b)=>Math.min(a.w,a.h)-Math.min(b.w,b.h)).slice(0,3)),fail:names(fail),spacedOk:names(small.filter(t=>!fail.includes(t)))}};
const same=(a,b)=>Buffer.compare(a,b)===0;
async function indicatorSeen(page,clip){const a=await page.screenshot({clip});await page.evaluate(()=>{window.__cur=document.activeElement;window.__cur.blur()});const b=await page.screenshot({clip});await page.evaluate(()=>window.__cur.focus({preventScroll:true}));return !same(a,b)}
async function ax(page,cdp,tagged){await cdp.send('DOM.enable');const {root}=await cdp.send('DOM.getDocument',{depth:-1,pierce:true}),byIdx={};
 const walk=n=>{const a=n.attributes||[],i=a.indexOf('data-a11y');if(i>=0)byIdx[a[i+1]]=n.backendNodeId;[...(n.children||[]),...(n.contentDocument?[n.contentDocument]:[])].forEach(walk)};walk(root);
 const {nodes}=await cdp.send('Accessibility.getFullAXTree'),back={},roles={};
 for(const n of nodes){if(n.ignored)continue;if(n.backendDOMNodeId)back[n.backendDOMNodeId]={role:n.role?.value,name:n.name?.value||''};roles[n.role?.value]=(roles[n.role?.value]||0)+1}
 const named=n=>nodes.filter(x=>!x.ignored&&x.role?.value===n).map(x=>x.name?.value||'(no name)');
 const rows=tagged.map(t=>({...t,...(back[byIdx[t.i]]||{role:'(not in accessibility tree)',name:''})}));
 return {landmarks:{banner:named('banner'),main:named('main'),contentinfo:named('contentinfo'),navigation:named('navigation'),region:named('region'),form:named('form'),dialog:named('dialog')},
  noName:rows.filter(r=>r.interactive&&!r.name&&!/^(dialog|generic)$/.test(r.role)).map(r=>`${r.d} role=${r.role}`),
  hiddenFocusable:rows.filter(r=>r.interactive&&r.ariaHidden&&!r.disabled&&r.tabindex!=='-1').map(r=>r.d),
  genericNamed:rows.filter(r=>r.aria&&/^(generic|none|)$/.test(r.role||'')).map(r=>`${r.d} role=${r.role}`),
  notInTree:rows.filter(r=>r.interactive&&!r.disabled&&r.role==='(not in accessibility tree)').map(r=>r.d),
  kinds:[...new Set(rows.filter(r=>r.interactive).map(r=>`${r.role}: ${r.name.slice(0,30)||'-'}`))].slice(0,70),interactive:rows.filter(r=>r.interactive).length,rows}}
// 2.1.1 / 2.4.3 / 2.4.7 / 2.4.11: Tab from the top, one stop at a time. Each stop is checked for coverage (elementFromPoint at 5 points) and
// each new kind of control is compared pixel-for-pixel focused versus blurred (no change = no visible indicator).
async function tabWalk(page,cap,kindsDone,out,opts={}){const ids=new Set(),stops=[];let prev=null;
 for(let i=0;i<cap;i++){await page.keyboard.press(opts.reverse?'Shift+Tab':'Tab');const s=await page.evaluate(()=>window.__a.stop());
  if(s.body||ids.has(s.id)){out.ended=s.body?'left the document':'wrapped to the first stop';break}ids.add(s.id);
  if(!kindsDone.has(s.kind)&&s.inView&&s.w>0){kindsDone.add(s.kind);if(!await indicatorSeen(page,s.clip))out.noIndicator.push(`${s.d} (${s.kind})`)}
  if(s.points>0&&s.covered===s.points)out.hidden.push(`${s.d} by ${s.by}`);else if(s.covered>0)out.partlyCovered.push(`${s.d} ${s.covered}/${s.points} points under ${s.by}`);
  if(!s.inView)out.offScreen.push(s.d);if(s.tabindex&&+s.tabindex>0)out.positiveTabindex.push(s.d);
  if(prev&&prev.y-s.y>240&&!s.dialog)out.backwards.push(`${prev.d} -> ${s.d}`);prev=s;stops.push(s.d)}
 out.stops=stops.length;out.first=stops.slice(0,6);out.last=stops.slice(-3);out.list=stops;return out}
const newWalk=()=>({noIndicator:[],hidden:[],partlyCovered:[],offScreen:[],positiveTabindex:[],backwards:[]});
const focusKey=async(page,sel,key)=>{await page.focus(sel);await page.keyboard.press(key)};
async function open(browser,route,width,service){const ctx=await browser.newContext({viewport:{width,height:width<800?844:900},reducedMotion:'reduce',timezoneId:'America/Los_Angeles',extraHTTPHeaders:service?{'x-qa-club-service':'1'}:{}});
 await ctx.addInitScript(`(${HELP})()`);
 await ctx.route('**/*',r=>{const q=r.request(),u=new URL(q.url());if(!/^https?:$/.test(u.protocol))return r.continue();if(u.hostname!=='127.0.0.1'){seen.nonLoopback++;seen.hosts.push(u.hostname);return r.abort()}if(q.method()!=='GET'&&q.method()!=='HEAD'){seen.nonGet++;return r.abort()}
  if(service&&u.pathname==='/api/community')return r.fulfill({contentType:'application/json',body:JSON.stringify(api)});r.continue()});
 const page=await ctx.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.clock.setFixedTime(new Date(FIXED));await page.goto(`http://127.0.0.1:${server.address().port}${route}`);await page.waitForLoadState('networkidle');
 if(route==='/')await page.locator('#catalog-grid article').first().waitFor();if(route==='/hike/')await page.locator('#upcoming-hikes article').first().waitFor();
 return {ctx,page,errors}}
// One dialog opened by keyboard: where focus lands, the Tab cycle inside it, Escape, and where focus returns (close/return focus is also asserted by static-site-qa.cjs:265-266).
async function dialogTest(page,opener,name,kindsDone){const out={name,...newWalk()};
 await focusKey(page,opener,'Enter');await page.locator('dialog[open]').waitFor({timeout:3000}).catch(()=>{});out.opened=await page.evaluate(()=>!!document.querySelector('dialog[open]'));
 if(!out.opened)return {...out,note:'did not open'};
 out.landed=await page.evaluate(()=>window.__a.stop()).then(s=>s.d||'body');const sc=await page.evaluate(SCAN);out.targets=targetFails(sc.targets);out.unlabelled=sc.controls.filter(c=>!c.labels&&!c.aria).map(c=>c.d);out.controlCount=sc.controls.length;out.fixed=sc.fixed;out.label=await page.evaluate(()=>{const d=document.querySelector('dialog[open]'),l=d.getAttribute('aria-labelledby');return d.getAttribute('aria-label')||(l&&document.getElementById(l)?.textContent)||null});out.scrollable=await page.evaluate(()=>{const d=document.querySelector('dialog[open]');return d.scrollHeight>d.clientHeight});
 await tabWalk(page,14,kindsDone,out);out.escapeCloses=await page.keyboard.press('Escape').then(()=>page.evaluate(()=>!document.querySelector('dialog[open]')));await page.waitForTimeout(200);
 out.focusReturnedTo=await page.evaluate(()=>window.__a.desc(document.activeElement));delete out.list;return out}
async function collect(browser,route,width,service){const {ctx,page,errors}=await open(browser,route,width,service),cdp=await ctx.newCDPSession(page),r={route,width,state:service?'service-fixture':'published'},tests=[];
 const kindsDone=new Set(),kb=newWalk();
 if(route==='/hike/'&&!service){await page.locator('[data-trail-explorer]').scrollIntoViewIfNeeded();await page.locator('[data-trail-explorer][data-ready=true]').waitFor({timeout:8000}).catch(()=>{});await page.evaluate(()=>scrollTo(0,0))}
 await page.evaluate(()=>{scrollTo(0,0);document.activeElement.blur()});
 const walk=await tabWalk(page,900,kindsDone,kb);
 const sc=await page.evaluate(SCAN),a=await ax(page,cdp,sc.tagged);
 const missed=sc.tagged.filter(t=>t.interactive&&!t.disabled&&t.tabindex!=='-1'&&!t.hit).map(t=>t.d);// every enabled, tab-reachable control must have been a stop
 Object.assign(r,{images:sc.images,headings:sc.headings,headingIssues:sc.headingIssues,cards:sc.cards,outsideLandmarks:sc.outsideLandmarks,controls:sc.controls,dupIds:sc.dupIds,dangling:sc.dangling,landmarks:a.landmarks,noName:a.noName,hiddenFocusable:a.hiddenFocusable,genericNamed:a.genericNamed,notInTree:a.notInTree,roleNameKinds:a.kinds,interactiveCount:a.interactive,
  fixed:sc.fixed,toast:sc.toast,targets:targetFails(sc.targets),keyboard:{...walk,list:undefined,notReached:missed,indicatorKindsChecked:kindsDone.size},errors});
 tests.push(await dialogTest(page,'[data-policy]','privacy dialog',kindsDone));
 await page.evaluate(()=>{scrollTo(0,0);document.activeElement.blur()});await focusKey(page,'.skip-link','Enter');await page.keyboard.press('Tab');
 tests.push({name:'skip link (Enter, then Tab)',hash:await page.evaluate(()=>location.hash),next:await page.evaluate(()=>window.__a.desc(document.activeElement)),insideTarget:await page.evaluate(()=>!!document.getElementById(location.hash.slice(1))?.contains(document.activeElement))});
 if(route==='/'&&!service){ // catalog: filter keys, card details, a "See all from maker" button that re-renders the grid
  await page.evaluate(()=>scrollTo(0,0));const f=await (async()=>{await focusKey(page,'[data-filter="dairy"]','Space');return page.evaluate(()=>({pressed:document.querySelector('[data-filter="dairy"]').getAttribute('aria-pressed'),count:document.querySelector('#catalog-count').textContent,focus:window.__a.desc(document.activeElement)}))})();
  tests.push({name:'catalog filter by keyboard (Space on Dairy & cheese)',...f});await focusKey(page,'[data-filter="all"]','Enter');
  const det=await page.evaluate(()=>{const s=document.querySelector('#catalog-grid .maker-story summary');s.focus();return window.__a.desc(s)});await page.keyboard.press('Enter');
  const open=await page.evaluate(()=>({open:document.querySelector('#catalog-grid .maker-story').open}));await page.keyboard.press('Tab');const inside=await page.evaluate(()=>({next:window.__a.desc(document.activeElement),insideDetails:!!document.activeElement.closest('.maker-story-content')}));
  tests.push({name:'card details by keyboard (Enter on summary, then Tab)',summary:det,...open,...inside});
  const sa=await page.evaluate(()=>{const b=document.querySelector('#catalog-grid [data-from]');if(!b)return null;b.closest('details').open=true;b.focus();return window.__a.desc(b)});
  if(sa){await page.keyboard.press('Enter');await page.waitForTimeout(300);const lost=await page.evaluate(()=>document.activeElement===document.body);await page.keyboard.press('Tab');tests.push({name:'"See all from maker" by keyboard (Enter, then Tab)',button:sa,focusAfterEnter:lost?'document body (focus lost)':'kept',nextTab:await page.evaluate(()=>window.__a.desc(document.activeElement)),count:await page.evaluate(()=>document.querySelector('#catalog-count').textContent),chip:await page.evaluate(()=>document.querySelector('.catalog-from')?.textContent.trim())})}}
 if(route==='/hike/'&&!service){ // trail map by keyboard, then the enlarged-map dialog
  await page.evaluate(()=>{scrollTo(0,0);document.activeElement.blur()});
  const m=await page.evaluate(()=>{const s=document.querySelector('.trail-map-stage');return s?{zoom:s.dataset.zoom}:null});
  if(m){const z=async k=>{await page.keyboard.press(k);return page.evaluate(()=>document.querySelector('.trail-map-stage').dataset.zoom)};await page.focus('.trail-map-stage');const vb=()=>page.evaluate(()=>document.querySelector('.trail-map-canvas').getAttribute('viewBox'));
   const t={name:'trail map stage keys',start:m.zoom,plus:await z('+'),minus:await z('-')};await z('+');const v0=await vb();await page.keyboard.press('ArrowRight');t.arrowMoves=v0!==await vb();t.home=await z('Home');
   await page.focus('#trail-distance');const r0=await page.locator('#trail-elevation-readout').textContent();await page.keyboard.press('ArrowRight');t.sliderMoves=r0!==await page.locator('#trail-elevation-readout').textContent();
   await focusKey(page,'[data-map-layer="topo"]','Enter');t.topoPressed=await page.getAttribute('[data-map-layer="topo"]','aria-pressed');await focusKey(page,'[data-map-layer="aerial"]','Enter');
   await focusKey(page,'[data-map-action="in"]','Enter');t.zoomButton=await page.evaluate(()=>document.querySelector('.trail-map-stage').dataset.zoom);await focusKey(page,'[data-map-action="fit"]','Enter');t.fitButton=await page.evaluate(()=>document.querySelector('.trail-map-stage').dataset.zoom);tests.push(t);
   await page.focus('[data-map-action="in"]');for(let i=0;i<3;i++)await page.keyboard.press('Enter');await page.waitForTimeout(100);const zi=await page.evaluate(()=>({zoom:document.querySelector('.trail-map-stage').dataset.zoom,disabled:document.querySelector('[data-map-action="in"]').disabled,focus:document.activeElement===document.body?'document body (focus lost)':window.__a.desc(document.activeElement)}));await page.keyboard.press('Tab');
   tests.push({name:'trail map Zoom in x3 by keyboard (button disables at max zoom)',...zi,nextTab:await page.evaluate(()=>window.__a.desc(document.activeElement))});await focusKey(page,'[data-map-action="fit"]','Enter');
   const nm=['#preview-rsvp-name','Synthetic Visitor'],em=['#preview-rsvp-email','synthetic@example.invalid'];await page.fill(nm[0],nm[1]);await page.fill(em[0],em[1]);await page.focus('#preview-rsvp-email');await page.keyboard.press('Enter');await page.waitForTimeout(100);
   tests.push({name:'sample RSVP submitted by keyboard (Enter in email; nothing is sent)',status:await page.locator('#preview-hike-rsvp .form-status').textContent(),focus:await page.evaluate(()=>window.__a.desc(document.activeElement))});
   tests.push(await dialogTest(page,'[data-map-action="expand"]','enlarged trail map dialog (Enlarge map)',kindsDone));await page.setViewportSize({width,height:360});tests.push(await dialogTest(page,'[data-map-action="expand"]','enlarged trail map dialog at 360 px high',kindsDone))}}
 if(route==='/hike/'&&service){await page.evaluate(()=>{scrollTo(0,0);document.activeElement.blur()});tests.push(await dialogTest(page,'[data-rsvp]','RSVP dialog (synthetic event)',kindsDone));await page.setViewportSize({width,height:360});tests.push(await dialogTest(page,'[data-rsvp]','RSVP dialog at 360 px high',kindsDone))}
 if(route==='/404.html'){ // detector controls: a covered control and a suppressed outline must be caught; two adjacent 10 px targets fail 2.5.8, one isolated 10 px target passes by spacing
  await page.evaluate(()=>{scrollTo(0,0);document.activeElement.blur()});await page.focus('[data-policy]');const ok=await indicatorSeen(page,(await page.evaluate(()=>window.__a.read())).clip);
  await page.evaluate(()=>{document.activeElement.style.outline='none'});const supp=await indicatorSeen(page,(await page.evaluate(()=>window.__a.read())).clip);
  const cov=await page.evaluate(()=>{const b=document.activeElement,o=document.createElement('div');Object.assign(o.style,{position:'fixed',inset:'0',zIndex:'99'});document.body.append(o);const c=window.__a.cover(b);o.remove();return c});
  const T=(x,y)=>({d:'t',x,y,w:10,h:10,inline:false,disabled:false});
  r.selfChecks={indicatorSeenOnDefault:ok,indicatorSeenWhenSuppressed:supp,coverDetected:cov.p>0&&cov.c===cov.p,adjacentSmallTargetsFail:targetFails([T(0,0),T(12,0)]).fail.length===2,isolatedSmallTargetPasses:targetFails([T(0,0),T(200,0)]).fail.length===0}}
 r.tests=tests;await ctx.close();return r}
(async()=>{const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined}),rows=[];
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 try{for(const route of ROUTES)for(const width of WIDTHS)rows.push(await collect(browser,route,width,false));
  for(const route of ['/','/hike/'])for(const width of WIDTHS)rows.push(await collect(browser,route,width,true))}finally{const v=browser.version();await browser.close();server.close();fs.rmSync(tmp,{recursive:true,force:true});globalThis.__v=v}
 const missing=ROUTES.flatMap(r=>WIDTHS.filter(w=>!rows.some(x=>x.state==='published'&&x.route===r&&x.width===w)).map(w=>r+'@'+w)),selfOk=rows.filter(x=>x.selfChecks).every(x=>x.selfChecks.indicatorSeenOnDefault&&!x.selfChecks.indicatorSeenWhenSuppressed&&x.selfChecks.coverDetected&&x.selfChecks.adjacentSmallTargetsFail&&x.selfChecks.isolatedSmallTargetPasses);
 console.log(JSON.stringify({sha,chromium:globalThis.__v,published,checkPublish:checked,fixedClock:FIXED,nonLoopbackRequests:seen.nonLoopback,nonLoopbackHosts:seen.hosts,nonGetRequests:seen.nonGet,complete:!missing.length,missing,selfChecksOk:selfOk,rows}));
 process.exit(missing.length||!selfOk||seen.nonLoopback||seen.nonGet?1:0)})().catch(e=>{process.stderr.write('a11y QA failed: '+(e.stack||e)+'\n');fs.rmSync(tmp,{recursive:true,force:true});process.exit(1)});

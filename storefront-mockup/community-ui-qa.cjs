const {out,base}=require('./qa-env.cjs').qaEnv({preview:true});
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const fs=require('fs');
const check=(value,message)=>{if(!value)throw Error(message)};
(async()=>{
 const b=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
 const p=await b.newPage({viewport:{width:390,height:844},reducedMotion:'reduce'});
 const errors=[];p.on('pageerror',e=>errors.push(e.message));
 // Real integration checks are confined to the temporary fixture server.
 // AV1737-11: a full hike says so with no RSVP button; one place left is singular. Only qa-hike's fields are overridden.
 const api=process.env.COMMUNITY_TEST_URL+'/api/community',qaHike=()=>p.locator('.hike-event').filter({hasText:'QA trail fixture'});
 const shown=async(fields,id='qa-hike')=>{
  await p.unroute(api);
  await p.route(api,async r=>{const res=await r.fetch(),j=await res.json();Object.assign(j.events.find(e=>e.id===id),fields);await r.fulfill({response:res,json:j})});
  await p.goto(process.env.COMMUNITY_TEST_URL+'/hike');await qaHike().waitFor();
  const buttons=qaHike().locator('[data-rsvp]');
  return {text:await qaHike().innerText(),count:await buttons.count(),buttons};
 };
 let h=await shown({remaining:0});
 check(h.text.includes('This hike is full.')&&!/places? available/.test(h.text)&&h.count===0,'Full hike offered an RSVP: '+h.text);
 check((await qaHike().locator('.hike-full').innerText()).trim()==='This hike is full.','Full hike notice missing its hook');
 check(await qaHike().getByRole('button').count()===0,'Full hike still shows a button');
 h=await shown({remaining:1});
 check(h.text.includes('1 place available')&&!h.text.includes('1 places')&&!h.text.includes('This hike is full'),'One place not singular: '+h.text);
 check(h.count===1&&await h.buttons.isEnabled()&&(await h.buttons.innerText()).trim()==='RSVP to this hike ↗','One place lost its enabled RSVP button');
 h=await shown({remaining:2});
 check(h.text.includes('2 places available')&&h.count===1&&await h.buttons.isEnabled(),'Two places wrong: '+h.text);
 h=await shown({remaining:null});
 check(h.text.includes('RSVPs open')&&!/places? available/.test(h.text)&&h.count===1&&await h.buttons.isEnabled(),'Uncapped hike wrong: '+h.text);
 h=await shown({rsvpOpen:false,remaining:0});
 check(h.text.includes('RSVP details will be shared when confirmed.')&&!h.text.includes('This hike is full')&&h.count===0,'Closed RSVP lost to full: '+h.text);
 // AV1322-09: an upcoming scheduled hike carries one .ics link with escaped text; cancelled and completed hikes carry none.
 await shown({title:'QA trail fixture Hike; bring water, snacks\\ & hats',meetingPoint:'North lot\nGate 2'});
 const cal=qaHike().locator('a.hike-ics'),href=await cal.getAttribute('href')||'',ics=decodeURIComponent(href.slice(href.indexOf(',')+1)),flat=ics.replace(/\r\n /g,'');
 check(await cal.count()===1&&await cal.getAttribute('download')==='qa-hike.ics'&&(await cal.innerText()).trim()==='Add to calendar'&&href.startsWith('data:text/calendar;charset=utf-8,'),'Upcoming hike lacks its calendar link');
 check(flat.includes('\r\nSUMMARY:QA trail fixture Hike\\; bring water\\, snacks\\\\ & hats\r\n')&&flat.includes('\r\nLOCATION:North lot\\nGate 2\r\n')&&/\r\nDTSTART:\d{8}T\d{6}Z\r\n/.test(ics)&&flat.includes(`\r\nURL:${process.env.COMMUNITY_TEST_URL}/hike#qa-hike\r\n`),'Calendar text wrong: '+JSON.stringify(ics));
 check(ics.split('\r\n').every(l=>Buffer.byteLength(l)<=75),'Calendar line over 75 octets');
 check(await p.locator('#upcoming-hikes .hike-event a.hike-ics').count()===5&&await p.locator('#past-hikes a.hike-ics').count()===0,'Calendar links not on exactly the upcoming scheduled hikes');
 await shown({status:'cancelled'});
 check(await qaHike().locator('.label').innerText()==='CANCELLED'&&await qaHike().locator('a.hike-ics').count()===0,'Cancelled hike offered a calendar link');
 // AV0207-01: owner-set logistics in a fixed order, escaped, in the card and the RSVP dialog; an unset field shows nothing.
 const byTitle=t=>p.locator('.hike-event').filter({has:p.locator('h2',{hasText:t})}),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
 const facts=l=>l.evaluate(n=>[...n.querySelectorAll('.hike-facts dt')].map(d=>d.textContent+'='+d.nextElementSibling.textContent));
 const FULL=['Meet=QA full meeting point','Meet at=8:45 am','Address=QA Road 1, Los Osos · Directions','Start=9:00 am','Back=Around 12:30 pm','Distance=4 miles','Pace / terrain=Easy','Time on trail=3 hours','Bring along=Water and a snack'];
 await shown({});
 const full=byTitle('QA all logistics'),bare=byTitle('QA no logistics'),dir=full.locator('.hike-facts a');
 check(same(await facts(full),FULL),'Full hike rows wrong: '+JSON.stringify(await facts(full)));
 check(await full.locator('.hike-facts + p.hike-access').count()===1&&(await full.locator('.hike-access').innerText()).trim()==='QA access: no pets.','Access note missing after the facts');
 check(await dir.count()===1&&await dir.getAttribute('href')==='https://www.google.com/maps/search/?api=1&query=QA%20Road%201%2C%20Los%20Osos'&&await dir.getAttribute('target')==='_blank'&&await dir.getAttribute('rel')==='noopener'&&await dir.getAttribute('class')==='text-link'&&(await dir.innerText()).trim()==='Directions','Directions link wrong');
 const bareText=await bare.innerText();
 check(same(await facts(bare),['Meet=QA meeting point','Distance=2 miles','Pace / terrain=Flat','Time on trail=1 hour'])&&await bare.locator('.hike-access').count()===0&&!/Address|Directions|Bring along|Meet at|undefined|null/.test(bareText),'Hike without logistics gained rows: '+bareText);
 await full.locator('[data-rsvp]').click();await p.locator('#rsvp-name').waitFor();
 const dlg=p.locator('#dialog-content');
 check(same(await facts(dlg),FULL)&&await dlg.locator('.hike-facts + p.hike-access').count()===1&&(await dlg.locator('.hike-access').innerText()).trim()==='QA access: no pets.','RSVP dialog lacks the logistics: '+JSON.stringify(await facts(dlg)));
 await p.keyboard.press('Escape');
 const addr='QA 1 & 2 <b>Main</b> "St" #5';
 await shown({bring:'   ',meetTime:'',returnTime:null,walkTime:7,accessNote:' \n ',meetingAddress:addr});
 const qd=qaHike().locator('.hike-facts a'),qhref=await qd.getAttribute('href')||'';
 check(same(await facts(qaHike()),['Meet=QA meeting point',`Address=${addr} · Directions`,'Distance=3 miles','Pace / terrain=Gentle pace','Time on trail=2 hours'])&&await qaHike().locator('.hike-facts b').count()===0&&await qaHike().locator('.hike-access').count()===0,'Blank fields shown or address not escaped: '+JSON.stringify(await facts(qaHike())));
 check(qhref.startsWith('https://www.google.com/maps/search/?api=1&query=')&&new URL(qhref).searchParams.get('query')===addr&&new URL(qhref).hash==='','Directions query does not decode to the address: '+qhref);
 await shown({status:'cancelled'},'qa-full');
 check(await full.locator('.label').innerText()==='CANCELLED'&&same(await facts(full),FULL)&&await full.locator('.hike-access').count()===1&&await full.locator('[data-rsvp]').count()===0,'Cancelled hike lost its rows or kept RSVP');
 await p.unroute(api);
 check(!errors.length,'Page errors while overriding places: '+JSON.stringify(errors));
 // AV2022-12: a real hike naming a route idea shows its title and trail link (display only). Fixture payload only.
 const ideas=[{id:'qa-r1',title:'QA Route One',sourceUrl:'https://example.org/qa-trail',sourceName:'QA Parks'},{id:'qa-r2',title:'QA Script Route',sourceUrl:'javascript:alert(1)',sourceName:'QA Bad'},
  {id:'qa-r3',title:'QA <b>bold</b> "quoted"',sourceUrl:'https://example.org/qa-3',sourceName:'QA Esc'},{id:'qa-r4',title:'QA Unnamed Source',sourceUrl:'https://example.org/qa-4'},{id:'qa-r5',title:'QA Plain Route',sourceUrl:'http://example.org/qa-5',sourceName:'QA Plain'}];
 const linked={'qa-hike':'qa-r1','qa-race':'qa-missing','qa-past':'qa-r1'},extra=[['qa-r2','QA js route'],['qa-r3','QA escaped route'],['qa-r4','QA unnamed route'],['qa-r5','QA http route']];
 await p.route(api,async r=>{const res=await r.fetch(),j=await res.json(),h=j.events.find(e=>e.id==='qa-hike');j.routeIdeas=ideas;
  j.events.push(...extra.map(([t,title])=>({...h,id:'x-'+t,title,trailId:t})));for(const e of j.events)if(linked[e.id])e.trailId=linked[e.id];await r.fulfill({response:res,json:j})});
 await p.goto(process.env.COMMUNITY_TEST_URL+'/hike');await qaHike().waitFor();await p.locator('.hike-event',{hasText:'QA http route'}).waitFor();
 const card=t=>p.locator('.hike-event').filter({has:p.locator('h2',{hasText:t})}),line=t=>card(t).locator('.hike-route'),said=async t=>(await line(t).textContent()).replace(/\s+/g,' ').trim();
 let link=line('QA trail fixture').locator('a');
 check(await line('QA trail fixture').count()===1&&await said('QA trail fixture')==='Route: QA Route One · QA Parks ↗','Linked route line wrong: '+await said('QA trail fixture'));
 check(await link.getAttribute('href')==='https://example.org/qa-trail'&&await link.getAttribute('target')==='_blank'&&await link.getAttribute('rel')==='noopener'&&await link.getAttribute('class')==='text-link','Route link attributes wrong');
 check(await card('QA trail fixture').locator('.hike-facts + .hike-route').count()===1,'Route line not right after the hike facts');
 check(await line('QA uncapped event').count()===0,'Hike without trailId gained a route line');
 check(await line('QA limited places').count()===0,'Unknown trailId produced a route line');
 check(await said('QA js route')==='Route: QA Script Route'&&await line('QA js route').locator('a').count()===0,'Non-https javascript: route was linked');
 check(await said('QA http route')==='Route: QA Plain Route'&&await line('QA http route').locator('a').count()===0,'Plain http route was linked');
 check(await p.locator('a[href^="javascript"],a[href^="http:"]').count()===0,'Unsafe route href reached the page');
 check(await said('QA escaped route')==='Route: QA <b>bold</b> "quoted" · QA Esc ↗'&&await line('QA escaped route').locator('b').count()===0,'Route title not escaped');
 link=line('QA unnamed route').locator('a');
 check((await link.textContent()).replace(/\s+/g,' ').trim()==='Trail information ↗'&&await link.getAttribute('href')==='https://example.org/qa-4','Missing sourceName not labelled Trail information');
 // AV1622-03: a linked real past hike is a trail-journal entry: its own title and recap, the route's place/stats/https link, no details row, no RSVP/calendar.
 const entry=p.locator('#past-hikes .trail-journal-entry').filter({has:p.locator('h3',{hasText:'QA past outing'})});
 check(await entry.count()===1&&await p.locator('#past-hikes details.past-hike').count()===0&&await p.locator('#past-hikes .hike-route,#past-hikes a.hike-ics,#past-hikes [data-rsvp]').count()===0,'Linked past hike is not a plain journal entry');
 check(await entry.locator('h3').textContent()==='QA past outing'&&await entry.locator('a.text-link').getAttribute('href')==='https://example.org/qa-trail'&&await entry.locator('a.text-link').getAttribute('rel')==='noopener','Journal entry lost its title or trail link');
 await card('QA trail fixture').getByRole('button',{name:'RSVP to this hike ↗'}).click();await p.locator('#rsvp-name').waitFor();
 check(!(await p.locator('#hike-rsvp').evaluate(f=>f.parentElement.innerText)).includes('QA Route One'),'Route copied into the RSVP dialog');
 await p.keyboard.press('Escape');
 await p.unroute(api);
  // AV0207-03: only the first upcoming scheduled hike linked to idea-point-buchon mounts the trail explorer (once per page).
 const buchon={id:'idea-point-buchon',title:'Point Buchon',sourceUrl:'https://example.org/pb',sourceName:'QA Parks'},trailJson='**/assets/trails/point-buchon.json',consoleErrors=[];
 p.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
 const explorerPage=async(change,abort=false)=>{await p.unroute(api);await p.unroute(trailJson);if(abort)await p.route(trailJson,r=>r.abort());
  await p.route(api,async r=>{const res=await r.fetch(),j=await res.json();j.routeIdeas=[buchon,...ideas];change(j.events,j.events.find(e=>e.id==='qa-hike'));await r.fulfill({response:res,json:j})});
  await p.goto(process.env.COMMUNITY_TEST_URL+'/hike');await qaHike().waitFor();await p.locator('[data-trail-explorer]').evaluateAll(a=>a.forEach(h=>h.scrollIntoView()));await p.waitForFunction(()=>[...document.querySelectorAll('[data-trail-explorer]')].every(h=>h.dataset.ready));
  return {n:await p.locator('.trail-explorer').count(),hosts:await p.locator('[data-trail-explorer]').count(),inCard:async t=>card(t).locator('[data-trail-explorer] .trail-explorer .trail-profile-svg').count()}};
 let ex=await explorerPage((_,h)=>{h.trailId='idea-point-buchon'});
 check(ex.n===1&&ex.hosts===1&&await ex.inCard('QA trail fixture')===1&&await p.locator('.trail-profile-svg path,.trail-profile-svg polyline').count()>0&&await card('QA trail fixture').locator('.hike-route').count()===1,'Buchon hike lacks exactly one explorer with its elevation chart');
 ex=await explorerPage((ev,h)=>{h.trailId='idea-point-buchon';ev.find(e=>e.id==='qa-race').trailId='idea-point-buchon';h.startsAt=new Date(Date.parse(h.startsAt)+864e5).toISOString()});
 check(ex.n===1&&ex.hosts===1&&await ex.inCard('QA limited places')===1&&await ex.inCard('QA trail fixture')===0,'Two Buchon hikes did not give one explorer in the earlier card');
 ex=await explorerPage((ev,h)=>{h.trailId='idea-point-buchon';h.status='cancelled'});
 check(ex.n===0&&ex.hosts===0,'Cancelled Buchon hike mounted an explorer');
 ex=await explorerPage((ev,h)=>{h.trailId='idea-point-buchon';h.status='cancelled';ev.find(e=>e.id==='qa-race').trailId='idea-point-buchon'});
 check(ex.n===1&&await ex.inCard('QA limited places')===1,'A cancelled Buchon hike hid the scheduled one');
 ex=await explorerPage((ev,h)=>{h.trailId='qa-r1';ev.find(e=>e.id==='qa-race').trailId='idea-point-buchon-x';ev.find(e=>e.id==='qa-full').trailId='qa-missing'});
 check(ex.n===0&&ex.hosts===0&&await said('QA trail fixture')==='Route: QA Route One · QA Parks ↗','Other or missing trailId gained an explorer or lost its route line');
 ex=await explorerPage((_,h)=>{h.trailId='idea-point-buchon'});
 check(await card('QA trail fixture').getByRole('button',{name:'RSVP to this hike ↗'}).count()===1,'Explorer card lost its RSVP button');
 consoleErrors.length=0;
 ex=await explorerPage((_,h)=>{h.trailId='idea-point-buchon'},true);
 check(ex.n===0&&ex.hosts===1&&(await card('QA trail fixture').locator('.trail-map-unavailable').innerText()).includes('The interactive map couldn’t load.')&&!errors.length&&!consoleErrors.some(m=>!/Failed to load resource/.test(m)),'Blocked trail data: no unavailable text or an error escaped: '+JSON.stringify(consoleErrors));
 await p.unroute(trailJson);
 check(!errors.length,'Page errors with route ideas: '+JSON.stringify(errors));
 await p.goto(process.env.COMMUNITY_TEST_URL+'/hike');
 check(await p.locator('.hike-event').filter({hasText:'QA trail fixture'}).locator('[data-confirmed-guests]').textContent()==='2','Initial party count wrong');
 await p.getByRole('button',{name:'RSVP to this hike ↗',exact:true}).first().click();
 await p.locator('#rsvp-name').fill('UI Test');
 await p.locator('#rsvp-email').fill('ui-test@example.invalid');
 await p.locator('#rsvp-party').selectOption('1');
 await p.getByRole('button',{name:'Save my RSVP ↗',exact:true}).click();
 await p.getByText('Your RSVP is saved locally. No confirmation email has been sent.',{exact:true}).waitFor();
 await p.keyboard.press('Escape');
 await p.locator('.hike-event').filter({hasText:'QA trail fixture'}).locator('[data-confirmed-guests]').filter({hasText:'3'}).waitFor();
 await p.goto(process.env.COMMUNITY_TEST_URL+'/');
 await p.locator('#newsletter-email').fill('newsletter-ui@example.invalid');
 await p.locator('#community-newsletter input[name="hikes"]').check();
 await p.getByRole('button',{name:'Send me Michael’s newsletter ↗',exact:true}).click();
 await p.locator('#community-newsletter .form-status').filter({hasText:'Saved to the local signup list.'}).waitFor();
 await p.goto(process.env.COMMUNITY_TEST_URL+'/hike');
 await p.locator('#hike-email').fill('hiking-ui@example.invalid');
 await p.getByRole('button',{name:'Keep me on the trail list',exact:true}).click();
 await p.locator('#hike-updates .form-status').filter({hasText:'Saved to the local signup list.'}).waitFor();
 check(await p.getByText('QA past outing',{exact:true}).count(),'History missing');
 check(!await p.locator('#preview-hike-rsvp').count(),'Preview replaced a confirmed event');
 // The normal site's mock invitation must never post or store personal data.
 await p.goto(base+'/hike');
 await p.locator('#preview-hike-rsvp').waitFor();
 const publicData=await p.evaluate(()=>fetch('/api/community').then(r=>r.json()));
 check(publicData.events.length===0,'Mock events entered real calendar');
 check(publicData.routeIdeas.length===3,'Missing requested trails');
 check(!await p.locator('[data-rsvp]').count(),'Mockup exposed real RSVP action');
 check(await p.getByText('Sample invitation · plans to be confirmed',{exact:true}).count(),'Sample invitation unlabeled');
 check(await p.locator('.trail-journal-entry').count()===2,'Archive examples missing');
 check((await p.locator('#history-context').innerText()).includes('not confirmed'),'Archive appears to be real history');
 check(!await p.locator('.hike-route').count(),'Sample invitation/archive gained a real route line');
 check(!await p.locator('.hike-facts,.hike-access').count()&&await p.locator('.trail-logistics dt').count()===3,'Sample invitation gained real-hike logistics rows');
 const posts=[];p.on('request',r=>{if(r.method()==='POST')posts.push(r.url())});
 await p.locator('#preview-hike-rsvp button').click();
 check(await p.locator('#preview-rsvp-name').evaluate(e=>!e.validity.valid),'Missing-name validation');
 await p.locator('#preview-rsvp-name').fill('Demo visitor');
 await p.locator('#preview-rsvp-email').fill('not-an-email');
 await p.locator('#preview-hike-rsvp button').click();
 check(await p.locator('#preview-rsvp-email').evaluate(e=>!e.validity.valid),'Invalid email accepted');
 await p.locator('#preview-rsvp-email').fill('demo@example.invalid');
 await p.locator('#preview-rsvp-party').selectOption('2');
 await p.locator('#preview-hike-rsvp button').click();
 await p.locator('#preview-hike-rsvp .form-status').filter({hasText:'No details were saved or sent.'}).waitFor();
 check(posts.length===0,'Demo form made a POST request');
 check(await p.locator('[data-confirmed-guests]').textContent()==='0','Demo RSVP changed guest count');
 check(await p.evaluate(()=>localStorage.length===0&&sessionStorage.length===0),'Demo stored browser data');
 check(await p.locator('#preview-rsvp-name').inputValue()==='','Demo retained submitted name');
 check(await p.locator('#preview-hike-rsvp .form-status').evaluate(e=>e===document.activeElement),'Success not announced/focused');
 await p.reload();await p.locator('#preview-hike-rsvp').waitFor();
 const layouts=[];
 for(const width of [320,375,390,430,768,1024,1440]){
  await p.setViewportSize({width,height:900});
  const info=await p.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,background:getComputedStyle(document.body).backgroundColor,smallTargets:[...document.querySelectorAll('#preview-hike-rsvp input,#preview-hike-rsvp select,#preview-hike-rsvp button')].filter(e=>e.getBoundingClientRect().height<44).length}));
  layouts.push({width,...info});
 }
 check(!layouts.some(x=>x.overflow||x.smallTargets),'Responsive overflow or short controls');
 check(!errors.length,JSON.stringify(errors));
 await p.setViewportSize({width:390,height:844});
 await p.locator('.club-intro').screenshot({path:out+'/hiking-intro-mobile.png'});
 await p.locator('.trail-invitation').screenshot({path:out+'/hiking-invitation-mobile.png'});
 await p.locator('.hike-history').screenshot({path:out+'/hiking-history-mobile.png'});
 await p.setViewportSize({width:1440,height:1000});
 await p.locator('#hikes').screenshot({path:out+'/hiking-desktop.png'});
 // RF1720-2: a scheduled hike stays listed (as Today) until midnight Pacific on its own day. Times derive from the fixture.
 const hike=(await (await fetch(process.env.COMMUNITY_TEST_URL+'/api/community')).json()).events.find(e=>e.title==='QA trail fixture');
 const start=Date.parse(hike.startsAt),wall=t=>Date.parse(new Date(t).toLocaleString('sv-SE',{timeZone:'America/Los_Angeles'}).replace(' ','T')+'Z');
 const pacificAt=w=>{const t=w-(wall(w)-w);return w-(wall(t)-t)}; // the instant whose Pacific wall clock reads w
 const nextDay=Date.parse(new Date(start).toLocaleDateString('en-CA',{timeZone:'America/Los_Angeles'})+'T00:00Z')+864e5;
 const today='Today — started '+new Date(start).toLocaleTimeString('en-US',{timeZone:'America/Los_Angeles',hour:'numeric',minute:'2-digit'});
 const baseJson=await (await fetch(process.env.COMMUNITY_TEST_URL+'/api/community')).json();
 const view=async(now,timezoneId='America/Los_Angeles',extra=[],keep=()=>true,stat=false)=>{
  const c=await b.newContext({timezoneId}),pg=await c.newPage(),errs=[];pg.on('pageerror',e=>errs.push(e.message));
  if(stat){ // published-site mode: no club service, /community.json is the only source
   await pg.route('**/api/community',r=>r.fulfill({status:404,contentType:'text/plain',body:'no service'}));
   await pg.route('**/community.json',r=>r.fulfill({json:{...baseJson,events:baseJson.events.filter(keep).concat(extra)}}));
  }else await pg.route('**/api/community',async r=>{const res=await r.fetch(),j=await res.json();j.events=j.events.filter(keep).concat(extra);await r.fulfill({response:res,json:j})});
  await pg.clock.setFixedTime(now);await pg.goto(process.env.COMMUNITY_TEST_URL+'/hike');
  await pg.locator('#upcoming-hikes :is(.hike-event,.hike-empty,.trail-invitation)').first().waitFor();
  const r=await pg.evaluate(()=>({up:document.querySelector('#upcoming-hikes').innerText,past:document.querySelector('#past-hikes').innerText,dates:Object.fromEntries([...document.querySelectorAll('.hike-event')].map(a=>[a.querySelector('h2').textContent,a.querySelector('.hike-date').textContent])),
   cards:[...document.querySelectorAll('.hike-event')].map(a=>({cls:a.className,label:a.querySelector('.label').textContent,title:a.querySelector('h2').textContent,rsvp:a.querySelectorAll('[data-rsvp]').length,ics:a.querySelectorAll('.hike-ics').length,guests:(a.querySelector('[data-confirmed-guests]')||{}).textContent??null,text:a.innerText})),empty:!!document.querySelector('#upcoming-hikes :is(.hike-empty,.trail-invitation)')}));
  check(!errs.length,'Page errors at '+new Date(now).toISOString()+': '+JSON.stringify(errs));await c.close();return r;
 };
 const after=start+Math.min(18e5,(pacificAt(nextDay)-start)/2),cancelled={...hike,id:'qa-cancelled',title:'QA cancelled fixture',status:'cancelled'};
 let v=await view(after,'America/Los_Angeles',[cancelled]);
 check(v.dates['QA trail fixture']===today,'Started hike not listed as Today: '+v.dates['QA trail fixture']);
 check(!v.cards.find(c=>c.title==='QA trail fixture').text.includes('Add to calendar'),'Started hike offered a calendar link');
 const sentence='This hike is cancelled. Nothing else is needed from you.',cx=v=>v.cards.find(c=>c.title==='Cancelled: QA cancelled fixture');
 // AV1737-12 inverts RF1720-2's same-day check: a hike cancelled earlier today stays listed, marked, with no RSVP, despite rsvpOpen.
 // RF0834-14: its date line is still the planned date/time (the fixture has no zone, so Pacific), never "started".
 const planned=new Date(start).toLocaleString('en-US',{timeZone:'America/Los_Angeles',weekday:'long',month:'long',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
 check(cx(v)&&cx(v).rsvp===0&&cx(v).text.includes(sentence)&&v.dates['Cancelled: QA cancelled fixture']===planned&&!/started/i.test(cx(v).text),'Cancelled hike from earlier today not listed with its planned date: '+v.up);
 v=await view(start-6e4);
 check(v.dates['QA trail fixture']&&!v.dates['QA trail fixture'].includes('Today'),'Hike before start not shown with its date');
 v=await view(pacificAt(nextDay+6e4));
 check(!v.up.includes('QA trail fixture')&&!v.past.includes('QA trail fixture'),'Hike still listed after midnight Pacific');
 v=await view(pacificAt(nextDay-6e4),'Asia/Tokyo');
 check(v.dates['QA trail fixture'],'Hike dropped at the viewer’s midnight, not Pacific midnight');
 // AV1737-12: cancelled hikes stay listed, marked, with no RSVP, until midnight Pacific at the end of their own day.
 const tomorrow={...cancelled,startsAt:new Date(start+864e5).toISOString()},early={...cancelled,id:'qa-early',title:'QA early cancelled',startsAt:new Date(start-3e4).toISOString()};
 v=await view(start-6e4,'America/Los_Angeles',[tomorrow,early]);
 const titles=v.cards.map(c=>c.title),s=v.cards.find(c=>c.title==='QA uncapped event'),c=cx(v);
 check(titles[0]==='Cancelled: QA early cancelled'&&titles.at(-1)==='Cancelled: QA cancelled fixture'&&titles.includes('QA uncapped event'),'Scheduled and cancelled not listed by start: '+JSON.stringify(titles));
 check(c.cls==='hike-event hike-cancelled'&&c.label==='CANCELLED'&&c.text.includes(sentence)&&c.rsvp===0&&!/RSVPs open|places? available|This hike is full|RSVP details|THE NEXT HIKE/.test(c.text),'Tomorrow’s cancelled hike card wrong: '+c.text);
 check(s.rsvp===1&&s.cls==='hike-event'&&s.label==='COMING UP'&&!s.text.includes(sentence),'Scheduled hike lost its RSVP or was marked cancelled: '+s.text);
check(v.cards.filter(c=>c.label==='THE NEXT HIKE').length===1&&v.cards.find(c=>c.label==='THE NEXT HIKE').title==='QA trail fixture','Exactly the first scheduled card should be THE NEXT HIKE: '+JSON.stringify(v.cards.map(c=>c.label+'|'+c.title)));
 v=await view(pacificAt(nextDay+6e4),'America/Los_Angeles',[cancelled]);
 check(!v.up.includes('QA cancelled fixture'),'Cancelled hike still listed after midnight Pacific at the end of its day');
 v=await view(pacificAt(nextDay-6e4),'Asia/Tokyo',[cancelled]);
 check(cx(v)&&cx(v).rsvp===0,'Cancelled hike dropped at the viewer’s midnight, not Pacific midnight');
 v=await view(start-6e4,'America/Los_Angeles',[tomorrow],e=>e.status!=='scheduled');
 check(v.cards.length===1&&cx(v)&&cx(v).rsvp===0&&!v.empty,'Only a cancelled hike showed the empty state or sample invitation: '+v.up);
 check(v.past.includes('QA past outing')&&!v.up.includes('QA past outing'),'Completed hike not only under past hikes');
// AV1937-08: only the first scheduled card says THE NEXT HIKE; later scheduled cards say COMING UP; cancelled cards keep CANCELLED.
{
const ev=(id,ms,status='scheduled')=>({...hike,rsvpOpen:true,remaining:null,id,title:'AV '+id,status,startsAt:new Date(start+ms).toISOString().replace('.000Z','Z')}),none=()=>false,at=start-6e4,L=v=>v.cards.map(c=>c.label+'|'+c.title).join(' ; ');
const NEXT='THE NEXT HIKE',SOON='COMING UP',CX='CANCELLED',ctl=c=>c.rsvp+(c.ics?'c':'');
const cards=v=>v.cards;
// test_unsorted_scheduled_labels
let q=await view(at,'America/Los_Angeles',[ev('c',3e5),ev('a',1e5),ev('b',2e5)],none);
check(L(q)===[NEXT+'|AV a',SOON+'|AV b',SOON+'|AV c'].join(' ; '),'Unsorted scheduled labels wrong: '+L(q));
// test_cancelled_before_and_between_scheduled
q=await view(at,'America/Los_Angeles',[ev('s2',3e5),ev('x2',2e5,'cancelled'),ev('s1',1e5),ev('x1',-1e4,'cancelled')],none);
check(L(q)===[CX+'|Cancelled: AV x1',NEXT+'|AV s1',CX+'|Cancelled: AV x2',SOON+'|AV s2'].join(' ; '),'Cancelled/scheduled labels wrong: '+L(q));
check(cards(q).filter(c=>c.label===CX).every(c=>c.rsvp===0&&!c.ics&&c.text.includes(sentence)),'Cancelled card gained RSVP or calendar link');
check(cards(q).filter(c=>c.label!==CX).every(c=>c.rsvp===1),'Scheduled card lost its RSVP');
// test_equal_start_selects_one
q=await view(at,'America/Los_Angeles',[ev('t1',1e5),ev('t2',1e5),ev('t3',1e5)],none);
check(L(q)===[NEXT+'|AV t1',SOON+'|AV t2',SOON+'|AV t3'].join(' ; '),'Equal-start labels wrong: '+L(q));
// test_one_scheduled_unchanged
q=await view(at,'America/Los_Angeles',[ev('one',1e5)],none);
check(L(q)===NEXT+'|AV one'&&ctl(q.cards[0])==='1c','Single hike changed: '+L(q)+ctl(q.cards[0]));
q=await view(at,'America/Los_Angeles',[ev('x',-1e4,'cancelled'),ev('one',1e5)],none);
check(L(q)===[CX+'|Cancelled: AV x',NEXT+'|AV one'].join(' ; ')&&ctl(q.cards[1])==='1c','Single hike after a cancelled one changed: '+L(q));
// test_no_scheduled_or_no_events
q=await view(at,'America/Los_Angeles',[ev('x',1e5,'cancelled'),ev('y',2e5,'cancelled')],none);
check(L(q)===[CX+'|Cancelled: AV x',CX+'|Cancelled: AV y'].join(' ; ')&&!q.empty&&!/THE NEXT HIKE|COMING UP/.test(q.up),'All-cancelled list wrong: '+L(q)+' '+q.up);
q=await view(at,'America/Los_Angeles',[],none);
check(!q.cards.length&&q.empty&&!/COMING UP/.test(q.up),'No real events did not keep the sample/empty state: '+q.up);
// test_same_day_started_then_midnight
q=await view(after,'America/Los_Angeles',[ev('later',after-start+6e4)],e=>e.id==='qa-hike');
check(L(q)===['TODAY|QA trail fixture',NEXT+'|AV later'].join(' ; '),'Started hike is not TODAY or the next future hike is not next: '+L(q));
q=await view(pacificAt(nextDay-6e4),'Asia/Tokyo',[ev('later',pacificAt(nextDay)-start+6e4)],e=>e.id==='qa-hike');
check(q.cards[0]&&q.cards[0].label==='TODAY'&&q.cards[0].title==='QA trail fixture'&&q.cards[1]&&q.cards[1].label===NEXT,'Tokyo viewer lost Pacific same-day TODAY label: '+L(q));
q=await view(pacificAt(nextDay+6e4),'America/Los_Angeles',[{...ev('later',5e5),startsAt:new Date(pacificAt(nextDay)+36e5).toISOString()},{...ev('later2',6e5),startsAt:new Date(pacificAt(nextDay)+72e5).toISOString()}],e=>e.id==='qa-hike');
check(L(q)===[NEXT+'|AV later',SOON+'|AV later2'].join(' ; '),'After Pacific midnight the successor is not next: '+L(q));
// test_rerender_recomputes_first: removing/cancelling the earliest on reload promotes its successor
q=await view(at,'America/Los_Angeles',[ev('p',1e5),ev('r',2e5)],none);
check(q.cards[0].label===NEXT&&q.cards[0].title==='AV p'&&q.cards[1].label===SOON,'Before override wrong: '+L(q));
q=await view(at,'America/Los_Angeles',[ev('p',1e5,'cancelled'),ev('r',2e5)],none);
check(L(q)===[CX+'|Cancelled: AV p',NEXT+'|AV r'].join(' ; '),'Cancelled earliest left a stale winner: '+L(q));
q=await view(at,'America/Los_Angeles',[ev('r',2e5)],none);
check(L(q)===NEXT+'|AV r','Removed earliest left a stale winner: '+L(q));
check(q.past===''||!q.past.includes('AV r'),'Upcoming hike listed in history');
// AV1104-05: a hike under way is TODAY with closed RSVPs, in service and published-static modes alike.
const STARTED='This hike has started, so RSVPs are closed.',OLD=/RSVP details|To join, ask|places? available|RSVPs open|This hike is full|THE NEXT HIKE|COMING UP/;
for(const stat of [false,true])for(const tz of ['America/Los_Angeles','Asia/Tokyo']){
 const m=(stat?'static ':'service ')+tz+': ';
 // startedTodayServiceAndStatic / startedBoundaryAndStaleOpenFlag
 for(const [name,now,extra] of [['exact start',start,{rsvpOpen:true,remaining:3,rsvpEnabled:true,confirmedGuests:1}],['start+1ms',start+1,{rsvpOpen:true,remaining:0,confirmedGuests:2}],['stale flags',after,{rsvpOpen:true,remaining:null,rsvpEnabled:false,confirmedGuests:7}]]){
  q=await view(now,tz,[{...hike,id:'qa-hike',...extra}],none,stat);
  const c=q.cards[0];
  check(c&&c.label==='TODAY'&&c.text.includes(STARTED)&&c.rsvp===0&&!c.ics&&!OLD.test(c.text),m+name+' started card wrong: '+(c&&c.label+' '+c.text));
  if(stat)check(c.guests===null,m+name+' static started card showed a guest count: '+c.guests);
  else check(c.guests===String(extra.confirmedGuests),m+name+' service count changed: '+c.guests);
 }
 q=await view(start-1,tz,[{...hike,id:'qa-hike',rsvpOpen:false,remaining:0,rsvpEnabled:true}],none,stat);
 check(q.cards[0].label===NEXT&&!q.cards[0].text.includes(STARTED),m+'start-1ms is not yet started: '+L(q));
 // nextFutureAfterTodayAndCancelled
 const tv=[ev('f2',3e5),ev('t2',-2e4),ev('f1',1e5),ev('f1b',1e5),ev('t1',-3e4),ev('cx',-4e4,'cancelled')];
 q=await view(start,tz,tv,none,stat);
 const lab=q.cards.map(c=>c.label+'|'+c.title).join(' ; ');
 check(lab===[CX+'|Cancelled: AV cx','TODAY|AV t1','TODAY|AV t2',NEXT+'|AV f1',SOON+'|AV f1b',SOON+'|AV f2'].join(' ; '),m+'Mixed list labels wrong: '+lab);
 check(q.cards.filter(c=>c.label==='TODAY').every(c=>c.text.includes(STARTED)&&!c.rsvp&&!c.ics)&&q.cards[0].text.includes(sentence)&&!q.cards[0].text.includes(STARTED),m+'TODAY/cancelled copy wrong');
 q=await view(start,tz,[ev('t1',-3e4),ev('cx',-4e4,'cancelled')],none,stat);
 check(!q.cards.some(c=>c.label===NEXT||c.label===SOON),m+'Started-only list invented a next hike: '+L(q));
 // cancelledAndCompletedNotStarted: malformed start, completed
 q=await view(after,tz,[ev('bad',0),{...ev('done',-1e5,'completed')}].map(e=>e.id==='bad'?{...e,startsAt:'not a date'}:e),none,stat);
 check(!q.cards.some(c=>c.label==='TODAY'),m+'Malformed or completed hike became TODAY: '+L(q));
}
// RF0814-11: the home Next hike line skips a started walk, but /hike keeps it as TODAY and labels the future walk THE NEXT HIKE (live and static).
{const evt=(id,title,startsAt)=>({...hike,id,title,status:'scheduled',startsAt,timezone:'America/Los_Angeles'}),pair=[evt('r-3','QA future afternoon walk','2026-11-09T15:00:00-08:00'),evt('r-9','QA started morning walk','2026-11-09T09:00:00-08:00')];
 for(const stat of [false,true]){const v=await view(Date.parse('2026-11-09T20:00:00Z'),'America/Los_Angeles',pair,e=>false,stat),card=t=>v.cards.find(c=>c.title===t);
  check(card('QA started morning walk')&&card('QA started morning walk').label==='TODAY','/hike lost the TODAY card (static='+stat+'): '+v.up);
  check(card('QA future afternoon walk')&&card('QA future afternoon walk').label==='THE NEXT HIKE','/hike lost THE NEXT HIKE card (static='+stat+'): '+v.up)}}
// RF0834-14: a cancelled hike's date line is its planned date/time (event zone, else Pacific) before, at and after its start, never "started";
// a scheduled hike at the same start keeps TODAY and "Today — started". Both stay listed until Pacific midnight. Expected dates are literal strings.
{const rf=(id,title,startsAt,status,more={})=>({...hike,rsvpOpen:true,remaining:3,rsvpEnabled:true,confirmedGuests:2,id,title,status,startsAt,timezone:'America/Los_Angeles',...more});
 const X='Cancelled: QA cancelled nine',S='QA scheduled nine',PLANNED='Monday, November 9, 2026 at 9:00 AM PST',NOTE='QA moved to next week.';
 const pair=[rf('rf-x','QA cancelled nine','2026-11-09T09:00:00-08:00','cancelled',{cancelNote:NOTE}),rf('rf-s',S,'2026-11-09T09:00:00-08:00','scheduled')];
 const nine=Date.parse('2026-11-09T17:00:00Z'),midnight=Date.parse('2026-11-10T08:00:00Z');
 for(const stat of [false,true])for(const tz of ['America/Los_Angeles','Asia/Tokyo']){const m='RF0834-14 '+(stat?'static ':'service ')+tz+' ';
  // cancelledDateNeverStartedAtBoundary / scheduledStartedDateUnchanged / cancelledDateVisibleUntilPacificMidnight (still listed)
  for(const [name,now] of [['start-1ms',nine-1],['exact start',nine],['start+1ms',nine+1],['later that day',nine+3*36e5],['Pacific midnight-1ms',midnight-1]]){
   const q=await view(now,tz,pair,none,stat),x=q.cards.find(c=>c.title===X),s=q.cards.find(c=>c.title===S),w=m+name+': ';
   check(x&&x.cls==='hike-event hike-cancelled'&&x.label===CX&&q.dates[X]===PLANNED,w+'cancelled date is not the planned date: '+JSON.stringify(q.dates));
   check(!/started/i.test(x.text)&&x.text.includes(sentence)&&x.text.includes(NOTE)&&x.rsvp===0&&!x.ics&&!OLD.test(x.text),w+'cancelled card wrong: '+x.text);
   check(!q.past.includes('QA cancelled nine')&&!q.past.includes(S),w+'hike moved to past hikes: '+q.past);
   if(now<nine)check(s&&s.label===NEXT&&q.dates[S]===PLANNED&&!s.text.includes(STARTED),w+'scheduled hike before its start wrong: '+JSON.stringify(s));
   else check(s&&s.label==='TODAY'&&q.dates[S]==='Today — started 9:00 AM'&&s.text.includes(STARTED)&&s.rsvp===0&&!s.ics,w+'scheduled started hike wrong: '+JSON.stringify(s));
  }
  for(const [name,now] of [['Pacific midnight',midnight],['Pacific midnight+1ms',midnight+1]]){const q=await view(now,tz,pair,none,stat);
   check(!/QA (cancelled|scheduled) nine/.test(q.up+q.past)&&!q.cards.length,m+name+': hike still listed or moved to past hikes: '+q.up+' | '+q.past)}
 }
 // cancelledDateUsesEventZoneNotViewerZone: a Tokyo viewer (already the next calendar day there) sees the event's own zone, else Pacific;
 // on the fall-back day the two 1:30 AM starts keep their instants (PDT, then PST).
 for(const stat of [false,true]){const m='RF0834-14 '+(stat?'static':'service')+' zones: ';
  let q=await view(nine+1,'Asia/Tokyo',[rf('z-ny','QA cancelled New York','2026-11-09T09:00:00-08:00','cancelled',{timezone:'America/New_York'}),rf('z-none','QA cancelled no zone','2026-11-09T09:00:00-08:00','cancelled',{timezone:undefined})],none,stat);
  check(q.dates['Cancelled: QA cancelled New York']==='Monday, November 9, 2026 at 12:00 PM EST'&&q.dates['Cancelled: QA cancelled no zone']===PLANNED&&!/started/i.test(q.up),m+'event-zone dates wrong: '+JSON.stringify(q.dates));
  q=await view(Date.parse('2026-11-01T10:00:00Z'),'Asia/Tokyo',[rf('z-pst','QA cancelled PST','2026-11-01T01:30:00-08:00','cancelled',{timezone:undefined}),rf('z-pdt','QA cancelled PDT','2026-11-01T01:30:00-07:00','cancelled')],none,stat);
  check(L(q)===[CX+'|Cancelled: QA cancelled PDT',CX+'|Cancelled: QA cancelled PST'].join(' ; ')&&q.dates['Cancelled: QA cancelled PDT']==='Sunday, November 1, 2026 at 1:30 AM PDT'&&q.dates['Cancelled: QA cancelled PST']==='Sunday, November 1, 2026 at 1:30 AM PST'&&!/started/i.test(q.up),m+'fall-back dates wrong: '+L(q)+' '+JSON.stringify(q.dates));
 }}
}
// AV1102-04/AV0007-01: the home page shows one "Next hike" line from the live API, else the published community.json; none, cancelled-only, past-only or both sources failing leaves it hidden. A valid live answer is never second-guessed by the static file.
const days=n=>new Date(Date.now()+n*864e5).toISOString(),oneLine=s=>s.replace(/\s+/g,' ').trim();
// RF0814-11: optional 4th argument {now,tz} fixes the page clock (and viewer timezone) before load; without it the callers behave as before.
const nextLine=async(events,width=390,stat,clock)=>{const c=await b.newContext({viewport:{width,height:800},...(clock&&clock.tz?{timezoneId:clock.tz}:{})}),pg=await c.newPage(),errs=[],reqs=[],posts=[];pg.on('pageerror',e=>errs.push(e.message));pg.on('request',q=>{reqs.push(q.url());if(q.method()==='POST')posts.push(q.url())});if(clock&&clock.now!==undefined)await pg.clock.setFixedTime(new Date(clock.now));
 if(stat!==undefined)await pg.route('**/community.json',r=>stat===null?r.fulfill({status:404,contentType:'text/html',body:'<p>no</p>'}):r.fulfill({json:{clubName:'QA',events:stat}}));
 await pg.route('**/api/community',async r=>{if(typeof events==='string')return r.fulfill({status:events==='500'?500:200,contentType:'text/html',body:'<p>no</p>'});const res=await r.fetch(),j=await res.json();j.events=events(j.events);await r.fulfill({response:res,json:j})});
 await Promise.all([pg.waitForResponse('**/api/community'),pg.goto(process.env.COMMUNITY_TEST_URL+'/')]);await pg.evaluate(()=>new Promise(r=>setTimeout(r,150)));
 const el=pg.locator('#next-hike-line'),a=el.locator('a'),box=await pg.evaluate(()=>{const l=document.querySelector('#next-hike-line').getBoundingClientRect(),h=document.querySelector('.hero-copy').getBoundingClientRect();return {out:l.width>0&&(l.left<h.left-1||l.right>h.right+1),page:document.documentElement.scrollWidth>innerWidth}});
 const r={staticAsked:reqs.some(u=>u.endsWith('/community.json')),hidden:await el.isHidden(),n:await el.count(),links:await a.count(),text:oneLine(await el.textContent()),href:await a.first().getAttribute('href').catch(()=>null),bold:await el.locator('b').count(),preview:reqs.some(u=>u.includes('hiking-preview')),sampleAsked:reqs.some(u=>/hiking-preview|trail-invitation/.test(u)),posts:posts.length,...box};
 check(!errs.length,'Page errors on the home page: '+JSON.stringify(errs));await c.close();return r};
const mk=(id,title,days_,status='scheduled')=>({...hike,id,title,status,startsAt:days(days_)}),shownText=(x,t)=>oneLine('Next hike: '+new Date(x.startsAt).toLocaleDateString('en-US',{timeZone:'America/Los_Angeles',weekday:'long',month:'long',day:'numeric'})+', '+new Date(x.startsAt).toLocaleTimeString('en-US',{timeZone:'America/Los_Angeles',hour:'numeric',minute:'2-digit'})+' - '+t);
const soon=mk('n-soon','QA earlier hike',10),late=mk('n-late','QA later hike',60);
let n=await nextLine(e=>[late,soon,mk('n-x','QA cancelled sooner',5,'cancelled')]);
check(!n.hidden&&n.n===1&&n.links===1&&n.href==='/hike#upcoming-hikes'&&n.text===shownText(soon,'QA earlier hike')&&/^Next hike: \w+day, \w+ \d+, \d+:\d\d [AP]M - QA earlier hike$/.test(n.text)&&!n.preview,'Next hike line wrong (earliest scheduled, cancelled skipped): '+JSON.stringify(n));
n=await nextLine(e=>[mk('n-b','QA <b>bold</b> & more',3)]);check(!n.hidden&&n.text.endsWith(' - QA <b>bold</b> & more')&&n.bold===0,'Title not shown literally: '+JSON.stringify(n));
for(const [name,events] of [['none',()=>[]],['cancelled only',()=>[mk('n-c','QA cancelled',3,'cancelled')]],['past or completed only',()=>[mk('n-p','QA past',-3),mk('n-d','QA done',3,'completed')]],['500','500'],['not JSON','200']]){
 n=await nextLine(events,390,null);check(n.hidden&&n.n===1&&n.links===0&&n.text==='','Next hike line shown for '+name+': '+JSON.stringify(n))}
// AV0007-01: API failing -> published community.json names the earliest scheduled hike; a valid live answer (even empty) never falls back.
const stat=[late,soon,mk('n-x','QA cancelled sooner',5,'cancelled')];
for(const [name,events] of [['500','500'],['not JSON','200']]){
 n=await nextLine(events,390,stat);check(!n.hidden&&n.n===1&&n.links===1&&n.href==='/hike#upcoming-hikes'&&n.text===shownText(soon,'QA earlier hike')&&!n.preview,'Static Next hike wrong after API '+name+': '+JSON.stringify(n))}
n=await nextLine('500',390,[mk('n-b','QA <b>bold</b> & more',3)]);check(!n.hidden&&n.text.endsWith(' - QA <b>bold</b> & more')&&n.bold===0,'Static title not literal: '+JSON.stringify(n));
for(const [name,sx] of [['none',[]],['cancelled only',[mk('n-c','QA cancelled',3,'cancelled')]],['past or completed only',[mk('n-p','QA past',-3),mk('n-d','QA done',3,'completed')]]]){
 n=await nextLine('500',390,sx);check(n.hidden&&n.n===1&&n.links===0&&n.text===''&&!n.preview,'Static Next hike shown for '+name+': '+JSON.stringify(n))}
n=await nextLine(e=>[],390,[mk('n-d','QA static decoy',3)]);check(n.hidden&&n.links===0&&!n.staticAsked,'Empty live calendar fell back to static: '+JSON.stringify(n));
n=await nextLine(e=>[mk('n-c','QA cancelled',3,'cancelled')],390,[mk('n-d','QA static decoy',3)]);check(n.hidden&&n.links===0&&!n.staticAsked,'Cancelled-only live calendar fell back to static: '+JSON.stringify(n));
n=await nextLine(e=>[soon],390,[mk('n-d','QA static decoy',3)]);check(!n.hidden&&n.text===shownText(soon,'QA earlier hike')&&!n.staticAsked,'Live hike did not win over static: '+JSON.stringify(n));
for(const width of [390,1440]){n=await nextLine(e=>[mk('n-w','QA a long hike title to check the line wraps inside the hero on a phone and a desktop',3)],width);check(!n.hidden&&!n.out&&!n.page,'Next hike line overflows at '+width+': '+JSON.stringify(n))}
// RF0814-11: the Next hike line names only a scheduled hike starting strictly after the fixed clock. Live and static-fallback matrices; the sample invitation is never asked for and nothing is POSTed.
{const NOW='2026-11-09T20:00:00Z',zones=[undefined,'Asia/Tokyo'],ev=(id,title,startsAt,status='scheduled')=>({...hike,id,title,status,startsAt,timezone:'America/Los_Angeles'});
 const nine=ev('r-9','QA started morning walk','2026-11-09T09:00:00-08:00'),three=ev('r-3','QA future afternoon walk','2026-11-09T15:00:00-08:00'),threeText='Next hike: Monday, November 9, 3:00 PM - QA future afternoon walk';
 const run=(src,events,clock)=>src==='live'?nextLine(()=>events,390,undefined,clock):nextLine('500',390,events,clock);
 const shown=(n,text,why)=>check(!n.hidden&&n.n===1&&n.links===1&&n.href==='/hike#upcoming-hikes'&&n.text===text&&!n.sampleAsked&&n.posts===0,why+': '+JSON.stringify(n)),
  hiddenLine=(n,why)=>check(n.hidden&&n.n===1&&n.links===0&&n.text===''&&!n.sampleAsked&&n.posts===0,why+': '+JSON.stringify(n));
 for(const src of ['live','static'])for(const tz of zones){const m=src+'/'+(tz||'viewer-default')+': ',clock={now:NOW,tz};
  // homeNextSkipsStartedWithFutureSibling (both input orders)
  shown(await run(src,[three,nine],clock),threeText,m+'started+future (future first)');shown(await run(src,[nine,three],clock),threeText,m+'started+future (started first)');
  shown(await run(src,[three],clock),threeText,m+'future only');hiddenLine(await run(src,[nine],clock),m+'started only');
  // homeNextStartBoundary
  shown(await run(src,[three],{now:'2026-11-09T22:59:59.999Z',tz}),threeText,m+'start-1ms');hiddenLine(await run(src,[three],{now:'2026-11-09T23:00:00.000Z',tz}),m+'exact start');hiddenLine(await run(src,[three],{now:'2026-11-09T23:00:00.001Z',tz}),m+'start+1ms');
  // homeNextAbsoluteTimeAcrossZones: identical 1:30 AM wall text twice on 1 Nov, chosen by instant; equal instants keep input order
  const pdt=ev('f-pdt','QA first 1:30','2026-11-01T01:30:00-07:00'),pst=ev('f-pst','QA second 1:30','2026-11-01T01:30:00-08:00');
  shown(await run(src,[pst,pdt],{now:'2026-11-01T08:00:00Z',tz}),'Next hike: Sunday, November 1, 1:30 AM - QA first 1:30',m+'before both 1:30s');
  shown(await run(src,[pst,pdt],{now:'2026-11-01T09:00:00Z',tz}),'Next hike: Sunday, November 1, 1:30 AM - QA second 1:30',m+'between the 1:30s');
  hiddenLine(await run(src,[pst,pdt],{now:'2026-11-01T09:30:00Z',tz}),m+'both 1:30s started');
  shown(await run(src,[ev('e-2','QA equal second','2026-12-06T09:00:00-08:00'),ev('e-1','QA equal first','2026-12-06T09:00:00-08:00')],clock),'Next hike: Sunday, December 6, 9:00 AM - QA equal second',m+'equal instants keep input order');
  // homeNextFiltersAndFallback: unusable records are never selected beside a valid future sibling; titles stay escaped
  const bad=[ev('x1','QA bad start','not a date'),{...ev('x2','QA no start',''),startsAt:undefined},ev('x3','QA cancelled','2026-11-09T16:00:00-08:00','cancelled'),ev('x4','QA completed','2026-11-09T16:00:00-08:00','completed')];
  shown(await run(src,[...bad,nine,ev('x5','QA <b>good</b> sibling','2026-11-09T17:00:00-08:00')],clock),'Next hike: Monday, November 9, 5:00 PM - QA <b>good</b> sibling',m+'filters + escaping');
  hiddenLine(await run(src,bad,clock),m+'only unusable records')}
 // a valid live answer with only a started walk (or nothing) is final: the static file's future decoy is never consulted
 n=await nextLine(()=>[nine],390,[three],{now:NOW});check(n.hidden&&n.links===0&&n.text===''&&!n.staticAsked&&n.posts===0&&!n.sampleAsked,'Started-only live calendar fell back to a static future decoy: '+JSON.stringify(n));
 n=await nextLine(()=>[],390,[three],{now:NOW});check(n.hidden&&n.links===0&&!n.staticAsked,'Empty live calendar fell back to static under a fixed clock: '+JSON.stringify(n));
 n=await nextLine('500',390,null,{now:NOW});hiddenLine(n,'API 500 and static 404 under a fixed clock')}
 const result={guestCountUpdatedAfterRSVP:true,demoGuestCountUnchanged:true,checkedAt:new Date().toISOString(),rsvpForm:true,newsletterForm:true,hikingUpdates:true,pastHikes:true,confirmedEventTakesPrecedence:true,realCalendarEmpty:true,demoPosts:posts.length,demoBrowserStorage:false,demoValidation:true,demoSuccessFocus:true,layouts,errors};
 fs.writeFileSync(out+'/community-ui-QA.json',JSON.stringify(result,null,2));
 console.log('Community UI passed');await b.close();
})().catch(e=>{console.error(e);process.exit(1)});

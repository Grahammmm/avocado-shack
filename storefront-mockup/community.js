(()=>{
let club, preview;
const dateLabel=e=>new Date(e.startsAt).toLocaleString('en-US',{timeZone:e.timezone||'America/Los_Angeles',weekday:'long',month:'long',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
const pacificDay=d=>new Date(d).toLocaleDateString('en-CA',{timeZone:'America/Los_Angeles'});
const upcoming=e=>e.status==='scheduled'&&(new Date(e.startsAt)>new Date()||pacificDay(e.startsAt)===pacificDay(Date.now()));
const showCancelled=e=>e.status==='cancelled'&&pacificDay(e.startsAt)>=pacificDay(Date.now());
// RF0834-14: only a scheduled hike says it started; a cancelled one keeps its planned date/time (dateLabel) before, at and after its start.
const hikeDate=e=>e.status==='scheduled'&&new Date(e.startsAt)<=new Date()?`Today — started ${new Date(e.startsAt).toLocaleTimeString('en-US',{timeZone:'America/Los_Angeles',hour:'numeric',minute:'2-digit'})}`:dateLabel(e);
const trailById=id=>(club.routeIdeas||[]).find(t=>t.id===id);
// AV0207-03: route ideas that have trail-explorer data (assets/trails/point-buchon.json); the explorer's element ids allow one per page.
const EXPLORER_TRAILS=new Set(['idea-point-buchon']);
const metric=(label,value,link='')=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}${link}</dd></div>`;
// AV0207-01: a set field is a non-empty string after trim; the Directions URL is encodeURIComponent'd, then esc()'d.
const set=v=>typeof v==='string'&&v.trim()!=='';
const directions=a=>` · <a class="text-link" href="${esc('https://www.google.com/maps/search/?api=1&query='+encodeURIComponent(a))}" target="_blank" rel="noopener">Directions</a>`;
// AV1422-06: no count at all (not "0") when nobody counted, i.e. the static site's null.
function attendance(e){if(e.confirmedGuests==null)return '';const n=Number.isInteger(e.confirmedGuests)&&e.confirmedGuests>=0?e.confirmedGuests:0;return `<p class="hike-attendance"><strong data-confirmed-guests>${n}</strong> confirmed ${n===1?'guest':'guests'}</p>`}
function details(e){return `<dl class="hike-facts">${[['Meet',e.meetingPoint],['Meet at',e.meetTime],['Address',e.meetingAddress],['Start',e.walkTime],['Back',e.returnTime],['Distance',e.distance],['Pace / terrain',e.difficulty],['Time on trail',e.duration],['Bring along',e.bring]].filter(x=>set(x[1])).map(([k,v])=>metric(k,v,k==='Address'?directions(v):'')).join('')}</dl>${set(e.accessNote)?`<p class="hike-access">${esc(e.accessNote)}</p>`:''}`}
function route(e){const t=e.trailId&&trailById(e.trailId);if(!t)return '';let https=false;try{https=new URL(t.sourceUrl).protocol==='https:'}catch{}return `<p class="hike-route">Route: ${esc(t.title)}${https?` · <a class="text-link" href="${esc(t.sourceUrl)}" target="_blank" rel="noopener">${esc(t.sourceName||'Trail information')} <span aria-hidden="true">↗</span></a>`:''}</p>`}
// AV1322-09: an "Add to calendar" .ics (RFC 5545) built in the page for an upcoming scheduled hike only; no server, no fetch.
// TEXT escaping: \ ; , escaped, newlines as \n, other control characters dropped; lines folded at 75 octets.
const icsText=s=>String(s??'').replace(/[\\;,]/g,'\\$&').replace(/\r\n?|\n/g,'\\n').replace(/[\x00-\x1f\x7f]/g,'');
const utf8=new TextEncoder(),fold=l=>{let o='',n=0;for(const c of l){const b=utf8.encode(c).length;if(n+b>75){o+='\r\n ';n=1}o+=c;n+=b}return o};
// Content has no end time, so the event length is a fixed, stated two hours (DURATION:PT2H).
function ics(e){const t=new Date(e.startsAt).toISOString().replace(/[-:]|\.\d+/g,'');return ['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Avocado Shack//Hiking Club//EN','BEGIN:VEVENT',`UID:${icsText(e.id)}@avocadoshack`,`DTSTAMP:${t}`,`DTSTART:${t}`,'DURATION:PT2H',`SUMMARY:${icsText(e.title)}`,`LOCATION:${icsText(set(e.meetingAddress)?(set(e.meetingPoint)?e.meetingPoint+', '+e.meetingAddress:e.meetingAddress):e.meetingPoint)}`,...(d=>d.length?[`DESCRIPTION:${icsText(d.join('\n'))}`]:[])([['Meet',e.meetTime],['Bring',e.bring],['Access',e.accessNote]].filter(x=>set(x[1])).map(x=>x[0]+': '+x[1])),`URL:${location.origin}/hike#${encodeURIComponent(e.id)}`,'END:VEVENT','END:VCALENDAR'].map(fold).join('\r\n')+'\r\n'}
// Scheduled and not yet started; an unparseable startsAt gives NaN, which is never > now, so no link (and ics() is never called).
// RF1050-24: only an explicitly zoned start (Z or +/-HH:MM) is exported; a zone-less one would take the visitor's zone. JS $ (no m flag) matches only the true end, so a final newline fails.
const calendarStart=e=>{const s=e&&e.startsAt;if(typeof s!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2})?(Z|[+-][0-9]{2}:[0-9]{2})$/.test(s))return null;const t=Date.parse(s);return Number.isFinite(t)?t:null};
function calendar(e){const t=e.status==='scheduled'?calendarStart(e):null;return t!==null&&t>Date.now()?`<p><a class="text-link hike-ics" download="${esc(e.id)}.ics" href="${esc('data:text/calendar;charset=utf-8,'+encodeURIComponent(ics(e)))}">Add to calendar</a></p>`:''}
// AV1109-13: display-only facts; the original record still owns RSVP and calendar data.
const invitationPhotos={'idea-point-buchon':`<figure class="trail-photograph"><img src="/assets/trails/point-buchon-coast.webp" alt="Sunlit sea arches and blue Pacific water below the bluffs at Point Buchon" loading="lazy" width="1600" height="1067"><figcaption><span>Point Buchon, from the bluffs.</span><span>Photo: <a href="https://commons.wikimedia.org/wiki/File:Waterscape_with_massive_arches_and_stone_outcroppings_of_Miguelito_shale,_Point_Buchon.jpg" target="_blank" rel="noopener">Mike Baird</a> · <a href="https://creativecommons.org/licenses/by/2.0/" target="_blank" rel="noopener">CC BY 2.0</a></span></figcaption></figure>`};
const firstText=(...values)=>values.find(set);
const safeGuide=t=>{try{return new URL(t?.sourceUrl).protocol==='https:'?t.sourceUrl:null}catch{return null}};
function invitationModel(e,t,{sample=false,label='',canExplore=false}={}){
 const x=e.status==='cancelled',started=label==='TODAY';
 const past=isNaN(Date.parse(e.startsAt))||pacificDay(e.startsAt)<pacificDay(Date.now());
 const day=new Date(e.startsAt).toLocaleDateString('en-US',{timeZone:'America/Los_Angeles',weekday:'long',month:'long',day:'numeric',year:'numeric'});
 const rows=sample?[['Round trip',t.distance],['Difficulty',t.difficulty],[t.elevationLabel,t.elevation],['Allow',t.duration]]:
  [['Distance',firstText(e.distance,t?.distance,'to be confirmed')],['Difficulty',firstText(e.difficulty,t?.difficulty,'to be confirmed')],...(set(t?.elevation)?[[firstText(t.elevationLabel,'Elevation change'),t.elevation]]:[]),['Time',firstText(e.duration,t?.duration,'to be confirmed')]];
 const state=sample||x||started?null:spotsState(e,spotsCount(e));
 const guide=safeGuide(t);
 return {e,t,sample,label:sample?'THE NEXT HIKE':label,cancelled:x,
  title:sample?`${esc(t.title)}<br><em>A morning on the coast.</em>`:`${x?'Cancelled: ':''}${esc(e.title)}`,
  place:sample?`${esc(t.place)} · Central Coast, California`:set(t?.place)?esc(t.place):'',
  date:sample?(past?'<p class="trail-invitation-date">Date to be confirmed</p>':`<p class="trail-invitation-date"><time datetime="${esc(e.startsAt)}">${esc(day)}</time> · ${esc(e.walkTime)}</p>`):`<p class="hike-date">${esc(hikeDate(e))}</p>`,
  description:sample?e.invitation:firstText(t?.description,e.description,'Michael will share the details soon.'),
  photo:Object.hasOwn(invitationPhotos,e.trailId)?invitationPhotos[e.trailId]:'',stats:rows.map(([k,v])=>metric(k,v)).join(''),
  spots:state?spotsMarkup(state):'',
  map:canExplore?'<div data-trail-explorer><p class="trail-map-unavailable">Loading the trail map…</p></div>':guide?`<p class="trail-map-unavailable"><a class="text-link" href="${esc(guide)}" target="_blank" rel="noopener">Trail map: official guide ↗</a></p>`:'<p class="trail-map-unavailable">Map to come.</p>',
  plan:sample?`<div class="trail-plan"><h3>Meet at the trailhead.</h3><dl class="trail-logistics"><div><dt>Meet at ${esc(e.meetTime)}</dt><dd>${esc(e.meetingPoint)}<br><span>${esc(e.meetingAddress)}</span></dd></div><div><dt>On the trail</dt><dd>${esc(e.walkTime)} start · back ${esc(e.returnTime.toLowerCase())}.<br><span>Time includes a relaxed pace and stops along the way.</span></dd></div><div><dt>Bring along</dt><dd>${esc(e.bring)}</dd></div></dl><p class="trail-access">${esc(e.accessNote)}</p><a class="text-link" href="${esc(t.sourceUrl)}" target="_blank" rel="noopener">Trail access &amp; visitor information <span aria-hidden="true">↗</span></a></div>`:richLogistics(e,t),
  join:sample?`<div class="trail-rsvp-wrap"><p class="label">WALK WITH US</p><h3 id="preview-rsvp-heading">I’ll come along.</h3>${attendance({confirmedGuests:0})}<p>Tell us who’s coming and how many are in your group.</p><form id="preview-hike-rsvp" aria-labelledby="preview-rsvp-heading"><div class="trail-form-row"><div><label for="preview-rsvp-name">Your name</label><input id="preview-rsvp-name" name="name" autocomplete="name" maxlength="120" required></div><div><label for="preview-rsvp-party">How many?</label><select id="preview-rsvp-party" name="partySize" aria-label="People attending, including you">${Array.from({length:6},(_,i)=>`<option value="${i+1}">${i+1} ${i?'people':'person'}</option>`).join('')}</select></div></div><label for="preview-rsvp-email">Email address</label><input id="preview-rsvp-email" name="email" type="email" autocomplete="email" required placeholder="you@example.com"><button class="button" type="submit">Count me in <span aria-hidden="true">↗</span></button><p class="sample-caption">Sample RSVP · nothing is sent or saved.</p><p class="form-status" role="status" tabindex="-1"></p></form></div>`:`<div class="trail-rsvp-wrap">${attendance(e)}${calendar(e)}${x?`${typeof e.cancelNote==='string'&&e.cancelNote?`<p class="club-small hike-cancel-note" data-hike-id="${esc(e.id)}">${esc(e.cancelNote)}</p>`:''}<p class="club-small">This hike is cancelled. Nothing else is needed from you.</p>`:started?'<p class="club-small">This hike has started, so RSVPs are closed.</p>':e.rsvpOpen&&(state.kind==='left'||state.kind==='nolimit')?`<button class="button" data-rsvp="${esc(e.id)}">RSVP to this hike ↗</button>`:''}</div>`};
}
function richLogistics(e,t){
 const rows=[['Meet',e.meetingPoint],['Meet at',e.meetTime],['Address',e.meetingAddress],['Start',e.walkTime],['Back',e.returnTime],['Route type',t?.routeType],['Terrain',t?.terrain],['Bring along',firstText(e.bring,'The usual: water, sturdy shoes, a layer and a snack.')]];
 return `<div class="trail-plan"><h3>Meet at the trailhead.</h3><dl class="hike-facts trail-logistics">${rows.filter(x=>set(x[1])).map(([k,v])=>metric(k,v,k==='Address'?directions(v):'')).join('')}</dl>${set(e.accessNote)?`<p class="hike-access">${esc(e.accessNote)}</p>`:''}${route(e)}</div>`;
}
function renderInvitation(m){
 const {e,sample}=m;
 return `<article${sample?'':anchor(e)} class="${sample?'':'hike-event'+(m.cancelled?' hike-cancelled':'')+' '}trail-invitation" ${sample?'aria-labelledby="featured-hike-title"':`aria-label="${esc(e.title)}"`}>
  <div class="trail-invitation-head"><p class="label">${m.label}</p>${sample?'<p class="sample-caption">Sample invitation · plans to be confirmed</p>':''}</div>
  <div class="trail-feature${m.photo?'':' trail-feature-no-photo'}">
   <div class="trail-feature-copy">${sample?`${m.place?`<p class="trail-place">${m.place}</p>`:''}<h2 id="featured-hike-title">${m.title}</h2>${m.date}`:`${m.date}<h2>${m.title}</h2>${m.place?`<p class="trail-place">${m.place}</p>`:''}`}<p>${esc(m.description)}</p><p class="trail-host-note">A community hike led by Michael Wolfe.</p></div>
   ${m.photo}
  </div>
  <dl class="trail-stats" aria-label="Hike at a glance">${m.stats}</dl>
  ${m.spots}${m.map}
  <div class="trail-plan-rsvp">
   ${m.plan}
   ${m.join}
  </div>
 </article>`;
}
function sampleInvitation(e){const t=trailById(e.trailId);return t?renderInvitation(invitationModel(e,t,{sample:true,canExplore:EXPLORER_TRAILS.has(e.trailId)})):''}
function sampleHistory(item,index){
 const t=trailById(item.trailId);if(!t)return '';
 return `<article class="trail-journal-entry"><div class="trail-journal-marker" aria-hidden="true">${index===0?'↗':'≈'}</div><div class="trail-journal-copy"><p class="trail-place">${esc(t.place)} <span>· ${esc(item.dateLabel)}</span></p><h3>${esc(t.title)}</h3><p>${esc(t.description)}</p><dl class="trail-journal-stats">${metric('Distance',t.distance)}${metric('Difficulty',t.difficulty)}${metric(t.elevationLabel,t.elevation)}${metric('Allow',t.duration)}</dl><a class="text-link" href="${esc(t.sourceUrl)}" target="_blank" rel="noopener">Explore this trail <span aria-hidden="true">↗</span></a></div></article>`;
}
// AV1622-03: a real completed hike is a trail-journal entry (same markup as sampleHistory). Its own title and recap lead; a matching public route idea adds place/stats/link, else its own fields. Empty stats are omitted.
function pastEntry(e,index){
 const t=trailById(e.trailId),own=(k)=>set(e[k])?e[k]:null;
 const tz=e.timezone||'America/Los_Angeles',ms=Date.parse(e.startsAt);
 const month=Number.isNaN(ms)?'':new Date(ms).toLocaleDateString('en-US',{timeZone:tz,month:'long',year:'numeric'});
 const place=t?(set(t.place)?t.place:null):own('meetingPoint');
 const rows=t?[['Distance',t.distance],['Difficulty',t.difficulty],[set(t.elevationLabel)?t.elevationLabel:'Elevation',t.elevation],['Allow',t.duration]]:[['Distance',e.distance],['Difficulty',e.difficulty],['Allow',e.duration]];
 const stats=rows.filter(x=>set(x[1])).map(([k,v])=>metric(k,v)).join('');
 let https=false;if(t){try{https=new URL(t.sourceUrl).protocol==='https:'}catch{}}
 const when=month?`<span>${place?'· ':''}<time datetime="${esc(e.startsAt)}">${esc(month)}</time></span>`:'';
 return `<article${anchor(e)} class="trail-journal-entry"><div class="trail-journal-marker" aria-hidden="true">${index===0?'↗':'≈'}</div><div class="trail-journal-copy"><p class="trail-place">${place?esc(place)+' ':''}${when}</p><h3>${esc(e.title)}</h3><p class="trail-journal-recap">${esc(e.recap||e.description||'')}</p>${stats?`<dl class="trail-journal-stats">${stats}</dl>`:''}${https?`<a class="text-link" href="${esc(t.sourceUrl)}" target="_blank" rel="noopener">Explore this trail <span aria-hidden="true">↗</span></a>`:''}</div></article>`;
}
// AV1422-08: the 1.8 MB aerial and route file load only once the map is within one screen of view.
function mountWhenNear(host){
 if(!host||host.dataset.observing)return;host.dataset.observing='true';
 if(!('IntersectionObserver' in window))return window.AvoshackTrailExplorer?.mount(host);
 const io=new IntersectionObserver(es=>{if(es.some(e=>e.isIntersecting)){io.disconnect();window.AvoshackTrailExplorer?.mount(host)}},{rootMargin:'100% 0px'});io.observe(host);
}
// SPOTS-BEGIN AV1109-12 (docs/hass/HIKE-PAGE.md 3.3.1): one line says what is known about spots. A limit (capacity) may be stated on its own; "left" only from a trusted count, i.e. whole numbers, capacity 1-1000 equal to the hike's own capacity, 0 <= left <= capacity. Anything else is unknown, never coerced or inferred.
// count is null or {capacity, remaining}. Internal seam (AV1109-13 reuses it), not a wire format.
const spotsCapacity=e=>Number.isInteger(e.capacity)&&e.capacity>0?e.capacity:null;
function spotsState(e,count){
 const cap=spotsCapacity(e);
 if(e.rsvpEnabled!==true||(!e.staticSite&&e.rsvpOpen!==true))return {kind:'off',text:'RSVP details will be shared when confirmed.'};
 if(cap===null)return {kind:'nolimit',text:'To join, ask at the Shack.'};
 const c=count&&Number.isInteger(count.capacity)&&count.capacity>=1&&count.capacity<=1000&&count.capacity===cap&&Number.isInteger(count.remaining)&&count.remaining>=0&&count.remaining<=cap?count.remaining:null;
 if(c===null)return {kind:'unknown',text:`Limited to ${cap} people · availability unconfirmed; ask at the Shack`};
 if(c===0)return {kind:'full',full:true,text:'Full. Ask at the Shack to go on the waitlist.',compact:'Full'};
 return {kind:'left',text:`${c} spot${c===1?'':'s'} left`};
}
const spotsMarkup=s=>`<p class="club-small${s.full?' hike-full':''}">${esc(s.text)}</p>`;
// The live API computes capacity and remaining together; the static community.json has no count (any stray one is ignored).
const spotsCount=e=>e.staticSite?null:{capacity:e.capacity,remaining:e.remaining};
// SPOTS-END
// AV1622-01: a real hike card carries its event id (the address the .ics URL: line links to), unless the id is empty, already a page id, or already used by an earlier card.
const staticIds=new Set(),usedIds=new Set();let jumped=false,scanned=false;
const anchor=e=>{const id=e&&e.id;if(typeof id!=='string'||id===''||staticIds.has(id)||usedIds.has(id))return '';usedIds.add(id);return ` id="${esc(id)}"`};
// Once per page load, after the first render: scroll to and focus the card the address names; unknown, malformed or static ids do nothing.
function jump(){let want;try{want=decodeURIComponent((location.hash||'').slice(1))}catch{return}
 if(!want||staticIds.has(want))return;
 const card=[...document.querySelectorAll('#upcoming-hikes .hike-event[id], #past-hikes .trail-journal-entry[id]')].find(x=>x.id===want);if(!card)return;
 card.scrollIntoView({block:'start'});card.setAttribute('tabindex','-1');card.focus({preventScroll:true})}
function render(){
 usedIds.clear();
 const next=club.events.filter(e=>upcoming(e)||showCancelled(e)).sort((a,b)=>new Date(a.startsAt)-new Date(b.startsAt));
 const samplesOn=club.showSamples!==false,demo=samplesOn&&preview?.enabled&&preview.upcoming&&trailById(preview.upcoming.trailId);
 let explorer=false;const now=Date.now(),started=e=>e.status==='scheduled'&&Date.parse(e.startsAt)<=now&&pacificDay(e.startsAt)===pacificDay(now),first=next.find(e=>e.status==='scheduled'&&Date.parse(e.startsAt)>now);
 $('#upcoming-hikes').innerHTML=next.length?next.map(e=>{const x=e.status==='cancelled',t=started(e),trail=trailById(e.trailId);
  const canExplore=!explorer&&e.status==='scheduled'&&!!trail&&EXPLORER_TRAILS.has(e.trailId);if(canExplore)explorer=true;
  return renderInvitation(invitationModel(e,trail,{label:x?'CANCELLED':t?'TODAY':e===first?'THE NEXT HIKE':'COMING UP',canExplore}));}).join(''):demo?sampleInvitation(preview.upcoming):'<div class="hike-empty"><h2>The next walk starts here.</h2><p>No hike is currently scheduled. When Michael confirms the next outing, you’ll find the trail, date, meeting point, and RSVP here.</p><a class="text-link" href="#hike-updates">Tell me when a hike is planned ↗</a></div>';
 const past=club.events.filter(e=>e.status==='completed').sort((a,b)=>new Date(b.startsAt)-new Date(a.startsAt));
 const samplePast=samplesOn&&!past.length&&preview?.enabled&&(preview.past||[]).some(e=>trailById(e.trailId));
 $('#history-context').textContent=samplePast?'Sample archive · these outings are not confirmed club history.':'Places and memories from our walks together.';
 $('#past-hikes').classList.toggle('trail-journal',!!(past.length||samplePast));
 $('#past-hikes').innerHTML=past.length?past.map(pastEntry).join(''):samplePast?preview.past.map(sampleHistory).join(''):'<p class="club-small history-empty">We’re gathering the club’s past outings. Routes and stories will appear here as Michael shares them.</p>';
 mountWhenNear(document.querySelector('[data-trail-explorer]'));
 if(!jumped){jumped=true;jump()}
 const form=$('#preview-hike-rsvp');
 if(form)form.onsubmit=e=>{e.preventDefault();const status=form.querySelector('.form-status');status.textContent='That’s how the RSVP will work. No details were saved or sent.';form.reset();status.focus();};
}
// The live club service adds RSVP counts; a plain static host has no /api, so fall back to the published
// community.json (same club, events and route ideas). Without the service nobody can RSVP online.
// The club service's GET (no visitor data) answers acceptsSubmissions:true; that is the only way a form may POST.
// One GET /api/community at a time: callers that arrive while it is in flight (the probe, loadNext, liveData) share it.
let serviceProbe,inflight;
const apiCommunity=()=>inflight??=(async()=>{try{
 const r=await fetch('/api/community',{cache:'no-store'});
 if(!r.ok||!(r.headers.get('Content-Type')||'').includes('application/json'))return null;
 return await r.json()}catch{return null}})().finally(()=>{inflight=null});
const liveData=()=>apiCommunity();
const liveService=()=>serviceProbe??=apiCommunity().then(d=>d?.acceptsSubmissions===true);
async function clubData(){
 const live=await liveData();if(live)return live;
 const r=await fetch('/community.json',{cache:'no-store'});if(!r.ok)throw Error();
 const data=await r.json();data.events=(data.events||[]).map(e=>({...e,confirmedGuests:null,remaining:null,rsvpOpen:false,staticSite:true}));return data;
}
async function load(){try{
 if(!scanned){scanned=true;document.querySelectorAll('[id]').forEach(x=>staticIds.add(x.id))}
 const [data,previewResponse]=await Promise.all([clubData(),fetch('/hiking-preview.json',{cache:'no-store'}).catch(()=>null)]);
 club=data;preview=previewResponse?.ok?await previewResponse.json().catch(()=>null):null;render();
}catch{$('#upcoming-hikes').innerHTML='<p>The hike calendar isn’t available right now. Please try again shortly.</p>';$('#past-hikes').innerHTML='<p class="club-small">Past outings will appear when the calendar is available.</p>'}}
// Visitors only ever see these sentences or the service's own plain message, never a browser or parser error.
const SIGNUP_CLOSED='Online signup isn’t open yet, so nothing was sent or saved. Please say hello at the Shack instead.';
const SIGNUP_UNREACHABLE='We couldn’t reach the signup service, so nothing was saved. Please try again later.';
async function send(form,path,data){const status=form.querySelector('.form-status'),button=form.querySelector('button[type="submit"]');button.disabled=true;status.textContent='Saving…';try{
 // Without the club service (the published static site) nothing the visitor typed leaves the browser.
 if(!await liveService()){status.textContent=SIGNUP_CLOSED;return false}
 let r;try{r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}catch{status.textContent=SIGNUP_UNREACHABLE;return false}
 let result=null;if((r.headers.get('Content-Type')||'').includes('application/json'))result=await r.json().catch(()=>null);
 if(!r.ok||!result||typeof result.message!=='string'){status.textContent=result&&typeof result.error==='string'?result.error:SIGNUP_CLOSED;return false}
 status.textContent=result.message;form.reset();return true
}finally{button.disabled=form.getAttribute('aria-disabled')==='true'}}
if($('#hike-updates'))$('#hike-updates').onsubmit=e=>{e.preventDefault();send(e.currentTarget,'/api/community/subscriptions',{email:e.currentTarget.email.value,newsletter:false,hikes:true})};
if($('#community-newsletter'))$('#community-newsletter').onsubmit=e=>{e.preventDefault();send(e.currentTarget,'/api/community/subscriptions',{email:e.currentTarget.email.value,newsletter:true,hikes:e.currentTarget.hikes.checked})};
// AV1422-07: without the club service both signup forms say so up front and are disabled; while the probe is pending they stay enabled. Same cached probe as send(); it shares the page's one in-flight GET /api/community.
const SIGNUP_CLOSED_UPFRONT='Online signup isn’t open yet. Please say hello at the Shack instead.';
for(const form of [$('#community-newsletter'),$('#hike-updates')])if(form)liveService().then(ok=>{if(ok)return;form.querySelector('.form-status').textContent=SIGNUP_CLOSED_UPFRONT;form.setAttribute('aria-disabled','true');form.querySelectorAll('input,select,textarea,button').forEach(x=>x.disabled=true)});
if($('#upcoming-hikes'))$('#upcoming-hikes').onclick=e=>{const button=e.target.closest('[data-rsvp]');if(!button)return;const event=club.events.find(x=>x.id===button.dataset.rsvp);if(!event)return;show(`<p class="label">NORTH COAST HIKING CLUB</p><h2>Join the next hike.</h2><h3>${esc(event.title)}</h3><p>${esc(dateLabel(event))}</p>${details(event)}<form id="hike-rsvp"><label for="rsvp-name">Your name</label><input id="rsvp-name" name="name" autocomplete="name" maxlength="120" required><label for="rsvp-email">Email address</label><input id="rsvp-email" name="email" type="email" autocomplete="email" required><label for="rsvp-party">People in your group, including you</label><select id="rsvp-party" name="partySize">${Array.from({length:Math.min(6,event.remaining??6)},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join('')}</select><p class="setup-note">Your RSVP goes on the club’s list. No confirmation email is sent.</p><button class="button" type="submit">Save my RSVP ↗</button><p class="form-status" role="status"></p></form>`);$('#hike-rsvp').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;const saved=await send(f,'/api/community/rsvps',{eventId:event.id,name:f.elements.name.value,email:f.elements.email.value,partySize:Number(f.elements.partySize.value)});if(saved)load()}};
// AV1102-04/AV0007-01: the home page's one "Next hike" line. Live /api/community, else the published /community.json (never the sample hikes); any failure or no scheduled upcoming hike leaves it hidden.
// RF0814-11: only scheduled events starting strictly after the instant sampled once at load are eligible (by parsed instant, not calendar day), so a started walk (still TODAY on /hike via upcoming()) never hides the actual next hike; started-only leaves the line hidden.
async function loadNext(){try{
 const data=await clubData(),now=Date.now();
 const e=(data.events||[]).filter(x=>x.status==='scheduled'&&new Date(x.startsAt).getTime()>now).sort((a,b)=>new Date(a.startsAt)-new Date(b.startsAt))[0];if(!e)return;
 const at=new Date(e.startsAt),tz=e.timezone||'America/Los_Angeles',line=$('#next-hike-line');
 const when=at.toLocaleDateString('en-US',{timeZone:tz,weekday:'long',month:'long',day:'numeric'})+', '+at.toLocaleTimeString('en-US',{timeZone:tz,hour:'numeric',minute:'2-digit'});
 line.innerHTML=`<a class="text-link" href="/hike#upcoming-hikes">Next hike: ${esc(when)} - ${esc(e.title)}</a>`;line.hidden=false}catch{}}
if($('#upcoming-hikes'))load();else if($('#next-hike-line'))loadNext();
})();

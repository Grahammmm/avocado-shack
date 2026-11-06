(()=>{
let club, preview;
const dateLabel=e=>new Date(e.startsAt).toLocaleString('en-US',{timeZone:e.timezone||'America/Los_Angeles',weekday:'long',month:'long',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
const pacificDay=d=>new Date(d).toLocaleDateString('en-CA',{timeZone:'America/Los_Angeles'});
const upcoming=e=>e.status==='scheduled'&&(new Date(e.startsAt)>new Date()||pacificDay(e.startsAt)===pacificDay(Date.now()));
const showCancelled=e=>e.status==='cancelled'&&pacificDay(e.startsAt)>=pacificDay(Date.now());
const hikeDate=e=>new Date(e.startsAt)<=new Date()?`Today — started ${new Date(e.startsAt).toLocaleTimeString('en-US',{timeZone:'America/Los_Angeles',hour:'numeric',minute:'2-digit'})}`:dateLabel(e);
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
function sampleInvitation(e){
 const t=trailById(e.trailId); if(!t)return '';
 // AV1422-05: once the sample's Pacific day has passed (or startsAt is unparseable) say so instead of showing a past date.
 const past=isNaN(Date.parse(e.startsAt))||pacificDay(e.startsAt)<pacificDay(Date.now());
 const day=new Date(e.startsAt).toLocaleDateString('en-US',{timeZone:'America/Los_Angeles',weekday:'long',month:'long',day:'numeric',year:'numeric'});
 return `<article class="trail-invitation" aria-labelledby="featured-hike-title">
  <div class="trail-invitation-head"><p class="label">THE NEXT HIKE</p><p class="sample-caption">Sample invitation · plans to be confirmed</p></div>
  <div class="trail-feature">
   <div class="trail-feature-copy"><p class="trail-place">${esc(t.place)} · Central Coast, California</p><h2 id="featured-hike-title">${esc(t.title)}<br><em>A morning on the coast.</em></h2>${past?'<p class="trail-invitation-date">Date to be confirmed</p>':`<p class="trail-invitation-date"><time datetime="${esc(e.startsAt)}">${esc(day)}</time> · ${esc(e.walkTime)}</p>`}<p>${esc(e.invitation)}</p><p class="trail-host-note">A community hike led by Michael Wolfe.</p></div>
   <figure class="trail-photograph"><img src="/assets/trails/point-buchon-coast.webp" alt="Sunlit sea arches and blue Pacific water below the bluffs at Point Buchon" loading="lazy" width="1600" height="1067"><figcaption><span>Point Buchon, from the bluffs.</span><span>Photo: <a href="https://commons.wikimedia.org/wiki/File:Waterscape_with_massive_arches_and_stone_outcroppings_of_Miguelito_shale,_Point_Buchon.jpg" target="_blank" rel="noopener">Mike Baird</a> · <a href="https://creativecommons.org/licenses/by/2.0/" target="_blank" rel="noopener">CC BY 2.0</a></span></figcaption></figure>
  </div>
  <dl class="trail-stats" aria-label="Hike at a glance">${metric('Round trip',t.distance)}${metric('Difficulty',t.difficulty)}${metric(t.elevationLabel,t.elevation)}${metric('Allow',t.duration)}</dl>
  <div data-trail-explorer><p class="trail-map-unavailable">Loading the trail map…</p></div>
  <div class="trail-plan-rsvp">
   <div class="trail-plan"><h3>Meet at the trailhead.</h3><dl class="trail-logistics"><div><dt>Meet at ${esc(e.meetTime)}</dt><dd>${esc(e.meetingPoint)}<br><span>${esc(e.meetingAddress)}</span></dd></div><div><dt>On the trail</dt><dd>${esc(e.walkTime)} start · back ${esc(e.returnTime.toLowerCase())}.<br><span>Time includes a relaxed pace and stops along the way.</span></dd></div><div><dt>Bring along</dt><dd>${esc(e.bring)}</dd></div></dl><p class="trail-access">${esc(e.accessNote)}</p><a class="text-link" href="${esc(t.sourceUrl)}" target="_blank" rel="noopener">Trail access &amp; visitor information <span aria-hidden="true">↗</span></a></div>
   <div class="trail-rsvp-wrap"><p class="label">WALK WITH US</p><h3 id="preview-rsvp-heading">I’ll come along.</h3>${attendance({confirmedGuests:0})}<p>Tell us who’s coming and how many are in your group.</p><form id="preview-hike-rsvp" aria-labelledby="preview-rsvp-heading"><div class="trail-form-row"><div><label for="preview-rsvp-name">Your name</label><input id="preview-rsvp-name" name="name" autocomplete="name" maxlength="120" required></div><div><label for="preview-rsvp-party">How many?</label><select id="preview-rsvp-party" name="partySize" aria-label="People attending, including you">${Array.from({length:6},(_,i)=>`<option value="${i+1}">${i+1} ${i?'people':'person'}</option>`).join('')}</select></div></div><label for="preview-rsvp-email">Email address</label><input id="preview-rsvp-email" name="email" type="email" autocomplete="email" required placeholder="you@example.com"><button class="button" type="submit">Count me in <span aria-hidden="true">↗</span></button><p class="sample-caption">Sample RSVP · nothing is sent or saved.</p><p class="form-status" role="status" tabindex="-1"></p></form></div>
  </div>
 </article>`;
}
function sampleHistory(item,index){
 const t=trailById(item.trailId);if(!t)return '';
 return `<article class="trail-journal-entry"><div class="trail-journal-marker" aria-hidden="true">${index===0?'↗':'≈'}</div><div class="trail-journal-copy"><p class="trail-place">${esc(t.place)} <span>· ${esc(item.dateLabel)}</span></p><h3>${esc(t.title)}</h3><p>${esc(t.description)}</p><dl class="trail-journal-stats">${metric('Distance',t.distance)}${metric('Difficulty',t.difficulty)}${metric(t.elevationLabel,t.elevation)}${metric('Allow',t.duration)}</dl><a class="text-link" href="${esc(t.sourceUrl)}" target="_blank" rel="noopener">Explore this trail <span aria-hidden="true">↗</span></a></div></article>`;
}
// AV1422-08: the 1.8 MB aerial and route file load only once the map is within one screen of view.
function mountWhenNear(host){
 if(!host||host.dataset.observing)return;host.dataset.observing='true';
 if(!('IntersectionObserver' in window))return window.AvoshackTrailExplorer?.mount(host);
 const io=new IntersectionObserver(es=>{if(es.some(e=>e.isIntersecting)){io.disconnect();window.AvoshackTrailExplorer?.mount(host)}},{rootMargin:'100% 0px'});io.observe(host);
}
// AV1622-01: a real hike card carries its event id (the address the .ics URL: line links to), unless the id is empty, already a page id, or already used by an earlier card.
const staticIds=new Set(),usedIds=new Set();let jumped=false,scanned=false;
const anchor=e=>{const id=e&&e.id;if(typeof id!=='string'||id===''||staticIds.has(id)||usedIds.has(id))return '';usedIds.add(id);return ` id="${esc(id)}"`};
// Once per page load, after the first render: scroll to and focus the card the address names; unknown, malformed or static ids do nothing.
function jump(){let want;try{want=decodeURIComponent((location.hash||'').slice(1))}catch{return}
 if(!want||staticIds.has(want))return;
 const card=[...document.querySelectorAll('#upcoming-hikes .hike-event[id], #past-hikes .past-hike[id]')].find(x=>x.id===want);if(!card)return;
 card.scrollIntoView({block:'start'});card.setAttribute('tabindex','-1');card.focus({preventScroll:true})}
function render(){
 usedIds.clear();
 const next=club.events.filter(e=>upcoming(e)||showCancelled(e)).sort((a,b)=>new Date(a.startsAt)-new Date(b.startsAt));
 const samplesOn=club.showSamples!==false,demo=samplesOn&&preview?.enabled&&preview.upcoming&&trailById(preview.upcoming.trailId);
 let explorer=false;const now=Date.now(),started=e=>e.status==='scheduled'&&Date.parse(e.startsAt)<=now&&pacificDay(e.startsAt)===pacificDay(now),first=next.find(e=>e.status==='scheduled'&&Date.parse(e.startsAt)>now);
 $('#upcoming-hikes').innerHTML=next.length?next.map(e=>{const x=e.status==='cancelled',t=started(e);return `<article${anchor(e)} class="hike-event${x?' hike-cancelled':''}"><p class="label">${x?'CANCELLED':t?'TODAY':e===first?'THE NEXT HIKE':'COMING UP'}</p><p class="hike-date">${esc(hikeDate(e))}</p><h2>${x?'Cancelled: ':''}${esc(e.title)}</h2><p>${esc(e.description||'')}</p>${attendance(e)}${details(e)}${route(e)}${!explorer&&e.status==='scheduled'&&EXPLORER_TRAILS.has(e.trailId)&&trailById(e.trailId)&&(explorer=true)?'<div data-trail-explorer><p class="trail-map-unavailable">Loading the trail map…</p></div>':''}${calendar(e)}${x?'<p class="club-small">This hike is cancelled. Nothing else is needed from you.</p>':t?'<p class="club-small">This hike has started, so RSVPs are closed.</p>':e.rsvpOpen?e.remaining===0?'<p class="club-small hike-full">This hike is full.</p>':`<p class="club-small">${e.remaining===null?'RSVPs open':`${e.remaining} place${e.remaining===1?'':'s'} available`}</p><button class="button" data-rsvp="${esc(e.id)}">RSVP to this hike ↗</button>`:e.staticSite&&e.rsvpEnabled?'<p class="club-small">To join, ask at the Shack.</p>':'<p class="club-small">RSVP details will be shared when confirmed.</p>'}</article>`}).join(''):demo?sampleInvitation(preview.upcoming):'<div class="hike-empty"><h2>The next walk starts here.</h2><p>No hike is currently scheduled. When Michael confirms the next outing, you’ll find the trail, date, meeting point, and RSVP here.</p><a class="text-link" href="#hike-updates">Tell me when a hike is planned ↗</a></div>';
 const past=club.events.filter(e=>e.status==='completed').sort((a,b)=>new Date(b.startsAt)-new Date(a.startsAt));
 const samplePast=samplesOn&&!past.length&&preview?.enabled&&(preview.past||[]).some(e=>trailById(e.trailId));
 $('#history-context').textContent=samplePast?'Sample archive · these outings are not confirmed club history.':'Places and memories from our walks together.';
 $('#past-hikes').classList.toggle('trail-journal',!!samplePast);
 $('#past-hikes').innerHTML=past.length?past.map(e=>`<details${anchor(e)} class="past-hike"><summary><span>${esc(e.title)}</span><time>${esc(new Date(e.startsAt).toLocaleDateString('en-US',{timeZone:e.timezone||'America/Los_Angeles',month:'long',day:'numeric',year:'numeric'}))}</time></summary><p>${esc(e.recap||e.description||'')}</p>${details(e)}</details>`).join(''):samplePast?preview.past.map(sampleHistory).join(''):'<p class="club-small history-empty">We’re gathering the club’s past outings. Routes and stories will appear here as Michael shares them.</p>';
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
async function loadNext(){try{
 const data=await clubData();
 const e=(data.events||[]).filter(upcoming).sort((a,b)=>new Date(a.startsAt)-new Date(b.startsAt))[0];if(!e)return;
 const at=new Date(e.startsAt),tz=e.timezone||'America/Los_Angeles',line=$('#next-hike-line');
 const when=at.toLocaleDateString('en-US',{timeZone:tz,weekday:'long',month:'long',day:'numeric'})+', '+at.toLocaleTimeString('en-US',{timeZone:tz,hour:'numeric',minute:'2-digit'});
 line.innerHTML=`<a class="text-link" href="/hike#upcoming-hikes">Next hike: ${esc(when)} - ${esc(e.title)}</a>`;line.hidden=false}catch{}}
if($('#upcoming-hikes'))load();else if($('#next-hike-line'))loadNext();
})();

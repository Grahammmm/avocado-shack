(()=>{
let club, preview;
const dateLabel=e=>new Date(e.startsAt).toLocaleString('en-US',{timeZone:e.timezone||'America/Los_Angeles',weekday:'long',month:'long',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'});
const upcoming=e=>e.status==='scheduled'&&new Date(e.startsAt)>new Date();
const trailById=id=>(club.routeIdeas||[]).find(t=>t.id===id);
const metric=(label,value)=>`<div><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`;
function details(e){return `<dl class="hike-facts">${[['Meet',e.meetingPoint],['Distance',e.distance],['Pace / terrain',e.difficulty],['Time on trail',e.duration]].filter(x=>x[1]).map(([k,v])=>metric(k,v)).join('')}</dl>`}
function sampleInvitation(e){
 const t=trailById(e.trailId); if(!t)return '';
 const day=new Date(e.startsAt).toLocaleDateString('en-US',{timeZone:'America/Los_Angeles',weekday:'long',month:'long',day:'numeric',year:'numeric'});
 return `<article class="trail-invitation" aria-labelledby="featured-hike-title">
  <div class="trail-invitation-head"><p class="label">THE NEXT HIKE</p><p class="sample-caption">Sample invitation · plans to be confirmed</p></div>
  <div class="trail-feature">
   <div class="trail-feature-copy"><p class="trail-place">${esc(t.place)} · Central Coast, California</p><h3 id="featured-hike-title">${esc(t.title)}<br><em>A morning on the coast.</em></h3><p class="trail-invitation-date"><time datetime="${esc(e.startsAt)}">${esc(day)}</time> · ${esc(e.walkTime)}</p><p>${esc(e.invitation)}</p><p class="trail-host-note">A community hike led by Michael Wolfe.</p></div>
   <figure class="trail-map"><img src="assets/point-buchon-trail.svg" alt="Illustrated Point Buchon coastal route from Coon Creek toward Windy Point" loading="lazy" width="600" height="450"><figcaption><span>THE COAST, AT WALKING PACE</span><span>Route illustration · not for navigation</span></figcaption></figure>
  </div>
  <dl class="trail-stats" aria-label="Hike at a glance">${metric('Round trip',t.distance)}${metric('Difficulty',t.difficulty)}${metric(t.elevationLabel,t.elevation)}${metric('Allow',t.duration)}</dl>
  <div class="trail-plan-rsvp">
   <div class="trail-plan"><h4>Meet at the trailhead.</h4><dl class="trail-logistics"><div><dt>Meet at ${esc(e.meetTime)}</dt><dd>${esc(e.meetingPoint)}<br><span>${esc(e.meetingAddress)}</span></dd></div><div><dt>On the trail</dt><dd>${esc(e.walkTime)} start · back ${esc(e.returnTime.toLowerCase())}.<br><span>Time includes a relaxed pace and stops along the way.</span></dd></div><div><dt>Bring along</dt><dd>${esc(e.bring)}</dd></div></dl><p class="trail-access">${esc(e.accessNote)}</p><a class="text-link" href="${esc(t.sourceUrl)}" target="_blank" rel="noopener">Trail access &amp; visitor information <span aria-hidden="true">↗</span></a></div>
   <div class="trail-rsvp-wrap"><p class="label">WALK WITH US</p><h4 id="preview-rsvp-heading">I’ll come along.</h4><p>Tell us who’s coming and how many are in your group.</p><form id="preview-hike-rsvp" aria-labelledby="preview-rsvp-heading"><div class="trail-form-row"><div><label for="preview-rsvp-name">Your name</label><input id="preview-rsvp-name" name="name" autocomplete="name" maxlength="120" required></div><div><label for="preview-rsvp-party">How many?</label><select id="preview-rsvp-party" name="partySize" aria-label="People attending, including you">${Array.from({length:6},(_,i)=>`<option value="${i+1}">${i+1} ${i?'people':'person'}</option>`).join('')}</select></div></div><label for="preview-rsvp-email">Email address</label><input id="preview-rsvp-email" name="email" type="email" autocomplete="email" required placeholder="you@example.com"><button class="button" type="submit">Count me in <span aria-hidden="true">↗</span></button><p class="sample-caption">Sample RSVP · nothing is sent or saved.</p><p class="form-status" role="status" tabindex="-1"></p></form></div>
  </div>
 </article>`;
}
function sampleHistory(item,index){
 const t=trailById(item.trailId);if(!t)return '';
 return `<article class="trail-journal-entry"><div class="trail-journal-marker" aria-hidden="true">${index===0?'↗':'≈'}</div><div class="trail-journal-copy"><p class="trail-place">${esc(t.place)} <span>· ${esc(item.dateLabel)}</span></p><h4>${esc(t.title)}</h4><p>${esc(t.description)}</p><dl class="trail-journal-stats">${metric('Distance',t.distance)}${metric('Difficulty',t.difficulty)}${metric(t.elevationLabel,t.elevation)}${metric('Allow',t.duration)}</dl><a class="text-link" href="${esc(t.sourceUrl)}" target="_blank" rel="noopener">Explore this trail <span aria-hidden="true">↗</span></a></div></article>`;
}
function render(){
 const next=club.events.filter(upcoming).sort((a,b)=>new Date(a.startsAt)-new Date(b.startsAt));
 const demo=preview?.enabled&&preview.upcoming&&trailById(preview.upcoming.trailId);
 $('#upcoming-hikes').innerHTML=next.length?next.map(e=>`<article class="hike-event"><p class="label">THE NEXT HIKE</p><p class="hike-date">${esc(dateLabel(e))}</p><h3>${esc(e.title)}</h3><p>${esc(e.description||'')}</p>${details(e)}${e.rsvpOpen?`<p class="club-small">${e.remaining===null?'RSVPs open':`${e.remaining} places available`}</p><button class="button" data-rsvp="${esc(e.id)}" ${e.remaining===0?'disabled':''}>${e.remaining===0?'This hike is full':'RSVP to this hike ↗'}</button>`:'<p class="club-small">RSVP details will be shared when confirmed.</p>'}</article>`).join(''):demo?sampleInvitation(preview.upcoming):'<div class="hike-empty"><h3>The next walk starts here.</h3><p>No hike is currently scheduled. When Michael confirms the next outing, you’ll find the trail, date, meeting point, and RSVP here.</p><a class="text-link" href="#hike-updates">Tell me when a hike is planned ↗</a></div>';
 const past=club.events.filter(e=>e.status==='completed').sort((a,b)=>new Date(b.startsAt)-new Date(a.startsAt));
 const samplePast=!past.length&&preview?.enabled&&(preview.past||[]).some(e=>trailById(e.trailId));
 $('#history-context').textContent=samplePast?'Sample archive · these outings are not confirmed club history.':'Places and memories from our walks together.';
 $('#past-hikes').classList.toggle('trail-journal',!!samplePast);
 $('#past-hikes').innerHTML=past.length?past.map(e=>`<details class="past-hike"><summary><span>${esc(e.title)}</span><time>${esc(new Date(e.startsAt).toLocaleDateString('en-US',{timeZone:e.timezone||'America/Los_Angeles',month:'long',day:'numeric',year:'numeric'}))}</time></summary><p>${esc(e.recap||e.description||'')}</p>${details(e)}</details>`).join(''):samplePast?preview.past.map(sampleHistory).join(''):'<p class="club-small history-empty">We’re gathering the club’s past outings. Routes and stories will appear here as Michael shares them.</p>';
 const form=$('#preview-hike-rsvp');
 if(form)form.onsubmit=e=>{e.preventDefault();const status=form.querySelector('.form-status');status.textContent='That’s how the RSVP will work. No details were saved or sent.';form.reset();status.focus();};
}
async function load(){try{
 const responses=await Promise.all([fetch('/api/community',{cache:'no-store'}),fetch('/hiking-preview.json',{cache:'no-store'}).catch(()=>null)]);
 if(!responses[0].ok)throw Error();
 club=await responses[0].json();preview=responses[1]?.ok?await responses[1].json().catch(()=>null):null;render();
}catch{$('#upcoming-hikes').innerHTML='<p>The hike calendar isn’t available right now. Please try again shortly.</p>';$('#past-hikes').innerHTML='<p class="club-small">Past outings will appear when the calendar is available.</p>'}}
async function send(form,path,data){const status=form.querySelector('.form-status'),button=form.querySelector('button[type="submit"]');button.disabled=true;status.textContent='Saving…';try{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});const result=await r.json();if(!r.ok)throw Error(result.error||'We couldn’t save that. Please try again.');status.textContent=result.message;form.reset();return true}catch(e){status.textContent=e.message==='Failed to fetch'?'The local service isn’t available. Please try again.':e.message;return false}finally{button.disabled=false}}
$('#hike-updates').onsubmit=e=>{e.preventDefault();send(e.currentTarget,'/api/community/subscriptions',{email:e.currentTarget.email.value,newsletter:false,hikes:true})};
$('#community-newsletter').onsubmit=e=>{e.preventDefault();send(e.currentTarget,'/api/community/subscriptions',{email:e.currentTarget.email.value,newsletter:true,hikes:e.currentTarget.hikes.checked})};
$('#upcoming-hikes').onclick=e=>{const button=e.target.closest('[data-rsvp]');if(!button)return;const event=club.events.find(x=>x.id===button.dataset.rsvp);if(!event)return;show(`<p class="label">NORTH COAST HIKING CLUB</p><h2>Join the next hike.</h2><h3>${esc(event.title)}</h3><p>${esc(dateLabel(event))}</p>${details(event)}<form id="hike-rsvp"><label for="rsvp-name">Your name</label><input id="rsvp-name" name="name" autocomplete="name" maxlength="120" required><label for="rsvp-email">Email address</label><input id="rsvp-email" name="email" type="email" autocomplete="email" required><label for="rsvp-party">People in your group, including you</label><select id="rsvp-party" name="partySize">${Array.from({length:Math.min(6,event.remaining??6)},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join('')}</select><p class="setup-note">This RSVP is saved in the local sandbox. Email confirmations are not connected.</p><button class="button" type="submit">Save my RSVP ↗</button><p class="form-status" role="status"></p></form>`);$('#hike-rsvp').onsubmit=async e=>{e.preventDefault();const f=e.currentTarget;const saved=await send(f,'/api/community/rsvps',{eventId:event.id,name:f.elements.name.value,email:f.elements.email.value,partySize:Number(f.elements.partySize.value)});if(saved)load()}};
load();
})();

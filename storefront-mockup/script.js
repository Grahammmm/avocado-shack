const esc=t=>String(t??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=s=>document.querySelector(s);
const dialog=$('#dialog');
function show(html){
 $('#dialog-content').innerHTML=html;
 const heading=$('#dialog-content h2');
 if(heading){heading.id='dialog-title';dialog.setAttribute('aria-labelledby','dialog-title');dialog.removeAttribute('aria-label')}
 else{dialog.removeAttribute('aria-labelledby');dialog.setAttribute('aria-label','Avocado Shack')}
 dialog.scrollTop=0;if(!dialog.open)dialog.showModal();
}
$('.close').onclick=()=>dialog.close();
// A click whose target is the dialog itself is either its backdrop or its own padding/border; only a pointer outside the dialog's box (measured now) is the backdrop.
dialog.addEventListener('click',e=>{if(e.target!==dialog)return;const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close()});
$('[data-policy]').onclick=()=>show('<h2>Your privacy matters.</h2><p>This site doesn’t use cookies, analytics or advertising trackers. Catalog search and filters work inside this page. Nothing is sold on this website, so no payment information is collected.</p><p>Online signup for Michael’s newsletter and hiking updates isn’t open yet. Until it is, those forms don’t send or save what you type, and the sample hike RSVP never leaves your browser. To hear about news or the next hike, ask us at the Shack.</p><p>Links to producers, trail information and maps go to other websites, which have their own privacy policies.</p>');

// Keep old shared hiking anchors useful after moving the club onto its own page.
if(document.querySelector('#market')&&['#hikes','#upcoming-hikes','#past-heading','#hike-updates','#route-ideas-heading'].includes(location.hash)){
 location.replace('/hike'+(location.hash==='#route-ideas-heading'?'#hikes':location.hash));
}

// AV1104-03: the sentence under the Visit hours ("Open now - closes 6pm") is worked out here, in Pacific time, from the weekly times the page carries as data; any doubt and it stays empty and hidden.
(()=>{
 const el=document.querySelector('.visit-open-status');if(!el)return;
 const DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],DATE=/^\d{4}-\d{2}-\d{2}$/;
 const sane=d=>d===null||(!!d&&typeof d==='object'&&!Array.isArray(d)&&((Object.keys(d).join()==='closed'&&d.closed===true)||(Object.keys(d).join()==='opens,closes'&&Number.isInteger(d.opens)&&Number.isInteger(d.closes)&&d.opens>=0&&d.opens<d.closes&&d.closes<=1439)));
 let week=null;try{const w=JSON.parse(el.dataset.weeklyHours);if(Array.isArray(w)&&w.length===7&&w.every(sane))week=w}catch(e){}
 if(!week){el.hidden=true;el.textContent='';return}
 let fmt=null;try{fmt=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',calendar:'gregory',numberingSystem:'latn',hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',weekday:'long',hour:'2-digit',minute:'2-digit'})}catch(e){}
 const pacific=()=>{const now=new Date();if(!fmt||isNaN(now))return null;const p={};for(const x of fmt.formatToParts(now))p[x.type]=x.value;const dow=DAYS.indexOf(p.weekday),h=+p.hour,m=+p.minute,day=p.year+'-'+p.month+'-'+p.day;return dow>=0&&DATE.test(day)&&h>=0&&h<=24&&m>=0&&m<60?{day,dow,min:(h%24)*60+m}:null};
 // A notice showing today (any wording) silences the status; so does one whose dates cannot be read.
 const noticed=day=>[...document.querySelectorAll('.home-notice')].some(n=>{const f=n.dataset.from,u=n.dataset.until;return !DATE.test(u||'')||(f!==undefined&&!DATE.test(f))||((f===undefined||day>=f)&&day<=u)});
 const clock=t=>{const h=Math.floor(t/60),m=t%60;return (h%12||12)+(m?':'+String(m).padStart(2,'0'):'')+(h<12?'am':'pm')};
 const say=()=>{
  const p=pacific();if(!p||noticed(p.day))return '';
  const t=week[p.dow];if(!t)return '';
  if(!t.closed){if(p.min>=t.opens&&p.min<t.closes)return 'Open now - closes '+clock(t.closes);if(p.min<t.opens)return 'Closed now - opens '+DAYS[p.dow]+' '+clock(t.opens)}
  for(let i=1;i<=7;i++){const d=(p.dow+i)%7,n=week[d];if(!n)return '';if(!n.closed)return 'Closed now - opens '+DAYS[d]+' '+clock(n.opens)}
  return '';
 };
 const update=()=>{let text='';try{text=say()}catch(e){}if(el.textContent!==text)el.textContent=text;if(el.hidden!==!text)el.hidden=!text};
 update();setInterval(update,1000);document.addEventListener('visibilitychange',update);window.addEventListener('pageshow',update);
})();

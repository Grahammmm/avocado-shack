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
dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
$('[data-policy]').onclick=()=>show('<h2>Your privacy matters.</h2><p>This site doesn’t use cookies, analytics or advertising trackers. Catalog search and filters work inside this page. Nothing is sold on this website, so no payment information is collected.</p><p>Online signup for Michael’s newsletter and hiking updates isn’t open yet. Until it is, those forms don’t send or save what you type, and the sample hike RSVP never leaves your browser. To hear about news or the next hike, ask us at the Shack.</p><p>Links to producers, trail information and maps go to other websites, which have their own privacy policies.</p>');

// Keep old shared hiking anchors useful after moving the club onto its own page.
if(document.querySelector('#market')&&['#hikes','#upcoming-hikes','#past-heading','#hike-updates','#route-ideas-heading'].includes(location.hash)){
 location.replace('/hike'+(location.hash==='#route-ideas-heading'?'#hikes':location.hash));
}

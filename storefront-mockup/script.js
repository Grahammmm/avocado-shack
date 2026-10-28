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
$('[data-policy]').onclick=()=>show('<h2>Your privacy matters.</h2><p>Catalog search and filters stay in this page. Newsletter and hiking forms save the details you choose to submit to the local sandbox database: email, subscription choices, and, for a hike RSVP, your name and party size. The sample hike RSVP stays in your browser only while you fill it in and does not send or save any details. No payment information is collected.</p><p>Email delivery is not connected. Nothing is sent to an email service or to Michael’s proposed mailbox. Before a public launch, we’ll connect delivery, an unsubscribe option, and the final privacy information. External producer and map links have their own privacy policies.</p>');

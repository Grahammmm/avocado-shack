/* Cached public map imagery, OSM trail geometry and a USGS terrain profile.
   No location permission, third-party map SDK, tracking or visitor persistence. */
(()=>{
const ns='http://www.w3.org/2000/svg';
const ft=m=>m*3.28084,mi=m=>m/1609.344;
const roundedGain=m=>Math.round(ft(m)/50)*50;
const icon=(name)=>({plus:'<path d="M12 5v14M5 12h14"/>',minus:'<path d="M5 12h14"/>',fit:'<path d="M8 4H4v4m12-4h4v4M4 16v4h4m12-4v4h-4"/><circle cx="12" cy="12" r="3"/>',expand:'<path d="M8 4H4v4m12-4h4v4M4 16v4h4m12-4v4h-4M4 4l5 5m11-5-5 5M4 20l5-5m11 5-5-5"/>'}[name]);
const control=(action,label,symbol)=>`<button type="button" data-map-action="${action}" aria-label="${label}" title="${label}"><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7">${icon(symbol)}</svg></button>`;
function node(tag,attrs={}){const n=document.createElementNS(ns,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);return n;}

const UNAVAILABLE='<p class="trail-map-unavailable">The interactive map couldn’t load. <a href="https://www.pge.com/en/about/in-your-community/recreational-areas.html" target="_blank" rel="noopener">View the official trail guide ↗</a></p>';
async function mount(host){
 if(!host||host.dataset.mounted)return;
 host.dataset.mounted='true';
 if(host.dataset.ready==='error')host.innerHTML='<p class="trail-map-unavailable">Loading the trail map…</p>';
 delete host.dataset.ready;
 try{
  let d;
  try{const response=await fetch('/assets/trails/point-buchon.json');if(!response.ok)throw Error('Trail data unavailable');d=await response.json();}
  catch(error){
   delete host.dataset.mounted;if(!host.isConnected)return;
   host.innerHTML=UNAVAILABLE+'<p><button type="button" data-trail-retry>Try loading the map again</button></p>';host.dataset.ready='error';
   host.querySelector('[data-trail-retry]').addEventListener('click',e=>{if(host.isConnected&&host.contains(e.currentTarget))mount(host);});return;
  }
  if(!host.isConnected){delete host.dataset.mounted;return;}
  const miles=mi(d.distanceMeters).toFixed(1),gain=roundedGain(d.gainMeters),loss=roundedGain(d.lossMeters);
  const wrapper=document.createElement('section');wrapper.className='trail-explorer';wrapper.setAttribute('aria-labelledby','trail-explorer-heading');wrapper.setAttribute('aria-live','off');
  wrapper.innerHTML=`<div class="trail-explorer-heading"><div><p class="trail-eyebrow">A CLOSER LOOK</p><h3 id="trail-explorer-heading">Follow the coastline.</h3><p>${miles} miles out &amp; back · from Coon Creek parking</p></div><div class="trail-layer-switch" role="group" aria-label="Map view"><button type="button" data-map-layer="aerial" aria-pressed="true">Aerial</button><button type="button" data-map-layer="topo" aria-pressed="false">Topo</button></div></div>
  <div class="trail-map-stage" tabindex="0" role="region" aria-label="Interactive Point Buchon route map" aria-describedby="trail-map-help" data-layer="aerial">
   <svg class="trail-map-canvas" aria-hidden="true" preserveAspectRatio="xMidYMid meet"><image class="trail-basemap" href="/assets/trails/point-buchon-aerial.webp" x="0" y="0" width="1000" height="562.5"/><path class="trail-route-halo"/><path class="trail-route-line"/><g class="trail-route-markers"></g><circle class="trail-position-halo"/><circle class="trail-position-dot"/></svg>
   <div class="trail-compass" aria-hidden="true"><span>N</span><svg viewBox="0 0 22 30"><path d="M11 2 20 27 11 21 2 27Z" fill="currentColor"/><path d="M11 2v19l9 6Z" fill="#f8f5ec"/></svg></div>
   <div class="trail-map-tools" role="group" aria-label="Map controls">${control('in','Zoom in','plus')}${control('out','Zoom out','minus')}${control('fit','Show full route','fit')}${control('expand','Enlarge map','expand')}</div>
   <div class="trail-map-scale" aria-hidden="true"><span>500 m</span><i></i></div><div class="trail-map-route-key"><i></i> Out &amp; back route</div>
  </div>
  <div class="trail-map-caption"><p id="trail-map-help">Zoom in, then drag to explore. Keyboard: + / − to zoom; arrow keys to move.</p><p>Imagery: <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map" target="_blank" rel="noopener">USGS</a> · Route: <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap</a></p></div>
  <div class="trail-elevation"><div class="trail-elevation-heading"><h4>The ups &amp; downs.</h4><p><span>↗ ~${gain} ft gain</span><span>↘ ~${loss} ft loss</span></p></div><div class="trail-profile-chart"><svg class="trail-profile-svg" role="img" aria-label="Estimated elevation profile for the ${miles}-mile round trip. The return retraces the outbound route."></svg></div><div class="trail-profile-readout"><label for="trail-distance">Explore the elevation</label><output for="trail-distance" id="trail-elevation-readout"></output></div><input id="trail-distance" class="trail-distance" type="range" min="0" max="${d.profile.length-1}" step="1" value="0" aria-label="Distance along the hike" aria-describedby="trail-elevation-readout"><p class="trail-profile-hint">Slide along the profile to see your position on the map. Heights are feet above sea level.</p></div>
  <details class="trail-map-notes"><summary>About this route &amp; map</summary><p>The line includes the walk from Coon Creek parking to the check-in station, then the main trail to the turnaround and back. The optional northern loop is not included. Our mapped route is about ${miles} miles; PG&amp;E describes the trail as 6.6 miles round trip.</p><p>Elevation is estimated from <a href="https://www.usgs.gov/3d-elevation-program" target="_blank" rel="noopener">USGS 3DEP terrain data</a>, sampled every 50 metres and lightly smoothed. It is not a GPS recording. Imagery is an aerial survey, not a live view. This is a route overview; check current access and follow trail signs.</p><p><a href="https://www.pge.com/assets/pge/images/about/point-buchon-trail-map.jpg" target="_blank" rel="noopener">Official trail map ↗</a><a href="https://www.pge.com/en/about/in-your-community/recreational-areas.html" target="_blank" rel="noopener">Access &amp; trail conditions ↗</a></p></details>`;
  host.replaceChildren(wrapper);
  const q=s=>wrapper.querySelector(s),stage=q('.trail-map-stage'),svg=q('.trail-map-canvas'),photo=q('.trail-basemap');
  // AV1422-08 edge 5: a failed aerial image (the first layer) is a failed map load, same fallback and retry as a failed route file.
  let failed=false;
  photo.addEventListener('error',()=>{
   const enlarged=!!(dialog&&dialog.contains(wrapper));
   if(failed||!/aerial/.test(photo.getAttribute('href'))||!host.isConnected||!(enlarged||host.contains(wrapper)))return;
   failed=true;
   if(enlarged){const d=dialog;dialog=null;document.body.style.overflow=previousOverflow;d.close();d.remove();}
   delete host.dataset.mounted;host.innerHTML=UNAVAILABLE+'<p><button type="button" data-trail-retry>Try loading the map again</button></p>';host.dataset.ready='error';host.querySelector('[data-trail-retry]').addEventListener('click',e=>{if(host.isConnected&&host.contains(e.currentTarget))mount(host);});
  });
  const profile=d.profile,slider=q('.trail-distance'),output=q('#trail-elevation-readout');
  const [minX,minY,maxX,maxY]=d.bounds3857;
  function project(lon,lat){const x=6378137*lon*Math.PI/180,y=6378137*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360));return [(x-minX)/(maxX-minX)*1000,(maxY-y)/(maxY-minY)*562.5];}
  const points=d.coordinates.map(p=>project(...p));
  const routePath=points.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(3)},${p[1].toFixed(3)}`).join(' ');
  q('.trail-route-halo').setAttribute('d',routePath);q('.trail-route-line').setAttribute('d',routePath);
  const pointBounds={left:Math.min(...points.map(p=>p[0])),right:Math.max(...points.map(p=>p[0])),top:Math.min(...points.map(p=>p[1])),bottom:Math.max(...points.map(p=>p[1]))};
  const markers=[{point:points[0],text:'Coon Creek parking',letter:'P'},{point:points.at(-1),text:'Turnaround',letter:'↶'}].map(m=>{
   const g=node('g');g.append(node('circle',{class:'trail-endpoint-circle'}),node('text',{class:'trail-endpoint-letter','text-anchor':'middle','dominant-baseline':'central'}),node('text',{class:'trail-endpoint-label','dominant-baseline':'central'}));g.children[1].textContent=m.letter;g.children[2].textContent=m.text;q('.trail-route-markers').append(g);return {...m,element:g};
  });
  let size={width:0,height:0},view,base,zoom=1,selected=0,drag=null,dialog=null,previousOverflow='';
  function setView(){
   const halfW=view.width/2,halfH=view.height/2;
   // Keep at least the centre of the bounded imagery in reach at every zoom level.
   view.cx=Math.max(Math.min(halfW,500),Math.min(1000-Math.min(halfW,500),view.cx));
   view.cy=Math.max(Math.min(halfH,281.25),Math.min(562.5-Math.min(halfH,281.25),view.cy));
   svg.setAttribute('viewBox',`${view.cx-halfW} ${view.cy-halfH} ${view.width} ${view.height}`);
   const scale=view.width/size.width;
   markers.forEach(({point,element})=>{
    element.setAttribute('transform',`translate(${point[0]} ${point[1]}) scale(${scale})`);
    element.children[0].setAttribute('r','10');
    const label=element.children[2],onRight=point[0]>view.cx,phoneStart=size.width<500&&point===points[0];
    label.textContent=phoneStart?'Coon Creek parking':element===markers[0].element?'Coon Creek parking':'Turnaround';
    label.setAttribute('x',phoneStart?'0':onRight?'-17':'17');label.setAttribute('y',phoneStart?'23':'0');label.setAttribute('text-anchor',phoneStart?'middle':onRight?'end':'start');
   });
   q('.trail-position-halo').setAttribute('r',9*scale);q('.trail-position-dot').setAttribute('r',4.5*scale);
   const metresPerScreenPixel=(maxX-minX)/1000*scale*Math.cos(35.24*Math.PI/180);
   const scaleMetres=metresPerScreenPixel*85>500?500:metresPerScreenPixel*85>200?200:100;
   q('.trail-map-scale span').textContent=`${scaleMetres} m`;q('.trail-map-scale i').style.width=`${scaleMetres/metresPerScreenPixel}px`;
   q('[data-map-action="in"]').disabled=zoom>=4;q('[data-map-action="out"]').disabled=zoom<=1;
   stage.classList.toggle('is-zoomed',zoom>1);stage.dataset.zoom=zoom.toFixed(2);
  }
  function fit(){
   size={width:stage.clientWidth,height:stage.clientHeight};if(!size.width)return;
   const ratio=size.width/size.height;
   const height=Math.max(pointBounds.bottom-pointBounds.top+100,(pointBounds.right-pointBounds.left+100)/ratio);
   base={width:height*ratio,height,cx:(pointBounds.left+pointBounds.right)/2,cy:(pointBounds.top+pointBounds.bottom)/2};
   view={...base};zoom=1;setView();
  }
  function changeZoom(factor){if(!view)return;zoom=Math.min(4,Math.max(1,zoom*factor));view.width=base.width/zoom;view.height=base.height/zoom;setView();}
  function drawProfile(){
   const chart=q('.trail-profile-svg'),w=q('.trail-profile-chart').clientWidth,h=178;if(!w)return;
   const left=36,right=12,top=23,bottom=28,plotW=w-left-right,plotH=h-top-bottom;
   const ceiling=Math.ceil(ft(d.maxElevationMeters)/100)*100;
   chart.setAttribute('viewBox',`0 0 ${w} ${h}`);chart.replaceChildren();
   const xy=p=>[left+p.distanceMeters/d.distanceMeters*plotW,top+(1-ft(p.elevationMeters)/ceiling)*plotH];
   for(let elev=0;elev<=ceiling;elev+=100){const y=top+(1-elev/ceiling)*plotH;chart.append(node('line',{x1:left,y1:y,x2:w-right,y2:y,class:'profile-grid'}));const t=node('text',{x:left-7,y:y+4,'text-anchor':'end',class:'profile-axis'});t.textContent=elev;chart.append(t);}
   const ticks=w<480?[0,2,4,6]:[0,1,2,3,4,5,6];for(const m of ticks){const x=left+m/mi(d.distanceMeters)*plotW;const t=node('text',{x,y:h-7,'text-anchor':m===0?'start':'middle',class:'profile-axis'});t.textContent=`${m} mi`;chart.append(t);}
   const line=profile.map((p,i)=>`${i?'L':'M'}${xy(p).map(v=>v.toFixed(2)).join(',')}`).join(' ');
   chart.append(node('path',{d:`${line} L${w-right},${h-bottom} L${left},${h-bottom} Z`,class:'profile-area'}),node('path',{d:line,class:'profile-line'}));
   chart.append(node('line',{x1:left+plotW/2,y1:top-2,x2:left+plotW/2,y2:h-bottom,class:'profile-turnaround'}));
   const turn=node('text',{x:left+plotW/2,y:13,'text-anchor':'middle',class:'profile-axis'});turn.textContent='Turn around';chart.append(turn);
   chart.append(node('line',{class:'profile-cursor',y1:top,y2:h-bottom}),node('circle',{class:'profile-point',r:5}));
   chart._xy=xy;chart._plot={left,plotW};updatePosition(selected);
  }
  function updatePosition(index){
   selected=Math.max(0,Math.min(profile.length-1,Math.round(index)));const p=profile[selected];slider.value=String(selected);
   const direction=p.distanceMeters>d.oneWayMeters?'return':'outbound',elevation=Math.round(ft(p.elevationMeters));
   output.textContent=`${mi(p.distanceMeters).toFixed(1)} mi · ${elevation} ft`;
   slider.setAttribute('aria-valuetext',`${mi(p.distanceMeters).toFixed(1)} miles ${direction}, ${elevation} feet above sea level`);
   const pos=project(p.lon,p.lat);for(const mark of [q('.trail-position-halo'),q('.trail-position-dot')]){mark.setAttribute('cx',pos[0]);mark.setAttribute('cy',pos[1]);}
   const chart=q('.trail-profile-svg');if(chart._xy){const [x,y]=chart._xy(p);const cursor=q('.profile-cursor');cursor.setAttribute('x1',x);cursor.setAttribute('x2',x);q('.profile-point').setAttribute('cx',x);q('.profile-point').setAttribute('cy',y);}
  }
  function selectFromPointer(e){const chart=q('.trail-profile-svg'),box=chart.getBoundingClientRect();if(!chart._plot)return;const distance=Math.max(0,Math.min(1,(e.clientX-box.left-chart._plot.left)/chart._plot.plotW))*d.distanceMeters;let i=0;while(i<profile.length-1&&profile[i].distanceMeters<distance)i++;if(i&&distance-profile[i-1].distanceMeters<profile[i].distanceMeters-distance)i--;updatePosition(i);}
  slider.addEventListener('input',()=>updatePosition(Number(slider.value)));
  q('.trail-profile-svg').addEventListener('pointermove',e=>{if(e.pointerType==='mouse')selectFromPointer(e);});
  q('.trail-profile-svg').addEventListener('pointerdown',selectFromPointer);
  wrapper.addEventListener('click',e=>{
   const layer=e.target.closest('[data-map-layer]');if(layer){stage.dataset.layer=layer.dataset.mapLayer;photo.setAttribute('href',`/assets/trails/point-buchon-${layer.dataset.mapLayer}.webp`);wrapper.querySelectorAll('[data-map-layer]').forEach(b=>b.setAttribute('aria-pressed',String(b===layer)));return;}
   const action=e.target.closest('[data-map-action]')?.dataset.mapAction;if(!action)return;
   if(action==='in')changeZoom(1.6);if(action==='out')changeZoom(1/1.6);if(action==='fit')fit();
   if(action==='expand'){
    if(dialog){dialog.close();return;}
    dialog=document.createElement('dialog');dialog.className='trail-map-dialog';dialog.setAttribute('aria-label','Point Buchon map and elevation');
    const close=document.createElement('button');close.type='button';close.className='trail-map-close';close.textContent='Close map ×';close.addEventListener('click',()=>dialog.close());
    dialog.append(close,wrapper);document.body.append(dialog);previousOverflow=document.body.style.overflow;document.body.style.overflow='hidden';
    q('[data-map-action="expand"]').setAttribute('aria-label','Return to page');q('[data-map-action="expand"]').title='Return to page';
    dialog.addEventListener('close',()=>{if(failed)return;host.append(wrapper);document.body.style.overflow=previousOverflow;dialog.remove();dialog=null;q('[data-map-action="expand"]').setAttribute('aria-label','Enlarge map');q('[data-map-action="expand"]').title='Enlarge map';q('[data-map-action="expand"]').focus({preventScroll:true});});
    dialog.showModal();close.focus();
   }
  });
  stage.addEventListener('keydown',e=>{if(e.target!==stage)return;const k=e.key;if(['+','=','-','_','ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home'].includes(k)){e.preventDefault();if(k==='+'||k==='=')changeZoom(1.6);else if(k==='-'||k==='_')changeZoom(1/1.6);else if(k==='Home')fit();else {view.cx+=(k==='ArrowRight'?1:k==='ArrowLeft'?-1:0)*view.width*.12;view.cy+=(k==='ArrowDown'?1:k==='ArrowUp'?-1:0)*view.height*.12;setView();}}});
  stage.addEventListener('pointerdown',e=>{if(e.target.closest('button')||e.button!==0||(e.pointerType==='touch'&&zoom===1))return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,cx:view.cx,cy:view.cy};stage.setPointerCapture(e.pointerId);stage.classList.add('is-dragging');});
  stage.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;view.cx=drag.cx-(e.clientX-drag.x)*view.width/size.width;view.cy=drag.cy-(e.clientY-drag.y)*view.height/size.height;setView();});
  const endDrag=()=>{drag=null;stage.classList.remove('is-dragging');};stage.addEventListener('pointerup',endDrag);stage.addEventListener('pointercancel',endDrag);stage.addEventListener('lostpointercapture',endDrag);
  new ResizeObserver(()=>{if(stage.clientWidth!==size.width||stage.clientHeight!==size.height){fit();drawProfile();}}).observe(stage);
  fit();drawProfile();updatePosition(0);
  const stats=host.closest('.trail-invitation')?.querySelectorAll('.trail-stats dd');if(stats?.length===4){stats[0].textContent=`${miles} miles`;stats[2].textContent=`~${gain} ft`;stats[2].previousElementSibling.textContent='Est. elevation gain';}
  host.dataset.ready='true';
 }catch(error){host.innerHTML=UNAVAILABLE;host.dataset.ready='error';}
}
window.AvoshackTrailExplorer={mount};
})();

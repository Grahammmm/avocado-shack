let activeCategory='all',limit=12,visibleCount=0,linkedItem='',activeFrom='';
const makerCounts=new Map();catalog.forEach(p=>makerCounts.set(p.producerKey,(makerCounts.get(p.producerKey)||0)+1));
const validFrom=key=>Object.hasOwn(producers,key)&&makerCounts.get(key)>=2;
$('#catalog-grid').insertAdjacentHTML('beforebegin','<p class="catalog-from" hidden></p>');
function maker(p){return producers[p.producerKey]}
function organic(p){return /\borganic\b/i.test(p.name)||['Ocean Ranch','Straus','Green Gold','Massa Organics'].includes(p.producerKey)}
function photo(p){return `<img loading="lazy" width="800" height="800" src="${esc(p.image)}" alt="${esc(p.imageAlt||p.name)}">`}
function origin(p){return maker(p)?`Based in ${maker(p).place}`:'Ask us about the source in store.'}
function badges(p){return organic(p)?'<div class="food-badges"><span>Organic</span></div>':''}
function brand(p){return p.displayBrand||(p.brand==='Producer not identified'?'From the market':p.brand)}
function card(p){
 const m=maker(p);
 return `<article data-product-id="${esc(p.id)}" data-category="${esc(p.category)}"><div class="food-card-top"><div class="product-image">${photo(p)}</div><div class="food-identity"><p class="product-meta">${esc(brand(p))}</p><h3>${esc(p.name)}</h3><p class="origin-label">${esc(origin(p))}</p>${badges(p)}</div></div><p class="food-description">${esc(p.description)}</p>${m?`<details class="maker-story"><summary>Meet the maker<span class="sr-only">: ${esc(m.name)}</span></summary><div class="maker-story-content"><p>${esc(m.story)}</p><a href="${esc(m.url)}" target="_blank" rel="noopener">Visit ${esc(m.name)} <span aria-hidden="true">↗</span></a>${makerCounts.get(p.producerKey)>=2?`<button type="button" class="text-link" data-from="${esc(p.producerKey)}">See all ${makerCounts.get(p.producerKey)} from ${esc(m.name)}</button>`:''}</div></details>`:''}<a class="text-link card-link" href="?item=${esc(encodeURIComponent(p.id))}#market">Link to this</a></article>`;
}
[...new Set(catalog.map(p=>p.brand))].sort().forEach(b=>{const o=document.createElement('option');o.value=b;o.textContent=b==='Producer not identified'?'Other market selections':b;$('#brand-filter').append(o)});
// AV1102-03: the words match sitegen.AVAILABILITY_WORDS (pinned by a test); "Last confirmed ..." is never current.
const CURRENT=new Set(['Available today','Limited','Sold out']),AVAIL=new Set(['Available today','Limited']);let availBox=null;
if(catalog.some(p=>CURRENT.has(p.availability))){$('#brand-filter').closest('label').insertAdjacentHTML('afterend','<label class="avail-filter"><input type="checkbox" id="avail-filter"> Available today</label>');availBox=$('#avail-filter')}
const fold=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[\u2018\u2019\u02bc]/g,"'").toLowerCase();
const SHELF=Object.fromEntries([...document.querySelectorAll('[data-filter]')].filter(b=>b.dataset.filter!=='all').map(b=>[b.dataset.filter,b.textContent.trim()]));
// One search normalization for filtering, the address and restore: trimmed, at most 80 characters (code points).
const searchText=s=>[...String(s||'').trim()].slice(0,80).join('').trim();
function filteredProducts(){const term=fold(searchText($('#product-search').value)),brand=$('#brand-filter').value;return catalog.filter(p=>(!activeFrom||p.producerKey===activeFrom)&&(activeCategory==='all'||p.category===activeCategory)&&(!brand||p.brand===brand)&&(!availBox?.checked||AVAIL.has(p.availability))&&fold(`${p.name} ${p.brand} ${maker(p)?.place||''} ${SHELF[p.category]||''} ${organic(p)?'Organic':''}`).includes(term))}
function renderCatalog(append=false){const chip=$('.catalog-from');chip.hidden=!activeFrom;chip.innerHTML=activeFrom?`From ${esc(producers[activeFrom].name)} <button type="button" data-clear-from>Show everything</button>`:'';const list=filteredProducts(),end=Math.min(limit,list.length);if(!append){$('#catalog-grid').innerHTML='';visibleCount=0}$('#catalog-grid').insertAdjacentHTML('beforeend',list.slice(visibleCount,end).map(card).join(''));visibleCount=end;$('#catalog-count').textContent=`${list.length} selections · ${visibleCount} shown`;$('#catalog-sentinel').textContent=visibleCount<list.length?'More good things as you scroll.':list.length?'That’s this selection. Explore another category, producer, or town.':'Nothing here just yet. Try another category or clear your filters.';$('#more-products').hidden=('IntersectionObserver' in window)||visibleCount>=list.length;$('#clear-filters').hidden=!anyFilter()}
function anyFilter(){return activeCategory!=='all'||!!searchText($('#product-search').value)||!!$('#brand-filter').value||!!activeFrom||!!availBox?.checked}
function syncUrl(){const p=new URLSearchParams(location.search),set=(k,v)=>v?p.set(k,v):p.delete(k),s=()=>p.toString();
 linkedItem='';p.delete('item');  // A filter change also cancels any pending item scroll/focus.
 set('from',activeFrom);set('shelf',activeCategory==='all'?'':activeCategory);set('q',searchText($('#product-search').value));set('maker',$('#brand-filter').value);set('avail',availBox?.checked?'1':'');
 history.replaceState(null,'',location.pathname+(s()?'?'+s():'')+location.hash)}
function resetCatalog(){limit=12;syncUrl();renderCatalog();scheduleScroll()}
$('#clear-filters').onclick=()=>{selectShelf($('[data-filter="all"]'));$('#product-search').value='';$('#brand-filter').value='';activeFrom='';if(availBox)availBox.checked=false;resetCatalog();$('#product-search').focus()};
function loadMore(){if(visibleCount>=filteredProducts().length)return;limit+=12;renderCatalog(true)}
// Typed or pasted text past the limit is cut in the box too, so the box, the results and a shared address agree.
$('#product-search').oninput=()=>{const box=$('#product-search');if([...box.value.trim()].length>80)box.value=searchText(box.value);resetCatalog()};$('#brand-filter').onchange=resetCatalog;if(availBox)availBox.onchange=resetCatalog;$('#more-products').onclick=loadMore;
function selectShelf(b){activeCategory=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b))})}
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{selectShelf(b);resetCatalog()});
document.addEventListener('click',e=>{const b=e.target.closest('[data-from],[data-clear-from]');if(!b)return;const key=b.dataset.from||'';if(key&&!validFrom(key))return;activeFrom=key;selectShelf($('[data-filter="all"]'));$('#product-search').value='';$('#brand-filter').value='';resetCatalog();$('#catalog-grid').scrollIntoView({block:'start'})});
let scrollFrame=0, sectionNavigation=false, sectionTimer;
function checkScroll(){
 scrollFrame=0;
 const edge=$('#catalog-sentinel').getBoundingClientRect();
 // Loading products above a visitor who has moved on would shift their section.
 if(!sectionNavigation&&visibleCount<filteredProducts().length&&edge.bottom>=0&&edge.top<innerHeight+600){loadMore();scrollFrame=requestAnimationFrame(checkScroll)}
}
function scheduleScroll(){if(!scrollFrame)scrollFrame=requestAnimationFrame(checkScroll)}
function resumeCatalog(){clearTimeout(sectionTimer);sectionNavigation=false;scheduleScroll()}
function waitForSectionScroll(){clearTimeout(sectionTimer);sectionTimer=setTimeout(resumeCatalog,250)}
function followSection(hash){
 const target=document.getElementById(hash.slice(1));
 if(target&&target!==$('#market')&&!$('#market').contains(target)){sectionNavigation=true;waitForSectionScroll()}
}
// Pause during anchor scrolling through the catalog, including direct hash links.
followSection(location.hash);
document.addEventListener('click',event=>{const link=event.target.closest('a[href^="#"]');if(link)followSection(link.getAttribute('href'))},true);
window.addEventListener('hashchange',()=>followSection(location.hash));
// Restore shelf, search, brand and maker views; only a known multi-product maker can be active.
// A malformed address must never stop the catalog, so the whole restore is guarded.
try{const u=new URLSearchParams(location.search),shelf=[...document.querySelectorAll('[data-filter]')].find(x=>x.dataset.filter===u.get('shelf')),mk=u.get('maker');
 activeFrom=validFrom(u.get('from'))?u.get('from'):'';
 if(shelf)selectShelf(shelf);$('#product-search').value=searchText(u.get('q'));$('#brand-filter').value=mk&&[...$('#brand-filter').options].some(o=>o.value===mk)?mk:'';
 // AV1322-10: ?item=<catalog id> wins over the filters: show everything, load enough cards to reach it.
 // An unknown, empty or over-80-character id is ignored and the filters above apply as before.
 const item=u.get('item'),i=item&&[...item].length<=80?catalog.findIndex(p=>p.id===item):-1;
 if(i>=0){activeFrom='';selectShelf($('[data-filter="all"]'));$('#product-search').value='';$('#brand-filter').value='';limit=Math.max(12,Math.ceil((i+1)/12)*12);linkedItem=item;if(availBox)availBox.checked=false}
 if(availBox)availBox.checked=u.get('avail')==='1'&&i<0;
 let fix=false;if(u.has('from')&&!activeFrom){u.delete('from');fix=true}if(u.has('avail')&&!availBox?.checked){u.delete('avail');fix=true}
 if(fix){const q=u.toString();history.replaceState(null,'',location.pathname+(q?'?'+q:'')+location.hash)}}catch(e){}
renderCatalog();
// Prefer load, after the browser's #market jump, but do not wait indefinitely for a nonessential asset.
let linkedShown=false;
function showLinked(){const el=[...document.querySelectorAll('#catalog-grid article')].find(a=>a.dataset.productId===linkedItem);
 // A late load may repair the anchor jump only while the visitor has not moved focus elsewhere.
 if(el&&(!linkedShown||document.activeElement===el)){linkedShown=true;el.setAttribute('tabindex','-1');el.scrollIntoView({block:'center'});el.focus({preventScroll:true})}}
if(linkedItem){if(document.readyState==='complete')showLinked();else{
 const fallback=setTimeout(showLinked,1000);
 addEventListener('load',()=>{clearTimeout(fallback);requestAnimationFrame(showLinked)},{once:true});
}}
if('IntersectionObserver' in window){
 const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))scheduleScroll()},{rootMargin:'600px 0px'});
 observer.observe($('#catalog-sentinel'));
 window.addEventListener('scroll',()=>{if(sectionNavigation)waitForSectionScroll();else scheduleScroll()},{passive:true});
 window.addEventListener('resize',scheduleScroll);
}

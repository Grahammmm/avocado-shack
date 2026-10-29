let activeCategory='all',activeSource='all',limit=12,visibleCount=0;
const localPlaces=['Cambria','San Miguel','Paso Robles','San Luis Obispo','Atascadero','Templeton','Big Sur','Arroyo Grande','Cayucos','Carpinteria','Central Coast'];
function maker(p){return producers[p.producerKey]}
function local(p){return !!maker(p)&&localPlaces.some(x=>maker(p).place.includes(x))}
function organic(p){return /\borganic\b/i.test(p.name)||['Ocean Ranch','Straus','Green Gold','Massa Organics'].includes(p.producerKey)}
function photo(p){return `<img loading="lazy" width="800" height="800" src="${esc(p.image)}" alt="${esc(p.name)}">`}
function origin(p){return maker(p)?`Based in ${maker(p).place}`:'Ask us about the source in store.'}
function badges(p){return `<div class="food-badges">${local(p)?'<span>Central Coast maker</span>':''}${organic(p)?'<span>Organic</span>':''}</div>`}
function brand(p){return p.displayBrand||(p.brand==='Producer not identified'?'From the market':p.brand)}
function card(p){
 const m=maker(p);
 return `<article data-product-id="${esc(p.id)}" data-category="${esc(p.category)}"><div class="food-card-top"><div class="product-image">${photo(p)}</div><div class="food-identity"><p class="product-meta">${esc(brand(p))}</p><h3>${esc(p.name)}</h3><p class="origin-label">${esc(origin(p))}</p>${badges(p)}</div></div><p class="food-description">${esc(p.description)}</p>${m?`<section class="maker-story" aria-label="About ${esc(m.name)}"><p>${esc(m.story)}</p><a href="${esc(m.url)}" target="_blank" rel="noopener">${esc(m.name)} <span aria-hidden="true">↗</span></a></section>`:''}</article>`;
}
[...new Set(catalog.map(p=>p.brand))].sort().forEach(b=>{const o=document.createElement('option');o.value=b;o.textContent=b==='Producer not identified'?'Other market selections':b;$('#brand-filter').append(o)});
function filteredProducts(){const term=$('#product-search').value.trim().toLowerCase(),brand=$('#brand-filter').value;return catalog.filter(p=>(activeCategory==='all'||p.category===activeCategory)&&(!brand||p.brand===brand)&&(activeSource==='all'||(activeSource==='local'?local(p):organic(p)))&&(`${p.name} ${p.brand} ${maker(p)?.place||''}`.toLowerCase().includes(term)))}
function renderCatalog(append=false){const list=filteredProducts(),end=Math.min(limit,list.length);if(!append){$('#catalog-grid').innerHTML='';visibleCount=0}$('#catalog-grid').insertAdjacentHTML('beforeend',list.slice(visibleCount,end).map(card).join(''));visibleCount=end;$('#catalog-count').textContent=`${list.length} selections · ${visibleCount} shown`;$('#catalog-sentinel').textContent=visibleCount<list.length?'More good things as you scroll.':list.length?'That’s this selection. Explore another category, producer, or town.':'Nothing here just yet. Try another category or clear your filters.';$('#more-products').hidden=('IntersectionObserver' in window)||visibleCount>=list.length;}
function resetCatalog(){limit=12;renderCatalog();scheduleScroll()}
function loadMore(){if(visibleCount>=filteredProducts().length)return;limit+=12;renderCatalog(true)}
$('#product-search').oninput=resetCatalog;$('#brand-filter').onchange=resetCatalog;$('#more-products').onclick=loadMore;
for(const [attr,set] of [['filter',v=>activeCategory=v],['source',v=>activeSource=v]])document.querySelectorAll(`[data-${attr}]`).forEach(b=>b.onclick=()=>{set(b.dataset[attr]);document.querySelectorAll(`[data-${attr}]`).forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b))});resetCatalog()});
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
renderCatalog();
if('IntersectionObserver' in window){
 const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))scheduleScroll()},{rootMargin:'600px 0px'});
 observer.observe($('#catalog-sentinel'));
 window.addEventListener('scroll',()=>{if(sectionNavigation)waitForSectionScroll();else scheduleScroll()},{passive:true});
 window.addEventListener('resize',scheduleScroll);
}

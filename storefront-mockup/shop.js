const esc=t=>String(t??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let activeCategory='all',activeSource='all',limit=12,visibleCount=0;
const localPlaces=['Cambria','San Miguel','Paso Robles','San Luis Obispo','Atascadero','Templeton','Big Sur','Arroyo Grande','Cayucos','Carpinteria','Central Coast'];
const makerNotes={
 'Etto':'Organic durum wheat, bronze dies, and slow drying in Paso Robles. Pasta with texture that holds the sauce.',
 'Stepladder':'A Cambria ranch and creamery making cheese in a restored barn. A real place, with real people behind the food.',
 'Fair Hills Farm':'A San Miguel organic orchard bringing its apple harvest into juices and gently sweetened teas.',
 'Ocean Ranch':'Woman-owned and handmade in small batches. Organic granola with a little imagination behind every flavor.',
 "Linn's":'A family farming and food-making story in Cambria, carried from one generation to the next.',
 'Straus':'A family dairy business with roots in organic farming. Care for the farm carries through to the creamery.',
 'Cal Poly':'Made through Cal Poly’s hands-on food programs. Every product helps students learn their craft.',
 'Alle-Pia':'Italian family recipes and small-batch cured meats, made on California’s Central Coast.',
 'Joebella / Avocado Shack':'Joseph and Isabel’s devotion to coffee, roasted in small batches in Atascadero.',
 'Corberosa':'Coffee roasted on hot air to bring the character of the bean into the cup.',
 'Sunshine Olive':'A Templeton olive-oil producer. A good bottle belongs where you can taste it: beside bread and vegetables.',
 'Big Sur Honey Company':'Dylan and Jessie’s family apiary on Big Sur’s south coast. A small business with a place behind the jar.',
 'Massa Organics':'Greg Massa and Raquel Krach grow organic rice and almonds near Chico, with attention to healthier soil.',
 'Mighty Cap Mushrooms':'Chris Batlle’s garage project grew into a gourmet mushroom farm in Paso Robles.',
 'AG Berries':'Maria “Trini” Iñiguez’s family farming story in Arroyo Grande, rooted in a commitment to organic growing.',
 'Green Gold':'Certified organic microgreens grown in Arroyo Grande. Small leaves with a fresh place at the table.',
 'Stardust Grove':'A Cambria family farm caring for its orchard through a regenerative approach.',
 'Taco Works':'Born in a San Luis Obispo restaurant. A local food story that grew around a very good tortilla chip.',
 'Maple Valley':'An organic maple cooperative with a Wisconsin bottling operation. Good food has stories farther afield, too.',
 'Sierra Nevada':'Traditional dairy craft from a California cheese company founded by two friends.',
 'Cayucos':'Hot sauce born in a little shack across from the beach. A Central Coast maker with a taste for heat.',
 "Brian's":'Old-world-style bread from Atascadero. Sourdough starter, time, and loaves scored by hand.',
 'Jayleaf':'A family greens business with roots in Hollister. Fresh leaves at the heart of what they do.',
 "Sean's":'A San Luis Obispo food business built from kitchen experiments with grains, fruit, nuts, and seeds.',
 'Love Beets':'A family-founded food company making beets easier to enjoy, with production roots in Rochester.',
 'Ava’s':'California Keitt mangoes identified by the distributor as Coachella Valley fruit.'
};
function maker(p){return producers[p.producerKey]}
function local(p){return !!maker(p)&&localPlaces.some(x=>maker(p).place.includes(x))}
function organic(p){return /\borganic\b/i.test(p.name)||['Ocean Ranch','Straus','Green Gold','Massa Organics'].includes(p.producerKey)}
function photo(p){return `<img loading="lazy" width="800" height="800" src="${esc(p.image)}" alt="${esc(p.name)}">`}
function origin(p){return maker(p)?`Based in ${maker(p).place}`:'Ask us about this grower or maker in the Shack.'}
function badges(p){return `<div class="food-badges">${local(p)?'<span>Central Coast maker</span>':''}${organic(p)?'<span>Organic</span>':''}</div>`}
function firstThought(text){const parts=(text||'').match(/[^.!?]+[.!?]+(?:[”’])?/g);return parts?parts.slice(0,2).join(' ').trim():text}
function brand(p){return p.displayBrand||(p.brand==='Producer not identified'?'From the market':p.brand)}
function card(p){return `<article data-category="${esc(p.category)}"><button class="product-image" data-product="${p.id}" aria-label="Discover ${esc(p.name)}">${photo(p)}</button><div class="product-meta"><span>${esc(brand(p))}</span></div><h3>${esc(p.name)}</h3><p class="origin-label">${esc(origin(p))}</p>${badges(p)}<p class="food-description">${esc(firstThought(p.description))}</p>${maker(p)?`<p class="maker-note">${esc(makerNotes[p.producerKey]||firstThought(maker(p).story))}</p>`:''}<button class="text-link food-detail" data-product="${p.id}">${maker(p)?'Food & maker story':'Discover this food'} ↗</button></article>`}
[...new Set(catalog.map(p=>p.brand))].sort().forEach(b=>{const o=document.createElement('option');o.value=b;o.textContent=b==='Producer not identified'?'Other market selections':b;$('#brand-filter').append(o)});
function filteredProducts(){const term=$('#product-search').value.trim().toLowerCase(),brand=$('#brand-filter').value;return catalog.filter(p=>(activeCategory==='all'||p.category===activeCategory)&&(!brand||p.brand===brand)&&(activeSource==='all'||(activeSource==='local'?local(p):organic(p)))&&(`${p.name} ${p.brand} ${maker(p)?.place||''}`.toLowerCase().includes(term)))}
function renderCatalog(append=false){const list=filteredProducts(),end=Math.min(limit,list.length);if(!append){$('#catalog-grid').innerHTML='';visibleCount=0}$('#catalog-grid').insertAdjacentHTML('beforeend',list.slice(visibleCount,end).map(card).join(''));visibleCount=end;$('#catalog-count').textContent=`${list.length} selections · ${visibleCount} shown`;$('#catalog-sentinel').textContent=visibleCount<list.length?'More good things as you scroll.':list.length?'That’s this selection. Explore another category, producer, or town.':'Nothing here just yet. Try another category or clear your filters.';$('#more-products').hidden=('IntersectionObserver' in window)||visibleCount>=list.length;}
function resetCatalog(){limit=12;renderCatalog();scheduleScroll()}
function loadMore(){if(visibleCount>=filteredProducts().length)return;limit+=12;renderCatalog(true)}
$('#product-search').oninput=resetCatalog;$('#brand-filter').onchange=resetCatalog;$('#more-products').onclick=loadMore;
for(const [attr,set] of [['filter',v=>activeCategory=v],['source',v=>activeSource=v]])document.querySelectorAll(`[data-${attr}]`).forEach(b=>b.onclick=()=>{set(b.dataset[attr]);document.querySelectorAll(`[data-${attr}]`).forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b))});resetCatalog()});
let scrollFrame=0;function checkScroll(){scrollFrame=0;if(visibleCount<filteredProducts().length&&$('#catalog-sentinel').getBoundingClientRect().top<innerHeight+600){loadMore();scrollFrame=requestAnimationFrame(checkScroll)}}function scheduleScroll(){if(!scrollFrame)scrollFrame=requestAnimationFrame(checkScroll)}
renderCatalog();if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))scheduleScroll()},{rootMargin:'600px 0px'});observer.observe($('#catalog-sentinel'));window.addEventListener('scroll',scheduleScroll,{passive:true});window.addEventListener('resize',scheduleScroll)}
function detail(p){const m=maker(p);show(`${photo(p)}<p class="label">${esc(brand(p))}</p><h2>${esc(p.name)}</h2><p class="origin-label">${esc(origin(p))}</p>${badges(p)}<p class="product-story">${esc(p.description||'A good thing to bring to the table.')}</p>${m?`<section class="maker-story"><p class="label">MEET THE MAKER</p><h3>${esc(m.name)}</h3><p class="maker-place">${esc(m.place)}</p><p>${esc(m.story)}</p><a class="text-link" href="${esc(m.url)}" target="_blank" rel="noopener">More from ${esc(m.name)} ↗</a></section>`:''}<p class="detail-visit">Come find your next favorite at the Shack.<br><a href="#visit" class="text-link" data-visit>Visit us in Morro Bay ↗</a></p>`);$('[data-visit]').onclick=()=>dialog.close()}
$('#catalog-grid').onclick=e=>{const b=e.target.closest('[data-product]');if(!b)return;const p=catalog.find(p=>p.id===b.dataset.product);if(p)detail(p)};

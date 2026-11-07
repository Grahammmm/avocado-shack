// Test driver for hass/tests/test_catalog_new_order.py (AV0222-09): runs the real storefront-mockup/shop.js in node:vm
// with a synthetic catalog and a fixed clock. Argument: JSON {catalog, now, nowAfter, q, brand, category, from, avail,
// search, loads}. Prints JSON {ids (filtered order), rendered (card ids in the grid), limit, count}.
const fs=require('fs'),path=require('path'),vm=require('vm');
const site=path.join(__dirname,'..','..','..','storefront-mockup');
const o=JSON.parse(process.argv[2]);
let clock=new Date(o.now);
class FixedDate extends Date{constructor(...a){if(a.length)super(...a);else super(clock.getTime())}}
const stub=new Proxy(function(){},{get:(t,k)=>k==='value'||k==='hash'?'':stub,apply:()=>stub,construct:()=>stub,
  set:()=>true,has:()=>false});
let grid='',count='';
const el=props=>new Proxy({},{get:(t,k)=>k in props?props[k]:stub,set:(t,k,v)=>{props[k]=v;return true}});
const els={
  '#product-search':el({value:''}),'#brand-filter':el({value:''}),'#avail-filter':el({checked:false}),
  '#catalog-grid':el({insertAdjacentHTML:(w,h)=>{grid+=h},set innerHTML(v){grid=''}}),
  '#catalog-count':el({set textContent(v){count=v}}),
};
els['[data-filter="all"]']=el({dataset:{filter:'all'}});
const doc=new Proxy(stub,{get:(t,k)=>k==='querySelector'?s=>els[s]||stub:stub});
const ctx=vm.createContext({catalog:o.catalog,producers:o.producers||{},catalogFreshness:o.freshness||null,document:doc,window:stub,
  location:{search:o.search||'',hash:'',pathname:'/'},history:{replaceState:()=>{}},URLSearchParams,Intl,Date:FixedDate,
  requestAnimationFrame:()=>0,setTimeout:()=>0,clearTimeout:()=>{},addEventListener:()=>{},innerHeight:800});
const helpers=fs.readFileSync(path.join(site,'script.js'),'utf8').split('\n')
  .filter(line=>line.startsWith('const esc=')||line.startsWith('const $='));
if(helpers.length!==2)throw new Error('script.js esc/$ definitions not found');
vm.runInContext(helpers.join('\n'),ctx);
vm.runInContext(fs.readFileSync(path.join(site,'shop.js'),'utf8').replace(/^let activeCategory='all'/,"var activeCategory='all'"),ctx);
const run=s=>vm.runInContext(s,ctx);
els['#product-search'].value=o.q||'';els['#brand-filter'].value=o.brand||'';els['#avail-filter'].checked=!!o.avail;
if(o.category||o.from){run(`activeCategory=${JSON.stringify(o.category||'all')};activeFrom=${JSON.stringify(o.from||'')};renderCatalog()`)}
else if(o.q||o.brand||o.avail)run('renderCatalog()');
if(o.nowAfter)clock=new Date(o.nowAfter);
for(let i=0;i<(o.loads||0);i++)run('loadMore()');
const rendered=[...grid.matchAll(/data-product-id="([^"]*)"/g)].map(m=>m[1]);
process.stdout.write(JSON.stringify({ids:run('filteredProducts().map(p=>p.id)'),rendered,limit:run('limit'),count,
  newBadges:(grid.match(/<span>New<\/span>/g)||[]).length})+'\n');

// Test driver for hass/tests/test_maker_optional_story.py (AV0222-10): runs the real storefront-mockup/shop.js in node:vm with
// synthetic catalog and producers. Argument: JSON {catalog, producers, now, from, search}. Prints JSON {cards: [html of each
// drawn card, in order]}. Nothing is read from the network or the real catalog.
const fs=require('fs'),path=require('path'),vm=require('vm');
const site=path.join(__dirname,'..','..','..','storefront-mockup');
const o=JSON.parse(process.argv[2]);
const clock=new Date(o.now||'2026-11-07T20:00:00Z');
class FixedDate extends Date{constructor(...a){if(a.length)super(...a);else super(clock.getTime())}}
const stub=new Proxy(function(){},{get:(t,k)=>k==='value'||k==='hash'?'':stub,apply:()=>stub,construct:()=>stub,
  set:()=>true,has:()=>false});
let grid='';
const el=props=>new Proxy({},{get:(t,k)=>k in props?props[k]:stub,set:(t,k,v)=>{props[k]=v;return true}});
const els={
  '#product-search':el({value:''}),'#brand-filter':el({value:''}),'#avail-filter':el({checked:false}),
  '#catalog-grid':el({insertAdjacentHTML:(w,h)=>{grid+=h},set innerHTML(v){grid=''}}),
  '#catalog-count':el({set textContent(v){}}),
};
els['[data-filter="all"]']=el({dataset:{filter:'all'}});
const doc=new Proxy(stub,{get:(t,k)=>k==='querySelector'?s=>els[s]||stub:stub});
const ctx=vm.createContext({catalog:o.catalog,producers:o.producers,catalogFreshness:null,document:doc,window:stub,
  location:{search:'',hash:'',pathname:'/'},history:{replaceState:()=>{}},URLSearchParams,Intl,Date:FixedDate,
  requestAnimationFrame:()=>0,setTimeout:()=>0,clearTimeout:()=>{},addEventListener:()=>{},innerHeight:800});
const helpers=fs.readFileSync(path.join(site,'script.js'),'utf8').split('\n')
  .filter(line=>line.startsWith('const esc=')||line.startsWith('const $='));
if(helpers.length!==2)throw new Error('script.js esc/$ definitions not found');
vm.runInContext(helpers.join('\n'),ctx);
vm.runInContext(fs.readFileSync(path.join(site,'shop.js'),'utf8').replace(/^let activeCategory='all'/,"var activeCategory='all'"),ctx);
if(o.from)vm.runInContext(`activeFrom=${JSON.stringify(o.from)};renderCatalog()`,ctx);
process.stdout.write(JSON.stringify({cards:grid.split('<article').slice(1).map(a=>'<article'+a)})+'\n');

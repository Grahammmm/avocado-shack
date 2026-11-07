// Test driver for hass/tests/test_product_new.py (AV1622-06): loads storefront-mockup/shop.js in node:vm with stub page
// globals (empty catalog) and, for each case {"product": {...}, "now": ISO instant}, prints the real badges(p) markup
// as a JSON array of strings. The case list is JSON on stdin; the clock the page sees is exactly the case's "now".
// esc() and $() are the real one-line definitions from script.js, as in shop_organic_driver.cjs.
const fs=require('fs'),path=require('path'),vm=require('vm');
const site=path.join(__dirname,'..','..','..','storefront-mockup');
const stub=new Proxy(function(){},{get:(t,k)=>k==='value'||k==='hash'?'':stub,apply:()=>stub,construct:()=>stub,
  set:()=>true,has:()=>false});
const ctx=vm.createContext({catalog:[],producers:{},document:stub,window:stub,location:stub,
  requestAnimationFrame:()=>0,setTimeout:()=>0,clearTimeout:()=>{},innerHeight:800});
const helpers=fs.readFileSync(path.join(site,'script.js'),'utf8').split('\n')
  .filter(line=>line.startsWith('const esc=')||line.startsWith('const $='));
if(helpers.length!==2)throw new Error('script.js esc/$ definitions not found');
vm.runInContext(helpers.join('\n'),ctx);
vm.runInContext(fs.readFileSync(path.join(site,'shop.js'),'utf8'),ctx);
const cases=JSON.parse(fs.readFileSync(0,'utf8'));
ctx.cases=cases;
ctx.RealDate=Date;
const out=vm.runInContext(`cases.map(c=>{const D=RealDate,fake=new D(c.now);
  Date=class extends D{constructor(...a){a.length?super(...a):super(+fake)}static now(){return +fake}};
  try{return badges(c.product)}finally{Date=D}})`,ctx);
process.stdout.write(JSON.stringify(Array.from(out))+'\n');

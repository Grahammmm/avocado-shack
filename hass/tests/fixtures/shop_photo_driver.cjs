// Test driver for hass/tests/test_product_alt.py: loads storefront-mockup/shop.js in node:vm with stub page
// globals (empty catalog) and prints photo(p) for the product JSON given as the first argument.
// esc() and $() are the real one-line definitions from script.js, so escaping is the storefront's own.
const fs=require('fs'),path=require('path'),vm=require('vm');
const site=path.join(__dirname,'..','..','..','storefront-mockup');
// Any page object: every property is itself (strings for .value/.hash), calls return it, sets are ignored.
const stub=new Proxy(function(){},{get:(t,k)=>k==='value'||k==='hash'?'':stub,apply:()=>stub,construct:()=>stub,
  set:()=>true,has:()=>false});
const ctx=vm.createContext({catalog:[],producers:{},document:stub,window:stub,location:stub,
  requestAnimationFrame:()=>0,setTimeout:()=>0,clearTimeout:()=>{},innerHeight:800});
const helpers=fs.readFileSync(path.join(site,'script.js'),'utf8').split('\n')
  .filter(line=>line.startsWith('const esc=')||line.startsWith('const $='));
if(helpers.length!==2)throw new Error('script.js esc/$ definitions not found');
vm.runInContext(helpers.join('\n'),ctx);
vm.runInContext(fs.readFileSync(path.join(site,'shop.js'),'utf8'),ctx);
ctx.product=JSON.parse(process.argv[2]);
process.stdout.write(vm.runInContext('photo(product)',ctx)+'\n');

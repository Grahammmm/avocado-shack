// Test driver for hass/tests/test_organic_sync.py: loads storefront-mockup/shop.js in node:vm with stub page
// globals (empty catalog), runs the real organic(p) on a JSON array of products (first argument) and prints
// {"rule": {"source", "flags", "makers"}, "results": [bool, ...]}. The optional second argument is a test-only
// path to an alternative shop.js (mutation controls); the default is the checked-out production file.
// esc() and $() are the real one-line definitions from script.js, as in shop_photo_driver.cjs.
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
vm.runInContext(fs.readFileSync(process.argv[3]||path.join(site,'shop.js'),'utf8'),ctx);
const src=vm.runInContext('typeof organic==="function"?organic.toString():""',ctx);
// Fail closed: exactly one regex literal tested against p.name, or-ed with one literal string array of makers
// checked with .includes(p.producerKey). Anything else means the rule changed shape.
const shape=/^function organic\(p\)\{return (\/(?:[^\/\\\n]|\\.)+\/[a-z]*)\.test\(p\.name\)\|\|(\[(?:\s*'[^']*'\s*,?)*\s*\])\.includes\(p\.producerKey\)\}$/.exec(src);
if(!shape)throw new Error('Organic rule shape changed; update parity harness. organic() is: '+src);
const re=vm.runInContext(shape[1],ctx);
const makers=vm.runInContext(shape[2],ctx);
const rule={source:re.source,flags:re.flags,makers:Array.from(makers)};
ctx.products=JSON.parse(process.argv[2]);
const results=vm.runInContext('products.map(p=>organic(p))',ctx);
process.stdout.write(JSON.stringify({rule,results:Array.from(results)})+'\n');

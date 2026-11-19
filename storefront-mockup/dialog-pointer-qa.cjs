// RF0511-12: real mouse gestures against the shared dialog (script.js + style.css) in a tiny synthetic page.
// A press that starts inside the dialog and is released on the backdrop must not close it; a press and release
// outside still does. Nothing is sent: every request but the page, script and stylesheet is aborted.
//   node storefront-mockup/dialog-pointer-qa.cjs
const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const read=f=>fs.readFileSync(path.join(__dirname,f));
const HTML='<!doctype html><meta charset="utf-8"><title>dialog pointer QA</title><link rel="stylesheet" href="/style.css"><body><button data-policy>Privacy</button><button id="opener" type="button">Open</button><dialog id="dialog"><button class="close" aria-label="Close details">×</button><div id="dialog-content"></div></dialog><script src="/script.js"></script>';
const FORM='<h2>Join the walk</h2><p id="para">Synthetic paragraph text that can be selected by dragging.</p><form id="f" action="/never" method="post"><label>Name <input id="name" value="Sam Synthetic"></label><label>Note <input id="note" value="two guests"></label></form>';
(async()=>{
 const browser=await chromium.launch();
 try{
  for(const width of [390,1440]){
   const ctx=await browser.newContext({viewport:{width,height:900}}),p=await ctx.newPage(),errors=[],posts=[],blocked=[];
   p.setDefaultTimeout(4000);p.on('pageerror',e=>errors.push(e.message));p.on('request',r=>{if(r.method()==='POST')posts.push(r.url())});
   await p.route('**/*',r=>{const u=new URL(r.request().url()),f={'/':['text/html',HTML],'/script.js':['text/javascript',read('script.js')],'/style.css':['text/css',read('style.css')]}[u.pathname];
    if(u.origin==='http://qa.test'&&f)return r.fulfill({contentType:f[0],body:f[1]});blocked.push(u.href);return r.abort()});
   await p.goto('http://qa.test/');
   const open=async()=>{await p.evaluate(h=>show(h),FORM);assert.equal(await p.evaluate(()=>document.querySelector('#dialog').open),true)};
   const isOpen=()=>p.evaluate(()=>document.querySelector('#dialog').open);
   const box=async s=>(await p.locator(s).boundingBox());
   const mid=async s=>{const b=await box(s);return {x:b.x+b.width/2,y:b.y+b.height/2}};
   const rect=()=>p.evaluate(()=>{const r=document.querySelector('#dialog').getBoundingClientRect();return {l:r.left,t:r.top,r:r.right,b:r.bottom}});
   const outsidePt=async()=>{const r=await rect();return {x:Math.max(2,r.l/2),y:r.t+20}};
   const gesture=async(from,to)=>{await p.mouse.move(from.x,from.y);await p.mouse.down();await p.mouse.move(to.x,to.y,{steps:6});await p.mouse.up()};
   const values=()=>p.evaluate(()=>[document.querySelector('#name').value,document.querySelector('#note').value,document.querySelector('#dialog-content').innerHTML]);
   const tag=w=>'width '+width+': '+w;
   // interior_text_drag_outside_keeps_open (also records what the page actually saw)
   await open();const before=await values();
   await p.evaluate(()=>{window.__ev=[];for(const t of ['pointerdown','pointerup','click'])document.addEventListener(t,e=>window.__ev.push({t,tg:e.target.id||e.target.tagName,x:e.clientX}),true)});
   const rBefore=await rect();await gesture(await mid('#para'),await outsidePt());
   const ev=await p.evaluate(()=>window.__ev);
   assert.equal(ev[0].tg,'para',tag('pointerdown on the paragraph'));assert.equal(ev.at(-1).t,'click',tag('a click was synthesized'));assert.equal(ev.at(-1).tg,'dialog',tag('click targets the dialog'));
   assert.ok(ev.at(-1).x<rBefore.l,tag('the click landed on the backdrop'));
   assert.equal(await isOpen(),true,tag('interior drag to backdrop keeps dialog open'));assert.deepEqual(await values(),before,tag('content unchanged'));
   // filled_form_drag_outside_keeps_values
   await p.fill('#name','Typed Synthetic');await p.fill('#note','three guests');const typed=await values();
   await gesture(await mid('#name'),await outsidePt());
   assert.equal(await isOpen(),true,tag('drag from an input keeps dialog open'));assert.deepEqual(await values(),typed,tag('typed values kept'));
   assert.deepEqual(posts,[],tag('nothing posted'));assert.deepEqual(await p.evaluate(()=>[localStorage.length,sessionStorage.length]),[0,0],tag('nothing stored'));
   // outside_press_and_release_closes, with inside clicks staying open (padding/border/paragraph), also after a resize
   const r0=await rect();
   await p.mouse.click(r0.l+2,r0.t+r0.b/2-r0.t/2);assert.equal(await isOpen(),true,tag('border/padding click keeps open'));
   await p.mouse.click((await mid('#para')).x,(await mid('#para')).y);assert.equal(await isOpen(),true,tag('paragraph click keeps open'));
   await p.setViewportSize({width:width===390?420:1200,height:800});await p.waitForTimeout(100);
   const r1=await rect();await p.mouse.click(r1.l+2,(r1.t+r1.b)/2);assert.equal(await isOpen(),true,tag('padding click after resize keeps open'));
   await p.mouse.click(...Object.values(await outsidePt()));assert.equal(await isOpen(),false,tag('plain backdrop click closes'));
   // cancelled_or_stale_pointer_cannot_close
   await p.setViewportSize({width,height:900});await open();
   await p.mouse.move(...Object.values(await outsidePt()));await p.mouse.down();
   await p.evaluate(()=>document.querySelector('#dialog').dispatchEvent(new PointerEvent('pointercancel',{bubbles:true,pointerId:1})));
   await p.mouse.up();assert.equal(await isOpen(),true,tag('cancelled outside press cannot close'));
   await p.mouse.move(...Object.values(await outsidePt()));await p.mouse.down();await p.mouse.up();assert.equal(await isOpen(),false,tag('control: fresh outside press closes'));
   await open();await p.mouse.move(...Object.values(await outsidePt()));await p.mouse.down();await p.mouse.up();assert.equal(await isOpen(),false);
   await open();await gesture(await mid('#para'),await outsidePt());assert.equal(await isOpen(),true,tag('reopened dialog: interior drag does not inherit an earlier outside press'));
   await p.evaluate(()=>document.querySelector('#dialog').dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:2,clientY:2})));
   assert.equal(await isOpen(),true,tag('a click with no outside press cannot close'));
   await gesture(await outsidePt(),await mid('#para'));assert.equal(await isOpen(),true,tag('outside-to-inside drag keeps open'));
   // close_and_escape_preserve_native_behavior
   await p.locator('.close').focus();await p.keyboard.press('Escape');assert.equal(await isOpen(),false,tag('Escape closes'));
   await p.evaluate(()=>document.querySelector('[data-policy]').click());assert.equal(await isOpen(),true);
   assert.equal(await p.locator('#dialog').getAttribute('aria-labelledby'),'dialog-title',tag('accessible title'));
   await p.locator('.close').click();assert.equal(await isOpen(),false,tag('Close button closes'));
   assert.deepEqual(errors,[],tag('page errors'));assert.deepEqual(posts,[],tag('posts'));
   await ctx.close();
  }
  console.log('dialog pointer QA passed');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});

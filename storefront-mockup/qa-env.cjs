// Guard for the storefront QA scripts: require an explicit loopback preview server
// and keep output outside the repository (default: a fresh temp folder).
// Runs before Playwright is loaded; a refusal exits 2 with one line on stderr.
const fs=require('fs'),os=require('os'),path=require('path');
const refuse=m=>{process.stderr.write('QA refused: '+m+'\n');process.exit(2)};
// Resolve symlinks and '..' component by component, as the filesystem does (a lexical
// path.resolve first would turn link/.. into the link's folder instead of its target's parent).
function canon(dir){
 let p='/';
 for(const c of (path.isAbsolute(dir)?dir:process.cwd()+'/'+dir).split('/')){
  if(c===''||c==='.')continue;
  if(c==='..'){p=path.dirname(p);continue}
  p=path.join(p,c);
  try{fs.lstatSync(p)}catch{continue}
  try{p=fs.realpathSync(p)}catch{return null}  // dangling link: refuse
 }
 return p;
}
function outside(p){
 const rel=p&&path.relative(fs.realpathSync(path.resolve(__dirname,'..')),p);
 return !!rel&&(rel==='..'||rel.startsWith('..'+path.sep)||path.isAbsolute(rel));
}
function qaEnv({preview=true}={}){
 let base;
 if(preview){
  const raw=process.env.PREVIEW_URL||'';let u=null;try{u=new URL(raw)}catch{}
  // URL drops an explicit default :80 from u.port, so also read the port from the raw authority.
  const port=u&&(u.port||/:\d+$/.test((/^http:\/\/([^/?#]*)/i.exec(raw)||[])[1]||''));
  if(!u||u.protocol!=='http:'||!['127.0.0.1','localhost'].includes(u.hostname)||!port||u.username||u.password)
   refuse('set PREVIEW_URL to an isolated loopback server (http://127.0.0.1:<port>)');
  base=u.origin+u.pathname.replace(/\/$/,'');
 }
 let out=process.env.QA_OUT_DIR;
 if(out){out=canon(out);if(!outside(out))refuse('QA_OUT_DIR must be outside the repository')}
 else{  // check the temp base itself before creating anything in it
  const tmp=canon(os.tmpdir());if(!outside(tmp))refuse('QA_OUT_DIR must be outside the repository');
  out=fs.mkdtempSync(path.join(tmp,'avoshack-qa-'));process.stderr.write('QA_OUT_DIR='+out+'\n')}
 return {out,base};
}
// Excise only the exact read-only amount from a real card for the commerce-word audit.
// Keep the normal whole-body innerText semantics, and never mask extra text or markup.
const commerceAuditText=page=>page.evaluate(()=>{
 const retained=[];
 try{
  for(const p of document.querySelectorAll('#catalog-grid article[data-product-id] .food-identity > p.product-meta.product-price')){
   const id=p.closest('article').dataset.productId;
   const price=catalog.find(record=>record.id===id)?.sellingPrice;
   if(typeof price!=='string'||!/^(?:0|[1-9][0-9]{0,5})\.[0-9]{2}(?: per lb| each)?$/.test(price)||
      p.childNodes.length!==1||p.firstChild.nodeType!==Node.TEXT_NODE||p.textContent!=='$'+price)continue;
   retained.push([p.firstChild,p.textContent]);p.firstChild.data='';
  }
  return document.body.innerText;
 }finally{for(const [node,text] of retained)node.data=text}
});
module.exports={qaEnv,commerceAuditText};

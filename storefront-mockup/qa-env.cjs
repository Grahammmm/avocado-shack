// Guard for the storefront QA scripts: require an explicit loopback preview server
// and keep output outside the repository (default: a fresh temp folder).
// Runs before Playwright is loaded; a refusal exits 2 with one line on stderr.
const fs=require('fs'),os=require('os'),path=require('path');
const refuse=m=>{process.stderr.write('QA refused: '+m+'\n');process.exit(2)};
function outside(dir){
 let p=path.resolve(dir);const tail=[];
 while(!fs.existsSync(p)){tail.unshift(path.basename(p));p=path.dirname(p)}
 p=path.join(fs.realpathSync(p),...tail);
 const rel=path.relative(fs.realpathSync(path.resolve(__dirname,'..')),p);
 return rel!==''&&(rel==='..'||rel.startsWith('..'+path.sep)||path.isAbsolute(rel));
}
function qaEnv({preview=true}={}){
 let base;
 if(preview){
  let u=null;try{u=new URL(process.env.PREVIEW_URL||'')}catch{}
  if(!u||u.protocol!=='http:'||!['127.0.0.1','localhost'].includes(u.hostname)||!u.port||u.username||u.password)
   refuse('set PREVIEW_URL to an isolated loopback server (http://127.0.0.1:<port>)');
  base=u.origin+u.pathname.replace(/\/$/,'');
 }
 let out=process.env.QA_OUT_DIR;
 if(out){if(!outside(out))refuse('QA_OUT_DIR must be outside the repository')}
 else{out=fs.mkdtempSync(path.join(os.tmpdir(),'avoshack-qa-'));process.stderr.write('QA_OUT_DIR='+out+'\n')}
 return {out,base};
}
module.exports={qaEnv};

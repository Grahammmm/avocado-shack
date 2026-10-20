import sharp from 'sharp';import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {execFile} from 'node:child_process';import {promisify} from 'node:util';
const run=promisify(execFile),pixels=40000000;
const unreadable=()=>Object.assign(new Error('This photo could not be read. Please send a JPEG, PNG, WebP, or a readable HEIC photo.'),{status:422});
export async function ownerPhoto(buffer){
 let metadata;try{metadata=await sharp(buffer,{limitInputPixels:pixels}).metadata()}catch{throw unreadable()}
 if(!['jpeg','png','webp','heif'].includes(metadata.format)||!metadata.width||!metadata.height||metadata.width*metadata.height>pixels)throw unreadable();
 const encode=input=>sharp(input,{limitInputPixels:pixels}).rotate().resize({width:1400,height:1800,fit:'inside',withoutEnlargement:true}).jpeg({quality:88}).toBuffer();
 try{return {jpeg:await encode(buffer),format:metadata.format,decoder:'sharp'}}catch{if(metadata.format!=='heif'||process.platform!=='darwin')throw unreadable()}
 const folder=await fs.mkdtemp(path.join(os.tmpdir(),'avo-heic-'));try{
  const input=path.join(folder,'input.heic'),output=path.join(folder,'decoded.jpg');await fs.writeFile(input,buffer,{mode:0o600});await run('/usr/bin/sips',['-s','format','jpeg',input,'--out',output],{timeout:30000,maxBuffer:65536});await fs.chmod(output,0o600);return {jpeg:await encode(await fs.readFile(output)),format:metadata.format,decoder:'macos-sips'};
 }catch{throw unreadable()}finally{await fs.rm(folder,{recursive:true,force:true})}
}

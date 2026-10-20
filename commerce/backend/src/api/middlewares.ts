import {defineMiddlewares} from '@medusajs/framework/http'
import {timingSafeEqual} from 'node:crypto'
export default defineMiddlewares({routes:[{matcher:'/internal/*',middlewares:[(req:any,res:any,next:any)=>{const supplied=String(req.headers['x-avo-internal']||'');const expected=process.env.JWT_SECRET||'';if(!expected||supplied.length!==expected.length||!timingSafeEqual(Buffer.from(supplied),Buffer.from(expected)))return res.status(403).json({error:'Forbidden'});next()}]}]})

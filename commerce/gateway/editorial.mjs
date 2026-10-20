export const defaultContent={featured_product_id:'',featured_revision:'',hours:'Monday–Friday: 9am–6pm\nSaturday: 9am–5pm\nSunday: Closed',welcome:'Browse what’s in the Shack, choose your favorites, and pick up in Morro Bay.',note_heading:'There’s always something worth discovering.',note:'Good food begins with attention: to the season, to the people who grow it, and to the neighbors who bring it home.'};
export function validateContent(value){if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('Provide website copy.');const output={};for(const key of Object.keys(defaultContent)){const text=value[key]===undefined?defaultContent[key]:value[key];if(['featured_product_id','featured_revision'].includes(key)){if(typeof text!=='string'||text.length>200)throw new Error('Choose one featured product.');output[key]=text.trim();continue;}if(typeof text!=='string'||!text.trim()||text.length>(key==='note_heading'?100:key==='hours'?500:1500))throw new Error('Use a short, nonempty '+key.replaceAll('_',' ')+'.');output[key]=text.trim()}return output}
export function validateSlot({capacity,cutoff,starts_at,active}){if(!Number.isSafeInteger(capacity)||capacity<1||capacity>100)throw new Error('Capacity must be 1 to 100 orders.');if(typeof active!=='boolean')throw new Error('Choose whether bookings are open.');const date=new Date(cutoff);if(!Number.isFinite(date.getTime())||date>new Date(starts_at))throw new Error('The cutoff must be at or before pickup starts.');return {capacity,active,cutoff:date.toISOString()}}

export function interpretContentMessage(message){
 const match=message.match(/^(?:website\s+(note|welcome|heading|hours)|(?:change|set|update)\s+(?:the\s+)?(welcome|owner note|owner-note heading|note heading|store hours|hours)\s+to)\s*:\s*([\s\S]+)$/i);
 if(!match)return null;const label=(match[1]||match[2]).toLowerCase();return {key:label.includes('hours')?'hours':label==='welcome'?'welcome':label.includes('heading')?'note_heading':'note',text:match[3].trim()};
}

export function interpretFeatureMessage(message){
 if(/^stop featuring products[.!]?$/i.test(message.trim()))return {clear:true};
 const match=message.trim().match(/^feature(?: product)?(?:\s*:\s*|\s+)(.{1,200})$/i);return match?{name:match[1].trim()}:null;
}

export const featureRevision=product=>product.metadata.source_draft+':'+product.metadata.applied_version;

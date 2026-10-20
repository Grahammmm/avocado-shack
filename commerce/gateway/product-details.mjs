export const detailKeys=['description','package_size','ingredients','allergens','handling'];
export function productDetails(fields){
 const result={};for(const key of detailKeys){if(fields[key]===undefined)continue;if(typeof fields[key]!=='string'||fields[key].length>(key==='description'?2000:1000))throw Object.assign(new Error('Keep product details as short plain text.'),{status:422});result[key]=fields[key].trim();}return result;
}

function canonical(value){if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));return value}
export function sameQuoteItems(a,b){return JSON.stringify(canonical(a))===JSON.stringify(canonical(b))}
export function samePurchaseItems(saved,submitted){
 if(!Array.isArray(submitted)||saved.length!==submitted.length||new Set(submitted.map(i=>i.product_id)).size!==submitted.length)return false;
 return saved.every(old=>{const item=submitted.find(i=>i.product_id===old.product_id);return item&&Number.isSafeInteger(item.quantity)&&item.quantity===old.quantity&&(!item.variant_id||item.variant_id===old.variant_id)});
}

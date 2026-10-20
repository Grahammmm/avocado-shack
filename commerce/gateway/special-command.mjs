import {discountRule} from './discount-rule.mjs';
// Explicit owner input only. This proposes an immediate price/allocation update,
// not a scheduled promotion or automatic price restoration.
export function specialCommand(message,products){
 if(!/^special\s*:/i.test(message.trim()))return null;
 const m=message.trim().match(/^special\s*:\s*([^,\n]{2,80}),\s*(each|jar|bottle|bag|loaf|bunch),\s*(\$\d+(?:\.\d{1,2})?|\d{1,3}(?:\.\d{1,2})?%\s+off),\s*(\d+) available for online pickup\.?$/i);
 if(!m)throw Object.assign(new Error('Use “Special: product name, each, $price, quantity available for online pickup”. A price may also be written as 25% off. Use the separate scheduled-special command for dates.'),{status:422});
 const matches=products.filter(p=>p.title.trim().toLowerCase()===m[1].trim().toLowerCase()&&p.metadata.unit===m[2].toLowerCase());
 if(matches.length!==1||matches[0].metadata.kind==='box'||matches[0].variants.length!==1)throw Object.assign(new Error('Choose one already approved individual product with its exact selling unit.'),{status:422});
 const product=matches[0],quantity=Number(m[4]);
 const normal=product.variants[0].price_set?.prices?.find(p=>p.currency_code==='usd'&&!p.price_list_id);const previous_price_minor=normal?Math.round(Number(normal.amount)*100):product.metadata.price_minor;
 const {price_minor,rule}=discountRule(previous_price_minor,m[3]);
 if(!Number.isSafeInteger(price_minor)||price_minor<=0||price_minor>=previous_price_minor||!Number.isSafeInteger(quantity)||quantity<=0||quantity>100000)throw Object.assign(new Error('A special requires a lower positive price and a positive confirmed online quantity.'),{status:422});
 return {fields:{name:product.title,unit:product.metadata.unit,price_minor,quantity,stock_pool:'online',stock_action:'recount',_special_source:{product_id:product.id,revision:`${product.metadata.source_draft}:${product.metadata.applied_version}`,price_minor:previous_price_minor,discount_rule:rule}},note:`Owner-proposed special${rule.type==='percentage'?' ('+rule.expression+'; '+rule.rounding+')':''}: $${(previous_price_minor/100).toFixed(2)} to $${(price_minor/100).toFixed(2)} per ${product.metadata.unit}; total online allocation ${quantity}. Changes only after approval. No end date or automatic price restoration is set. Existing accepted orders keep their original price.`};
}

export function assertSpecialSource(fields,product){
 const source=fields._special_source;if(!source)return;
 if(fields._approved_target!==undefined)return; // Already frozen for supported-engine retry.
 const price=product?.variants[0]?.price_set?.prices?.find(p=>p.currency_code==='usd'&&!p.price_list_id);const currentPrice=price?Math.round(Number(price.amount)*100):product?.metadata.price_minor;
 if(!product||product.status!=='published'||product.id!==source.product_id||`${product.metadata.source_draft}:${product.metadata.applied_version}`!==source.revision||currentPrice!==source.price_minor)throw Object.assign(new Error('The special’s product changed. Send a new special and review it.'),{status:409});
 if(source.discount_rule&&fields.price_minor!==discountRule(currentPrice,source.discount_rule.expression).price_minor)throw Object.assign(new Error('The price no longer matches the reviewed discount rule. Send a new special.'),{status:422});
 if(fields.price_minor>=currentPrice||fields.stock_action!=='recount'||fields.stock_pool!=='online')throw Object.assign(new Error('Review a lower special price and the total online quantity.'),{status:422});
}

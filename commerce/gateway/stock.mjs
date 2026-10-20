export function stockTarget({action,quantity,before,reserved,reason}){
 if(!['receipt','transfer_in','transfer_out','recount','spoilage','correction'].includes(action))throw new Error('Choose a supported stock movement.');
 if(!Number.isSafeInteger(quantity)||quantity<0)throw new Error('Quantity must be a nonnegative whole selling unit.');
 if(!reason?.trim())throw new Error('Give a reason for the stock movement.');
 const target=['receipt','transfer_in'].includes(action)?before+quantity:['transfer_out','spoilage'].includes(action)?before-quantity:quantity;
 if(target<reserved||target<0)throw new Error('This movement would consume reserved stock or overdraw the online bin.');
 return target;
}

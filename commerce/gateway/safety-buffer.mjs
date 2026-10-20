export function bufferAvailable(level,buffer=0){
 const stocked=Number(level?.stocked_quantity),reserved=Number(level?.reserved_quantity);
 if(!Number.isSafeInteger(stocked)||!Number.isSafeInteger(reserved)||stocked<0||reserved<0||!Number.isSafeInteger(buffer)||buffer<0)throw new Error('Inventory availability needs review.');
 return Math.max(0,stocked-reserved-buffer);
}

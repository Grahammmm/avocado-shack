import type {MedusaContainer} from '@medusajs/framework/types'
import {Modules} from '@medusajs/framework/utils'
import {createInventoryLevelsWorkflow,updateInventoryLevelsWorkflow} from '@medusajs/medusa/core-flows'
type Target={inventory_id:string,location_id:string,operation_id:string,expected_before:number,target_quantity:number}
// The quantity and receipt share one native inventory-level update. A replay
// returns current stock; it never recounts an old target after a later movement.
export async function applyInventoryTarget(scope:MedusaContainer,input:Target,allowCreate=false){
 const inventory=scope.resolve(Modules.INVENTORY);let [level]=await inventory.listInventoryLevels({inventory_item_id:input.inventory_id,location_id:input.location_id});
 if(!Number.isSafeInteger(input.expected_before)||!Number.isSafeInteger(input.target_quantity)||input.target_quantity<0)throw new Error('Exact stock target required');
 if(!level){if(!allowCreate||input.expected_before!==0)throw new Error('Online bin not found');await createInventoryLevelsWorkflow(scope).run({input:{inventory_levels:[{inventory_item_id:input.inventory_id,location_id:input.location_id,stocked_quantity:0}]}});[level]=await inventory.listInventoryLevels({inventory_item_id:input.inventory_id,location_id:input.location_id});}
 const receipts=(level.metadata?.avo_stock_receipts||{}) as Record<string,{target_quantity:number}>;
 if(Object.prototype.hasOwnProperty.call(receipts,input.operation_id)){if(receipts[input.operation_id].target_quantity!==input.target_quantity)throw new Error('Stock receipt target differs');return {quantity:Number(level.stocked_quantity),reserved_quantity:Number(level.reserved_quantity),applied_target:input.target_quantity,replayed:true};}
 if(Number(level.stocked_quantity)!==input.expected_before)throw new Error('Physical stock changed before this operation was applied');if(input.target_quantity<Number(level.reserved_quantity))throw new Error('Movement would consume reserved stock');
 const update={id:level.id,inventory_item_id:input.inventory_id,location_id:input.location_id,stocked_quantity:input.target_quantity,metadata:{...level.metadata,avo_stock_receipts:{...receipts,[input.operation_id]:{target_quantity:input.target_quantity}}}};
 await updateInventoryLevelsWorkflow(scope).run({input:{updates:[update]}});[level]=await inventory.listInventoryLevels({inventory_item_id:input.inventory_id,location_id:input.location_id});
 if(Number(level.stocked_quantity)!==input.target_quantity||(level.metadata?.avo_stock_receipts as any)?.[input.operation_id]?.target_quantity!==input.target_quantity)throw new Error('Stock and operation receipt readback mismatch');return {quantity:Number(level.stocked_quantity),reserved_quantity:Number(level.reserved_quantity),applied_target:input.target_quantity,replayed:false};
}

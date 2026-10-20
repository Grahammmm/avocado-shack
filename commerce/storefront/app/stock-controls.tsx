'use client';
import {useState} from 'react';
export default function StockControls({products,movements=[],busy,onApply}:any){
 const [reference,setReference]=useState(''),[action,setAction]=useState('receipt'),[productId,setProductId]=useState('');
 const individual=products.filter((p:any)=>p.metadata.kind!=='box');
 const selected=productId||individual[0]?.id;
 const previous=movements.filter((m:any)=>m.product_id===selected&&m.state==='applied');
 return <details className="stock-controls"><summary>Record an online-bin stock movement</summary>
 <p>Receipts and transfers in add units. Counter transfers and spoilage remove units. Recounts set the total. Reserved pickup stock is protected.</p>
 <form onSubmit={e=>{e.preventDefault();const f=new FormData(e.currentTarget);const event_id=reference||crypto.randomUUID();setReference(event_id);onApply({product_id:f.get('product_id'),action:f.get('action'),quantity:Number(f.get('quantity')),reason:f.get('reason'),corrects_movement_id:f.get('corrects_movement_id')||null,event_id},()=>setReference(''))}}>
 <div className="form-grid"><label>Product<select name="product_id" required value={selected||''} onChange={e=>setProductId(e.target.value)}>{individual.map((p:any)=><option key={p.id} value={p.id}>{p.title} / {p.metadata.unit}</option>)}</select></label>
 <label>Movement<select name="action" value={action} onChange={e=>setAction(e.target.value)}><option value="receipt">New units received</option><option value="transfer_in">Move counter stock into online bin</option><option value="transfer_out">Move online stock to counter</option><option value="spoilage">Remove spoiled units</option><option value="recount">Set counted online total</option><option value="correction">Correct a recorded movement</option></select></label>
 {action==='correction'&&<label>Movement to correct<select name="corrects_movement_id" required defaultValue="" key={selected}><option value="">Choose the earlier movement</option>{previous.map((m:any)=><option key={m.id} value={m.id}>{m.action}: {m.before_quantity} → {m.target_quantity} · {m.reason}</option>)}</select></label>}
 <label>{action==='correction'||action==='recount'?'Correct online total':'Quantity'}<input name="quantity" type="number" min="0" step="1" required/></label><label>Reason<input name="reason" maxLength={500} required/></label></div>
 <button disabled={busy||!individual.length||(action==='correction'&&!previous.length)}>Apply and verify this movement</button></form>
 <h3>Recent stock history</h3>{!movements.length?<p>No recorded movements yet.</p>:<ol className="stock-history">{movements.slice(0,15).map((m:any)=><li key={m.id}><strong>{products.find((p:any)=>p.id===m.product_id)?.title||'Product'} · {m.action}</strong><br/>{m.before_quantity} → {m.target_quantity} · {m.state}<br/>{m.reason}{m.corrects_movement_id&&<small>Corrects movement {m.corrects_movement_id.slice(0,8)}</small>}</li>)}</ol>}
 </details>;
}

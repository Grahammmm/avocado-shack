from pathlib import Path
import json,html
r=Path(__file__).resolve().parent
observations=[
('Preserves shelf','Multiple jars of preserves; individual flavors and sizes need label review.'),
('Flower bouquets','Mixed bouquets displayed; flower varieties and selling unit unconfirmed.'),
('Pantry shelf','Packaged products and bottled drinks; separate individual products before approval.'),
('Sauces and coffee','Jarred sauces, bottled sauces, and coffee bags visible; variants unconfirmed.'),
('Sauces','Multiple bottled sauces; match each price tag to its exact product.'),
('Canned cider','SLO Cider branding visible; alcohol status requires review; block online publication until reviewed.'),
('Bread','Packaged bread loaves; brand signage and individual varieties visible.'),
('Produce display','Avocados, citrus and other produce; separate varieties and units.'),
('Produce display','Mixed fruits and vegetables; shelf photo cannot establish total stock.'),
('Refrigerated beverages','Cans/bottles behind glass; glare obscures some labels; alcohol status unconfirmed.'),
('Refrigerated deli','Salamini, sliced/packaged deli items and cheese; refrigeration and labels require review.'),
('Eggs','Egg cartons and a promotional sign; confirm carton size, current price and promotion limits.'),
('Dairy','Milk, cream, butter and yogurt; brands/variants require individual label review.'),
('Prepared foods','Refrigerated jars/tubs and eggs; contents and allergens need label review.'),
('Cheese and eggs','Packaged cheese and egg cartons; variants and sizes require confirmation.'),
('Cheese','Packaged cheese; individual varieties and weights require label review.'),
('Pantry and honey','Packaged dry goods, honey and preserves; several distinct products.'),
('Oil and pantry','Bottled oil and packaged dry goods; sizes and product names need review.'),
('Oil and dry goods','Bottled oil and packaged dry goods; may overlap the preceding shelf photo.'),
('Bottled drinks','Bottled beverages and a promotional sign; exact variants and current prices unconfirmed.'),
('Packaged pantry','Several packaged/jarred products; sideways photo; rotate in review without overwriting original.'),
('Pantry staples','Bottles of grains/legumes, jars and other staples; exact units unconfirmed.'),
('Berries','Strawberries and other berries in containers; pack sizes and varieties need confirmation.'),
('Vegetables','Fennel, broccoli, leafy vegetables, celery and other produce; separate products.'),
('Root vegetables','Carrots, beets and other produce; selling units unconfirmed.'),
('Greens and mushrooms','Packaged greens and several mushroom types; identify individual varieties.'),
('Vegetables and greens','Packaged greens, ginger, peppers, eggplant and other produce; separate products.'),
('Tomatoes and produce','Tomatoes and mixed produce; reused shipping cartons do not prove origin or supplier.'),
('Melons','Several melons/watermelons; varieties, weights and selling units unconfirmed.'),
('Fruit and avocados','Mixed fruit and avocado display; avocado variety and prices require review.'),
('Store overview','Wide shop photo; suitable store context, not a single product record.'),
('Bread and store view','Packaged bread display and store context; separate from individual product images.'),
('Store overview','Wide shop photo; suitable store context, not a stock count.')]
manifest=json.loads((r/'manifest.json').read_text());unique=[x for x in manifest if 'photo'in x];cards=[]
for row,(category,note) in zip(unique,observations):
 row['observed_category']=category;row['visual_observation']=note;row['publication_status']='private_draft';row['shipping_eligibility']='unverified';row['stock_count_inferred']=False
 filename=Path(row['photo']).name
 cards.append(f'<article><a href="photos/{filename}"><img loading="lazy" src="previews/{filename}" alt="{html.escape(category)}"></a><div><small>{filename}</small><h2>{html.escape(category)}</h2><p>{html.escape(note)}</p><p class="unknown">Price · quantity · selling unit · online allocation: owner confirmation needed.</p></div></article>')
(r/'manifest.json').write_text(json.dumps(manifest,indent=2))
(r/'review.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Avocado Shack photo intake</title><style>body{margin:0;background:#f7f6ef;color:#183e32;font:17px/1.5 system-ui}header,main{max-width:1200px;margin:auto;padding:24px}h1{font:44px Georgia}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}article{background:white;border:1px solid #ddd}img{width:100%;height:300px;object-fit:contain;background:#eee}article div{padding:18px}h2{font-size:22px}small{color:#555}.unknown{font-size:15px;color:#665536}a:focus-visible{outline:4px solid #ac472b}</style><header><h1>Product photos. Private review.</h1><p>33 unique photos · 3 exact duplicates linked. These are product evidence, not verified stock. Nothing is published or available to order.</p><p>Photo → identify individual products → confirm price, unit, receipt/count and online-bin quantity → review exact changes → approve → verify saved result.</p></header><main><section>'''+''.join(cards)+'</section></main></html>')
print('33 photo observations saved; review page created; no price or stock invented.')

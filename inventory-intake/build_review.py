from pathlib import Path
import json,html,sys
from urllib.parse import quote
r=Path(__file__).resolve().parent
UNKNOWN_CATEGORY='Photo awaiting review'
UNKNOWN_NOTE='Product identity and details need owner review.'
manifest=json.loads((r/'manifest.json').read_text());unique=[x for x in manifest if 'photo'in x];cards=[]
# Each photo row is rendered from its OWN recorded observations only; nothing is attached by position.
# Preflight every row before any output is written, so a refusal leaves both outputs untouched.
for number,row in enumerate(unique,1):
 for field in('observed_category','visual_observation'):
  if field in row and not isinstance(row[field],str):sys.exit(f'refused: photo row {number}: {field} must be a string; no files written')
duplicates=[x for x in manifest if 'duplicate_of'in x and 'photo'not in x]
for row in unique:
 category=row.get('observed_category')or UNKNOWN_CATEGORY;note=row.get('visual_observation')or UNKNOWN_NOTE
 row['observed_category']=category;row['visual_observation']=note;row['publication_status']='private_draft';row['shipping_eligibility']='unverified';row['stock_count_inferred']=False
 filename=Path(row['photo']).name;asset_name=quote(filename,safe='');display_name=html.escape(filename,quote=True)
 cards.append(f'<article><a href="{html.escape("photos/"+asset_name,quote=True)}"><img loading="lazy" src="{html.escape("previews/"+asset_name,quote=True)}" alt="{html.escape(category)}"></a><div><small>{display_name}</small><h2>{html.escape(category)}</h2><p>{html.escape(note)}</p><p class="unknown">Price · quantity · selling unit · online allocation: owner confirmation needed.</p></div></article>')
(r/'manifest.json').write_text(json.dumps(manifest,indent=2))
(r/'review.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Avocado Shack photo intake</title><style>body{margin:0;background:#f7f6ef;color:#183e32;font:17px/1.5 system-ui}header,main{max-width:1200px;margin:auto;padding:24px}h1{font:44px Georgia}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}article{background:white;border:1px solid #ddd}img{width:100%;height:300px;object-fit:contain;background:#eee}article div{padding:18px}h2{font-size:22px}small{color:#555}.unknown{font-size:15px;color:#665536}a:focus-visible{outline:4px solid #ac472b}</style><header><h1>Product photos. Private review.</h1><p>'''+f'{len(unique)} unique photos · {len(duplicates)} exact duplicates linked.'+''' These are product evidence, not verified stock. Nothing is published or available to order.</p><p>Photo → identify individual products → confirm price, unit, receipt/count and online-bin quantity → review exact changes → approve → verify saved result.</p></header><main><section>'''+''.join(cards)+'</section></main></html>')
print(f'{len(unique)} photo observations saved; review page created; no price or stock invented.')

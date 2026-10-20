from pathlib import Path
import hashlib,json,subprocess
from PIL import Image,ImageOps,ImageDraw
root=Path(__file__).resolve().parent
names=[f'IMG_{i}.heic' for i in range(9707,9740)]+['IMG_9709 2.heic','IMG_9708 2.heic','IMG_9708 3.heic']
rows=[];seen={}
for name in names:
 p=Path('/Users/owner/Downloads')/name;h=hashlib.sha256(p.read_bytes()).hexdigest()
 if h in seen:
  rows.append({'source_file':str(p),'sha256':h,'duplicate_of':seen[h]});continue
 seen[h]=name;dest=root/'photos'/f'{p.stem}.jpg'
 subprocess.run(['/usr/bin/sips','-s','format','jpeg',str(p),'--out',str(dest)],stdout=subprocess.DEVNULL,check=True)
 im=Image.open(dest);im.thumbnail((1200,1200));im.save(root/'previews'/dest.name,quality=90)
 rows.append({'source_file':str(p),'sha256':h,'photo':str(dest),'status':'needs_review','product_name':None,'quantity':None,'stock_pool':None,'unit':None,'price_minor_units':None,'currency':'USD','claims':[]})
unique=[r for r in rows if 'photo'in r]
for batch in range(3):
 sheet=Image.new('RGB',(1000,1200),'#eee');d=ImageDraw.Draw(sheet)
 for j,r in enumerate(unique[batch*12:(batch+1)*12]):
  im=Image.open(r['photo']);im.thumbnail((245,345));x=(j%4)*250;y=(j//4)*400;sheet.paste(im,(x+(250-im.width)//2,y+30));d.text((x+8,y+8),Path(r['photo']).stem,fill='black')
 sheet.save(root/f'contact-sheet-{batch+1}.jpg',quality=92)
(root/'manifest.json').write_text(json.dumps(rows,indent=2))
print(f'{len(unique)} unique photos imported; {len(rows)-len(unique)} duplicate files linked; originals unchanged.')

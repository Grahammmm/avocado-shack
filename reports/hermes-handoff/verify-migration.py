"""Read-only current-site checks plus isolated API fixtures. No outbound mail."""
import concurrent.futures, datetime, hashlib, json, os, sqlite3, subprocess, tempfile, time, urllib.error, urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[2]
base='http://127.0.0.1:3101'
def request(base,path,data=None,origin=None):
 headers={'Content-Type':'application/json'}
 if origin: headers['Origin']=origin
 req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
 try:
  with urllib.request.urlopen(req,timeout=5) as response: return response.status,json.load(response)
 except urllib.error.HTTPError as response:return response.code,json.load(response)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
result={}
status,public=request(base,'/api/community');assert status==200
assert public['events']==[] and len(public['routeIdeas'])==3 and not public['emailConnected']
result['activeCalendarUndatedOnly']=True
catalog=json.loads((root/'storefront-mockup/catalog-products.js').read_text().split('=',1)[1].strip().removesuffix(';'))
assert len(catalog)==170
for item in catalog:
 assert 'price' not in item
 path=item['image'];assert (root/'storefront-mockup'/path).is_file()
 with urllib.request.urlopen(base+'/'+path,timeout=5) as response:assert response.status==200
result['catalogImagesServed']=len(catalog)
db=Path(os.environ['AVOSHACK_COMMUNITY_DB'])
with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as connection:
 assert connection.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
 result['communityDatabaseIntegrity']='ok'
 result['subscriptionCount']=connection.execute('select count(*) from subscriptions').fetchone()[0]
 result['rsvpCount']=connection.execute('select count(*) from rsvps').fetchone()[0]
future=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=30)).isoformat()
with tempfile.TemporaryDirectory(prefix='avoshack-migration-') as directory:
 directory=Path(directory);cfg=directory/'community.json';fixturedb=directory/'community.sqlite3'
 cfg.write_text(json.dumps({'events':[{'id':'qa','title':'QA only','startsAt':future,'status':'scheduled','meetingPoint':'Fixture','capacity':1,'rsvpEnabled':True}]}))
 env={**os.environ,'AVOSHACK_COMMUNITY_CONFIG':str(cfg),'AVOSHACK_COMMUNITY_DB':str(fixturedb)}
 process=subprocess.Popen(['python3',str(root/'storefront-mockup/community-server.py'),'--port','3102'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 fixture='http://127.0.0.1:3102'
 try:
  for _ in range(50):
   try: request(fixture,'/api/community');break
   except OSError:time.sleep(.1)
  assert request(fixture,'/api/community/subscriptions',{'email':'bad','newsletter':True})[0]==400
  assert request(fixture,'/api/community/subscriptions',{'email':'qa@example.invalid','newsletter':True},'https://unrelated.example')[0]==403
  assert request(fixture,'/api/community/subscriptions',{'email':'qa@example.invalid','newsletter':True})[0]==200
  assert request(fixture,'/api/community/subscriptions',{'email':'qa@example.invalid','hikes':True})[0]==200
  with sqlite3.connect(fixturedb) as c:assert c.execute('select newsletter,hikes from subscriptions').fetchall()==[(1,1)]
  def reserve(i):return request(fixture,'/api/community/rsvps',{'eventId':'qa','email':f'rsvp{i}@example.invalid','name':'QA','partySize':1})[0]
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(reserve,[1,2]))==[200,409]
  assert 'example.invalid' not in json.dumps(request(fixture,'/api/community')[1])
  with sqlite3.connect(fixturedb) as c:
   saved=directory/'restore.sqlite3'
   with sqlite3.connect(saved) as target:c.backup(target)
  with sqlite3.connect(saved) as c:assert c.execute('select count(*) from rsvps').fetchone()[0]==1
  result.update({'isolatedSignupPersistence':True,'consentMerge':True,'invalidEmailRejected':True,'crossOriginRejected':True,'concurrentCapacitySafe':True,'publicApiNoPersonalData':True,'isolatedSqliteBackupRestore':True})
 finally:process.terminate();process.wait(timeout=5)
result['passed']=True
print(json.dumps(result,indent=2))

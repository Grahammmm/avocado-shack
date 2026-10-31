import concurrent.futures, datetime, json, os, sqlite3, subprocess, sys, tempfile, time, urllib.parse, urllib.request, urllib.error
from pathlib import Path
root=Path(__file__).resolve().parent
base='http://127.0.0.1:3102'
def refuse(m):print('QA refused: '+m,file=sys.stderr);sys.exit(2)
try:u=urllib.parse.urlsplit(os.environ.get('PREVIEW_URL',''));loop=u.scheme=='http' and u.hostname in('127.0.0.1','localhost') and u.port is not None and u.username is None
except ValueError:loop=False
if not loop:refuse('set PREVIEW_URL to an isolated loopback server (http://127.0.0.1:<port>)')
out=os.environ.get('QA_OUT_DIR')
if out:
 p=Path(os.path.abspath(out));tail=[]
 while not p.exists():tail.insert(0,p.name);p=p.parent
 p=p.resolve().joinpath(*tail);repo=root.parent.resolve()
 if p==repo or repo in p.parents:refuse('QA_OUT_DIR must be outside the repository')
else:out=tempfile.mkdtemp(prefix='avoshack-qa-');print('QA_OUT_DIR='+out,file=sys.stderr)
future=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=30)).isoformat()
events=[dict(id='qa-hike',title='QA trail fixture',startsAt=future,status='scheduled',meetingPoint='QA meeting point',distance='3 miles',difficulty='Gentle pace',duration='2 hours',capacity=3,rsvpEnabled=True),dict(id='qa-race',title='QA limited places',startsAt=future,status='scheduled',meetingPoint='QA meeting point',capacity=1,rsvpEnabled=True),dict(id='qa-past',title='QA past outing',startsAt='2025-01-01T10:00:00-08:00',status='completed',meetingPoint='QA meeting point',recap='A test history entry; not a published hike.',rsvpEnabled=False)]
events.append(dict(id='qa-unlimited',title='QA uncapped event',startsAt=future,status='scheduled',meetingPoint='QA meeting point',rsvpEnabled=True,confirmedGuests=999))
with tempfile.TemporaryDirectory(prefix='avoshack-community-qa-') as t:
 config=Path(t)/'community.json';dbpath=Path(t)/'community.sqlite3';config.write_text(json.dumps({'events':events}))
 env={**os.environ,'AVOSHACK_COMMUNITY_CONFIG':str(config),'AVOSHACK_COMMUNITY_DB':str(dbpath)}
 proc=subprocess.Popen(['python3',str(root/'community-server.py'),'--port','3102'],env=env,stdout=subprocess.DEVNULL)
 def request(path,data=None,origin=None):
  headers={'Content-Type':'application/json'}
  if origin:headers['Origin']=origin
  r=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
  try:
   with urllib.request.urlopen(r,timeout=5) as x:return x.status,json.load(x)
  except urllib.error.HTTPError as x:return x.code,json.load(x)
 try:
  for i in range(40):
   try:request('/api/community');break
   except OSError:time.sleep(.1)
  assert request('/api/community/subscriptions',{'email':'not valid','newsletter':True})[0]==400
  assert request('/api/community/subscriptions',{'email':'qa@example.invalid','newsletter':True},'https://unrelated.example')[0]==403
  assert request('/api/community/subscriptions',{'email':'Qa@Example.invalid','newsletter':True})[0]==200
  assert request('/api/community/subscriptions',{'email':'qa@example.invalid','hikes':True})[0]==200
  with sqlite3.connect(dbpath) as db:assert db.execute('SELECT newsletter,hikes FROM subscriptions WHERE email=?',('qa@example.invalid',)).fetchone()==(1,1)
  assert all(e['confirmedGuests']==0 for e in request('/api/community')[1]['events'])
  payload={'eventId':'qa-hike','name':'QA Person','email':'rsvp@example.invalid','partySize':2}
  assert request('/api/community/rsvps',payload)[0]==200
  assert request('/api/community/rsvps',payload)[1]['alreadyRegistered']
  event=next(e for e in request('/api/community')[1]['events'] if e['id']=='qa-hike')
  assert event['remaining']==1 and event['confirmedGuests']==2
  assert request('/api/community/rsvps',{**payload,'eventId':'qa-unlimited','partySize':4})[0]==200
  event=next(e for e in request('/api/community')[1]['events'] if e['id']=='qa-unlimited')
  assert event['remaining'] is None and event['confirmedGuests']==4
  assert request('/api/community/rsvps',{**payload,'email':'too-many@example.invalid'})[0]==409
  assert request('/api/community/rsvps',{**payload,'eventId':'qa-past'})[0]==409
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   results=list(pool.map(lambda i:request('/api/community/rsvps',{**payload,'eventId':'qa-race','partySize':1,'email':f'race{i}@example.invalid'})[0],range(2)))
  assert sorted(results)==[200,409]
  public=json.dumps(request('/api/community')[1]);assert 'example.invalid' not in public
  node=os.environ.get('NODE','node')
  subprocess.run([node,str(root/'community-ui-qa.cjs')],env={**os.environ,'COMMUNITY_TEST_URL':base,'QA_OUT_DIR':out},check=True)
  result={'subscriptionsPersisted':True,'consentMerge':True,'invalidEmailRejected':True,'crossOriginRejected':True,'duplicateRSVPPrevented':True,'capacityEnforced':True,'concurrentCapacitySafe':True,'pastRSVPRejected':True,'noPersonalDataInPublicAPI':True,'noExternalEmailSent':True,'fixtureDataIsolated':True,'guestCountIncludesPartySize':True,'duplicateGuestCountStable':True,'uncappedGuestCount':True,'configuredCountCannotOverrideDatabase':True}
  (Path(out)/'community-api-QA.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
 finally:proc.terminate();proc.wait(timeout=5)

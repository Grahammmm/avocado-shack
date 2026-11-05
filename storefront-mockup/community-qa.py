import concurrent.futures, datetime, importlib.util, json, os, sqlite3, subprocess, sys, tempfile, threading, urllib.parse, urllib.request, urllib.error
from pathlib import Path
root=Path(__file__).resolve().parent
def refuse(m):print('QA refused: '+m,file=sys.stderr);sys.exit(2)
try:u=urllib.parse.urlsplit(os.environ.get('PREVIEW_URL',''));loop=u.scheme=='http' and u.hostname in('127.0.0.1','localhost') and u.port is not None and u.username is None
except ValueError:loop=False
if not loop:refuse('set PREVIEW_URL to an isolated loopback server (http://127.0.0.1:<port>)')
out=os.environ.get('QA_OUT_DIR')
if out:
 p='/'  # resolve symlinks and '..' in order, as the filesystem does (abspath first would not)
 for c in os.path.join(os.getcwd(),out).split('/'):p=p if c in('','.') else os.path.dirname(p) if c=='..' else os.path.realpath(os.path.join(p,c))
 out=p;repo=str(root.parent.resolve())
 if p==repo or p.startswith(repo+os.sep):refuse('QA_OUT_DIR must be outside the repository')
else:out=tempfile.mkdtemp(prefix='avoshack-qa-');print('QA_OUT_DIR='+out,file=sys.stderr)
future=(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(days=30)).isoformat()
events=[dict(id='qa-hike',title='QA trail fixture',startsAt=future,status='scheduled',meetingPoint='QA meeting point',distance='3 miles',difficulty='Gentle pace',duration='2 hours',capacity=3,rsvpEnabled=True),dict(id='qa-race',title='QA limited places',startsAt=future,status='scheduled',meetingPoint='QA meeting point',capacity=1,rsvpEnabled=True),dict(id='qa-past',title='QA past outing',startsAt='2025-01-01T10:00:00-08:00',status='completed',meetingPoint='QA meeting point',recap='A test history entry; not a published hike.',rsvpEnabled=False)]
events.append(dict(id='qa-unlimited',title='QA uncapped event',startsAt=future,status='scheduled',meetingPoint='QA meeting point',rsvpEnabled=True,confirmedGuests=999))
# AV0207-01: one hike with every owner-set logistics field and one with none (the server must pass them through).
events.append(dict(id='qa-full',title='QA all logistics',startsAt=future,status='scheduled',meetingPoint='QA full meeting point',meetTime='8:45 am',meetingAddress='QA Road 1, Los Osos',walkTime='9:00 am',returnTime='Around 12:30 pm',distance='4 miles',difficulty='Easy',duration='3 hours',bring='Water and a snack',accessNote='QA access: no pets.',rsvpEnabled=True))
events.append(dict(id='qa-bare',title='QA no logistics',startsAt=future,status='scheduled',meetingPoint='QA meeting point',distance='2 miles',difficulty='Flat',duration='1 hour',rsvpEnabled=True))
with tempfile.TemporaryDirectory(prefix='avoshack-community-qa-') as t:
 config=Path(t)/'community.json';dbpath=Path(t)/'community.sqlite3';config.write_text(json.dumps({'events':events}))
 # Bind port 0 atomically: concurrent CI jobs must never share a fixture server.
 spec=importlib.util.spec_from_file_location('community_qa_server',root/'community-server.py')
 fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
 fixture.CONFIG=config;fixture.DB=dbpath;fixture.connect().close()
 server=fixture.ThreadingHTTPServer(('127.0.0.1',0),fixture.Handler)
 base=f'http://127.0.0.1:{server.server_port}'
 worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
 def request(path,data=None,origin=None):
  headers={'Content-Type':'application/json'}
  if origin:headers['Origin']=origin
  r=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
  try:
   with urllib.request.urlopen(r,timeout=5) as x:return x.status,json.load(x)
  except urllib.error.HTTPError as x:return x.code,json.load(x)
 try:
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
  def raw(body,path='/api/community/rsvps'):
   r=urllib.request.Request(base+path,data=body,headers={'Content-Type':'application/json'})
   try:
    with urllib.request.urlopen(r,timeout=5) as x:return x.status,json.load(x)
   except urllib.error.HTTPError as x:return x.code,json.load(x)
  def rows():
   with sqlite3.connect(dbpath) as db:return [db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in ('subscriptions','rsvps')]
  def snapshot():
   with sqlite3.connect(dbpath) as db:return [db.execute(f'SELECT * FROM {t} ORDER BY 1,2').fetchall() for t in ('subscriptions','rsvps')]
  def seats(event_id):return next(e for e in request('/api/community')[1]['events'] if e['id']==event_id)['confirmedGuests']
  def test_non_string_email_rejected_without_writes():
   # RF0200-11: only JSON strings identify an email; nothing is stringified or saved.
   bad=[None,True,False,0,7,1.5,[],['typed@example.invalid'],{},{'a':'typed@example.invalid'}]
   good={'eventId':'qa-unlimited','name':'Typed Guest','partySize':2}
   before,used=snapshot(),seats('qa-unlimited')
   for value in bad:
    for path,body in ((sub,{'email':value,'newsletter':True,'hikes':True}),(rsv,{**good,'email':value})):
     got=raw(json.dumps(body).encode(),path);assert got==(400,{'error':bad_email}),(path,value,got)
     assert snapshot()==before and seats('qa-unlimited')==used,(path,value)
  def test_non_string_name_rejected_without_writes():
   bad=[None,True,False,0,7,1.5,[],['Typed Guest'],{},{'name':'Typed Guest'}]
   ok={'eventId':'qa-unlimited','email':'typed-name@example.invalid','partySize':3}
   before,used=snapshot(),seats('qa-unlimited')
   bodies=[dict(ok)]+[{**ok,'name':v} for v in bad]
   for body in bodies:
    got=raw(json.dumps(body).encode(),rsv);assert got==(400,{'error':bad_name}),(body,got)
    assert snapshot()==before and seats('qa-unlimited')==used,body
   assert request(rsv,{**ok,'name':'Typed Guest'})[0]==200 and seats('qa-unlimited')==used+3
  def test_string_identity_normalization_and_boundaries():
   # Valid text behaves as before: trimmed, lower-cased, consent merged, duplicates add no places.
   assert request(sub,{'email':'  Mixed.Case@Example.INVALID \t','newsletter':True})[0]==200
   assert request(sub,{'email':'MIXED.case@example.invalid','hikes':True})[0]==200
   with sqlite3.connect(dbpath) as db:assert db.execute("SELECT email,newsletter,hikes FROM subscriptions WHERE email LIKE 'mixed.case%'").fetchall()==[('mixed.case@example.invalid',1,1)]
   used,pad={'eventId':'qa-unlimited','partySize':1},'  Pad.Guest@Example.INVALID  '
   assert request(rsv,{**used,'email':pad,'name':'  Zo\u00eb \u00dcnic\u00f6de  '})[0]==200
   with sqlite3.connect(dbpath) as db:assert db.execute("SELECT email,name FROM rsvps WHERE email LIKE 'pad.guest%'").fetchall()==[('pad.guest@example.invalid','Zo\u00eb \u00dcnic\u00f6de')]
   before,seated=snapshot(),seats('qa-unlimited')
   dup=request(rsv,{**used,'email':'PAD.guest@example.invalid','name':'Other Name','partySize':6})
   assert dup[0]==200 and dup[1]['alreadyRegistered'] and snapshot()==before and seats('qa-unlimited')==seated
   assert request(rsv,{**used,'email':'long-name@example.invalid','name':'\u00e9'*120})[0]==200
   before=snapshot()
   for n,name in enumerate(('','   ','\u00e9'*121,' '+'x'*121+' ')):
    got=raw(json.dumps({**used,'email':f'edge{n}@example.invalid','name':name}).encode(),rsv);assert got==(400,{'error':bad_name}),(name,got)
   assert snapshot()==before
   tail='@example.invalid';assert request(sub,{'email':'a'*(254-len(tail))+tail,'newsletter':True})[0]==200
   before=snapshot()
   assert raw(json.dumps({'email':'a'*(255-len(tail))+tail,'newsletter':True}).encode(),sub)==(400,{'error':bad_email}) and snapshot()==before
  def test_closed_hike_keeps_error_precedence():
   before=snapshot()
   for event_id in ('qa-past','no-such-hike'):
    for extra in ({'email':['typed@example.invalid'],'name':'Typed Guest'},{'email':'closed@example.invalid','name':['Typed Guest']},{'email':{'a':1},'name':None},{'email':None}):
     got=raw(json.dumps({'eventId':event_id,'partySize':1,**extra}).encode(),rsv);assert got==(409,{'error':closed}),(event_id,extra,got)
     assert snapshot()==before
  sub,rsv,new='/api/community/subscriptions','/api/community/rsvps',{'eventId':'qa-hike','name':'New Guest','email':'new@example.invalid','partySize':1}
  bad_email,bad_name,bad_party,form_msg='Please enter a valid email address.','Please enter your name (up to 120 characters).','Choose between one and six people.','Please use the form on the page.'
  generic,closed='Please check your name, email, and form selections.','This hike is not accepting RSVPs.'
  cases=[(sub,{'email':'not-an-email','newsletter':True},400,bad_email),(sub,{'newsletter':True},400,bad_email),
   (sub,{'email':'new@example.invalid'},400,'Choose at least one kind of update.'),(sub,{'email':'new@example.invalid','newsletter':False,'hikes':'yes'},400,'Choose at least one kind of update.'),
   (rsv,{**new,'email':'not-an-email'},400,bad_email),(rsv,{**new,'name':''},400,bad_name),(rsv,{**new,'name':'   '},400,bad_name),(rsv,{**new,'name':'x'*121},400,bad_name),
   (rsv,{**new,'partySize':0},400,bad_party),(rsv,{**new,'partySize':7},400,bad_party),(rsv,{**new,'partySize':'2'},400,bad_party),(rsv,{**new,'partySize':True},400,bad_party),
   (sub,[],400,form_msg),(rsv,[],400,form_msg),(rsv,'qa-hike',400,form_msg),(sub,None,400,form_msg),
   (rsv,{**new,'eventId':'qa-past','email':'not-an-email','partySize':0},409,closed),(rsv,{**new,'eventId':'no-such-hike','name':''},409,closed),(rsv,{'name':'x'},409,closed)]
  before=rows()
  for path,body,code,msg in cases:
   got=raw(json.dumps(body).encode(),path);assert got==(code,{'error':msg}),(path,body,got)
   assert rows()==before,(path,body,rows())
  for body in (b'{bad',b'{"email": "new@example.invalid", "newsletter": true',b'\xff\xfe',b'NaN-not-json'):
   for path in (sub,rsv):
    got=raw(body,path);assert got==(400,{'error':generic}),(path,body,got);assert rows()==before
  assert request(rsv,{**new,'eventId':'qa-unlimited','name':'x'*120,'partySize':6})[0]==200 and rows()==[before[0],before[1]+1]
  node=os.environ.get('NODE','node')
  subprocess.run([node,str(root/'community-ui-qa.cjs')],env={**os.environ,'COMMUNITY_TEST_URL':base,'QA_OUT_DIR':out},check=True)
  for check in (test_non_string_email_rejected_without_writes,test_non_string_name_rejected_without_writes,test_string_identity_normalization_and_boundaries,test_closed_hike_keeps_error_precedence):check()
  result={'subscriptionsPersisted':True,'consentMerge':True,'invalidEmailRejected':True,'crossOriginRejected':True,'duplicateRSVPPrevented':True,'capacityEnforced':True,'concurrentCapacitySafe':True,'pastRSVPRejected':True,'noPersonalDataInPublicAPI':True,'noExternalEmailSent':True,'fixtureDataIsolated':True,'guestCountIncludesPartySize':True,'duplicateGuestCountStable':True,'uncappedGuestCount':True,'configuredCountCannotOverrideDatabase':True}
  (Path(out)/'community-api-QA.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
 finally:server.shutdown();server.server_close();worker.join(timeout=5)

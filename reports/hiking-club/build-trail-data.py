"""Prepare reproducible public trail geometry. No visitor data or credentials."""
from pathlib import Path
import xml.etree.ElementTree as ET
import json,math,heapq,statistics
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[1]
raw_path=BASE/'map-sources/point-buchon-osm.xml'
raw=ET.parse(raw_path).getroot() if raw_path.exists() else None
saved=json.loads((BASE/'map-sources/osm-trail-subset.json').read_text()) if raw is None else None
nodes={e.attrib['id']:(float(e.attrib['lon']),float(e.attrib['lat'])) for e in raw.findall('node')} if raw is not None else saved['nodes']
def distance(a,b):
 x1,y1=map(math.radians,a);x2,y2=map(math.radians,b)
 return 6371000*2*math.asin(math.sqrt(math.sin((y2-y1)/2)**2+math.cos(y1)*math.cos(y2)*math.sin((x2-x1)/2)**2))
graph={};ways=[]
for e in raw.findall('way') if raw is not None else []:
 tags={t.attrib['k']:t.attrib['v'] for t in e.findall('tag')}
 if tags.get('name')!='Point Buchon Trail' and e.attrib['id'] not in ['308126320','308126321','308126322','308126323']:continue
 ids=[n.attrib['ref'] for n in e.findall('nd')];ways.append({'id':e.attrib['id'],'tags':tags,'nodes':ids})
if saved:ways=saved['ways']
for w in ways:
 ids=w['nodes']
 for a,b in zip(ids,ids[1:]):
  d=distance(nodes[a],nodes[b]);graph.setdefault(a,[]).append((d,b));graph.setdefault(b,[]).append((d,a))
start='4431152000';end='2063972669'
queue=[(0,start)];cost={start:0};previous={}
while queue:
 d,a=heapq.heappop(queue)
 if a==end:break
 if d!=cost[a]:continue
 for length,b in graph[a]:
  nd=d+length
  if nd<cost.get(b,float('inf')):cost[b]=nd;previous[b]=a;heapq.heappush(queue,(nd,b))
ids=[end]
while ids[-1]!=start:ids.append(previous[ids[-1]])
ids.reverse();route=[nodes[n] for n in ids]
cumulative=[0.]
for a,b in zip(route,route[1:]):cumulative.append(cumulative[-1]+distance(a,b))
# Uniform 50 m spacing, plus the exact endpoints; these are USGS sample locations.
sampled=[];j=1
for d in [i*50 for i in range(math.floor(cumulative[-1]/50)+1)]+[cumulative[-1]]:
 while j<len(cumulative)-1 and cumulative[j]<d:j+=1
 t=(d-cumulative[j-1])/(cumulative[j]-cumulative[j-1]);a,b=route[j-1:j+1]
 sampled.append([round(a[0]+(b[0]-a[0])*t,7),round(a[1]+(b[1]-a[1])*t,7),round(d,2)])
def merc(c):return [6378137*math.radians(c[0]),6378137*math.log(math.tan(math.pi/4+math.radians(c[1])/2))]
xy=[merc(p) for p in route];xs,ys=zip(*xy);cx=(min(xs)+max(xs))/2;cy=(min(ys)+max(ys))/2
height=(max(ys)-min(ys))*1.25;width=height*16/9
bounds=[cx-width/2,cy-height/2,cx+width/2,cy+height/2]
geo={'type':'Feature','properties':{'name':'Point Buchon Trail','source':'OpenStreetMap contributors','license':'ODbL 1.0','sourceUrl':'https://www.openstreetmap.org/copyright','wayIds':[w['id'] for w in ways],'from':'Coon Creek parking','to':'Trail turnaround beyond Windy Point','selection':'Pecho Valley Road walking approach from Coon Creek parking, then shortest connected Point Buchon Trail route; optional spurs excluded.','oneWayMeters':round(cumulative[-1],1)},'geometry':{'type':'LineString','coordinates':route}}
(BASE/'map-sources/point-buchon-route.geojson').write_text(json.dumps(geo,indent=2)+'\n')
(BASE/'map-sources/route-sampling.json').write_text(json.dumps({'samples':sampled,'bounds3857':bounds,'oneWayMeters':round(cumulative[-1],1)}))
# Retain only the bounded trail source subset and the nodes actually referenced.
needed={n for w in ways for n in w['nodes']}
(BASE/'map-sources/osm-trail-subset.json').write_text(json.dumps({'copyright':'© OpenStreetMap contributors, ODbL 1.0','downloaded':'2026-10-28','api':'https://api.openstreetmap.org/api/0.6/map?bbox=-120.925,35.215,-120.875,35.265','ways':ways,'nodes':{n:nodes[n] for n in needed}},indent=2))
print(json.dumps({'oneWayMiles':cumulative[-1]/1609.344,'roundTripMiles':2*cumulative[-1]/1609.344,'routePoints':len(route),'samples':len(sampled),'bounds3857':bounds},indent=2))

# Elevation comes from the USGS 3DEP getSamples response, not a drawn profile.
elev=json.loads((BASE/'map-sources/point-buchon-elevation.json').read_text())['samples']
elev=sorted(elev,key=lambda s:s['locationId'])
assert len(elev)==len(sampled)
for p,s in zip(sampled,elev):
 assert abs(p[0]-s['location']['x'])<.00001 and abs(p[1]-s['location']['y'])<.00001
z=[float(s['value']) for s in elev]
smooth=[z[0]]+[statistics.median(z[i-1:i+2]) for i in range(1,len(z)-1)]+[z[-1]]
outbound=[{'lon':p[0],'lat':p[1],'distanceMeters':p[2],'elevationMeters':round(h,3)} for p,h in zip(sampled,smooth)]
profile=outbound+[dict(p,distanceMeters=round(2*cumulative[-1]-p['distanceMeters'],2)) for p in outbound[-2::-1]]
gain=sum(max(0,b['elevationMeters']-a['elevationMeters']) for a,b in zip(profile,profile[1:]))
loss=sum(max(0,a['elevationMeters']-b['elevationMeters']) for a,b in zip(profile,profile[1:]))
data={'id':'point-buchon','name':'Point Buchon Trail','bounds3857':bounds,'coordinates':route,'profile':profile,
 'oneWayMeters':round(cumulative[-1],2),'distanceMeters':round(2*cumulative[-1],2),'gainMeters':round(gain,2),'lossMeters':round(loss,2),
 'maxElevationMeters':round(max(smooth),2),'minElevationMeters':round(min(smooth),2),
 'startLabel':'Coon Creek parking','endLabel':'Turnaround','routeCredit':'© OpenStreetMap contributors','routeLicense':'https://www.openstreetmap.org/copyright',
 'method':'OSM shortest connected named trail and parking approach, optional loop excluded. USGS 3DEP terrain sampled every 50 m with bilinear interpolation and a 3-point median filter; exact endpoints retained. Return follows the same path. Elevation is metres above sea level; cumulative gain/loss is an estimate and varies with sampling.',
 'imagery':'USGS The National Map / USDA NAIP aerial imagery, not live satellite imagery.',
 'sources':['https://api.openstreetmap.org/api/0.6/map?bbox=-120.925,35.215,-120.875,35.265','https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer','https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer','https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer','https://www.pge.com/en/about/in-your-community/recreational-areas.html']}
(ROOT/'storefront-mockup/assets/trails/point-buchon.json').write_text(json.dumps(data,separators=(',',':'))+'\n')

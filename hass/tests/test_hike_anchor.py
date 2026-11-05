"""AV1622-01: storefront-mockup/community.js gives each real hike card (upcoming, cancelled, completed) its event id as
an anchor, and /hike#<id> scrolls to and focuses that card once, after the club data has loaded. The real script runs
under node (vm sandbox, fixed clock, fixture club payload, fake DOM, no network); skipped when node is absent."""
import html, json, re, shutil, subprocess, unittest
from urllib.parse import unquote
from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "storefront-mockup"
NODE = shutil.which("node")
NOW = "2026-11-03T20:00:00Z"  # 12:00 Pacific
HARNESS = r"""
const fs=require('fs'),vm=require('vm'),[site,now,club,hash,staticIds,rsvp,preview]=JSON.parse(fs.readFileSync(0,'utf8'));
const el={'#upcoming-hikes':{innerHTML:''},'#past-hikes':{innerHTML:'',classList:{toggle(){}}},'#history-context':{textContent:''}};
const un=s=>s.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
const log={scroll:[],focus:[],tabindex:[]};
const card=id=>({id,scrollIntoView(o){log.scroll.push([id,o.block])},setAttribute(k,v){log.tabindex.push([id,k,v])},focus(o){log.focus.push([id,o.preventScroll])}});
const cards=()=>[...(el['#upcoming-hikes'].innerHTML+el['#past-hikes'].innerHTML).matchAll(/<(?:article|details) id="([^"]*)" class="(?:hike-event|past-hike)/g)].map(m=>card(un(m[1])));
const form={elements:{name:{value:'A'},email:{value:'a@b.c'},partySize:{value:'1'}},querySelector:()=>({textContent:'',disabled:false}),getAttribute:()=>null,reset(){}};
const ctx=vm.createContext({TextEncoder,location:{origin:'https://club.example',hash},
 $:s=>el[s]||null,
 show(){el['#hike-rsvp']=form},
 document:{querySelector:()=>null,querySelectorAll:s=>s==='[id]'?staticIds.map(id=>({id})):cards()},
 fetch:async(u,o)=>u==='/api/community'?{ok:true,headers:{get:h=>h.toLowerCase()==='content-type'?'application/json':null},json:async()=>club}
  :u==='/hiking-preview.json'&&preview?{ok:true,json:async()=>preview}
  :o&&o.method==='POST'?{ok:true,headers:{get:()=>'application/json'},json:async()=>({message:'saved'})}:{ok:false,headers:{get:()=>null}}});ctx.window=ctx;
vm.runInContext(`{const R=Date,N=Date.parse('${now}');Date=class extends R{constructor(...a){super(...(a.length?a:[N]))}static now(){return N}}}`,ctx);
vm.runInContext(fs.readFileSync(site+'/script.js','utf8').split('\n')[0],ctx);
let thrown=null;
try{vm.runInContext(fs.readFileSync(site+'/community.js','utf8'),ctx)}catch(e){thrown=String(e)}
setTimeout(async()=>{
 if(rsvp&&el['#upcoming-hikes'].onclick){
  el['#upcoming-hikes'].onclick({target:{closest:()=>({dataset:{rsvp}})}});
  if(form.onsubmit)await form.onsubmit({preventDefault(){},currentTarget:form});
  await new Promise(r=>setTimeout(r,100));
 }
 process.stdout.write(JSON.stringify({up:el['#upcoming-hikes'].innerHTML,past:el['#past-hikes'].innerHTML,log,thrown}));
},100);
"""


def hike(id, startsAt="2026-12-05T09:00:00-08:00", status="scheduled", **kw):
    return dict(id=id, title=kw.pop("title", "Hike " + str(id)), startsAt=startsAt, status=status,
                meetingPoint="North lot", rsvpOpen=kw.pop("rsvpOpen", False), **kw)


@unittest.skipUnless(NODE, "node is required to run community.js")
class HikeAnchorTest(unittest.TestCase):
    def run_page(self, events, hash="", static=("upcoming-hikes", "past-hikes", "hike-updates"), rsvp=None, preview=None, **club):
        club = dict(dict(routeIdeas=[], acceptsSubmissions=True), events=list(events), **club)
        p = subprocess.run([NODE, "-e", HARNESS], input=json.dumps([str(SITE), NOW, club, hash, list(static), rsvp, preview]),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertIsNone(out["thrown"])
        self.assertNotIn("calendar isn’t available", out["up"])  # render() completed
        return out

    def ids(self, markup, tag):
        return [html.unescape(i) for i in re.findall(r"<%s id=\"([^\"]*)\"" % tag, markup)]

    def test_card_id_and_ics_url_unchanged(self):
        out = self.run_page([hike("spring-1", title="Spring")])
        self.assertEqual(self.ids(out["up"], "article"), ["spring-1"])
        self.assertIn('<article id="spring-1" class="hike-event">', out["up"])
        href = html.unescape(re.search(r'hike-ics" download="[^"]*" href="([^"]*)"', out["up"]).group(1))
        self.assertIn("URL:https://club.example/hike#spring-1\r\n", unquote(href.split(",", 1)[1]))

    def test_odd_id_escaped_and_found_by_hash_malformed_hash_does_nothing(self):
        weird = 'a b&"x'
        out = self.run_page([hike(weird)], hash="#a%20b%26%22x")
        self.assertIn('<article id="a b&amp;&quot;x" class', out["up"])
        self.assertEqual(out["log"]["scroll"], [[weird, "start"]])
        out = self.run_page([hike(weird)], hash="#%E0%A4")  # malformed escape: no action, no throw
        self.assertEqual(out["log"], {"scroll": [], "focus": [], "tabindex": []})

    def test_static_empty_and_duplicate_ids_get_no_anchor(self):
        out = self.run_page([hike("hike-updates", title="Static clash"), hike("", title="Empty"),
                             hike("dup", "2026-12-06T09:00:00-08:00"), hike("dup", "2026-12-07T09:00:00-08:00")],
                            hash="#hike-updates")
        self.assertEqual(self.ids(out["up"], "article"), ["dup"])
        self.assertEqual(out["up"].count("<article "), 4)
        self.assertEqual(out["log"]["scroll"], [])  # a static id is left to the browser's own jump

    def test_hash_scrolls_and_focuses_once_unknown_hash_does_nothing(self):
        out = self.run_page([hike("spring-1"), hike("other", "2026-12-06T09:00:00-08:00")], hash="#spring-1")
        self.assertEqual(out["log"], {"scroll": [["spring-1", "start"]], "focus": [["spring-1", True]],
                                      "tabindex": [["spring-1", "tabindex", "-1"]]})
        out = self.run_page([hike("spring-1")], hash="#nope")
        self.assertEqual(out["log"], {"scroll": [], "focus": [], "tabindex": []})
        out = self.run_page([hike("spring-1")], hash="")
        self.assertEqual(out["log"]["scroll"], [])

    def test_rsvp_rerender_does_not_scroll_again(self):
        out = self.run_page([hike("spring-1", rsvpOpen=True, remaining=3)], hash="#spring-1", rsvp="spring-1")
        self.assertEqual(out["log"]["scroll"], [["spring-1", "start"]])
        self.assertEqual(len(out["log"]["focus"]), 1)
        self.assertIn('id="spring-1"', out["up"])  # the card was redrawn with its anchor

    def test_cancelled_and_completed_anchored_sample_never(self):
        # cancelled and completed hikes
        out = self.run_page([hike("cx", status="cancelled"), hike("done", "2026-10-01T09:00:00-07:00", status="completed")],
                            hash="#done")
        self.assertEqual(self.ids(out["up"], "article"), ["cx"])
        self.assertIn('<article id="cx" class="hike-event hike-cancelled">', out["up"])
        self.assertEqual(self.ids(out["past"], "details"), ["done"])
        self.assertEqual(out["log"]["scroll"], [["done", "start"]])
        # with no real hikes the sample invitation and archive are drawn without any anchor
        trail = {"id": "t1", "title": "T", "place": "P", "distance": "1", "difficulty": "e", "elevationLabel": "Up",
                 "elevation": "1", "duration": "1", "description": "d", "sourceUrl": "https://example.org"}
        sample = {"enabled": True, "upcoming": {"id": "sample-up", "trailId": "t1", "startsAt": "2026-12-01T09:00:00-08:00",
                                                "meetTime": "8", "walkTime": "9", "returnTime": "NOON", "bring": "x",
                                                "meetingPoint": "p", "meetingAddress": "a", "accessNote": "n",
                                                "invitation": "i"},
                  "past": [{"id": "sample-past", "trailId": "t1", "dateLabel": "May"}]}
        out = self.run_page([], hash="#sample-up", preview=sample, routeIdeas=[trail])
        self.assertIn("trail-invitation", out["up"])
        self.assertIn("trail-journal-entry", out["past"])
        self.assertNotIn(' id="sample-', out["up"] + out["past"])
        self.assertEqual(out["log"]["scroll"], [])


if __name__ == "__main__":
    unittest.main()

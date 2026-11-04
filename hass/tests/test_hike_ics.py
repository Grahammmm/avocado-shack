"""AV1322-09: storefront-mockup/community.js renders an "Add to calendar" .ics link for an upcoming scheduled hike
only. The real script runs under node (vm sandbox, fixed clock, fixture club payload, no network, no browser);
skipped when node is absent. Each case reads the rendered #upcoming-hikes HTML and decodes the data: href.
The stubbed fetch answers like a real Response (ok, headers.get, json), because liveData() inspects Content-Type.
A stub missing headers makes liveData() throw, so render() shows its fallback and every assertion below is moot."""
import html, json, re, shutil, subprocess, unittest, urllib.parse
from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "storefront-mockup"
NODE = shutil.which("node")
NOW = "2026-11-03T20:00:00Z"  # 12:00 Pacific
HARNESS = r"""
const fs=require('fs'),vm=require('vm'),[site,now,club]=JSON.parse(fs.readFileSync(0,'utf8'));
const el={'#upcoming-hikes':{innerHTML:''},'#past-hikes':{innerHTML:'',classList:{toggle(){}}},'#history-context':{textContent:''}};
const ctx=vm.createContext({TextEncoder,location:{origin:'https://club.example'},$:s=>el[s]||null,document:{querySelector:()=>null},
 fetch:async u=>u==='/api/community'?{ok:true,headers:{get:h=>h.toLowerCase()==='content-type'?'application/json':null},json:async()=>club}:{ok:false,headers:{get:()=>null}}});ctx.window=ctx;
vm.runInContext(`{const R=Date,N=Date.parse('${now}');Date=class extends R{constructor(...a){super(...(a.length?a:[N]))}static now(){return N}}}`,ctx);
vm.runInContext(fs.readFileSync(site+'/script.js','utf8').split('\n')[0],ctx);
vm.runInContext(fs.readFileSync(site+'/community.js','utf8'),ctx);
setTimeout(()=>process.stdout.write(el['#upcoming-hikes'].innerHTML),100);
"""
LINK = re.compile(r'<a class="text-link hike-ics" download="([^"]*)" href="([^"]*)">Add to calendar</a>')
LONG = ("Sunrise ridge walk to the old lighthouse, café stop, tide pools; " * 2)[:120]


def hike(id, startsAt, status="scheduled", **kw):
    return dict(id=id, title=kw.pop("title", "Hike " + id), startsAt=startsAt, status=status,
                meetingPoint=kw.pop("meetingPoint", "North lot"), rsvpOpen=False, **kw)


@unittest.skipUnless(NODE, "node is required to run community.js")
class HikeIcsTest(unittest.TestCase):
    def render(self, *events):
        club = {"events": list(events), "routeIdeas": []}
        out = subprocess.run([NODE, "-e", HARNESS], input=json.dumps([str(SITE), NOW, club]),
                             capture_output=True, text=True, timeout=60, check=True).stdout
        self.assertNotIn("calendar isn’t available", out)  # render() completed
        cards = {}
        for art in out.split("<article ")[1:]:
            title = html.unescape(re.search(r"<h3>(.*?)</h3>", art).group(1))
            links = LINK.findall(art)
            cards[title] = [(d, urllib.parse.unquote(html.unescape(h).split(",", 1)[1])) for d, h in links]
        return cards

    def ics(self, event):
        (download, text), = self.render(event)[event["title"]]
        self.assertEqual(download, event["id"] + ".ics")
        self.assertTrue(text.endswith("\r\n") and all(len(l.encode()) <= 75 for l in text.split("\r\n")), text)
        return text, text.replace("\r\n ", "").split("\r\n")

    def test_upcoming_hike_utc_start_and_fields(self):
        text, lines = self.ics(hike("winter", "2026-12-05T09:00:00-08:00", title="Winter walk"))
        self.assertEqual(lines[:4], ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Avocado Shack//Hiking Club//EN",
                                     "BEGIN:VEVENT"])
        for want in ("UID:winter@avocadoshack", "DTSTAMP:20261205T170000Z", "DTSTART:20261205T170000Z",
                     "DURATION:PT2H", "SUMMARY:Winter walk", "LOCATION:North lot",
                     "URL:https://club.example/hike#winter", "END:VEVENT", "END:VCALENDAR"):
            self.assertIn(want, lines)
        _, lines = self.ics(hike("autumn", "2027-10-09T09:00:00-07:00"))
        self.assertIn("DTSTART:20271009T160000Z", lines)

    def test_text_escaped_and_control_characters_dropped(self):
        _, lines = self.ics(hike("esc", "2026-12-05T09:00:00-08:00", title="Hike; bring water, snacks\\ & hats",
                                 meetingPoint="North lot\nGate 2\r\nby the\tsign"))
        self.assertIn("SUMMARY:Hike\\; bring water\\, snacks\\\\ & hats", lines)
        self.assertIn("LOCATION:North lot\\nGate 2\\nby thesign", lines)

    def test_long_title_folds_and_unfolds(self):
        text, lines = self.ics(hike("long", "2026-12-05T09:00:00-08:00", title=LONG))
        self.assertIn("\r\n ", text)
        self.assertIn("SUMMARY:" + LONG.replace(",", "\\,").replace(";", "\\;"), lines)

    def test_cancelled_completed_started_and_unparseable_get_none(self):
        cards = self.render(hike("up", "2026-12-05T09:00:00-08:00", title="Upcoming"),
                            hike("cx", "2026-12-06T09:00:00-08:00", "cancelled", title="Gone"),
                            hike("done", "2026-12-07T09:00:00-08:00", "completed", title="Done"),
                            hike("today", "2026-11-03T11:00:00-08:00", title="Started"),
                            hike("bad", "not-a-date", title="Bad date"))
        self.assertEqual(len(cards["Upcoming"]), 1)
        self.assertEqual(cards["Cancelled: Gone"], [])
        self.assertEqual(cards["Started"], [])  # listed as Today, already started: no link
        self.assertEqual(set(cards), {"Upcoming", "Cancelled: Gone", "Started"})


if __name__ == "__main__":
    unittest.main()

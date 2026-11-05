"""AV1322-09: storefront-mockup/community.js renders an "Add to calendar" .ics link for an upcoming scheduled hike
only. The real script runs under node (vm sandbox, fixed clock, fixture club payload, no network, no browser);
skipped when node is absent. Each case reads the rendered #upcoming-hikes HTML and decodes the data: href.
The stubbed fetch answers like a real Response (ok, headers.get, json), because liveData() inspects Content-Type.
A stub missing headers makes liveData() throw, so render() shows its fallback and every assertion below is moot."""
import html, json, os, re, shutil, subprocess, unittest, urllib.parse
from pathlib import Path

SITE = Path(__file__).resolve().parents[2] / "storefront-mockup"
NODE = shutil.which("node")
NOW = "2026-11-03T20:00:00Z"  # 12:00 Pacific
HARNESS = r"""
const fs=require('fs'),vm=require('vm'),[site,now,club]=JSON.parse(fs.readFileSync(0,'utf8'));
const el={'#upcoming-hikes':{innerHTML:''},'#past-hikes':{innerHTML:'',classList:{toggle(){}}},'#history-context':{textContent:''}};
const ctx=vm.createContext({TextEncoder,location:{origin:'https://club.example'},$:s=>el[s]||null,document:{querySelector:()=>null,querySelectorAll:()=>[]},
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
    def render(self, *events, tz=None):
        club = {"events": list(events), "routeIdeas": []}
        env = dict(os.environ, TZ=tz) if tz else None
        out = subprocess.run([NODE, "-e", HARNESS], input=json.dumps([str(SITE), NOW, club]),
                             capture_output=True, text=True, timeout=60, check=True, env=env).stdout
        self.assertNotIn("calendar isn’t available", out)  # render() completed
        cards = {}
        for art in out.split("<article ")[1:]:
            title = html.unescape(re.search(r"<h2>(.*?)</h2>", art).group(1))
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

    def test_no_detail_fields_leave_file_unchanged(self):
        text, lines = self.ics(hike("plain", "2026-12-05T09:00:00-08:00", title="Plain"))
        self.assertEqual([l for l in lines if l.startswith(("LOCATION", "DESCRIPTION"))], ["LOCATION:North lot"])
        self.assertEqual(lines[4:], ["UID:plain@avocadoshack", "DTSTAMP:20261205T170000Z", "DTSTART:20261205T170000Z",
                                     "DURATION:PT2H", "SUMMARY:Plain", "LOCATION:North lot",
                                     "URL:https://club.example/hike#plain", "END:VEVENT", "END:VCALENDAR", ""])
        _, lines = self.ics(hike("blank", "2026-12-05T09:00:00-08:00", meetingAddress="  ", meetTime="", bring=None, accessNote=" "))
        self.assertNotIn("DESCRIPTION", "".join(l[:11] for l in lines))
        self.assertIn("LOCATION:North lot", lines)

    def test_address_follows_meeting_point_and_folds(self):
        _, lines = self.ics(hike("addr", "2026-12-05T09:00:00-08:00", meetingAddress="123 Example St, Cayucos CA"))
        self.assertIn("LOCATION:North lot\\, 123 Example St\\, Cayucos CA", lines)
        long = "125 Example Street, " + "Cayucos California " * 5
        text, lines = self.ics(hike("addr2", "2026-12-05T09:00:00-08:00", meetingAddress=long))
        self.assertIn("\r\n ", text)
        self.assertIn("LOCATION:" + ("North lot, " + long).replace(",", "\\,"), lines)

    def test_address_without_meeting_point_is_location_alone(self):
        _, lines = self.ics(hike("only", "2026-12-05T09:00:00-08:00", meetingPoint="", meetingAddress="123 Example St"))
        self.assertIn("LOCATION:123 Example St", lines)

    def test_description_parts_in_order_and_position(self):
        _, lines = self.ics(hike("b", "2026-12-05T09:00:00-08:00", bring="water"))
        self.assertIn("DESCRIPTION:Bring: water", lines)
        _, lines = self.ics(hike("all", "2026-12-05T09:00:00-08:00", accessNote="Gate code at lot", bring="water", meetTime="8:30 AM"))
        self.assertIn("DESCRIPTION:Meet: 8:30 AM\\nBring: water\\nAccess: Gate code at lot", lines)
        i = [l.split(":")[0] for l in lines]
        self.assertEqual(i.index("DESCRIPTION"), i.index("LOCATION") + 1)
        self.assertEqual(i.index("URL"), i.index("DESCRIPTION") + 1)
        self.assertEqual(lines.count("DURATION:PT2H"), 1)
        self.assertNotIn("DTEND", i)

    def test_description_text_escaped_and_control_dropped(self):
        _, lines = self.ics(hike("e", "2026-12-05T09:00:00-08:00", accessNote="Dirt road; 4\\4, line\r\nnext\x07end"))
        self.assertIn("DESCRIPTION:Access: Dirt road\\; 4\\\\4\\, line\\nnextend", lines)

    def test_description_multibyte_folds_on_octets(self):
        note = "Café stop 🥑 " * 12
        text, lines = self.ics(hike("mb", "2026-12-05T09:00:00-08:00", accessNote=note))
        self.assertIn("\r\n ", text)
        self.assertIn("DESCRIPTION:Access: " + note, lines)

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

    def test_naive_start_never_offers_calendar_in_any_host_zone(self):
        for tz in ("UTC", "Asia/Tokyo"):
            cards = self.render(hike("n", "2026-12-05T09:00:00", title="Naive", timezone="America/Los_Angeles"), tz=tz)
            self.assertEqual(cards.get("Naive", []), [], tz)

    def test_explicit_zones_produce_host_independent_instants(self):
        want = {"A": "20261205T170000Z", "B": "20270805T160000Z", "C": "20261205T090000Z",
                "D": "20261206T020000Z", "E": "20261205T170030Z"}
        evs = [hike("A", "2026-12-05T09:00-08:00", title="A"), hike("B", "2027-08-05T09:00:00-07:00", title="B"),
               hike("C", "2026-12-05T09:00:00Z", title="C"), hike("D", "2026-12-05T18:00:00-08:00", title="D"),
               hike("E", "2026-12-05T09:00:30-08:00", title="E")]
        for tz in ("UTC", "Asia/Tokyo"):
            cards = self.render(*evs, tz=tz)
            for k, v in want.items():
                (_, text), = cards[k]
                self.assertIn("\r\nDTSTART:" + v + "\r\n", text, (tz, k))

    def test_calendar_start_shape_refusals(self):
        bad = ["2026-12-05", "2026-12-05 09:00:00-08:00", "2026-12-05T09:00:00", "2026-12-05T09:00:00-0800",
               " 2026-12-05T09:00:00Z", "2026-12-05T09:00:00Z ", "2026-12-05T09:00:00Z\n", "2026-12-05T09:00:00.5Z",
               "2026-12-05T09:00:00z", None, 1796461200000, "garbage"]
        evs = [hike("b%d" % i, v, title="Bad%d" % i) for i, v in enumerate(bad)]
        cards = self.render(*evs, hike("ok", "2026-12-05T09:00:00Z", title="Good"))
        self.assertEqual(len(cards["Good"]), 1)
        for i in range(len(bad)):
            self.assertEqual(cards.get("Bad%d" % i, []), [], repr(bad[i]))

    def test_status_and_start_boundary_unchanged(self):
        cards = self.render(hike("now", "2026-11-03T12:00:00-08:00", title="Equal"),
                            hike("past", "2026-11-03T11:59:00-08:00", title="Past"),
                            hike("fut", "2026-11-03T12:00:01-08:00", title="Future"))
        self.assertEqual(cards.get("Equal", []), [])
        self.assertEqual(cards.get("Past", []), [])
        self.assertEqual(len(cards["Future"]), 1)


if __name__ == "__main__":
    unittest.main()

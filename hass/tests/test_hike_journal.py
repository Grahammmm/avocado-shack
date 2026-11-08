"""AV1622-03: a real completed hike renders as a trail-journal entry (same markup as the sample archive), keeping its
AV1622-01 anchor. Runs the real community.js under node with the AV1622-01 harness (fixed clock, fake DOM, no network)."""
import json, re, subprocess, unittest

from hass.tests.test_hike_anchor import HARNESS as BASE_HARNESS, NODE, NOW, SITE, hike

HARNESS = BASE_HARNESS.replace("vm.createContext({TextEncoder,", "vm.createContext({TextEncoder,URL,")  # route() validates sourceUrl with URL
assert HARNESS != BASE_HARNESS

TRAIL = {"id": "t1", "title": "Route Title", "place": "Montaña Shore", "distance": "5 miles", "difficulty": "Moderate",
         "elevationLabel": "Climb", "elevation": "400 ft", "duration": "3 hours", "description": "route blurb",
         "sourceUrl": "https://example.org/trail"}
DONE = "2026-10-03T09:00:00-07:00"


def done(id, startsAt=DONE, **kw):
    return {**hike(id, startsAt, status="completed"), **kw}


@unittest.skipUnless(NODE, "node is required to run community.js")
class HikeJournalTest(unittest.TestCase):
    def page(self, events, hash="", preview=None, routes=(TRAIL,), **club):
        club = dict(dict(routeIdeas=list(routes), acceptsSubmissions=True), events=list(events), **club)
        p = subprocess.run([NODE, "-e", HARNESS], input=json.dumps([str(SITE), NOW, club, hash, ["upcoming-hikes", "past-hikes"], None, preview]),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        self.assertIsNone(out["thrown"])
        return out

    def entries(self, out):
        return re.findall(r"<article [^>]*class=\"trail-journal-entry\">.*?</article>", out["past"])

    def test_completed_linked_journal(self):
        out = self.page([done("done-1", title="Our Day", recap="We went.", trailId="t1", meetingPoint="North lot")], hash="#done-1")
        (entry,) = self.entries(out)
        self.assertNotIn("<details", out["past"])
        self.assertIn('<article id="done-1" class="trail-journal-entry">', entry)
        self.assertIn("<h3>Our Day</h3>", entry)  # the event title, never the route's
        self.assertNotIn("Route Title", entry)
        self.assertIn('<p class="trail-journal-recap">We went.</p>', entry)
        self.assertIn('Montaña Shore <span>· <time datetime="2026-10-03T09:00:00-07:00">October 2026</time></span>', entry)
        for want in ("<dt>Distance</dt><dd>5 miles</dd>", "<dt>Difficulty</dt><dd>Moderate</dd>", "<dt>Climb</dt><dd>400 ft</dd>", "<dt>Allow</dt><dd>3 hours</dd>"):
            self.assertIn(want, entry)
        self.assertIn('href="https://example.org/trail" target="_blank" rel="noopener">Explore this trail', entry)
        self.assertEqual(out["log"]["scroll"], [["done-1", "start"]])  # AV1622-01 anchor still focuses it

    def test_without_or_unknown_route_uses_event_fields(self):
        evs = [done("a", "2026-10-03T09:00:00-07:00", title="None", distance="2 mi", difficulty="Easy", duration="1 h", recap="r"),
               done("b", "2026-10-02T09:00:00-07:00", title="Unknown", trailId="nope", distance="3 mi"),
               done("c", "2026-10-01T09:00:00-07:00", title="Hidden", trailId="hidden-idea")]
        out = self.page(evs)
        a, b, c = self.entries(out)
        self.assertIn("North lot <span>·", a)
        self.assertIn("<dt>Distance</dt><dd>2 mi</dd>", a)
        self.assertIn("<dt>Difficulty</dt><dd>Easy</dd>", a)
        self.assertIn("<dt>Allow</dt><dd>1 h</dd>", a)
        self.assertIn("<dt>Distance</dt><dd>3 mi</dd>", b)
        self.assertNotIn("<dt>Difficulty", b)
        self.assertNotIn("trail-journal-stats", c)
        for e in (a, b, c):
            self.assertNotIn("Montaña", e)
            self.assertNotIn("Explore this trail", e)
            self.assertNotIn("Climb", e)

    def test_recap_and_title_are_escaped(self):
        out = self.page([done("x", title='A "q" <b>[t]</b>', recap='<img src=x onerror=alert(1)> & "r"', trailId="t1")])
        (entry,) = self.entries(out)
        self.assertNotIn("<b>", entry)
        self.assertNotIn("<img", entry)
        self.assertIn("A &quot;q&quot; &lt;b&gt;[t]&lt;/b&gt;", entry)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt; &amp; &quot;r&quot;", entry)

    def test_missing_stats_and_unsafe_link(self):
        bare = dict(TRAIL, id="bare", elevation="", duration=None, sourceUrl="https://example.org/ok")
        bare.pop("elevationLabel")
        routes = [bare] + [dict(TRAIL, id=i, sourceUrl=u) for i, u in (("http", "http://example.org/x"), ("js", "javascript:alert(1)"), ("bad", "not a url"))]
        evs = [done("e%d" % n, "2026-10-0%dT09:00:00-07:00" % (9 - n), title="T%d" % n, trailId=t) for n, t in enumerate(("bare", "http", "js", "bad"))]
        out = self.page(evs, routes=routes)
        bare_e, *unsafe = self.entries(out)
        self.assertNotIn("Climb", bare_e)
        self.assertNotIn("Elevation", bare_e)
        self.assertNotIn("<dt>Allow", bare_e)
        self.assertIn('href="https://example.org/ok"', bare_e)
        for e in unsafe:
            self.assertNotIn("<a ", e)
        self.assertNotRegex(out["past"], r'href="(?:http:|javascript:)')

    def test_real_history_suppresses_samples(self):
        sample = {"enabled": True, "upcoming": {"id": "su", "trailId": "t1", "startsAt": "2026-12-01T09:00:00-08:00", "meetTime": "8",
                  "walkTime": "9", "returnTime": "NOON", "bring": "x", "meetingPoint": "p", "meetingAddress": "a", "accessNote": "n", "invitation": "i"},
                  "past": [{"id": "sp", "trailId": "t1", "dateLabel": "May"}]}
        real = self.page([done("r1", title="Real one")], preview=sample)
        self.assertIn("Real one", real["past"])
        self.assertNotIn("route blurb", real["past"])
        self.assertEqual(len(self.entries(real)), 1)
        for other in (hike("sch"), hike("can", status="cancelled")):
            out = self.page([other], preview=sample)  # scheduled/cancelled are not history: samples come back
            self.assertIn("route blurb", out["past"])
            self.assertEqual(len(self.entries(out)), 1)
        off = self.page([], preview=dict(sample, enabled=False))
        self.assertIn("history-empty", off["past"])
        self.assertNotIn("trail-journal-entry", off["past"])

    def test_order_and_anchor_retained(self):
        evs = [done("old", "2026-09-01T09:00:00-07:00", title="Older"), done("new", "2026-10-20T09:00:00-07:00", title="Newer"),
               done("upcoming-hikes", "2026-10-10T09:00:00-07:00", title="Static clash"), done("new", "2026-10-11T09:00:00-07:00", title="Dup"),
               hike("sched", "2026-12-05T09:00:00-08:00")]
        out = self.page(evs, hash="#old")
        titles = re.findall(r"<h3>([^<]*)</h3>", out["past"])
        self.assertEqual(titles, ["Newer", "Dup", "Static clash", "Older"])
        self.assertEqual(re.findall(r'<article id="([^"]*)"', out["past"]), ["new", "old"])  # static and duplicate ids get none
        self.assertEqual(out["log"]["scroll"], [["old", "start"]])
        self.assertEqual(len(out["log"]["focus"]), 1)
        self.assertNotIn("hike-ics", out["past"])
        self.assertNotIn("data-rsvp", out["past"])
        self.assertEqual(self.page([done("d")], hash="#nope")["log"]["scroll"], [])


if __name__ == "__main__":
    unittest.main()

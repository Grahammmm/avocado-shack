"""AV1052-06 (H13/H17): `listing store` replies what the site shows for the store (effective defaults, plain text) from the
saved writer content; read-only, works while paused. Fixture content only.
Run: python3 -B -m unittest hass.tests.test_listing_store -v
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from hass import conversation
from hass.content_model import DEFAULT_HEADLINE, DEFAULT_INTRO, DEFAULT_STORY
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

HEAD = "This is from my saved copy, not a live look at the website:"
UNAVAILABLE = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"
BASE = [HEAD, "Store", "Address: 2190 Main Street · Morro Bay", "Hours:", "- Monday–Friday 9am–6pm", "- Saturday 9am–5pm · Closed Sunday"]
PHOTO = "assets/products/photo-0123456789abcdef.jpg"
ALT = 'Crate of "Hass" avocados & lemons'


class ListingStoreTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "listing store reached the interpreter/editor"))
        self.path = self.repo.wt / "hass" / "content" / "store.json"

    def put(self, **fields):
        doc = json.loads(self.path.read_text("utf-8"))
        for k, v in fields.items():
            if v is None: doc.pop(k, None)
            else: doc[k] = v
        self.path.write_text(json.dumps(doc), "utf-8")

    def store(self, text="listing store"):
        n = self.n
        self.assertEqual(self.say(text), "listing")
        self.assertEqual(self.disposition(f"m{n + 1}"), "listing")
        [reply] = self.replies()
        return reply.splitlines()

    # Contract: the reply is the site's effective words in the fixed order. Bug caught: blank optional fields, HTML-escaped
    # text, a phone line when none is saved, or a missing/misplaced shelf-check line.
    def test_store_fields_follow_site_defaults_and_order(self):
        self.assertEqual(self.store(), BASE + [f"Intro: {DEFAULT_INTRO}", f"Headline: {DEFAULT_HEADLINE[0]}", DEFAULT_HEADLINE[1],
                                               "Story: " + DEFAULT_STORY[:80] + "…", "Home photo: the shop's own photo", "Shelf check: not done yet"])
        self.put(phone="8055550123", intro="Fish & chips - fresh!", headline=["Hello & welcome.", "Come in."], story="A short story from the shop floor.",
                 selection_checked_on="2026-11-02")
        lines = self.store()
        self.assertEqual(lines[:6], BASE)
        self.assertEqual(lines[6:], ["Phone: (805) 555-0123", "Intro: Fish & chips - fresh!", "Headline: Hello & welcome.", "Come in.",
                                     "Story: A short story from the shop floor.", "Home photo: the shop's own photo",
                                     "Selection last checked by Michael on Monday, November 2."])
        after = self.path.read_text("utf-8")  # the command writes nothing
        self.store()
        self.assertEqual(self.path.read_text("utf-8"), after)

    # Contract: Story is exactly value[:80] in characters (not bytes), "…" only when longer. Bug caught: off-by-one, byte cut, ellipsis inside the 80.
    def test_story_79_80_81_unicode(self):
        for n, tail in ((79, ""), (80, ""), (81, "…")):
            story = "é" * (n - 1) + "😀"
            self.put(story=story)
            self.assertEqual(next(l for l in self.store() if l.startswith("Story: ")), "Story: " + story[:80] + tail, n)

    # Contract: owner photo shows its description only; default says so; clearing restores it. Bug caught: leaking the file path.
    def test_home_photo_owner_default_and_clear(self):
        self.put(homeImage={"image": PHOTO, "imageAlt": ALT})
        lines = self.store()
        self.assertIn(f"Home photo: yours - {ALT}", lines)
        self.assertNotIn("photo-0123456789abcdef", "\n".join(lines))
        self.put(homeImage=None)
        self.assertIn("Home photo: the shop's own photo", self.store())

    # Contract: the notice line is the shared status/report formatter (scheduled/active/ended); no notice, no line. Pacific day, not UTC.
    def test_notice_legacy_scheduled_active_ended(self):
        self.assertFalse([l for l in self.store() if l.startswith("Home notice")])
        self.put(notice={"text": "Closed Thanksgiving Day", "until": "2026-11-26"})
        want = "Home notice: Closed Thanksgiving Day - through Thursday, November 26"
        self.assertEqual(self.store()[-2], want)
        self.assertEqual(self.status_notice(), want)
        self.put(notice={"text": "Closed Thanksgiving Day", "from": "2026-11-20", "until": "2026-11-26"})
        self.assertEqual(self.store()[-2], "Home notice: Closed Thanksgiving Day - from Friday, November 20 through Thursday, November 26; not shown yet")
        self.now = datetime(2026, 11, 27, 7, 30, tzinfo=timezone.utc)  # 23:30 PST on the 26th: last day, still shown
        self.assertEqual(self.store()[-2], "Home notice: Closed Thanksgiving Day - from Friday, November 20 through Thursday, November 26")
        self.now = datetime(2026, 11, 27, 8, 30, tzinfo=timezone.utc)  # 00:30 PST on the 27th: ended
        self.assertEqual(self.store()[-2], "Home notice: Closed Thanksgiving Day - from Friday, November 20 through Thursday, November 26; no longer shown")

    def status_notice(self):
        self.assertEqual(self.say("status"), "status")
        return next(l for l in self.replies()[0].splitlines() if l.startswith("Home notice"))

    # Contract: the shelf-check sentence is the site's, stale after 7 days, with the phone when set. Bug caught: day-7/day-8 off-by-one.
    def test_shelf_check_absent_fresh_stale_phone(self):
        self.put(selection_checked_on="2026-11-02", phone="8055550123")
        self.now = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)  # day 7
        self.assertEqual(self.store()[-1], "Selection last checked by Michael on Monday, November 2.")
        self.now = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)  # day 8
        self.assertEqual(self.store()[-1], "Selection last checked by Michael on Monday, November 2 (more than a week ago - call (805) 555-0123 or visit to confirm).")
        self.put(phone=None)
        self.assertEqual(self.store()[-1], "Selection last checked by Michael on Monday, November 2 (more than a week ago - call or visit to confirm).")

    # Contract: only the whole word `store` is this branch and it beats an id named store; other ids keep working.
    def test_store_reserved_dispatch_preserves_other_listing_ids(self):
        self.assertEqual(self.store("LISTING Store!")[:2], [HEAD, "Store"])
        self.assertEqual(conversation.read_command("listing store?"), ("listing", "store"))
        self.assertEqual(verb("listing store"), "listing")
        cdir = self.repo.wt / "hass" / "content"
        doc = json.loads((cdir / "makers.json").read_text("utf-8"))
        doc["makers"]["store"] = {"name": "Store Co", "place": "Cayucos", "story": "A story.", "url": "https://example.com/"}
        (cdir / "makers.json").write_text(json.dumps(doc), "utf-8")
        self.assertEqual(self.store("listing store")[1], "Store")
        pid = json.loads((cdir / "products.json").read_text("utf-8"))["products"][0]["id"]
        n = self.n
        self.assertEqual(self.say(f"listing {pid}"), "listing")
        self.assertEqual(self.replies()[0].splitlines()[:2], [HEAD, "Name: Hass avocado"])
        self.assertEqual(self.store("listing storefront"), ["I don't know that one. Try find and a word from its name."])
        self.assertEqual(self.store("listing store hours please"), ["I don't know that one. Try find and a word from its name."])  # AV1052-07: a name, never the store branch or the interpreter
        self.assertEqual(self.calls, [])

    # Contract: read-only and fail-closed. Bug caught: a draft expired/changed by the listing, a partial reply on bad content.
    def test_listing_store_is_read_only_and_fails_closed(self):
        draft, _reply = self.propose("hours")
        self.calls.clear()
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        tables = self.tables()
        self.now = T0 + timedelta(seconds=601)  # the draft has lapsed; only a later non-read-only message sweeps it
        self.assertEqual(self.store()[:2], [HEAD, "Store"])
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.editor.applies, self.tables()), ("proposed", 0, 0, tables))
        self.say("listing store", pid="dup1")
        self.assertEqual(len(self.replies()), 1)
        self.say("listing store", pid="dup1")
        self.assertEqual(self.replies(), [])
        self.say("listing store", sender="stranger@example.com", pid="s1")
        self.assertEqual(self.replies(), [])
        for bad in ({"phone": "123"}, {"intro": "bad<b>"}, {"notice": {"text": "x", "until": "nonsense"}}, {"selection_checked_on": "not-a-date"}):
            good = self.path.read_text("utf-8")
            self.put(**bad)
            self.assertEqual(self.store(), [UNAVAILABLE], bad)
            self.path.write_text(good, "utf-8")
        self.path.write_text("{not json", "utf-8")
        self.assertEqual(self.store(), [UNAVAILABLE])


if __name__ == "__main__":
    unittest.main()

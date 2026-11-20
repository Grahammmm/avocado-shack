"""AV2137-08 (F07/SHOP-1): `post` warns first when the card shows Sold out or Limited; the draft and photo are unchanged.
Run: python3 -B -m unittest hass.tests.test_post_availability -v
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from datetime import date, datetime, timezone
from types import SimpleNamespace

from hass import social_draft
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_post_command import PostTests, WARNING
from hass.tests.test_status_pause import StoreMixin

STOCK = "The website shows {name} as {word} (checked {day}). A post now may send people in for something that is not on the shelf."
HEAD = "Here's a post you can copy. I haven't posted anything."


def content(**product):
    record = {"id": "p1", "name": "Loaf", "description": "Fresh.", "image": "assets/products/p1.webp", "status": "active",
              "category": "bread", **product}
    return SimpleNamespace(products=[record], makers={}, store={"selection_checked_on": "2026-11-02"})


class BuildAvailabilityTests(unittest.TestCase):
    """The word is the card's (sitegen rule), for the injected shop day; refusals carry no key."""

    def shown(self, today, **product):
        site = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, site)
        (site / "assets" / "products").mkdir(parents=True)
        (site / "assets" / "products" / "p1.webp").write_bytes(b"x")
        out = social_draft.build(content(**product), "p1", site, today=today)
        return out.get("availability", "ABSENT") if out["draft"] else out

    def test_word_is_the_card_label_for_the_given_day(self):
        mon, tue = date(2026, 11, 2), date(2026, 11, 3)
        for product, today, want in (
                (dict(available="no", available_on="2026-11-02"), mon, "Sold out"),
                (dict(available="limited", available_on="2026-11-02"), tue, "Limited"),
                (dict(available="yes", available_on="2026-11-02"), mon, "Available today"),
                (dict(available="no", available_on="2026-11-02"), date(2026, 11, 9), "Sold out"),  # day 7 still current
                (dict(available="no", available_on="2026-11-02"), date(2026, 11, 10), "Last confirmed Monday, November 2"),  # day 8
                (dict(available="no", available_on="2026-11-09"), mon, None),  # own day in the future: no word
                (dict(available="maybe", available_on="2026-11-02"), mon, None),
                (dict(), mon, None)):
            with self.subTest(product=product, today=today):
                self.assertEqual(self.shown(today, **product), want)

    def test_refusal_has_no_availability_key(self):
        out = social_draft.build(content(status="held", available="no", available_on="2026-11-02"), "p1", today=date(2026, 11, 2))
        self.assertEqual(out, {"draft": False, "reason": "not on the site"})

    def test_cli_prints_the_word_for_the_injected_clock(self):
        import contextlib, io
        from hass.tests import test_social_draft as base
        seen = {}
        for now, want in (("2026-11-03T20:00:00+00:00", "Sold out"), ("2026-11-10T20:00:00+00:00", "Last confirmed Monday, November 2")):
            tc = base.SocialDraftTests()
            tc.setUp()
            self.addCleanup(tc.tearDown) if hasattr(tc, "tearDown") else None
            tc.load({"id": "p1", "name": "Loaf", "description": "Fresh.", "image": "assets/products/p1.webp", "status": "active",
                     "category": "bread", "available": "no", "available_on": "2026-11-02"})
            store = tc.root / "content" / "store.json"
            doc = json.loads(store.read_text("utf-8"))
            doc["selection_checked_on"] = "2026-11-02"
            store.write_text(json.dumps(doc), "utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                social_draft.main(["p1", "--now", now], tc.root / "content", tc.site)
            seen[now] = json.loads(out.getvalue()).get("availability")
            self.assertEqual(seen[now], want)


class PostAvailabilityTests(StoreMixin, ConversationTestCase):
    """Integrated: borrows PostTests' fixture and `post` without subclassing, so its tests are not rerun here."""

    post = PostTests.post

    def setUp(self):
        super().setUp()
        self.site = self.repo.wt / "storefront-mockup"
        PostTests.fixture(self)

    def mark(self, index, word, on, checked="2026-11-02"):
        base = self.repo.wt / "hass" / "content"
        doc = json.loads((base / "products.json").read_text("utf-8"))
        doc["products"][index].update(available=word, available_on=on)
        (base / "products.json").write_text(json.dumps(doc), "utf-8")
        store = json.loads((base / "store.json").read_text("utf-8"))
        store["selection_checked_on"] = checked
        (base / "store.json").write_text(json.dumps(store), "utf-8")
        return doc["products"][index]["name"]

    def body(self, index):
        from hass.content_model import load_content
        want = social_draft.build(load_content(self.repo.wt / "hass" / "content"), self.ids[index], self.site)
        return f"{HEAD}\n{want['caption']}\nWhat the photo shows: {want['alt']}"

    def test_sold_out_and_limited_warn_between_illustration_line_and_body(self):
        for word, shown in (("no", "Sold out"), ("limited", "Limited")):
            with self.subTest(word=word):
                name = self.mark(0, word, "2026-11-02")
                text, files = self.post(f"post {self.ids[0]}")
                notice = STOCK.format(name=name, word=shown, day="Monday, November 2")
                self.assertEqual(text, f"{WARNING}\n{notice}\n{self.body(0)}")
                self.assertEqual([Path(path).resolve() for path in files], [(self.site / "post-test" / "real.jpg").resolve()])
                self.assertEqual((self.drafts(), self.commits(), self.approvals()), ([], 0, 0))

    def test_name_post_gets_the_same_reply_as_the_id(self):
        name = self.mark(0, "no", "2026-11-02")
        by_id = self.post(f"post {self.ids[0]}")
        self.assertEqual(self.post(f"post {name}"), by_id)
        self.assertIn("Sold out", by_id[0])

    def test_owner_photo_gets_only_the_stock_line(self):
        import re
        from unittest import mock
        name = self.mark(0, "no", "2026-11-02")
        owner = mock.patch.object(social_draft, "HOME_IMAGE_RE", re.compile(r"post-test/real\.jpg"))
        owner.start()
        self.addCleanup(owner.stop)
        text, _ = self.post(f"post {self.ids[0]}")
        self.assertEqual(text, f"{STOCK.format(name=name, word='Sold out', day='Monday, November 2')}\n{self.body(0)}")

    def test_other_words_and_no_word_get_no_line(self):
        for word, on in (("yes", "2026-11-02"), ("no", "2026-10-20"), ("limited", None), (None, None)):
            with self.subTest(word=word, on=on):
                if word is None:
                    base = self.repo.wt / "hass" / "content"
                    doc = json.loads((base / "products.json").read_text("utf-8"))
                    doc["products"][0].pop("available", None), doc["products"][0].pop("available_on", None)
                    (base / "products.json").write_text(json.dumps(doc), "utf-8")
                elif on is None:
                    continue  # available_on is required with a word; covered by the content model
                else:
                    self.mark(0, word, on, checked="2026-10-19" if on == "2026-10-20" else "2026-11-02")
                text, _ = self.post(f"post {self.ids[0]}")
                self.assertEqual(text, f"{WARNING}\n{self.body(0)}")

    def test_refusals_never_carry_the_line(self):
        for index in (2, 3, 1, 5):  # held, hidden, missing photo, symlinked photo
            self.mark(index, "no", "2026-11-02")
            text, files = self.post(f"post {self.ids[index]}")
            self.assertNotIn("not on the shelf", text)
            self.assertEqual(files, [])


if __name__ == "__main__":
    unittest.main()

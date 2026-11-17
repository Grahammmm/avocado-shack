"""RF0500-13: `listing <id>` resolves an exact saved id/key across all four kinds before any name/title fallback.
Fixture content only; read-only.
Run: python3 -B -m unittest hass.tests.test_listing_exact_identity -v
"""

import json
import unittest

from hass.tests import test_listing_command as base
from hass.tests.test_conversation import ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

EVENT = {"title": "Synthetic ridge outing", "startsAt": "2026-11-14T09:00:00-08:00", "timezone": "America/Los_Angeles",
         "status": "scheduled"}


class ExactIdentityTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "listing reached the interpreter/editor"))
        self.cdir = self.repo.wt / "hass" / "content"

    # fixture helpers shared with the existing listing tests (functions only, so its tests are not re-run here)
    edit = base.ListingTests.edit
    product = base.ListingTests.product
    pid = base.ListingTests.pid
    listing = base.ListingTests.listing
    fields = base.ListingTests.fields
    maker_key = base.ListingTests.maker_key

    def add_event(self, ident, **over):
        self.edit("community.json", lambda doc: doc["events"].append(dict(EVENT, id=ident, **over)))

    def test_exact_hike_id_beats_product_name(self):
        self.product(self.pid(), name="zzshadow")
        self.add_event("zzshadow")
        head, f = self.fields("zzshadow")
        self.assertEqual((head, f["Title"]), ("Synthetic ridge outing", "Synthetic ridge outing"))
        self.assertNotIn("Maker", f)
        self.assertEqual(self.fields("Synthetic ridge outing")[1], f)  # the title control reads the same record

    def test_exact_route_id_beats_product_name(self):
        rid = json.loads((self.cdir / "community.json").read_text("utf-8"))["routeIdeas"][0]["id"]
        self.product(self.pid(), name=rid)
        head, f = self.fields(rid)
        self.assertIn("Place", f)
        self.assertNotIn("Maker", f)

    def test_exact_maker_key_beats_product_name_and_hike_title(self):
        key = self.maker_key()
        self.product(self.pid(), name=key)
        self.add_event("zz-other", title=key)
        head, f = self.fields(key)
        self.assertNotIn("Availability", f)
        self.assertNotIn("Starts", f)

    def test_exact_product_id_is_not_reinterpreted_as_hike_title(self):
        pid = self.pid()
        self.add_event("zz-event", title=pid)
        head, f = self.fields(pid)
        self.assertIn("Availability", f)
        self.assertNotIn("Starts", f)

    def test_cross_kind_collision_still_refuses_with_shadowing_name(self):
        pid = self.pid()
        self.add_event(pid)
        self.assertEqual(self.listing(pid), [base.MANY])

    def test_no_exact_match_keeps_fallbacks(self):
        self.assertEqual(self.listing("no-such-id"), [base.NONE])
        self.assertEqual(self.listing(self.pid().upper()), [base.NONE])  # ids are not folded
        self.add_event("zz-event")
        self.assertEqual(self.fields("Synthetic ridge outing")[0], "Synthetic ridge outing")
        self.add_event("zz-event-2")
        self.assertEqual(self.listing("Synthetic ridge outing"), [base.NONE])  # two titles: still no guess


if __name__ == "__main__":
    unittest.main()

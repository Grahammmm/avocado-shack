"""RF0440-10 tests: store.confirm_selection is all-or-nothing. A later missing, hidden or held product refuses the
whole check and leaves the supplied Content untouched (direct registered-op calls, not via the editor, which
discards its working copy anyway).
Run: python3 -B -m unittest hass.tests.test_selection_refusal_atomic -v
"""

import copy
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass.content_model import Content
from hass.ops import NotFound, OpContext, Refused, load_registry

NOW = datetime(2026, 11, 2, 20, tzinfo=timezone.utc)  # midday Pacific, 2026-11-02
HELD = {"reason": "test concern", "source": "test source"}


def content(*extra, first=None, store=None):
    products = [dict({"id": "test-good", "name": "Test fruit", "status": "active"}, **(first or {})),
                {"id": "test-same", "name": "Test same", "status": "active"}]
    products += [dict(p) for p in extra]
    return Content(products=products, makers={}, community={}, store=dict(store or {}))


def apply(c, args, now=NOW):
    return load_registry()["store.confirm_selection"].apply(c, args, OpContext(now, Path("."), {}))


class AtomicRefusalTests(unittest.TestCase):
    def assertUnchanged(self, c, args, kind, now=NOW, text=None):
        before, ids = copy.deepcopy(c), [id(p) for p in c.products]
        out = apply(c, args, now)
        self.assertIsInstance(out, kind)
        if text:
            self.assertIn(text, str(out.__dict__))
        self.assertEqual(c, before, "refusal must leave the whole content unchanged")
        self.assertEqual([id(p) for p in c.products], ids)

    def test_later_missing_hidden_or_held_leaves_full_content_unchanged(self):
        cases = (("missing", NotFound, None, "test-bad"),
                 ("hidden", Refused, None, "hidden"),
                 ("held", Refused, HELD, "test concern"))
        for status, kind, hold, text in cases:
            for first in (None, {"available": "no", "available_on": "2026-10-30"}):
                with self.subTest(status=status, first=first):
                    extra = [] if status == "missing" else [{"id": "test-bad", "name": "Bad", "status": status,
                                                              **({"hold": hold} if hold else {})}]
                    self.assertUnchanged(content(*extra, first=first), {"yes": ["test-good", "test-bad"]}, kind,
                                         text=text)

    def test_refusal_is_atomic_across_all_availability_lists(self):
        bad = {"id": "test-bad", "name": "Bad", "status": "hidden"}
        for args in ({"yes": ["test-good"], "limited": ["test-bad"]},
                     {"yes": ["test-good"], "limited": ["test-same"], "no": ["test-bad"]},
                     {"no": ["test-bad", "test-good"]}):
            with self.subTest(args=args):
                self.assertUnchanged(content(bad), args, Refused)

    def test_first_failure_precedence_and_duplicate_date_guards(self):
        hidden = {"id": "test-hid", "name": "Hid", "status": "hidden"}
        held = {"id": "test-held", "name": "Held", "status": "held", "hold": HELD}
        self.assertUnchanged(content(hidden, held), {"yes": ["test-good", "test-hid", "test-held"]}, Refused,
                             text="test-hid is hidden")
        self.assertUnchanged(content(hidden, held), {"yes": ["test-good", "test-held", "test-hid"]}, Refused,
                             text="test concern")
        self.assertUnchanged(content(hidden), {"yes": ["test-good", "test-nope", "test-good"]}, Refused,
                             text="listed twice")
        self.assertUnchanged(content(hidden), {"yes": ["test-good", "test-hid"], "date": "2026-11-03"}, Refused,
                             text="future")
        self.assertUnchanged(content(hidden), {"yes": ["test-good", "test-hid"], "date": "2026-10-01"}, Refused,
                             text="days ago")
        self.assertUnchanged(content(hidden, store={"selection_checked_on": "2026-11-02"}),
                             {"yes": ["test-good", "test-hid"], "date": "2026-11-01"}, Refused, text="already checked")

    def test_success_keeps_touch_order_and_dates(self):
        c = content(first={"available": "yes", "available_on": "2026-11-02"}, store={})
        first = c.products[0]
        out = apply(c, {"yes": ["test-good"], "limited": ["test-same"]})
        self.assertEqual([(t.collection, t.key) for t in out][1:], [("products", "test-same")])
        self.assertEqual(out[0].collection, "store")
        self.assertIs(c.products[0], first)
        self.assertEqual((c.products[1]["available"], c.products[1]["available_on"]), ("limited", "2026-11-02"))
        self.assertEqual(c.store["selection_checked_on"], "2026-11-02")
        self.assertEqual(out[1].before, {"id": "test-same", "name": "Test same", "status": "active"})

    def test_empty_selection_and_noop_behavior_unchanged(self):
        c = content()
        self.assertTrue(apply(c, {}))
        self.assertEqual(c.store["selection_checked_on"], "2026-11-02")
        self.assertUnchanged(c, {}, Refused, text="nothing to change")


if __name__ == "__main__":
    unittest.main()

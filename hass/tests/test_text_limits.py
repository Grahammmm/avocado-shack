"""AV1537-05 tests: content text fields have maximum lengths (content_model.TEXT_LIMITS), checked by the validator.

Validator cases run on an in-memory copy of the real content; op cases run the production editor on a throwaway
writer repo (test_editor.WriterRepo). Nothing touches the checkout, the live service or its database.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import copy
import unittest
from datetime import datetime, timedelta, timezone

from hass.content_model import (CATEGORIES, CONTENT_DIR, EVENT_TEXT_FIELDS, MAX_ADDRESS_PART, MAX_HOURS_LINE,
                                TEXT_LIMITS, ContentError, load_and_validate, load_content, validate)
from hass.tests.test_catalog_ops import CatalogRepo, _req
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeRepo

EVENT = {"id": "hike-2026-12-05-limits", "title": "Limits hike", "startsAt": "2026-12-05T09:00:00-08:00",
         "timezone": "America/Los_Angeles", "status": "completed", **{f: "x" for f in EVENT_TEXT_FIELDS}}


def _content():
    """Real content plus one event carrying every event text field, and an imageAlt on the first product."""
    content = load_content(CONTENT_DIR)
    content.community["events"] = [copy.deepcopy(EVENT)]
    content.products[0]["imageAlt"] = "x"
    return content


def _problems(content):
    try:
        validate(content, None)
    except ContentError as exc:
        return exc.problems
    return []


def _targets(content):
    """(group, field) -> (record, where prefix) for one record of each kind."""
    product, (maker_key, maker) = content.products[0], next(iter(content.makers.items()))
    records = {"product": (product, f"product {product['id']}"), "maker": (maker, f"maker {maker_key!r}"),
               "event": (content.community["events"][0], "events[0]"),
               "routeIdea": (content.community["routeIdeas"][0], "routeIdeas[0]"),
               "club": (content.community["club"], "community.club")}
    return {(g, f): records[g] for g in records for f in TEXT_LIMITS[g]}


def _longest(content):
    """(group, field) -> longest current string value of that field in the real content."""
    groups = {"product": content.products, "maker": list(content.makers.values()),
              "event": content.community["events"], "routeIdea": content.community["routeIdeas"],
              "club": [content.community["club"]], "store": [content.store]}
    out = {}
    for group, recs in groups.items():
        for field in TEXT_LIMITS[group]:
            values = [r.get(field) for r in recs] if field != "hoursLine" else content.store["hours"]
            out[(group, field)] = max((len(v) for v in values if isinstance(v, str)), default=0)
    return out


class ValidatorLimitTests(unittest.TestCase):
    def test_every_field_at_and_over_its_limit(self):
        base = _content()
        self.assertEqual(_problems(base), [])
        for (group, field), _ in _targets(base).items():
            if field == "category":
                continue  # only CATEGORIES values are valid; over-length is checked below
            limit = TEXT_LIMITS[group][field]
            for size, expected in ((limit, []), (limit + 1, ["{where}.%s: longer than %d characters" % (field, limit)])):
                with self.subTest(group=group, field=field, size=size):
                    content = copy.deepcopy(base)
                    rec, where = _targets(content)[(group, field)]
                    rec[field] = "a" * size
                    self.assertEqual(_problems(content), [e.format(where=where) for e in expected])

    def test_category_over_limit_is_one_named_problem(self):
        content = _content()
        content.products[0]["category"] = "a" * (TEXT_LIMITS["product"]["category"] + 1)
        self.assertEqual(_problems(content), [f"product {content.products[0]['id']}.category: longer than 40 characters"])

    def test_code_points_are_counted_and_image_alt_message_kept(self):
        content = _content()
        pid = content.products[0]["id"]
        content.products[0]["name"] = "e\u0301" * 40  # 40 accented letters written as 80 code points: at the limit
        self.assertEqual(_problems(content), [])
        content.products[0]["name"] += "a"
        self.assertEqual(_problems(content), [f"product {pid}.name: longer than 80 characters"])
        content = _content()
        content.products[0]["imageAlt"] = "a" * 201
        self.assertEqual(_problems(content), [f"product {pid}.imageAlt: longer than 200 characters"])

    def test_real_content_validates_with_headroom(self):
        load_and_validate()
        content = load_content(CONTENT_DIR)
        longest = _longest(content)
        self.assertGreater(longest[("product", "description")], 100)  # the scan reads the real values
        for (group, field), length in longest.items():
            with self.subTest(group=group, field=field):
                self.assertGreaterEqual(TEXT_LIMITS[group][field], 1.5 * length)
        self.assertGreaterEqual(TEXT_LIMITS["product"]["category"], 1.5 * max(map(len, CATEGORIES)))
        self.assertEqual(TEXT_LIMITS["store"], {"streetAddress": MAX_ADDRESS_PART, "town": MAX_ADDRESS_PART,
                                                "hoursLine": MAX_HOURS_LINE})


class OpLimitTests(unittest.TestCase):
    def repo(self, cls):
        repo = cls()
        self.addCleanup(repo.cleanup)
        return repo

    def assertInvalid(self, repo, field, *ops):
        head, drafts = repo.head(), repo.drafts()
        result = repo.prepare(_req(*ops))
        self.assertEqual(result["result"], "invalid", result)
        self.assertTrue(any(f".{field}: longer than" in p for p in result["problems"]), result["problems"])
        self.assertEqual((repo.head(), repo.drafts()), (head, drafts))  # no draft file, no commit

    def test_product_edit_description(self):
        repo = self.repo(CatalogRepo)
        self.assertInvalid(repo, "description", ("product.edit", {"id": "photo-product-001", "description": "a" * 601}))
        repo.run(("product.edit", {"id": "photo-product-001", "description": "a" * 600}))

    def assertRefusedLong(self, repo, reason, *ops):
        head, drafts = repo.head(), repo.drafts()
        result = repo.prepare(_req(*ops))
        self.assertEqual((result["result"], result.get("reason")), ("refused", reason), result)
        self.assertEqual((repo.head(), repo.drafts()), (head, drafts))  # no draft file, no commit

    def test_hike_create_title_and_complete_recap(self):
        repo = self.repo(HikeRepo)
        self.assertRefusedLong(repo, "title is longer than 80 characters", ("hike.create", {**HIKE, "title": "a" * 81}))
        repo.run(("hike.create", HIKE))
        repo.now = datetime(2026, 12, 5, 12, 0, tzinfo=timezone(timedelta(hours=-8)))
        self.assertRefusedLong(repo, "recap is longer than 2000 characters",
                               ("hike.complete", {"id": HIKE_ID, "recap": "a" * 2001}))
        repo.run(("hike.complete", {"id": HIKE_ID, "recap": "a" * 2000}))
        self.assertEqual(repo.event()["status"], "completed")


if __name__ == "__main__":
    unittest.main()

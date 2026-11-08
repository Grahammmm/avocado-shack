"""AVO-SPECIALS-1: weekly specials (store.specials, hass/specials.py, hass/ops/specials.py).

Ops run through editor.prepare + apply on a throwaway repo (test_store_ops.StoreRepo); the browser tests need
PLAYWRIGHT_MODULE. Run: python3 -m unittest hass.tests.test_specials -v
"""

import copy, json, os, re, subprocess, tempfile, unittest  # noqa: E401
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from hass import claims, live_policy, preview, sitegen, specials
from hass.content_model import REPO_ROOT, active_specials, load_content, shop_today, validate_store
from hass.ops import OpContext, Refused, load_registry
from hass.tests.test_store_ops import INDEX, REVERT, StoreTestCase, _req

ADD, EDIT, REMOVE, CLEAR = "specials.add", "specials.edit", "specials.remove", "specials.clear_expired"
CONTENT = load_content()
STORE = CONTENT.store
PRODUCT = CONTENT.active_products()[0]


def day(offset):
    return (shop_today() + timedelta(days=offset)).isoformat()


def special(n=1, start=-1, end=3, **extra):
    return {"id": f"sp-{n}", "title": f"Special {n}", "deal": f"{n} for $5", "start": day(start), "end": day(end), "order": n, **extra}


def problems(*items, store=STORE, ids=None):
    out = []
    validate_store(out, {**store, "specials": list(items)}, product_ids=ids or {PRODUCT["id"]})
    return out


def page(*items, today=None):
    content = copy.deepcopy(CONTENT)
    content.store["specials"] = list(items)
    return sitegen.render(content, today=today)[INDEX].decode("utf-8")


def result(repo, op, args):
    out = repo.prepare(_req((op, args)))
    return out["result"], out.get("reason")


class ModelTests(unittest.TestCase):
    def test_no_specials_is_valid_and_the_saved_page_is_unchanged(self):
        self.assertNotIn("specials", STORE)
        self.assertEqual(problems(), [])
        self.assertEqual(sitegen.main(["--check"]), 0)
        self.assertEqual(sitegen.render(CONTENT)[INDEX], (REPO_ROOT / INDEX).read_bytes())

    def test_a_good_special_and_every_optional_field(self):
        self.assertEqual(problems(special(), special(2, product=PRODUCT["id"], picture=True)), [])

    def test_end_date_is_required_and_not_before_start(self):
        no_end = {k: v for k, v in special().items() if k != "end"}
        self.assertTrue(any("missing field 'end'" in p for p in problems(no_end)))
        self.assertTrue(any("before the start date" in p for p in problems(special(start=2, end=1))))
        self.assertEqual(problems(special(start=2, end=2)), [])  # a one-day special
        self.assertTrue(any("must be a real date" in p for p in problems({**special(), "end": "2026-02-30"})))
        self.assertTrue(any("longer than 31 days" in p for p in problems(special(start=0, end=31))))

    def test_text_rules_no_html_links_contact_or_title_price(self):
        for field, bad in [("title", "<b>Sale</b>"), ("deal", "2 for <i>5</i>"), ("deal", "see www.example.com"),
                           ("deal", "visit shop.com now"), ("deal", "Visit example.dev for details"), ("title", "Visit example.edu for details"), ("deal", "http://x.org"), ("deal", "mail me@shack.example"),
                           ("deal", "call 805 555 0123"), ("deal", "call 8055550123"), ("title", "Eggs $3"),
                           ("title", "!!"), ("deal", "a" * 61), ("title", "a" * 61), ("title", "Two\nlines"),
                           ("deal", "&lt;b&gt;"), ("title", " padded"), ("deal", "x {{y}} z")]:
            with self.subTest(field=field, bad=bad):
                self.assertTrue(problems({**special(), field: bad}), (field, bad))
        for good in ("2 for $5", "Free sample Saturday", "$3.50 a bunch", "Buy 2, get 1 free", "Salt & pepper deal"):
            self.assertEqual(problems({**special(), "deal": good}), [], good)
        self.assertEqual(problems({**special(), "deal": "a" * 60, "title": "b" * 60}), [])

    def test_product_must_exist_and_picture_needs_a_product(self):
        self.assertTrue(any("not a product" in p for p in problems(special(product="no-such-thing"))))
        self.assertTrue(any("picture" in p for p in problems(special(picture=True))))
        self.assertTrue(any("picture" in p for p in problems(special(product=PRODUCT["id"], picture=False))))

    def test_shape_unknown_fields_ids_and_order(self):
        for bad in ({**special(), "price": 5}, {**special(), "id": "Bad Id"}, {**special(), "order": 100},
                    {**special(), "order": "1"}, {**special(), "order": True}, "text", None):
            with self.subTest(bad=bad):
                self.assertTrue(problems(bad))
        self.assertTrue(any("duplicate id" in p for p in problems(special(), special())))
        self.assertTrue(validate_problems_for("nope"))

    def test_at_most_six_active_at_once_and_expired_do_not_count(self):
        six = [special(n) for n in range(1, 7)]
        self.assertEqual(problems(*six), [])
        self.assertTrue(any("more than 6" in p for p in problems(*six, special(7))))
        old = [special(n, start=-10, end=-5) for n in range(7, 12)]
        self.assertEqual(problems(*six, *old), [])  # expired ones are kept without trouble
        later = special(7, start=10, end=12)  # starts after the six end: never more than six at once
        self.assertEqual(problems(*[special(n, end=3) for n in range(1, 7)], later), [])
        self.assertTrue(any("more than 6" in p for p in problems(*six, special(7, start=2, end=6))))  # overlaps from day 2
        self.assertTrue(any("at most 20" in p for p in problems(*[special(n, start=-40, end=-39) for n in range(21)])))

    def test_active_rule_edges_and_pacific_midnight(self):
        sp = {**special(), "start": "2026-11-10", "end": "2026-11-12"}
        store = {"specials": [sp]}
        for d, shown in ((date(2026, 11, 9), 0), (date(2026, 11, 10), 1), (date(2026, 11, 12), 1), (date(2026, 11, 13), 0)):
            self.assertEqual(len(active_specials(store, d)), shown, d)
        # 23:30 PST on the 12th is 07:30Z on the 13th: still the last day; 00:30 PST on the 13th is gone
        for utc, shown in ((datetime(2026, 11, 13, 7, 30, tzinfo=timezone.utc), 1), (datetime(2026, 11, 13, 8, 30, tzinfo=timezone.utc), 0)):
            self.assertEqual(len(active_specials(store, shop_today(utc))), shown, utc)
        # PDT: 23:30 PDT on 4 July is 06:30Z on the 5th
        store = {"specials": [{**sp, "start": "2026-07-01", "end": "2026-07-04"}]}
        self.assertEqual(len(active_specials(store, shop_today(datetime(2026, 7, 5, 6, 30, tzinfo=timezone.utc)))), 1)
        self.assertEqual(len(active_specials(store, shop_today(datetime(2026, 7, 5, 7, 30, tzinfo=timezone.utc)))), 0)


def validate_problems_for(value):
    out = []
    validate_store(out, {**STORE, "specials": value})
    return out


class RenderTests(unittest.TestCase):
    def test_zero_active_renders_nothing_at_all(self):
        for items in ((), (special(end=-1, start=-5),), (special(start=2, end=4),)):
            text = page(*items)
            self.assertEqual(text.encode(), (REPO_ROOT / INDEX).read_bytes(), items)
            for word in ("weekly-specials", "specials-heading", "This week", "SPECIALS_JS", "data-end"):
                self.assertNotIn(word, text)

    def test_one_special_section_sits_at_the_top_of_the_page_with_its_script(self):
        text = page(special(1, deal="2 for $5", title="Fresh strawberries"))
        self.assertEqual(text.count('class="weekly-specials"'), 1)
        self.assertEqual(text.count("This week’s specials"), 1)
        self.assertLess(text.index("weekly-specials"), text.index('class="hero"'))
        self.assertEqual(text.count(specials.SPECIALS_JS + "</body>"), 1)
        self.assertIn('<p class="special-deal">2 for $5</p>', text)
        self.assertEqual(text.count("<li data-start="), 1)
        self.assertIn("<h3>Fresh strawberries</h3>", text)
        self.assertIn(f'data-start="{day(-1)}" data-end="{day(3)}"', text)

    def test_deal_line_is_shown_exactly_as_typed_and_escaped(self):
        text = page({**special(), "deal": "2 for $5 & Free sample Saturday", "title": "Fish & chips"})
        self.assertIn('<p class="special-deal">2 for $5 &amp; Free sample Saturday</p>', text)
        self.assertIn("<h3>Fish &amp; chips</h3>", text)

    def test_six_specials_in_order_and_sort_ties_by_title(self):
        items = [special(n, order=10 - n) for n in range(1, 7)]
        text = page(*items)
        self.assertEqual(text.count("<li data-start="), 6)
        self.assertEqual(re.findall(r"<h3>(Special \d)</h3>", text), [f"Special {n}" for n in range(6, 0, -1)])

    def test_expired_special_never_renders_even_if_left_in_the_file(self):
        text = page(special(1, start=-9, end=-1), special(2))
        self.assertNotIn("Special 1", text)
        self.assertIn("Special 2", text)

    def test_end_day_shows_and_next_day_is_gone_in_the_generated_page(self):
        sp = {**special(), "start": "2026-11-10", "end": "2026-11-12"}
        self.assertIn("Special 1", page(sp, today=date(2026, 11, 12)))
        self.assertNotIn("weekly-specials", page(sp, today=date(2026, 11, 13)))
        self.assertNotIn("weekly-specials", page(sp, today=date(2026, 11, 9)))

    def test_picture_reuse_uses_the_products_own_picture_only_when_active(self):
        text = page(special(product=PRODUCT["id"], picture=True))
        self.assertIn(f'<img class="special-image" src="{PRODUCT["image"]}"', text)
        self.assertIn(f'href="?item={PRODUCT["id"]}#market"', text)
        self.assertNotIn("special-image", page(special(product=PRODUCT["id"])))  # linked, no picture asked for
        content = copy.deepcopy(CONTENT)
        content.products = [dict(p, status="hidden") if p["id"] == PRODUCT["id"] else p for p in content.products]
        content.store["specials"] = [special(product=PRODUCT["id"], picture=True)]
        hidden = sitegen.render(content)[INDEX].decode()
        self.assertNotIn("special-image", hidden)
        self.assertNotIn("?item=", hidden.split('class="hero"')[0])
        self.assertIn("Special 1", hidden)

    def test_no_price_field_and_no_price_outside_the_deal_line(self):
        text = page(special(deal="Free sample Saturday"))
        section = text[text.index("weekly-specials"):text.index('class="hero"')]
        self.assertNotIn("$", section)
        before = (REPO_ROOT / INDEX).read_text("utf-8")
        self.assertNotRegex(before, r"\$\s?\d")  # the site shows no prices today

    def test_publish_includes_the_section_and_script(self):
        content = copy.deepcopy(CONTENT)
        content.store["specials"] = [special(product=PRODUCT["id"], picture=True)]
        files = sitegen.publish_files(content, REPO_ROOT)
        self.assertIn(b"weekly-specials", files["index.html"])
        self.assertIn(PRODUCT["image"], files)
        self.assertNotIn(b"weekly-specials", files["hike/index.html"])

    def test_preview_target_lists_what_the_page_shows_today(self):
        record = {"collection": "store", "key": "store", "before": dict(STORE),
                  "after": {**STORE, "specials": [special(1), special(2, start=-9, end=-5)]}}
        self.assertEqual(preview.target_for(record)["specials"], [{"title": "Special 1", "deal": "1 for $5"}])
        same = {**record, "before": record["after"]}
        self.assertNotIn("specials", preview.target_for(same))

    def test_claims_and_live_policy_see_the_words(self):
        draft = {"ops": [{"op": ADD, "args": {}}], "records": [{"collection": "store", "key": "store", "before": dict(STORE),
                 "after": {**STORE, "specials": [special(title="Organic eggs", deal="Free sample Saturday")]}}]}
        hits = claims.unstated(draft, "add a special", {})
        self.assertTrue(any("specials.sp-1.title" in where for where, _ in hits), hits)
        self.assertEqual(claims.unstated(draft, "add a special: Organic eggs, free sample Saturday", {}), [])
        priced = {"ops": [{"op": ADD, "args": {}}], "records": [{"collection": "store", "key": "store", "before": dict(STORE),
                  "after": {**STORE, "specials": [special()]}}]}
        self.assertIn("protected sentences: prices", live_policy.check(priced))  # a deal price never goes live from chat


class OpTests(StoreTestCase):
    def test_add_edit_remove_and_undo_round_trip_returns_the_identical_page(self):
        repo = self.repo()
        original, store = repo.read(INDEX), repo.store()
        added = repo.run((ADD, {"title": "Fresh strawberries", "deal": "2 for $5", "end": day(3)}))
        self.assertEqual(repo.store()["specials"], [{"id": "fresh-strawberries", "title": "Fresh strawberries", "deal": "2 for $5",
                                                    "start": day(0), "end": day(3), "order": 0}])
        self.assertIn('<p class="special-deal">2 for $5</p>', repo.text(INDEX))
        edited = repo.run((EDIT, {"id": "fresh-strawberries", "deal": "3 for $10", "end": day(4)}))
        self.assertIn('<p class="special-deal">3 for $10</p>', repo.text(INDEX))
        self.assertEqual(repo.store()["specials"][0]["end"], day(4))
        repo.run((REVERT, {"changeId": edited["change_id"]}))  # undo the edit: the add is back
        self.assertEqual(repo.store()["specials"][0]["deal"], "2 for $5")
        self.assertIn('<p class="special-deal">2 for $5</p>', repo.text(INDEX))
        repo.run((REVERT, {"changeId": added["change_id"]}))  # undo the add: the saved files are as they started
        self.assertEqual((repo.store(), repo.read(INDEX), repo.status()), (store, original, ""))

    def test_remove_then_undo_and_unknown_id(self):
        repo = self.repo()
        repo.run((ADD, {"title": "Honey sticks", "deal": "Buy 2, get 1 free", "end": day(2)}))
        self.assertEqual(result(repo, REMOVE, {"id": "nope"}), ("refused", "there is no special nope"))
        removed = repo.run((REMOVE, {"id": "honey-sticks"}))
        self.assertNotIn("specials", repo.store())
        self.assertNotIn("weekly-specials", repo.text(INDEX))
        repo.run((REVERT, {"changeId": removed["change_id"]}))
        self.assertEqual(repo.store()["specials"][0]["id"], "honey-sticks")

    def test_clear_expired_removes_only_finished_ones_and_undo_brings_them_back(self):
        repo = self.repo()
        repo.run((ADD, {"title": "Live one", "deal": "Free sample", "end": day(2)}))
        content_store = repo.store()
        content_store["specials"].insert(0, special(9, start=-9, end=-2))  # an old one nobody removed
        (repo.wt / "hass/content/store.json").write_text(json.dumps(content_store, ensure_ascii=False, indent=2) + "\n")
        from hass.tests.test_editor import git
        git(repo.wt, "commit", "-qam", "an old special")
        cleared = repo.run((CLEAR, {}))
        self.assertEqual([s["id"] for s in repo.store()["specials"]], ["live-one"])
        self.assertEqual(result(repo, CLEAR, {}), ("refused", "there are no finished specials to clear"))
        repo.run((REVERT, {"changeId": cleared["change_id"]}))
        self.assertEqual([s["id"] for s in repo.store()["specials"]], ["sp-9", "live-one"])

    def test_clear_expired_with_nothing_saved_is_refused(self):
        self.assertEqual(result(self.repo(), CLEAR, {}), ("refused", "there are no finished specials to clear"))

    def test_add_refusals_leave_no_draft(self):
        repo = self.repo()
        head = repo.head()
        cases = [({"title": "Eggs", "deal": "2 for $5", "end": day(-1)}, "the last day"),
                 ({"title": "Eggs", "deal": "2 for $5", "start": day(3), "end": day(1)}, "is before the first day"),
                 ({"title": "Eggs", "deal": "2 for $5", "end": day(40)}, "runs at most 31 days"),
                 ({"title": "Eggs", "deal": "2 for $5", "end": day(1), "picture": True}, "name the product too"),
                 ({"title": "Eggs", "deal": "2 for $5", "end": day(1), "product": "no-such-thing"}, "is not a product"),
                 ({"title": "Eggs", "deal": "2 for $5", "end": day(1), "order": 100}, "the order is 0 to 99"),
]
        for args, why in cases:
            with self.subTest(why=why):
                outcome, reason = result(repo, ADD, args)
                self.assertIn(outcome, ("refused", "not_found", "invalid"))
                self.assertIn(why, reason or "")
        for args in ({"title": "<b>Eggs</b>", "deal": "x y z", "end": day(1)}, {"title": "Eggs $3", "deal": "2 for $5", "end": day(1)},
                     {"title": "Eggs", "deal": "2 for <b>5</b>", "end": day(1)}, {"title": "Eggs", "deal": "see www.eggs.com", "end": day(1)}):
            self.assertEqual(result(repo, ADD, args)[0], "invalid", args)
        self.assertEqual(result(repo, ADD, {"title": "Eggs", "deal": "2 for $5"})[0], "needs-details")  # the end date is required
        self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, [], ""))

    def test_seventh_overlapping_special_is_refused_but_a_later_one_is_fine(self):
        repo = self.repo()
        for n in range(6):
            repo.run((ADD, {"title": f"Deal number {n}", "deal": "Free sample", "end": day(3)}))
        outcome, reason = result(repo, ADD, {"title": "One too many", "deal": "Free sample", "end": day(3)})
        self.assertEqual(outcome, "refused")
        self.assertIn("at most 6 specials can show at once", reason)
        repo.run((ADD, {"title": "After the rest", "deal": "Free sample", "start": day(4), "end": day(6)}))
        self.assertEqual(len(repo.store()["specials"]), 7)

    def test_duplicate_title_edit_to_the_past_and_noop_edit_are_refused(self):
        repo = self.repo()
        repo.run((ADD, {"title": "Honey sticks", "deal": "Free sample", "end": day(2)}))
        self.assertIn("already a special called", result(repo, ADD, {"title": "honey  sticks", "deal": "x y z", "end": day(2)})[1])
        self.assertIn("already past", result(repo, EDIT, {"id": "honey-sticks", "end": day(-1)})[1])
        self.assertEqual(result(repo, EDIT, {"id": "honey-sticks", "deal": "Free  sample"}), ("refused", "that special already says that"))
        self.assertEqual(result(repo, EDIT, {"id": "honey-sticks"})[0], "needs-details")

    def test_product_link_picture_and_clear_product(self):
        repo = self.repo()
        repo.run((ADD, {"title": "Tasting", "deal": "Free sample", "end": day(2), "product": PRODUCT["id"], "picture": True}))
        self.assertIn("special-image", repo.text(INDEX))
        repo.run((EDIT, {"id": "tasting", "picture": False}))
        self.assertNotIn("special-image", repo.text(INDEX))
        self.assertIn(f'?item={PRODUCT["id"]}', repo.text(INDEX))
        repo.run((EDIT, {"id": "tasting", "clearProduct": True}))
        self.assertNotIn("product", repo.store()["specials"][0])

    def test_pacific_midnight_boundary_for_add(self):
        apply, content = load_registry()[ADD].apply, load_content()
        end = "2026-11-26"
        at = lambda utc: apply(content, {"title": "Pie day", "deal": "Free slice", "end": end}, OpContext(utc, REPO_ROOT, {}))  # noqa: E731
        self.assertNotIsInstance(at(datetime(2026, 11, 27, 7, 30, tzinfo=timezone.utc)), Refused)  # 23:30 PST on the 26th
        self.assertEqual(at(datetime(2026, 11, 27, 8, 30, tzinfo=timezone.utc)), Refused("the last day 2026-11-26 is already past"))

    def test_the_page_consistency_check_survives_the_last_day_passing(self):
        from unittest import mock
        repo = self.repo()
        repo.run((ADD, {"title": "Fresh strawberries", "deal": "2 for $5", "end": day(0)}))
        before = repo.read(INDEX)
        with mock.patch.object(sitegen, "shop_today", return_value=shop_today() + timedelta(days=1)):
            self.assertEqual(sitegen.main(["--check", "--repo", str(repo.wt)]), 0)  # the exact pre-expiry page is accepted
            (repo.wt / INDEX).write_bytes(before.replace(b"2 for $5", b"9 for $9"))
            self.assertEqual(sitegen.main(["--check", "--repo", str(repo.wt)]), 1)  # real drift is not
        self.assertNotIn(b"Fresh strawberries", sitegen.render(load_content(repo.wt / "hass/content"),
                         repo.wt / "hass/templates", today=shop_today() + timedelta(days=1))[INDEX])

    def test_ops_layer_names(self):
        self.assertTrue({ADD, EDIT, REMOVE, CLEAR} <= set(load_registry()))


@unittest.skipUnless(os.environ.get("PLAYWRIGHT_MODULE"), "PLAYWRIGHT_MODULE is not set")
class BrowserTests(unittest.TestCase):
    def test_script_hides_a_card_after_its_last_day_and_the_section_with_it(self):
        out = subprocess.run(["node", str(Path(__file__).with_name("specials_expiry.cjs"))], input=specials.SPECIALS_JS,
                             text=True, capture_output=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        print(out.stdout.strip())

    def test_full_page_shows_the_section_on_a_phone_and_hides_it_once_expired(self):
        from hass.preview import VIEWPORTS  # noqa: F401
        shot = os.environ.get("SPECIALS_SCREENSHOT_DIR")
        out = subprocess.run(["node", str(Path(__file__).with_name("specials_page.cjs"))],
                             input=json.dumps({"html": page(special(1, product=PRODUCT["id"], picture=True), special(2, title="Sample Saturday", deal="Free sample Saturday")),
                                               "root": str(REPO_ROOT / "storefront-mockup"), "shots": shot, "today": day(0)}),
                             text=True, capture_output=True, timeout=120)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        print(out.stdout.strip())


if __name__ == "__main__":
    unittest.main()

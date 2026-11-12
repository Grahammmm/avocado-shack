"""RF1741-13: a count question keeps a leading or inner `low` that introduces a product word ('how much low fat milk is left').

The shelf reply and answer.site's unsupported-stock guard share reports.count_query; `low` stays a stop word for a terminal
stock state ('how many eggs low'), so nameless and whole-shelf asks keep answering the whole report.
Run: python3 -B -m unittest hass.tests.test_report_count_low_modifier -v
"""
import unittest
from datetime import timedelta

from hass.skills import reports
from hass.tests import test_skills_reports as rep

NO_COUNTS = rep.NO_COUNTS
MILK_SHELF = [rep.prod("Low Fat Milk", "limited"), rep.prod("Milk", "yes"), rep.prod("Low Sodium Broth", "no"),
              rep.prod("Organic Low Sugar Jam", "yes"), rep.prod("eggs", "limited")]


def plain(c, text, **kw):
    return rep.PLAIN(rep.said(c, text, **kw))


class LowModifierQuery(unittest.TestCase):
    def test_low_fat_milk_count_preserves_the_complete_product_query(self):
        c = rep.content(MILK_SHELF)
        for text in ("how much low fat milk is left", "how many of the low fat milk do we have", "How MANY Low Fat Milk do we have?"):
            with self.subTest(text):
                self.assertEqual(reports.count_query(text), "low fat milk")
                self.assertEqual(plain(c, text), NO_COUNTS + "Low Fat Milk: limited")
        self.assertEqual(plain(c, "how many milk do we have"),  # the plain word is still the resolver's own question
                         "Which one do you mean: Low Fat Milk (Shack) or Milk (Shack)?")
        self.assertEqual(plain(c, "how many eggs do we have"), NO_COUNTS + "eggs: limited")

    def test_low_modifier_at_start_and_inside_product_names(self):
        c = rep.content(MILK_SHELF)
        self.assertEqual(reports.count_query("how much low sodium broth is left"), "low sodium broth")
        self.assertEqual(reports.count_query("how many of the organic low sugar jam do we have"), "organic low sugar jam")
        self.assertEqual(plain(c, "how much low sodium broth is left"), NO_COUNTS + "Low Sodium Broth: sold out")
        self.assertEqual(plain(c, "how many ORGANIC LOW SUGAR JAM do we have"), NO_COUNTS + "Organic Low Sugar Jam: available")
        self.assertEqual(reports.count_query("how many low fat milk is left"), "low fat milk")  # 'is left' stays a suffix

    def test_terminal_low_and_whole_shelf_questions_keep_their_old_meaning(self):
        for text, want in (("morning report", None), ("what is low today", None), ("how many", ""), ("how many do we have", ""),
                           ("how many are low", ""), ("how many low", ""), ("how many low do we have", ""),
                           ("how many low the", ""), ("how many eggs low", "eggs"), ("how many eggs low now", "eggs"),
                           ("how many eggs are low", "eggs"), ("how many things are low", ""), ("how many hikes are coming up", ""),
                           ("how many people are coming", "")):
            with self.subTest(text):
                self.assertEqual(reports.count_query(text), want)
        c = rep.content(MILK_SHELF)
        for text in ("how many are low", "how many low", "how many low do we have"):
            with self.subTest(text):
                self.assertEqual(rep.said(c, text), rep.engine(c))


class LowModifierGuardAndFreshness(unittest.TestCase):
    def test_low_product_guard_reuses_existing_no_count_reply_and_reason(self):
        c = rep.content(MILK_SHELF)
        ctx = rep.site_ctx(c)
        for text in ("how much low fat milk is left", "how many of the low fat milk do we have"):
            with self.subTest(text):
                reply, reason = reports.site_guard({"kind": "product", "subject": "low fat milk"}, [text], ctx)
                self.assertEqual((rep.PLAIN(reply), reason), (NO_COUNTS + "Low Fat Milk: limited", "other"))
        reply, reason = reports.site_guard({}, ["how many are low"], ctx)  # nameless: the generic sentence, as before
        self.assertEqual((reply, reason), ("I don't keep stock counts.", "other"))
        reply, reason = reports.site_guard({}, ["how much low fat milk costs"], ctx)  # price still wins where it wins
        self.assertEqual(reason, "price")

    def test_low_product_ambiguity_alias_hidden_and_held_are_not_guessed(self):
        dup = rep.content([rep.prod("Low Fat Milk", "yes", pid="m-1"), rep.prod("low fat milk", "no", pid="m-2")])
        self.assertTrue(plain(dup, "how many low fat milk do we have").startswith("Which one do you mean: "))
        c = rep.content([rep.prod("Low Fat Milk", "limited", pid="m-1")])
        self.assertEqual(plain(c, "how many cows do we have", aliases={"cows": ("product", "m-1")}), NO_COUNTS + "Low Fat Milk: limited")
        for status in ("held", "hidden"):
            with self.subTest(status):
                gone = rep.content([rep.prod("Low Fat Milk", "no", status=status), rep.prod("Milk", "yes")])
                self.assertEqual(plain(gone, "how many low fat milk do we have"), reports.NOT_ON_REPORT)
        self.assertEqual(plain(rep.content([rep.prod("Milk", "yes")]), "how many low fat milk do we have"),  # no shorter match
                         "I don't know a product called that. What is it called on the site?")

    def test_low_product_freshness_and_text_bounds_are_unchanged(self):
        old, future = (rep.TODAY - timedelta(days=9)).isoformat(), (rep.TODAY + timedelta(days=2)).isoformat()
        for checked, tail in ((old, "more than a week ago"), (future, "still to come"), (None, "I still need your shelf check.")):
            c = rep.content([rep.prod("Low Fat Milk", "limited", on=checked)], checked=checked)
            with self.subTest(checked):
                lines = plain(c, "how many low fat milk do we have").split("\n")
                self.assertEqual(len(lines), 2)
                self.assertTrue(lines[0].startswith(NO_COUNTS + "Low Fat Milk: "), lines)
                self.assertIn(tail, lines[1])
        c = rep.content(MILK_SHELF)
        self.assertEqual(plain(c, "how many eggs do we have"), NO_COUNTS + "eggs: limited")
        self.assertEqual(rep.PLAIN(rep.said(c, "how many low fat milk do we have", "how many eggs do we have")), NO_COUNTS + "eggs: limited")  # latest
        self.assertEqual(rep.PLAIN(rep.said(c, "how many eggs do we have", "how many low fat milk do we have")), NO_COUNTS + "Low Fat Milk: limited")
        late = "x" * reports.MAX_TEXT + " how many low fat milk do we have"  # cut at the message bound: the ask is lost
        self.assertEqual(rep.said(c, late), rep.engine(c))
        self.assertEqual(rep.said(c, "how many low fat milk do we have", "email me the report"), reports.NO_PUSH)


class LowModifierDispatch(rep.ShelfCase):
    def test_real_dispatch_delivers_product_local_answer_without_editor_work(self):
        self.scenario("fresh")

        def rename(doc):
            for p in doc["products"]:
                if p["id"] == rep.EGGS:
                    p["name"] = "Low Fat Milk"
        self.edit("products.json", rename)
        self.baseline = rep.snapshot_of(self)
        for text in ("how much low fat milk is left", "how many of the low fat milk do we have"):
            with self.subTest(text):
                status, [reply] = self.ask(text)
                self.assertEqual((status, reply), ("answer", NO_COUNTS + "Low Fat Milk: limited"))
                self.assertEqual(self.calls, [])
        self.untouched()


if __name__ == "__main__":
    unittest.main()

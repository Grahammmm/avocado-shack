"""AV2007-15 tests: 'did the shelf check, all good', 'shelf check done' and 'shelf check: all good' make today's shelf-check
draft (stock.checked with empty slots) by code, in ops-only and both modes, and only `yes <code>` saves it.

The real Conversation and production Editor run on the H02 throwaway shop with an injected clock; the interpreter is a scripted
stand-in that records every text it is asked (a deterministic route never asks it).
Run: python3 -B -m unittest hass.tests.test_plain_shelf_check -q
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from hass.skills import stock
from hass.tests.test_editor import git
from hass.tests.test_skill_dispatch import SkillCase

PHRASES = ("did the shelf check, all good", "shelf check done", "shelf check: all good")
HASS = "photo-product-001"
DAY = "2026-11-02"  # SkillCase's clock: Monday 2026-11-02 09:00 PST


class PlainShelfCheck(SkillCase):
    MODE = "both"
    SKILLS = (stock.STOCK_CHECKED,)

    def edit(self, name, change):
        path = self.repo.wt / "hass" / "content" / name
        doc = json.loads(path.read_text("utf-8"))
        change(doc)
        path.write_text(json.dumps(doc), "utf-8")
        git(self.repo.wt, "commit", "-qam", f"seed {name}")
        self.base = self.count()

    def content(self, name):
        return (self.repo.wt / "hass" / "content" / name).read_bytes()

    def checked_on(self):
        return json.loads(self.content("store.json")).get("selection_checked_on")

    def ask(self, text):
        disposition = self.say(text)
        return disposition, "\n".join(self.replies())

    def propose_check(self, text=PHRASES[0]):
        disposition, reply = self.ask(text)
        self.assertEqual(disposition, "proposed", reply)
        return self.drafts()[-1], reply


class ModeTests:
    """The same behaviour in each skills mode."""

    def test_three_plain_forms_propose_empty_check_in_each_mode(self):
        for text in PHRASES + ("Shelf check done!", "  DID the shelf   check, all good. "):
            with self.subTest(text=text):
                before = len(self.drafts())
                draft, reply = self.propose_check(text)
                self.assertEqual(draft["reason"], "shelf-check")
                self.assertEqual([(o["op"], o["args"]) for o in json.loads(draft["ops_json"])], [("store.confirm_selection", {})])
                self.assertIn(f"Reply yes {draft['code']} to save it", reply)
                self.assertEqual(self.asked, [])  # never reached the model
                self.nothing_written()
                self.assertEqual(len(self.drafts()), max(before, 1))  # a repeat reuses the waiting draft
                self.assertIsNone(self.checked_on())

    def test_requires_its_code_before_and_after_reopen(self):
        draft, _ = self.propose_check()
        code = draft["code"]
        for opened in (False, True):
            if opened:
                self.conv = self.open()
            self.assertEqual(self.say("yes"), "no-target")
            self.assertEqual(self.replies(), [f"Reply yes {code} to save the shelf check."])
            self.assertEqual(self.say("yes 0000"), "no-target")
            self.replies()
            self.nothing_written()
        self.assertEqual(self.say(f"yes {code}"), "approved")
        self.replies()
        self.assertEqual(self.commits(), 1)
        self.assertEqual(self.checked_on(), DAY)
        self.assertEqual(self.say(f"yes {code}", pid="again-yes"), "no-target")  # a second yes writes nothing more
        self.replies()
        self.assertEqual(self.commits(), 1)

    def test_preapproval_cancel_and_duplicate_delivery_write_nothing(self):
        draft, _ = self.propose_check()
        self.assertEqual(self.say(PHRASES[0], pid="m-dup"), "proposed")
        self.replies()
        n = len(self.drafts())
        self.assertEqual(self.say(PHRASES[0], pid="m-dup"), "duplicate")  # the same delivery again is idempotent
        self.assertEqual((self.replies(), len(self.drafts())), ([], n))
        again, reply = self.propose_check(PHRASES[1])
        self.assertEqual(again["code"], draft["code"])  # a repeated phrase reuses the waiting code
        self.assertEqual(len(self.drafts()), n)
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.replies()
        self.nothing_written()
        self.assertEqual(self.asked, [])

    def test_already_checked_today_is_noop(self):
        draft, _ = self.propose_check()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.replies()
        self.assertEqual(self.commits(), 1)
        n = len(self.drafts())
        disposition, reply = self.ask(PHRASES[1])
        self.assertEqual((disposition, reply), ("refused", stock.DONE_TODAY))
        self.assertEqual((len(self.drafts()), self.commits(), self.asked), (n, 1, []))

    def test_near_miss_negation_question_and_exception_tails_do_not_match(self):
        for text in ("did not do the shelf check", "shelf check done?", "will do the shelf check", "all good",
                     "all good except watermelon", "shelf check done, eggs are out", "shelf check done tomorrow",
                     "did the shelf check, all good except the eggs", "shelf check not done"):
            with self.subTest(text=text):
                self.assertFalse(stock.plain_shelf_check(text))
                if stock.shelf_check_except(text) is not None: continue  # AV2007-16: a separate route drafts it (hass.tests.test_shelf_check_except)
                self.script(text, {"unsupported": "stand-in"})
                before = len(self.drafts())
                self.assertEqual(self.say(text), "unsupported")
                self.replies()
                self.assertEqual((self.asked[-1][0], len(self.drafts())), (text, before))
        for bad in (None, 5, b"shelf check done", ["shelf check done"]):
            self.assertFalse(stock.plain_shelf_check(bad))

    def test_midnight_and_future_stored_check(self):
        self.now = datetime(2026, 11, 3, 7, 30, tzinfo=timezone.utc)  # 23:30 PST on the 2nd
        draft, _ = self.propose_check()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.replies()
        self.assertEqual(self.checked_on(), "2026-11-02")
        self.now = datetime(2026, 11, 3, 8, 30, tzinfo=timezone.utc)  # 00:30 PST on the 3rd: a new shop day
        draft, _ = self.propose_check()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.replies()
        self.assertEqual(self.checked_on(), "2026-11-03")
        self.edit("store.json", lambda doc: doc.update(selection_checked_on="2026-11-09"))  # stored date in the future
        disposition, reply = self.ask(PHRASES[2])
        self.assertEqual((disposition, reply), ("refused", stock.AFTER))
        self.assertEqual(self.commits(), 0)

    def test_no_product_words_refreshed_and_undo_restores(self):
        self.edit("products.json", lambda doc: next(p for p in doc["products"] if p["id"] == HASS).update(available="no", available_on="2026-10-30"))
        self.edit("store.json", lambda doc: doc.update(selection_checked_on="2026-10-30"))  # the words are dated by an earlier check
        products, store = self.content("products.json"), self.content("store.json")
        draft, _ = self.propose_check()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.replies()
        self.assertEqual(self.content("products.json"), products)
        self.assertNotEqual(self.content("store.json"), store)
        self.assertEqual(self.checked_on(), DAY)
        self.assertEqual(self.say("undo"), "proposed")
        self.replies()
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.replies()
        self.assertEqual(self.content("products.json"), products)
        self.assertEqual(json.loads(self.content("store.json")), json.loads(store))  # the editor rewrites the file pretty-printed; the content is restored

    def test_stale_reissue_names_the_new_code_and_only_it_saves(self):
        # Contract: a stale shelf-check draft is written up again with its code-required marker, and the reply is
        # rendered from that saved row. Bug it catches: the reply rendered from the pre-marker snapshot told the owner
        # to send bare `yes`, which the next turn refuses.
        old, _ = self.propose_check()
        self.edit("products.json", lambda doc: next(p for p in doc["products"] if p["id"] == HASS).update(description="Picked this week."))
        self.assertEqual(self.say(f"yes {old['code']}"), "approved")
        reply = "\n".join(self.replies())
        stale, new = self.drafts()[-2:]
        self.assertEqual((stale["state"], stale["reason"], new["state"], new["reason"]), ("rejected", "stale", "proposed", "shelf-check"))
        self.assertNotEqual(new["code"], old["code"])
        self.assertIn("written it up again", reply)
        self.assertIn(f"Reply yes {new['code']} to save it", reply)
        self.assertNotIn("Reply yes to", reply)
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.say("yes"), "no-target")  # the bare yes the old reply would have asked for is refused
        self.replies()
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.say(f"yes {new['code']}"), "approved")
        self.replies()
        self.assertEqual((self.commits(), self.checked_on()), (1, DAY))

    def test_paused_busy_and_disabled_skill(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        draft, reply = self.propose_check()  # drafting is allowed while paused; saving is not
        self.assertIn("paused", reply.lower())
        self.assertEqual(self.say(f"yes {draft['code']}"), "paused")
        self.replies()
        self.nothing_written()
        self.assertEqual(self.asked, [])
        self.editor.skill_allowed = lambda skill: False  # the owner switched this skill off
        n = len(self.drafts())
        self.assertEqual(self.say(PHRASES[1]), "refused")
        self.assertEqual((self.replies(), len(self.drafts())), (["That's switched off, so nothing changed."], n))


class OpsOnlyPlainShelfCheck(ModeTests, PlainShelfCheck):
    MODE = "ops-only"


class BothPlainShelfCheck(ModeTests, PlainShelfCheck):
    MODE = "both"


if __name__ == "__main__":
    unittest.main()

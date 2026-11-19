"""H06 tests: selective undo, conflicts, persist-before-reply and hidden additions (fake Previewer, no browser).

Each test uses the H05 conversation setup (temp Git repo, linked writer worktree, private 0700 state dir, injected
clock) with the A2 fixture ops plus the production ops (A3 product.add, H06 history.revert).
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from hass import conversation, editor, migration_check, preview
from hass.content_model import REPO_ROOT
from hass.fixture_chat import FixtureAdapter
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_editor import DESC, NEW_HOURS
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
ORIGINAL = next(p for p in json.loads((REPO_ROOT / "hass/content/products.json").read_text("utf-8"))["products"]
                if p["id"] == "photo-product-001")["description"]
NEW_PRODUCT = {"name": "Test quince", "brand": "Avocado Shack", "category": "fruit", "description": "Fragrant.",
               "image": "assets/products/photo-product-001.webp", "displayBrand": "Avocado Shack"}


class FakePreviewer:
    """Writes a small PNG and reports passing checks; records every target."""

    def __init__(self):
        self.targets = []

    def capture(self, files, target, out_png):
        self.targets.append(target)
        preview._write_private(Path(out_png), PNG)
        return {"ok": True, "png": str(out_png), "checks": {"fake": True}, "error": None}


class H06TestCase(ConversationTestCase):
    def make_previewer(self):
        return FakePreviewer()

    def setUp(self):
        super().setUp()
        self.interp.mapping.update({
            "desc2": _ops((DESC, {"id": "photo-product-001", "description": "Buttery."})),
            "add Avocado Shack quince": _ops(("product.add", NEW_PRODUCT))})
        self.editor = conversation.Editor(self.repo.state, {**fixture_ops.registry(), **load_registry()})
        self.previewer = self.make_previewer()
        self.conv = self.open()
        self.base = self.count()

    def open(self, ed=None):
        return conversation.Conversation(str(self.repo.state), ed or self.editor, self.interp, lambda: self.now,
                                         getattr(self, "previewer", None))

    def sent(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return self.out.sent[before:]

    def apply(self, text):
        """Propose and approve one change; return its draft row."""
        draft, _reply = self.propose(text)
        self.assertEqual(self.say("yes"), "approved")
        self.sent()
        return [d for d in self.drafts() if d["row_id"] == draft["row_id"]][0]

    def content(self, name):
        return json.loads((self.repo.wt / "hass/content" / f"{name}.json").read_text("utf-8"))

    def product(self, pid):
        return next(p for p in self.content("products")["products"] if p["id"] == pid)


class UndoTests(H06TestCase):
    def test_selective_undo_keeps_later_edits(self):
        a, b = self.apply("desc"), self.apply("hours")
        self.assertEqual((a["state"], b["state"], self.commits()), ("verified", "verified", 2))
        self.assertEqual(self.say(f"undo {a['code']}"), "proposed")
        [reply] = self.sent()
        self.assertTrue(reply["text"].startswith("To undo that, I'd change it back:\nHere's the change I'd make:"), reply["text"])
        self.assertEqual(len(reply["attachments"]), 1)
        self.assertEqual(self.say("yes"), "approved")
        [done] = self.sent()
        rev = self.drafts()[-1]
        self.assertEqual(done["text"], f"Saved and checked: {rev['summary']}\n{conversation.answers.NOT_LIVE}")
        self.assertEqual(self.product("photo-product-001")["description"], ORIGINAL)
        self.assertEqual(self.content("store")["hours"], NEW_HOURS)
        self.assertEqual(self.commits(), 3)
        self.assertEqual([d["state"] for d in self.drafts()], ["reverted", "verified", "verified"])
        self.assertEqual(editor.show(a["change_id"], state=str(self.repo.state))["change"]["revertedBy"],
                         rev["change_id"])
        listed = editor.history(state=str(self.repo.state))["history"]
        self.assertEqual([h["change_id"] for h in listed], [rev["change_id"], b["change_id"], a["change_id"]])
        self.assertEqual(listed[0]["ops"], [f'history.revert {{"changeId": "{a["change_id"]}"}}'])
        self.assertEqual(self.say("history"), "history")
        lines = self.replies()[0].splitlines()
        self.assertEqual(lines[1:], [f"- {r['summary']}, approved Mon Nov 2 9:00 am: saved, but I'm not sure it's on the website" for r in (rev, b)]
                         + [f"- {a['summary']}, approved Mon Nov 2 9:00 am: undone"])
        self.assertEqual(self.say(f"undo {a['code']}"), "not-drafted")
        self.assertEqual(self.replies(), ["I couldn't undo that, so nothing changed. Could you say it another way?"])
        self.assertEqual((len(self.drafts()), self.commits()), (3, 3))

    def test_conflict_is_refused_without_a_draft(self):
        a = self.apply("desc")
        self.apply("desc2")
        self.assertEqual(self.say(f"undo {a['code']}"), "not-drafted")
        [reply] = self.replies()
        self.assertEqual(reply, "That has changed since, so I can't undo it cleanly. Tell me what it should say now, and I'll change it to that.")
        self.assertEqual((len(self.drafts()), self.commits()), (2, 2))

    def test_result_is_persisted_before_the_reply(self):
        self.propose("desc")
        self.out = FixtureAdapter(fail_sends=1)
        self.assertEqual(self.say("yes"), "approved")
        with self.assertRaises(ConnectionError):
            self.conv.flush(self.out)
        [row] = self.drafts()
        self.assertEqual(row["state"], "verified")
        self.assertEqual(Path(row["screenshot"]).read_bytes(), PNG)
        self.conv = self.open()  # restart
        [sent] = self.sent()
        self.assertEqual((sent["text"].split(":")[0], sent["attachments"]),
                         ("Saved and checked", [row["screenshot"]]))
        self.assertEqual((self.sent(), self.commits()), ([], 1))

    def test_undo_of_an_addition_hides_it(self):
        added = self.apply("add Avocado Shack quince")
        [record] = editor.show(added["change_id"], state=str(self.repo.state))["change"]["records"]
        self.assertEqual(self.say("undo"), "proposed")
        self.replies()
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.assertEqual(self.product(record["key"])["status"], "hidden")
        catalog = (self.repo.wt / "storefront-mockup/catalog-products.js").read_text("utf-8")
        self.assertNotIn(record["key"], catalog)
        self.assertEqual(migration_check.run_checks(self.repo.wt)[0], [])
        self.assertEqual((self.drafts()[0]["state"], self.commits()), ("reverted", 2))


class EventUndoTests(HikeTestCase):
    def test_restored_scheduled_event_must_start_in_future(self):
        for op in ("hike.cancel", "hike.complete", "hike.update"):
            for delay in (timedelta(), timedelta(days=24)):
                with self.subTest(op=op, delay=delay):
                    repo = self.repo()
                    repo.run(("hike.create", HIKE))
                    repo.make_db([])
                    start = datetime.fromisoformat(repo.event()["startsAt"])
                    if op == "hike.complete":
                        repo.now = start
                    args = {"id": HIKE_ID}
                    if op == "hike.update":
                        args["date"] = "2027-01-05"
                    changed = repo.run((op, args))
                    before = repo.event()
                    repo.now = start + delay
                    result = self.assertRejected(repo, "refused",
                                                 ("history.revert", {"changeId": changed["change_id"]}))
                    self.assertEqual(result["reason"], "start is in the past")
                    self.assertEqual(repo.event(), before)

    def test_restored_capacity_respects_confirmed_seats(self):
        for counts in ("over-capacity", "missing", "unreadable", "at-capacity"):
            with self.subTest(counts=counts):
                repo = self.repo()
                repo.run(("hike.create", HIKE))
                repo.make_db([])
                raised = repo.run(("hike.update", {"id": HIKE_ID, "capacity": 20}))
                repo.db.unlink()
                seats = 15 if counts == "over-capacity" else 12
                repo.make_db([(HIKE_ID, 6), (HIKE_ID, 3), (HIKE_ID, seats - 9), ("other-event", 6)])
                if counts == "missing":
                    repo.use_db("")
                elif counts == "unreadable":
                    repo.use_db(str(repo.state.parent / "missing.sqlite3"))
                before = repo.db.read_bytes()
                if counts == "at-capacity":
                    repo.run(("history.revert", {"changeId": raised["change_id"]}))
                    self.assertEqual(repo.event()["capacity"], 12)
                else:
                    result = self.assertRejected(repo, "refused",
                                                 ("history.revert", {"changeId": raised["change_id"]}))
                    self.assertEqual(result["reason"], "capacity 12 is below 15 confirmed guests"
                                     if counts == "over-capacity" else "guest count unavailable")
                    self.assertEqual(repo.event()["capacity"], 20)
                self.assertEqual(repo.db.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

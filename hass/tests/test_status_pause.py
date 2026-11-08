"""H17 tests: `status`, `pause changes` and `resume changes` (with H14 confirmed-guest totals).

Same setup as H05/H06 (temp Git repo, linked writer worktree, private 0700 state dir, injected clock, fixture
interpreter). RSVP databases are temp SQLite files with placeholder example.invalid rows only.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import sqlite3
import unittest
from datetime import timedelta

from hass import conversation, editor, voice
from hass.tests.test_conversation import GROUP, SETTINGS, STRANGER, T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, SCHEMA as RSVP_SCHEMA, _req
from hass.tests.test_undo import H06TestCase

PAUSED = ("Changes are stopped. I won't save anything new until you say 'resume changes'. No requests are waiting. "
          "Changes already on the website stay there.")  # SHOP-4 wording
PAUSED_ONE = PAUSED.replace("No requests are waiting.", "1 request is waiting.")
NOT_ON_SITE = ("It's saved, but I'm not sure it's on the website. {why}. If copying it started and stopped partway, some "
               "pages may already show it. Please ask Graham to copy it to the website again, which puts every page in place.")
NOT_COPIED = "Copying it to the website hasn't been done, or didn't finish"
PAST = ('Past hike was yesterday at 9 am and is still listed as coming up. '  # AV1537-07: started before T0
        'Tell me if it happened or was cancelled.')


def gated(code):
    return f"Changes are paused, so I haven't saved that. Say resume changes, then reply yes {code}."


class StoreMixin:
    def disposition(self, pid):
        return self.conv.db.execute("SELECT disposition FROM messages WHERE provider_id = ?", (pid,)).fetchone()[0]

    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def tables(self):
        return {r[0] for r in self.conv.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def status(self):
        self.assertEqual(self.say("status"), "status")
        [reply] = self.replies()
        return reply.splitlines()


class PauseTests(StoreMixin, ConversationTestCase):
    def test_pause_blocks_apply_until_resume_and_survives_restart(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("pause changes", pid="p1"), "pause")
        self.assertEqual(self.replies(), [PAUSED_ONE])  # the waiting draft is counted
        for text in ("yes", f"yes {draft['code']}", "Approve!", "approved."):  # every approval wording is gated
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "paused")
                self.assertEqual(self.replies(), [gated(draft["code"])])
        [row] = self.drafts()
        self.assertEqual((row["state"], row["expires_at"]), ("proposed", draft["expires_at"]))
        self.assertEqual((self.commits(), self.editor.applies, self.approvals()), (0, 0, 0))
        self.assertEqual(self.disposition("p1"), "pause")
        self.assertEqual(self.status()[0], "Changes are paused since today at 9 am. Say resume changes when you're ready.")
        self.conv = self.open()  # restart: still paused
        self.assertEqual(self.say("yes", pid="y2"), "paused")
        self.assertEqual((self.disposition("y2"), self.replies(), self.commits()), ("paused", [gated(draft["code"])], 0))
        self.assertEqual(self.say("resume changes"), "resume")
        self.assertEqual(self.replies(), [f"Changes are back on.\nOne change is waiting. Reply yes {draft['code']} to save it."])
        self.assertEqual((self.commits(), self.editor.applies, self.drafts()[0]["state"]), (0, 0, "proposed"))
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual((self.commits(), self.drafts()[0]["state"], self.approvals()), (1, "applied", 1))

    def test_pause_edge_paths(self):
        self.assertEqual(self.say("resume"), "resume")
        self.assertEqual(self.replies(), ["Changes are already on."])
        self.assertEqual(self.say("Pause changes!"), "pause")
        self.assertEqual(self.replies(), [PAUSED])
        self.now = T0 + timedelta(minutes=5)
        self.assertEqual(self.say("pause"), "pause")
        self.assertEqual(self.replies(), [PAUSED])  # already stopped: the same answer, nothing changes
        draft, reply = self.propose("hours")  # proposals still work and say they are paused
        self.assertTrue(reply.endswith("Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix.\n"
                                       "Changes are paused, so nothing will be saved yet. Say resume changes first, then yes."), reply)
        self.assertEqual(self.say("no"), "rejected")  # cancel still works while paused
        self.assertEqual(self.replies(), ["Okay, I've cancelled that. Nothing changed."])
        self.assertEqual((self.drafts()[0]["state"], self.commits()), ("rejected", 0))
        late, _reply = self.propose("desc")
        self.assertEqual(self.say("yes"), "paused")
        self.replies()
        self.now = T0 + timedelta(hours=1)  # the approval window ends during the pause
        self.assertEqual(self.say("RESUME CHANGES."), "resume")
        self.assertEqual(self.replies(), ["Changes are back on."])
        self.assertEqual(self.say("yes"), "no-target")  # the sweep at resume already closed it
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.assertEqual(self.say(f"yes {late['code']}"), "no-target")
        self.assertEqual(self.replies(), ["That change timed out today at 9:15 am, so nothing changed. Tell me again if you still want it."])
        self.assertEqual((self.drafts()[1]["state"], self.commits(), self.editor.applies), ("expired", 0, 0))
        self.assertEqual(self.say("resume"), "resume")
        self.assertEqual(self.replies(), ["Changes are already on."])

    def test_parsing(self):
        for text, parsed in (("STATUS.", ("status", None)), ("Pause changes!", ("pause", None)), (" pause ", ("pause", None)),
                             ("resume changes", ("resume", None)), ("Resume!", ("resume", None)),
                             ("history", ("history", None)), ("undo abcd", ("undo", "abcd"))):
            with self.subTest(text=text):
                self.assertEqual(conversation.parse_command(text), parsed)
        for text in ("pause the hike", "status of the hike", "resume hikes", "pause changes now", "please pause"):
            with self.subTest(text=text):
                self.assertIsNone(conversation.parse_command(text))
        self.assertEqual(self.say("pause the hike"), "unsupported")  # goes to the interpreter
        self.assertEqual(self.replies(), ["Sorry, I can't do that yet."])
        self.assertEqual(self.status()[0], "Everything is ready.")


class ReadOnlyTests(StoreMixin, ConversationTestCase):
    def test_status_changes_nothing(self):
        self.propose("hours")
        before = (self.drafts(), self.approvals(), self.tables(), self.commits())
        self.assertEqual(self.say("status", pid="s1"), "status")
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual((self.drafts(), self.approvals(), self.tables(), self.commits()), before)
        self.assertNotIn("control", self.tables())
        self.assertEqual(self.disposition("s1"), "status")

    def test_status_after_expiry_changes_nothing(self):
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        draft, _reply = self.propose("hours")
        self.now = T0 + timedelta(seconds=601)  # the proposal lapsed; no other message has swept it yet
        control = lambda: self.conv.db.execute("SELECT * FROM control").fetchall()
        before = (self.drafts(), self.approvals(), control(), self.commits())
        self.assertEqual(before[0][0]["state"], "proposed")
        self.assertEqual(self.status()[:3], ["Changes are paused since today at 9 am. Say resume changes when you're ready.", conversation.NOTHING, "I still need your shelf check."])
        self.assertEqual((self.drafts(), self.approvals(), control(), self.commits()), before)
        self.assertEqual(self.say("resume changes"), "resume")  # any later message still expires it
        self.assertEqual(self.replies(), ["Changes are back on."])
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.assertEqual(self.replies(), ["That change timed out today at 9:10 am, so nothing changed. Tell me again if you still want it."])
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.commits()), ("expired", 0, 0))

    def test_ignored_and_duplicate_messages_do_not_pause(self):
        draft, _reply = self.propose("hours")
        cases = [("echo", dict(from_me=True)), ("not-read", dict(kind="edited")),
                 ("ignored", dict(sender=STRANGER)), ("ignored", dict(chat=GROUP))]
        for text in ("status", "pause changes"):
            for disposition, kwargs in cases:
                with self.subTest(text=text, case=kwargs):
                    self.assertEqual(self.say(text, **kwargs), disposition)
                    reply = [conversation.NOT_READ_REPLY] if disposition == "not-read" else []
                    self.assertEqual((self.replies(), self.conv._paused()), (reply, None))
        self.assertEqual(self.say("pause changes", pid="dup"), "pause")
        self.assertEqual(self.say("resume changes"), "resume")
        self.replies()
        self.assertEqual(self.say("pause changes", pid="dup"), "duplicate")
        self.assertEqual((self.replies(), self.conv._paused()), ([], None))
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.commits(), 1)


class FailingEditor(conversation.Editor):
    def apply(self, change_id, draft_hash):
        return {"result": "failed", "reason": "simulated apply failure"}


class FailingPreviewer:
    def capture(self, files, target, out_png):
        return {"ok": False, "png": None, "checks": {}, "error": "simulated check failure"}


class StatusTests(StoreMixin, H06TestCase):
    def test_waiting_drafts_and_last_change(self):
        self.interp.mapping["need"] = _ops((HOURS, {}))
        self.assertEqual(self.say("need"), "needs-details")
        self.sent()
        needs = self.drafts()[-1]
        waiting = self.propose("desc")[0]
        self.assertEqual(self.status(), [  # nothing applied yet: no last-change line; no events: no hike line
            "Everything is ready.", "I'm waiting for details: Please provide: hours", "Waiting for your yes: the description for Hass avocado (reply yes 5390)",
            "I still need your shelf check."])
        self.assertEqual(self.say(f"yes {waiting['code']}"), "approved")
        self.interp.mapping["fill"] = {**_ops((HOURS, {"hours": NEW_HOURS})), "revises": needs["code"]}
        self.assertEqual(self.say("fill"), "proposed")
        self.assertEqual(self.say("yes"), "approved")  # the older row is the most recent result
        self.sent()
        filled = self.drafts()[0]
        self.assertEqual((filled["code"], [d["state"] for d in self.drafts()]), (needs["code"], ["verified"] * 2))
        last = f"Last change: {filled['summary']}. " + NOT_ON_SITE.format(why=NOT_COPIED)
        self.assertNotIn(filled["commit"][:7], last)
        self.assertEqual(self.status()[1:], [conversation.NOTHING, "I still need your shelf check.", last])
        self.assertEqual(self.say("need"), "needs-details")
        self.sent()
        two = self.propose("desc2")[0]
        needs2 = self.drafts()[-2]
        self.assertEqual(self.status(), [
            "Everything is ready.", f"I'm waiting for details: {needs2['summary']}",
            f"Waiting for your yes: {two['summary']} (reply yes {two['code']})", "I still need your shelf check.", last])

    def test_failed_and_unverified_results(self):
        self.editor = FailingEditor(self.repo.state, self.editor.registry)
        self.conv = self.open()
        failed = self.apply("hours")
        self.assertEqual((failed["state"], failed["reason"]), ("failed", "simulated apply failure"))  # kept in the store
        self.assertEqual(self.status()[-1], f"Last change: {failed['summary']}. I couldn't save that, and the website is unchanged. Please send the change again.")
        self.previewer, self.editor = FailingPreviewer(), conversation.Editor(self.repo.state, self.editor.registry)
        self.conv = self.open()
        applied = self.apply("desc")
        self.assertEqual(applied["state"], "applied")
        self.assertEqual(self.status()[-1], f"Last change: {applied['summary']}. " + NOT_ON_SITE.format(
            why="The preview check didn't pass: I couldn't check the preview"))  # SHOP-4
        self.assertEqual(self.drafts()[-1]["reason"], "not verified: products photo-product-001: simulated check failure")
        self.assertEqual(self.commits(), 1)

    def test_undo_while_paused_is_proposed_but_gated(self):
        done = self.apply("desc")
        self.assertEqual(self.say("pause changes"), "pause")
        self.sent()
        self.assertEqual(self.say(f"undo {done['code']}"), "proposed")
        [reply] = self.sent()
        self.assertTrue(reply["text"].endswith("\n" + voice.plain(conversation.PAUSED_LINE)), reply["text"])
        undo = self.drafts()[-1]
        self.assertEqual(self.say("yes"), "paused")
        self.assertEqual([r["text"] for r in self.sent()], [gated(undo["code"])])
        self.assertEqual(([d["state"] for d in self.drafts()], self.commits()), (["verified", "proposed"], 1))
        self.assertEqual(self.say("resume changes"), "resume")
        self.sent()
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(([d["state"] for d in self.drafts()], self.commits()), (["reverted", "verified"], 2))


class GuestTotalTests(StoreMixin, H06TestCase):
    def hike(self, *ops):
        draft = editor.prepare(_req(*ops), state=str(self.repo.state), now=NOW)
        self.assertEqual(draft["result"], "ok", draft)
        out = editor.apply(draft["draft"]["change_id"], draft["draft"]["draft_hash"], state=str(self.repo.state), now=NOW)
        self.assertEqual(out["result"], "applied", out)

    def rsvp_db(self, name, rows, schema=RSVP_SCHEMA):
        path = self.repo.state.parent / name
        db = sqlite3.connect(path)
        db.execute(schema)
        for n, (event_id, party) in enumerate(rows, 1):
            db.execute("INSERT INTO rsvps(event_id,email,name,party_size,created_at) VALUES(?,?,?,?,?)",
                       (event_id, f"guest{n}@example.invalid", f"Placeholder {n}", party, "2026-10-30T00:00:00Z"))
        db.commit()
        db.close()
        return str(path)

    def use(self, path):
        self.set_settings({**SETTINGS, **({} if path is None else {"guestCountsDb": path})})
        self.conv = self.open()

    def setUp(self):
        super().setUp()
        self.hike(("hike.create", HIKE))
        self.hike(("hike.create", {**HIKE, "title": "Past hike", "date": "2026-11-01"}))  # before the clock (T0)
        self.hike(("hike.create", {**HIKE, "title": "Cancelled hike", "date": "2026-12-01"}))
        self.hike(("hike.cancel", {"id": "hike-2026-12-01-cancelled-hike"}))
        open_hike = {k: v for k, v in HIKE.items() if k != "capacity"}
        self.hike(("hike.create", {**open_hike, "title": "Open hike", "date": "2026-11-20", "noCapacityLimit": True}))

    def test_confirmed_totals_from_rsvps(self):
        self.use(self.rsvp_db("rsvps.sqlite3", [(HIKE_ID, 2), (HIKE_ID, 3), ("hike-2026-12-01-cancelled-hike", 4),
                                                ("hike-2026-11-01-past-hike", 6)]))
        lines = self.status()
        self.assertEqual(lines[-3:], ["Open hike, Friday, Nov 20 at 9 am: 0 guests have signed up",
                                      "Test hike, Saturday, Dec 5 at 9 am: 5 guests have signed up, with room for 12", PAST])
        self.assertEqual([line for line in lines if "Past hike" in line], [PAST])  # its 6 RSVPs are never shown
        text = "\n".join(lines)
        for absent in ("Cancelled hike", "example.invalid", "guest1", "Placeholder"):
            self.assertNotIn(absent, text)

    def test_unknown_counts_are_never_guessed(self):
        wrong = self.rsvp_db("wrong.sqlite3", [], schema="CREATE TABLE other(id INTEGER)")
        for path in (None, "", str(self.repo.state.parent / "missing.sqlite3"), wrong):
            with self.subTest(path=path):
                self.use(path)
                self.assertEqual(self.status()[-3:], ["Open hike, Friday, Nov 20 at 9 am: I can't see how many guests have signed up",
                                                      "Test hike, Saturday, Dec 5 at 9 am: I can't see how many guests have signed up",
                                                      PAST])
        self.assertFalse((self.repo.state.parent / "missing.sqlite3").exists())

    def test_unreadable_content_gives_one_line(self):
        (self.repo.wt / "hass/content/community.json").write_text("{", "utf-8")
        self.assertEqual(self.status()[-1], "I can't read the hike list right now.")
        (self.repo.wt / "hass/content/community.json").write_text(json.dumps({"events": [{"status": "scheduled"}]}))
        self.assertEqual(self.status()[-1], "I can't read the hike list right now.")


if __name__ == "__main__":
    unittest.main()

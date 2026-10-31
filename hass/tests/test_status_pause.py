"""H17 tests: `status`, `pause changes` and `resume changes` (with H14 confirmed-guest totals).

Same setup as H05/H06 (temp Git repo, linked writer worktree, private 0700 state dir, injected clock, fixture
interpreter). RSVP databases are temp SQLite files with placeholder example.invalid rows only.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json
import sqlite3
import unittest
from datetime import timedelta

from hass import conversation, editor
from hass.tests.test_conversation import GROUP, SETTINGS, STRANGER, T0, ConversationTestCase, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS
from hass.tests.test_hike_ops import HIKE, HIKE_ID, NOW, SCHEMA as RSVP_SCHEMA, _req
from hass.tests.test_undo import H06TestCase

PAUSED = "Changes paused. Drafts can still be prepared; nothing is applied until you send resume changes."


def gated(code):
    return f"Changes are paused; {code} was not applied. Send resume changes, then yes {code}."


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
        self.assertEqual(self.replies(), [PAUSED])
        for text in ("yes", f"yes {draft['code']}", "Approve!", "approved."):  # every approval wording is gated
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "paused")
                self.assertEqual(self.replies(), [gated(draft["code"])])
        [row] = self.drafts()
        self.assertEqual((row["state"], row["expires_at"]), ("proposed", draft["expires_at"]))
        self.assertEqual((self.commits(), self.editor.applies, self.approvals()), (0, 0, 0))
        self.assertEqual(self.disposition("p1"), "pause")
        self.assertEqual(self.status()[0], "Changes: paused since 2026-11-02 09:00 PST")
        self.conv = self.open()  # restart: still paused
        self.assertEqual(self.say("yes", pid="y2"), "paused")
        self.assertEqual((self.disposition("y2"), self.replies(), self.commits()), ("paused", [gated(draft["code"])], 0))
        self.assertEqual(self.say("resume changes"), "resume")
        self.assertEqual(self.replies(), [f"Changes resumed.\nWaiting for approval: {draft['code']}; "
                                          "reply yes <code> to apply."])
        self.assertEqual((self.commits(), self.editor.applies, self.drafts()[0]["state"]), (0, 0, "proposed"))
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual((self.commits(), self.drafts()[0]["state"], self.approvals()), (1, "applied", 1))

    def test_pause_edge_paths(self):
        self.assertEqual(self.say("resume"), "resume")
        self.assertEqual(self.replies(), ["Changes are not paused."])
        self.assertEqual(self.say("Pause changes!"), "pause")
        self.assertEqual(self.replies(), [PAUSED])
        self.now = T0 + timedelta(minutes=5)
        self.assertEqual(self.say("pause"), "pause")
        self.assertEqual(self.replies(), ["Changes are already paused (since 2026-11-02 09:00 PST)."])
        draft, reply = self.propose("hours")  # proposals still work and say they are paused
        self.assertTrue(reply.endswith("Reply yes to apply, no to cancel, or send a correction.\n"
                                       "Changes are paused; send resume changes before yes."), reply)
        self.assertEqual(self.say("no"), "rejected")  # cancel still works while paused
        self.assertEqual(self.replies(), [f"Cancelled {draft['code']}; nothing changed."])
        self.assertEqual((self.drafts()[0]["state"], self.commits()), ("rejected", 0))
        late, _reply = self.propose("desc")
        self.assertEqual(self.say("yes"), "paused")
        self.replies()
        self.now = T0 + timedelta(hours=1)  # the approval window ends during the pause
        self.assertEqual(self.say("RESUME CHANGES."), "resume")
        self.assertEqual(self.replies(), ["Changes resumed."])
        self.assertEqual(self.say("yes"), "no-target")  # the sweep at resume already closed it
        self.assertEqual(self.replies(), [conversation.NOTHING])
        self.assertEqual(self.say(f"yes {late['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{late['code']} expired at 2026-11-02 09:15 PST; nothing changed."])
        self.assertEqual((self.drafts()[1]["state"], self.commits(), self.editor.applies), ("expired", 0, 0))
        self.assertEqual(self.say("resume"), "resume")
        self.assertEqual(self.replies(), ["Changes are not paused."])

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
        self.assertEqual(self.status()[0], "Changes: on")


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
        self.assertEqual(self.status()[:2], ["Changes: paused since 2026-11-02 09:00 PST", conversation.NOTHING])
        self.assertEqual((self.drafts(), self.approvals(), control(), self.commits()), before)
        self.assertEqual(self.say("resume changes"), "resume")  # any later message still expires it
        self.assertEqual(self.replies(), ["Changes resumed."])
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"{draft['code']} expired at 2026-11-02 09:10 PST; nothing changed."])
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.commits()), ("expired", 0, 0))

    def test_ignored_and_duplicate_messages_do_not_pause(self):
        draft, _reply = self.propose("hours")
        cases = [("echo", dict(from_me=True)), ("edited-ignored", dict(kind="edited")),
                 ("ignored", dict(sender=STRANGER)), ("ignored", dict(chat=GROUP))]
        for text in ("status", "pause changes"):
            for disposition, kwargs in cases:
                with self.subTest(text=text, case=kwargs):
                    self.assertEqual(self.say(text, **kwargs), disposition)
                    self.assertEqual((self.replies(), self.conv._paused()), ([], None))
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
            "Changes: on", f"{needs['code']} needs details: {needs['summary']}",
            f"{waiting['code']} waiting (expires 2026-11-02 09:10 PST): {waiting['summary']}"])
        self.assertEqual(self.say(f"yes {waiting['code']}"), "approved")
        self.interp.mapping["fill"] = {**_ops((HOURS, {"hours": NEW_HOURS})), "revises": needs["code"]}
        self.assertEqual(self.say("fill"), "proposed")
        self.assertEqual(self.say("yes"), "approved")  # the older row is the most recent result
        self.sent()
        filled = self.drafts()[0]
        self.assertEqual((filled["code"], [d["state"] for d in self.drafts()]), (needs["code"], ["verified"] * 2))
        last = f"Last change: {filled['code']} verified: {filled['summary']} ({filled['commit'][:7]})"
        self.assertEqual(self.status()[1:], [conversation.NOTHING, last])
        self.assertEqual(self.say("need"), "needs-details")
        self.sent()
        two = self.propose("desc2")[0]
        needs2 = self.drafts()[-2]
        self.assertEqual(self.status(), [
            "Changes: on", f"{needs2['code']} needs details: {needs2['summary']}",
            f"{two['code']} waiting (expires 2026-11-02 09:10 PST): {two['summary']}", last])

    def test_failed_and_unverified_results(self):
        self.editor = FailingEditor(self.repo.state, self.editor.registry)
        self.conv = self.open()
        failed = self.apply("hours")
        self.assertEqual(failed["state"], "failed")
        self.assertEqual(self.status()[-1],
                         f"Last change: {failed['code']} failed: {failed['summary']} - simulated apply failure")
        self.previewer, self.editor = FailingPreviewer(), conversation.Editor(self.repo.state, self.editor.registry)
        self.conv = self.open()
        applied = self.apply("desc")
        self.assertEqual(applied["state"], "applied")
        self.assertEqual(self.status()[-1], f"Last change: {applied['code']} applied: {applied['summary']} "
                                            f"({applied['commit'][:7]}) - not verified: simulated check failure")
        self.assertEqual(self.commits(), 1)

    def test_undo_while_paused_is_proposed_but_gated(self):
        done = self.apply("desc")
        self.assertEqual(self.say("pause changes"), "pause")
        self.sent()
        self.assertEqual(self.say(f"undo {done['code']}"), "proposed")
        [reply] = self.sent()
        self.assertTrue(reply["text"].endswith("\n" + conversation.PAUSED_LINE), reply["text"])
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
        self.assertEqual(lines[-2:], ["Hike Open hike 2026-11-20 09:00 PST: 0 confirmed of no limit",
                                      "Hike Test hike 2026-12-05 09:00 PST: 5 confirmed of 12"])
        text = "\n".join(lines)
        for absent in ("Past hike", "Cancelled hike", "example.invalid", "guest1", "Placeholder"):
            self.assertNotIn(absent, text)

    def test_unknown_counts_are_never_guessed(self):
        wrong = self.rsvp_db("wrong.sqlite3", [], schema="CREATE TABLE other(id INTEGER)")
        for path in (None, "", str(self.repo.state.parent / "missing.sqlite3"), wrong):
            with self.subTest(path=path):
                self.use(path)
                self.assertEqual(self.status()[-2:], ["Hike Open hike 2026-11-20 09:00 PST: guest count unavailable",
                                                      "Hike Test hike 2026-12-05 09:00 PST: guest count unavailable"])
        self.assertFalse((self.repo.state.parent / "missing.sqlite3").exists())

    def test_unreadable_content_gives_one_line(self):
        (self.repo.wt / "hass/content/community.json").write_text("{", "utf-8")
        self.assertEqual(self.status()[-1], "Hikes: unavailable")
        (self.repo.wt / "hass/content/community.json").write_text(json.dumps({"events": [{"status": "scheduled"}]}))
        self.assertEqual(self.status()[-1], "Hikes: unavailable")


if __name__ == "__main__":
    unittest.main()

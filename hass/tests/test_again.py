"""AV2152-03 (H05/H16): `again <code>` re-drafts a proposal that expired in the last 7 days as a NEW proposal (new code, fresh
expiry), with no interpreter call, only when the site as it is now would end every record it touches with the values the
expired draft showed. It still needs `yes <new code>`.
Run: python3 -B -m unittest hass.tests.test_again -v
"""

import itertools
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from hass import conversation, voice
from hass.tests.test_commands_doc import verb
from hass.tests.test_conversation import CHAT, GROUP, OWNER, SETTINGS, STRANGER, ConversationTestCase, _ops
from hass.tests.test_editor import DESC, HOURS, NEW_HOURS, git

USAGE = "Send again and an expired draft code, e.g. again a1b2."
PRODUCT = "photo-product-001"
OTHER_PRODUCT = "photo-product-016"
WEEK = timedelta(days=7)


def drift(code):
    return f"the site changed since {code}; send the change again"


class ParserTests(unittest.TestCase):
    def test_whole_command_only_with_the_rest_kept(self):
        parse = conversation.parse_command
        for text in ("again a1b2", " AGAIN A1B2 ", "Again a1b2.", "again a1b2!"):
            self.assertEqual(parse(text), ("again", "a1b2"), text)
        self.assertEqual(parse("again"), ("again", ""))
        self.assertEqual(parse("again a1b2 please"), ("again", "a1b2 please"))
        self.assertEqual(parse("again a1b2?"), ("again", "a1b2?"))  # a ? is not a read-only command's question mark
        for text in ("againplease", "please again a1b2", "again-a1b2", "a1b2 again"):
            self.assertIsNone(parse(text), text)
        self.assertEqual(verb("again a1b2"), "again")

    def test_final_values_compare_whole_after_with_json_types(self):
        final = conversation.Conversation._again_final
        rec = lambda after, key="k", col="c": {"collection": col, "key": key, "before": None, "after": after}  # noqa: E731
        base = final([rec({"a": 1, "b": [1, 2]})])
        self.assertEqual(base, final([rec({"b": [1, 2], "a": 1})]))  # object key order is ignored
        self.assertEqual(final([rec({"x": 0}), rec({"a": 1, "b": [1, 2]})]), base)  # the last after of a repeated record wins
        self.assertEqual(final([{**rec({"a": 1, "b": [1, 2]}), "before": {"zzz": 1}}]), base)  # before is never compared
        for name, other in (("list order", rec({"a": 1, "b": [2, 1]})), ("bool vs number", rec({"a": True, "b": [1, 2]})),
                            ("float vs int", rec({"a": 1.0, "b": [1, 2]})), ("null field", rec({"a": 1, "b": None})),
                            ("another field", rec({"a": 1, "b": [1, 2], "c": 3})), ("deleted record", rec(None)),
                            ("another key", rec({"a": 1, "b": [1, 2]}, key="j")), ("another collection", rec({"a": 1, "b": [1, 2]}, col="d"))):
            self.assertNotEqual(base, final([other]), name)
        self.assertNotEqual(final([rec(None)]), final([rec({})]))
        self.assertEqual(final([rec(None)]), final([rec(None)]))  # a deletion equals a deletion
        self.assertNotEqual(final([rec({})]), final([rec({}), rec({}, key="extra")]))  # an extra touched key
        for bad in (None, [], {}, [1], [{"collection": "c", "key": "k"}], [{"collection": "c", "key": 1, "after": {}}], [rec(float("nan"))]):
            self.assertIsNone(final(bad), bad)


class AgainTestCase(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping.update({
            "both": _ops((HOURS, {"hours": NEW_HOURS}), (DESC, {"id": PRODUCT, "description": "Ripe and creamy."})),
            "twice": _ops((HOURS, {"hours": ["Monday 1pm"]}), (HOURS, {"hours": NEW_HOURS})),
            "half": {"ops": [{"op": HOURS, "args": {}}], "revises": None}})
        self.asked, self.names = [], itertools.count()
        real = self.interp.interpret
        self.interp.interpret = lambda *a, **k: (self.asked.append(a[0]), real(*a, **k))[1]

    # -- helpers ---------------------------------------------------------------------------------------------------
    def lapse(self, text="hours", after=1):
        """Propose `text`, then move the clock `after` seconds past its expiry (not swept yet)."""
        draft, _ = self.propose(text)
        self.now = datetime.fromisoformat(draft["expires_at"]) + timedelta(seconds=after)
        return draft

    def again(self, code, expect="again"):
        self.asked.clear()
        self.assertEqual(self.say(f"again {code}"), expect)
        self.assertEqual(self.asked, [])  # never the interpreter
        return self.replies()

    def sweep(self):
        """Any command that is not read-only expires what has lapsed; `undo` with nothing to undo changes nothing else."""
        self.say("undo")
        self.replies()

    def row(self, code):
        return next(d for d in self.drafts() if d["code"] == code)

    def approvals(self):
        return self.conv.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0]

    def artifact(self, draft):
        return self.repo.state / "drafts" / f"{draft['change_id']}.json"

    def tamper(self, draft, change):
        """Edit the stored artifact of a draft (and nothing else): change(doc) mutates the parsed JSON."""
        doc = json.loads(self.artifact(draft).read_text("utf-8"))
        change(doc)
        self.artifact(draft).write_text(json.dumps(doc, indent=2, sort_keys=True), "utf-8")

    def edit_product(self, pid, **fields):
        """Commit a change to one product record of the writer worktree (the site moved on); no field = a new name."""
        path = self.repo.wt / "hass/content/products.json"
        doc = json.loads(path.read_text("utf-8"))
        next(p for p in doc["products"] if p["id"] == pid).update(fields or {"name": f"Renamed {next(self.names)}"})
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8")
        git(self.repo.wt, "commit", "-q", "-a", "-m", "site moved on")
        self.base = self.count()  # the site's own commits are not this conversation's

    def refused(self, code, text):
        """`again <code>` is answered with exactly `text`, makes no row, moves no state and approves or saves nothing."""
        self.sweep()
        before = self.drafts()
        self.assertEqual(self.again(code), [text])
        self.assertEqual(self.drafts(), before)
        self.assertEqual((self.editor.applies, self.commits(), self.approvals()), (0, 0, 0))


class RedraftTests(AgainTestCase):
    def test_again_expired_same_site_new_code_ttl_and_yes(self):
        old = self.lapse()
        [reply] = self.again(old["code"].upper() + ".", "proposed")
        self.assertEqual(len(self.drafts()), 2)
        old_after, new = self.drafts()
        self.assertEqual((old_after["state"], old_after["expires_at"], old_after["reason"]), ("expired", old["expires_at"], None))
        self.assertEqual((new["state"], new["reason"]), ("proposed", f"again:{old['code']}"))
        self.assertNotEqual(new["code"], old["code"])
        self.assertEqual(new["expires_at"], (self.now + timedelta(seconds=600)).isoformat())
        self.assertEqual(new["proposed_at"], self.now.isoformat())
        self.assertEqual((new["ops_json"], new["summary"]), (old["ops_json"], old["summary"]))
        self.assertTrue(reply.startswith(f"Again {old['code']}:\nHere's the change I'd make:\n"), reply)
        self.assertIn(f"Reply yes {new['code']} to save it, or no to cancel.", reply)  # always the new code
        self.assertEqual((self.editor.applies, self.commits(), self.approvals()), (0, 0, 0))
        self.assertEqual(self.say("yes"), "no-target")  # a bare yes never approves it
        self.assertEqual(self.say(f"yes {old['code']}"), "no-target")  # nor does the old code
        self.assertEqual((self.commits(), self.row(new["code"])["state"]), (0, "proposed"))
        self.replies()
        self.assertEqual(self.say(f"yes {new['code']}"), "approved")
        self.assertEqual((self.commits(), self.row(new["code"])["state"], self.row(old["code"])["state"]), (1, "applied", "expired"))
        self.assertEqual(json.loads((self.repo.wt / "hass/content/store.json").read_text("utf-8"))["hours"], NEW_HOURS)

    def test_again_unrelated_record_passes_and_a_new_base_still_needs_the_code(self):
        old = self.lapse("both")
        self.edit_product(OTHER_PRODUCT)  # another record: the base moves, the end values do not
        self.again(old["code"], "proposed")
        new = self.drafts()[-1]
        self.assertNotEqual((new["base"], new["draft_hash"]), (old["base"], old["draft_hash"]))
        self.assertEqual(self.say("yes"), "no-target")  # its hash is new, so only the named yes counts
        self.assertEqual(self.replies(), [f"That change was written up again from an expired one, so I want to be sure. Reply yes {new['code']} if you still want it."])
        self.assertEqual(self.say(f"yes {new['code']}"), "approved")
        self.assertEqual(self.commits(), 1)

    def test_again_touched_field_drift_refuses(self):
        old = self.lapse("desc")
        self.edit_product(PRODUCT)  # same record, another field: it would ride along
        self.refused(old["code"], drift(old["code"]))
        old = self.lapse("both")
        self.edit_product(PRODUCT)  # the hours still match; one of two records does not
        self.refused(old["code"], drift(old["code"]))

    def test_again_extra_or_missing_touched_key_refuses_and_record_order_does_not_matter(self):
        extra = {"collection": "products", "key": "zzz", "before": None, "after": {}}
        for name, change, ok in (("extra key", lambda d: d["records"].append(extra), False), ("missing key", lambda d: d["records"].pop(), False),
                                 ("order", lambda d: d["records"].reverse(), True)):
            with self.subTest(name):
                old = self.lapse("both")
                self.edit_product(OTHER_PRODUCT)  # a new base, so the draft is prepared fresh and the stored one is compared
                self.tamper(old, change)
                if ok: self.again(old["code"], "proposed")
                else: self.refused(old["code"], drift(old["code"]))

    def test_again_repeated_touches_compare_the_last_after(self):
        old = self.lapse("twice")
        self.edit_product(OTHER_PRODUCT)
        self.assertEqual([r["collection"] for r in json.loads(self.artifact(old).read_text("utf-8"))["records"]], ["store", "store"])
        self.again(old["code"], "proposed")  # the same end hours, however many times they were touched

    def test_again_prepare_refusal_question_or_no_op_refuses(self):
        old = self.lapse("desc")
        path = self.repo.wt / "hass/content/products.json"
        doc = json.loads(path.read_text("utf-8"))
        doc["products"] = [p for p in doc["products"] if p["id"] != PRODUCT]
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8")
        git(self.repo.wt, "commit", "-q", "-a", "-m", "the product is gone")
        self.base = self.count()
        self.refused(old["code"], drift(old["code"]))  # the record it changed is gone: not found
        for out in ({"result": "refused", "reason": "the operations change nothing"}, {"result": "needs-details", "question": "Which one?"},
                     {"result": "invalid", "problems": ["x"]}, {"result": "ok", "draft": {"records": []}}, {"result": "ok", "draft": {"records": [3]}}):
            with self.subTest(out=out), mock.patch.object(self.editor, "prepare", return_value=out):
                self.refused(old["code"], drift(old["code"]))
        with mock.patch.object(self.editor, "prepare", side_effect=RuntimeError("boom")):
            self.refused(old["code"], drift(old["code"]))


class WindowTests(AgainTestCase):
    def test_again_window_boundary_and_unswept_expiry(self):
        for name, after in (("at its expiry", 0), ("a second after", 1), ("exactly seven days", int(WEEK.total_seconds()))):
            with self.subTest(name):
                old = self.lapse("hours", after)
                self.assertEqual(self.row(old["code"])["state"], "proposed")  # lapsed, not swept
                self.again(old["code"], "proposed")
                self.assertEqual(self.row(old["code"])["state"], "expired")  # the ordinary sweep ran first
                self.assertEqual(self.drafts()[-1]["reason"], f"again:{old['code']}")
                self.say("no")
                self.replies()
        old = self.lapse("hours", int(WEEK.total_seconds()) + 1)
        self.refused(old["code"], f"{old['code']} expired more than 7 days ago; send the change again.")

    def test_again_dst_and_offset_instants(self):
        old = self.lapse("hours", 0)
        self.sweep()
        self.assertEqual(self.row(old["code"])["state"], "expired")
        pst = datetime(2026, 11, 1, 9, 30, tzinfo=timezone.utc)  # 01:30 PST, the second 01:30 of the day DST ended
        for name, text, now in (("same instant, pst offset", "2026-11-01T01:30:00-08:00", pst + WEEK),
                                ("pdt offset is an hour earlier", "2026-11-01T01:30:00-07:00", pst + WEEK),
                                ("india offset", pst.astimezone(ZoneInfo("Asia/Kolkata")).isoformat(), pst + WEEK)):
            with self.subTest(name):
                self.conv.db.execute("UPDATE drafts SET expires_at = ? WHERE row_id = ?", (text, old["row_id"]))
                self.now = now
                if name.startswith("pdt"):
                    self.refused(old["code"], f"{old['code']} expired more than 7 days ago; send the change again.")
                else:
                    self.again(old["code"], "proposed")
                    self.say("no")
                    self.replies()

    def test_again_bad_missing_naive_or_future_expiry_fails_closed(self):
        old = self.lapse("hours", 0)
        self.sweep()
        for name, value in (("missing", None), ("bad", "not a time"), ("naive", "2026-11-02T17:10:00"),
                            ("future", (self.now + timedelta(seconds=1)).isoformat())):
            with self.subTest(name):
                self.conv.db.execute("UPDATE drafts SET expires_at = ? WHERE row_id = ?", (value, old["row_id"]))
                self.refused(old["code"], f"{old['code']}: the draft details are not available any more.")

    def test_again_artifact_missing_or_not_the_rows_draft_refuses(self):
        for name, change in (("missing artifact", lambda d: self.artifact(d).unlink()),
                             ("other ops", lambda d: self.tamper(d, lambda doc: doc.update(ops=[]))),
                             ("other hash", lambda d: self.tamper(d, lambda doc: doc.update(draft_hash="sha256:" + "0" * 64))),
                             ("other base", lambda d: self.tamper(d, lambda doc: doc.update(base="sha256:" + "1" * 64))),
                             ("no records", lambda d: self.tamper(d, lambda doc: doc.update(records=[]))),
                             ("odd records", lambda d: self.tamper(d, lambda doc: doc.update(records=["x"])))):
            with self.subTest(name):
                old = self.lapse("hours", 1)
                change(old)
                self.refused(old["code"], f"{old['code']}: the draft details are not available any more.")
                self.artifact(old).unlink(missing_ok=True)


class StateTests(AgainTestCase):
    def test_again_each_ineligible_state(self):
        waiting, _ = self.propose("hours")
        self.refused(waiting["code"], f"{waiting['code']} is still waiting for your yes, so there is nothing to draft again.")
        self.assertEqual(self.say("no"), "rejected")
        self.replies()
        self.refused(waiting["code"], "That one was cancelled, so nothing changed.")
        self.assertEqual(self.say("half"), "needs-details")
        self.replies()
        asking = self.drafts()[-1]
        self.refused(asking["code"], f"{asking['code']} is still waiting for details, so there is nothing to draft again.")
        self.now += timedelta(seconds=601)  # the question lapses: an expired question has nothing prepared
        self.refused(asking["code"], f"{asking['code']} expired before it was a proposal; send the change again.")
        self.assertEqual(self.drafts()[-1]["state"], "expired")
        for state, text in (("approved", "That one is being saved."), ("applied", "That one is already saved."),
                            ("verified", "That one is already saved."), ("failed", "That one couldn't be saved."),
                            ("reverted", f"{waiting['code']}: the draft details are not available any more.")):  # AV2137-01: undone drafts need the linked undo
            with self.subTest(state):
                self.conv.db.execute("UPDATE drafts SET state = ? WHERE row_id = ?", (state, waiting["row_id"]))
                self.refused(waiting["code"], text)
        self.conv.db.execute("UPDATE drafts SET state = 'rejected', reason = 'revised', replaced_by = 'abcd' WHERE row_id = ?", (waiting["row_id"],))
        self.refused(waiting["code"], "That one was replaced by a newer one.")

    def test_again_unknown_code_and_usage(self):
        self.refused("ffff", "No draft ffff.")
        for text in ("again", "again ", "again abc", "again a1b2c3d4e5f60", "again xyz1", "again a1b2 a1b2", "again a1b2?", "again 12345678\n9"):
            with self.subTest(text=text):
                before = self.drafts()
                self.assertEqual(self.say(text), "again")
                self.assertEqual(self.replies(), [USAGE])
                self.assertEqual(self.drafts(), before)
        for code in ("abcd", "abcdef012345"):  # 4 and 12 character codes are well formed: an unknown one is "No draft"
            self.assertEqual(self.say(f"again {code}"), "again")
            self.assertEqual(self.replies(), [f"No draft {code}."])
        self.assertEqual(self.asked, [])

    def test_again_photo_drafts_are_refused(self):
        sha = "a" * 64
        for name, change in (("set_photo", lambda ops: ops.append({"op": "product.set_photo", "args": {"id": PRODUCT, "photo": sha, "imageAlt": "x"}})),
                             ("home image", lambda ops: ops.append({"op": "store.set_home_image", "args": {"photo": sha, "imageAlt": "x"}})),
                             ("args.photo", lambda ops: ops[0]["args"].update(photo=sha)),
                             ("product.add photo", lambda ops: ops.append({"op": "product.add", "args": {"photo": sha}}))):
            with self.subTest(name):
                old = self.lapse("hours", 1)
                ops = json.loads(old["ops_json"])
                change(ops)
                self.conv.db.execute("UPDATE drafts SET ops_json = ? WHERE row_id = ?", (json.dumps(ops, sort_keys=True), old["row_id"]))
                self.tamper(old, lambda doc: doc.update(ops=ops))
                self.refused(old["code"], f"{old['code']} is a photo draft; send the photo again.")
                self.artifact(old).unlink()
        with self.subTest("assets"):
            old = self.lapse("hours", 1)
            self.tamper(old, lambda doc: doc.update(assets={"assets/products/photo-x.jpg": "sha256:" + "2" * 64}))
            self.refused(old["code"], f"{old['code']} is a photo draft; send the photo again.")


class ApprovalTests(AgainTestCase):
    def test_again_named_yes_after_restart_stale_and_drift(self):
        old = self.lapse("both")
        self.again(old["code"], "proposed")
        new = self.drafts()[-1]
        self.conv = self.open()  # restart: the marker is stored, not remembered
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual(self.say("Approve!"), "no-target")
        self.assertEqual((self.commits(), self.editor.applies), (0, 0))
        self.replies()
        self.edit_product(OTHER_PRODUCT)  # the base moves while it waits: apply says stale, the end values are the same
        self.assertEqual(self.say(f"yes {new['code']}"), "approved")
        [moved] = self.replies()
        self.assertTrue(moved.startswith("The website changed while that was waiting, so I've written it up again."), moved)
        again = self.drafts()[-1]
        self.assertEqual((self.row(new["code"])["state"], again["state"], again["reason"]), ("rejected", "proposed", f"again:{old['code']}"))
        self.assertEqual(self.commits(), 0)
        self.assertEqual(self.say("yes"), "no-target")  # the successor still needs its own code
        self.replies()
        self.edit_product(PRODUCT)  # now a touched record moves while it waits: never a changed outcome
        before = len(self.drafts())
        self.assertEqual(self.say(f"yes {again['code']}"), "approved")
        self.assertEqual(self.replies(), [f"The website changed while that was waiting, and now that change would end differently, so nothing changed. "
                                          f"Send the change again (it was written up again from {old['code']})."])
        self.assertEqual((len(self.drafts()), self.row(again["code"])["state"], self.commits()), (before, "rejected", 0))

    def test_again_old_code_and_cancelled_successor_do_not_approve(self):
        old = self.lapse()
        self.again(old["code"], "proposed")
        self.assertEqual(self.say(f"yes {old['code']}"), "no-target")
        self.assertEqual(self.replies(), [f"That change timed out {self.conv._when(old['expires_at'])}, so nothing changed. Tell me again if you still want it."])
        self.assertEqual(self.say("no"), "rejected")  # cancelling the new one is ordinary
        self.assertEqual((self.drafts()[0]["state"], self.drafts()[-1]["state"]), ("expired", "rejected"))
        self.assertEqual(self.say("yes"), "no-target")
        self.assertEqual((self.commits(), self.approvals()), (0, 0))

    def test_again_paused_and_usage_exhausted(self):
        self.set_settings({**SETTINGS, "interpreterDailyCap": 1})
        self.conv = self.open()
        old = self.lapse()
        self.assertEqual(self.conv._calls(self.now)[1], 1)  # the cap is used up
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        [reply] = self.again(old["code"], "proposed")
        self.assertTrue(reply.endswith(voice.plain(conversation.PAUSED_LINE)), reply)  # preparing is allowed, with the usual paused line
        self.assertEqual(self.conv._calls(self.now)[1], 1)  # no model call counted
        new = self.drafts()[-1]
        self.assertEqual(self.say(f"yes {new['code']}"), "paused")
        self.assertEqual((self.commits(), self.editor.applies, self.approvals(), self.row(new["code"])["state"]), (0, 0, 0, "proposed"))

    def test_again_twice_makes_separately_coded_proposals(self):
        old = self.lapse()
        self.again(old["code"], "proposed")
        self.again(old["code"], "proposed")
        codes = [d["code"] for d in self.drafts()]
        self.assertEqual((len(codes), len(set(codes))), (3, 3))
        self.assertEqual([d["state"] for d in self.drafts()], ["expired", "proposed", "proposed"])


class ReplayAndHelpTests(AgainTestCase):
    def test_again_auth_replay_echo_reaction_and_attachment(self):
        old = self.lapse()
        self.asked.clear()
        before = self.drafts()
        self.assertEqual(self.say(f"again {old['code']}", sender=STRANGER), "ignored")
        self.assertEqual(self.say(f"again {old['code']}", chat=GROUP), "ignored")
        self.assertEqual(self.say(f"again {old['code']}", from_me=True), "echo")
        self.assertEqual(self.say(f"again {old['code']}", kind="reaction"), "not-read")
        self.assertEqual(self.say(f"again {old['code']}", kind="edited"), "not-read")
        msg = conversation.Inbound("att1", CHAT, OWNER, f"again {old['code']}", False, "new", self.now.isoformat(), 1)
        self.assertEqual(self.conv.handle(msg), "attachment-unsupported")  # a caption is never a command
        self.assertEqual(self.drafts(), before)
        self.assertEqual(self.asked, [])
        self.replies()
        self.assertEqual(self.say(f"again {old['code']}", pid="dup"), "proposed")
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual((self.say(f"again {old['code']}", pid="dup"), self.replies()), ("duplicate", []))
        self.assertEqual(len(self.drafts()), len(before) + 1)

    def test_again_help_and_docs(self):
        lines = voice.plain(conversation.help_detail("again")).splitlines()  # AV1052-12: the full line is in `help again`
        self.assertEqual(lines, ["again a1b2 - re-draft an expired or undone change (within 7 days)"])
        self.assertEqual(self.say("help again"), "help")
        self.assertEqual(self.replies(), lines)


if __name__ == "__main__":
    unittest.main()

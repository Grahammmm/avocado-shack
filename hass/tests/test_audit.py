"""AVB-10 tests: one audit log for every action (hass/audit.py and the Conversation lines).

Unit tests use a private temp state folder and a fixed clock. Conversation tests use the H06 setup from test_undo (temp Git
repo, linked writer worktree, private 0700 state dir, fake previewer, injected clock); nothing touches live state.
Run: python3 -m unittest hass.tests.test_audit -v
"""

import contextlib, errno, io, json, os, shutil, subprocess, sys, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import audit
from hass.content_model import REPO_ROOT
from hass.conversation import Inbound
from hass.skills.hikes import Refusal
from hass.skills.reports import REPORT_SHELF
from hass.stagelog import short
from hass.tests.test_conversation import CHAT, OWNER, _ops
from hass.tests.test_editor import DESC
from hass.tests.test_skill_dispatch import HIKE_ADD, LIVE1, MILL, SkillCase, skill_reply, toy
from hass.tests.test_undo import H06TestCase

T0 = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)
SCRIPT = REPO_ROOT / "hass" / "audit.py"
TILL: dict = dict(who="owner", pack="till", target="till", env="sandbox", result="ok", draft="7c1e", skill="till.stock@1",
            refs={"till": "tj-0123abcd"}, subjects=["items:hass-avocado"], fields=["stock"])
PRIVATE_TEXT = "kumquat desc $12.50 call +1 805 555 0142"  # owner words, a price and a phone number: none may reach the log
ACT, APPROVE = audit.new_action("till", "lf"), dict(approval="A1", approved_by="owner")
MARK = b"!torn\n"  # what closes off a line that stopped before its LF (the audit contract, not read from hass.audit)


def lines(state):
    folder = Path(state) / audit.FOLDER
    return [json.loads(x) for p in sorted(folder.iterdir()) for x in p.read_text("utf-8").splitlines()] if folder.is_dir() else []


class AuditLogTests(unittest.TestCase):
    def setUp(self):
        self.state = Path(tempfile.mkdtemp(prefix="avb10-"))
        os.chmod(self.state, 0o700)
        self.addCleanup(shutil.rmtree, self.state, True)
        self.log = audit.AuditLog(self.state, lambda: T0)

    def test_lines_are_numbered_private_and_append_only(self):
        act = audit.new_action("till", 1)
        self.assertTrue(self.log.record("drafted", action=act, strict=True, **TILL))
        self.assertTrue(self.log.record("approved", action=act, approval="A1", approved_by="owner", strict=True, **TILL))
        day = self.state / audit.FOLDER / "2026-11-13.jsonl"
        first = day.read_text("utf-8").splitlines()
        self.assertEqual([json.loads(x)["seq"] for x in first], [1, 2])
        self.assertEqual(json.loads(first[0]), {"at": "2026-11-13T21:00:00Z", "seq": 1, "action": act, "step": "drafted", **TILL})
        self.assertEqual(oct(day.stat().st_mode & 0o777), "0o600")
        self.assertEqual(oct((self.state / audit.FOLDER).stat().st_mode & 0o777), "0o700")
        self.log.record("applied", action=act, **TILL)
        self.assertEqual(day.read_text("utf-8").splitlines()[:2], first)  # earlier lines are never rewritten
        self.assertEqual([r["step"] for r in self.log.rows()], ["drafted", "approved", "applied"])

    def test_rules_refuse_text_prices_numbers_tokens_and_unknown_keys(self):
        base = {"at": "2026-11-13T21:00:00Z", "seq": 1, "action": audit.new_action("x"), "step": "applied", **TILL}
        self.assertEqual(audit.check(base), [])
        bad = {"text": ({"text": "two avocados please"}, "unknown key: text"),
               "price": ({"fields": ["$12.50"]}, "bad value: fields"),
               "phone who": ({"who": "+18055550142"}, "bad value: who"),
               "phone subject": ({"subjects": ["items:8055550142"]}, "digit run: subjects"),
               "count": ({"fields": ["stock12345"]}, "digit run: fields"),
               "sentence result": ({"result": "the till said no"}, "bad value: result"),
               "token ref": ({"refs": {"token": "not-a-real-token"}}, "bad value: refs"),
               "approved without who": ({"step": "approved"}, "missing: approved_by")}
        for name, (change, problem) in bad.items():
            with self.subTest(name):
                self.assertIn(problem, audit.check({**base, **change}))
        self.assertIn("missing: env", audit.check({k: v for k, v in base.items() if k != "env"}))
        self.assertFalse(self.log.record("applied", action=base["action"], **{**TILL, "fields": ["$12.50"]}))
        with self.assertRaises(audit.AuditError):
            self.log.record("applied", action=base["action"], strict=True, **{**TILL, "who": "+18055550142"})
        self.assertEqual(lines(self.state), [])  # a refused line is never written, not even in part

    def test_a_linked_or_shared_folder_or_file_is_refused(self):
        elsewhere = Path(tempfile.mkdtemp(prefix="avb10-elsewhere-"))
        self.addCleanup(shutil.rmtree, elsewhere, True)
        os.symlink(elsewhere, self.state / audit.FOLDER)
        act = audit.new_action("x")
        self.assertFalse(self.log.record("applied", action=act, **TILL))
        with self.assertRaises(audit.AuditError):
            self.log.record("applied", action=act, strict=True, **TILL)
        self.assertEqual(list(elsewhere.iterdir()), [])
        os.unlink(self.state / audit.FOLDER)
        (self.state / audit.FOLDER).mkdir(mode=0o700)
        os.symlink(elsewhere / "x.jsonl", self.state / audit.FOLDER / "2026-11-13.jsonl")
        self.assertFalse(self.log.record("applied", action=act, **TILL))
        self.assertFalse((elsewhere / "x.jsonl").exists())

    def test_reader_and_check_skip_and_count_bad_lines(self):
        act = audit.new_action("x")
        self.log.record("applied", action=act, strict=True, **TILL)
        day = self.state / audit.FOLDER / "2026-11-13.jsonl"
        with open(day, "a", encoding="utf-8") as fh:
            fh.write("not json\n" + json.dumps({**json.loads(day.read_text("utf-8")), "note": "hello"}) + "\n")
        self.assertEqual(len(self.log.rows()), 1)
        self.log.record("verified", action=act, **TILL)
        self.assertEqual([r["seq"] for r in self.log.rows()], [1, 4])  # the number counts every line in the file
        run = subprocess.run([sys.executable, str(SCRIPT), "check", "--state", str(self.state)], capture_output=True, text=True)
        self.assertEqual((run.returncode, json.loads(run.stdout)), (1, {"result": "bad", "lines": 2, "bad": 2, "days": 1}))

    def test_subjects_and_fields_hold_ids_and_names_only(self):
        records = [{"collection": "products", "key": "photo-product-001", "before": {"description": "Old.", "price": 1250},
                    "after": {"description": "New.", "price": 1250}},
                   {"collection": "store", "key": None, "before": {"hours": "9-5"}, "after": {"hours": "8-5"}},
                   {"collection": "products", "key": "call-8055550142", "before": None, "after": {"name": "x"}}]
        self.assertEqual(audit.subjects_of(records), ["products:photo-product-001", "store"])
        self.assertEqual(audit.fields_of(records), ["description", "hours", "record"])

    # -- a write that does not finish (review round 1, finding 1) ---------------------------------------------------
    def _writes(self, *plan):
        """Patch os.write: each call takes the next of `plan` (n: write the first n bytes for real; an exception: raise it);
        when the plan runs out, writes go through whole."""
        real, steps = os.write, list(plan)

        def fake(fd, data):
            if not steps: return real(fd, data)
            step = steps.pop(0)
            if isinstance(step, BaseException): raise step
            return real(fd, bytes(data[:step])) if step else 0  # a negative n: all but the last -n bytes
        return mock.patch.object(audit.os, "write", fake)

    def test_a_short_write_is_finished_before_record_says_yes(self):
        act = audit.new_action("short")
        with self._writes(20, 7, 1):  # three short writes, then the rest whole
            self.assertTrue(self.log.record("approved", action=act, approval="A1", approved_by="owner", strict=True, **TILL))
        [row] = self.log.rows()
        self.assertEqual((row["action"], row["step"], row["seq"]), (act, "approved", 1))
        day = self.state / audit.FOLDER / "2026-11-13.jsonl"
        self.assertEqual(day.read_bytes().count(b"\n"), 1)

    def test_a_write_that_stops_is_refused_keeps_earlier_lines_and_is_detectable(self):
        act = audit.new_action("stops")
        self.assertTrue(self.log.record("drafted", action=act, strict=True, **TILL))
        day = self.state / audit.FOLDER / "2026-11-13.jsonl"
        first = day.read_bytes()
        for name, plan in {"partial then error": (20, OSError(errno.ENOSPC, "full")), "no progress": (0,),
                           "error": (OSError(errno.EIO, "io"),)}.items():
            with self.subTest(name):
                with self._writes(*plan), self.assertRaises(audit.AuditError):
                    self.log.record("approved", action=act, approval="A1", approved_by="owner", strict=True, **TILL)
                with self._writes(*plan):
                    self.assertFalse(self.log.record("approved", action=act, approval="A1", approved_by="owner", **TILL))
                self.assertTrue(day.read_bytes().startswith(first))  # the earlier line is untouched
                self.assertEqual([r["step"] for r in self.log.rows()], ["drafted"])  # no approved line was kept
        self.assertTrue(self.log.record("approved", action=act, approval="A1", approved_by="owner", strict=True, **TILL))
        self.assertEqual([r["step"] for r in self.log.rows()], ["drafted", "approved"])  # the next line stands on its own
        run = subprocess.run([sys.executable, str(SCRIPT), "check", "--state", str(self.state)], capture_output=True, text=True)
        self.assertEqual((run.returncode, json.loads(run.stdout)["lines"], json.loads(run.stdout)["bad"]), (1, 2, 2))  # the two torn ends

    # -- a write that stops just before its LF, and the next write after one that stopped (review round 2) ------------
    def _fresh(self, torn_approval=False):
        """A new state folder: one drafted line; with torn_approval, then an approved line that stopped just before its LF."""
        state = Path(tempfile.mkdtemp(prefix="avb10-lf-"))
        os.chmod(state, 0o700)
        self.addCleanup(shutil.rmtree, state, True)
        log = audit.AuditLog(state, lambda: T0)
        self.assertTrue(log.record("drafted", action=ACT, strict=True, **TILL))
        if torn_approval:
            with self._writes(-1, OSError(errno.ENOSPC, "full")), self.assertRaises(audit.AuditError):
                log.record("approved", action=ACT, strict=True, **APPROVE, **TILL)
        return state, log, state / audit.FOLDER / "2026-11-13.jsonl"

    @staticmethod
    def _cli(state, *args):
        """The command line's own main(), in this process: (exit code, what it printed)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out): code = audit.main([*args, "--state", str(state)])
        return code, out.getvalue()

    def _check(self, state):
        code, out = self._cli(state, "check")
        got = json.loads(out)
        return code, got["lines"], got["bad"]

    def _only(self, state, log, steps):
        """The records are exactly `steps`; no approved line reaches the reader, history or the command line."""
        self.assertEqual([r["step"] for r in log.rows()], steps)
        self.assertEqual((log.approved(10), log.approved_drafts()), ([], set()))
        self.assertEqual([json.loads(x)["step"] for x in self._cli(state, "show")[1].splitlines()], steps)
        self.assertEqual(self._cli(state, "history"), (0, "no approved actions\n"))

    def test_a_write_that_stops_just_before_its_lf_is_never_a_record(self):
        state, log, day = self._fresh()
        first = day.read_bytes()
        with self._writes(-1, OSError(errno.ENOSPC, "full")), self.assertRaises(audit.AuditError):
            log.record("approved", action=ACT, strict=True, **APPROVE, **TILL)
        torn = day.read_bytes()[len(first):]
        self.assertEqual((torn[:1], torn[-1:], json.loads(torn)["step"]), (b"{", b"}", "approved"))  # only the LF is missing
        self._only(state, log, ["drafted"])
        self.assertEqual(self._check(state), (1, 1, 1))
        run = subprocess.run([sys.executable, str(SCRIPT), "check", "--state", str(state)], capture_output=True, text=True)
        self.assertEqual((run.returncode, json.loads(run.stdout)), (1, {"result": "bad", "lines": 1, "bad": 1, "days": 1}))
        # the next line closes the torn one off with `!torn` LF: kept byte for byte, bad for good, with its own number
        self.assertTrue(log.record("refused", action=ACT, strict=True, **{**TILL, "result": "said-no"}))
        self.assertTrue(day.read_bytes().startswith(first + torn + MARK))
        self.assertEqual([r["seq"] for r in log.rows()], [1, 3])
        self._only(state, log, ["drafted", "refused"])
        self.assertEqual(self._check(state), (1, 2, 1))
        self.assertTrue(log.record("refused", action=ACT, strict=True, **{**TILL, "result": "said-no"}))
        self.assertEqual(self._check(state), (1, 3, 1))  # still one bad line: it never turns into a record
        self.assertEqual(audit.TORN, MARK)
        # the same stop without strict says False and leaves the same bytes
        state, log, day = self._fresh()
        with self._writes(-1, OSError(errno.ENOSPC, "full")):
            self.assertFalse(log.record("approved", action=ACT, **APPROVE, **TILL))
        self.assertEqual(day.read_bytes(), first + torn)
        self._only(state, log, ["drafted"])

    def test_every_stop_in_a_line_or_in_the_line_after_a_torn_one_stays_out_and_later_lines_are_safe(self):
        """All-prefix sweep. Stage `line`: an approved line stops after k of its bytes. Stage `recovery`: on drafted + an
        approved line torn just before its LF, the next approved line (`!torn` LF + the line) stops after k bytes: in the
        marker, just after it, or anywhere in the new line up to just before its LF. Then a healthy line is written."""
        for stage in ("line", "recovery"):
            _, log, day = self._fresh(stage == "recovery")  # the whole write, to learn its bytes (the control)
            before = day.read_bytes()
            self.assertTrue(log.record("approved", action=ACT, strict=True, **APPROVE, **TILL))
            payload = day.read_bytes()[len(before):]
            self.assertEqual([(r["step"], r["seq"]) for r in log.rows()][1:], [("approved", 2 if stage == "line" else 3)])
            self.assertEqual(payload.startswith(MARK), stage == "recovery")
            for k in range(len(payload)):  # 0 is a write that makes no progress
                with self.subTest(stage=stage, k=k):
                    state, log, day = self._fresh(stage == "recovery")
                    before, strict = day.read_bytes(), k % 2 == 0
                    with self._writes(k, OSError(errno.ENOSPC, "full")):
                        if strict:
                            with self.assertRaises(audit.AuditError):
                                log.record("approved", action=ACT, strict=True, **APPROVE, **TILL)
                        else:
                            self.assertFalse(log.record("approved", action=ACT, **APPROVE, **TILL))
                    stopped = day.read_bytes()
                    self.assertEqual(stopped, before + payload[:k])  # only what was written; nothing before it changed
                    if stage == "line": bad, seq = (0, 2) if k == 0 else (1, 3)
                    else: bad, seq = (1, 3) if k <= len(MARK) else (2, 4)  # a second torn line counts as one more
                    self._only(state, log, ["drafted"])
                    self.assertEqual(self._check(state), (1 if bad else 0, 1, bad))
                    self.assertTrue(log.record("refused", action=ACT, strict=True, **{**TILL, "result": "said-no"}))
                    self.assertTrue(day.read_bytes().startswith(stopped))
                    self.assertEqual([r["seq"] for r in log.rows()], [1, seq])
                    self._only(state, log, ["drafted", "refused"])
                    self.assertEqual(self._check(state), (1 if bad else 0, 2, bad))

    def test_only_the_lf_byte_ends_a_record(self):
        self.assertTrue(self.log.record("drafted", action=ACT, strict=True, **TILL))
        day = self.state / audit.FOLDER / "2026-11-13.jsonl"
        line = day.read_bytes()[:-1]
        others = [line + b"\r\n", b" " + line + b"\n", line + b" \n", line.replace(b",", b", ", 1) + b"\n",
                  line[:-1] + b',"seq":1}\n']  # a CR, spaces, or a key twice: not the bytes record() writes
        with open(day, "ab") as fh: fh.write(b"".join(others) + line + b"\r")  # and an end with a CR but no LF
        self.assertEqual([r["seq"] for r in self.log.rows()], [1])
        self.assertEqual(self._check(self.state), (1, 1, len(others) + 1))
        self.assertTrue(self.log.record("refused", action=ACT, strict=True, **{**TILL, "result": "said-no"}))
        self.assertIn(line + b"\r" + MARK, day.read_bytes())
        self.assertEqual([(r["step"], r["seq"]) for r in self.log.rows()], [("drafted", 1), ("refused", len(others) + 3)])
        self.assertEqual(self._check(self.state), (1, 2, len(others) + 1))

    # -- where a till change stands (review round 1, finding 3) -----------------------------------------------------
    def test_till_history_says_only_what_the_lines_show(self):
        unsure = "I'm not sure where it stands, so please check it"
        cases = {"checked": ([("applied", "ok"), ("verified", "ok")], "saved and checked"),
                 "check failed": ([("applied", "ok"), ("verified", "not-verified")], "saved, but I couldn't check it, so please look at it"),
                 "saved": ([("applied", "ok")], "saved"),
                 "being saved": ([], "being saved"),
                 "stale before the write": ([("failed", "stale")], "it didn't go through, so nothing changed"),
                 "failed after the write": ([("applied", "ok"), ("failed", "failed")], "something went wrong after it was saved; " + unsure),
                 "failed, not known where": ([("failed", "failed")], unsure),
                 "interrupted": ([("failed", "interrupted")], unsure),
                 "verified with no write": ([("verified", "ok")], unsure)}
        for n, (name, (steps, words)) in enumerate(cases.items()):
            with self.subTest(name):
                act = audit.new_action("till-state", n)
                self.log.record("approved", action=act, approval="A1", approved_by="owner", strict=True, **TILL)
                for step, result in steps: self.log.record(step, action=act, strict=True, **{**TILL, "result": result})
                [entry] = [e for e in self.log.approved(50) if e["action"] == act]
                self.assertEqual(audit.till_line(entry), f"- A change on the test till: {words}.")


class ConversationAuditTests(H06TestCase):
    def setUp(self):
        super().setUp()
        self.interp.mapping[PRIVATE_TEXT] = _ops((DESC, {"id": "photo-product-001", "description": "Ripe and creamy."}))

    def steps(self):
        return [(r["step"], r["result"]) for r in lines(self.repo.state)]

    def test_a_site_change_writes_one_action_with_every_step(self):
        a = self.apply(PRIVATE_TEXT)
        rows = lines(self.repo.state)
        self.assertEqual(self.steps(), [("drafted", "ok"), ("approved", "ok"), ("applied", "ok"), ("verified", "ok")])
        self.assertEqual({r["action"] for r in rows}, {rows[0]["action"]})
        for r in rows:
            self.assertEqual(audit.check(r), [])
            self.assertEqual((r["who"], r["pack"], r["target"], r["env"], r["draft"]), ("owner", "site", "site", "sandbox", a["code"]))
            self.assertEqual(r["refs"]["change"], a["change_id"])
        self.assertEqual(rows[0]["msg"], short("m1"))  # the request
        self.assertEqual((rows[1]["msg"], rows[1]["approval"], rows[1]["approved_by"]), (short("m2"), "A1", "owner"))  # the yes
        self.assertEqual((rows[0]["subjects"], rows[0]["fields"]), (["products:photo-product-001"], ["description"]))
        self.assertEqual(rows[2]["refs"]["commit"], a["commit"])
        raw = b"".join(p.read_bytes() for p in (self.repo.state / audit.FOLDER).iterdir())
        for private in ("kumquat", "12.50", "$", "805 555", "0142 ", "Ripe", "creamy", OWNER, CHAT, a["summary"]):
            self.assertNotIn(private.encode(), raw, private)

    def test_no_and_expiry_are_refused_lines(self):
        self.propose("desc")
        self.assertEqual(self.say("no"), "rejected")
        self.assertEqual(self.say("hours"), "proposed")
        self.now += timedelta(seconds=601)
        self.say("yes")
        self.assertEqual(self.steps(), [("drafted", "ok"), ("refused", "said-no"), ("drafted", "ok"), ("refused", "expired")])

    def test_undo_names_the_action_it_takes_back(self):
        a = self.apply("desc")
        self.assertEqual(self.say(f"undo {a['code']}"), "proposed")
        self.assertEqual(self.say("yes"), "approved")
        rows = lines(self.repo.state)
        undone = [r for r in rows if r["step"] == "undone"]
        self.assertEqual(len(undone), 1)
        self.assertEqual(undone[0]["undo_of"], rows[0]["action"])
        self.assertNotEqual(undone[0]["action"], rows[0]["action"])
        [entry] = [e for e in self.conv.audit.approved(5) if e["action"] == rows[0]["action"]]
        self.assertEqual(entry["undone_by"], undone[0]["action"])

    def test_a_held_approval_leaves_no_approved_line(self):
        self.propose("desc")
        self.assertEqual(self.conv.handle(Inbound("held-yes", CHAT, OWNER, "yes", received_at=self.now.isoformat()), apply=False),
                         "approval-held")
        self.assertEqual(self.steps(), [("drafted", "ok")])

    def test_history_shows_a_site_change_and_a_sandbox_till_change(self):
        """The AVB-10 acceptance: a site change and a sandbox till change both appear, in `history` and on the command line."""
        a = self.apply("desc")
        till = audit.AuditLog(self.repo.state, lambda: self.now)  # what the till engine (AVB-15) writes, strict
        act = audit.new_action("till", "sandbox-1")
        till.record("drafted", action=act, strict=True, **TILL)
        till.record("approved", action=act, approval="A1", approved_by="owner", strict=True, **TILL)
        till.record("applied", action=act, strict=True, **TILL)
        self.assertEqual(self.say("history"), "history")
        [reply] = self.replies()
        self.assertEqual(reply.splitlines()[:2], ["Here's what we changed lately:", "- A change on the test till, approved Mon Nov 2 9:00 am: saved."])
        self.assertEqual(len(reply.splitlines()), 3)
        self.assertIn(a["summary"], reply.splitlines()[2])
        run = subprocess.run([sys.executable, str(SCRIPT), "history", "--state", str(self.repo.state)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        out = run.stdout.splitlines()
        self.assertEqual(len(out), 2)
        self.assertIn("till (sandbox)  till.stock@1  draft 7c1e  applied ok", out[0])
        self.assertIn(f"site (sandbox)  -  draft {a['code']}  verified ok", out[1])
        check = subprocess.run([sys.executable, str(SCRIPT), "check", "--state", str(self.repo.state)], capture_output=True, text=True)
        self.assertEqual((check.returncode, json.loads(check.stdout)["bad"]), (0, 0))

    def test_history_keeps_changes_from_before_the_audit_log(self):
        old = self.apply("desc")
        os.rename(self.repo.state / audit.FOLDER, self.repo.state.parent / "audit-aside")  # as if approved before AVB-10
        new = self.apply("hours")
        self.assertEqual(self.say("history"), "history")
        [reply] = self.replies()
        shown = reply.splitlines()[1:]
        self.assertEqual(len(shown), 2)
        self.assertIn(new["summary"], shown[0])
        self.assertIn(old["summary"], shown[1])

    def test_owner_history_tells_a_failed_till_check_from_a_passed_one(self):
        till = audit.AuditLog(self.repo.state, lambda: self.now)
        for name, result in (("checked", "ok"), ("not-checked", "not-verified")):
            act = audit.new_action("till", name)
            till.record("approved", action=act, approval="A1", approved_by="owner", strict=True, **TILL)
            till.record("applied", action=act, strict=True, **TILL)
            till.record("verified", action=act, strict=True, **{**TILL, "result": result})
        self.assertEqual(self.say("history"), "history")
        [reply] = self.replies()
        self.assertEqual(reply.splitlines(), ["Here's what we changed lately:",
                                              "- A change on the test till, approved Mon Nov 2 9:00 am: saved, but I couldn't check it, so please look at it.",
                                              "- A change on the test till, approved Mon Nov 2 9:00 am: saved and checked."])

    def test_till_history_uses_approval_not_later_time_and_handles_bad_time(self):
        till = audit.AuditLog(self.repo.state, lambda: self.now)
        act = audit.new_action("till", "time-test")
        till.record("approved", action=act, approval="A1", approved_by="owner", strict=True, **TILL)
        self.now += timedelta(hours=2)
        till.record("applied", action=act, strict=True, **TILL)
        self.assertEqual(self.say("history"), "history")
        self.assertEqual(self.replies(), ["Here's what we changed lately:\n- A change on the test till, approved Mon Nov 2 9:00 am: saved."])
        [entry] = self.conv.audit.approved(5)
        for bad in (None, "", "invalid", "2026-11-02T17:00:00"):
            with self.subTest(at=bad), mock.patch.object(self.conv.audit, "approved", return_value=[{**entry, "at": bad}]):
                self.assertEqual(self.say("history"), "history")
                self.assertEqual(self.replies(), ["Here's what we changed lately:\n- A change on the test till, time unknown: saved."])


def _refuse(slots, ctx):
    raise Refusal("I can't add a hike that long ago.")


OLD_HIKE = toy("hike.old", "add an old hike", HIKE_ADD.slots, _refuse)


class SkillAuditTests(SkillCase):
    """Review round 1, finding 2: a skill that answers (read-only) or refuses before any draft is an action too."""
    SKILLS = (HIKE_ADD, REPORT_SHELF, OLD_HIKE)

    def test_a_report_answer_is_an_answered_line(self):
        text = "please show the shelf report"
        self.script(text, skill_reply("report.shelf"))
        self.assertEqual(self.say(text), "answer")
        [answer] = self.replies()
        [row] = lines(self.repo.state)
        self.assertEqual(audit.check(row), [])
        self.assertEqual({k: row[k] for k in ("step", "result", "skill", "pack", "target", "env", "approval", "who", "msg")},
                         {"step": "answered", "result": "ok", "skill": f"report.shelf@{REPORT_SHELF.version}", "pack": "reports",
                          "target": "local", "env": "sandbox", "approval": "A0", "who": "owner", "msg": short("m1")})
        raw = b"".join(p.read_bytes() for p in (self.repo.state / audit.FOLDER).iterdir())
        for private in (text, "shelf report", *[w for w in answer.split() if len(w) > 5][:5], OWNER, CHAT):
            self.assertNotIn(private.encode(), raw, private)
        self.assertEqual(self.conv.audit.approved(5), [])  # an answer is not a change: history does not list it

    def test_a_skill_refusal_before_any_draft_is_a_refused_line(self):
        self.script(LIVE1, skill_reply("hike.old", **MILL))
        self.assertEqual(self.say(LIVE1), "refused")
        self.assertEqual(self.replies(), ["I can't add a hike that long ago."])
        [row] = lines(self.repo.state)
        self.assertEqual((row["step"], row["result"], row["skill"], row["pack"], row["target"]),
                         ("refused", "refused", "hike.old@1", "site", "local"))
        self.assertNotIn("approval", row)
        self.nothing_written()

    def test_a_drafted_skill_change_still_writes_its_site_steps(self):
        self.script(LIVE1, skill_reply("hike.add", **MILL))
        self.assertEqual(self.say(LIVE1), "proposed")
        self.assertEqual([(r["step"], r["skill"], r["target"]) for r in lines(self.repo.state)],
                         [("drafted", "hike.add@1", "site")])


if __name__ == "__main__":
    unittest.main()

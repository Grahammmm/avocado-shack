"""AVB-10 tests: one audit log for every action (hass/audit.py and the Conversation lines).

Unit tests use a private temp state folder and a fixed clock. Conversation tests use the H06 setup from test_undo (temp Git
repo, linked writer worktree, private 0700 state dir, fake previewer, injected clock); nothing touches live state.
Run: python3 -m unittest hass.tests.test_audit -v
"""

import json, os, shutil, subprocess, sys, tempfile, unittest  # noqa: E401
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import audit
from hass.content_model import REPO_ROOT
from hass.conversation import Inbound
from hass.stagelog import short
from hass.tests.test_conversation import CHAT, OWNER, _ops
from hass.tests.test_editor import DESC
from hass.tests.test_undo import H06TestCase

T0 = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)
SCRIPT = REPO_ROOT / "hass" / "audit.py"
TILL: dict = dict(who="owner", pack="till", target="till", env="sandbox", result="ok", draft="7c1e", skill="till.stock@1",
            refs={"till": "tj-0123abcd"}, subjects=["items:hass-avocado"], fields=["stock"])
PRIVATE_TEXT = "kumquat desc $12.50 call +1 805 555 0142"  # owner words, a price and a phone number: none may reach the log


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
        self.assertEqual(reply.splitlines()[:2], ["Here's what we changed lately:", "- A change on the test till: saved."])
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


if __name__ == "__main__":
    unittest.main()

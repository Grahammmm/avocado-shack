"""AV1537-13 (H20/H25): `statebackup.py drill` runs verify, restore --paused, health and history in one command.

Fixtures come from test_statebackup (throwaway repo, writer + drill worktrees, private state dir; no live state).
"""

import contextlib, io, json, os, sqlite3, subprocess, sys  # noqa: E401
from datetime import timedelta
from unittest import mock

from hass import editor, health, statebackup
from hass.tests.test_conversation import T0
from hass.tests.test_statebackup import PRIVATE, SCRIPT, BackupTestCase, tree

FIXED, SENTINEL = T0 + timedelta(minutes=3), "SENTINEL-drill-owner-text"
KEYS = {"result", "state", "worktree", "files", "paused", "health_problems", "health_info", "history"}
# A mocked health detail the drill line must never carry. The NUL byte makes it impossible in any filesystem path (POSIX
# paths are NUL-terminated C strings), so the temp dirs the line rightly names can never contain it by accident.
DETAIL = "SECRET-DETAIL\0SENTINEL"

def strings(value):  # every key and string in decoded JSON: a leaked NUL is escaped in the raw line, intact once decoded
    if isinstance(value, dict):
        for key, item in value.items(): yield key; yield from strings(item)  # noqa: E702
    elif isinstance(value, list):
        for item in value: yield from strings(item)
    elif isinstance(value, str): yield value

class DrillCommandTests(BackupTestCase):
    def cli(self, *argv):  # (exit code, the one JSON line, raw stdout), in process so mocks apply
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf): code = statebackup.main([str(a) for a in argv])
        [line] = buf.getvalue().splitlines()
        return code, json.loads(line), buf.getvalue()

    def drill_args(self, backup, into, wt=None):
        return ("drill", backup, "--into", into, "--worktree", wt or self.drill_wt)

    def sentinel_backup(self):  # two applied changes; one draft's op args carry the sentinel (history would show it)
        self.apply("kumquat desc")
        self.apply("kumquat hours")
        path = sorted((self.repo.state / "drafts").glob("chg-*.json"))[0]
        doc = json.loads(path.read_text("utf-8"))
        doc["ops"][0]["args"]["note"] = SENTINEL
        path.write_text(json.dumps(doc), "utf-8")
        return self.backup()

    def assert_nothing_new(self, names, *paths):
        self.assertEqual(sorted(os.listdir(self.tmp)), names)  # no target, no .restore- temp dir
        for path in paths: self.assertFalse(os.path.lexists(path), path)

    def test_good_backup_drills_ok_paused_one_line_without_owner_text(self):
        backup, new = self.sentinel_backup(), self.tmp / "restored"
        run = subprocess.run([sys.executable, str(SCRIPT), *map(str, self.drill_args(backup, new))],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        [line] = run.stdout.splitlines()
        got = json.loads(line)
        self.assertEqual(set(got), KEYS)
        self.assertEqual((got["result"], got["paused"], got["state"], got["health_problems"]),
                         ("ok", True, str(new.resolve()), []))
        self.assertIn("paused", got["health_info"])
        self.assertEqual((got["history"], got["files"]), (2, len(self.files(backup))))
        with contextlib.closing(sqlite3.connect(new / statebackup.DB)) as db:
            self.assertEqual(db.execute("SELECT name, value, provider_id FROM control").fetchall(),
                             [("paused", "1", "statebackup-restore")])
        hist = json.dumps(editor.history(state=str(new)))
        self.assertIn(SENTINEL, hist)  # the restored history holds it; the drill line never does
        for text in (SENTINEL, *PRIVATE, "kumquat", "product.", "chg-"): self.assertNotIn(text, run.stdout, text)
        self.assertEqual(run.stderr, "")

    def test_corrupt_backup_stops_at_verify_and_makes_nothing(self):
        backup, new = self.backup(), self.tmp / "restored"
        data = bytearray((backup / "config.json").read_bytes())
        data[0] ^= 1  # one byte flipped
        (backup / "config.json").write_bytes(bytes(data))
        names = sorted(os.listdir(self.tmp))
        with mock.patch.object(statebackup, "restore", wraps=statebackup.restore) as restore:
            code, got, _ = self.cli(*self.drill_args(backup, new))
        self.assertEqual((code, got["result"], got["step"]), (1, "corrupt", "verify"))
        self.assertIn("hash mismatch: config.json", got["problems"])
        self.assertEqual(restore.call_count, 0)
        self.assert_nothing_new(names, new)

    def test_existing_into_is_refused_at_restore_untouched(self):
        backup, taken = self.backup(), self.tmp / "taken"
        taken.mkdir(mode=0o700)
        (taken / "keep.txt").write_text("keep", "utf-8")
        before = tree(taken)
        code, got, _ = self.cli(*self.drill_args(backup, taken))
        self.assertEqual((code, got), (1, {"result": "refused", "step": "restore",
                                           "problems": ["restore dir already exists; left untouched"]}))
        self.assertEqual(tree(taken), before)

    def test_writer_worktree_is_attended(self):
        backup, new = self.backup(), self.tmp / "restored"
        names = sorted(os.listdir(self.tmp))
        for wt in (self.repo.wt, f"{self.repo.wt}/"):  # the recorded writer worktree, also with a trailing slash
            with self.subTest(wt=wt):
                code, got, _ = self.cli(*self.drill_args(backup, new, wt))
                self.assertEqual((code, got), (1, {"result": "refused", "step": "restore",
                                                   "problems": [statebackup.ATTENDED]}))
                self.assert_nothing_new(names, new)

    def test_into_inside_the_repository_is_unsafe(self):
        backup = self.backup()
        for into in (self.repo.main / "restored", self.drill_wt / "restored", self.repo.wt / "restored"):
            with self.subTest(into=into.name, parent=into.parent.name):
                before = sorted(os.listdir(into.parent))
                code, got, _ = self.cli(*self.drill_args(backup, into))
                self.assertEqual((code, got["result"]), (2, "unsafe-state"))
                self.assertEqual(sorted(os.listdir(into.parent)), before)

    def test_structural_health_problem_fails_the_drill_and_keeps_the_dir(self):
        backup = self.backup()
        cases = (([{"check": "db-integrity", "detail": "database unreadable"}], False, "db-integrity"),
                 ([{"check": "inbox-integrity", "detail": "1 issue(s)"}], False, "inbox-integrity"),
                 ([{"check": "settings", "detail": DETAIL}], False, "settings"),
                 ([{"check": "state", "detail": DETAIL}], True, "state"))
        for i, (problems, unsafe, check) in enumerate(cases):
            new = self.tmp / f"restored-{i}"
            with self.subTest(check=check), mock.patch.object(health, "check", return_value=(problems, [], unsafe)):
                code, got, out = self.cli(*self.drill_args(backup, new))
                self.assertEqual((code, got["result"], got["step"], got["health_problems"]),
                                 (1, "drill-failed", "health", [check]))
                self.assertFalse([s for s in strings(got) if problems[0]["detail"] in s], out)  # ids only, no detail
                self.assertTrue((new / statebackup.DB).is_file())  # left in place for inspection
                self.assertEqual(statebackup.verify(str(backup))["result"], "ok")

    def test_history_failure_fails_the_drill_at_history(self):
        backup, new = self.backup(), self.tmp / "restored"
        for i, effect in enumerate(({"result": "error"}, editor.UnsafeState("x"))):
            with self.subTest(effect=effect), mock.patch.object(editor, "history", side_effect=[effect]):
                code, got, _ = self.cli(*self.drill_args(backup, new.with_name(f"r{i}")))
                self.assertEqual((code, got["result"], got["step"], got["history"]), (1, "drill-failed", "history", 0))

    def test_non_structural_problem_stays_ok_and_is_listed(self):
        self.assertEqual(self.say("kumquat desc"), "proposed")  # the draft reply stays unsent in the outbox
        backup, new = self.backup(), self.tmp / "restored"
        got = statebackup.drill(str(backup), str(new), str(self.drill_wt), now=T0 + timedelta(hours=2))
        self.assertEqual((got["result"], got["health_problems"], got["paused"]), ("ok", ["outbox-stuck"], True))
        self.assertNotIn("step", got)
        early = statebackup.drill(str(backup), str(self.tmp / "early"), str(self.drill_wt), now=FIXED)
        self.assertEqual((early["result"], early["health_problems"]), ("ok", []))  # not stuck yet

    def test_drill_takes_no_paused_flag_and_restore_keeps_it(self):
        backup, new = self.backup(), self.tmp / "restored"
        bad = subprocess.run([sys.executable, str(SCRIPT), *map(str, self.drill_args(backup, new)), "--paused"],
                             capture_output=True, text=True)
        self.assertEqual((bad.returncode, os.path.lexists(new)), (2, False))
        code, got, _ = self.cli("restore", backup, "--into", new, "--worktree", self.drill_wt, "--paused")
        self.assertEqual((code, got["result"], got["paused"]), (0, "ok", True))

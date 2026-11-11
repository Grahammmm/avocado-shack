"""RF1025-11: trial_summary refuses an observed database-leaf replacement (detection only, not confinement)."""
import contextlib, io, json, os, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass import trial_summary as ts  # noqa: E402
from hass.tests.test_trial_summary import make_state, run  # noqa: E402

AT = "2026-11-01T20:00:00+00:00"
CANARY = "CANARY-ident-91"
real_connect = sqlite3.connect


class Proxy:
    """Real connection; `after` runs once the COMMIT has executed (the final query seam)."""
    def __init__(self, db, after=None): self.db, self.after, self.closed, self.sql = db, after, 0, []
    def execute(self, sql, *a):
        self.sql.append(sql)
        cur = self.db.execute(sql, *a)
        if sql == "COMMIT" and self.after: self.after()
        return cur
    def close(self): self.closed += 1; self.db.close()
    def __setattr__(self, k, v):
        if k == "isolation_level": self.db.isolation_level = v
        else: object.__setattr__(self, k, v)


class IdentityTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(); self.addCleanup(self._t.cleanup)
        self.d = Path(self._t.name) / "state"; self.d.mkdir()
        self.alt = Path(self._t.name) / "alt"; self.alt.mkdir()
        make_state(self.d, approvals=[AT])
        make_state(self.alt, approvals=[AT] * 9)
        self.leaf = self.d / "conversation.sqlite3"

    def swap_symlink(self):
        self.leaf.rename(self.d / "aside"); self.leaf.symlink_to(self.alt / "conversation.sqlite3")

    def swap_regular(self):
        os.replace(self.alt / "conversation.sqlite3", self.leaf)

    def summarize(self): return ts.summarize(str(self.d), ts.date(2026, 11, 1), 1)

    def at_connect(self, mutate, after=None):
        def connect(*a, **k):
            mutate()
            return Proxy(real_connect(*a, **k), after)
        return mock.patch.object(ts.sqlite3, "connect", connect)

    def test_baseline_unchanged_store_reports(self):
        self.assertEqual(self.summarize()["totals"]["approvals"], 1)

    def test_leaf_symlink_installed_at_connect_is_unreadable(self):
        with self.at_connect(self.swap_symlink), self.assertRaises(ts.Unreadable): self.summarize()
        for flag, want in (([], "Trial summary unavailable.\n"), (["--json"], '{"result": "unreadable"}\n')):
            self.leaf.unlink(); (self.d / "aside").rename(self.leaf)
            with self.at_connect(self.swap_symlink):
                code, out, err = run("--state", str(self.d), "--from", "2026-11-01", *flag)
            self.assertEqual((code, out, err), (1, want, ""))

    def test_regular_inode_replacement_is_also_unreadable(self):
        with self.at_connect(self.swap_regular), self.assertRaises(ts.Unreadable): self.summarize()

    def test_leaf_disappears_or_changes_type_before_connect(self):
        def gone(): self.leaf.rename(self.d / "aside")
        def as_dir(): gone(); self.leaf.mkdir()
        def as_fifo(): gone(); os.mkfifo(self.leaf)
        for mutate in (gone, as_dir, as_fifo):
            with self.subTest(mutate.__name__):
                if self.leaf.exists() or self.leaf.is_symlink():
                    (self.leaf.rmdir if self.leaf.is_dir() else self.leaf.unlink)()
                if (self.d / "aside").exists(): (self.d / "aside").rename(self.leaf)
                real_lstat, calls = os.lstat, []
                def lstat(p, *a, **k):
                    if str(p) == str(self.leaf): calls.append(1)
                    if str(p) == str(self.leaf) and len(calls) == 2: mutate()
                    return real_lstat(p, *a, **k)
                with mock.patch.object(ts.os, "lstat", lstat), mock.patch.object(ts.sqlite3, "connect") as conn:
                    with self.assertRaises(ts.Unreadable): self.summarize()
                conn.assert_not_called()

    def test_lstat_oserror_is_unreadable(self):
        real_lstat, calls = os.lstat, []
        def lstat(p, *a, **k):
            if str(p) == str(self.leaf):
                calls.append(1)
                if len(calls) == 2: raise OSError(f"{CANARY} boom")
            return real_lstat(p, *a, **k)
        with mock.patch.object(ts.os, "lstat", lstat), self.assertRaises(ts.Unreadable) as cm: self.summarize()
        self.assertNotIn(CANARY, repr(cm.exception))

    def test_replacement_after_queries_discards_counts(self):
        with self.at_connect(lambda: None, after=self.swap_regular), self.assertRaises(ts.Unreadable): self.summarize()
        self.leaf.unlink(); make_state(self.d, approvals=[AT])
        with self.at_connect(lambda: None, after=lambda: (self.leaf.rename(self.d / "aside"), self.leaf.symlink_to(self.d / "aside"))):
            code, out, err = run("--state", str(self.d), "--from", "2026-11-01", "--json")
        self.assertEqual((code, out, err), (1, '{"result": "unreadable"}\n', ""))

    def test_connection_closed_on_post_open_identity_refusal(self):
        made = []
        def connect(*a, **k):
            made.append(Proxy(real_connect(*a, **k)))
            self.swap_regular()  # swap lands while SQLite opens
            return made[-1]
        with mock.patch.object(ts.sqlite3, "connect", connect), self.assertRaises(ts.Unreadable): self.summarize()
        self.assertEqual((len(made), made[0].closed, made[0].sql), (1, 1, []))

    def test_unchanged_store_and_live_wal_keep_exact_reports(self):
        before = self.summarize()
        w = real_connect(self.leaf); w.execute("PRAGMA journal_mode=WAL"); w.commit()
        w.execute("UPDATE approvals SET approved_at = ?", (AT,))
        w.execute("INSERT INTO approvals(sender, chat, provider_id, change_id, draft_hash, base, expires_at, approved_at) "
                  "VALUES ('s', 'c', 'extra', 'x', 'h', 'b', '2099-01-01T00:00:00+00:00', ?)", (AT,))
        w.commit()
        try:
            self.assertEqual(self.summarize()["totals"]["approvals"], 2)
        finally: w.close()
        self.assertEqual(before["totals"]["approvals"], 1)

    def test_identity_failures_do_not_echo_canaries_or_retry(self):
        (self.d / f"{CANARY}-x").mkdir()
        before = (self.alt / "conversation.sqlite3").read_bytes()
        n = []
        def connect(*a, **k): n.append(1); self.swap_symlink(); return Proxy(real_connect(*a, **k))
        with mock.patch.object(ts.sqlite3, "connect", connect):
            code, out, err = run("--state", str(self.d), "--from", "2026-11-01")
        self.assertEqual((code, out, err, len(n)), (1, "Trial summary unavailable.\n", "", 1))
        self.assertEqual((self.alt / "conversation.sqlite3").read_bytes(), before)
        code, out, err = run("--state", str(self.d), "--from", "not-a-date")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

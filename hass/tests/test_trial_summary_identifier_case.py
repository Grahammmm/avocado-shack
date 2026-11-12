"""RF0540-11: trial_summary reads SQLite table/column names with SQLite's ASCII case-insensitivity (never Unicode)."""
import json, sqlite3, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hass import trial_summary as ts  # noqa: E402
from hass.tests.test_trial_summary import report, run  # noqa: E402

CANON = {"messages": "messages", "drafts": "drafts", "approvals": "approvals", "usage": "usage",
         "disposition": "disposition", "received_at": "received_at", "state": "state", "created_at": "created_at",
         "approved_at": "approved_at", "day": "day", "calls": "calls"}
MIXED = {k: k.upper() if i % 2 else k.title() for i, k in enumerate(CANON)}


def build(tmp, names=None, skip=(), **over):
    """Real external DB; `names` maps each canonical identifier to its spelling; `skip` omits a column outright."""
    n = {**CANON, **(names or {}), **over}
    col = lambda k: "" if k in skip else f", {n[k]} TEXT"
    db = sqlite3.connect(Path(tmp) / "conversation.sqlite3")
    db.executescript(f"""
CREATE TABLE {n['messages']}(id TEXT, {n['disposition']} TEXT{col('received_at')});
CREATE TABLE {n['drafts']}(id TEXT, {n['state']} TEXT{col('created_at')});
CREATE TABLE {n['approvals']}(id TEXT{col('approved_at')});
CREATE TABLE {n['usage']}({n['day']} TEXT, {n['calls']} INTEGER);""")
    db.execute(f"INSERT INTO {n['messages']} VALUES ('a', 'approved', '2026-11-01T12:00:00-08:00')" if "received_at" not in skip
               else f"INSERT INTO {n['messages']} VALUES ('a', 'approved')")
    if "received_at" not in skip:
        db.execute(f"INSERT INTO {n['messages']} VALUES ('b', 'approved', '2026-11-03T08:00:00-08:00')")
        db.execute(f"INSERT INTO {n['messages']} VALUES ('c', 'approved', 'garbage')")
    cols = "" if "created_at" in skip else ", ?"
    db.execute(f"INSERT INTO {n['drafts']} VALUES ('d', 'approved'{cols})", (("2026-11-02T01:00:00-08:00",) if cols else ()))
    db.execute(f"INSERT INTO {n['approvals']} VALUES ('x'{'' if 'approved_at' in skip else ', ' + repr('2026-11-02T09:00:00-08:00')})")
    db.execute(f"INSERT INTO {n['usage']} VALUES ('2026-11-01', 4)")
    db.commit(); db.close()
    return tmp


class IdentifierCaseTest(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory(); self.addCleanup(self._t.cleanup); self.tmp = self._t.name

    def rep(self, **kw):
        return report(build(self.tmp, **kw))

    def test_canonical_expected_counts(self):
        r = self.rep()
        d = {x["day"]: x for x in r["daysSummary"]}
        self.assertEqual(sum(d["2026-11-01"]["messages"].values()), 1)
        self.assertEqual(sum(d["2026-11-03"]["messages"].values()), 1)
        self.assertEqual(sum(r["unknown"]["messages"].values()), 1)
        self.assertEqual(sum(d["2026-11-02"]["drafts"].values()), 1)
        self.assertEqual(d["2026-11-02"]["approvals"], 1)
        self.assertEqual(d["2026-11-01"]["interpreterCalls"], 4)
        self.assertEqual(sum(r["totals"]["messages"].values()), 3)

    def test_mixed_case_tables_and_columns_match_canonical(self):
        want = self.rep()
        for group in (("messages",), ("drafts",), ("approvals",), ("usage",), ("messages", "drafts", "approvals", "usage"),
                      ("disposition",), ("state",), ("day", "calls"), ("received_at", "created_at", "approved_at"),
                      tuple(CANON)):
            with self.subTest(group=group), tempfile.TemporaryDirectory() as t:
                self.assertEqual(report(build(t, {k: MIXED[k] for k in group})), want)

    def test_missing_optional_and_required_columns(self):
        r = self.rep(skip=("received_at", "created_at", "approved_at"))
        self.assertEqual(sum(r["unknown"]["messages"].values()), 1)
        self.assertEqual(sum(r["unknown"]["drafts"].values()), 1)
        self.assertEqual(r["unknown"]["approvals"], 1)
        with tempfile.TemporaryDirectory() as t:
            build(t); db = sqlite3.connect(Path(t) / "conversation.sqlite3")
            db.execute("ALTER TABLE usage RENAME COLUMN calls TO ncalls"); db.commit(); db.close()
            self.assertEqual(run("--state", t, "--from", "2026-11-01", "--json")[:2],
                             (1, json.dumps({"result": "unreadable"}) + "\n"))

    def test_ascii_only_no_unicode_equivalence(self):
        with tempfile.TemporaryDirectory() as t:  # U+017F long s casefolds to s, but SQLite does not equate it
            build(t, messages="mes\u017fages")
            self.assertEqual(sum(report(t)["totals"]["messages"].values()), 0)
        with tempfile.TemporaryDirectory() as t:
            build(t, disposition="d\u0131sposition")  # dotless i
            self.assertEqual(run("--state", t, "--from", "2026-11-01", "--json")[0], 1)
        self.assertEqual(ts._fold("ABCz\u212a"), "abcz\u212a")


if __name__ == "__main__":
    unittest.main()

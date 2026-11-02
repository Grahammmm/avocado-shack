"""AV1737-08 (H06): the result check covers every touched record of a change (at most VERIFY_MAX distinct targets)
and a failure names the record (fake previewer recording targets, no browser).

The change's records are swapped in after the proposal (editor.show wrapped), so any record mix can be checked.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""
import contextlib
import io
import unittest
from datetime import timedelta
from pathlib import Path

from hass import conversation, health, preview
from hass.tests.test_undo import PNG, H06TestCase


def hidden(key):
    return {"collection": "products", "key": key, "before": {"status": "active"},
            "after": {"name": f"Name {key}", "status": "hidden", "description": "x"}}


STORE = {"hours": ["Open daily"], "streetAddress": "5 Example St", "town": "Cayucos"}


def store(field):
    return {"collection": "store", "key": "store", "before": {field: None}, "after": dict(STORE)}


class ScriptedPreviewer:
    """Passes every capture except result capture number ``fail_at``; records result targets and file names."""

    def __init__(self, fail_at=None):
        self.fail_at, self.results = fail_at, []

    def capture(self, files, target, out_png):
        if "-result" in Path(out_png).name:
            self.results.append((target, Path(out_png).name))
            if len(self.results) == self.fail_at:
                return {"ok": False, "png": None, "checks": {}, "error": "simulated miss"}
        preview._write_private(Path(out_png), PNG)
        return {"ok": True, "png": str(out_png), "checks": {"fake": True}, "error": None}


class VerifyAllRecordsTests(H06TestCase):
    def run_change(self, records, fail_at=None):
        """Propose 'desc', swap its records for ``records`` (None keeps the real one), approve; return (row, reply)."""
        self.previewer = ScriptedPreviewer(fail_at)
        self.conv = self.open()
        draft, _reply = self.propose("desc")
        if records is not None:
            real = self.editor.show

            def show(change_id, *args, **kwargs):
                out = real(change_id, *args, **kwargs)
                if change_id == draft["change_id"] and out.get("change"):
                    out = {**out, "change": {**out["change"], "records": records}}
                return out
            self.editor.show = show
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(self.say("yes"), "approved")
        self.log = err.getvalue()
        [reply] = self.sent()
        return [d for d in self.drafts() if d["row_id"] == draft["row_id"]][0], reply

    def names(self, row, n):
        cid = row["change_id"]
        return [f"{cid}-result.png"] + [f"{cid}-result-{i}.png" for i in range(2, n + 1)]

    def test_three_hidden_products_three_captures(self):
        row, reply = self.run_change([hidden("p1"), hidden("p2"), hidden("p3")])
        targets, files = zip(*self.previewer.results)
        self.assertEqual([t["id"] for t in targets], ["p1", "p2", "p3"])
        self.assertEqual([t["status"] for t in targets], ["hidden"] * 3)
        self.assertEqual(list(files), self.names(row, 3))
        for name in files:
            self.assertEqual((self.repo.state / "screenshots" / name).read_bytes(), PNG)
        first = str(self.repo.state / "screenshots" / files[0])
        self.assertEqual((row["state"], row["screenshot"], row["reason"]), ("verified", first, None))
        self.assertEqual((reply["text"], reply["attachments"]),
                         (f"Applied and checked {row['code']}: {row['summary']}", [first]))
        self.assertEqual(self.log, "")

    def test_second_of_three_fails_names_it_and_stops(self):
        row, reply = self.run_change([hidden("p1"), hidden("p2"), hidden("p3")], fail_at=2)
        self.assertEqual([t["id"] for t, _n in self.previewer.results], ["p1", "p2"])  # p3 never captured
        self.assertEqual((row["state"], row["screenshot"]), ("applied", None))
        self.assertEqual(row["reason"], "not verified: products p2: simulated miss")
        self.assertEqual(reply["text"],
                         f"Applied {row['code']}, but the preview check failed: products p2: simulated miss")
        self.assertFalse((self.repo.state / "screenshots" / self.names(row, 3)[2]).exists())

    def test_first_failure_names_the_first_record(self):
        row, _reply = self.run_change([store("hours"), hidden("p2")], fail_at=1)
        self.assertEqual(len(self.previewer.results), 1)
        self.assertEqual(row["reason"], "not verified: store store: simulated miss")

    def test_seven_records_capture_five_and_log_the_rest(self):
        records = [hidden(f"p{i}") for i in range(1, 8)]
        row, reply = self.run_change(records[:1] + [hidden("p1")] + records[1:])  # a repeat of p1 is not counted
        self.assertEqual(conversation.VERIFY_MAX, 5)
        self.assertEqual([t["id"] for t, _n in self.previewer.results], ["p1", "p2", "p3", "p4", "p5"])
        self.assertEqual([n for _t, n in self.previewer.results], self.names(row, 5))
        self.assertEqual((row["state"], reply["text"]),
                         ("verified", f"Applied and checked {row['code']}: {row['summary']}"))
        self.assertEqual(self.log,
                         f"verify {row['change_id']}: over 5 records, not checked: products p6, products p7\n")

    def test_fifth_record_failure_is_named(self):
        row, _reply = self.run_change([hidden(f"p{i}") for i in range(1, 8)], fail_at=5)
        self.assertEqual(len(self.previewer.results), 5)
        self.assertEqual(row["reason"], "not verified: products p5: simulated miss")
        self.assertEqual(self.log, "")

    def test_records_with_the_same_target_capture_once(self):
        row, _reply = self.run_change([store("hours"), hidden("p1"), store("streetAddress")])
        targets = [t for t, _n in self.previewer.results]
        self.assertEqual([t["kind"] for t in targets], ["store", "product"])
        self.assertEqual(targets[0], preview.target_for(store("town")))
        self.assertEqual(row["state"], "verified")

    def test_two_store_fields_capture_once(self):
        row, _reply = self.run_change([store("hours"), store("town")])
        self.assertEqual([n for _t, n in self.previewer.results], self.names(row, 1))

    def test_single_record_change_keeps_the_old_path(self):
        row, reply = self.run_change(None)
        [(target, name)] = self.previewer.results
        self.assertEqual((target["id"], name), ("photo-product-001", f"{row['change_id']}-result.png"))
        self.assertEqual(row["screenshot"], str(self.repo.state / "screenshots" / name))
        self.assertEqual(reply["attachments"], [row["screenshot"]])

    def test_no_records_unchanged(self):
        row, reply = self.run_change([])
        self.assertEqual(self.previewer.results, [])
        self.assertEqual((row["state"], row["reason"]), ("applied", "not verified: no change record"))
        self.assertEqual(reply["text"], f"Applied {row['code']}, but the preview check failed: no change record")

    def test_health_counts_the_failed_change_once(self):
        self.run_change([hidden("p1"), hidden("p2"), hidden("p3")], fail_at=2)
        problems = health.check(str(self.repo.state), now=self.now + timedelta(hours=1))[0]
        self.assertEqual([p for p in problems if p["check"] == "unverified"], [{"check": "unverified", "detail": "1"}])


if __name__ == "__main__":
    unittest.main()

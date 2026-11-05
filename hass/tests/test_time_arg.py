"""RF0210-12 (H02/H04): typed hike clock arguments accept only ASCII HH:MM; Unicode digits are an invalid time, not a later ValueError."""

import contextlib, io, json, tempfile, unittest  # noqa: E401
from pathlib import Path
from unittest import mock

from hass import editor
from hass.ops import Arg, Op, check_args, hikes
from hass.tests.test_hike_ops import HIKE, HIKE_ID, HikeTestCase, _req

OP = Op("t.op", {"time": Arg("time")}, lambda *a: None)
ERR = (["t.op.time: must be HH:MM (24 h)"])
TYPE_ERR_VALUES = (None, True, 930, ["09:30"], {"t": "09:30"})
BAD = ("09:3\u0663", "0\u0669:30", "\uff10\uff19:\uff13\uff10", "\u0966\u096f:\u0969\u0966", "\u0660\u0669:\u0663\u0660",
       "09\uff1a30", "09\u058930", "24:00", "23:60", "9:30", "09:30:00", "09:30+08:00", " 09:30", "09:30 ", "09:30\n")
PROBLEM = ["ops[0] 'hike.create': hike.create.time: must be HH:MM (24 h)"]


def check(value):
    return check_args(OP, {"time": value}, {}, Path("."))


class TimeArgTests(unittest.TestCase):
    def test_time_kind_rejects_non_ascii_digits(self):
        for value in BAD[:5]:
            with self.subTest(value=value):
                self.assertEqual(check(value), (ERR, []))

    def test_ascii_time_boundaries_and_malformed_grammar(self):
        for value in ("00:00", "09:30", "19:59", "23:59"):
            with self.subTest(value=value):
                self.assertEqual(check(value), ([], []))
        for value in BAD[5:]:
            with self.subTest(value=value):
                self.assertEqual(check(value), (ERR, []))
        for value in TYPE_ERR_VALUES:
            with self.subTest(value=value):
                problems, missing = check(value)
                self.assertEqual(missing, [])
                self.assertEqual(len(problems), 1)
                self.assertNotIn("HH:MM", problems[0])


class HikePrepareTests(HikeTestCase):
    def test_create_and_update_bad_clock_are_invalid_without_draft(self):
        repo = self.repo()
        with mock.patch.object(hikes, "_start", side_effect=AssertionError("handler reached")):
            for bad in ("09:3\u0663", "0\u0669:30"):
                with self.subTest(op="create", time=bad):
                    result = self.assertRejected(repo, "invalid", ("hike.create", {**HIKE, "time": bad}))
                    self.assertEqual(result, {"result": "invalid", "problems": PROBLEM})
        repo.run(("hike.create", HIKE))
        for bad in ("09:3\u0663", "0\u0669:30"):
            with self.subTest(op="update", time=bad):
                result = self.assertRejected(repo, "invalid", ("hike.update", {"id": HIKE_ID, "time": bad}))
                self.assertEqual(result, {"result": "invalid", "problems": ["ops[0] 'hike.update': hike.update.time: must be HH:MM (24 h)"]})
        self.assertEqual(repo.event()["startsAt"], "2026-12-05T09:00:00-08:00")

    def test_cli_bad_clock_is_invalid_not_io_error(self):
        repo = self.repo()
        with tempfile.TemporaryDirectory() as tmp:
            req = Path(tmp) / "req.json"
            req.write_text(json.dumps(_req(("hike.create", {**HIKE, "time": "09:3\u0663"}))), "utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = editor.main(["prepare", str(req), "--state", str(repo.state)])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out.getvalue()), {"result": "invalid", "problems": PROBLEM})
        self.assertEqual(err.getvalue(), "")
        self.assertNotIn("\u0663", out.getvalue())

    def test_corrected_ascii_clock_uses_normal_draft_and_dst_rules(self):
        repo = self.repo()
        head = repo.head()
        result = repo.prepare(_req(("hike.create", HIKE)))
        self.assertEqual(result["result"], "ok", result)
        self.assertEqual(repo.head(), head)  # a draft, nothing applied
        gap = repo.prepare(_req(("hike.create", {**HIKE, "date": "2062-03-12", "time": "02:30"})))
        self.assertEqual(gap["result"], "needs-details", gap)


if __name__ == "__main__":
    unittest.main()

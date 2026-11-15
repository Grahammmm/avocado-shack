"""AV1104-04 (H13): store.set_hours still drafts hours the website cannot read for its open/closed line, with one warning.

The rule is sitegen.parse_hours (AV1104-03), imported by hass.ops.store and never copied. Throwaway writer repo only.
Run: python3 -B -m unittest hass.tests.test_store_hours_warning -v
"""

import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import conversation
from hass.content_model import load_content
from hass.ops import OpContext, store as store_ops
from hass.tests.test_conversation import ConversationTestCase, _ops
from hass.tests.test_store_ops import SET_ADDRESS, SET_HOURS, REVERT, StoreTestCase, _req

TAIL = ' is not like "Saturday 9am-5pm" or "Closed Sunday".'
HEAD = "The website will not say open or closed now with these hours: line "
BAD = ["Monday-Friday 9am-6pm", "Sat by appointment"]


def warning(number, text):
    return f'{HEAD}{number} "{text}"{TAIL}'


class HoursWarningTests(StoreTestCase):
    def warnings(self, repo, *ops):
        out = repo.prepare(_req(*ops))
        self.assertEqual(out["result"], "ok", out)
        return out["draft"]["warnings"], out

    def test_unreadable_hours_warns_but_drafts(self):
        repo = self.repo()
        head, commits = repo.head(), repo.commits()
        warnings, out = self.warnings(repo, (SET_HOURS, {"hours": BAD}))
        self.assertEqual(warnings, ['The website will not say open or closed now with these hours: line 2 '
                                    '"Sat by appointment" is not like "Saturday 9am-5pm" or "Closed Sunday".'])
        [record] = out["draft"]["records"]
        self.assertEqual(record["after"]["hours"], BAD)
        self.assertEqual((repo.head(), repo.commits(), repo.status()), (head, commits, ""))  # prepare writes nothing
        self.assertEqual(repo.apply(out["draft"])["result"], "applied")
        self.assertEqual(repo.store()["hours"], BAD)
        old = repo.run((REVERT, {"changeId": out["draft"]["change_id"]}))
        self.assertEqual(old["warnings"], [])
        self.assertEqual(repo.store()["hours"], load_content().store["hours"])

    def test_first_bad_line_is_named_one_based(self):
        repo = self.repo()
        for hours, number, text in (
                (["Open daily", "Monday 9am-5pm"], 1, "Open daily"),
                (["Monday 9am-5pm", "Tuesday & Wednesday \"late\""], 2, 'Tuesday & Wednesday "late"'),
                (["Monday 9am-5pm", "Tuesday 9am-5pm", "Wednesday 9am-5pm", "Thursday 9am-5pm", "Friday 9am-5pm",
                  "Saturday 9am-5pm", "Sunday later"], 7, "Sunday later"),
                (["Monday 9am-5pm", "see us " + "x" * 50], 2, "see us " + "x" * 50),
                (["Bad first", "Monday 9am-5pm", "Also bad"], 1, "Bad first")):
            with self.subTest(hours=hours):
                self.assertEqual(self.warnings(repo, (SET_HOURS, {"hours": hours}))[0], [warning(number, text)])

    def test_cross_line_and_second_clause_errors_warn(self):
        repo = self.repo()
        for hours, number, text in (
                (["Monday 9am-5pm", "Monday 10am-6pm"], 2, "Monday 10am-6pm"),
                (["Monday 9am-5pm · Tuesday by chance"], 1, "Monday 9am-5pm · Tuesday by chance")):
            with self.subTest(hours=hours):
                self.assertEqual(self.warnings(repo, (SET_HOURS, {"hours": hours}))[0], [warning(number, text)])

    def test_readable_hours_have_no_warning(self):
        repo = self.repo()
        for hours in (["Monday-Friday 9am-6pm", "Saturday 9am–5pm · Closed Sunday"], ["Monday 9am-5pm"],
                      ["Monday-Friday 9:30am-6pm"], ["Closed Sunday"], ["Closed Monday-Tuesday", "Wednesday 10am–2pm"]):
            with self.subTest(hours=hours):
                self.assertEqual(self.warnings(repo, (SET_HOURS, {"hours": hours}))[0], [])

    def test_the_shared_parser_is_the_only_rule(self):
        repo = self.repo()
        hours = ["Monday 9am-5pm", "Whenever"]
        sentinel = {"days": None, "errors": [{"line": 5, "text": "Sentinel \"text\""}, {"line": 6, "text": "later"}]}
        with mock.patch.object(store_ops, "parse_hours", return_value=sentinel) as parse:
            self.assertEqual(self.warnings(repo, (SET_HOURS, {"hours": hours}))[0], [warning(5, 'Sentinel "text"')])
        parse.assert_called_once_with(hours)
        other = ["Monday 9am-5pm", "Whenever else"]  # a different draft: the same request would reuse the first one
        with mock.patch.object(store_ops, "parse_hours", return_value={"days": [None] * 7, "errors": []}) as parse:
            self.assertEqual(self.warnings(repo, (SET_HOURS, {"hours": other}))[0], [])
        parse.assert_called_once_with(other)

    def test_refusals_add_no_warning(self):
        repo = self.repo()
        current = repo.store()["hours"]
        for label, hours in (("unchanged", current), ("spacing only", [h.replace(" ", "  ") for h in current]),
                             ("repeat", ["Whenever", "whenever"]), ("8 lines", [f"Later {i}" for i in range(8)]),
                             ("too long", ["x" * 61]), ("punctuation only", ["Whenever", "..."])):
            with self.subTest(label):
                head, drafts = repo.head(), repo.drafts()
                out = repo.prepare(_req((SET_HOURS, {"hours": hours})))
                self.assertEqual(out["result"], "refused", out)
                self.assertNotIn("warnings", out)
                self.assertEqual((repo.head(), repo.drafts(), repo.status()), (head, drafts, ""))
        self.assertEqual(repo.prepare(_req((SET_HOURS, {"hours": "Whenever"})))["result"], "invalid")

    def test_other_ops_and_earlier_warnings(self):
        repo = self.repo()
        self.assertEqual(self.warnings(repo, (SET_ADDRESS, {"town": "Cayucos"}))[0], [])
        both, _out = self.warnings(repo, (SET_HOURS, {"hours": ["Whenever"]}), (SET_HOURS, {"hours": ["Later on"]}))
        self.assertEqual(both, [warning(1, "Whenever"), warning(1, "Later on")])
        content = load_content()
        ctx = OpContext(now=datetime(2026, 11, 2, tzinfo=timezone.utc), site_dir=Path("."), settings={}, warnings=["earlier"])
        store_ops._set_hours(content, {"hours": BAD}, ctx)
        self.assertEqual(ctx.warnings, ["earlier", warning(2, "Sat by appointment")])
        self.assertEqual(content.store["hours"], BAD)


class HoursWarningConversationTests(ConversationTestCase):
    """The production registry and the writer worktree's store record, as the live conversation runs."""

    def setUp(self):
        super().setUp()
        self.editor = conversation.Editor(self.repo.state)
        self.conv = self.open()

    def test_warning_flows_to_proposal_and_show(self):
        self.interp.mapping["odd hours"] = _ops((SET_HOURS, {"hours": BAD}))
        draft, reply = self.propose("odd hours")
        line = "Heads up: " + warning(2, "Sat by appointment")
        self.assertEqual(reply.count(line), 1, reply)
        self.assertEqual(reply.count("Heads up:"), 1)
        self.assertEqual(self.say(f"show {draft['code']}"), "show")
        [shown] = self.replies()
        self.assertEqual(shown.count(line), 1, shown)
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("proposed", 0))  # still needs yes
        self.assertEqual(self.say("yes"), "approved")
        self.replies()
        self.assertEqual((self.drafts()[-1]["state"], self.commits()), ("applied", 1))

    def test_readable_hours_show_no_heads_up(self):
        self.interp.mapping["clear hours"] = _ops((SET_HOURS, {"hours": ["Monday-Saturday 9am-6pm", "Closed Sunday"]}))
        _draft, reply = self.propose("clear hours")
        self.assertNotIn("Heads up", reply)


if __name__ == "__main__":
    unittest.main()

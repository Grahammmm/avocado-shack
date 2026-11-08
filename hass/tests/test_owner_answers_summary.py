"""RF1300-19 tests: owner answers print the change summary only when it is one readable line of text.

did_it_work and applied_text use the stored summary stripped when it is a str, non-empty after strip, has no line
break, control character or U+2028/U+2029 and is at most 200 characters; anything else reads "the change".
Pure functions only, synthetic change rows; nothing is read, written or sent.
Run: python3 -B -m unittest hass.tests.test_owner_answers_summary
"""
import unittest
from datetime import datetime, timezone

from hass import owner_answers as answers

NOW = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)  # 10:00 Pacific
INSTALLED = {"state": "installed", "installed_at": "2026-11-02T09:05:00-08:00"}
UNREADABLE = ("   ", "", None, ["x"], {"a": 1}, 42, "Hours\nupdated", "Hours\r\nupdated", "a\u2028b", "a\u2029b",
              "x\x07y", "tab\there", "x" * 201)
NOT_LIVE = answers.NOT_LIVE
# Captured from origin/main before RF1300-19: these answers never print the summary.
GOLDEN = {
    "proposed": "It's waiting for your yes. Nothing has changed yet.",
    "needs-details": "It's waiting for your yes. Nothing has changed yet.",
    "approved": "You said yes, but it isn't saved yet, so nothing has changed on the website.",
    "reverted": "That change was undone.",
    "failed": "I couldn't save that, and the website is unchanged. Please send the change again.",
}
INSTALL_FAILED = ("That didn't reach the website, and the website is unchanged. "
                  "I couldn't update the website pages.")


def done(summary):
    return answers.did_it_work({"state": "applied", "summary": summary}, INSTALLED, NOW)


class DidItWorkSummaryTests(unittest.TestCase):
    def test_readable_summary_unchanged(self):
        self.assertEqual(done("Hours updated"), "Done. \ue000Hours updated\ue001 is on the website now (I checked today at 9:05 am).")

    def test_unreadable_summary_reads_the_change(self):
        for summary in UNREADABLE:
            with self.subTest(summary=summary):
                got = done(summary)
                self.assertEqual(got, "Done. the change is on the website now (I checked today at 9:05 am).")
                self.assertNotIn("[", got)
                self.assertNotIn("{", got)

    def test_missing_summary_key_reads_the_change(self):
        got = answers.did_it_work({"state": "verified"}, INSTALLED, NOW)
        self.assertEqual(got, "Done. the change is on the website now (I checked today at 9:05 am).")

    def test_summary_is_stripped(self):
        self.assertEqual(done("  Hours  "), "Done. \ue000Hours\ue001 is on the website now (I checked today at 9:05 am).")

    def test_length_limit(self):
        self.assertEqual(done("y" * 200), f"Done. \ue000{'y' * 200}\ue001 is on the website now (I checked today at 9:05 am).")
        self.assertEqual(done("  " + "y" * 200 + "  "), f"Done. \ue000{'y' * 200}\ue001 is on the website now (I checked today at 9:05 am).")
        self.assertEqual(done("y" * 201), "Done. the change is on the website now (I checked today at 9:05 am).")

    def test_other_states_byte_identical_for_any_summary(self):
        for state, want in GOLDEN.items():
            for summary in UNREADABLE + ("Hours updated",):
                with self.subTest(state=state, summary=summary):
                    got = answers.did_it_work({"state": state, "summary": summary}, INSTALLED, NOW)
                    self.assertEqual(got, want)
        for summary in UNREADABLE + ("Hours updated",):
            with self.subTest(install="failed", summary=summary):
                got = answers.did_it_work({"state": "applied", "summary": summary},
                                          {"state": "failed", "reason": "write failed: x"}, NOW)
                self.assertEqual(got, INSTALL_FAILED)


class AppliedTextSummaryTests(unittest.TestCase):
    def test_readable_summary_unchanged(self):
        self.assertEqual(answers.applied_text("AB12", "Hours updated"), f"Saved: \ue000Hours updated\ue001\n{NOT_LIVE}")
        self.assertEqual(answers.applied_text("AB12", " Hours ", checked=True), f"Saved and checked: \ue000Hours\ue001\n{NOT_LIVE}")

    def test_unreadable_summary_reads_the_change(self):
        for summary in UNREADABLE:
            with self.subTest(summary=summary):
                got = answers.applied_text("AB12", summary)
                self.assertEqual(got, f"Saved: the change\n{NOT_LIVE}")
                self.assertEqual(got.count("\n"), 1)

    def test_error_reply_unchanged_and_summary_not_printed(self):
        for summary in UNREADABLE + ("Hours updated",):
            with self.subTest(summary=summary):
                got = answers.applied_text("AB12", summary, error="preview server did not start")
                self.assertEqual(got, f"I saved it, but the preview check didn't pass: I couldn't make a preview.\n{NOT_LIVE}")


if __name__ == "__main__":
    unittest.main()

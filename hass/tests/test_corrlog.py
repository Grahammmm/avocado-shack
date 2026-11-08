"""HASS-VOICE-1 tests: the correspondence log (hass/corrlog.py) and the rows the conversation writes into it.

1. The log itself: append-only day files, row fields, kinds, reason codes, the 80-character excerpt with numbers, addresses
   and links blanked, 90-day retention, never raising on a bad folder, the last-ten list and the weekly line.
2. The moments that write a row: a slow reply, a question asked again, Mike saying no or "that's wrong", a held-back message.
3. G only: `problems` and `weekly` answer only the numbers in settings gSenders; gSenders can never overlap ownerSenders;
   Mike's morning report never carries the weekly line.
Synthetic only: temporary folders, throwaway repo, injected clock; nothing is sent.
Run: python3 -B -m unittest hass.tests.test_corrlog
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hass import conversation, corrlog, morning_report, voice
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0, ConversationTestCase

G = "g@example.invalid"
NOW = datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc)


class LogCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name)
        self.now = NOW
        self.log = corrlog.CorrLog(self.state, lambda: self.now)

    def files(self):
        return sorted(p.name for p in (self.state / corrlog.FOLDER).iterdir())

    def lines(self):
        return [json.loads(x) for p in sorted((self.state / corrlog.FOLDER).iterdir()) for x in p.read_text("utf-8").splitlines()]


class LogFile(LogCase):
    def test_a_row_has_the_agreed_fields_and_nothing_else(self):
        self.assertTrue(self.log.record("could-not-do", "no-skill", msg="provider-msg-1", reply=7, excerpt="can you order boxes", seconds=3.14159))
        [row] = self.lines()
        self.assertEqual(set(row), {"at", "kind", "reason", "msg", "reply", "excerpt", "seconds"})
        self.assertEqual((row["kind"], row["reason"], row["excerpt"], row["seconds"]), ("could-not-do", "no-skill", "can you order boxes", 3.1))
        self.assertEqual(row["at"], "2026-11-08T18:00:00+00:00")
        self.assertEqual(len(row["msg"]), 12)  # one-way short id, never the provider id
        self.assertNotIn("provider-msg-1", json.dumps(row))
        self.assertEqual(len(row["reply"]), 12)

    def test_seconds_is_left_out_when_not_given(self):
        self.log.record("error", "save-failed")
        self.assertNotIn("seconds", self.lines()[0])

    def test_every_kind_is_accepted_and_an_unknown_kind_is_not(self):
        self.assertEqual(set(corrlog.KINDS), {"did-not-understand", "could-not-do", "asked-again", "error", "slow", "voice-fallback", "corrected"})
        for kind in corrlog.KINDS: self.assertTrue(self.log.record(kind, "x"), kind)
        self.assertFalse(self.log.record("compliment", "x"))
        self.assertEqual(len(self.lines()), len(corrlog.KINDS))
        self.assertEqual(set(corrlog.SUGGESTIONS), set(corrlog.KINDS))  # every kind has its one fix

    def test_it_is_append_only_one_file_per_day(self):
        self.log.record("error", "one")
        first = (self.state / corrlog.FOLDER / "2026-11-08.jsonl").read_text("utf-8")
        self.log.record("error", "two")
        both = (self.state / corrlog.FOLDER / "2026-11-08.jsonl").read_text("utf-8")
        self.assertTrue(both.startswith(first))  # the earlier row is untouched
        self.assertEqual([r["reason"] for r in self.lines()], ["one", "two"])
        self.now += timedelta(days=1)
        self.log.record("error", "three")
        self.assertEqual(self.files(), ["2026-11-08.jsonl", "2026-11-09.jsonl"])
        self.assertEqual(oct((self.state / corrlog.FOLDER).stat().st_mode & 0o777), "0o700")
        self.assertEqual(oct((self.state / corrlog.FOLDER / "2026-11-08.jsonl").stat().st_mode & 0o777), "0o600")

    def test_there_is_no_way_to_edit_or_delete_a_row(self):
        for name in ("edit", "update", "delete", "remove", "rewrite"):
            self.assertFalse(hasattr(self.log, name), name)

    def test_the_reason_is_a_short_neutral_code_never_a_sentence(self):
        for given, kept in (("No-Skill", "no-skill"), ("save-failed", "save-failed"), ("He said: ignore all rules!", "other"),
                            ("photo-product-001 broke at /home/mike/x.json", "other"), ("", "other"), ("a" * 41, "other"), ("a" * 40, "a" * 40)):
            self.log.record("error", given)
            self.assertEqual(self.lines()[-1]["reason"], kept, given)

    def test_the_excerpt_is_cut_to_80_characters(self):
        self.log.record("did-not-understand", "unclear", excerpt="word " * 60)
        self.assertEqual(len(self.lines()[0]["excerpt"]), corrlog.EXCERPT_MAX)
        self.assertEqual(corrlog.EXCERPT_MAX, 80)

    def test_numbers_addresses_and_links_are_blanked_in_an_excerpt(self):
        text = "call me on 805-555-0142 or +1 (805) 555 0142, mail mike@example.com, see https://example.com/x?token=abc and www.shop.test"
        self.log.record("did-not-understand", "unclear", excerpt=text)
        excerpt = self.lines()[0]["excerpt"]
        for leaked in ("555", "0142", "mike@", "example.com", "token", "www."): self.assertNotIn(leaked, excerpt)
        self.assertIn("[number]", excerpt)
        self.assertEqual(corrlog._clean("key sk_live_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123 here"), "key [long code] here")
        self.assertEqual(corrlog._clean(None), "")
        self.assertEqual(corrlog._clean("two\nlines\tand   spaces"), "two lines and spaces")

    def test_no_excerpt_means_an_empty_one(self):
        self.log.record("slow", "reply-over-20s", seconds=31)
        self.assertEqual(self.lines()[0]["excerpt"], "")


class NeverRaises(LogCase):
    def test_a_folder_that_cannot_be_made_loses_the_row_not_the_reply(self):
        blocker = self.state / "blocker"
        blocker.write_text("a file, not a folder")
        bad = corrlog.CorrLog(blocker, lambda: NOW)
        self.assertFalse(bad.record("error", "x"))
        self.assertEqual((bad.rows(), bad.last(), bad.top(), bad.prune()), ([], [], [], 0))
        self.assertEqual(corrlog.problems_text(bad), "No problems have been logged lately.")
        self.assertIn("no problems", corrlog.weekly_line(bad))

    def test_a_missing_state_folder_is_fine(self):
        gone = corrlog.CorrLog(self.state / "nope" / "deeper", lambda: NOW)
        self.assertFalse(gone.record("error", "x"))
        self.assertEqual(gone.rows(), [])

    def test_a_clock_that_fails_does_not_raise(self):
        def boom(): raise RuntimeError("clock")
        self.assertFalse(corrlog.CorrLog(self.state, boom).record("error", "x"))

    def test_a_symlinked_day_file_is_not_followed(self):
        (self.state / corrlog.FOLDER).mkdir()
        elsewhere = self.state / "elsewhere.txt"
        elsewhere.write_text("keep")
        os.symlink(elsewhere, self.state / corrlog.FOLDER / "2026-11-08.jsonl")
        self.assertFalse(self.log.record("error", "x"))
        self.assertEqual(elsewhere.read_text(), "keep")

    def test_damaged_lines_and_stray_files_are_skipped(self):
        self.log.record("error", "good")
        day = self.state / corrlog.FOLDER / "2026-11-08.jsonl"
        with open(day, "a", encoding="utf-8") as f:
            f.write("not json\n[1, 2]\n" + json.dumps({"kind": "bogus", "at": NOW.isoformat()}) + "\n"
                    + json.dumps({"kind": "error", "at": "yesterday-ish"}) + "\n"
                    + json.dumps({"kind": "error", "at": "2026-11-08T10:00:00"}) + "\n")  # no time zone: not trusted
        (self.state / corrlog.FOLDER / "notes.txt").write_text("hello")
        self.assertEqual([r["reason"] for r in self.log.rows()], ["good"])


class Retention(LogCase):
    def test_day_files_older_than_90_days_are_deleted_whole(self):
        for days_ago in (0, 30, 89, 90, 91, 200):
            self.now = NOW - timedelta(days=days_ago)
            self.log.record("error", f"d{days_ago}")
        self.now = NOW
        (self.state / corrlog.FOLDER / "notes.txt").write_text("not a day file: left alone")
        self.assertEqual(self.log.prune(), 2)  # 91 and 200 days old
        self.assertEqual(len(self.files()), 5)  # four day files and the stray file
        self.assertIn("notes.txt", self.files())
        self.assertEqual(corrlog.RETENTION_DAYS, 90)

    def test_rows_older_than_90_days_are_not_read_even_before_pruning(self):
        self.now = NOW - timedelta(days=120)
        self.log.record("error", "old")
        self.now = NOW - timedelta(days=10)
        self.log.record("error", "recent")
        self.now = NOW
        self.assertEqual([r["reason"] for r in self.log.rows()], ["recent"])

    def test_prune_leaves_a_symlink_alone(self):
        (self.state / corrlog.FOLDER).mkdir()
        elsewhere = self.state / "elsewhere.txt"
        elsewhere.write_text("keep")
        os.symlink(elsewhere, self.state / corrlog.FOLDER / "2025-01-01.jsonl")
        self.assertEqual(self.log.prune(), 0)
        self.assertTrue(elsewhere.exists())


class ForG(LogCase):
    def fill(self, kinds):
        for i, kind in enumerate(kinds):
            self.now = NOW + timedelta(minutes=i)
            self.log.record(kind, f"r{i}", excerpt=f"he wrote {i}" if i % 2 else None)

    def test_problems_lists_the_last_ten_newest_first(self):
        self.fill(["error"] * 15)
        text = corrlog.problems_text(self.log)
        lines = text.splitlines()
        self.assertEqual(lines[0], "The last 10 problems, newest first:")
        self.assertEqual(len(lines), 11)
        self.assertIn("(r14)", lines[1])  # newest first
        self.assertIn("(r5)", lines[10])
        self.assertNotIn("(r4)", text)

    def test_problems_is_plain_words_for_one_row_and_for_none(self):
        self.assertEqual(corrlog.problems_text(self.log), "No problems have been logged lately.")
        self.log.record("slow", "reply-over-20s")
        text = corrlog.problems_text(self.log)
        self.assertIn("The last 1 problem, newest first:", text)
        self.assertIn("a reply took more than 20 seconds", text)
        self.assertIn("Sun Nov 8, 10:00 am", text)  # shop time, written naturally
        self.assertEqual(voice.check(text, long_ok=True, ids_ok=True), [])

    def test_problems_shows_what_he_wrote_but_not_numbers(self):
        self.log.record("did-not-understand", "unclear", excerpt="order 12 boxes, call 805 555 0142")
        text = corrlog.problems_text(self.log)
        self.assertIn("He wrote:", text)
        self.assertNotIn("0142", text)

    def test_weekly_is_the_three_most_common_with_one_fix_each(self):
        self.fill(["error"] * 4 + ["did-not-understand"] * 3 + ["slow"] * 2 + ["corrected"])
        line = corrlog.weekly_line(self.log)
        self.assertEqual(self.log.top(), [("error", 4), ("did-not-understand", 3), ("slow", 2)])
        for kind, n in (("error", 4), ("did-not-understand", 3), ("slow", 2)):
            self.assertIn(f"{corrlog.KINDS[kind]} ({n} times; try: {corrlog.SUGGESTIONS[kind]})", line)
        self.assertNotIn(corrlog.KINDS["corrected"], line)  # only three
        self.assertEqual(line.count("try:"), 3)
        self.assertLess(line.index("something went wrong"), line.index("I did not understand"))

    def test_weekly_counts_only_the_last_seven_days_and_ties_are_stable(self):
        self.now = NOW - timedelta(days=9)
        for _ in range(5): self.log.record("error", "old")
        self.now = NOW
        self.log.record("slow", "a")
        self.log.record("could-not-do", "b")
        self.assertEqual(self.log.top(), [("could-not-do", 1), ("slow", 1)])
        line = corrlog.weekly_line(self.log)
        self.assertNotIn("something went wrong", line)
        self.assertIn("(1 time; try:", line)

    def test_weekly_with_nothing_logged_says_so(self):
        self.assertEqual(corrlog.weekly_line(self.log), "Talking with Mike this week: no problems logged.")

    def test_the_command_line_reads_the_same_text(self):
        self.fill(["error", "slow"])
        for what, text in (("problems", corrlog.problems_text), ("weekly", corrlog.weekly_line)):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(corrlog.main([what, "--state", str(self.state)]), 0)
            self.assertTrue(out.getvalue().strip())


class Moments(ConversationTestCase):
    """The conversation writes a row at each problem moment, and only for those."""

    def kinds(self):
        return [(r["kind"], r["reason"]) for r in self.conv.log.rows()]

    def test_a_slow_reply_is_logged_when_it_leaves(self):
        self.say("hours")  # a draft reply, stored now
        self.now += timedelta(seconds=corrlog.SLOW_SECONDS + 15)
        self.replies()
        self.assertIn(("slow", "reply-over-20s"), self.kinds())
        [slow] = [r for r in self.conv.log.rows() if r["kind"] == "slow"]
        self.assertGreater(slow["seconds"], corrlog.SLOW_SECONDS)

    def test_a_quick_reply_is_not_logged(self):
        self.say("hours")
        self.now += timedelta(seconds=corrlog.SLOW_SECONDS - 5)
        self.replies()
        self.assertNotIn("slow", [k for k, _ in self.kinds()])

    def test_a_question_asked_again_is_logged(self):
        self.say("when?")
        self.replies()
        self.assertEqual(self.kinds(), [])
        self.now += timedelta(minutes=1)
        self.say("when?")
        self.assertIn(("asked-again", "same-question"), self.kinds())

    def test_a_question_asked_a_long_time_later_is_not_logged(self):
        self.say("when?")
        self.now += timedelta(hours=2)
        self.say("when?")
        self.assertNotIn("asked-again", [k for k, _ in self.kinds()])

    def test_saying_no_is_logged_as_a_correction(self):
        draft, _reply = self.propose("hours")
        self.assertEqual(self.say("no"), "rejected")
        self.assertIn(("corrected", "said-no"), self.kinds())

    def test_thats_wrong_is_logged_as_a_correction(self):
        self.propose("hours")
        self.say("that's wrong")
        self.assertIn(("corrected", "owner-corrected"), self.kinds())

    def test_not_what_i_meant_is_logged_as_a_correction(self):
        self.propose("hours")
        self.say("not what I meant")
        self.assertIn(("corrected", "owner-corrected"), self.kinds())

    def test_an_ordinary_happy_path_logs_nothing(self):
        self.propose("hours")
        self.say("yes")
        self.replies()
        self.assertEqual(self.kinds(), [])

    def test_something_it_cannot_do_is_logged_as_could_not_do(self):
        self.say("unknown thing")  # the fixture interpreter answers "Sorry, I can't do that yet."
        self.assertIn(("could-not-do", "no-skill"), self.kinds())

    def test_a_held_back_message_is_logged_as_a_voice_fallback(self):
        self.conv.outbox.strict = False
        self.conv.outbox.add(CHAT, "The interpreter failed closed on photo-product-001.")
        [row] = self.conv.log.rows()
        self.assertEqual(row["kind"], "voice-fallback")
        self.assertNotIn("photo-product-001", json.dumps(row))

    def test_no_row_holds_more_than_the_agreed_fields(self):
        self.say("hours")
        self.now += timedelta(seconds=60)
        self.replies()
        self.say("that's wrong")
        for row in self.conv.log.rows():
            self.assertLessEqual(set(row), {"at", "kind", "reason", "msg", "reply", "excerpt", "seconds"})
            self.assertLessEqual(len(row["excerpt"]), corrlog.EXCERPT_MAX)

    def test_the_log_lives_in_the_state_folder_only(self):
        self.say("that's wrong")
        self.assertTrue((self.repo.state / corrlog.FOLDER).is_dir())


class GOnly(ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.set_settings({**SETTINGS, "gSenders": [G]})
        self.conv = self.open()
        self.conv.log.record("error", "save-failed")
        self.conv.log.record("slow", "reply-over-20s")

    def test_problems_from_g_gets_the_list(self):
        self.assertEqual(self.say("problems", chat="chat-g", sender=G), "g-problems")
        [reply] = self.replies()
        self.assertTrue(reply.startswith("The last 2 problems, newest first:"), reply)

    def test_weekly_from_g_gets_the_week(self):
        self.assertEqual(self.say("weekly", chat="chat-g", sender=G), "g-weekly")
        [reply] = self.replies()
        self.assertIn("most common problems were", reply)

    def test_problems_from_any_other_number_gets_no_answer(self):
        for sender in ("stranger@example.invalid", "+18055550100"):
            for word in ("problems", "weekly"):
                self.say(word, chat="chat-x", sender=sender)
                self.assertEqual(self.replies(), [], (sender, word))
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 0)

    def test_mike_asking_for_problems_gets_no_list(self):
        self.say("problems")  # Mike's own number is an owner sender, not a G sender
        for reply in self.replies(): self.assertNotIn("most common", reply) or self.assertNotIn("newest first", reply)
        self.say("weekly")
        for reply in self.replies(): self.assertNotIn("newest first", reply)

    def test_g_is_not_an_owner_and_cannot_approve_changes(self):
        draft, _reply = self.propose("hours")
        self.say("yes", chat="chat-g", sender=G)
        self.replies()
        self.assertEqual(self.drafts()[-1]["state"], "proposed")
        self.assertEqual(self.commits(), 0)

    def test_g_overlapping_the_owner_is_a_config_error(self):
        for g in ([OWNER], [G, OWNER], [OWNER.upper()]):
            with self.subTest(g=g):
                self.set_settings({**SETTINGS, "gSenders": g})
                with self.assertRaises(conversation.ConfigError):
                    self.open()

    def test_g_senders_must_be_a_list_of_addresses(self):
        for g in ("g@example.invalid", 5, [5], [None], {"a": 1}):
            with self.subTest(g=g):
                self.set_settings({**SETTINGS, "gSenders": g})
                with self.assertRaises(conversation.ConfigError):
                    self.open()

    def test_without_g_senders_nobody_gets_the_list(self):
        self.set_settings(SETTINGS)
        self.conv = self.open()
        self.say("problems", chat="chat-g", sender=G)
        self.assertEqual(self.replies(), [])


class MikesReport(unittest.TestCase):
    def run_report(self, for_g=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        state = Path(tmp.name)
        corrlog.CorrLog(state, lambda: datetime.now(timezone.utc)).record("error", "save-failed")
        content = state / "content"
        content.mkdir()
        for name, doc in (("products", {"schemaVersion": 1, "products": []}), ("makers", {"schemaVersion": 1, "makers": {}}),
                          ("community", {"schemaVersion": 1}), ("store", {"schemaVersion": 1})):
            (content / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
        out = io.StringIO()
        self.assertEqual(morning_report.main((["--for-g", str(state)] if for_g else []), content_dir=content, out=out), 0)
        return out.getvalue()

    def test_mikes_report_never_contains_the_weekly_line(self):
        text = self.run_report()
        self.assertNotIn("Talking with Mike", text)
        self.assertNotIn("most common problems", text)
        self.assertEqual(voice.check(text.strip(), long_ok=True), [])

    def test_g_gets_the_weekly_line_after_the_report(self):
        text = self.run_report(for_g=True)
        self.assertIn("Talking with Mike this week", text)
        self.assertIn("something went wrong (1 time; try:", text)

    def test_the_morning_report_has_no_weekly_option_that_mike_can_reach(self):
        # --for-g is a command-line flag for G's run on the box; nothing in the chat code passes it.
        source = (Path(conversation.__file__)).read_text("utf-8")
        self.assertNotIn("for-g", source)
        self.assertNotIn("weekly_line", source.split("def _for_g")[0])


class SafeFolder(unittest.TestCase):
    def test_the_state_backup_does_not_take_the_log(self):
        from hass import statebackup
        source = Path(statebackup.__file__).read_text("utf-8")
        self.assertNotIn(corrlog.FOLDER, source)  # it lists the files it takes; the log is not one of them


if __name__ == "__main__":
    unittest.main()

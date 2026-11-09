"""HASS-LIVE-PLAN-1 test battery on a scratch site: nothing here touches the live site, host.json, real state, keys or the Mac.

Scratch pieces: a throwaway writer repo and 0700 state (WriterRepo), a throwaway bare Git remote standing in for
theavocadoman-site, a clone of it as the site checkout, a fake page fetch that reads the bare remote, an injected clock and a real
Conversation with a scripted interpreter. The release engine is the real LiveEditor (fixture page build, as in test_publish_live).

Scenarios (plan section F): 1 apply + publish + verify; 2 undo; 3 publish failure; 4 a refused risky edit; 5 a stranger;
6 G's chat as the second owner; 7 Graham's one-command revert; 8 the one-line switch back to private mode.
Run: python3 -m unittest hass.tests.test_live_drill -v
"""
import contextlib
import io
import json
import subprocess
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from hass import conversation as conv, host, owner_answers as answers
from hass.fixture_chat import FixtureAdapter
from hass.ops import load_registry
from hass.tests import fixture_ops
from hass.tests.test_conversation import CHAT, OWNER, STRANGER, _ops
from hass.tests.test_editor import DESC, HOURS, NEW_HOURS, git
from hass.tests.test_host import HostCase
from hass.tests import test_publish_live as pl

G, GCHAT = "g@example.invalid", "chat-fixture-g"
BARE_PUSH_REFUSED = b"ssh: connect to host github-avocadoman port 22: Connection refused"


class Drill(pl.ReleaseCase):
    SETTINGS_EXTRA = {}

    def setUp(self):
        super().setUp()
        if self.SETTINGS_EXTRA:
            cfg = json.loads((self.repo.state / "config.json").read_text())
            cfg["settings"].update(self.SETTINGS_EXTRA)
            from hass import editor
            editor._write_json(self.repo.state / "config.json", cfg)
            self.live.settings = conv.load_settings(self.repo.state)
        self.interp = conv.FixtureInterpreter({
            "hours": _ops((HOURS, {"hours": NEW_HOURS})),
            "hours2": _ops((HOURS, {"hours": ["Fixture other hours"]})),
            "organic": _ops((DESC, {"id": "photo-product-001", "description": "Organic fruit"}))})
        self.out, self.n = FixtureAdapter(), 0
        self.live.registry = {**fixture_ops.registry(), "history.revert": load_registry()["history.revert"]}
        self.conv = conv.Conversation(str(self.repo.state), self.live, self.interp, lambda: self.now)
        self.live.conv = self.conv  # as host.make_worker does

    def say(self, text, chat=CHAT, sender=OWNER):
        self.n += 1
        return self.conv.handle(conv.Inbound(f"drill{self.n}", chat, sender, text, False, "new", self.now.isoformat()))

    def sent(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [(row.get("chat"), row["text"]) for row in self.out.sent[before:]]

    def settle_and_flush(self):
        self.live.reconcile()
        self.live.reconcile()
        return self.sent()

    def site_index(self):
        return subprocess.run(["git", "-C", str(self.bare), "show", "main:index.html"], capture_output=True, check=True).stdout

    def code(self):
        return self.conv.db.execute("SELECT code FROM drafts WHERE state = 'proposed' ORDER BY row_id DESC").fetchone()[0]

    def publish_hours(self):
        self.assertEqual(self.say("hours"), "proposed")
        self.sent()
        self.assertEqual(self.say(f"yes {self.code()}"), "approved")

    # 1 ------------------------------------------------------------------------------------------------------------
    def test_1_apply_publish_and_verify(self):
        seed = self.site_index()
        self.assertEqual(self.say("hours"), "proposed")
        [(_chat, proposal)] = self.sent()
        self.assertIn("to put it on the website", proposal)
        self.assertIn("Monday–Friday 9am–6pm", proposal)  # the full previous text is shown
        self.assertEqual(self.say(f"yes {self.code()}"), "approved")
        self.assertEqual(self.push_calls, 1)  # one push, made by the release engine
        self.assertNotEqual(self.site_index(), seed)  # the scratch remote has the new page
        self.assertEqual(self.entry()["state"], "pushed")
        saved = self.sent()
        self.assertEqual(len(saved), 1)
        self.assertTrue(saved[0][1].startswith("Saved:"))
        self.assertNotIn("Now showing", saved[0][1])  # "saved" is never the website outcome
        shown = self.settle_and_flush()  # the page is read back from the remote and matches
        self.assertEqual(self.entry()["state"], "live")
        self.assertEqual(len(shown), 1)
        self.assertIn(answers.LIVE_SHOWN, shown[0][1])
        self.assertEqual(self.settle_and_flush(), [])  # said once
        self.assertEqual(git(self.bare, "log", "--format=%s").count("hass live: " + self.entry()["change_id"]), 1)

    # 2 ------------------------------------------------------------------------------------------------------------
    def test_2_undo_reverses_it_on_the_site(self):
        seed = self.site_index()
        self.publish_hours()
        self.sent()
        self.settle_and_flush()
        self.assertNotEqual(self.site_index(), seed)
        self.assertEqual(self.say("undo"), "proposed")
        self.sent()
        self.assertEqual(self.say(f"yes {self.code()}"), "approved")
        self.sent()
        shown = self.settle_and_flush()
        self.assertEqual(self.site_index(), seed)
        self.assertEqual([j["kind"] for j in self.live.books.journals()], ["change", "undo"])
        self.assertEqual(self.entry()["state"], "live")
        self.assertIn(answers.LIVE_SHOWN, shown[0][1])
        self.assertEqual(self.push_calls, 2)

    # 3 ------------------------------------------------------------------------------------------------------------
    def test_3_publish_failure_says_unchanged_and_blocks_the_next_change(self):
        seed = self.site_index()

        def refuse(cwd, args):
            if args[0] == "push": raise subprocess.CalledProcessError(128, args, stderr=BARE_PUSH_REFUSED)
        self.fault = refuse
        self.publish_hours()
        self.sent()
        self.assertEqual(self.entry()["state"], "not-published")
        told = self.settle_and_flush()
        self.assertEqual(len(told), 1)
        self.assertIn("did not go on the website", told[0][1])
        self.assertIn("The website is unchanged", told[0][1])
        self.assertIn("Graham has been told", told[0][1])
        self.assertNotIn("Your change is on the website", told[0][1])
        self.assertEqual(self.site_index(), seed)
        self.assertEqual(git(self.site, "rev-parse", "HEAD"), self.site_before)  # the local site checkout was put back
        # the next change waits for Graham instead of piling on
        self.assertEqual(self.say("hours2"), "proposed")
        self.sent()
        self.assertEqual(self.say(f"yes {self.code()}"), "approved")
        [(_c, again)] = self.sent()
        self.assertIn("still being checked", again)  # the real reason, in words
        self.assertTrue(again.endswith("Nothing changed on the website."))
        self.assertEqual(len(self.live.books.journals()), 1)  # refused before any journal: no second release opened

    def test_3b_a_push_that_may_have_landed_is_never_called_live(self):
        def timeout(cwd, args):
            if args[0] == "push": raise subprocess.TimeoutExpired(args, 60)
        self.fault = timeout
        self.publish_hours()
        self.sent()
        self.assertEqual(self.entry()["state"], "unknown")
        told = self.settle_and_flush()
        self.assertTrue(all(answers.LIVE_SHOWN not in text for _c, text in told))

    # 4 ------------------------------------------------------------------------------------------------------------
    def test_4_a_refused_risky_edit_changes_nothing_and_is_kept_privately(self):
        seed, writer = self.site_index(), self.repo.head()
        self.assertEqual(self.say("organic"), "proposed")
        [(_c, reply)] = self.sent()
        self.assertIn("I can't put this on the website from chat", reply)
        self.assertIn("I've saved it for Graham", reply)
        code = self.conv.db.execute("SELECT code FROM drafts").fetchone()[0]
        self.assertEqual(self.say(f"yes {code}"), "no-target")
        self.assertIn("I can't put this on the website", self.sent()[0][1])
        self.assertEqual((self.site_index(), self.repo.head(), self.push_calls, self.live.books.journals()), (seed, writer, 0, []))
        [row] = self.conv.db.execute("SELECT reason, state FROM backlog").fetchall()
        self.assertEqual(tuple(row), ("policy", "open"))

    # 5 ------------------------------------------------------------------------------------------------------------
    def test_5_a_stranger_changes_nothing_and_gets_no_reply(self):
        self.assertEqual(self.say("hours"), "proposed")
        self.sent()
        code = self.code()
        before = (self.site_index(), self.repo.head(), self.conv.db.execute("SELECT count(*) FROM outbox").fetchone()[0])
        strangers = [dict(sender=STRANGER), dict(chat="chat-someone-else", sender=STRANGER)]
        if not self.SETTINGS_EXTRA: strangers.append(dict(chat=GCHAT, sender=G))  # G is a stranger unless set as an owner
        for kwargs in strangers:
            for text in (f"yes {code}", "yes", "undo", "status", "hours2"):
                self.assertEqual(self.say(text, **kwargs), "ignored")
        self.assertEqual(self.sent(), [])
        self.assertEqual((self.site_index(), self.repo.head(), self.conv.db.execute("SELECT count(*) FROM outbox").fetchone()[0]), before)
        self.assertEqual((self.push_calls, self.live.books.journals()), (0, []))

    # 7 ------------------------------------------------------------------------------------------------------------
    def test_7_graham_reverts_the_last_live_change_with_one_command(self):
        seed = self.site_index()
        self.publish_hours()
        self.sent()
        self.settle_and_flush()
        self.assertNotEqual(self.site_index(), seed)
        self.now += timedelta(seconds=61)
        out = self.live.operate("revert-last")
        self.assertEqual(out["result"], "ok")
        self.assertEqual(self.site_index(), seed)
        told = self.settle_and_flush()
        self.assertEqual([text for _c, text in told], [answers.LIVE_TAKEN_BACK])
        self.assertEqual(self.conv.db.execute("SELECT state FROM drafts WHERE code = ?", (out["undid"][-4:],)).fetchone(), None)
        self.assertEqual(self.conv.db.execute("SELECT state FROM drafts").fetchone()[0], "reverted")
        # nothing left to revert after the one change: a second command says so and changes nothing
        self.now += timedelta(seconds=61)
        self.assertEqual(self.live.operate("revert-last"), {"result": "nothing-to-revert"})
        self.assertEqual(self.push_calls, 2)

    def drafts_states(self):
        return [r[0] for r in self.conv.db.execute("SELECT state FROM drafts ORDER BY row_id")]

    def published_then_undo_with(self, fault):
        """Publish one change, then run Graham's revert while the push is faulty. Returns (site as published, revert result)."""
        self.publish_hours()
        self.sent()
        self.settle_and_flush()
        published, before = self.site_index(), self.drafts_states()
        self.assertEqual(before, ["applied"])
        self.fault = fault
        self.now += timedelta(seconds=61)
        return published, self.live.operate("revert-last")

    def test_7c_a_revert_that_does_not_publish_leaves_the_change_and_its_chat_status_alone(self):
        def refuse(cwd, args):
            if args[0] == "push": raise subprocess.CalledProcessError(128, args, stderr=BARE_PUSH_REFUSED)
        published, out = self.published_then_undo_with(refuse)
        self.assertEqual((out["result"], out["state"]), ("not-published", "not-published"))  # never "ok"
        self.assertEqual(self.site_index(), published)  # the change is still on the website
        self.settle_and_flush()
        self.assertEqual(self.drafts_states(), ["applied"])  # still the live change, not "undone"

    def test_7d_an_unknown_revert_stays_open_and_closes_the_chat_draft_only_when_proved_live(self):
        from hass.tests.test_publish_live import git

        def lose(cwd, args):  # the push reaches the remote, but the answer is lost
            if args[0] == "push":
                git(cwd, *args)
                raise subprocess.TimeoutExpired("git", 60)
            if args[0] == "ls-remote": raise subprocess.TimeoutExpired("git", 60)
        published, out = self.published_then_undo_with(lose)
        self.assertEqual((out["result"], out["state"]), ("unknown", "unknown"))
        self.settle_and_flush()
        self.assertEqual(self.drafts_states(), ["applied"])  # not proved yet
        self.fault = None
        self.now += timedelta(minutes=11)
        self.settle_and_flush()  # a later tick (or a restart) reads the remote, then reads the page back
        self.assertEqual(self.entry()["state"], "live")
        self.assertEqual(self.drafts_states(), ["reverted"])

    def test_7b_revert_is_refused_while_stopped_or_unsettled(self):
        self.publish_hours()
        self.sent()
        self.settle_and_flush()
        Path(self.cfg["stopFile"]).write_text("")
        self.now += timedelta(seconds=61)
        self.assertEqual(self.live.operate("revert-last")["result"], "refused")
        self.assertEqual(self.push_calls, 1)


class DrillWithG(Drill):
    """6: G's own chat is a second owner: G's yes publishes and the website answer goes to G's chat, text only."""
    SETTINGS_EXTRA = {"gSenders": [G], "gChat": GCHAT, "gIsOwner": True}

    def test_6_g_publishes_and_is_told_in_g_chat(self):
        self.assertEqual(self.say("hours", chat=GCHAT, sender=G), "proposed")
        [(chat, _t)] = self.sent()
        self.assertEqual(chat, GCHAT)
        self.assertEqual(self.say(f"yes {self.code()}", chat=GCHAT, sender=G), "approved")
        told = self.sent() + self.settle_and_flush()
        self.assertTrue(told and all(chat == GCHAT for chat, _t in told), told)
        self.assertTrue(any(answers.LIVE_SHOWN in text for _c, text in told))
        self.assertTrue(all(row["attachments"] == "[]" for row in self.conv.db.execute("SELECT attachments FROM outbox WHERE chat = ?", (GCHAT,))))

    def test_6b_mikes_yes_cannot_publish_gs_change(self):
        self.say("hours", chat=GCHAT, sender=G)
        self.sent()
        self.say(f"yes {self.code()}")
        self.say("yes")
        self.sent()
        self.assertEqual((self.push_calls, self.live.books.journals()), (0, []))

    def two_identical_proposals(self, first, second):
        """Mike and G ask for the same change before either says yes: one shared change_id, two drafts, `second` asked last."""
        for chat, sender in (first, second):
            self.assertEqual(self.say("hours", chat=chat, sender=sender), "proposed")
        self.sent()
        rows = self.conv.db.execute("SELECT chat, code, change_id FROM drafts WHERE state = 'proposed' ORDER BY row_id").fetchall()
        self.assertEqual(len({r["change_id"] for r in rows}), 1)  # the editor's deterministic id is shared
        self.assertEqual([r["chat"] for r in rows], [first[0], second[0]])
        return {r["chat"]: r["code"] for r in rows}

    def approve_and_expect_every_message_in(self, chat, sender, codes, text_part):
        self.assertEqual(self.say(f"yes {codes[chat]}", chat=chat, sender=sender), "approved")
        self.assertEqual(self.entry()["chat"], chat)  # the approver's chat is kept in the release record
        told = self.sent() + self.settle_and_flush()
        self.assertTrue(any(text_part in text for _c, text in told), told)
        self.assertTrue(told and all(c == chat for c, _t in told), told)  # nothing for the other owner

    def test_6d_mike_approving_his_own_is_told_even_when_gs_identical_draft_is_newest(self):
        codes = self.two_identical_proposals((CHAT, OWNER), (GCHAT, G))
        self.approve_and_expect_every_message_in(CHAT, OWNER, codes, answers.LIVE_SHOWN)
        self.assertEqual(self.conv.db.execute("SELECT count(*) FROM outbox WHERE chat = ?", (GCHAT,)).fetchone()[0], 1)  # only G's own proposal

    def test_6e_g_approving_his_own_is_told_in_g_chat_even_when_mikes_identical_draft_is_newest(self):
        codes = self.two_identical_proposals((GCHAT, G), (CHAT, OWNER))
        self.approve_and_expect_every_message_in(GCHAT, G, codes, answers.LIVE_SHOWN)

    def test_6f_a_failed_release_is_told_to_the_approver_not_the_newest_drafts_owner(self):
        def refuse(cwd, args):
            if args[0] == "push": raise subprocess.CalledProcessError(128, args, stderr=BARE_PUSH_REFUSED)
        self.fault = refuse
        codes = self.two_identical_proposals((CHAT, OWNER), (GCHAT, G))
        self.approve_and_expect_every_message_in(CHAT, OWNER, codes, "did not go on the website")

    def test_6g_the_routing_chat_is_read_from_the_release_record_only(self):
        entry = {"chat": GCHAT}
        self.assertEqual(self.live._asker(entry), GCHAT)
        self.assertEqual(self.live._asker({}), CHAT)  # an older record, or Graham's one-command revert: Mike's chat, no guessing

    def test_6c_g_numbers_never_reach_a_published_file(self):
        self.assertIn(G, self.live.private_values())
        self.assertIn(GCHAT, self.live.private_values())


class CommandForms(unittest.TestCase):
    """The runbook says `python3 hass/publish_live.py ...`; it must start like `python3 -m hass.publish_live ...` does."""

    def test_both_command_forms_start_and_know_revert_last(self):
        root = Path(__file__).resolve().parents[2]
        for argv in (["hass/publish_live.py", "--help"], ["-m", "hass.publish_live", "--help"]):
            with self.subTest(argv=argv):
                run = subprocess.run([sys.executable, "-B", *argv], cwd=root, capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertIn("revert-last", run.stdout)


# 8 --------------------------------------------------------------------------------------------------------------
class SwitchBack(HostCase):
    """The one-line switch back to private mode: `python3 hass/host.py mode private --host host.json`."""

    def mode(self, value, path):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = host.main(["mode", value, "--host", str(path)])
        return code, json.loads(out.getvalue())

    def live_json(self):
        cfg = json.loads((self.repo.state / "config.json").read_text())
        cfg["settings"].update(liveSite="theavocadoman.com", approvalNeedsCode=True)
        from hass import editor
        editor._write_json(self.repo.state / "config.json", cfg)
        release = dict(siteCheckout="/fixture/site", siteRemote="git@github-avocadoman:Grahammmm/theavocadoman-site.git",
                       liveUrl="https://theavocadoman.com", stopFile="/fixture/STOP")
        return self.host_json(approvals="live", release=release, pictures=True, previewer=True)

    def test_live_to_private_and_back_keeps_the_file_private_and_valid(self):
        path = self.live_json()
        code, out = self.mode("private", path)
        self.assertEqual((code, out["result"], out["approvals"]), (0, "ok", "private"))
        self.assertEqual(json.loads(Path(path).read_text())["approvals"], "private")
        self.assertEqual(Path(path).stat().st_mode & 0o777, 0o600)
        self.assertEqual([p.name for p in Path(path).parent.iterdir() if p.name.endswith(".tmp")], [])
        self.assertEqual(host.load_host(path)["approvals"], "private")
        self.assertEqual(self.mode("live", path)[0], 0)  # the release block is still there
        self.assertEqual(host.load_host(path)["approvals"], "live")
        self.assertEqual(self.mode("hold", path)[1]["approvals"], "hold")

    def test_a_switch_to_live_that_would_not_load_changes_nothing(self):
        path = self.host_json(approvals="private")
        before = Path(path).read_bytes()
        code, out = self.mode("live", path)
        self.assertEqual((code, out["result"]), (2, "config"))
        self.assertEqual(Path(path).read_bytes(), before)
        self.assertEqual([p.name for p in Path(path).parent.iterdir() if p.name.endswith(".tmp")], [])

    def test_a_host_file_that_is_not_private_is_refused(self):
        path = self.host_json(approvals="private")
        Path(path).chmod(0o644)
        self.assertEqual(self.mode("hold", path)[0], 2)
        self.assertEqual(json.loads(Path(path).read_text())["approvals"], "private")

    def test_in_private_mode_the_chat_behaves_privately_even_with_live_site_set(self):
        self.live_json()
        path = self.host_json(approvals="private")
        worker = host.make_worker(host.load_host(path), self.store, build=lambda: self.interp, clock=self.clock)
        self.assertNotIn("liveSite", worker.conv.settings)
        self.assertEqual(type(worker.conv.editor).__name__, "Editor")  # no release engine in private mode



# The release-case tests inherited from test_publish_live are not repeated here.
for _cls in (Drill, DrillWithG):
    for _name in dir(pl.ReleaseCase):
        if _name.startswith("test_") and _name not in vars(_cls):
            setattr(_cls, _name, None)


if __name__ == "__main__":
    unittest.main()

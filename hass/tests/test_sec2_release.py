"""HASS-SEC-2 (findings M1, M3 and L6 of reports/hass/SEC-1.md) on the real release engine with a scratch site.

M1: an undo of a change that never went on the website through the release engine (saved in private mode before live) is
refused by LiveEditor.apply before anything is written, and in chat it is answered with the plain refusal and kept for Graham;
an undo of a change that did go live still goes live and stays outside the daily cap (test_publish_live covers the cap).
M3: the publish screen finds phone numbers in every common form in text files and the owners' own numbers in any format
(and their email addresses in any letter case), even in unchanged files; image bytes keep the strict rule.
L6: when one owner's undo of ANOTHER owner's change goes live, the original owner's chat is told; Graham's one-command revert
tells the owner whose change it took back.
Scratch Git remotes, injected clock, fixture page build (as test_publish_live). Nothing touches the live site or real state.
Run: python3 -B -m unittest hass.tests.test_sec2_release -v
"""
import json
import subprocess
import unittest
from datetime import timedelta

from hass import conversation as conv, editor, owner_answers as answers, publish_live as p, release_journal as r, voice
from hass.fixture_chat import FixtureAdapter
from hass.ops import load_registry
from hass.tests import fixture_ops, test_publish_live as pl
from hass.tests.test_conversation import CHAT, OWNER, _ops
from hass.tests.test_editor import HOURS, NEW_HOURS, _req, git
from hass.tests.test_owners_two import GCHAT, GEE, MCHAT, MIKE, TWO

# The scratch release fixture of test_publish_live, borrowed method by method so that none of ITS tests run again here.
_BORROWED = ('setUp', 'fixture_build', 'wrapper', 'fetch', 'open', 'wait', 'draft', 'apply', 'entry', 'settle', 'restart',
             'assert_refused_unchanged')


class Release(unittest.TestCase):
    pass


for _name in _BORROWED: setattr(Release, _name, getattr(pl.ReleaseCase, _name))


class Chat(Release):
    """A real Conversation on the release engine, as host.make_worker wires it (what test_live_drill.Drill sets up)."""
    SETTINGS_EXTRA = {}

    def setUp(self):
        super().setUp()
        if self.SETTINGS_EXTRA:
            cfg = json.loads((self.repo.state / "config.json").read_text())
            cfg["settings"].update(self.SETTINGS_EXTRA)
            editor._write_json(self.repo.state / "config.json", cfg)
            self.live.settings = conv.load_settings(self.repo.state)
        self.interp = conv.FixtureInterpreter({"hours": _ops((HOURS, {"hours": NEW_HOURS}))})
        self.out, self.n = FixtureAdapter(), 0
        self.live.registry = {**fixture_ops.registry(), "history.revert": load_registry()["history.revert"]}
        self.conv = conv.Conversation(str(self.repo.state), self.live, self.interp, lambda: self.now)
        self.addCleanup(self.conv.db.close)
        self.live.conv = self.conv

    def say(self, text, chat=CHAT, sender=OWNER):
        self.n += 1
        return self.conv.handle(conv.Inbound(f"sec{self.n}", chat, sender, text, False, "new", self.now.isoformat()))

    def sent(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [(row.get("chat"), row["text"]) for row in self.out.sent[before:]]

    def settle_and_flush(self):
        self.live.reconcile()
        self.live.reconcile()
        return self.sent()

    def code(self):
        return self.conv.db.execute("SELECT code FROM drafts WHERE state = 'proposed' ORDER BY row_id DESC").fetchone()[0]


def reanchor(case):
    """The site is rebuilt from the writer's current head and anchored there (what `publish_live adopt` does after private use)."""
    for rel, data in case.fixture_build(case.repo.head(), case.live.day(), 'x', 'base').items(): (case.site / rel).write_bytes(data)
    git(case.site, 'add', '-A')
    git(case.site, 'commit', '-q', '-m', 'adopted')
    git(case.site, 'push', '-q', 'origin', 'main')
    r.atomic(case.hostdir / 'publish.json', dict(anchor_site_commit=git(case.site, 'rev-parse', 'HEAD'),
                                                 anchor_build_today=case.live.day(), anchor_seq=0, anchor_at=case.now.isoformat()))


class M1ReleaseTests(Release):
    def private_change(self):
        d = self.draft()
        self.assertEqual(editor.apply(d['change_id'], d['draft_hash'], state=self.repo.state, registry=self.live.registry)['result'], 'applied')
        reanchor(self)
        return d['change_id']

    def undo_of(self, cid):
        return editor.prepare(_req(('history.revert', {'changeId': cid})), state=self.repo.state, registry=self.live.registry)['draft']

    def test_undo_of_a_change_saved_before_live_is_refused_before_anything_is_written(self):
        undo = self.undo_of(self.private_change())
        self.assert_refused_unchanged(undo)
        out = self.apply(undo)
        self.assertIn('never went on the website', out['reason'])
        self.assertEqual(self.push_calls, 0)
        words = answers.live_refused(out['reason'])
        self.assertIsNotNone(words)
        self.assertEqual(voice.check(words), [], words)

    def test_undo_of_a_change_that_went_live_still_goes_live_outside_the_cap(self):
        self.apply(); self.settle()
        orig = self.entry()['change_id']
        self.assertTrue(self.live.went_live(orig))
        self.live.cfg['dailyCap'] = 1
        self.assertEqual(self.apply(self.undo_of(orig))['result'], 'applied')
        self.settle()
        self.assertEqual((self.entry()['kind'], self.entry()['state']), ('undo', 'live'))

    def test_undo_of_a_change_whose_release_failed_is_refused(self):
        def refused(cwd, args):
            if args[0] == 'push': raise subprocess.CalledProcessError(1, 'git', stderr=b'ssh: connect to host x port 22: Connection refused')
        self.fault = refused
        self.apply()
        self.settle()
        orig = self.entry()['change_id']
        self.assertEqual(self.entry()['state'], 'not-published')
        self.assertFalse(self.live.went_live(orig))


class M1ChatTests(Chat):
    def test_chat_undo_of_a_change_saved_in_private_mode_is_refused_in_plain_words_and_kept_for_graham(self):
        private = conv.Conversation(str(self.repo.state), conv.Editor(str(self.repo.state), self.live.registry), self.interp, lambda: self.now)
        self.n += 1
        self.assertEqual(private.handle(conv.Inbound(f"drill{self.n}", CHAT, OWNER, "hours", False, "new", self.now.isoformat())), "proposed")
        code = private.db.execute("SELECT code FROM drafts WHERE state = 'proposed'").fetchone()[0]
        self.n += 1
        self.assertEqual(private.handle(conv.Inbound(f"drill{self.n}", CHAT, OWNER, f"yes {code}", False, "new", self.now.isoformat())), "approved")
        private.db.close()
        reanchor(self)
        self.now += timedelta(minutes=5)
        self.sent()
        self.say(f"undo {code}")
        [(_chat, reply)] = self.sent()
        self.assertIn("I can't put this on the website from chat", reply)
        self.assertNotIn("to put it on the website", reply)
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM backlog WHERE reason = 'policy'").fetchone()[0], 1)
        undo = self.conv.db.execute("SELECT code FROM drafts WHERE state = 'proposed' ORDER BY row_id DESC").fetchone()[0]
        self.assertEqual(self.say(f"yes {undo}"), "no-target")
        [(_chat, reply)] = self.sent()
        self.assertIn("I can't put this on the website from chat", reply)
        self.assertEqual((self.push_calls, self.live.books.journals()), (0, []))


class M3ScreenTests(unittest.TestCase):
    def test_phone_numbers_in_every_common_form_are_found_in_text_files(self):
        for value in (b'Call 8055551234', b'Text +18055551234', b'+1 (805) 555 1234', b'805 5551234', b'1-805-555-1234',
                      b'(805)555-1234', b'+44 20 7946 0958'):
            for path in ('index.html', 'catalog-products.js', 'community.json'):
                with self.subTest(value=value, path=path): self.assertEqual(p.privacy({path: value}, {}, ''), ['phone'])
        self.assertEqual(p.privacy({'a.js': b'ok'}, {}, 'hass live: call 8055551234'), ['phone'])

    def test_numbers_that_are_not_phones_stay_quiet(self):
        for value in (b'"lng": -120.8740879, "lat": 35.2741389', b'id a8055551234b', b'sha 3f8055551234c0', b'2026-11-09',
                      b'Mile 2.5', b'$12.50', b'93023-1234', b'v1.2.3'):
            with self.subTest(value=value): self.assertEqual(p.privacy({'index.html': value}, {}, ''), [])
        # image bytes keep the strict separator rule: a run of digits inside a picture is not a phone
        self.assertEqual(p.privacy({'assets/products/photo-product-167.webp': b'RIFF\x00\x003333333333+3333333334\x00'}, {}, ''), [])

    def test_an_owner_number_is_found_in_any_format_even_in_an_unchanged_file(self):
        for owner in ('+18055551234', 'iMessage;-;+18055551234', '+1 (805) 555-1234'):
            for value in (b'805-555-1234', b'(805) 555 1234', b'805.555.1234', b'+1 805 5551234', b'8055551234', b'tel:+18055551234',
                          b'8 0 5 5 5 5 1 2 3 4'):
                with self.subTest(owner=owner, value=value):
                    self.assertIn('owner', p.privacy({'index.html': value}, {'index.html': value}, '', (owner,)))
        self.assertIn('owner', p.privacy({'a.js': b'ok'}, {}, 'hass live: 805 555 1234', ('+18055551234',)))
        self.assertNotIn('owner', p.privacy({'index.html': b'805-555-9999'}, {}, '', ('+18055551234',)))

    def test_an_owner_email_is_found_in_any_letter_case(self):
        self.assertIn('owner', p.privacy({'index.html': b'MIKE@Gmail.COM'}, {'index.html': b'MIKE@Gmail.COM'}, '', ('mike@gmail.com',)))
        self.assertIn('owner', p.privacy({'index.html': b'x'}, {}, 'Mike@gmail.com', ('mike@GMAIL.com',)))


class L6Drill(Chat):
    SETTINGS_EXTRA = TWO

    def mike_change_goes_live(self):
        self.assertEqual(self.say("hours", chat=MCHAT, sender=MIKE), "proposed")
        self.sent()
        code = self.code()
        self.assertEqual(self.say(f"yes {code}", chat=MCHAT, sender=MIKE), "approved")
        self.sent()
        self.settle_and_flush()
        self.assertEqual(self.entry()["state"], "live")
        return code

    def test_the_original_owner_is_told_when_another_owners_undo_goes_live(self):
        code = self.mike_change_goes_live()
        self.now += pl.timedelta(minutes=5)
        self.assertEqual(self.say(f"undo {code}", chat=GCHAT, sender=GEE), "proposed")
        self.sent()
        self.assertEqual(self.say(f"yes {self.code()}", chat=GCHAT, sender=GEE), "approved")
        self.sent()
        shown = self.settle_and_flush()
        self.assertEqual(self.entry()["kind"], "undo")
        self.assertEqual(self.entry()["state"], "live")
        to_g = [t for c, t in shown if c == GCHAT]
        to_mike = [t for c, t in shown if c == MCHAT]
        self.assertTrue(any(answers.LIVE_SHOWN in t for t in to_g), shown)
        self.assertEqual(len(to_mike), 1, shown)
        self.assertIn("G took your change back off the website", to_mike[0])
        summary = self.conv.db.execute("SELECT summary FROM drafts WHERE code = ?", (code,)).fetchone()[0]
        self.assertIn(summary, to_mike[0])
        self.assertEqual(self.settle_and_flush(), [])  # said once

    def test_your_own_undo_is_not_reported_twice(self):
        code = self.mike_change_goes_live()
        self.now += pl.timedelta(minutes=5)
        self.assertEqual(self.say(f"undo {code}", chat=MCHAT, sender=MIKE), "proposed")
        self.sent()
        self.assertEqual(self.say(f"yes {self.code()}", chat=MCHAT, sender=MIKE), "approved")
        self.sent()
        shown = self.settle_and_flush()
        self.assertEqual([c for c, _t in shown], [MCHAT], shown)

    def test_grahams_revert_tells_the_owner_whose_change_it_took_back(self):
        self.assertEqual(self.say("hours", chat=GCHAT, sender=GEE), "proposed")
        self.sent()
        self.assertEqual(self.say(f"yes {self.code()}", chat=GCHAT, sender=GEE), "approved")
        self.sent()
        self.settle_and_flush()
        self.now += pl.timedelta(minutes=5)
        self.assertEqual(self.live.operate("revert-last")["result"], "ok")
        shown = self.settle_and_flush()
        self.assertEqual(shown, [(GCHAT, answers.LIVE_TAKEN_BACK)], shown)


if __name__ == "__main__":
    unittest.main()

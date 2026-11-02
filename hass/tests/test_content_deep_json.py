"""RF1920-4 (H05/H19) tests: a writer-worktree makers.json or community.json nested too deep is "unreadable" to the
claim check (the maker change asks), to status ("Hikes: unavailable") and to health's guest-count check ("hikes
unreadable"), never a RecursionError. Same fixtures as test_status_past_hikes / test_claims (temp Git repo, linked
writer worktree, 0700 state dir, fixed clock) and test_health_guests (temp state dir, plain temp worktree).
Run: python3 -m unittest hass.tests.test_content_deep_json -v
"""

import json
import subprocess
import unittest

from hass.tests import test_health_guests as hg
from hass.tests import test_status_past_hikes as ph
from hass.tests.test_conversation import _ops
from hass.tests.test_status_pause import StoreMixin
from hass.tests.test_undo import H06TestCase

DEEP = "[" * 100_000 + "]" * 100_000
LINNS = "these are from Linn’s"
LINNS_OPS = _ops(("product.edit", {"id": "photo-product-001", "producerKey": "Linn's"}))


class DeepConversationTests(StoreMixin, H06TestCase):
    hike, past = ph.PastHikeStatusTests.hike, ph.PastHikeStatusTests.past

    def content(self, name):
        return self.repo.wt / "hass" / "content" / name

    def worktree(self):  # every tracked or untracked change, plus the bytes of the edited content files
        status = subprocess.run(["git", "-C", str(self.repo.wt), "status", "--porcelain"], capture_output=True,
                                text=True, check=True).stdout
        return status, [self.content(n).read_bytes() for n in ("makers.json", "community.json")], self.commits()

    def status_unchanged(self):
        before = (self.drafts(), self.approvals(), self.worktree())
        lines = self.status()
        self.assertEqual((self.drafts(), self.approvals(), self.worktree()), before)
        return lines

    def test_deep_community_status_still_replies(self):  # 1, 4
        self.past("Past hike")
        valid = self.status_unchanged()
        self.assertEqual(valid[-1], ph.passed("Past hike", "Sun 2026-11-01 09:00 PST"))  # 4: main's status
        self.content("community.json").write_text(DEEP, "utf-8")
        deep = self.status_unchanged()
        self.assertEqual(deep, [x for x in valid if not x.startswith(("Hike", "…"))] + ["Hikes: unavailable"])
        self.assertNotIn("RecursionError", "\n".join(deep))

    def test_events_string_is_unavailable(self):  # 5: valid JSON, wrong shape (existing path)
        self.content("community.json").write_text(json.dumps({"events": "scheduled"}), "utf-8")
        self.assertEqual(self.status_unchanged()[-1], "Hikes: unavailable")

    def deepen_makers_after_prepare(self):  # a hand edit or damaged checkout landing before the claim check
        real = self.editor.prepare

        def prepare(*args):
            out = real(*args)
            self.content("makers.json").write_text(DEEP, "utf-8")
            return out
        self.editor.prepare = prepare

    def test_deep_makers_asks_never_applies(self):  # 3, 4
        self.interp.mapping[LINNS] = LINNS_OPS
        self.assertEqual(self.say(LINNS), "proposed")  # 4: valid makers.json, the owner named the maker
        self.replies()
        self.say("no")
        self.replies()
        self.deepen_makers_after_prepare()
        before = (self.drafts(), self.approvals())
        self.assertEqual(self.say(LINNS), "claim-question")  # _makers() is None: every maker change asks
        [reply] = self.replies()
        self.assertTrue(reply.startswith("I did not draft that: "), reply)
        self.assertIn('"maker" in products photo-product-001 producerKey', reply)
        self.assertEqual((self.drafts(), self.approvals(), self.commits()), before + (0,))
        status, files, commits = self.worktree()
        self.assertEqual((status.strip(), files[0].decode("utf-8"), commits), ("M hass/content/makers.json", DEEP, 0))

    def test_deep_makers_before_the_message_is_not_drafted(self):  # 3: the editor already refuses it, no crash
        self.content("makers.json").write_text(DEEP, "utf-8")
        self.interp.mapping[LINNS] = LINNS_OPS
        self.assertEqual(self.say(LINNS), "not-drafted")
        [reply] = self.replies()
        self.assertIn("nested too deeply", reply)
        self.assertEqual((self.drafts(), self.commits()), ([], 0))


class DeepHealthTests(unittest.TestCase):
    setUp, config, events, run_health, guests = (hg.HealthGuestsTest.setUp, hg.HealthGuestsTest.config,
                                                 hg.HealthGuestsTest.events, hg.HealthGuestsTest.run_health,
                                                 hg.HealthGuestsTest.guests)

    def check(self, raw):
        self.config()
        self.events(raw=raw)
        path = self.wt / "hass" / "content" / "community.json"
        files = sorted(str(p.relative_to(self.tmp)) for p in self.tmp.rglob("*"))
        code, found, doc = self.guests()
        self.assertEqual((path.read_text(), sorted(str(p.relative_to(self.tmp)) for p in self.tmp.rglob("*"))),
                         (raw, files))  # nothing written to the worktree (or anywhere under the temp dir)
        return code, found, doc

    def test_deep_community_is_hikes_unreadable(self):  # 2: exit code as for "{"
        expected = self.check("{")[:2]
        code, found, doc = self.check(DEEP)
        self.assertEqual((code, found), expected)
        self.assertEqual((code, doc["ok"], found), (0, True, []))
        self.assertIn(hg.HIKES_INFO, doc["info"])

    def test_valid_and_string_events(self):  # 4: main's report; 5: events a string stays info-only
        code, found, doc = self.check(json.dumps({"events": [hg.event("h1", 3)]}))
        self.assertEqual((code, found, hg.HIKES_INFO in doc["info"]), (1, [hg.UNSET], False))
        code, found, doc = self.check(json.dumps({"events": "scheduled"}))
        self.assertEqual((code, found, hg.HIKES_INFO in doc["info"]), (0, [], True))


if __name__ == "__main__":
    unittest.main()

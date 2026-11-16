"""AV2007-18: a guest limit on a hike whose sign-up is off, and 'take the notice down' with no notice up, say the real reason.
Run: python3 -B -m unittest hass.tests.test_chat_dead_end_reasons -q
"""
import copy
import unittest

from hass import voice
from hass.skills.testkit import run_case_row

HIKE = "hike-2026-11-21-cass-hill-hike"
EVENT = {"id": HIKE, "title": "Cass Hill Hike", "startsAt": "2026-11-21T09:00:00-08:00", "timezone": "America/Los_Angeles",
         "status": "scheduled", "meetingPoint": "Cass Hill gate", "rsvpEnabled": False}
OFF_SENTENCE = "Sign-up is off for Cass Hill Hike, so there is no guest limit to change. Nothing changed."
NO_NOTICE = "There is no notice on the website now. Nothing changed."
GUEST_COUNT = "can't see how many guests"


def row(rid, text, ops, expect, event=None):
    out = {"id": rid, "kind": "refuse", "texts": [text], "replies": [{"ops": ops, "revises": None}], "expect": expect}
    if event is not None: out["seed"] = {"community": {"events": [event]}}
    return out


def limit(rid, event, args=None):
    return row(rid, "only 10 spots on the cass hill hike", [{"op": "hike.update", "args": {"id": HIKE, "capacity": 10, **(args or {})}}],
               {"disposition": "not-drafted", "reply_contains": OFF_SENTENCE}, event)


def run(r):
    res = run_case_row(r, {}, None)
    return res


class SignUpOff(unittest.TestCase):
    def test_off_hike_names_the_real_reason(self):
        res = run(limit("off", EVENT))
        self.assertEqual(res.problems, [], res.problems)

    def test_on_hike_keeps_the_guest_count_reply(self):
        r = limit("on", {**EVENT, "rsvpEnabled": True, "capacity": 12})
        r["expect"] = {"disposition": "not-drafted", "reply_contains": GUEST_COUNT, "reply_not_contains": "Sign-up is off"}
        self.assertEqual(run(r).problems, [])

    def test_asking_for_sign_up_on_is_not_rewritten(self):
        r = limit("enable", EVENT, {"rsvpEnabled": True})
        r["expect"] = {"disposition": "not-drafted", "reply_not_contains": "Sign-up is off"}
        self.assertEqual(run(r).problems, [])

    def test_unreadable_flag_or_cancelled_hike_keeps_the_fallback(self):
        for name, event in (("noflag", {k: v for k, v in EVENT.items() if k != "rsvpEnabled"}),
                            ("cancelled", {**EVENT, "status": "cancelled"})):
            with self.subTest(name):
                r = limit(name, copy.deepcopy(event))
                r["expect"] = {"disposition": "not-drafted", "reply_not_contains": "Sign-up is off"}
                self.assertEqual(run(r).problems, [])


class NoNotice(unittest.TestCase):
    def test_absent_notice_clear_says_so(self):
        r = row("clear", "take the notice down", [{"op": "store.clear_notice", "args": {}}],
                {"disposition": "not-drafted", "reply_contains": NO_NOTICE, "reply_not_contains": "say it another way"})
        self.assertEqual(run(r).problems, [])

    def test_voice_mapping_is_exact_and_narrow(self):
        for technical in ("there is no notice", "  There is no notice ", "THERE IS NO NOTICE"):
            self.assertEqual(voice.explain(technical), (NO_NOTICE, "notice-absent"))
        for other in ("there is no notice board", "the noticeboard is full", "there is no notice to take down; x", "", None):
            self.assertNotEqual(voice.explain(other)[1], "notice-absent", other)
        self.assertEqual(voice.explain("nothing to clear")[1], "nothing-to-clear")
        self.assertEqual(voice.check(NO_NOTICE), [])


if __name__ == "__main__":
    unittest.main()

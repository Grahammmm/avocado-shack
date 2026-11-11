"""HASS-CHAT-1 transcript scenarios: natural owner texts, the questions Hass asks, and the one proposal it ends in.

Each row of hass/tests/fixtures/chat/scenarios.jsonl is one conversation on the live site (liveSite set, a named yes), run on
the H02 throwaway writer with the PRODUCTION op registry and a fixed clock (T0 = Monday 2026-11-02 09:00 Pacific), so it passes
on any calendar day. The interpreter is a scripted stand-in: ``model`` is what a correct model returns for that owner text
(null: the text never reaches the model, e.g. a bare yes, no or undo). Every turn names the disposition and the words its reply
must and must not hold; ``{code}`` is the newest draft's code. Rows may also pin what the shop's own date reader (nl_prep) works
out from a text (``dates``), and the stored hike after a yes (``event``). On EVERY reply: never "Graham", never a route id.
Row fields: docs in the fixture's first row ("about"). Run: python3 -m unittest hass.tests.test_chat_scenarios -v
"""

import json
import unittest
from datetime import date
from pathlib import Path

from hass import conversation, nl_prep, voice
from hass.tests.test_conversation import SETTINGS
from hass.tests.test_hike_flow import Clocked, FlowCase, Scripted

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "chat" / "scenarios.json"
SITE = "fixture.example.invalid"
TODAY = date(2026, 11, 2)  # T0's Pacific day (Monday)
NEVER = ("Graham", "idea-", "can't put this on the website from chat: it changes something")


def rows():
    return [row for row in json.loads(FIXTURE.read_text("utf-8")) if "turns" in row]


class ScenarioCase(FlowCase):
    def setUp(self):
        super().setUp()
        self.conv.db.close()
        self.set_settings({**SETTINGS, "liveSite": SITE, "approvalNeedsCode": True})
        self.asked = []
        self.interp = Scripted({}, self.asked)
        self.editor = Clocked(self.repo.state, lambda: self.now)
        self.conv = self.open()
        self.addCleanup(lambda: self.conv.db.close())

    def code(self):
        drafts = self.drafts()
        return drafts[-1]["code"] if drafts else ""

    def play(self, row):
        for n, turn in enumerate(row["turns"], 1):
            text = turn["owner"].replace("{code}", self.code())
            if turn.get("model") is not None:
                model = json.loads(json.dumps(turn["model"]).replace("{code}", self.code()))
                self.interp.mapping[text] = model
            got = self.say(text)
            replies = [voice.plain(r) for r in self.replies()]
            where = f"{row['id']} turn {n} ({text!r}): {replies}"
            self.assertEqual(got, turn["disposition"], where)
            joined = "\n".join(replies)
            for want in turn.get("has", ()):
                self.assertIn(want.replace("{code}", self.code()), joined, where)
            for bad in (*turn.get("lacks", ()), *NEVER):
                self.assertNotIn(bad, joined, where)
            if "event" in turn:
                events = json.loads((self.repo.wt / "hass" / "content" / "community.json").read_text("utf-8"))["events"]
                event = events[-1]
                for key, value in turn["event"].items():
                    if value is None:
                        self.assertNotIn(key, event, where)
                    else:
                        self.assertEqual(event.get(key), value, where)
            self.now = self.now.replace(minute=self.now.minute + 1)


class ScenarioTests(ScenarioCase):
    """One test per fixture row (added below), plus the count and the date reader."""

    def test_at_least_25_owner_messages(self):
        self.assertGreaterEqual(sum(len(r["turns"]) for r in rows()), 25)

    def test_the_date_reader_resolves_this_saturday_and_flags_next_saturday(self):
        for row in rows():
            for turn in row["turns"]:
                if "dates" in turn:
                    with self.subTest(text=turn["owner"]):
                        got, _ = nl_prep.date_hints(turn["owner"], TODAY)
                        self.assertEqual([{k: v for k, v in g.items() if k in ("date", "unclear", "next")} for g in got], turn["dates"])


def _scenario(row):
    def test(self):
        self.play(row)
    test.__doc__ = row.get("about")
    return test


for _row in rows():
    setattr(ScenarioTests, "test_" + _row["id"].replace("-", "_"), _scenario(_row))


if __name__ == "__main__":
    unittest.main()

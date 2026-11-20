"""AV2137-07 (H03/H17): `held` lists the held products (id, name, recorded hold reason and source), up to 20, with the fixed closing
sentence; read-only, works while paused, never releases a hold.
Run: python3 -B -m unittest hass.tests.test_held_command -v
"""

import copy
import json
import unittest
from datetime import timedelta

from hass import conversation, voice
from hass.tests.test_conversation import STRANGER, T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

CANT_READ = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"
REASON = "Manufacturer site displays Graziers raw-milk cheese recall; hold pending exact product/lot verification"
SOURCE = "https://sierranevadacheese.com/"
FOOTER = ("Held products stay off the website and Hass cannot release them. "
          "Check the package against the recall notice and tell G or the operator.")
HOLD = {"reason": REASON, "source": SOURCE, "evidence": "Supplied store photograph", "record": "storefront-mockup/held-products.json"}
# the two held records on main (hass/content/products.json), copied
MAIN_HELD = [
    {"id": "photo-product-040", "name": "Raw milk white cheddar", "brand": "Sierra Nevada", "category": "dairy",
     "image": "assets/products/photo-product-040.webp", "status": "held", "hold": dict(HOLD)},
    {"id": "photo-product-133", "name": "Raw Milk Goat Cheddar", "brand": "Sierra Nevada", "category": "dairy",
     "image": "assets/products/photo-product-133.webp", "status": "held", "hold": dict(HOLD, evidence="Original photograph")},
]


def line(pid, name, reason=REASON, source=SOURCE):
    return f"- {pid}: {name} \u2014 {reason} (source {source})"


class HeldParseTests(unittest.TestCase):
    def test_whole_message_only(self):
        for text in ("held", "Held.", "HELD!", "  held  "):
            self.assertEqual(conversation.parse_command(text), ("held", None), text)
        self.assertEqual(conversation.read_command("held?"), ("held", None))
        for text in ("held products", "held photo-product-040", "unheld", "not held", "helds", "held\nx", "held?!?"):
            self.assertNotEqual(conversation.parse_command(text), ("held", None), text)
        self.assertIsNone(conversation.parse_command("held products"))

    def test_help_line_and_read_only_verb(self):
        self.assertIn("held", voice.plain(conversation.HELP_TEXT))
        self.assertIn("why some products are on hold", voice.plain(conversation.help_detail("held")))
        self.assertIn("held", conversation.READ_ONLY)


class HeldTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "held reached the interpreter/editor"))

    def path(self, name="products.json"):
        return self.repo.wt / "hass" / "content" / name

    def products(self):
        return json.loads(self.path().read_text("utf-8"))

    def put(self, held):
        """Replace every held product in the worktree by `held` (full records)."""
        doc = self.products()
        doc["products"] = [p for p in doc["products"] if p["status"] != "held"] + held
        self.path().write_text(json.dumps(doc), "utf-8")

    def synthetic(self, n):
        return [dict(copy.deepcopy(MAIN_HELD[0]), id=f"held-product-{i:03d}", name=f"Held cheese {i}") for i in range(n)]

    def held(self, text="held"):
        self.assertEqual(self.say(text), "held")
        self.assertEqual(self.disposition(f"m{self.n}"), "held")
        [reply] = self.replies()
        return reply.splitlines()

    def state(self):
        """Every table but the message and outbox records, plus the content and the repository head."""
        db = self.conv.db
        rows = {}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall():
            if name not in ("messages", "outbox", "message_chats"):
                rows[name] = [tuple(r) for r in db.execute(f"SELECT * FROM {name}").fetchall()]
        return rows, self.path().read_text("utf-8"), self.commits(), self.editor.applies

    def test_held_two_main_records_exact_reason_source_footer(self):
        self.put(MAIN_HELD)
        before = self.state()
        self.assertEqual(self.held(), ["Held products:", line("photo-product-040", "Raw milk white cheddar"),
                                       line("photo-product-133", "Raw Milk Goat Cheddar"), FOOTER])
        self.assertEqual(self.state(), before)
        self.assertEqual(self.held("Held?")[-1], FOOTER)  # a closing ? works for a read-only command
        # held products are in no other list: hidden leaves both out, find still shows only the status
        self.assertEqual(self.say("hidden"), "hidden")
        self.assertNotIn("cheddar", self.replies()[0].lower())

    def test_held_empty_and_twenty_twenty_one_sorted(self):
        self.put([])
        self.assertEqual(self.held(), ["No products are held."])
        doc = self.products()
        hidden = [p for p in doc["products"] if p["status"] == "active"][:2]
        for p in hidden: p["status"] = "hidden"  # hidden and active products are never listed
        self.path().write_text(json.dumps(doc), "utf-8")
        self.assertEqual(self.held(), ["No products are held."])
        records = self.synthetic(21)
        records[3]["name"] = "Held   cheese   three"  # stored spacing goes on one line
        records[3]["hold"]["reason"] = "A reason that is long " * 12 + "and ends here"
        self.put(list(reversed(records[:20])))
        lines = self.held()
        self.assertEqual(len(lines), 22)
        self.assertEqual([x.split(":")[0] for x in lines[1:-1]], [f"- held-product-{i:03d}" for i in range(20)])
        self.assertEqual(lines[4], line("held-product-003", "Held cheese three", records[3]["hold"]["reason"]))
        self.assertEqual((lines[0], lines[-1]), ("Held products:", FOOTER))
        self.put(list(reversed(records)))
        lines = self.held()
        self.assertEqual(len(lines), 23)
        self.assertEqual(lines[-2:], ["... and 1 more", FOOTER])
        self.assertNotIn("held-product-020", "\n".join(lines))

    def test_held_bad_or_unreadable_content_refuses(self):
        good = self.path().read_text("utf-8")
        self.path().write_text("{not json", "utf-8")
        self.assertEqual(self.held(), [CANT_READ])
        self.path().unlink()
        self.assertEqual(self.held(), [CANT_READ])
        self.path().write_text(good, "utf-8")
        for label, change in (("no reason", lambda h: h.pop("reason")), ("blank reason", lambda h: h.update(reason="   ")),
                              ("number reason", lambda h: h.update(reason=5)), ("no source", lambda h: h.pop("source")),
                              ("http source", lambda h: h.update(source="http://sierranevadacheese.com/")),
                              ("spaced source", lambda h: h.update(source="https://x.example/a b")),
                              ("no hold", lambda h: h.clear())):
            with self.subTest(label):
                records = copy.deepcopy(MAIN_HELD)
                change(records[1]["hold"])
                if label == "no hold": del records[1]["hold"]
                self.put(records)
                self.assertEqual(self.held(), [CANT_READ])  # no partial list, the good record is not shown either
        self.put(MAIN_HELD)
        self.assertEqual(len(self.held()), 4)

    def test_held_read_only_before_dispatch(self):
        self.put(MAIN_HELD)
        draft, _reply = self.propose("hours")
        self.calls.clear()  # the proposal is the only allowed interpreter/editor use
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        self.now = T0 + timedelta(seconds=601)  # the waiting change lapsed; no other message has swept it yet
        before = self.state()
        self.assertEqual(self.held("HELD")[-1], FOOTER)
        self.assertEqual(self.state(), before)
        self.assertEqual((self.drafts()[0]["state"], self.approvals()), ("proposed", 0))
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")  # a later message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_held_auth_replay_and_parser(self):
        self.put(MAIN_HELD)
        self.assertEqual(self.say("held", pid="dup"), "held")
        self.assertEqual(len(self.replies()), 1)
        self.assertEqual(self.say("held", pid="dup"), "duplicate")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.say("held", sender=STRANGER, pid="stranger"), "ignored")
        self.assertEqual(self.replies(), [])
        self.assertEqual(self.say("held", from_me=True, pid="echo"), "echo")
        self.assertEqual(self.say("held", kind="reaction", pid="react"), "not-read")
        self.replies()
        self.calls.clear()
        self.say("held products please")  # a sentence is the interpreter's
        self.assertEqual(self.calls, ["interpret"])
        self.calls.clear()

    def test_held_voice_exception_is_literal_only(self):
        self.assertEqual(voice.check(FOOTER, long_ok=True), [])
        self.assertEqual(voice.check("Held products:\n" + voice.quote(line("photo-product-040", "Raw milk")) + "\n" + FOOTER, long_ok=True), [])
        self.assertIn("the word 'operator'", voice.check("Ask the operator.", long_ok=True))
        self.assertIn("the word 'operator'", voice.check("Held products:\nAsk the operator.\n" + FOOTER, long_ok=True))
        self.assertIn("the word 'operator'", voice.check(FOOTER.replace("G or the", "G, the"), long_ok=True))
        self.assertIn("the word 'operator'", voice.check("Please. " + FOOTER, long_ok=True))
        self.assertIn("the word 'error'", voice.check(FOOTER + "\nAn error.", long_ok=True))
        self.assertEqual(voice.HELD_GUIDANCE, FOOTER)


if __name__ == "__main__":
    unittest.main()

"""AV1922-01 (H06/H17): `look` replies a fresh phone-width picture of the private preview as it is now.
Fake previewer, synthetic fixtures only. Run: python3 -B -m unittest hass.tests.test_look_command -v"""

import json
import os
import stat
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

from hass import conversation, preview, retention
from hass.chat import commands
from hass.content_model import load_content, shop_today
from hass.tests.test_conversation import CHAT, GROUP, STRANGER, T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

OK, FAIL = "The website now (private preview, phone):", "I could not take a picture of the site right now; nothing changed."
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 16
PASS = {"productShown": True, "noPageErrors": True}


class FakePreviewer:
    """Records every call; writes the picture the way the real previewer does (private, whole or not at all)."""

    def __init__(self, result=None, raises=None, write=True):
        self.calls, self.result, self.raises, self.write = [], result, raises, write

    def capture(self, files, target, out_png, assets=None, *, viewports=None):
        self.calls.append({"files": files, "target": target, "out": Path(out_png), "viewports": viewports, "assets": assets})
        if self.raises: raise self.raises
        if self.write: preview._write_private(Path(out_png), PNG)
        return self.result if self.result is not None else {"ok": True, "png": str(out_png), "checks": dict(PASS), "error": None}


class LookParseTests(unittest.TestCase):
    def test_whole_message_forms_and_lookalikes(self):
        for text, want in (("look", ""), (" Look. ", ""), ("LOOK hike!", "hike"), ("look  Hass  avocado.", "Hass  avocado"),
                           ("look photo-product-001", "photo-product-001")):
            self.assertEqual(conversation.parse_command(text), ("look", want), text)
        self.assertEqual(conversation.read_command("look?"), ("look", ""))
        for text in ("looks", "looking at hike", "please look", "look-alike", "lookhike"):
            self.assertIsNone(conversation.parse_command(text), text)

    def test_malformed_rest_is_usage_not_a_query(self):
        for text in ("look a\nb", "look a\x07b", "look " + "x" * 61):
            self.assertEqual(conversation.parse_command(text), ("look", None), repr(text))
        self.assertEqual(conversation.parse_command("look " + "x" * 60), ("look", "x" * 60))
        self.assertIn("look", commands.READ_ONLY)


class LookTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.fake, self.stocked = FakePreviewer(), False
        self.conv.previewer = self.fake
        self.shots = self.repo.state / "screenshots"
        self.ids = [p["id"] for p in self.content().products[:6]]

    def stock(self):
        """Give the first six products known names and statuses (once; left uncommitted, so draft tests call it after proposing)."""
        if self.stocked: return
        self.stocked, path = True, self.repo.wt / "hass" / "content" / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        for p, (status, name) in zip(doc["products"], (("active", "Green Jam"), ("active", "Red Jam"), ("held", "Held Thing"),
                                                       ("hidden", "Hidden Thing"), ("active", "Etto Olive Oil"), ("active", "Solo Thing"))):
            p.update(status=status, name=name)
        path.write_text(json.dumps(doc), "utf-8")

    def look(self, text="look"):
        self.stock()
        self.assertEqual(self.say(text), "look")
        self.assertEqual(self.disposition(f"m{self.n}"), "look")
        [row] = self.conv.db.execute("SELECT text, attachments FROM outbox ORDER BY id DESC LIMIT 1").fetchall()
        self.assertEqual(len(self.replies()), 1)
        return row["text"], json.loads(row["attachments"] or "[]")

    def content(self):
        return load_content(self.repo.wt / "hass" / "content")

    def snapshot(self):
        tables = {n: [tuple(r) for r in self.conv.db.execute(f"SELECT * FROM {n}")]
                  for n in {"drafts", "approvals"} | ({"usage", "control", "memory"} & self.tables())}
        return tables, self.repo.head(), (self.repo.wt / "hass" / "content" / "products.json").read_bytes()

    def test_look_current_home_hike_and_product_targets(self):
        self.stock()
        content = self.content()
        text, files = self.look("look")
        self.assertEqual(text, OK)
        [call] = self.fake.calls
        self.assertEqual(call["target"], preview.target_for({"collection": "store", "after": content.store}, shop_today(self.now)))
        self.assertEqual((call["files"], call["viewports"], call["assets"]), ({}, ("phone",), None))
        self.assertEqual(files, [str(call["out"])])
        self.assertEqual((call["out"].parent, call["out"].name[:5], call["out"].suffix), (self.shots, "look-", ".png"))
        self.assertEqual(call["out"].name, "look-20261102T170000000000Z.png")
        self.assertEqual(stat.S_IMODE(call["out"].stat().st_mode), 0o600)
        self.look("Look hike.")
        self.assertEqual(self.fake.calls[1]["target"], preview.target_for({"collection": "events", "key": "", "after": {}}))
        self.assertEqual(self.fake.calls[1]["target"], {"kind": "event", "title": "", "status": None, "id": "", "recap": ""})
        self.look(f"look {self.ids[0]}")
        product = next(p for p in content.products if p["id"] == self.ids[0])
        self.assertEqual(self.fake.calls[2]["target"], preview.target_for({"collection": "products", "key": product["id"], "after": product}))
        self.assertEqual(self.fake.calls[2]["target"]["kind"], "product")
        self.assertTrue(all(c["viewports"] == ("phone",) and c["files"] == {} for c in self.fake.calls))

    def test_look_shows_content_as_it_is_now_never_a_cached_picture(self):
        self.look("look")
        path = self.repo.wt / "hass" / "content" / "store.json"
        doc = json.loads(path.read_text("utf-8"))
        doc["streetAddress"] = "2 Example Street"
        path.write_text(json.dumps(doc), "utf-8")
        self.now += timedelta(minutes=1)
        text, files = self.look("look")
        self.assertEqual(self.fake.calls[1]["target"]["streetAddress"], "2 Example Street")
        self.assertNotEqual(self.fake.calls[0]["out"], self.fake.calls[1]["out"])
        self.assertEqual(files, [str(self.fake.calls[1]["out"])])

    def test_look_active_id_name_alias_and_ambiguity(self):
        self.assertEqual(self.look("look green jam")[0], OK)  # a name, case folded
        self.assertEqual(self.fake.calls[-1]["target"]["id"], self.ids[0])
        self.assertEqual(self.say("alias etto: " + self.ids[4]), "memory-saved")
        self.replies()
        self.assertEqual(self.look("look Etto")[0], OK)
        self.assertEqual(self.fake.calls[-1]["target"]["id"], self.ids[4])
        n = len(self.fake.calls)
        text, files = self.look("look jam")  # two active products
        jams = sorted(f"{p['id']} - {p['name']}" for p in self.content().products if p["status"] == "active" and "jam" in p["name"].lower())
        self.assertGreater(len(jams), 2)
        self.assertEqual(text.splitlines()[1:], jams[:10] + (["There are more. Add a word to narrow it down."] if len(jams) >= 10 else []))
        self.assertIn("more than one active product", text)
        for send, want in ((f"look {self.ids[2]}", f"{self.ids[2]} is not on the site; send find <words> for ids."),
                           (f"look {self.ids[3]}", f"{self.ids[3]} is not on the site; send find <words> for ids."),
                           ("look held thing", 'No active product matches "held thing"; send find <words> for ids.'),
                           ("look hidden thing", 'No active product matches "hidden thing"; send find <words> for ids.'),
                           ("look nosuch-id", 'No active product matches "nosuch-id"; send find <words> for ids.')):
            with self.subTest(send=send):
                text, files = self.look(send)
                self.assertEqual((text, files), (want, []))
        self.assertEqual(len(self.fake.calls), n)  # none of them took a picture

    def test_look_alias_table_is_not_created_by_a_read(self):
        self.assertNotIn("memory", self.tables())
        self.assertEqual(self.look("look Solo Thing")[0], OK)
        self.assertNotIn("memory", self.tables())

    def test_look_hike_wins_over_a_product_named_hike(self):
        self.look("look HIKE")
        self.assertEqual(self.fake.calls[0]["target"]["kind"], "event")

    def test_look_failure_never_attaches_or_leaks(self):
        self.conv.previewer = None
        self.assertEqual(self.look("look"), (FAIL, []))
        broken = {"ok": False, "png": None, "checks": {}, "error": "boom /home/x http://127.0.0.1:1"}
        cases = (FakePreviewer(raises=RuntimeError("secret /home/x")), FakePreviewer(result=broken),
                 FakePreviewer(result={"ok": True, "png": None, "checks": dict(PASS)}),  # png is not the expected file
                 FakePreviewer(result={"ok": "yes", "png": "x", "checks": dict(PASS)}), FakePreviewer(result="ok"),
                 FakePreviewer(result={"ok": True, "png": "set below", "checks": {}}),  # no checks
                 FakePreviewer(result={"ok": True, "png": "set below", "checks": {"a": True, "b": 1}}),
                 FakePreviewer(write=False))  # claims success but no file
        for fake in cases:
            self.conv.previewer = fake
            if isinstance(fake.result, dict) and fake.result.get("png") == "set below":
                fake.result["png"] = str(self.shots / "look-20261102T170000000000Z.png")
            with self.subTest(result=fake.result):
                self.now += timedelta(seconds=1)
                self.assertEqual(self.look("look"), (FAIL, []))
        failing = FakePreviewer()  # a failed page check leaves its own picture behind: still no attachment
        failing.result = {"ok": False, "png": None, "checks": {"productShown": False}, "error": "check failed: productShown"}
        self.conv.previewer = failing
        self.now += timedelta(seconds=1)
        self.assertEqual(self.look("look"), (FAIL, []))
        self.assertTrue(failing.calls[0]["out"].is_file())
        self.assertTrue(all(FAIL == row["text"] for row in self.conv.db.execute("SELECT text FROM outbox WHERE text LIKE '%picture%'")))

    def test_look_unsafe_screenshots_folder_or_unreadable_content(self):
        outside = self.repo.state / "elsewhere"
        outside.mkdir()
        self.shots.symlink_to(outside)
        self.assertEqual(self.look("look"), (FAIL, []))
        self.assertEqual(self.fake.calls, [])
        self.shots.unlink()
        (self.repo.wt / "hass" / "content" / "products.json").write_text("{not json", "utf-8")
        self.assertEqual(self.look("look"), (FAIL, []))
        self.assertEqual(self.look("look hike"), (FAIL, []))
        self.assertEqual(self.fake.calls, [])

    def test_look_no_expiry_model_or_business_writes(self):
        draft, _reply = self.propose("hours")
        self.stock()
        self.say("pause changes")
        self.replies()
        self.now += timedelta(seconds=601)  # the draft is past its time
        before = self.snapshot()
        with mock.patch.object(self.interp, "interpret", side_effect=AssertionError("model")), \
                mock.patch.object(type(self.conv), "_move", side_effect=AssertionError("expiry")), \
                mock.patch("socket.socket", side_effect=AssertionError("network")):
            for send in ("look", "look hike", f"look {self.ids[0]}", f"look {self.ids[2]}", "look jam", "look", "look a\nb"):
                with self.subTest(send=send):
                    self.look(send)
        self.assertEqual(self.snapshot(), before)  # works while paused; draft untouched, not expired
        self.assertEqual(self.drafts()[0]["state"], "proposed")
        self.assertEqual(self.commits(), 0)
        self.conv.db.execute("DELETE FROM control")
        self.say("when?")  # the next ordinary message still expires it
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_look_guard_precedence_and_parser_boundaries(self):
        for kw in (dict(sender=STRANGER), dict(chat=GROUP), dict(from_me=True), dict(kind="edited")):
            self.say("look", **kw)
        self.say("look", pid="dup-1")
        self.say("look", pid="dup-1")
        self.assertEqual(len(self.fake.calls), 1)  # a duplicate is not answered twice; strangers/echo/edits never capture
        for text in ("looks good", "look at the weather today please"):  # not the whole-message command with a known product
            self.say(text)
        n = len(self.fake.calls)
        self.say("look", kind="new", pid="photo-1")  # plain again
        self.assertEqual(len(self.fake.calls), n + 1)
        msg = conversation.Inbound("cap-1", CHAT, "owner@example.invalid", "look", False, "new", self.now.isoformat(), attachments=1)
        self.conv.handle(msg)
        self.assertEqual(len(self.fake.calls), n + 1)  # a photo caption is not a command

    def test_look_private_unique_screenshots_are_retained(self):
        names = []
        for _ in range(3):  # the injected clock does not move
            self.look("look")
            names.append(self.fake.calls[-1]["out"].name)
        self.assertEqual(names, ["look-20261102T170000000000Z.png", "look-20261102T170000000001Z.png", "look-20261102T170000000002Z.png"])
        files = sorted(self.shots.glob("look-*.png"))
        self.assertEqual([f.name for f in files], names)
        self.assertTrue(all(stat.S_IMODE(f.stat().st_mode) == 0o600 for f in files))
        (self.shots / "look-link.png").symlink_to(files[0])
        for f in files: os.utime(f, (0, 0))
        got = retention._shots(self.shots, T0 + timedelta(days=1))
        self.assertEqual(got, {"files": 3, "bytes": 3 * len(PNG)})  # counted like any screenshot; the link is not
        self.assertEqual(len(list(self.shots.glob("look-*.png"))), 4)  # nothing deleted


if __name__ == "__main__":
    unittest.main()

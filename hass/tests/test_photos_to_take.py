"""AV0222-04 (H10/H17): `photos to take` lists active products whose picture is not an installed photo-<16 hex> file,
by shelf in site order (10 names), read-only, works while paused. Run: python3 -B -m unittest hass.tests.test_photos_to_take
"""

import json
import shutil
import unittest
from datetime import timedelta

from hass import conversation, voice
from hass.content_model import CATEGORIES
from hass.tests.test_conversation import T0, ConversationTestCase
from hass.tests.test_status_pause import StoreMixin

UNAVAILABLE = "I can't look that up right now. Nothing has changed. Could you try again in a little while?"
GUIDE = "To replace one, send a photo with the product's name as the caption."
SAVED = "From saved listings, not a live website check."
HEX = "0123456789abcdef"


def head(n):
    return "Some products still show a stock picture instead of your own photo. The first few:"


class PhotosParseTests(unittest.TestCase):
    def test_exact_parser_help_and_lookalikes(self):
        for text in ("photos to take", "Photos To Take.", "PHOTOS TO TAKE!", "  photos to take  "):
            self.assertEqual(conversation.parse_command(text), ("photos", None), text)
        for text in ("photos", "photos to take please", "photos to take?", "which photos to take", "photos  to take"):
            self.assertIsNone(conversation.parse_command(text), text)
        self.assertEqual(conversation.parse_command("hidden"), ("hidden", None))
        self.assertEqual(conversation.parse_command("listing Etto"), ("listing", "Etto"))
        self.assertIn('photos to take - the products that still need a photo', voice.plain(conversation.HELP_TEXT).splitlines())


class PhotosTests(StoreMixin, ConversationTestCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        for obj, name in ((self.interp, "interpret"), (self.editor, "prepare"), (self.editor, "apply")):
            real = getattr(obj, name)
            setattr(obj, name, lambda *a, _r=real, _n=name, **k: (self.calls.append(_n), _r(*a, **k))[1])
        self.addCleanup(lambda: self.assertEqual(self.calls, [], "photos to take reached the interpreter/editor"))

    @property
    def path(self):
        return self.repo.wt / "hass" / "content" / "products.json"

    def load(self):
        return json.loads(self.path.read_text("utf-8"))

    def fixture(self, rows):
        """rows: (name, category, status, image); image None keeps the product's own catalog picture. Asset files are
        copies of one existing picture so content validation passes."""
        doc = self.load()
        base = doc["products"][0]
        assets = self.repo.wt / "storefront-mockup" / "assets"
        if assets.is_symlink():  # a private copy, so the shared site assets are never written
            target = assets.resolve()
            assets.unlink()
            shutil.copytree(target, assets)
        src = self.repo.wt / "storefront-mockup" / base["image"]
        out = []
        for i, (name, cat, status, image) in enumerate(rows):
            p = dict(base, id=f"p-{i:03d}", name=name, category=cat, status=status)
            if status == "held": p["hold"] = {"reason": "checking", "source": "https://example.com/"}
            if image is not None:
                dest = self.repo.wt / "storefront-mockup" / image
                if not dest.exists(): shutil.copy(src, dest)
                p["image"] = image
            out.append(p)
        doc["products"] = out
        self.path.write_text(json.dumps(doc), "utf-8")

    def photos(self, text="photos to take"):
        self.assertEqual(self.say(text), "photos")
        self.assertEqual(self.disposition(f"m{self.n}"), "photos")
        [reply] = self.replies()
        return reply.splitlines()

    def test_candidates_exclude_installed_hidden_and_held(self):
        self.fixture([("Legacy", "fruit", "active", None),
                      ("Installed jpg", "fruit", "active", f"assets/products/photo-{HEX}.jpg"),
                      ("Installed png", "fruit", "active", f"assets/products/photo-{HEX}.png"),
                      ("Hidden legacy", "fruit", "hidden", None), ("Held legacy", "fruit", "held", None)])
        self.assertEqual(self.photos(), [head(1), "- Legacy (Fruit)", GUIDE])

    def test_fullmatch_not_similar_filename(self):
        names = {"fifteen": f"photo-{HEX[:15]}.jpg", "seventeen": f"photo-{HEX}0.jpg", "upper": f"photo-{HEX.upper()}.jpg",
                 "prefixed": f"x-photo-{HEX}.jpg", "webp": f"photo-{HEX}.webp", "jpeg": f"photo-{HEX}.jpeg"}
        self.fixture([("ok", "eggs", "active", f"assets/products/photo-{HEX}.jpg")]
                     + [(n, "eggs", "active", f"assets/products/{f}") for n, f in names.items()])
        lines = self.photos()
        self.assertEqual(lines[0], head(len(names)))
        self.assertEqual(sorted(lines[1:-1]), sorted(f"- {n} (Eggs)" for n in names))

    def test_shelf_order_name_ties_and_global_ten_cap(self):
        order = ["fruit", "vegetables", "dairy", "eggs", "meat", "pantry", "drinks", "bread", "flowers"]
        self.assertEqual(list(CATEGORIES), order)
        labels = ["Fruit", "Vegetables", "Dairy & cheese", "Eggs", "Meat", "Pantry", "Drinks & coffee", "Bread", "Flowers"]
        rows = [("zed", "flowers", "active", None), ("Bee", "bread", "active", None), ("apple", "bread", "active", None),
                ("Twin", "fruit", "active", None), ("Twin", "fruit", "active", None), ("cat", "fruit", "active", None)]
        self.fixture(rows)
        self.assertEqual(self.photos(), [head(6), "- cat (Fruit)", "- Twin (Fruit)", "- Twin (Fruit)", "- apple (Bread)", "- Bee (Bread)", "- zed (Flowers)", GUIDE])
        for total, extra in ((10, None), (11, "When you've sent those, ask again and I'll show the next few."), (23, "When you've sent those, ask again and I'll show the next few.")):
            self.fixture([(f"n{i:02d}", order[i % 9], "active", None) for i in range(total)])
            lines = self.photos()
            self.assertEqual(lines[0], head(total))
            names = [ln for ln in lines if ln.startswith("- ")]
            self.assertEqual(len(names), 10)
            heads = [ln.rsplit(" (", 1)[1][:-1] for ln in names]
            self.assertEqual(heads, sorted(heads, key=labels.index))  # site order
            self.assertEqual(lines[-2:], [extra, GUIDE] if extra else [names[-1], GUIDE])
        self.fixture([])
        self.assertEqual(self.photos(), ["Every product on the website has your own photo."])

    def test_unreadable_and_invalid_catalog(self):
        good = self.path.read_text("utf-8")
        self.path.write_text("{not json", "utf-8")
        self.assertEqual(self.photos(), [UNAVAILABLE])
        self.path.write_text(good, "utf-8")
        self.fixture([("bad", "snacks", "active", None)])
        self.assertEqual(self.photos(), [UNAVAILABLE])
        doc = json.loads(good)
        doc["products"][0]["image"] = "assets/products/nope.jpg"  # no such file
        self.path.write_text(json.dumps(doc), "utf-8")
        self.assertEqual(self.photos(), [UNAVAILABLE])
        self.path.write_text(good, "utf-8")

    def test_paused_and_lapsed_draft_keep_state(self):
        draft, _reply = self.propose("hours")
        self.calls.clear()
        self.assertEqual(self.say("pause changes"), "pause")
        self.replies()
        control = [dict(r) for r in self.conv.db.execute("SELECT * FROM control")]
        self.now = T0 + timedelta(seconds=601)
        self.assertEqual(self.photos("PHOTOS TO TAKE")[-1], GUIDE)
        self.assertEqual([dict(r) for r in self.conv.db.execute("SELECT * FROM control")], control)
        self.assertEqual((self.drafts()[0]["state"], self.approvals(), self.editor.applies), ("proposed", 0, 0))
        self.assertEqual(self.say(f"yes {draft['code']}"), "no-target")
        self.assertEqual(self.drafts()[0]["state"], "expired")

    def test_sentence_is_not_the_command(self):
        self.calls.clear()
        self.say("photos to take please")
        self.assertEqual(self.calls, ["interpret"])
        self.calls.clear()


if __name__ == "__main__":
    unittest.main()

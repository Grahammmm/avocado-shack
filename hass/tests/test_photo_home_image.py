"""AV1937-01 (H12/H13) tests: a photo question answered "use it on the home page" becomes store.set_home_image with
that photo; one photo goes to one place; the photo prompt rule and the status count follow.

Harness of test_photo_draft (temp Git repo + writer worktree, private media root outside the repo), a fake photo
source and a fixture interpreter. Nothing is downloaded or sent.
Run: python3 -m unittest hass.tests.test_photo_home_image -v
"""

import json
import unittest
from datetime import timedelta

from hass import conversation
from hass.conversation import PHOTO_QUESTION, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.interpreter_prompt import build
from hass.tests.test_catalog_ops import IMAGE, NEW
from hass.tests.test_conversation import CHAT, OWNER, T0
from hass.tests.test_interpreter_prompt import FIXTURE, TEST_REGISTRY, tiny_content
from hass.tests.test_photo_draft import JPG, PNG, PNG_SHA, SHA
from hass.tests.test_photo_new_product import ADD
from hass.tests.test_set_photo import ALT, PID
from hass.tests import test_status_photos as status_photos

HOME = "store.set_home_image"
HALT = "The shop front in morning light"
STORE = "hass/content/store.json"
MANY = "One photo can go in one place; say which."
WEB = f"assets/products/photo-{SHA[:16]}.jpg"


def _op(op, /, **args):
    return {"op": op, "args": args}


def _home(imageAlt=HALT, **args):
    return _op(HOME, imageAlt=imageAlt, **args)


class HomeInterpreter:
    """Fixture: a mapped text answers with (ops, revises); revises True names the newest waiting draft, a string names that code."""

    def __init__(self):
        self.mapping = {}

    def interpret(self, text, pending, **kw):
        if text not in self.mapping: return {"unsupported": "Sorry, I can't do that yet."}
        ops, revises = self.mapping[text]
        waiting = [p["code"] for p in pending if p["state"] == "needs-details"]
        return {"ops": ops, "revises": (waiting[-1] if waiting else None) if revises is True else revises or None}


class HomePhotoBase(status_photos.Harness):
    def setUp(self):
        super().setUp()
        self.interp, self.now = HomeInterpreter(), T0
        self.conv = self.open()

    def open(self, photos="fake"):
        return conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), self.interp,
                                         lambda: self.now, photos=self.photos if photos == "fake" else photos)

    def say(self, text="", attachments=0, ops=None, revises=True):
        if ops is not None: self.interp.mapping[text] = (ops, revises)
        self.n += 1
        return self.conv.handle(Inbound(f"m{self.n}", CHAT, OWNER, text, received_at=T0.isoformat(), attachments=attachments))

    def photo_draft(self):
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.replies()
        return self.drafts()[-1]

    def photo_ops(self, row):
        return [(c["op"], c["args"].get("photo")) for c in json.loads(row["ops_json"])]

    def state(self):
        return (self.repo.head(), self.repo.read(STORE), self.repo.products(), self.drafts())

    def hero(self):
        return json.loads(self.repo.read(STORE)).get("homeImage")


class HomePhotoTests(HomePhotoBase):
    def test_question_offers_product_new_product_and_home_page(self):
        for word in ("product in the shop", "new product", "home page", "cannot see it"):
            self.assertIn(word, PHOTO_QUESTION)
        self.assertEqual(self.photo_draft()["summary"], PHOTO_QUESTION)

    def test_home_photo_later_answer_and_caption(self):
        self.photo_draft()
        self.assertEqual(self.say("use it on the home page", ops=[_home()]), "proposed")  # later answer
        [row] = self.drafts()
        self.assertEqual((row["state"], row["code"], self.photo_ops(row)), ("proposed", SHA[:4], [(HOME, SHA)]))
        self.replies()
        head, store, products = self.repo.head(), self.repo.read(STORE), self.repo.products()
        self.assertEqual((self.hero(), self.repo.head()), (None, head))  # preparing changed nothing
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.drafts()[0]["state"], "applied")
        self.assertEqual(self.hero(), {"image": WEB, "imageAlt": HALT})
        self.assertNotEqual(self.repo.read(STORE), store)
        self.assertEqual(self.repo.products(), products)  # only the home slot changed
        self.photos.data = PNG  # the same answer as a caption on the photo itself
        self.assertEqual(self.say("home page, front again", attachments=1, ops=[_home()]), "proposed")
        self.assertEqual(self.photo_ops(self.drafts()[-1]), [(HOME, PNG_SHA)])
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.hero()["image"], f"assets/products/photo-{PNG_SHA[:16]}.png")

    def test_home_photo_missing_alt_then_details(self):
        self.photo_draft()
        self.assertEqual(self.say("the home page", ops=[_op(HOME)]), "needs-details")
        self.assertEqual(self.say("hmm", ops=[_op(HOME)]), "needs-details")  # another incomplete answer
        [row] = self.drafts()
        self.assertEqual((row["state"], row["code"], self.photo_ops(row)), ("needs-details", SHA[:4], [(HOME, SHA)]))
        self.replies()
        self.assertEqual(self.say("status"), "status")
        self.assertEqual(status_photos.StatusPhotoTests.photo_line(self, self.replies()[0].splitlines()),
                         ["A photo is waiting for details from you."])
        self.assertEqual(self.say("it shows the shop front", ops=[_home()]), "proposed")
        self.assertEqual([(d["state"], self.photo_ops(d)) for d in self.drafts()], [("proposed", [(HOME, SHA)])])
        self.assertEqual(self.hero(), None)

    def test_home_and_product_destinations_refused(self):
        before = self.photo_draft()
        state = self.state()
        cases = {"home + set_photo": [_home(), _op("product.set_photo", id=PID, imageAlt=ALT)],
                 "set_photo + home": [_op("product.set_photo", id=PID, imageAlt=ALT), _home()],
                 "home + add": [_home(), _op("product.add", **ADD)],
                 "two home": [_home(), _home("Another view of the shop front")]}
        for name, ops in cases.items():
            with self.subTest(name):
                self.assertEqual(self.say(name, ops=ops), "photo-many-ops")
                self.assertEqual(self.replies(), [MANY])
                self.assertEqual(self.state(), state)
        self.assertEqual(self.drafts(), [before])
        self.assertEqual(self.repo.product(PID)["image"], IMAGE)

    def test_home_photo_mismatch_and_no_revises(self):
        before = self.photo_draft()
        state = self.state()
        self.assertEqual(self.say("other photo", ops=[_home(photo=PNG_SHA)]), "photo-mismatch")
        self.assertEqual(self.replies(), ["That answer goes with a different photo, so nothing changed. "
                                          "Which product is this photo for?"])
        self.assertEqual(self.state(), state)
        self.assertEqual(self.say("home, no draft", ops=[_home()], revises=False), "needs-details")  # never borrows the waiting photo
        self.assertEqual(self.state()[:3], state[:3])
        [waiting, asked] = self.drafts()
        self.assertEqual((waiting, self.photo_ops(asked)), (before, [(HOME, None)]))
        self.replies()
        self.assertNotEqual(self.say("home, unknown code", ops=[_home()], revises="zzzz"), "proposed")
        self.assertEqual((self.repo.head(), self.drafts()), (state[0], [waiting, asked]))  # a safe question, nothing written
        self.assertEqual(len(self.replies()), 1)

    def test_home_photo_bad_alt_and_bad_args(self):
        self.photo_draft()
        state = self.state()
        cases = {"file name": [_op(HOME, imageAlt="IMG_1234.jpg")], "generic": [_op(HOME, imageAlt="photo")],
                 "markup": [_op(HOME, imageAlt="<b>Shop</b><script>x</script>")],
                 "alt kind": [_op(HOME, imageAlt=7)], "photo kind": [_op(HOME, imageAlt=HALT, photo=5)],
                 "unknown field": [_home(style="wide")], "empty alt": [_op(HOME, imageAlt="")]}
        for name, ops in cases.items():
            with self.subTest(name):
                self.assertNotIn(self.say(name, ops=ops), ("proposed", "approved", "applied"))
                self.replies()
                self.assertEqual((self.repo.head(), self.repo.read(STORE), self.repo.products()), state[:3])
                self.assertEqual(self.hero(), None)
                self.assertNotIn("proposed", [d["state"] for d in self.drafts()])
        self.assertEqual(self.say("yes"), self.say("yes"))  # nothing proposed, so nothing to approve
        self.assertEqual(self.repo.head(), state[0])

    def test_home_photo_cancel_expire_duplicate(self):
        self.photo_draft()
        self.assertEqual(self.say("home", ops=[_op(HOME)]), "needs-details")
        self.replies()
        self.say("yes")  # an incomplete question cannot be approved
        self.assertEqual((self.hero(), [d["state"] for d in self.drafts()]), (None, ["needs-details"]))
        self.assertEqual(self.say(attachments=1), "photo-duplicate")  # the same photo again adds no row
        self.assertEqual(len(self.drafts()), 1)
        self.say("no")
        self.assertEqual([d["state"] for d in self.drafts()], ["rejected"])
        self.say("home, it shows the shop front", ops=[_home()])  # a cancelled question is not filled later
        [cancelled, asked] = self.drafts()  # it asks afresh and never borrows the cancelled photo
        self.assertEqual((self.hero(), cancelled["state"], asked["state"], self.photo_ops(asked)),
                         (None, "rejected", "needs-details", [(HOME, None)]))
        self.photos.data = PNG  # a new photo: ask, then let the question lapse
        self.assertEqual(self.say(attachments=1), "photo-draft")
        self.assertEqual(self.say("home", ops=[_op(HOME)]), "needs-details")
        self.now = T0 + timedelta(seconds=601)
        self.say("it shows the shop front", ops=[_home()])
        self.assertEqual(self.hero(), None)
        self.assertNotIn("proposed", [d["state"] for d in self.drafts()])
        self.say("yes")
        self.assertEqual(self.hero(), None)

    def test_home_photo_undo_restores_previous_slot(self):
        before = self.repo.read(STORE)
        self.photo_draft()
        self.say("home", ops=[_home()])
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.hero()["imageAlt"], HALT)
        self.assertEqual(self.say("undo"), "proposed")
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual((self.hero(), self.repo.read(STORE)), (None, before))  # absent again
        self.photos.data = PNG  # an existing slot: set, replace, undo back to the first
        self.assertEqual(self.say(attachments=1, text="home", ops=[_home()]), "proposed")
        self.say("yes")
        first = self.hero()
        self.photos.data = JPG
        self.assertEqual(self.say(attachments=1, text="home too", ops=[_home(imageAlt="The shop front at noon")]), "proposed")
        self.say("yes")
        self.assertNotEqual(self.hero(), first)
        self.assertEqual(self.say("undo"), "proposed")
        self.assertEqual(self.say("yes"), "approved")
        self.assertEqual(self.hero(), first)


class HomeStatusTests(HomePhotoBase):
    status, insert, photo_line, inbox = (vars(status_photos.StatusPhotoTests)[n] for n in ("status", "insert", "photo_line", "inbox"))

    def test_status_counts_home_photo_read_only(self):
        photo = "1" * 64
        home = json.dumps([{"op": HOME, "args": {"photo": photo}}])
        add = json.dumps([{"op": "product.add", "args": {"photo": photo, "name": "Quince"}}])
        self.insert("HOM1", home)
        self.assertEqual(self.photo_line(self.status()), ["A photo is waiting for details from you."])
        self.insert("HOM2", add)
        self.assertEqual(self.photo_line(self.status()), ["Some photos are waiting for details from you."])
        before = self.drafts()
        for code, ops in {"NUL1": json.dumps([{"op": HOME, "args": {"photo": None}}]), "EMP1": "[]",
                          "NOP1": json.dumps([{"op": HOME, "args": {}}]), "BAD1": "{not json",
                          "KND1": json.dumps([{"op": HOME, "args": {"photo": 7}}]), "ARG1": json.dumps([{"op": HOME, "args": "x"}]),
                          "STR1": json.dumps([{"op": HOME, "args": {"photo": ""}}]),
                          "MIX1": json.dumps([{"op": HOME, "args": {"photo": photo}}, {"op": "product.edit", "args": {}}])}.items():
            self.insert(code, ops)
        self.assertEqual(self.photo_line(self.status()), ["Some photos are waiting for details from you."])  # still two rows
        self.conv.db.execute("DELETE FROM drafts WHERE code = 'HOM2'")
        self.assertEqual(self.photo_line(self.status()), ["A photo is waiting for details from you."])
        self.conv.db.execute("UPDATE drafts SET state = 'proposed' WHERE code = 'HOM1'")  # proposed rows are not waiting for details
        self.assertEqual(self.photo_line(self.status()), [])
        self.conv.db.execute("UPDATE drafts SET state = 'needs-details', expires_at = ? WHERE code = 'HOM1'", ((T0 - timedelta(minutes=1)).isoformat(),))
        self.assertEqual(self.photo_line(self.status()), [])  # expired
        self.conv.db.execute("UPDATE drafts SET expires_at = ? WHERE code = 'HOM1'", ((T0 + timedelta(hours=1)).isoformat(),))
        rows = self.drafts()
        self.assertEqual(self.say("pause changes"), "pause")  # a paused status still counts
        self.replies()
        self.assertEqual(self.photo_line(self.status()), ["A photo is waiting for details from you."])
        self.inbox([("pending", 1)])
        lines = self.status()
        self.assertEqual((self.photo_line(lines), len(self.drafts()) >= len(before)), (["A photo is waiting for details from you."], True))
        self.assertIn("A photo is still coming in.", lines)  # downloading counts alongside
        self.assertEqual([d for d in self.drafts() if d["code"] in {r["code"] for r in rows}], rows)  # status wrote nothing


class PromptTests(unittest.TestCase):
    def test_prompt_offers_one_of_three_destinations(self):
        rule = ("- When a pending draft is a photo question (product.set_photo), answer with exactly one of product.set_photo (a "
                "listed product), product.add (a new product) or store.set_home_image (the home page), and set revises to its "
                "code. A new product, new item or new thing means product.add: read its name and details from the owner's earlier texts too, and ask only for a value still missing. Take imageAlt from the owner's words about the photo; never invent it.\n")
        self.assertEqual(FIXTURE.read_text("utf-8").count(rule), 1)
        self.assertEqual(build(TEST_REGISTRY, tiny_content()), FIXTURE.read_text("utf-8"))
        self.assertNotIn("never both", FIXTURE.read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()

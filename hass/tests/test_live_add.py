"""HASS-LIVE-ADD-1 (G, 2026-11-09): a NEW product, with its brand and maker, may go live from chat, under these rules and no wider.

1. product.add is live and may carry brand, displayBrand and producerKey on the NEW product (only inside this op), but only words
   the owner said in this request (live_policy.unsaid; the conversation drafts nothing otherwise); every sentence gate, the
   10-record limit and undo are unchanged.
2. maker.add is live only so that a new product can name the new maker: its name and place (town the owner said); its link
   (url) stays protected, and a maker on its own is refused.
3. product.set_photo stays private; product.edit may never change brand, displayBrand or producerKey; a maker's place or link
   on an existing maker, hiding and restoring makers stay private.

Real production ops (hass.ops.load_registry), real live_policy, a throwaway writer repo (PhotoRepo) and, for the end-to-end
test, the real release engine (LiveEditor) on a disposable local bare Git remote with the real site build. Nothing here
touches the live site, host.json, real state or the network. Run: python3 -B -m unittest hass.tests.test_live_add -v
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import conversation as conv, editor, media, live_policy as policy, publish_live as p, voice
from hass.content_model import REPO_ROOT
from hass.fixture_chat import FixtureAdapter
from hass.ops import load_registry
from hass.tests import test_publish_live as pl
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS
from hass.tests.test_catalog_ops import CatalogRepo
from hass.tests.test_editor import git
from hass.tests.test_live_policy import edit
from hass.tests.test_set_photo import FIXTURES, PhotoRepo, _settings

NOW = datetime(2026, 11, 8, 18, 0, tzinfo=timezone.utc)
SITE = "fixture.example.invalid"
PID = "photo-product-001"
KEY = "test-orchard"
PLACE = "Paso Robles, California"
ALT = "A jar of quince jam on a plain counter"
SAID = "New quince jam from Test Orchard in Paso Robles, goes on the pantry shelf"
DENIED = "New quince jam, not made by the people at Test Orchard in Paso Robles."
CORRECTED = "New quince jam from Test Orchard in Paso Robles. Correction: it is not from Test Orchard."
DENIED_AFTER = "New quince jam from Test Orchard in Paso Robles. Test Orchard is not the maker."
DENIED_NOAPOS = "New quince jam from Test Orchard in Paso Robles. Test Orchard isnt the maker."
DENIED_MODIFIED = "New quince jam from Test Orchard in Paso Robles. Test Orchard is definitely not the maker."


def op(opname, /, **args): return {"op": opname, "args": args}


def maker_op(**more):
    return op("maker.add", key=KEY, name="Test Orchard", place=PLACE, story="Test Orchard is based in Paso Robles, California.", **more)


def product_op(sha, **more):
    args = dict(name="Quince jam", brand="Test Orchard", category="pantry", description="Sweet and tart on warm toast.",
                producerKey=KEY, photo=sha, imageAlt=ALT)
    return op("product.add", **{**args, **more})


class FullRepo(CatalogRepo):
    """The writer repo of the release test: a full, isolated copy of the real source (as test_real_archive_build_checks builds
    it, with real picture files and no links), so the production site build can run on it. Plus a private photo store."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="hass-live-add-")
        tmp = Path(self._tmp.name)
        self.main, self.wt, self.state, self.media = tmp / "main", tmp / "writer", tmp / "state", tmp / "media"
        for name in ("hass", "storefront-mockup", "reports/hermes-handoff"):
            shutil.copytree(REPO_ROOT / name, self.main / name, ignore=shutil.ignore_patterns("__pycache__", "node_modules"))
        git(tmp, "init", "-q", "-b", "main", str(self.main))
        for key, value in (("maintenance.auto", "false"), ("gc.auto", "0"), ("user.name", "hass-test"),
                           ("user.email", "hass-test@example.invalid")):
            git(self.main, "config", key, value)
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", "base")
        git(self.main, "worktree", "add", "-q", "-b", "hass/content", str(self.wt))
        self.state.mkdir(mode=0o700)
        assert editor.init(str(self.state), str(self.wt))["result"] == "ok"
        _settings(self, mediaRoot=str(self.media))

    def store(self, data):
        return media.store_original(self.media, data, received_at="2026-11-02T18:00:00+00:00", source="fixture")["sha256"]


class LiveAddBase(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        self.sha = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())
        self.registry = load_registry()

    def draft(self, *ops):
        out = editor.prepare({"ops": list(ops)}, state=str(self.repo.state), registry=self.registry, now=NOW)
        self.assertEqual(out["result"], "ok", out)
        return out["draft"]

    def reasons(self, *ops): return policy.check(self.draft(*ops))

    def new_product(self, **more): return [maker_op(), product_op(self.sha, **more)]

    def maker_key(self):
        return next(iter(json.loads((self.repo.wt / "hass/content/makers.json").read_text())["makers"]))


class TheRulesOnRealDrafts(LiveAddBase):
    def test_1_a_new_product_with_brand_display_brand_and_maker_goes_live(self):
        self.assertEqual(self.reasons(*self.new_product()), [])
        self.assertEqual(self.reasons(*self.new_product(displayBrand="Test Orchard")), [])
        draft = self.draft(*self.new_product())
        fields = {r["collection"]: r["after"] for r in draft["records"]}
        self.assertEqual((fields["products"]["brand"], fields["products"]["producerKey"], fields["makers"]["place"]), ("Test Orchard", KEY, PLACE))
        # a new product on an existing maker, and one whose maker nobody knows (the house words) are live too
        maker = next(iter(json.loads((self.repo.wt / "hass/content/makers.json").read_text())["makers"].items()))
        self.assertEqual(self.reasons(product_op(self.sha, producerKey=maker[0], brand=maker[1]["name"])), [])
        unknown = {k: v for k, v in product_op(self.sha)["args"].items() if k != "producerKey"} | {"brand": "Producer not identified"}
        self.assertEqual(self.reasons(op("product.add", **unknown)), [])

    def test_1_the_image_argument_is_not_live(self):
        args = {k: v for k, v in product_op(self.sha)["args"].items() if k not in ("photo", "imageAlt", "producerKey")}
        args["image"] = "assets/products/photo-product-001.webp"
        self.assertEqual(self.reasons(op("product.add", **args)), ["not live: product.add.image"])

    def test_1_a_sentence_gate_still_stops_every_text_field_of_a_new_product(self):
        for label, more in {
            "origin in the description": dict(description="Grown in Paso Robles on the family farm."),
            "organic in the description": dict(description="Organic quince jam."),
            "health claim": dict(description="Good for your immunity."),
            "award": dict(description="Award-winning quince jam."),
            "trail fact": dict(description="Dogs allowed at the tasting."),
            "price words": dict(description="A fair price for a jar."),
            "dollars": dict(description="Six dollars a jar."),
            "contact": dict(description="Call 805 555 0123 to order."),
            "organic in the brand": dict(brand="Organic Test Orchard"),
            "an award in the name": dict(name="Award-winning quince jam"),
            "a price in the picture words": dict(imageAlt="Quince jam, 6 dollars"),
        }.items():
            with self.subTest(label=label):
                self.assertTrue(self.reasons(*self.new_product(**more)), label)
        self.assertIn("protected sentences: origin/organic", self.reasons(*self.new_product(description="Grown in Paso Robles on the family farm.")))
        self.assertIn("protected sentences: prices", self.reasons(*self.new_product(description="A fair price for a jar.")))

    def test_1_a_claim_cannot_hide_as_a_new_product_or_maker_name(self):
        """RETURN t_439e2607, finding 3: the same wording that is refused in a description is refused as a name."""
        claim = "Won first place at the county fair"
        for label, ops in {
            "product name": self.new_product(name=claim),
            "brand": self.new_product(brand=claim),
            "display brand": self.new_product(displayBrand=claim),
            "maker name": [op("maker.add", key=KEY, name=claim, place=PLACE, story="Based in Paso Robles, California."), product_op(self.sha)],
        }.items():
            with self.subTest(label=label):
                self.assertIn("protected sentences: health/awards/endorsements", self.reasons(*ops))
        with self.subTest(label="the same words in a description"):
            self.assertIn("protected sentences: health/awards/endorsements", self.reasons(*self.new_product(description=claim + ".")))
        with self.subTest(label="a plain farm-noun name still goes live"):
            self.assertEqual(self.reasons(*self.new_product()), [])

    def test_1_the_maker_text_goes_through_the_same_sentence_gates(self):
        for story in ("Test Orchard is a certified organic farm.", "Test Orchard has won an award."):
            with self.subTest(story=story):
                self.assertTrue(self.reasons(op("maker.add", key=KEY, name="Test Orchard", place=PLACE, story=story), product_op(self.sha)))

    def test_1_the_record_limit_stays(self):
        draft = self.draft(*self.new_product())
        self.assertLessEqual(len(draft["records"]), policy.MAX_RECORDS)
        draft["records"] = (draft["records"] * 6)[:policy.MAX_RECORDS]
        self.assertEqual(policy.check(draft), [])
        draft["records"] = (draft["records"] * 2)[:policy.MAX_RECORDS + 1]
        self.assertIn("more than 10 records", policy.check(draft))

    def test_1_sign_up_off_rules_stay(self):
        hike = op("hike.create", title="Walk", date="2026-11-14", time="08:00", meetingPoint="Trailhead", rsvpEnabled=True, capacity=8)
        self.assertIn("sign-up is on", self.reasons(*self.new_product(), hike))
        quiet = op("hike.create", title="Walk", date="2026-11-14", time="08:00", meetingPoint="Trailhead", rsvpEnabled=False)
        self.assertEqual(self.reasons(*self.new_product(), quiet), [])

    def test_1_undo_meets_the_same_content_gates(self):
        # HASS-SEC-2 (M1): an undo no longer always passes. The undo of a new product and maker (the product hidden, the maker
        # hidden, as history.revert writes them) passes; one that would change a protected field or sentence is refused.
        self.assertEqual(policy.check(edit("old", "new", op="history.revert")), [])
        product = {"brand": "Test Orchard", "producerKey": KEY, "status": "active"}
        maker = {"name": "Test Orchard", "place": PLACE, "story": "Test Orchard is based in Paso Robles, California."}
        hidden = {"ops": [{"op": "history.revert", "args": {}}], "records": [
            {"collection": "products", "key": "x", "before": product, "after": {**product, "status": "hidden"}},
            {"collection": "makers", "key": KEY, "before": maker, "after": {**maker, "hidden": True}}]}
        self.assertEqual(policy.check(hidden), [])
        undo = {"ops": [{"op": "history.revert", "args": {}}], "records": [
            {"collection": "products", "key": "x", "before": {"brand": "Test Orchard", "producerKey": KEY}, "after": None},
            {"collection": "makers", "key": KEY, "before": {"place": PLACE, "url": "https://example.com"}, "after": None}]}
        self.assertIn("protected field: makers.url", policy.check(undo))

    def test_2_the_maker_link_stays_protected(self):
        reasons = self.reasons(maker_op(url="https://www.example.com/orchard"), product_op(self.sha))
        self.assertIn("not live: maker.add.url", reasons)
        self.assertIn("protected field: makers.url", reasons)
        self.assertIn("I can't put this on the website from chat", policy.refusal(reasons))

    def test_2_a_maker_on_its_own_is_refused_in_plain_words(self):
        reasons = self.reasons(maker_op())
        self.assertEqual(reasons, [f"not live: {policy.LONE_MAKER}"])
        text = policy.refusal(reasons)
        self.assertIn("a maker on its own, without a new product", text)
        self.assertEqual(voice.check(text), [], text)
        # a product that names some OTHER maker does not make this maker live either
        self.assertEqual(self.reasons(maker_op(), product_op(self.sha, producerKey=next(iter(json.loads(
            (self.repo.wt / "hass/content/makers.json").read_text())["makers"])), brand="Someone")), reasons)

    def test_2_an_existing_makers_place_and_link_and_hiding_stay_private(self):
        key = next(iter(json.loads((self.repo.wt / "hass/content/makers.json").read_text())["makers"]))
        for field, value in (("place", "Somewhere, California"), ("url", "https://example.com/about")):
            with self.subTest(field=field):
                reasons = self.reasons(op("maker.edit", key=key, **{field: value}))
                self.assertIn(f"not live: maker.edit.{field}", reasons)
        for name, args in (("maker.hide", {"key": key, "withProducts": True}), ("maker.restore", {"key": key})):
            with self.subTest(op=name):
                self.assertIn(name, policy.PRIVATE)
                self.assertNotIn(name, policy.LIVE)
        self.assertEqual(self.reasons(op("maker.hide", key=key, withProducts=True)), ["not live: maker.hide"])
        # the field gate itself, on records: place on an EXISTING maker is protected even beside a live maker.add
        draft = {"ops": [op("maker.add", key="a", name="A", place="B", story="C"), product_op("0" * 64, producerKey="a")], "records": [
            {"collection": "makers", "key": "old", "before": {"place": "One"}, "after": {"place": "Two"}}]}
        self.assertIn("protected field: makers.place", policy.check(draft))

    def test_3_set_photo_stays_private_and_a_new_product_needs_no_second_picture_request(self):
        self.assertIn("product.set_photo", policy.PRIVATE)
        self.assertNotIn("product.set_photo", policy.LIVE)
        self.assertEqual(policy.PRIVATE["product.set_photo"], "changes a picture")
        self.assertEqual(self.reasons(op("product.set_photo", id=PID, photo=self.sha, imageAlt=ALT)), ["not live: product.set_photo"])
        self.assertIn("it changes a picture", policy._plain_reason("not live: product.set_photo"))

    def test_4_brand_display_brand_and_producer_of_an_existing_product_stay_refused(self):
        for field, value in (("brand", "Someone Else"), ("displayBrand", "Someone Else"), ("producerKey", self.maker_key())):
            with self.subTest(field=field):
                reasons = self.reasons(op("product.edit", id=PID, **{field: value}))
                self.assertIn(f"not live: product.edit.{field}", reasons)
                self.assertIn(f"protected field: products.{field}", reasons)
        for field in ("brand", "displayBrand", "producerKey"):
            with self.subTest(record=field):  # the field gate alone, even if the op table were widened or an add sits in the same draft
                draft = {"ops": [product_op("0" * 64)], "records": [
                    {"collection": "products", "key": PID, "before": {field: "old"}, "after": {field: "new"}}]}
                self.assertIn(f"protected field: products.{field}", policy.check(draft))
                gone = {"ops": [product_op("0" * 64)], "records": [{"collection": "products", "key": PID, "before": {field: "old"}, "after": None}]}
                self.assertIn(f"protected field: products.{field}", policy.check(gone))
        with mock.patch.dict(policy.LIVE, {"product.edit": {"id", "brand"}}):  # a widened table must still not pass the field gate
            self.assertIn("protected field: products.brand", self.reasons(op("product.edit", id=PID, brand="Someone Else")))

    def test_4_the_brand_fields_pass_only_when_product_add_is_on_the_live_list(self):
        draft = self.draft(*self.new_product())
        self.assertEqual(policy.check(draft), [])
        with mock.patch.dict(policy.LIVE, clear=False):
            del policy.LIVE["product.add"]
            reasons = policy.check(draft)
        self.assertIn("protected field: products.brand", reasons)
        self.assertIn("not live: product.add", reasons)
        with mock.patch.dict(policy.LIVE, clear=False):
            del policy.LIVE["maker.add"]
            self.assertIn("protected field: makers.place", policy.check(draft))

    def test_the_new_product_op_text_of_every_private_operation_is_unchanged(self):
        for name in ("product.set_photo", "maker.hide", "maker.restore", "store.set_phone", "store.set_hours", "route.add", "hike.samples"):
            with self.subTest(op=name):
                self.assertIn(name, policy.PRIVATE)
                self.assertIn("I've saved it for Graham", policy.refusal([f"not live: {name}"]))
        for name in ("product.add", "maker.add"):
            self.assertNotIn(name, policy.PRIVATE)


class TheBrandMustBeInHisWords(LiveAddBase):
    def test_unsaid_finds_a_brand_a_maker_and_a_town_he_did_not_say(self):
        draft = self.draft(*self.new_product(displayBrand="Test Orchard Farm"))
        self.assertEqual(policy.unsaid(draft, SAID), ["Test Orchard Farm"])
        self.assertEqual(policy.unsaid(self.draft(*self.new_product()), SAID), [])
        self.assertEqual(policy.unsaid(self.draft(*self.new_product()), "New quince jam on the pantry shelf"),
                         ["Test Orchard", "Paso Robles"])
        self.assertEqual(policy.unsaid(self.draft(*self.new_product()), "New quince jam from Test Orchard"), ["Paso Robles"])

    def test_a_denied_mention_does_not_count_and_a_new_word_next_to_it_does_not_either(self):
        draft = self.draft(*self.new_product())
        self.assertEqual(policy.unsaid(draft, "Not from Test Orchard in Paso Robles"), ["Test Orchard", "Paso Robles"])  # the denial runs to the end of its clause
        self.assertEqual(policy.unsaid(draft, "Test Orchards in Paso Robles"), ["Test Orchard"])  # whole words only
        self.assertEqual(policy.unsaid(draft, "TEST  ORCHARD, in paso robles."), [])  # case and spacing are ignored

    def test_the_owner_denying_the_brand_or_town_is_not_the_owner_saying_it(self):
        draft = self.draft(*self.new_product())
        for text in ("New quince jam, not made by the people at Test Orchard in Paso Robles.",  # the negator is far from the name
                     "New quince jam from Test Orchard in Paso Robles. Correction: it is not from Test Orchard.",  # a later correction
                     "New quince jam from Test Orchard in Paso Robles\nit isn't made by Test Orchard, sorry",
                     "from Test Orchard in Paso Robles. Wrong, ignore Test Orchard",
                     "New quince jam from Test Orchard, never made in Paso Robles",
                     DENIED_AFTER,  # the denial comes after the name
                     "New quince jam from Test Orchard in Paso Robles. Test Orchard didn't make it",
                     "New quince jam from Test Orchard in Paso Robles. Test Orchard was wrong, sorry",
                     "New quince jam from Test Orchard in Paso Robles\nTest Orchard isn't the maker",
                     DENIED_NOAPOS, DENIED_MODIFIED,  # an unpunctuated negator, and a modifier before the negator
                     "New quince jam from Test Orchard in Paso Robles. Test Orchard has really never made it",
                     "New quince jam from Test Orchard in Paso Robles. Test Orchard is the wrong maker",
                     "New quince jam from Test Orchard in Paso Robles. Test Orchard wasnt the maker",
                     "New quince jam from Test Orchard in Paso Robles. Test Orchard is no longer the maker"):
            with self.subTest(text=text):
                self.assertNotEqual(policy.unsaid(draft, text), [], text)
        self.assertEqual(policy.unsaid(draft, DENIED_AFTER), ["Test Orchard"])
        self.assertEqual(policy.unsaid(draft, DENIED_NOAPOS), ["Test Orchard"])
        self.assertEqual(policy.unsaid(draft, DENIED_MODIFIED), ["Test Orchard"])
        self.assertEqual(policy.unsaid(draft, "New quince jam, not made by the people at Test Orchard in Paso Robles."),
                         ["Test Orchard", "Paso Robles"])  # the denial runs to the end of its clause, so the town is asked too

    def test_a_later_plain_mention_and_a_denial_of_something_else_still_count(self):
        draft = self.draft(*self.new_product())
        for text in ("not from Test Orchard\nsorry, it is from Test Orchard in Paso Robles",  # the owner corrects himself back
                     "Not Acme, it is from Test Orchard in Paso Robles",
                     "No sugar added, from Test Orchard in Paso Robles",
                     "not an old recipe but from Test Orchard in Paso Robles",
                     "New quince jam. Test Orchard is in Paso Robles, it is made by Test Orchard",
                     "New quince jam. Test Orchard is definitely the maker, in Paso Robles",
                     "New quince jam. Test Orchard is the maker in Paso Robles, not in Cambria"):
            with self.subTest(text=text):
                self.assertEqual(policy.unsaid(draft, text), [], text)

    def test_the_texts_of_one_request_are_not_run_together(self):
        draft = self.draft(*self.new_product())
        self.assertEqual(policy.unsaid(draft, "from Test Orchard in Paso Robles\nnot from Test Orchard"), ["Test Orchard"])
        self.assertEqual(policy.unsaid(draft, "not\nfrom Test Orchard in Paso Robles"), [])  # a negator ends with its own text

    def test_the_house_words_for_an_unknown_maker_need_no_owner_words_and_nothing_else_is_asked(self):
        args = {k: v for k, v in product_op(self.sha)["args"].items() if k != "producerKey"} | {"brand": "Producer not identified"}
        draft = self.draft(op("product.add", **args))
        self.assertEqual(policy.unsaid(draft, "new jam, dont know who makes it"), [])
        self.assertEqual(policy.unsaid({"ops": [op("product.hide", id=PID)], "records": []}, ""), [])
        self.assertEqual(policy.unsaid(None, "x"), [])  # unreadable input never raises (check() is what refuses it)

    def test_the_question_is_plain(self):
        text = policy.unsaid_question(["Test Orchard", "Paso Robles", "A", "B"])
        self.assertEqual(voice.check(text), [], text)
        self.assertIn("and a few more", text)
        self.assertEqual(text.count("?"), 0)


class InChat(LiveAddBase):
    """The conversation with the real op registry in live mode: nothing is drafted for a brand he did not say."""

    def setUp(self):
        super().setUp()
        _settings(self.repo, **SETTINGS, liveSite=SITE, approvalNeedsCode=True, mediaRoot=str(self.repo.media))
        self.now, self.n, self.out = NOW, 0, FixtureAdapter()
        ops = [maker_op(), product_op(self.sha)]
        invented = [maker_op(), product_op(self.sha, brand="Acme Preserves", producerKey=KEY)]
        near = [op("maker.add", key=KEY, name="Test Orchard Farm", place=PLACE, story="Test Orchard Farm is based in Paso Robles, California."),
                product_op(self.sha, brand="Test Orchard Farm")]
        self.interp = conv.FixtureInterpreter({
            DENIED: {"ops": ops, "revises": None}, CORRECTED: {"ops": ops, "revises": None}, DENIED_AFTER: {"ops": ops, "revises": None},
            DENIED_NOAPOS: {"ops": ops, "revises": None}, DENIED_MODIFIED: {"ops": ops, "revises": None},
            SAID: {"ops": ops, "revises": None},
            "New quince jam from Test Orchard, goes on the pantry shelf": {"ops": ops, "revises": None},
            "new quince jam please": {"ops": invented, "revises": None},
            "New quince jam from Test Orchard in Paso Robles": {"ops": near, "revises": None},
            "change the brand to Test Orchard": {"ops": [op("product.edit", id=PID, brand="Test Orchard")], "revises": None}})
        self.conv = conv.Conversation(str(self.repo.state), conv.Editor(self.repo.state), self.interp, lambda: self.now)
        self.addCleanup(lambda: self.conv.db.close())

    def say(self, text):
        self.n += 1
        return self.conv.handle(conv.Inbound(f"live-add-{self.n}", CHAT, OWNER, text, False, "new", self.now.isoformat()))

    def replies(self):
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return [row["text"] for row in self.out.sent[before:]]

    def drafts(self): return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts")]

    def test_a_brand_he_said_is_offered_for_the_website(self):
        self.assertEqual(self.say(SAID), "proposed")
        [reply] = self.replies()
        self.assertIn("to put it on the website", reply)
        self.assertNotIn("I can't put this on the website", reply)
        self.assertEqual(len(self.drafts()), 1)

    def test_a_brand_or_town_he_did_not_say_is_asked_and_nothing_is_drafted(self):
        for text in ("new quince jam please", "New quince jam from Test Orchard, goes on the pantry shelf", "New quince jam from Test Orchard in Paso Robles", DENIED, CORRECTED, DENIED_AFTER,
                     DENIED_NOAPOS, DENIED_MODIFIED):
            with self.subTest(text=text):
                self.assertEqual(self.say(text), "claim-question")
                [reply] = self.replies()
                self.assertIn("You didn't say", reply)
                self.assertEqual(voice.check(reply), [], reply)
                self.assertEqual(self.drafts(), [])

    def test_changing_an_existing_products_brand_is_refused_and_saved_for_graham(self):
        self.assertEqual(self.say("change the brand to Test Orchard"), "proposed")
        [reply] = self.replies()
        self.assertIn("I can't put this on the website from chat", reply)
        self.assertIn("I've saved it for Graham", reply)
        self.assertNotIn("Reply yes", reply)
        code = self.drafts()[0]["code"]
        self.assertEqual(self.say(f"yes {code}"), "no-target")  # a yes cannot get around it


class LiveAddEndToEnd(pl.ReleaseCase):
    """A new product with a brand and a new maker, through the real op registry, the real live policy, the real release engine
    and the real site build, on a disposable local bare remote; then `undo` takes it off again."""

    def setUp(self):
        patcher = mock.patch.object(pl, "WriterRepo", FullRepo)
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()
        cfg = editor._read(self.repo.state / "config.json")
        cfg["settings"] = {**cfg["settings"], "mediaRoot": str(self.repo.media)}
        editor._write_json(self.repo.state / "config.json", cfg)
        self.sha = self.repo.store((FIXTURES / "pixel.jpg").read_bytes())
        self.live = self.open()

    def fixture_build(self, commit, today, cid, label, checks=False):  # the real build of the real writer tree
        return p.LiveEditor.build(self.live, commit, today, cid, label, checks=checks)

    def open(self):
        live = super().open()
        live.registry = load_registry()
        live.build = self.fixture_build
        return live

    def prepare(self, *ops):
        out = editor.prepare({"ops": list(ops)}, state=str(self.repo.state), registry=self.live.registry)
        self.assertEqual(out["result"], "ok", out)
        return out["draft"]

    def site_file(self, rel):
        return subprocess.run(["git", "-C", str(self.bare), "show", f"main:{rel}"], capture_output=True, check=True).stdout

    def site_files(self):
        return set(git(self.bare, "ls-tree", "-r", "--name-only", "main").splitlines())

    def test_a_new_product_with_a_brand_goes_live_appears_in_the_site_and_undo_removes_it_exactly(self):
        before_files = self.site_files()
        before = {rel: self.site_file(rel) for rel in before_files}
        self.assertNotIn(b"Quince jam", before["catalog-products.js"])
        draft = self.prepare(maker_op(), product_op(self.sha, displayBrand="Test Orchard"))
        self.assertEqual(policy.check(draft), [])
        self.assertEqual(self.apply(draft)["result"], "applied")
        self.settle()
        self.assertEqual(self.entry()["state"], "live")
        # it is in the built site (the catalog the page reads, the producers list and the picture), with the brand and the maker's place
        catalog = self.site_file("catalog-products.js")
        self.assertIn(b"Quince jam", catalog)
        self.assertIn(b"Test Orchard", catalog)
        self.assertIn(b"Paso Robles", self.site_file("producers.js") + catalog)
        picture = f"assets/products/photo-{self.sha[:16]}.jpg"
        self.assertIn(picture, self.site_files())
        self.assertEqual(git(self.site, "status", "--porcelain"), "")
        self.assertEqual(git(self.bare, "rev-parse", "main"), git(self.site, "rev-parse", "HEAD"))
        # undo
        self.now += timedelta(seconds=61)
        undo = self.prepare(op("history.revert", changeId=draft["change_id"]))
        self.assertEqual(policy.check(undo), [])
        self.assertEqual(self.apply(undo)["result"], "applied")
        self.settle()
        self.assertEqual(self.entry()["state"], "live")
        self.assertNotIn(b"Quince jam", self.site_file("catalog-products.js"))
        self.assertEqual(git(self.site, "status", "--porcelain"), "")
        self.assertEqual(git(self.bare, "rev-parse", "main"), git(self.site, "rev-parse", "HEAD"))
        after = {rel: self.site_file(rel) for rel in self.site_files()}
        self.assertEqual(before, after)  # exactly what the website was before: every file, the picture included

    def test_the_release_engine_refuses_what_stays_private(self):
        draft = self.prepare(op("product.edit", id=PID, brand="Someone Else"))
        self.assert_refused_unchanged(draft)
        draft = self.prepare(maker_op(url="https://www.example.com/orchard"), product_op(self.sha))
        self.assert_refused_unchanged(draft)
        draft = self.prepare(maker_op())
        self.assert_refused_unchanged(draft)


for _name in dir(pl.ReleaseCase):  # the release engine's own tests run in test_publish_live; only this class's tests run here
    if _name.startswith("test") and _name not in LiveAddEndToEnd.__dict__:
        setattr(LiveAddEndToEnd, _name, None)


if __name__ == "__main__":
    unittest.main()

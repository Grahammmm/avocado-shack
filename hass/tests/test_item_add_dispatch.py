"""SKILLS-ITEMADD-1: item.add through the REAL skill dispatcher and Conversation (not the test kit's simulation).

The test kit plays a recorded model reply and asks the skill's plan directly; this file runs the production path instead:
Conversation -> Dispatcher (validate, defaults, one question per missing slot, the skill's ``question`` / ``notes`` hooks, a plan
refusal kept as an open request) -> editor.prepare -> the proposal the owner reads before he says yes. Photos arrive as real
attachments and are stored by the conversation (media.store_original); the model is the only stand-in (it returns what a correct
model returns for each text). Nothing is written before the owner's own ``yes <code>``.

The dispatcher hooks (``question()``, a plan error's own sentence, ``notes()``, ``ctx.media_root`` / ``ctx.house_render``) are
SKILLS-FW-3d (a stacked PR on FW-3, PR 526). Without them this file is skipped, because the dispatcher then cannot deliver them.
Run: python3 -B -m unittest hass.tests.test_item_add_dispatch -v
"""
import json
import sys
import types
import unittest
from datetime import timedelta
from unittest import mock

from hass import conversation, voice
from hass.content_model import REPO_ROOT
from hass.skills import item_add as ia
from hass.skills import testkit

try:
    from hass.skills import dispatch
    HOOKS = hasattr(dispatch, "skill_hook")
except ImportError:  # the dispatcher (SKILLS-FW-3) is not on this branch yet
    dispatch, HOOKS = None, False

SYN = "reports/hass/newitem-1/synthetic/"
JAR, BAG, TILTED = SYN + "jar-white-sheet.jpg", SYN + "bag-red-cloth.jpg", SYN + "bottle-grey-wall-tilted.jpg"


class FakePhotos:
    """The photo source: ``fetch(provider_id, count)`` -> the bytes of the file this message carries."""

    def __init__(self):
        self.files = {}

    def fetch(self, provider_id, count):
        return [(REPO_ROOT / self.files[provider_id]).read_bytes()] * count


class Chat:
    """One owner conversation on the throwaway repo with the real dispatcher, item.add the only skill."""

    def __init__(self, photos, setup=None):
        self.kit = testkit.Scratch({}, {"item.add": ia.ITEM_ADD}, photos=list(photos), setup=setup)
        self.kit.conv.db.close()  # the kit's own Conversation is not used; this one has the dispatcher
        cfg = json.loads((self.kit.repo.state / "config.json").read_text("utf-8"))
        from hass import editor
        editor._write_json(self.kit.repo.state / "config.json", {**cfg, "settings": {**cfg["settings"], "skills": {"mode": "both"}}})
        self.asked, self.photos, self.mapping = [], FakePhotos(), {}
        self.now, self.n, self.out = testkit.START, 0, self.kit.out
        self.interp = _Interp(self.mapping, self.asked)
        self.router = types.ModuleType("hass.skills.router")
        self.router.candidates = lambda text, hints=None, open_request=None, attachment=None, skills=(): [("item.add", 10.0)]
        self._patch = mock.patch.dict(sys.modules, {"hass.skills.router": self.router})
        self._patch.start()
        self.registry = conversation.dispatch_mod.Registry(skills={"item.add": ia.ITEM_ADD}) if hasattr(conversation, "dispatch_mod") \
            and hasattr(conversation.dispatch_mod, "Registry") else __import__("hass.skills.model", fromlist=["Registry"]).Registry(skills={"item.add": ia.ITEM_ADD})
        self.conv = conversation.Conversation(str(self.kit.repo.state), self.kit.editor, self.interp, lambda: self.now,
                                              self.kit.previewer, photos=self.photos, skills=self.registry)

    def close(self):
        self._patch.stop()
        self.conv.db.close()
        self.kit.close()  # the kit's own Conversation db (already closed), its repo, media root and shop day

    def script(self, text, reply):
        self.interp.mapping[text] = reply

    def say(self, text, photo=None):
        """Send one message (with a photo when ``photo`` is a repo-relative file); returns (disposition, [the replies])."""
        self.n += 1
        self.now += timedelta(minutes=1)
        pid = f"it-{self.n}"
        if photo:
            self.photos.files[pid] = photo
        msg = conversation.Inbound(pid, testkit.CHAT, testkit.OWNER, text, False, "new", self.now.isoformat(), 1 if photo else 0)
        disposition = self.conv.handle(msg)
        before = len(self.out.sent)
        self.conv.flush(self.out)
        return disposition, [row["text"] for row in self.out.sent[before:]]

    def live(self):
        return self.conv.requests.get(testkit.CHAT, self.now)

    def drafts(self):
        return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def commits(self):
        return int(testkit._git(self.kit.wt, "rev-list", "--count", "HEAD")) - self.base_commits


class _Interp(conversation.FixtureInterpreter):
    def __init__(self, mapping, asked):
        super().__init__(mapping)
        self.asked = asked

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        self.asked.append((text, recent))
        return super().interpret(text, pending)


def reply(**slots):
    return {"skill": "item.add", "slots": slots, "revises": None}


@unittest.skipUnless(HOOKS, "needs the SKILLS-FW-3d dispatcher hooks (stacked on SKILLS-FW-3, PR 526)")
class RealDispatcher(unittest.TestCase):
    def open(self, *photos, setup=None):
        chat = Chat(photos, setup)
        chat.base_commits = int(testkit._git(chat.kit.wt, "rev-list", "--count", "HEAD"))
        self.addCleanup(chat.close)
        return chat


    def say_all(self, chat, steps, photo=None):
        """Play (text, scripted model reply or None) steps; the photo goes with the first message. Returns each reply set."""
        outs = []
        for i, (text, rep) in enumerate(steps):
            if rep is not None:
                chat.script(text, rep)
            outs.append(chat.say(text, photo if i == 0 else None))
        return outs

    def test_a_missing_farm_is_asked_with_the_saved_one_offered_and_a_short_answer_fills_it(self):
        chat = self.open(BAG)
        (d1, r1), (d2, r2), (d3, r3) = self.say_all(chat, [
            ("got some fresh tomatoes in today", reply(name="Tomatoes", form="fresh")),
            ("Etto", reply(maker="Etto")),
            ("in stock", reply(availability="yes")),
        ], BAG)
        self.assertEqual(d1, "question")
        self.assertEqual(len(r1), 1)
        self.assertIn("Who grew these tomatoes?", r1[0])
        self.assertIn("Last time it was", r1[0])  # the saved farm, offered by the skill's own question(), not the static slot wording
        live = chat.live()
        self.assertEqual((live["skill"], live["state"]), ("item.add", "drafted"))
        self.assertEqual(d2, "question")
        self.assertEqual(r2, ["Is it in stock right now?"])  # one short question at a time
        self.assertEqual(d3, "proposed")
        text = "\n".join(r3)
        self.assertIn("A new product: Tomatoes", text)
        self.assertIn("Etto is already on the site", text)
        self.assertEqual(chat.commits(), 0)  # nothing is written before his own yes
        self.assertEqual([r["kind"] for r in chat.kit.previewer.requests][-1], "product")

    def test_the_shelf_check_is_said_on_its_own_line_before_the_yes(self):
        chat = self.open(JAR)
        outs = self.say_all(chat, [
            ("new honey, in stock", reply(name="Honey", availability="yes")),
            ("Bee Happy Farm", reply(maker="Bee Happy Farm")),
            ("Atascadero, California", reply(place="Atascadero, California")),
            ("skip", reply()),  # HASS-LIVE-ADD-2: a new maker is asked for a story; skip keeps only the town line
        ], JAR)
        self.assertEqual([o[0] for o in outs], ["question", "question", "question", "proposed"])
        self.assertEqual(outs[1][1], ["Where is Bee Happy Farm based (town and state)?"])
        lines = [ln.strip() for ln in "\n".join(outs[3][1]).split("\n")]
        self.assertIn("This also records today as the day you checked the shelves.", lines)  # D2, its own line
        self.assertIn("Bee Happy Farm is new on the site, so I'm adding them too.", lines)
        self.assertTrue(any("Bee Happy Farm is based in Atascadero, California." in ln for ln in lines))  # D5
        self.assertTrue(any(ln.startswith("Reply yes to save it") for ln in lines))
        self.assertNotIn("$", "\n".join(outs[3][1]))  # D9: no price anywhere
        self.assertEqual(chat.commits(), 0)

    def test_a_new_maker_is_previewed_as_the_new_product_not_as_the_maker(self):
        chat = self.open(JAR)
        self.say_all(chat, [
            ("new honey, in stock", reply(name="Honey", availability="yes")),
            ("Bee Happy Farm", reply(maker="Bee Happy Farm")),
            ("Atascadero, California", reply(place="Atascadero, California")),
            ("skip", reply()),  # HASS-LIVE-ADD-2: a new maker is asked for a story; skip keeps only the town line
        ], JAR)
        self.assertEqual({r["kind"] for r in chat.kit.previewer.requests[-1:]}, {"product"})

    def test_a_photo_that_cannot_be_made_house_style_is_warned_about_before_the_yes(self):
        chat = self.open(TILTED)
        (disposition, replies), = self.say_all(chat, [
            ("new hot sauce from Cal Poly, in stock",
             reply(name="Hot sauce", maker="Cal Poly", shelf="pantry", availability="yes")),
        ], TILTED)
        self.assertEqual(disposition, "proposed")
        text = "\n".join(replies)
        warn = text.index("I'll use the photo as you took it")  # D6: kind retake advice, approval stays his
        self.assertLess(warn, text.index("Reply yes to save it"))
        self.assertIn("If this one is fine, just reply yes.", text)
        self.assertEqual(chat.commits(), 0)

    def test_item_add_in_a_calls_reply_shows_the_same_notes_before_the_yes(self):
        """A one-entry ``calls`` reply is drafted like a single skill: shelf-check line, maker explanation (D5), no price."""
        chat = self.open(JAR)
        text = "new honey from Bee Happy Farm in Atascadero, California, in stock"
        chat.script(text, {"calls": [{"skill": "item.add", "slots": {
            "name": "Honey", "maker": "Bee Happy Farm", "place": "Atascadero, California", "availability": "yes"}}], "revises": None})
        self.assertEqual(chat.say(text, JAR)[0], "question")  # a new maker is asked for a story first
        chat.script("skip", {"skill": "item.add", "slots": {}, "revises": None})
        disposition, replies = chat.say("skip")
        self.assertEqual(disposition, "proposed")
        lines = [ln.strip() for ln in "\n".join(replies).split("\n")]
        self.assertIn("This also records today as the day you checked the shelves.", lines)  # D2, its own line
        self.assertIn("Bee Happy Farm is new on the site, so I'm adding them too.", lines)
        self.assertTrue(any("Bee Happy Farm is based in Atascadero, California." in ln for ln in lines))  # D5
        self.assertTrue(any(ln.startswith("Reply yes to save it") for ln in lines))
        self.assertEqual(chat.commits(), 0)

    def test_item_add_in_a_calls_reply_warns_about_a_photo_that_cannot_be_made_house_style(self):
        chat = self.open(TILTED)
        text = "new hot sauce from Cal Poly, in stock"
        chat.script(text, {"calls": [{"skill": "item.add", "slots": {
            "name": "Hot sauce", "maker": "Cal Poly", "shelf": "pantry", "availability": "yes"}}], "revises": None})
        disposition, replies = chat.say(text, TILTED)
        self.assertEqual(disposition, "proposed")
        said = "\n".join(replies)
        self.assertLess(said.index("I'll use the photo as you took it"), said.index("Reply yes to save it"))  # D6, before his yes
        self.assertIn("This also records today as the day you checked the shelves.", said)  # D2 in the same reply
        self.assertEqual(chat.commits(), 0)

    def test_a_description_the_site_cannot_show_is_asked_again_and_the_request_is_kept(self):
        chat = self.open(JAR)
        (disposition, replies), = self.say_all(chat, [
            ("new Cal Poly honey is in. Amazing honey! Batch 12 is the best.",
             reply(name="Cal Poly honey", maker="Cal Poly", shelf="pantry", availability="yes",
                   description="Amazing honey! Batch 12 is the best.")),
        ], JAR)
        self.assertEqual(disposition, "question")  # the real editor never saw it
        self.assertIn("Could you send a different one?", replies[0])
        live = chat.live()
        self.assertEqual((live["skill"], live["state"]), ("item.add", "open"))  # kept, not closed as a failure
        self.assertEqual(chat.drafts(), [])
        self.assertEqual(chat.commits(), 0)

    def test_two_products_on_one_photo_ask_which_and_his_answer_goes_on_to_one_proposal(self):
        chat = self.open(JAR)
        first = "add the lemon curd and the plum jam, both from Cal Poly and in stock"
        (d1, r1), (d2, r2) = self.say_all(chat, [
            (first, reply(name="Lemon curd", maker="Cal Poly", shelf="pantry", availability="yes")),
            ("The lemon curd", reply(name="Lemon curd")),
        ], JAR)
        self.assertEqual((d1, r1), ("question", [ia.ONE_PHOTO]))  # the first, ambiguous message still asks and never picks
        self.assertEqual(chat.commits(), 0)
        self.assertEqual(d2, "proposed")  # his answer settles it: no repeat of the question
        text = "\n".join(r2)
        self.assertIn("A new product: Lemon curd", text)
        self.assertNotIn("Plum jam", text)  # no second product
        self.assertNotIn(ia.ONE_PHOTO, text)
        self.assertIn("Reply yes to save it", text)  # the normal approval, still his
        self.assertEqual(chat.commits(), 0)  # nothing is written before his own yes
        self.assertEqual([r["kind"] for r in chat.kit.previewer.requests][-1], "product")
        drafts = chat.drafts()
        self.assertEqual(len(drafts), 1)  # one change, one product
        self.assertEqual(json.dumps(drafts[0]).count("Plum jam"), 0)

    def test_a_photo_alone_asks_what_it_is_for_instead_of_guessing(self):
        chat = self.open(JAR)
        (disposition, replies), = self.say_all(chat, [("", None)], JAR)
        self.assertEqual(disposition, "photo-question")
        self.assertIn("add a new product", replies[0])
        self.assertEqual(chat.drafts(), [])


if __name__ == "__main__":
    unittest.main()

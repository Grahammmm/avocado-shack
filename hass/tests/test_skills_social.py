"""SKILLS-SOCIAL-1 part 1 (AV1109-06): the read-only caption skills social.item, social.hike and social.maker.

Each answer is social_draft's own caption (the same text as `post <id>` / `post hike <id>`), as text to copy: no attachment,
no approval, no draft, nothing posted, saved or scheduled. The real Conversation and Dispatcher run on the throwaway writer
repo with a scripted interpreter (skill-shaped replies), an injected clock and a stub router; every case row of
hass/tests/fixtures/skills/social/ is replayed through them and must give exactly the recorded answer.
Run: python3 -B -m unittest hass.tests.test_skills_social -v
"""
import json
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from hass import social_draft, skills, voice
from hass.content_model import REPO_ROOT, load_content
from hass.ops import load_registry
from hass.skills import dispatch, model, social, specials, testkit
from hass.tests.test_conversation import CHAT, T0
from hass.tests.test_skill_dispatch import DESCRIBE, SkillCase, skill_reply

CASES = REPO_ROOT / "hass" / "tests" / "fixtures" / "skills" / "social"
NAMES = ("social.item", "social.hike", "social.maker")
GOLDEN = "Golden berries picked at dawn, sweet and soft. " * 12  # a 576-character description: the caption runs past 600


def hike(hid, title, **changes):
    return {"id": hid, "title": title, "startsAt": "2026-11-14T16:00:00Z", "timezone": "America/Los_Angeles",
            "status": "scheduled", "meetingPoint": "the Shack porch", "trailId": "idea-point-buchon", **changes}


EVENTS = [hike("h-ok", "Bluff Walk"), hike("h-cancelled", "Cove Walk", status="cancelled"),
          hike("h-done", "Dune Walk", status="completed"), hike("h-past", "Pier Walk", startsAt="2026-11-01T16:00:00Z"),
          hike("h-draft", "Ridge Walk", status="draft"), hike("h-now", "Sunrise Walk", startsAt=T0.strftime("%Y-%m-%dT%H:%M:%SZ")),
          hike("h-spring", "Spring Walk", startsAt="2027-04-10T16:00:00Z"), hike("h-tag", "Porch Walk", meetingPoint="the #porch")]


class SocialCase(SkillCase):
    """The writer repo with photos, held/hidden/photo-less products, makers with and without a story, and hikes in every state."""
    SKILLS = social.SKILLS + (DESCRIBE,)

    def setUp(self):
        super().setUp()
        self.content_dir = self.repo.wt / "hass" / "content"
        site = self.repo.wt / "storefront-mockup"
        (site / "post-test").mkdir()
        (site / "post-test" / "real.jpg").write_bytes(b"jpeg")
        self.outside = tempfile.TemporaryDirectory()
        self.addCleanup(self.outside.cleanup)
        (Path(self.outside.name) / "far.jpg").write_bytes(b"jpeg")
        (site / "post-test" / "out.jpg").symlink_to(Path(self.outside.name) / "far.jpg")
        path = self.content_dir / "products.json"
        doc = json.loads(path.read_text("utf-8"))
        changes = ({"image": "post-test/real.jpg", "producerKey": "Linn's"}, {"status": "held"}, {"status": "hidden"},
                   {"image": "post-test/missing.jpg"}, {"image": "post-test/real.jpg"}, {"image": "post-test/out.jpg"},
                   {"image": "post-test/real.jpg", "description": GOLDEN.strip()})
        for p, change in zip(doc["products"], changes):
            p.update(status="active", **change) if "status" not in change else p.update(change)
        path.write_text(json.dumps(doc), "utf-8")
        path = self.content_dir / "makers.json"
        doc = json.loads(path.read_text("utf-8"))
        doc["makers"]["Stepladder"].pop("story", None)
        doc["makers"]["Etto"]["hidden"] = True
        doc["makers"]["Quiet Acres"] = {**doc["makers"]["Linn's"], "name": "Quiet Acres"}  # no product names this maker
        path.write_text(json.dumps(doc), "utf-8")
        path = self.content_dir / "community.json"
        doc = json.loads(path.read_text("utf-8"))
        doc["events"] = EVENTS
        path.write_text(json.dumps(doc), "utf-8")
        self.prepared = []  # every call into the draft path (editor.prepare, claims, proposal): a caption makes none
        real_draft = self.conv._draft
        self.conv._draft = lambda *a, **k: self.prepared.append(a) or real_draft(*a, **k)

    def content(self):
        return load_content(self.content_dir)

    def snapshot(self):
        return {p.name: p.read_bytes() for p in sorted(self.content_dir.iterdir()) if p.is_file()}

    def ask(self, text, reply):
        """One owner message answered by the real dispatcher: (disposition, [(plain text, attachments)], ...)."""
        self.script(text, reply)
        before = self.conv.db.execute("SELECT COALESCE(MAX(id), 0) FROM outbox").fetchone()[0]
        disposition = self.say(text)
        rows = self.conv.db.execute("SELECT text, attachments FROM outbox WHERE id > ? ORDER BY id", (before,)).fetchall()
        self.replies()
        return disposition, [(r["text"], json.loads(r["attachments"] or "[]")) for r in rows]

    def answered(self, text, reply):
        disposition, rows = self.ask(text, reply)
        self.assertTrue(all(files == [] for _t, files in rows), rows)  # a caption answer never carries a file
        return disposition, [t for t, _f in rows]

    def assert_untouched(self, before):
        self.assertEqual(self.snapshot(), before)
        self.nothing_written()
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.prepared, [])
        self.assertEqual(self.conv.db.execute("SELECT COUNT(*) FROM backlog").fetchone()[0]
                         if self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'backlog'").fetchone() else 0, 0)

    def want(self, kind, key, now=T0):
        c = self.content()
        if kind == "item":
            out = social_draft.build(c, key, self.repo.wt / "storefront-mockup")
            return "\n".join([social.COPY_HEAD, out["caption"], social.PRODUCT_PHOTO])
        out = social_draft.build_hike(c, key, now) if kind == "hike" else social_draft.build_maker(c, key)
        return "\n".join([social.COPY_HEAD, out["caption"], social.NO_PHOTO])

    def product(self, name):
        return next(p for p in self.content().products if p["name"] == name)


def rows(name):
    return testkit.load_rows(CASES / f"{name}.jsonl")


class DeclarationTests(unittest.TestCase):
    def test_three_registered_read_only_handlers(self):
        reg = skills.load_skills()
        self.assertEqual([n for n in reg.skills if n.startswith("social.")], [*NAMES, "social.recap"])  # part 2 (test_social_recap.py)
        self.assertEqual(skills.skill_lint(reg, load_registry()), [])
        social._register()  # registering again changes nothing
        social._register()
        for skill in social.SKILLS:
            with self.subTest(skill.name):
                self.assertEqual(model.lint_skill(skill, load_registry()), [])
                self.assertEqual((skill.approval, skill.edits, skill.side_effects, skill.preview, skill.live_class, skill.undo),
                                 ("none", (), ("none",), "none", "read-only", model.Undo("none", "none")))
                slots = {"item": "x", "hike": "y", "maker": "z"}
                self.assertEqual(skill.plan(slots, None), [])
                self.assertEqual(slots, {"item": "x", "hike": "y", "maker": "z"})
                self.assertIs(dispatch.READ_ONLY[skill.name], social.REPLIES[skill.name])
                self.assertIn(skill.name, dispatch.READ_ONLY_LONG)
                self.assertEqual(skill.cases, f"hass/tests/fixtures/skills/social/{skill.name}.jsonl")
                got = rows(skill.name)
                self.assertGreaterEqual(len(got), model.MIN_CASE_ROWS)
                self.assertGreaterEqual(sum(1 for r in got if r["kind"] == "refuse"), model.MIN_REFUSAL_ROWS)
                self.assertTrue(all(r["version"] == 1 and "undo" not in r and r["kind"] != "undo" for r in got))
        self.assertEqual(dispatch.READ_ONLY_LONG & {"specials.show", "answer.site"}, {"specials.show"})  # long: the captions, the specials list; not every read-only skill
        self.assertIs(dispatch.READ_ONLY["specials.show"], specials.show_reply)

    def test_every_fixed_reply_passes_the_voice_rules(self):
        for text in (social.COPY_HEAD, social.PRODUCT_PHOTO, social.NO_PHOTO, social.NO_POSTING, social.CANT_READ, social.CANT_SEE_PHOTO,
                     social.NO_STORY, dispatch.MIXED, *social.ITEM_REFUSALS.values(), *social.HIKE_REFUSALS.values(),
                     *social.MAKER_REFUSALS.values(), *social.SHARED_REFUSALS.values(), *social.RESOLVER_REFUSALS.values()):
            self.assertEqual(voice.check(text), [], text)
        self.assertEqual(social.NO_STORY.split(". ")[-1], "Add the maker's story first.")

    def test_posting_words_are_told_apart_from_caption_words(self):
        for text in ("post it now", "schedule it", "Schedule the honey post for Friday", "publish the hike post", "post this today",
                     "send the hike post to the club", "email it to the hikers", "can you post it on instagram for me",
                     "share that tonight", "post the honey now"):
            self.assertTrue(social.wants_posting([text]), text)
        for text in ("post about the honey", "write a post for the honey", "post hike Bluff Walk", "make an instagram post for the plums",
                     "caption for the sourdough so I can post it myself", "post about the scheduled hike", "I'll post it later",
                     "post the honey on instagram", "captions for the honey and the plum jam"):
            self.assertFalse(social.wants_posting([text]), text)
        self.assertIsNone(social.preflight("specials.show", {}, types.SimpleNamespace(texts=["post it now"])))


class HandlerTests(unittest.TestCase):
    """The reply functions on hand-made content: missing context, a broken record and a caption near Instagram's limit."""
    NOW = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.site = tempfile.TemporaryDirectory()
        self.addCleanup(self.site.cleanup)
        Path(self.site.name, "a.jpg").write_bytes(b"jpeg")
        self.content = types.SimpleNamespace(
            products=[{"id": "p1", "name": "Plum jam", "description": "x" * 2120, "image": "a.jpg", "status": "active",
                       "category": "pantry", "producerKey": "m"},
                      {"id": "p2", "name": "Fig jam", "description": "Figs.", "image": "a.jpg", "status": "active", "category": "pantry"}],
            makers={"m": {"name": "Jam Lady", "place": "Cambria, California", "story": "   "}}, community={"events": []})

    def ctx(self, **kw):
        return types.SimpleNamespace(**{"content": self.content, "site_dir": Path(self.site.name), "now": self.NOW, **kw})

    def test_long_caption_and_missing_context(self):
        text = social.item_reply({"item": "p1"}, self.ctx())
        caption = social_draft.build(self.content, "p1", Path(self.site.name))["caption"]
        self.assertTrue(2100 < len(caption) <= social_draft.MAX_CAPTION)
        self.assertEqual(voice.plain(text), "\n".join([social.COPY_HEAD, caption, social.PRODUCT_PHOTO]))
        self.assertEqual(voice.check(text, long_ok=True), [])
        self.assertTrue(voice.check(text))  # an everyday message this long is refused: long_ok is what lets it through
        self.assertEqual(social.item_reply({"item": "p2"}, self.ctx(site_dir=None)), social.CANT_SEE_PHOTO)  # never this checkout's own site
        self.assertEqual(social.item_reply({"item": "p2"}, self.ctx(content=None)), social.CANT_READ)
        self.assertEqual(social.hike_reply({"hike": "h"}, self.ctx(now=None)), social.CANT_READ)
        self.assertEqual(social.maker_reply({"maker": "m"}, self.ctx(content=None)), social.CANT_READ)
        self.assertEqual(social.maker_reply({"maker": "m"}, self.ctx()), social.NO_STORY)  # a blank story is no story
        broken = types.SimpleNamespace(products="nope", makers={}, community={"events": "nope"})
        for fn, slots in ((social.item_reply, {"item": "p1"}), (social.hike_reply, {"hike": "h"}), (social.maker_reply, {"maker": "m"})):
            self.assertEqual(fn(slots, self.ctx(content=broken)), social.CANT_READ)
        self.content.products[0]["description"] = "x" * 2300
        self.assertEqual(social.item_reply({"item": "p1"}, self.ctx()), social.SHARED_REFUSALS["caption too long"])


class CaseRowTests(SocialCase):
    def test_every_case_row_gives_the_recorded_answer(self):
        for name in NAMES:
            for row in rows(name):
                with self.subTest(row["id"]):
                    replay = row["note"]["dispatch"]
                    self.now = T0
                    self.conv.requests.close_live(CHAT, self.now, "closed")
                    before = self.snapshot()
                    disposition, said = self.answered(row["texts"][0], replay["skill"])
                    self.assertEqual(disposition, replay["disposition"])
                    self.assertEqual(said, replay["said"])
                    # The generic ops-only kit has no long-caption reply path.
                    # Its short wording replay is separate from this exact oracle.
                    answer = "\n\n".join(said)
                    generic = answer.splitlines()[0] if len(answer) > voice.LONG_AFTER else answer
                    self.assertEqual(row["replies"], [{"unsupported": generic}])
                    self.assertIn(row["expect"]["reply_contains"], "\n\n".join(said))
                    self.assert_untouched(before)


class ItemTests(SocialCase):
    def test_item_caption_uses_writer_site_and_has_no_attachment(self):
        before = self.snapshot()
        disposition, said = self.answered("write a post for the avocado", skill_reply("social.item", item="Hass avocado"))
        self.assertEqual(disposition, "answer")
        self.assertEqual(said, [self.want("item", self.product("Hass avocado")["id"])])
        self.assertIn("From Linn's in Cambria, California.", said[0])
        self.assertTrue(said[0].endswith("\n" + social.PRODUCT_PHOTO))
        self.assertIn(social_draft.build(self.content(), self.product("Hass avocado")["id"],
                                         self.repo.wt / "storefront-mockup")["caption"], said[0])
        # the photo is checked in the writer's own site folder: this checkout's site has no post-test folder
        self.assertFalse((REPO_ROOT / "storefront-mockup" / "post-test" / "real.jpg").exists())
        for name, want in (("Oranges", social.RESOLVER_REFUSALS[("item", "held")]), ("Lemons", social.RESOLVER_REFUSALS[("item", "hidden")]),
                           ("Strawberries", social.ITEM_REFUSALS["no photo on the site"]),
                           ("Blueberries", social.ITEM_REFUSALS["no photo on the site"])):  # a photo outside the site folder
            with self.subTest(name):
                self.assertEqual(self.answered(f"caption for the {name}", skill_reply("social.item", item=name))[1], [want])
                self.assertIsNone(self.live())
        self.assert_untouched(before)

    def test_long_caption_strict_voice_and_legacy_paths(self):
        golden = self.product("Golden raspberries")
        disposition, said = self.answered("caption for the golden raspberries", skill_reply("social.item", item="Golden raspberries"))
        self.assertEqual(disposition, "answer")
        self.assertGreater(len(said[0]), voice.LONG_AFTER)
        self.assertEqual(said, [self.want("item", golden["id"])])
        # the post command is unchanged: same caption, with its photo and alt line
        _d, rows = self.ask("post " + golden["id"], {"unsupported": "x"})
        self.assertIn(social_draft.build(self.content(), golden["id"], self.repo.wt / "storefront-mockup")["caption"], rows[0][0])
        self.assertEqual(len(rows[0][1]), 1)
        # a stranger gets nothing and starts nothing
        self.script("write a post for the avocado", skill_reply("social.item", item="Hass avocado"))
        self.say("write a post for the avocado", sender="stranger@example.invalid")
        self.assertEqual(self.replies(), [])
        # a duplicate delivery of the same message is answered once
        self.script("caption for the avocado", skill_reply("social.item", item="Hass avocado"))
        self.say("caption for the avocado", pid="dup-1")
        self.say("caption for the avocado", pid="dup-1")
        self.assertEqual(len(self.replies()), 1)


class HikeMakerTests(SocialCase):
    def test_hike_and_maker_engine_parity(self):
        before = self.snapshot()
        for title, key, when in (("Bluff Walk", "h-ok", T0), ("Sunrise Walk", "h-now", T0), ("Spring Walk", "h-spring", T0)):
            with self.subTest(title):
                disposition, said = self.answered(f"caption for the {title}", skill_reply("social.hike", hike=title))
                self.assertEqual((disposition, said), ("answer", [self.want("hike", key, when)]))
        self.assertIn("Saturday, April 10 at 9:00 am (Pacific)", self.answered("x spring", skill_reply("social.hike", hike="Spring Walk"))[1][0])
        self.assertIn("Saturday, November 14 at 8:00 am (Pacific)", self.answered("x bluff", skill_reply("social.hike", hike="Bluff Walk"))[1][0])
        for title, reason in (("Cove Walk", "hike is cancelled"), ("Dune Walk", "hike already happened"),
                              ("Pier Walk", "hike already happened"), ("Ridge Walk", "not scheduled")):
            with self.subTest(title):
                self.assertEqual(self.answered(f"post about {title}", skill_reply("social.hike", hike=title))[1], [social.HIKE_REFUSALS[reason]])
        self.assertEqual(self.answered("post about the porch walk", skill_reply("social.hike", hike="Porch Walk"))[1],
                         [social.SHARED_REFUSALS["free text has a hashtag or account name"]])
        self.now = T0 + timedelta(minutes=1)  # a minute after the start, the same hike has happened
        self.assertEqual(self.answered("sunrise again", skill_reply("social.hike", hike="Sunrise Walk"))[1],
                         [social.HIKE_REFUSALS["hike already happened"]])
        self.now = T0
        self.assertEqual(self.answered("maker post for linns", skill_reply("social.maker", maker="Linn's")), ("answer", [self.want("maker", "Linn's")]))
        self.assertEqual(self.answered("maker post for stepladder", skill_reply("social.maker", maker="Stepladder"))[1], [social.NO_STORY])
        self.assertEqual(self.answered("maker post for etto", skill_reply("social.maker", maker="Etto"))[1],
                         [social.RESOLVER_REFUSALS[("maker", "hidden")]])
        for _t, files in self.ask("maker post for linns again", skill_reply("social.maker", maker="Linn's"))[1]:
            self.assertEqual(files, [])
        self.assert_untouched(before)


class BatchTests(SocialCase):
    def test_two_items_two_answers_in_order(self):
        before = self.snapshot()
        avo, golden = self.product("Hass avocado")["id"], self.product("Golden raspberries")["id"]
        two = {"calls": [{"skill": "social.item", "slots": {"item": "Hass avocado"}},
                         {"skill": "social.item", "slots": {"item": "Golden raspberries"}}]}
        self.assertEqual(self.answered("captions for the avocado and the golden raspberries", two),
                         ("answer", [self.want("item", avo), self.want("item", golden)]))
        twice = {"calls": [{"skill": "social.item", "slots": {"item": "Hass avocado"}}, {"skill": "social.item", "slots": {"item": "Hass avocado"}}]}
        self.assertEqual(self.answered("avocado caption twice", twice), ("answer", [self.want("item", avo)]))
        # a held sibling is refused in its own words; the valid one still answers
        held = {"calls": [{"skill": "social.item", "slots": {"item": "Oranges"}}, {"skill": "social.maker", "slots": {"maker": "Linn's"}}]}
        self.assertEqual(self.answered("oranges and linns posts", held),
                         ("answer", [social.RESOLVER_REFUSALS[("item", "held")], self.want("maker", "Linn's")]))
        # an unknown sibling is asked about once; the answer gives its caption; the queued third ask is asked next
        three = {"calls": [{"skill": "social.item", "slots": {"item": "Hass avocado"}},
                           {"skill": "social.item", "slots": {"item": "zucchini bread"}},
                           {"skill": "social.hike", "slots": {}}]}
        disposition, said = self.answered("posts for the avocado, zucchini bread and a hike", three)
        self.assertEqual(disposition, "question")
        self.assertEqual(said[0], self.want("item", avo))
        self.assertEqual(said[1], "I don't know a product called that. What is it called on the site?")
        self.assertEqual(self.live()["skill"], "social.item")
        disposition, said = self.answered("the golden raspberries", skill_reply("social.item", item="Golden raspberries"))
        self.assertEqual(said, [self.want("item", golden), "Which hike should the post be about?"])
        disposition, said = self.answered("bluff walk", skill_reply("social.hike", hike="Bluff Walk"))
        self.assertEqual((disposition, said), ("answer", [self.want("hike", "h-ok")]))
        self.assertIsNone(self.live())
        self.assert_untouched(before)

    def test_a_held_answer_to_the_first_question_keeps_the_queued_caption(self):
        before = self.snapshot()
        two = {"calls": [{"skill": "social.item", "slots": {}}, {"skill": "social.hike", "slots": {}}]}
        self.assertEqual(self.answered("posts for a product and a hike", two),
                         ("question", ["Which product should the post be about?"]))
        self.assertEqual(len(self.live()["calls"]), 1)
        # the held product is refused in its own words, and the queued hike is still asked
        disposition, said = self.answered("the oranges", skill_reply("social.item", item="Oranges"))
        self.assertEqual((disposition, said), ("refused", [social.RESOLVER_REFUSALS[("item", "held")], "Which hike should the post be about?"]))
        self.assertEqual(self.live()["skill"], "social.hike")
        disposition, said = self.answered("bluff walk", skill_reply("social.hike", hike="Bluff Walk"))
        self.assertEqual((disposition, said), ("answer", [self.want("hike", "h-ok")]))
        self.assertIsNone(self.live())
        self.assert_untouched(before)

    def test_a_caption_and_a_change_in_one_message_draft_nothing(self):
        before = self.snapshot()
        mixed = {"calls": [{"skill": "social.item", "slots": {"item": "Hass avocado"}},
                           {"skill": "item.describe", "slots": {"product": "Hass avocado", "description": "Ripe and creamy"}}]}
        self.assertEqual(self.answered("caption for the avocado and make it say ripe and creamy", mixed), ("refused", [dispatch.MIXED]))
        self.assertIsNone(self.live())
        self.assert_untouched(before)


class PostingTests(SocialCase):
    def test_explicit_post_send_schedule_is_honest(self):
        before = self.snapshot()
        with mock.patch("socket.socket", side_effect=AssertionError("network")):
            for text, reply in (("post it now", skill_reply("social.item")), ("schedule it", skill_reply("social.hike")),
                                ("send the hike post to the club", skill_reply("social.hike", hike="Bluff Walk")),
                                ("post the avocado now", skill_reply("social.item", item="Hass avocado")),
                                ("publish the maker post", {"calls": [{"skill": "social.maker", "slots": {"maker": "Linn's"}}]})):
                with self.subTest(text):
                    self.assertEqual(self.answered(text, reply), ("refused", [social.NO_POSTING]))
                    self.assertIsNone(self.live())
            # ordinary caption wording is a caption
            self.assertEqual(self.answered("post about the avocado", skill_reply("social.item", item="Hass avocado")),
                             ("answer", [self.want("item", self.product("Hass avocado")["id"])]))
            # the slot question is still asked when nothing says post or schedule
            self.assertEqual(self.answered("write a post", skill_reply("social.item")), ("question", ["Which product should the post be about?"]))
        self.assert_untouched(before)


if __name__ == "__main__":
    unittest.main()

"""SKILLS-MAKERS-1: the four maker skills (add, edit, hide, restore a maker and their about text).

Proves, against the real content and the shared skill kit: the lint, every rule one by one, the plain-words replies
(HASS-VOICE-1 rules), the one-line note for a maker with no story (D5), the pronoun rewrite, the live boundary class
each skill declares, the case files (run through the real Conversation and Editor by test_skills_cases) and a restore
of a hidden maker with its undo (the shared kit cannot start from a hidden maker, so it is done here).
Run: python3 -B -m unittest hass.tests.test_skills_makers -v
"""
import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import itemstd, live_policy, skills, voice
from hass.content_model import REPO_ROOT, TEXT_LIMITS, load_and_validate
from hass.ops import load_registry
from hass.skills import makers as m
from hass.skills import testkit
from hass.tests.test_skill_dispatch import SkillCase, registry_of

CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
BY_NAME = {s.name: s for s in m.SKILLS}
CASES = REPO_ROOT / "hass" / "tests" / "fixtures" / "skills" / "makers"


def ctx(content=CONTENT, **extra):
    return SimpleNamespace(today="2026-11-08", content=content, **extra)


def refusal(fn, slots, **extra):
    with unittest.TestCase().assertRaises(m.Refusal) as caught:
        fn(slots, ctx(**extra))
    return caught.exception


def with_hidden(*keys):
    """A copy of the real content where these makers (and their products) are hidden."""
    content = copy.deepcopy(CONTENT)
    for key in keys:
        content.makers[key]["hidden"] = True
        for p in content.products:
            if p.get("producerKey") == key and p.get("status") == "active":
                p["status"] = "hidden"
    return content


class Declaration(unittest.TestCase):
    def test_four_skills_in_the_registry_and_the_lint_is_clean(self):
        registry = skills.load_skills()
        self.assertEqual([n for n in registry.skills if n.startswith("maker.")], ["maker.add", "maker.edit", "maker.hide", "maker.restore"])
        golden = {"maker.add": [{"name": "Bee Happy Farm", "place": "Atascadero, California"}], "maker.edit": [{"maker": "Etto", "story": "Pasta."}],
                  "maker.hide": [{"maker": "Etto"}], "maker.restore": [{"maker": "Etto"}]}
        self.assertEqual(skills.skill_lint(m.SKILLS, load_registry(), golden=golden), [])

    def test_every_rule_id_has_a_function_or_is_the_editors(self):
        for skill in m.SKILLS:
            for rule in skill.rules:
                with self.subTest(skill=skill.name, rule=rule):
                    self.assertTrue(callable(m.RULES.get(rule)) or rule in m.EDITOR_RULES)

    def test_limits_come_from_the_content_model(self):
        for skill in m.SKILLS:
            for slot in skill.slots:
                if slot.limit:
                    self.assertIn(slot.limit[1], TEXT_LIMITS[slot.limit[0]])

    def test_every_ask_is_short_and_every_refuse_reply_is_plain_words(self):
        for skill in m.SKILLS:
            for slot in skill.slots:
                self.assertEqual(voice.check(slot.ask) if slot.ask else [], [], slot.ask)
            for _why, reply in skill.refuse:
                self.assertEqual(voice.check(reply.replace("<Maker>", "Etto")), [], reply)

    def test_case_files_have_enough_rows_refusals_and_the_right_version(self):
        for skill in m.SKILLS:
            rows = [json.loads(line) for line in (REPO_ROOT / skill.cases).read_text("utf-8").splitlines() if line.strip()]
            with self.subTest(skill=skill.name):
                self.assertGreaterEqual(len(rows), 10)
                self.assertGreaterEqual(sum(r.get("kind") == "refuse" for r in rows), 2)
                self.assertTrue(all(r["version"] == skill.version for r in rows))
                self.assertTrue(any("plan" in r for r in rows))
                if skill.name != "maker.restore":  # restore needs a hidden maker to start from: see Restore below
                    self.assertTrue(any(r.get("expect", {}).get("diff") for r in rows), "a row that is approved and undone")

    def test_live_class_matches_the_live_boundary(self):
        """Each skill declares private-only or chat-live; live_policy.check on a real draft must agree."""
        scratch = testkit.Scratch({}, BY_NAME)
        try:
            def blocked(ops):
                out = scratch.editor.prepare(ops)
                self.assertEqual(out["result"], "ok", out)
                return bool(live_policy.check(out["draft"]))
            add = m.plan_add({"name": "Bee Happy Farm", "place": "Atascadero, California", "story": "Bees on the hill."}, ctx())
            self.assertTrue(blocked(add))
            self.assertTrue(blocked(m.plan_edit({"maker": "Etto", "place": "Templeton, California"}, ctx())))
            self.assertTrue(blocked(m.plan_hide({"maker": "Etto", "with_products": True}, ctx())))  # G: only the about text is live
        finally:
            scratch.close()
        self.assertEqual({s.name: s.live_class for s in m.SKILLS},
                         {"maker.add": "private-only", "maker.edit": "private-only", "maker.hide": "private-only", "maker.restore": "private-only"})

    def test_triggers_are_the_spec_sentences_and_unique_across_the_four(self):
        texts = [t.text.lower() for s in m.SKILLS for t in s.triggers]
        self.assertEqual(len(texts), len(set(texts)))
        self.assertTrue(all(len(s.triggers) >= 6 for s in m.SKILLS))


class AddAMaker(unittest.TestCase):
    def test_a_story_is_his_sentences_with_the_pronoun_replaced_by_the_name(self):
        out = m.describe_add({"name": "Bee Happy Farm", "place": "Atascadero, California", "story": "They keep bees on the hill. Their honey is dark."}, ctx())
        self.assertEqual(out.ops[0]["args"]["story"], "Bee Happy Farm keeps bees on the hill. Bee Happy Farm\u2019s honey is dark.")
        self.assertEqual(out.set_lines, ())

    def test_no_story_is_the_one_line_note_d5(self):
        out = m.describe_add({"name": "Lonesome Dove Bakery", "place": "Paso Robles, California"}, ctx())
        self.assertEqual(out.ops, [{"op": "maker.add", "args": {"key": "Lonesome Dove Bakery", "name": "Lonesome Dove Bakery", "place": "Paso Robles, California",
                                                              "story": "Lonesome Dove Bakery is based in Paso Robles, California."}}])
        self.assertIn("because you didn't give one", out.set_lines[0])
        self.assertEqual(m.fallback_story("Etto", "Paso Robles."), "Etto is based in Paso Robles.")
        self.assertLessEqual(len(m.fallback_story("n" * 80, "p" * 60)), TEXT_LIMITS["maker"]["story"])

    def test_a_claim_he_did_not_say_is_left_off_and_the_note_is_used(self):
        said = m.describe_add({"name": "Bee Happy Farm", "place": "Atascadero, California", "story": "They are organic."}, ctx(owner_text="Bee Happy Farm in Atascadero, they are organic"))
        self.assertEqual(said.ops[0]["args"]["story"], "Bee Happy Farm is organic.")
        self.assertEqual(said.left_off, ())
        unsaid = m.describe_add({"name": "Bee Happy Farm", "place": "Atascadero, California", "story": "They are organic."}, ctx(owner_text="Bee Happy Farm in Atascadero"))
        self.assertEqual(unsaid.ops[0]["args"]["story"], "Bee Happy Farm is based in Atascadero, California.")
        self.assertIn("organic", unsaid.left_off[0])
        denied = m.describe_add({"name": "Bee Happy Farm", "place": "Atascadero, California", "story": "They are organic."}, ctx(owner_text="Bee Happy Farm in Atascadero, not organic"))
        self.assertTrue(denied.left_off)

    def test_name_and_town_are_asked_for_when_missing(self):
        self.assertIn("What is the maker called", refusal(m.describe_add, {"place": "Cambria"}).reply)
        err = refusal(m.describe_add, {"name": "Bee Happy Farm"})
        self.assertEqual((err.kind, err.reply), ("question", "Where are they based (town and state)?"))

    def test_a_twin_is_never_a_second_maker(self):
        for said in ("Etto", "etto", "  ETTO ", "Linns", "linn\u2019s"):
            with self.subTest(said=said):
                self.assertIn("is already on the site", refusal(m.describe_add, {"name": said, "place": "Somewhere"}).reply)
        hidden = with_hidden("Etto")
        err = refusal(m.describe_add, {"name": "Etto", "place": "Paso Robles"}, content=hidden)
        self.assertIn("hidden", err.reply)
        self.assertIn("bring them back", err.reply)

    def test_a_price_and_special_marks_are_refused_in_every_text(self):
        for slots in ({"name": "Beans $5", "place": "x"}, {"name": "x", "place": "y $3"}, {"name": "x", "place": "y", "story": "Coffee, $12 a bag."},
                      {"name": "x", "place": "y", "story": "Beans per lb"}, {"name": "x", "place": "y", "story": "Beans 12 dollars"}):
            with self.subTest(slots=slots):
                self.assertEqual(refusal(m.describe_add, slots).reply, m.PRICE_REPLY)
        self.assertEqual(refusal(m.describe_add, {"name": "x", "place": "y", "story": "<b>Hi</b>"}).reply, m.PLAIN_TEXT_REPLY)

    def test_the_website_is_one_public_https_address_or_a_question(self):
        add = lambda url: m.describe_add({"name": "Bee Happy Farm", "place": "Atascadero, California", "url": url}, ctx()).ops[0]["args"].get("url")
        self.assertEqual(add("https://beehappyfarm.com"), "https://beehappyfarm.com")
        self.assertEqual(add("beehappyfarm.com"), "https://beehappyfarm.com")
        self.assertEqual(add("www.beehappyfarm.com/about"), "https://www.beehappyfarm.com/about")
        self.assertIsNone(add(""))
        for bad in ("bee-happy dot com", "http://beehappyfarm.com", "https://localhost", "https://10.0.0.1", "ettonew", "javascript:alert(1)"):
            with self.subTest(bad=bad):
                err = refusal(m.describe_add, {"name": "Bee Happy Farm", "place": "Atascadero", "url": bad})
                self.assertEqual(err.kind, "question")
                self.assertIn("full website address", err.reply)

    def test_text_over_the_limit_is_refused_naming_the_part(self):
        err = refusal(m.describe_add, {"name": "x" * (TEXT_LIMITS["maker"]["name"] + 1), "place": "y"})
        self.assertIn("name is longer", err.reply)
        err = refusal(m.describe_add, {"name": "x", "place": "y", "story": "A " * 400})
        self.assertIn("story is longer", err.reply.replace("about text", "story"))

    def test_without_the_content_the_editor_still_checks_the_twin(self):
        out = m.plan_add({"name": "Etto", "place": "Paso Robles, California"}, SimpleNamespace(today="2026-11-08"))
        self.assertEqual(out[0]["op"], "maker.add")


class Pronouns(unittest.TestCase):
    def test_table(self):
        name = "Ripple Creek Bakery"
        cases = {
            "They bake in small batches and sell at the market.": f"{name} bakes in small batches and sells at the market.",
            "They keep bees on the hill.": f"{name} keeps bees on the hill.",
            "They are small. They have goats.": f"{name} is small. {name} has goats.",
            "They started in a small kitchen and now dry pasta slowly.": f"{name} started in a small kitchen and now dries pasta slowly.",
            "They're family run.": f"{name} is family run.",
            "They also grow figs.": f"{name} also grows figs.",
            "They don't use sprays.": f"{name} doesn't use sprays.",
            "They can ship anywhere.": f"{name} can ship anywhere.",
            "They can bake and sell bread.": f"{name} can bake and sell bread.",  # a modal keeps the owner's later verbs
            "They don't spray and sell only fresh fruit.": f"{name} doesn't spray and sell only fresh fruit.",
            "They want to bake and sell bread.": f"{name} wants to bake and sell bread.",  # infinitive
            "They bake bread that locals love and buy.": f"{name} bakes bread that locals love and buy.",  # other subject
            "They grow figs and customers pick and eat them.": f"{name} grows figs and customers pick and eat them.",
            "They grow figs and customers bake and sell pies.": f"{name} grows figs and customers bake and sell pies.",
            "They bake bread, and sell it at the market.": f"{name} bakes bread, and sells it at the market.",
            "She started it in her kitchen.": f"{name} started it in her kitchen.",
            "Her bread is dark.": f"{name}\u2019s bread is dark.",
            "Their honey is dark.": f"{name}\u2019s honey is dark.",
            "Maria started it in her kitchen and now sells to the whole coast.": "Maria started it in her kitchen and now sells to the whole coast.",
            "They watch the weather": f"They watch the weather.",  # a verb we cannot bend is left as he wrote it
            "Honey and bread, they make both.": "Honey and bread, they make both.",  # only a leading pronoun is replaced
            "It is dark.": "It is dark.",
        }
        for said, want in cases.items():
            with self.subTest(said=said):
                self.assertEqual(m.story_words(said, name), want)

    def test_a_full_stop_is_added_and_spacing_cleaned(self):
        self.assertEqual(m.story_words("  Bees   on the hill ", "X"), "Bees on the hill.")
        self.assertEqual(m.story_words("", "X"), "")


class EditAMaker(unittest.TestCase):
    def test_a_story_replaces_the_whole_text(self):
        out = m.describe_edit({"maker": "etto", "story": "They make pasta in small batches."}, ctx())
        self.assertEqual(out.ops, [{"op": "maker.edit", "args": {"key": "Etto", "story": "Etto makes pasta in small batches."}}])

    def test_the_maker_may_be_named_loosely_and_the_key_is_used(self):
        self.assertEqual(m.describe_edit({"maker": "linn", "place": "Templeton, California"}, ctx()).ops[0]["args"]["key"], "Linn's")

    def test_it_already_says_that_changes_nothing(self):
        err = refusal(m.describe_edit, {"maker": "Etto", "place": "Paso Robles, California"})
        self.assertIn("already says that", err.reply)
        out = m.describe_edit({"maker": "Etto", "place": "Paso Robles, California", "name": "Etto Pasta"}, ctx())
        self.assertEqual(out.ops[0]["args"], {"key": "Etto", "name": "Etto Pasta"})
        self.assertIn("The town already says that.", out.notes)

    def test_nothing_to_change_asks_what(self):
        err = refusal(m.describe_edit, {"maker": "Etto"})
        self.assertEqual((err.kind, err.reply), ("question", "What should change about Etto?"))

    def test_a_link_cannot_be_given_and_taken_off_at_once(self):
        err = refusal(m.describe_edit, {"maker": "Etto", "url": "https://example.com", "clear_url": True})
        self.assertEqual(err.kind, "question")

    def test_a_link_the_site_started_with_cannot_be_removed_or_replaced(self):
        for slots in ({"maker": "Etto", "clear_url": True}, {"maker": "Etto", "url": "https://ettonew.example.com"}):
            with self.subTest(slots=slots):
                self.assertIn("was on the site from the start", refusal(m.describe_edit, slots).reply)
        self.assertTrue(m.SOURCE_URLS and all(m.SOURCE_URLS))

    def test_a_link_added_since_can_be_removed_and_one_that_is_not_there_is_said_so(self):
        content = copy.deepcopy(CONTENT)
        content.makers["Etto"]["url"] = "https://newer.example.com"
        out = m.describe_edit({"maker": "Etto", "clear_url": True}, ctx(content))
        self.assertEqual(out.ops[0]["args"], {"key": "Etto", "clearUrl": True})
        out = m.describe_edit({"maker": "Etto", "url": "https://newest.example.com"}, ctx(content))
        self.assertEqual(out.ops[0]["args"], {"key": "Etto", "url": "https://newest.example.com"})
        del content.makers["Etto"]["url"]
        self.assertIn("nothing to take off", refusal(m.describe_edit, {"maker": "Etto", "clear_url": True}, content=content).reply)
        content.makers["Etto"]["url"] = "https://pinned.example.com"  # ctx.source_urls replaces the frozen baseline
        self.assertIn("from the start", refusal(m.describe_edit, {"maker": "Etto", "clear_url": True}, content=content, source_urls={"https://pinned.example.com"}).reply)

    def test_a_new_name_may_not_be_another_makers(self):
        self.assertIn("already on the site", refusal(m.describe_edit, {"maker": "Etto", "name": "Stepladder"}).reply)
        self.assertEqual(m.describe_edit({"maker": "Linn", "name": "Linn's Preserves"}, ctx()).ops[0]["args"], {"key": "Linn's", "name": "Linn's Preserves"})

    def test_a_hidden_maker_is_not_edited(self):
        err = refusal(m.describe_edit, {"maker": "Etto", "story": "x"}, content=with_hidden("Etto"))
        self.assertEqual(err.kind, "question")
        self.assertIn("hidden", err.reply)

    def test_an_unknown_maker_lists_close_names(self):
        self.assertIn("Do you mean Stepladder", refusal(m.describe_edit, {"maker": "Stepladdr", "story": "x"}).reply)
        self.assertEqual(refusal(m.describe_edit, {"maker": "Acme", "story": "x"}).reply, "I don't know a maker called Acme. Who is it?")

    def test_several_makers_fit_one_question(self):
        err = refusal(m.describe_edit, {"maker": "a", "story": "x"})
        self.assertEqual(err.kind, "question")
        self.assertTrue(err.reply.startswith("Which maker do you mean:"))

    def test_a_claim_he_did_not_say_is_left_off_and_a_story_that_is_only_that_changes_nothing(self):
        err = refusal(m.describe_edit, {"maker": "Etto", "story": "They are gluten-free."}, owner_text="update Etto")
        self.assertIn("gluten-free", err.reply)
        out = m.describe_edit({"maker": "Etto", "place": "Templeton, California", "story": "They are gluten-free."}, ctx(owner_text="Etto is in Templeton"))
        self.assertEqual(out.ops[0]["args"], {"key": "Etto", "place": "Templeton, California"})
        self.assertIn("gluten-free", out.left_off[0])
        kept = m.describe_edit({"maker": "Etto", "story": "They are gluten-free."}, ctx(owner_text="update Etto: they are gluten-free"))
        self.assertEqual(kept.ops[0]["args"]["story"], "Etto is gluten-free.")

    def test_old_claims_in_a_kept_story_are_not_asked_about_again(self):
        old = CONTENT.makers["Etto"]["story"]
        out = m.describe_edit({"maker": "Etto", "story": old + " All their durum is American grown."}, ctx(owner_text="add a line to the Etto story: all their durum is American grown"))
        self.assertEqual(out.left_off, ())
        self.assertTrue(out.ops[0]["args"]["story"].endswith("American grown."))


class HideAMaker(unittest.TestCase):
    def test_a_maker_with_products_asks_once_and_names_how_many(self):
        err = refusal(m.describe_hide, {"maker": "Etto"})
        self.assertEqual((err.kind, err.reply), ("question", "Do you want me to hide their 5 products too?"))
        one = refusal(m.describe_hide, {"maker": "Big Sur Honey Company"})
        self.assertEqual(one.reply, "Do you want me to hide their one product too?")

    def test_keeping_the_products_is_refused_naming_them(self):
        err = refusal(m.describe_hide, {"maker": "Etto", "with_products": False})
        self.assertIn("I can't hide Etto and leave their products on the site: Artisan short-cut pasta", err.reply)
        self.assertIn("and 16 more", refusal(m.describe_hide, {"maker": "Cal Poly", "with_products": False}).reply)

    def test_with_the_products(self):
        out = m.describe_hide({"maker": "Etto", "with_products": True}, ctx())
        self.assertEqual(out.ops, [{"op": "maker.hide", "args": {"key": "Etto", "withProducts": True}}])
        self.assertIn("This hides Artisan short-cut pasta", out.notes[0])

    def test_a_maker_with_no_active_products_needs_no_question(self):
        content = with_hidden("Etto")
        content.makers["Etto"].pop("hidden")  # visible maker, every product hidden
        self.assertEqual(m.plan_hide({"maker": "Etto"}, ctx(content)), [{"op": "maker.hide", "args": {"key": "Etto"}}])
        self.assertEqual(m.plan_hide({"maker": "Etto", "with_products": True}, ctx(content))[0]["args"], {"key": "Etto", "withProducts": True})

    def test_already_hidden_and_unknown(self):
        self.assertIn("hidden. Do you want me to bring them back first?", refusal(m.describe_hide, {"maker": "Etto"}, content=with_hidden("Etto")).reply)
        self.assertEqual(refusal(m.describe_hide, {"maker": "Acme"}).reply, "I don't know a maker called Acme. Who is it?")

    def test_the_maker_alone_without_the_content(self):
        self.assertEqual(m.plan_hide({"maker": "Etto"}, SimpleNamespace(today="2026-11-08")), [{"op": "maker.hide", "args": {"key": "Etto"}}])


class RestoreAMaker(SkillCase):
    """The first five tests call the plan directly; the real_dispatch ones go through the production maker.restore
    declaration, the real slot resolver, Conversation and Editor (the shared kit's Scratch skips the slot resolver)."""
    SKILLS = (BY_NAME["maker.restore"],)

    def test_a_hidden_maker_comes_back_and_their_products_stay_hidden(self):
        content = with_hidden("Etto")
        out = m.describe_restore({"maker": "etto"}, ctx(content))
        self.assertEqual(out.ops, [{"op": "maker.restore", "args": {"key": "Etto"}}])
        self.assertIn("Their products stay hidden until you bring them back: Artisan short-cut pasta", out.notes[0])

    def test_a_maker_that_is_not_hidden_is_said_to_be_on_the_site(self):
        self.assertEqual(refusal(m.describe_restore, {"maker": "Etto"}).reply, "Etto is already on the site.")

    def test_unknown_lists_close_names_or_asks(self):
        content = with_hidden("Etto")
        self.assertEqual(refusal(m.describe_restore, {"maker": "Acme"}, content=content).reply, "I don't know a maker called Acme. Who is it?")
        self.assertIn("Do you mean Etto", refusal(m.describe_restore, {"maker": "Eto"}, content=content).reply)

    def test_two_hidden_makers_fit_one_question(self):
        content = with_hidden("Cal Poly", "Cayucos")
        err = refusal(m.describe_restore, {"maker": "ca"}, content=content)
        self.assertEqual(err.reply, "Which maker do you mean: Cal Poly or Cayucos?")

    def test_the_restore_is_drafted_approved_and_undone_through_the_real_conversation(self):
        scratch = testkit.Scratch({"Etto is back": {"skill": "maker.restore", "slots": {"maker": "Etto"}}, "undo": {"unsupported": "x"}}, BY_NAME)
        try:
            hide = scratch.editor.prepare([{"op": "maker.hide", "args": {"key": "Etto", "withProducts": True}}])["draft"]
            self.assertEqual(scratch.editor.apply(hide["change_id"], hide["draft_hash"])["result"], "applied")
            base = scratch.head()
            restore = scratch.editor.prepare(m.plan_restore({"maker": "Etto"}, scratch._ctx()))
            self.assertEqual(live_policy.check(restore["draft"]), ["not live: maker.restore"], "restoring a maker stays private (G 2026-11-08: only the about text is live)")
            disposition, out = scratch.say("Etto is back")
            self.assertEqual(disposition, "proposed", out)
            self.assertEqual(testkit.plain_words_problems("\n".join(out)), [])
            code = scratch.drafts()[-1]["code"]
            scratch.say(f"yes {code}")
            files, diff = testkit.tree_diff(scratch.wt, base)
            self.assertEqual([(e["file"], e["path"], e.get("before"), e.get("after")) for e in diff], [("hass/content/makers.json", "makers.Etto.hidden", True, None)])
            self.assertIn("hass/content/makers.json", files)
            disposition, out = scratch.say("undo")
            scratch.say(f"yes {scratch.drafts()[-1]['code']}")
            _files, back = testkit.tree_diff(scratch.wt, base)
            self.assertEqual(back, [], "undo brings the maker back to hidden exactly as before")
        finally:
            scratch.close()

    # -- the production dispatcher: the slot kind decides whether the hidden-aware handler is ever reached ----------
    def _hide(self, *keys):
        for key in keys:
            draft = self.editor.prepare([{"op": "maker.hide", "args": {"key": key, "withProducts": True}}])["draft"]
            self.assertEqual(self.editor.apply(draft["change_id"], draft["draft_hash"])["result"], "applied")
        self.base = self.count()

    def _asks(self, skill, slots, text="restore request"):
        self.script(text, {"skill": skill, "slots": slots})
        disposition = self.say(text)
        return disposition, self.replies()

    def _read(self, name):
        return (self.repo.wt / "hass" / "content" / name).read_text("utf-8")

    def test_real_dispatch_restores_hidden_maker_by_key_or_name(self):
        self._hide("Etto")
        for said in ("Etto", "etto", "Ett"):
            with self.subTest(said=said):
                disposition, out = self._asks("maker.restore", {"maker": said}, f"bring back {said}")
                self.assertEqual(disposition, "proposed", out)
                self.assertEqual(json.loads(self.drafts()[-1]["ops_json"]), [{"op": "maker.restore", "args": {"key": "Etto"}}])
                self.nothing_written()
        self.assertEqual(self.registry.skills["maker.restore"].slots[0].kind, "text")

    def test_real_dispatch_restore_approval_and_undo_preserve_products(self):
        self._hide("Etto")
        before_products, before_head = self._read("products.json"), self.repo.head()
        held = [p["id"] for p in json.loads(before_products)["products"] if p.get("status") == "held"]
        self.assertTrue(held, "the real held products are the held-product control")
        self.assertEqual(self._asks("maker.restore", {"maker": "Etto"})[0], "proposed")
        draft = self.drafts()[-1]
        self.assertEqual(live_policy.check(self.editor.prepare(json.loads(draft["ops_json"]))["draft"]), ["not live: maker.restore"], "restoring a maker stays private")
        self.nothing_written()
        self.assertEqual(self.say(f"yes {draft['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        _files, diff = testkit.tree_diff(self.repo.wt, before_head)
        self.assertEqual([(e["file"], e["path"], e.get("before"), e.get("after")) for e in diff], [("hass/content/makers.json", "makers.Etto.hidden", True, None)])
        self.assertEqual(self._read("products.json"), before_products, "no product comes back with the maker: hidden stay hidden, held stay held")
        self.say("undo")
        self.say(f"yes {self.drafts()[-1]['code']}")
        self.assertEqual(testkit.tree_diff(self.repo.wt, before_head)[1], [], "undo hides the maker again exactly as before")

    def test_real_dispatch_restore_refusals_are_not_visibility_loops(self):
        self._hide("Cal Poly", "Cayucos")
        cases = (("visible", {"maker": "Stepladder"}, "refused", "Stepladder is already on the site."),
                 ("unknown", {"maker": "Acme"}, "question", "I don't know a maker called Acme. Who is it?"),
                 ("blank", {"maker": "  "}, "question", None), ("malformed", {"maker": ["Cal Poly"]}, "question", None),
                 ("ambiguous", {"maker": "ca"}, "question", "Which maker do you mean: Cal Poly or Cayucos?"))
        for label, slots, expected, reply in cases:
            with self.subTest(label):
                disposition, out = self._asks("maker.restore", slots, f"restore {label}")
                self.assertEqual(disposition, expected, out)
                self.assertEqual(len(out), 1)
                if reply: self.assertEqual(out[0], reply)
                self.assertNotIn("back first", out[0])
                self.assertEqual(self.drafts(), [])
                self.nothing_written()
        disposition, out = self._asks("maker.restore", {"maker": "Cayucos"}, "bring back Cayucos")  # the complete corrected request
        self.assertEqual(disposition, "proposed", out)
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"]), [{"op": "maker.restore", "args": {"key": "Cayucos"}}])
        self.nothing_written()

    def test_restore_declaration_does_not_relax_other_maker_slots(self):
        self.assertEqual([BY_NAME[n].slots[0].kind for n in ("maker.restore", "maker.edit", "maker.hide")], ["text", "maker_ref", "maker_ref"])
        self._hide("Etto")
        for skill, slots in (("maker.edit", {"maker": "Etto", "story": "Etto makes pasta."}), ("maker.hide", {"maker": "Etto"})):
            with self.subTest(skill):
                self.registry = registry_of(BY_NAME[skill])
                self.conv = self.open()
                disposition, out = self._asks(skill, slots, f"{skill} Etto")
                self.assertEqual((disposition, out), ("refused", ["Etto is hidden. Do you want me to bring them back first?"]))
                self.assertEqual(self.drafts(), [])
                self.nothing_written()
        self.registry = registry_of(BY_NAME["maker.edit"])  # ordinary maker_ref resolution of a visible maker is unchanged
        self.conv = self.open()
        disposition, out = self._asks("maker.edit", {"maker": "Stepladder", "name": "Stepladder Farm"}, "rename Stepladder to Stepladder Farm")
        self.assertEqual(disposition, "proposed", out)
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"])[0]["args"]["key"], "Stepladder")


class PlainWords(unittest.TestCase):
    def test_every_reply_for_every_current_maker_passes_the_voice_rules(self):
        replies = []
        for key, maker in CONTENT.makers.items():
            name = maker["name"]
            for fn, slots in ((m.describe_edit, {"maker": key, "name": name}), (m.describe_hide, {"maker": key}),
                              (m.describe_hide, {"maker": key, "with_products": False}), (m.describe_restore, {"maker": key}),
                              (m.describe_add, {"name": name, "place": "Somewhere"}), (m.describe_edit, {"maker": key}),
                              (m.describe_edit, {"maker": key, "clear_url": True})):
                try:
                    out = fn(slots, ctx())
                    replies += list(out.notes) + list(out.set_lines) + list(out.left_off)
                except m.Refusal as exc:
                    replies.append(exc.reply)
            out = m.describe_hide({"maker": key, "with_products": True}, ctx())
            replies += list(out.notes)
        self.assertGreater(len(replies), 150)
        for reply in replies:
            with self.subTest(reply=reply[:70]):
                self.assertEqual(voice.check(reply, long_ok=True), [])
                self.assertEqual(testkit.plain_words_problems(reply), [])

    def test_no_reply_shows_an_id_or_an_operation_name(self):
        err = refusal(m.describe_hide, {"maker": "Etto", "with_products": False})
        self.assertNotRegex(err.reply, r"photo-product|maker\.|\bkey\b|withProducts|with_products")


class PlansArePure(unittest.TestCase):
    def test_a_plan_changes_nothing_it_is_given_and_answers_the_same_twice(self):
        slots = {"name": "Bee Happy Farm", "place": "Atascadero, California", "story": "They keep bees.", "url": "beehappyfarm.com"}
        before = copy.deepcopy(slots)
        one, two = m.plan_add(slots, ctx()), m.plan_add(slots, ctx())
        self.assertEqual((one, slots), (two, before))

    def test_every_plan_returns_only_registered_ops(self):
        registry = load_registry()
        for ops in (m.plan_add({"name": "B", "place": "P, California"}, ctx()), m.plan_edit({"maker": "Etto", "story": "S."}, ctx()),
                    m.plan_hide({"maker": "Etto", "with_products": True}, ctx()), m.plan_restore({"maker": "Etto"}, SimpleNamespace(today="x"))):
            for op in ops:
                self.assertIn(op["op"], registry)


class CaseFiles(unittest.TestCase):
    def test_the_cases_files_name_their_own_skill_and_parse(self):
        for skill in m.SKILLS:
            path = REPO_ROOT / skill.cases
            self.assertTrue(path.is_file(), path)
            rows = testkit.load_rows(path)
            names = {c.get("skill") for r in rows for c in ([x for x in r.get("replies", []) if isinstance(x, dict)] + [y for x in r.get("replies", []) if isinstance(x, dict) for y in x.get("calls", [])])}
            self.assertEqual(names - {None}, {skill.name})


# -- town-state (ITEM-STANDARD section 5, SKILLS-MAKERS-2) ---------------------------------------------------------
TOWN_Q, MISSING = "Which town are they in?", "Still missing: the town"
REGION_MAKERS = ("Straus", "Alle-Pia", "Corberosa", "Massa Organics", "Sierra Nevada", "Ava\u2019s")  # the six saved regions
ORCHARD = {"name": "Synthetic Orchard", "place": "Central Coast"}
FALLBACK_SET = "I set: the about text to \u201cSynthetic Orchard is based in Central Coast.\u201d, because you didn't give one."


def said(*texts):
    return ctx(texts=list(texts))


def asks_town(test, fn, slots, c):
    with test.assertRaises(m.Refusal) as caught:
        fn(slots, c)
    test.assertEqual((caught.exception.kind, caught.exception.reply), ("question", TOWN_Q), slots)


class TownState(unittest.TestCase):
    def test_town_state_calls_shared_checker(self):
        with mock.patch.object(m.itemstd, "check_maker", wraps=itemstd.check_maker) as spy:
            m.describe_add({"name": "Bee Happy Farm", "place": "Atascadero, California"}, ctx())
        self.assertEqual(spy.call_args.args[0]["place"], "Atascadero, California")
        # only producer_town in the checker's answer decides; its other gaps (no story, no website) never block or ask
        gaps = {"missing": ["story", "website"], "needs_a_look": []}
        with mock.patch.object(m.itemstd, "check_maker", return_value=gaps):
            self.assertEqual(m.plan_add(ORCHARD, ctx())[0]["args"]["place"], "Central Coast")
        with mock.patch.object(m.itemstd, "check_maker", return_value={"missing": ["producer_town"], "needs_a_look": []}):
            asks_town(self, m.describe_add, {"name": "Bee Happy Farm", "place": "Atascadero, California"}, ctx())
        self.assertEqual(m.RULES["town-state"], m.rule_town_state)
        self.assertEqual([s.name for s in m.SKILLS if "town-state" in s.rules], ["maker.add", "maker.edit"])

    def test_region_add_and_explicit_region_edit_ask_without_draft(self):
        for place in ("Central Coast", "Northern California", "Central Coast, California", "California\u2019s Central Coast",
                      "Near Chico, California", "Atascadero"):
            with self.subTest(place=place):
                asks_town(self, m.describe_add, {"name": "Synthetic Orchard", "place": place}, ctx())
                asks_town(self, m.describe_edit, {"maker": "Etto", "place": place}, ctx())
                self.assertEqual(m.notes("maker.add", {"name": "Synthetic Orchard", "place": place}, ctx()), {"say": [], "set": [], "warn": []})
        asks_town(self, m.describe_edit, {"maker": "Straus", "place": "Northern California"}, ctx())  # the same saved region still asks
        asks_town(self, m.describe_edit, {"maker": "Straus", "place": "Northern California", "story": "They make milk."}, ctx())
        for place in ("Paso Robles, California", "Paso Robels, Califronia", "  Paso   Robels,  Califronia "):  # used as given
            with self.subTest(place=place):
                out = m.describe_add({"name": "Synthetic Orchard", "place": place}, ctx())
                typed = " ".join(place.split())
                self.assertEqual(out.ops[0]["args"]["place"], typed)
                self.assertEqual(out.ops[0]["args"]["story"], f"Synthetic Orchard is based in {typed}.")  # D5 unchanged
                self.assertNotIn(MISSING, out.notes)
                self.assertEqual(m.describe_edit({"maker": "Linn", "place": place}, ctx()).ops[0]["args"], {"key": "Linn's", "place": typed})

    def test_unknown_keeps_region_and_says_still_missing(self):
        for latest in ("I don't know the town", "i don\u2019t know the town.", "I DON'T KNOW THE TOWN!",
                       "add Synthetic Orchard in Central Coast. I don't know the town",
                       "I don't know the town?", "I don't know the town?!", "I don\u2019t know the town...?",
                       "add Synthetic Orchard in Central Coast I don't know the town",
                       "add Synthetic Orchard in Central Coast I don't know the town?"):
            with self.subTest(latest=latest):
                c = said("add Synthetic Orchard in Central Coast", latest)
                out = m.describe_add(dict(ORCHARD), c)
                self.assertEqual(out.ops, [{"op": "maker.add", "args": {"key": "Synthetic Orchard", "name": "Synthetic Orchard", "place": "Central Coast",
                                                                       "story": "Synthetic Orchard is based in Central Coast."}}])
                self.assertEqual(out.notes.count(MISSING), 1)
                self.assertEqual(m.notes("maker.add", dict(ORCHARD), c), {"say": [MISSING], "set": [FALLBACK_SET], "warn": []})
                edit = m.describe_edit({"maker": "Etto", "place": "Northern California"}, c)
                self.assertEqual((edit.ops[0]["args"], edit.notes.count(MISSING)), ({"key": "Etto", "place": "Northern California"}, 1))
                self.assertEqual(m.notes("maker.edit", {"maker": "Etto", "place": "Northern California"}, c)["say"], [MISSING])
        fallback = ctx(owner_text="add Synthetic Orchard in Central Coast. I don't know the town")  # no texts: direct helper calls
        self.assertIn(MISSING, m.describe_add(dict(ORCHARD), fallback).notes)
        for line in (TOWN_Q, MISSING):
            self.assertEqual(voice.check(line), [], line)
            self.assertEqual(testkit.plain_words_problems(line), [], line)

    def test_unknown_is_not_inferred_or_saved_as_place(self):
        decline = "I don't know the town"
        for label, slots, c in (
                ("no context", ORCHARD, None), ("no texts", ORCHARD, ctx()), ("empty texts", ORCHARD, said()),
                ("decline used as the place", {"name": "Synthetic Orchard", "place": decline}, said("add Synthetic Orchard", decline)),
                ("phrase in the story", {**ORCHARD, "story": "I don't know the town."}, said("add Synthetic Orchard in Central Coast")),
                ("an older message", ORCHARD, said(decline, "add Synthetic Orchard in Central Coast")),
                ("not his last words", ORCHARD, said("I don't know the town but it is near Paso")),
                ("someone else's words", ORCHARD, said("Hawaii don't know the town")),
                ("a question about it", ORCHARD, said("Do you know the town?")),
                ("texts win over owner_text", ORCHARD, ctx(texts=["add it"], owner_text=decline)),
                ("a bare town is not a region", {"name": "Synthetic Orchard", "place": "Templeton"}, said(decline))):
            with self.subTest(label):
                asks_town(self, m.describe_add, dict(slots), c)
                self.assertEqual(m.notes("maker.add", dict(slots), c), {"say": [], "set": [], "warn": []})
        self.assertFalse(m.said_unknown_town(SimpleNamespace(texts=[None])))
        c = said("add Synthetic Orchard", decline)
        out = m.describe_add({"name": "Synthetic Orchard", "place": "Cambria, California"}, c)  # a town after all: no marker
        self.assertEqual((out.ops[0]["args"]["place"], MISSING in out.notes), ("Cambria, California", False))
        self.assertEqual(refusal(m.describe_add, {"name": "x", "place": "Central Coast $3"}, texts=[decline]).reply, m.PRICE_REPLY)
        self.assertEqual(refusal(m.describe_add, {**ORCHARD, "story": "Plums, $3 a bag."}, texts=[decline]).reply, m.PRICE_REPLY)
        self.assertIn("longer than", refusal(m.describe_add, {**ORCHARD, "story": "A " * 400}, texts=[decline]).reply)
        err = refusal(m.describe_edit, {"maker": "Straus", "place": "Northern California"}, texts=[decline])  # nothing would change
        self.assertIn("already says that", err.reply)
        self.assertEqual(m.notes("maker.edit", {"maker": "Straus", "place": "Northern California"}, c)["say"], [])
        self.assertEqual(m.notes("maker.hide", {"maker": "Etto", "with_products": True}, c), {"say": [], "set": [], "warn": []})

    def test_story_only_edit_does_not_reask_saved_region(self):
        before = copy.deepcopy(CONTENT.makers)
        regions = [k for k, rec in CONTENT.makers.items() if "place_is_a_region" in itemstd.check_maker(rec)["needs_a_look"]]
        self.assertEqual(sorted(regions), sorted(REGION_MAKERS))
        for key in REGION_MAKERS:
            with self.subTest(key=key):
                out = m.describe_edit({"maker": key, "story": "They make good food."}, ctx())
                self.assertEqual(out.ops[0]["args"], {"key": key, "story": f"{CONTENT.makers[key]['name']} makes good food."})
                self.assertNotIn(MISSING, out.notes)
                self.assertEqual(m.notes("maker.edit", {"maker": key, "story": "They make good food."}, ctx())["say"], [])
                self.assertNotIn("place", m.plan_edit({"maker": key, "name": "Renamed Maker"}, ctx())[0]["args"])
        self.assertEqual(CONTENT.makers, before, "planning changes no saved maker")


class TownStateDispatch(SkillCase):
    """The production maker.add / maker.edit declarations through the real dispatcher, Conversation and Editor."""
    SKILLS = (BY_NAME["maker.add"], BY_NAME["maker.edit"])

    def turn(self, text, skill, slots):
        self.script(text, {"skill": skill, "slots": slots})
        return self.say(text), self.replies()

    def asks(self, text, skill, slots):
        disposition, out = self.turn(text, skill, slots)
        self.assertEqual((disposition, out), ("question", [TOWN_Q]))
        self.assertEqual(self.drafts(), [])
        self.nothing_written()

    def proposed(self, text, skill, slots, ops):
        disposition, out = self.turn(text, skill, slots)
        self.assertEqual(disposition, "proposed", out)
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"]), ops)
        self.nothing_written()
        return "\n".join(out)

    def test_real_dispatch_region_then_town_continues_same_maker(self):
        self.asks("add Synthetic Orchard in Central Coast, they grow plums", "maker.add",
                   {"name": "Synthetic Orchard", "place": "Central Coast", "story": "They grow plums."})
        self.assertEqual(self.live()["question"], TOWN_Q)
        before = self.repo.head()
        products = (self.repo.wt / "hass" / "content" / "products.json").read_text("utf-8")
        reply = self.proposed("Paso Robels, California", "maker.add", {"place": "Paso Robels, California"},
                              [{"op": "maker.add", "args": {"key": "Synthetic Orchard", "name": "Synthetic Orchard",
                                                            "place": "Paso Robels, California", "story": "Synthetic Orchard grows plums."}}])
        self.assertNotIn(MISSING, reply)
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(self.commits(), 1)
        self.assertEqual(json.loads((self.repo.wt / "hass" / "content" / "makers.json").read_text("utf-8"))["makers"]["Synthetic Orchard"]["place"],
                         "Paso Robels, California")
        self.say("undo")
        self.say(f"yes {self.drafts()[-1]['code']}")
        _files, residue = testkit.tree_diff(self.repo.wt, before)
        self.assertTrue(residue and all(e["path"].startswith("makers.Synthetic Orchard") for e in residue), residue)  # declared add residue
        self.assertEqual((self.repo.wt / "hass" / "content" / "products.json").read_text("utf-8"), products)

    def test_real_dispatch_region_edit_then_town(self):
        self.asks("Etto is in Northern California", "maker.edit", {"maker": "Etto", "place": "Northern California"})
        self.proposed("Templeton, California", "maker.edit", {"place": "Templeton, California"},
                      [{"op": "maker.edit", "args": {"key": "Etto", "place": "Templeton, California"}}])

    def test_real_dispatch_unknown_keeps_region_and_shows_marker(self):
        self.asks("add Synthetic Orchard in Central Coast", "maker.add", dict(ORCHARD))
        self.asks("Central Coast is all I have", "maker.add", {})  # anything but his own "I don't know the town" asks again
        reply = self.proposed("I don\u2019t know the town.", "maker.add", {},
                              [{"op": "maker.add", "args": {"key": "Synthetic Orchard", "name": "Synthetic Orchard", "place": "Central Coast",
                                                            "story": "Synthetic Orchard is based in Central Coast."}}])
        self.assertEqual(reply.count(MISSING), 1)
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(self.commits(), 1)

    def test_real_dispatch_unknown_on_edit_and_in_the_first_message(self):
        self.asks("Etto is in Northern California", "maker.edit", {"maker": "Etto", "place": "Northern California"})
        reply = self.proposed("I don't know the town", "maker.edit", {},
                              [{"op": "maker.edit", "args": {"key": "Etto", "place": "Northern California"}}])
        self.assertEqual(reply.count(MISSING), 1)
        self.say("no")
        reply = self.proposed("add Synthetic Orchard in Central Coast. I don't know the town", "maker.add", dict(ORCHARD),
                              [{"op": "maker.add", "args": {"key": "Synthetic Orchard", "name": "Synthetic Orchard", "place": "Central Coast",
                                                            "story": "Synthetic Orchard is based in Central Coast."}}])
        self.assertEqual(reply.count(MISSING), 1)

    def test_real_dispatch_decline_is_never_saved_as_the_place(self):
        self.asks("add Synthetic Orchard in Central Coast", "maker.add", dict(ORCHARD))
        disposition, out = self.turn("I don't know the town", "maker.add", {"place": "I don't know the town"})
        self.assertEqual(disposition, "question", out)  # the dispatcher's own slot check asks again (town and state)
        self.assertEqual(len(out), 1)
        self.assertIn(out[0], (TOWN_Q, "Where are they based (town and state)?"))
        self.assertEqual(self.drafts(), [])
        self.nothing_written()


class FallbackStoryDisclosure(SkillCase):
    """A maker with no story: the proposal says the based-in line was Hass's choice, once, before the owner's yes."""
    SKILLS = (BY_NAME["maker.add"], BY_NAME["maker.edit"], BY_NAME["maker.hide"], BY_NAME["maker.restore"])
    BEE = {"name": "Bee Happy Farm", "place": "Atascadero, California"}
    BEE_SET = "I set: the about text to \u201cBee Happy Farm is based in Atascadero, California.\u201d, because you didn't give one."

    def propose_reply(self, text, mapping):
        self.script(text, mapping)
        self.assertEqual(self.say(text), "proposed")
        [reply] = self.replies()
        return reply

    def test_fallback_story_notes_disclose_exact_generated_value(self):
        for story in (None, "", "   "):
            with self.subTest(story=story):
                slots = {**self.BEE, **({} if story is None else {"story": story})}
                out = m.describe_add(dict(slots), ctx())
                got = m.notes("maker.add", slots, ctx())
                self.assertEqual(got, {"say": [], "set": [self.BEE_SET], "warn": []})
                self.assertEqual(out.ops[0]["args"]["story"], "Bee Happy Farm is based in Atascadero, California.")
                self.assertIn(out.ops[0]["args"]["story"], got["set"][0])
                self.assertEqual(voice.check(got["set"][0], long_ok=True), [])
        before = copy.deepcopy(CONTENT.makers)
        m.notes("maker.add", dict(self.BEE), ctx())
        self.assertEqual(CONTENT.makers, before)
        supplied = m.notes("maker.add", {**self.BEE, "story": "They keep bees on the hill."}, ctx())
        self.assertEqual(supplied, {"say": [], "set": [], "warn": []})

    def test_unknown_town_marker_and_story_disclosure_coexist(self):
        c = said("add Synthetic Orchard in Central Coast", "I don't know the town")
        self.assertEqual(m.notes("maker.add", dict(ORCHARD), c), {"say": [MISSING], "set": [FALLBACK_SET], "warn": []})
        for slots in ({"name": "Synthetic Orchard", "place": "Central Coast"}, {"name": "Synthetic Orchard"}, {"place": "Central Coast"},
                      {"name": "Synthetic Orchard", "place": "Central Coast", "story": "A $3 jar."}):
            with self.subTest(slots=slots):  # a plan that stops (a region not declined, a missing slot, a price) has no draft to note
                self.assertEqual(m.notes("maker.add", dict(slots), ctx()), {"say": [], "set": [], "warn": []})

    def test_production_add_discloses_default_before_yes(self):
        reply = self.propose_reply("add Bee Happy Farm in Atascadero, California", {"skill": "maker.add", "slots": dict(self.BEE)})
        self.assertEqual(reply.count(self.BEE_SET), 1)
        self.assertLess(reply.index(self.BEE_SET), reply.lower().index("reply yes"))
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"]), [{"op": "maker.add", "args": {
            "key": "Bee Happy Farm", "name": "Bee Happy Farm", "place": "Atascadero, California",
            "story": "Bee Happy Farm is based in Atascadero, California."}}])
        self.nothing_written()
        self.say("no")
        self.replies()
        again = self.propose_reply("add Bee Happy Farm in Atascadero, California again", {"calls": [{"skill": "maker.add", "slots": dict(self.BEE)}], "revises": None})
        self.assertEqual(again.count(self.BEE_SET), 1)
        self.assertLess(again.index(self.BEE_SET), again.lower().index("reply yes"))
        self.assertEqual(json.loads(self.drafts()[-1]["ops_json"])[0]["args"]["story"], "Bee Happy Farm is based in Atascadero, California.")
        self.assertEqual(self.say(f"yes {self.drafts()[-1]['code']}"), "approved")
        self.assertEqual(self.commits(), 1)

    def test_continued_maker_discloses_only_after_place_answer(self):
        self.script("add Bee Happy Farm", {"skill": "maker.add", "slots": {"name": "Bee Happy Farm"}})
        self.assertEqual(self.say("add Bee Happy Farm"), "question")
        [asked] = self.replies()
        self.assertNotIn("I set", asked)
        self.assertEqual(self.drafts(), [])
        reply = self.propose_reply("Atascadero, California", {"skill": "maker.add", "slots": {"place": "Atascadero, California"}})
        self.assertEqual(reply.count(self.BEE_SET), 1)
        self.say("no")
        self.replies()
        self.script("add Bee Happy Farm. They keep bees", {"skill": "maker.add", "slots": {"name": "Bee Happy Farm"}})
        self.assertEqual(self.say("add Bee Happy Farm. They keep bees"), "question")
        self.replies()
        reply = self.propose_reply("Atascadero, California", {"skill": "maker.add", "slots": {"place": "Atascadero, California", "story": "They keep bees."}})
        self.assertNotIn("I set", reply)
        self.assertNotIn("because you didn't give one", reply)
        self.assertIn("Bee Happy Farm keeps bees.", reply)

    def test_edit_hide_restore_and_refusals_keep_old_notes(self):
        c = said("Etto is in Northern California", "I don't know the town")
        self.assertEqual(m.notes("maker.edit", {"maker": "Etto", "place": "Northern California"}, c), {"say": [MISSING], "set": [], "warn": []})
        self.assertEqual(m.notes("maker.edit", {"maker": "Etto", "story": "They roast."}, ctx()), {"say": [], "set": [], "warn": []})
        self.assertEqual(m.notes("maker.hide", {"maker": "Etto"}, ctx()), {"say": [], "set": [], "warn": []})
        self.assertEqual(m.notes("maker.restore", {"maker": "Etto"}, ctx()), {"say": [], "set": [], "warn": []})
        twin = m.notes("maker.add", {"name": "Etto", "place": "Atascadero, California"}, ctx())  # already on the site: a question, no draft
        self.assertEqual(twin, {"say": [], "set": [], "warn": []})
        self.script("add Etto in Atascadero", {"skill": "maker.add", "slots": {"name": "Etto", "place": "Atascadero, California"}})
        self.assertEqual(self.say("add Etto in Atascadero"), "question")
        [reply] = self.replies()
        self.assertNotIn("I set", reply)
        self.assertEqual([d for d in self.drafts() if d["state"] == "proposed"], [])
        self.nothing_written()


class TownCaseRows(unittest.TestCase):
    def test_town_case_rows_and_strict_voice(self):
        rows = {name: testkit.load_rows(CASES / f"{name}.jsonl") for name in ("maker.add", "maker.edit")}
        town = {name: [r for r in got if r["id"].startswith(("town-", "plan-town-"))] for name, got in rows.items()}
        self.assertGreaterEqual(min(len(v) for v in town.values()), 5)
        self.assertGreaterEqual(sum(len(v) for v in town.values()), 10)
        said_lines = json.dumps(town)
        for line in (TOWN_Q, MISSING):
            self.assertIn(line, said_lines)
            self.assertEqual(voice.check(line), [], line)


if __name__ == "__main__":
    unittest.main()

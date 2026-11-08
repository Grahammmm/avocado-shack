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

from hass import live_policy, skills, voice
from hass.content_model import REPO_ROOT, TEXT_LIMITS, load_and_validate
from hass.ops import load_registry
from hass.skills import makers as m
from hass.skills import testkit

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
            self.assertFalse(blocked(m.plan_hide({"maker": "Etto", "with_products": True}, ctx())))
        finally:
            scratch.close()
        self.assertEqual({s.name: s.live_class for s in m.SKILLS},
                         {"maker.add": "private-only", "maker.edit": "private-only", "maker.hide": "chat-live", "maker.restore": "chat-live"})

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
        add = lambda url: m.describe_add({"name": "Bee Happy Farm", "place": "Atascadero", "url": url}, ctx()).ops[0]["args"].get("url")
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


class RestoreAMaker(unittest.TestCase):
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
            self.assertEqual(live_policy.check(restore["draft"]), [], "restoring a maker is allowed from the chat when live")
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
        for ops in (m.plan_add({"name": "B", "place": "P"}, ctx()), m.plan_edit({"maker": "Etto", "story": "S."}, ctx()),
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


if __name__ == "__main__":
    unittest.main()

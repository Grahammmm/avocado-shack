"""RF1036-11: quoted page copy equal to a supplied title/intro/paragraph is not a style or layout request."""
import copy
import json
import unittest

from hass.skills import acceptance_run, load_skills
from hass.skills.front import FRONT_BANNER, FRONT_FAQ, FRONT_PAGE, FRONT_SECTIONS, SKILLS, _StyleStop, plan_banner, plan_faq, plan_page, plan_sections
from hass.skills.shop import SkillStop
from hass.tests import test_skill_dispatch as dispatch_fixture

TITLE = "About the Shack"
PARA = "Our market welcomes neighbors every day."
STYLE_REFUSAL = "Colours, fonts, sizes and new kinds of parts can't be changed by message."


def slots_for(intro, title=TITLE, paragraphs=(PARA,), **more):
    return {"template": "about", "title": title, "intro": intro, "paragraphs": list(paragraphs), **more}


def say(slots, quote='"'):
    """The owner's message with the supplied fields in the given double quotes."""
    close = "\u201d" if quote == "\u201c" else quote
    return ("Fill the About template with title %s%s%s, intro %s%s%s, and paragraph %s%s%s."
            % (quote, slots["title"], close, quote, slots["intro"], close, quote, slots["paragraphs"][0], close))


def plan(slots, *texts):
    return plan_page(slots, {"texts": list(texts)})


class LiteralScanTests(unittest.TestCase):
    def test_literal_colour_and_font_words_plan_unchanged_page_text(self):
        for intro in ("We sell red onions.", "Look for the blue door.", "Ask about fonts at the shop.",
                      "Sizes run from small to large.", "Our layout is simple.", "We love html cakes.",
                      "Come say hello at the shop."):
            with self.subTest(intro=intro):
                slots = slots_for(intro)
                before = copy.deepcopy(slots)
                ops = plan(slots, say(slots))
                self.assertEqual(ops, [{"op": "store.set_page", "args": {"page": "about", "title": TITLE, "intro": intro, "paragraphs": [PARA]}}])
                self.assertEqual(slots, before)
        slots = slots_for("Come say hello.", title="Red door about", paragraphs=("Blue fonts are never used here.",))
        self.assertEqual(plan(slots, say(slots))[0]["args"]["paragraphs"], ["Blue fonts are never used here."])

    def test_ascii_and_curly_quotes_are_exact_and_balanced(self):
        slots = slots_for("We sell red onions.")
        self.assertTrue(plan(slots, say(slots, "\u201c")))
        self.assertTrue(plan(slots, say(slots, '"'), say(slots, "\u201c")))
        self.assertTrue(plan(slots, 'intro "We sell red onions." and again "We sell red onions."'))
        self.assertTrue(plan(slots, 'unrelated "hello there" then intro "We sell red onions."'))
        for label, text in (("unclosed", 'intro "We sell red onions.'),
                            ("mixed", 'intro "We sell red onions.\u201d'),
                            ("mixed2", 'intro \u201cWe sell red onions."'),
                            ("odd ascii count", 'intro "We sell red onions." for a 5" box'),
                            ("nested curly", 'intro \u201c\u201cWe sell red onions.\u201d'),
                            ("stray close", 'oops \u201d intro \u201cWe sell red onions.\u201d'),
                            ("no quotes", 'intro We sell red onions.')):
            with self.subTest(label=label), self.assertRaises(_StyleStop):
                plan(slots, text)
        quoted = slots_for('We sell "red" onions.')  # the value itself holds the delimiter: no span can equal it
        with self.assertRaises(_StyleStop):
            plan(quoted, 'intro "We sell "red" onions."')

    def test_style_request_outside_literal_still_refuses_and_logs(self):
        slots = slots_for("We sell red onions.")
        literal = '"We sell red onions."'
        for label, texts in (("blue after", (literal + " make the page blue",)),
                             ("font after", (literal + " and change its font",)),
                             ("layout after", (literal + " change layout",)),
                             ("earlier message", ("make it red", literal)),
                             ("later message", (literal, "bigger please")),
                             ("repeated red outside", (literal + " red",)),
                             ("html outside", ("html " + literal,))):
            with self.subTest(label=label):
                with self.assertRaises(_StyleStop) as caught:
                    plan(slots, *texts)
                self.assertEqual((str(caught.exception), caught.exception.backlog), (STYLE_REFUSAL, "other"))

    def test_quoted_instruction_without_matching_text_slot_is_not_hidden(self):
        for label, intro, text in (("unrelated quote", "Come say hello.", 'intro "Come say hello." and "make the page red"'),
                                   ("absent field", "Come say hello.", '"change the layout" for the About page'),
                                   ("changed value", "We sell red onions.", 'intro "We sell red onions, honest."'),
                                   ("substring of value", "We sell red onions.", '"We sell red onions" please'),
                                   ("case changed", "We sell red onions.", 'intro "we sell red onions."'),
                                   ("instruction returned as a slot", "make the page blue", 'make the page blue "About the Shack"')):
            with self.subTest(label=label), self.assertRaises(_StyleStop):
                plan(slots_for(intro), text)

    def test_literal_mask_never_bypasses_claims_markup_price_or_page_schema(self):
        def refused(slots, exc=SkillStop):
            with self.assertRaises(exc) as caught:
                plan(slots, say(slots))
            self.assertNotIsInstance(caught.exception, _StyleStop)
            return str(caught.exception)

        for label, bad in (("markup", "<b>red</b> onions"), ("url", "Red onions at https://example.com"),
                           ("handle", "Blue door, find us @redshack"), ("price", "Red onions are $5 today"),
                           ("hidden", "Red onions\u200b today")):
            with self.subTest(label=label):
                self.assertTrue(refused(slots_for(bad)))
        with self.subTest(label="claim the owner did not say"):  # only the intro is quoted; the title's claim is the model's
            slots = slots_for("We sell red onions.", title="The best shack")
            with self.assertRaises(SkillStop) as caught:
                plan(slots, 'intro "We sell red onions."')
            self.assertNotIsInstance(caught.exception, _StyleStop)
            self.assertIn("best", str(caught.exception).lower())
        with self.subTest(label="claim in his own words"):
            slots = slots_for("We sell red onions.", title="The best shack")
            self.assertTrue(plan(slots, 'title "The best shack" intro "We sell red onions."'))
        with self.subTest(label="unsupported page"):
            self.assertTrue(refused({**slots_for("We sell red onions."), "template": "shop"}))
        with self.subTest(label="no paragraph"):
            self.assertTrue(refused(slots_for("We sell red onions.", paragraphs=("Hi.",))))
        with self.subTest(label="hide and words"):
            hide = slots_for("We sell red onions.", hide=True)
            with self.assertRaises(SkillStop) as caught:
                plan(hide, say(hide))
            self.assertNotIsInstance(caught.exception, _StyleStop)
            self.assertIn("Hide the page", str(caught.exception))

    def test_other_front_skills_and_registry_artifacts_remain_identical(self):
        quoted = '"Make the shop red."'
        with self.assertRaises(_StyleStop):
            plan_sections({"hide": ["newsletter"]}, {"texts": [quoted]})
        with self.assertRaises(_StyleStop):
            plan_sections({"hide": ["newsletter"]}, {"texts": ["make it blue"]})
        self.assertTrue(plan_banner({"text": "Come say hello", "end": "2026-11-12"}, {"today": "2026-11-09", "texts": ["Come say hello"]}))
        self.assertTrue(plan_faq({"question": "Is parking near?", "answer": "Yes, say hello."}, {"texts": ["Is parking near? Yes, say hello."]}))
        self.assertEqual([s.name for s in SKILLS], ["front.sections", "front.banner", "front.page", "front.faq"])
        for skill in (FRONT_SECTIONS, FRONT_BANNER, FRONT_PAGE, FRONT_FAQ):
            self.assertEqual((skill.version, skill.live_class), (1, "private-only"))
            self.assertIs(load_skills().skills[skill.name].plan, skill.plan)
        self.assertEqual([s.name for s in FRONT_PAGE.slots], ["template", "title", "intro", "paragraphs", "hide"])
        rows = [r["id"] for r in acceptance_run.load_rows(acceptance_run.DEFAULT_ROWS) if r.get("skill", "").startswith("front.")]
        self.assertEqual(len(rows), 4)
        for result in acceptance_run.run_rows(acceptance_run.DEFAULT_ROWS, only=rows):
            self.assertEqual((result.ok, result.codes), (True, []), result.id)


class LiteralDispatchTests(dispatch_fixture.SkillCase):
    SKILLS = tuple(load_skills().skills.values())

    def backlog(self):
        if not self.conv.db.execute("SELECT 1 FROM sqlite_master WHERE name = 'backlog'").fetchone():
            return []  # the table is created on the first row
        return self.conv.db.execute("SELECT reason FROM backlog").fetchall()

    def draft_for(self, intro):
        slots = slots_for(intro)
        text = say(slots)
        self.script(text, dispatch_fixture.skill_reply("front.page", **slots))
        self.assertEqual(self.say(text), "proposed", self.replies())
        self.assertEqual(self.backlog(), [])
        self.assertEqual(self.commits(), 0)
        [draft] = self.drafts()
        self.assertEqual(draft["state"], "proposed")
        self.assertEqual([(o["op"], o["args"]["intro"]) for o in json.loads(draft["ops_json"])], [("store.set_page", intro)])

    def test_real_dispatch_literal_copy_drafts_without_backlog_and_without_apply(self):
        self.draft_for("We sell red onions.")

    def test_real_dispatch_healthy_control_drafts_the_same_way(self):
        self.draft_for("Come say hello at the shop.")

    def test_real_dispatch_residual_style_request_is_still_written_down(self):
        slots = slots_for("We sell red onions.")
        text = say(slots) + " Also make the page blue."
        self.script(text, dispatch_fixture.skill_reply("front.page", **slots))
        self.assertEqual(self.say(text), "backlog")
        self.assertEqual(self.drafts(), [])
        self.assertEqual(self.commits(), 0)
        self.assertEqual(len(self.backlog()), 1)
        self.assertIn(STYLE_REFUSAL, " ".join(self.replies()))


if __name__ == "__main__":
    unittest.main()

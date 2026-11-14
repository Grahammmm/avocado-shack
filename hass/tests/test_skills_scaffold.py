"""AVB-20: the new-skill scaffolder (hass/skills/scaffold.py).

Proves the one command: it makes a skill, its 10 case rows, its doc page and its test; the lint (with the case-file
minima) is clean; every row passes on the scratch shop through the real kit; nothing is written when it cannot pass; it
never overwrites. The samples are written under a temporary folder, so no sample skill joins the live registry.
Run: python3 -B -m unittest hass.tests.test_skills_scaffold -v
"""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from hass import live_policy
from hass.content_model import REPO_ROOT
from hass.ops import load_registry
from hass.skills import load_skills, scaffold, skill_lint, testkit
from hass.skills.model import MIN_CASE_ROWS, MIN_REFUSAL_ROWS


def run(*argv):
    """(exit code, stdout, stderr) of the command line."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = scaffold.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Made(unittest.TestCase):
    """One scaffold run per archetype; the checks below read what it wrote."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.root = Path(cls.tmp.name)
        cls.runs = {}
        for key, argv in {
            "product": ("sample.tuck_away", "--op", "product.hide", "--label", "tuck a product out of sight"),
            "text": ("sample.reword", "--op", "product.edit", "--arg", "description", "--label", "reword a product"),
            "private_text": ("sample.rename", "--op", "product.edit", "--arg", "name", "--label", "rename a product"),
            "store": ("sample.new_intro", "--op", "store.set_intro", "--label", "change the home intro"),
        }.items():
            cls.runs[key] = (argv[0], run("new", *argv, "--root", str(cls.root)))

    def paths(self, name):
        module = name.replace(".", "_")
        return {"module": self.root / "hass" / "skills" / f"{module}.py",
                "cases": self.root / "hass" / "tests" / "fixtures" / "skills" / name.split(".")[0] / f"{name}.jsonl",
                "doc": self.root / "docs" / "hass" / "skills" / f"{module}.md",
                "test": self.root / "hass" / "tests" / f"test_skills_{module}.py"}

    def skill(self, name):
        [skill] = testkit.load_skill_module(self.paths(name)["module"])
        return skill

    def test_the_command_succeeds_and_writes_the_four_files(self):
        for key, (name, (code, out, err)) in self.runs.items():
            with self.subTest(key):
                self.assertEqual((code, err), (0, ""), out)
                self.assertIn("REVIEW before merge", out)
                for path in self.paths(name).values():
                    self.assertTrue(path.is_file(), path)

    def test_the_lint_is_clean_with_the_case_file_minima(self):
        for key, (name, _r) in self.runs.items():
            with self.subTest(key):
                self.assertEqual(skill_lint([self.skill(name)], load_registry(), repo_root=self.root), [])

    def test_ten_case_rows_two_refusals_one_undo_and_every_row_passes(self):
        for key, (name, _r) in self.runs.items():
            with self.subTest(key):
                rows = testkit.load_rows(self.paths(name)["cases"])
                cases = [r for r in rows if not r.get("plan")]
                self.assertEqual(len(cases), MIN_CASE_ROWS)
                self.assertGreaterEqual(sum(r["kind"] == "refuse" for r in cases), MIN_REFUSAL_ROWS)
                self.assertTrue(any(r.get("undo") is True for r in cases))
                self.assertEqual({r["version"] for r in rows}, {1})
                for result in testkit.run_file(self.paths(name)["cases"], (self.skill(name),)):
                    self.assertEqual(result.problems, [], result.id)

    def test_the_expected_diff_is_recorded_and_the_edits_cover_it(self):
        rows = testkit.load_rows(self.paths("sample.tuck_away")["cases"])
        first = next(r for r in rows if r["id"] == "s01-clean-1")
        self.assertEqual(first["expect"]["diff"], [{"file": "hass/content/products.json", "path": "products[photo-product-042].status",
                                                    "before": "active", "after": "hidden"}])
        self.assertEqual(first["expect"]["preview"], {"kind": "product", "id": "photo-product-042"})
        self.assertEqual(self.skill("sample.tuck_away").edits, (("hass/content/products.json", "products[id].status"),))
        self.assertEqual(self.skill("sample.new_intro").preview, "home")

    def test_the_live_class_is_read_off_the_live_table_not_assumed(self):
        """A label, not a lock: chat-live exactly when live_policy lists the op with every argument the skill sends."""
        want = {"sample.tuck_away": "chat-live",  # product.hide is in live_policy.LIVE with {id}
                "sample.reword": "chat-live",  # product.edit may carry description
                "sample.rename": "private-only",  # the same op may not carry name live
                "sample.new_intro": "private-only"}  # store.set_intro is a PRIVATE op
        for _key, (name, _r) in self.runs.items():
            skill = self.skill(name)
            with self.subTest(name):
                self.assertEqual((skill.live_class, skill.approval, skill.version), (want[name], "owner-yes", 1))
                module, doc = self.paths(name)["module"].read_text("utf-8"), self.paths(name)["doc"].read_text("utf-8")
                for text in (module, doc):
                    self.assertIn("not a lock", text)
                    self.assertNotIn("until its owner lists it", text)
                    self.assertNotIn("until the operator lists", text)
                self.assertIn(f"`live_class` is `{want[name]}`", doc)

    def test_capability_metadata_describes_the_generated_site_writer(self):
        for key, (name, _r) in self.runs.items():
            with self.subTest(key):
                skill = self.skill(name)
                self.assertEqual((skill.pack, skill.targets, skill.approval_class, skill.logs, skill.who),
                                 ("site", ("site",), "A1", ("subjects", "fields"), "owner"))
                self.assertEqual(skill.sandbox, "full" if key in ("product", "text") else "preview")

    def test_a_label_over_an_already_live_op_is_never_called_private_only(self):
        """The reviewer's case: product.hide is already live, so a generated hide skill must say so (live_policy gates drafts, not this label)."""
        self.assertIn("product.hide", live_policy.LIVE)
        self.assertEqual(scaffold.live_boundary("product.hide", True, {})[0], "chat-live")
        self.assertEqual(scaffold.live_boundary("product.edit", True, {"description": "description"})[0], "chat-live")
        self.assertEqual(scaffold.live_boundary("product.edit", True, {"name": "name"})[0], "private-only")  # name is never live
        self.assertEqual(scaffold.live_boundary("store.set_phone", False, {"phone": "phone"})[0], "private-only")
        self.assertEqual(scaffold.live_boundary("store.set_hours", False, {})[0], "private-only")
        self.assertEqual(scaffold.live_boundary("route.add", False, {})[0], "private-only")
        # and it agrees with the gate that does decide: a real draft of the sample's plan passes live_policy.check
        draft = {"ops": [{"op": "product.hide", "args": {"id": "photo-product-042"}}],
                 "records": [{"collection": "products", "before": {"status": "active"}, "after": {"status": "hidden"}}]}
        self.assertEqual(live_policy.check(draft), [])

    def test_a_text_slot_refuses_a_price_and_a_blank(self):
        skill = self.skill("sample.reword")
        item = "photo-product-042"
        for words, want in (("Only $9 today", "doesn't show prices"), ("  ", "What should the description be?")):
            with self.assertRaises(ValueError) as caught:
                skill.plan({"item": item, "description": words}, None)
            self.assertIn(want, getattr(caught.exception, "reply", ""))

    def test_doc_page_has_a_row_for_every_sentence_and_the_generated_test_runs(self):
        for _key, (name, _r) in self.runs.items():
            doc = self.paths(name)["doc"].read_text("utf-8")
            for row in testkit.load_rows(self.paths(name)["cases"]):
                if "texts" in row:
                    self.assertIn(row["texts"][-1], doc)
            self.assertIn("SCAFFOLD", doc)
            compile(self.paths(name)["test"].read_text("utf-8"), str(self.paths(name)["test"]), "exec")

    def test_a_second_run_never_overwrites(self):
        code, _out, err = run("new", "sample.tuck_away", "--op", "product.hide", "--label", "tuck away", "--root", str(self.root))
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    def test_the_sample_is_not_in_the_live_registry(self):
        self.assertNotIn("sample.tuck_away", load_skills().skills)


class Refuses(unittest.TestCase):
    """Requests the scaffolder turns down before it writes anything."""

    def attempt(self, *argv, root=None):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run("new", *argv, "--root", str(root or tmp))
            written = sorted(p.name for p in Path(root or tmp).rglob("*") if p.is_file())
        return code, out, err, written

    def test_each_refusal_names_what_to_change_and_writes_nothing(self):
        cases = {
            "an op that is not registered": (("sample.x", "--op", "no.such", "--label", "x"), "not a registered op"),
            "an op the scaffold does not cover": (("sample.x", "--op", "store.set_hours", "--label", "change the hours"), "write this skill by hand"),
            "an id that is not a product": (("sample.x", "--op", "hike.cancel", "--label", "cancel a hike"), "not a product"),
            "a name that exists": (("stock.set", "--op", "product.hide", "--label", "hide it"), "already exists"),
            "a name that is not group.verb": (("Stock", "--op", "product.hide", "--label", "hide it"), "group.verb"),
            "an id as the label": (("sample.x", "--op", "product.hide", "--label", "item.hide"), "owner's words"),
            "an op with nothing to refuse": (("sample.x", "--op", "store.clear_notice", "--label", "clear the notice"), "nothing the scaffold can refuse"),
            "an argument the op lacks": (("sample.x", "--op", "product.hide", "--arg", "colour", "--label", "hide it"), "not a plain argument"),
            "a sentence another skill already owns": (("sample.x", "--op", "product.hide", "--label", "hide it", "--say", "the bread truck comes Monday"),
                                                      "already a trigger"),
        }
        for why, (argv, want) in cases.items():
            with self.subTest(why):
                code, _out, err, written = self.attempt(*argv)
                self.assertEqual(code, 2, err)
                self.assertIn(want, err)
                self.assertEqual(written, [])

    def test_a_python_keyword_module_name_is_refused_and_nothing_is_written(self):
        for word in ("class", "import", "return"):
            with self.subTest(word):
                code, _out, err, written = self.attempt("sample.x", "--op", "product.hide", "--label", "hide it", "--module", word)
                self.assertEqual(code, 2)
                self.assertIn("Python keyword", err)
                self.assertEqual(written, [])

    def test_words_that_break_the_generated_python_are_refused_and_rolled_back(self):
        code, _out, err, written = self.attempt("sample.x", "--op", "product.hide", "--label", 'tuck a product """ away')
        self.assertEqual(code, 2)
        self.assertIn("not valid", err)
        self.assertEqual(written, [])

    def test_a_generated_file_that_does_not_parse_is_caught_before_success(self):
        """check() compiles the generated module and test, because nothing else runs the test: a bad import line is caught here."""
        real = scaffold.render_test
        scaffold.render_test = lambda spec: real(spec).replace("import unittest", "from hass.skills import class as module")
        try:
            code, _out, err, written = self.attempt("sample.x", "--op", "product.hide", "--label", "tuck away")
        finally:
            scaffold.render_test = real
        self.assertEqual(code, 2)
        self.assertIn("not valid Python", err)
        self.assertEqual(written, [])

    def test_dry_run_lists_the_files_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run("new", "sample.tuck_away", "--op", "product.hide", "--label", "tuck away", "--dry-run", "--root", tmp)
            self.assertEqual((code, err), (0, ""))
            self.assertIn("hass/skills/sample_tuck_away.py", out)
            self.assertEqual(list(Path(tmp).rglob("*")), [])

    def test_a_skill_that_cannot_pass_is_rolled_back_whole(self):
        bad_setup = '[{"op": "product.hide", "args": {"id": "photo-product-999"}}]'  # an op the scratch shop refuses
        code, _out, err, written = self.attempt("sample.tuck_away", "--op", "product.hide", "--label", "tuck away", "--setup", bad_setup)
        self.assertEqual(code, 2)
        self.assertIn("did not end in a draft", err)
        self.assertEqual(written, [])


class Pieces(unittest.TestCase):
    def test_the_slip_is_one_swap_and_the_rows_are_deterministic(self):
        self.assertEqual(scaffold._typo("hide the honey"), "hide the hnoey")
        self.assertEqual(scaffold._typo("ok"), "ok")
        self.assertEqual(scaffold._snake("displayBrand"), "display_brand")
        ns = type("N", (), dict(name="sample.tuck_away", op="product.hide", label="tuck away", arg=None, say=None, summary=None,
                                module=None, setup=None))()
        spec = scaffold.build_spec(ns, load_registry(), testkit.registry_skills())
        self.assertEqual(scaffold.case_rows(spec), scaffold.case_rows(spec))
        self.assertEqual(scaffold.render_module(spec), scaffold.render_module(spec))
        self.assertEqual(len(scaffold.case_rows(spec)), 12)


if __name__ == "__main__":
    unittest.main()

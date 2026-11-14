"""AV1109-16: the offline acceptance engine (hass/skills/acceptance_run.py) proves itself in CI.

The eight-row self-test runs real flows (real Conversation, Dispatcher, Editor, sitegen, claims on a scratch worktree); the other
tests are independent failure-path oracles for the engine's own assertions. Nothing here is a full-site acceptance run.
"""
import contextlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

from hass import content_model, conversation
from hass.content_model import REPO_ROOT
from hass.skills import acceptance_run as A, dispatch, load_skills

SELFTEST_DIR = A.SELFTEST_ROWS.parent
SYNTHETIC = REPO_ROOT / "reports" / "hass" / "newitem-1" / "synthetic"
WANT_FAIL = {"bad-write-before-yes": "write-before-yes", "bad-wrong-diff": "wrong-diff",
             "bad-undo-residue": "residue-undeclared", "bad-privacy-leak": "privacy-leak"}
HOURS = ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–5pm · Closed Sunday"]


def good_row(**changes):
    row = {"id": "row-a", "schema_version": 1, "tag": "primary", "skill": "shop.hours", "skill_version": 1,
           "texts": ["we're open till 7 on fridays now"], "replies": [{"skill": "shop.hours", "slots": {"hours": HOURS}}],
           "expect": {"skills": ["shop.hours"], "dispositions": ["proposed"], "expected": "row-a.json", "undo": True}}
    row.update(changes)
    return row


class Base(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.registry = load_skills()

    def root(self, rows, expected=(), photos=()):
        """A scratch fixture root: messages.jsonl, the named self-test expected files (by id) and photos from the synthetic set."""
        tmp = tempfile.TemporaryDirectory(prefix="acc-test-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "messages.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
        for rid, source in dict(expected).items():
            (root / "expected").mkdir(exist_ok=True)
            shutil.copy(SELFTEST_DIR / "expected" / f"{source}.json", root / "expected" / f"{rid}.json")
        for name in photos:
            (root / "photos").mkdir(exist_ok=True)
            shutil.copy(SYNTHETIC / name, root / "photos" / name)
        return root

    def session(self, row):
        sess = A.Session(row, self.registry, SELFTEST_DIR, selftest=True)
        self.addCleanup(sess.close)
        return sess


class SelfTest(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.results = A.run_rows(A.SELFTEST_ROWS, selftest=True, registry=cls.registry)

    def test_selftest_eight_four_exact_failures(self):
        by_id = {r.id: r for r in self.results}
        self.assertEqual(len(by_id), 8)
        self.assertEqual(sum("must_fail" in r.row for r in self.results), 4)
        for rid, code in WANT_FAIL.items():
            self.assertEqual(by_id[rid].codes, [code], rid)  # exactly the intended failure, not any failure
        for rid in set(by_id) - set(WANT_FAIL):
            self.assertEqual(by_id[rid].codes, [], rid)
        self.assertTrue(all(ok for _r, ok, _w in A.judge_selftest(self.results, [r.row for r in self.results])))

    def test_good_rows_reach_the_real_outcomes(self):
        by_id = {r.id: r for r in self.results}
        self.assertEqual(by_id["good-draft-undo"].skills, ["shop.hours"])
        self.assertEqual(by_id["good-draft-undo"].facts["undo"], "identical")
        self.assertEqual(by_id["good-question"].dispositions, ["question"])
        self.assertEqual(by_id["good-unsupported"].dispositions, ["unsupported"])
        self.assertEqual(by_id["good-exchange"].dispositions, ["question", "proposed"])
        self.assertEqual(by_id["good-exchange"].facts["model_calls"], 2)

    def test_selftest_cli_exit_codes(self):
        with mock.patch.object(A, "run_rows", return_value=list(self.results)), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(A.main(["--selftest"]), 0)
        broken = list(self.results)
        broken[0] = mock.Mock(id="good-draft-undo", ok=False, codes=["wrong-diff"], row=broken[0].row)
        with mock.patch.object(A, "run_rows", return_value=broken), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(A.main(["--selftest"]), 1)  # a good row that fails is a failure
        swapped = [mock.Mock(id=r.id, ok=False, codes=["wrong-diff"], row=r.row) if r.id == "bad-privacy-leak" else r for r in self.results]
        with mock.patch.object(A, "run_rows", return_value=swapped), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(A.main(["--selftest"]), 1)  # a fault that fails for another reason is not its intended failure


class RealDispatch(Base):
    def test_raw_skill_reply_reaches_real_dispatcher(self):
        sess = self.session(good_row())
        self.assertIsInstance(sess.conv.dispatch, dispatch.Dispatcher)
        self.assertIs(sess.conv._proposal_reply.__func__, conversation.Conversation._proposal_reply)  # no stand-in prefix patch
        self.assertIs(type(sess.conv.interpreter), A.RecordedInterpreter)
        _msg, disposition, _out = sess.say("we're open till 7 on fridays now")
        self.assertEqual((disposition, sess.observed, sess.interp.calls), ("proposed", ["shop.hours"], 1))
        self.assertEqual([c["op"] for c in json.loads(sess.drafts()[-1]["ops_json"])], ["store.set_hours"])

    def test_dispatcher_validation_is_not_bypassed(self):
        def hide(rid, items, fragment):
            return good_row(id=rid, skill="item.hide", skill_version=1, texts=["hide the plums"], replies=[{"skill": "item.hide", "slots": {"items": items}}],
                            expect={"skills": ["item.hide", "none"], "dispositions": ["question"], "reply_contains": [fragment]})
        root = self.root([hide("unknown-name", "plums", "don't know a product"), hide("ill-typed", ["plums"], "can't use that")])
        got = {r.id: (r.codes, r.dispositions) for r in A.run_rows(root / "messages.jsonl", registry=self.registry)}
        self.assertEqual(got, {"unknown-name": ([], ["question"]), "ill-typed": ([], ["question"])})  # asked about by the real dispatcher, never drafted

    def test_reply_queue_tracks_actual_model_calls(self):
        rows = [good_row(id="no-call", skill="none", skill_version=None, texts=["status"], replies=[],
                         expect={"skills": ["none"], "dispositions": ["status"]}),
                good_row(id="needs-reply", skill="none", skill_version=None, texts=["update the hours"], replies=[],
                         expect={"skills": ["none"], "dispositions": ["question"]}),
                good_row(id="unused-reply", skill="none", skill_version=None, texts=["status"], replies=[{"question": "Which?"}],
                         expect={"skills": ["none"], "dispositions": ["status"]})]
        got = {r.id: r.codes for r in A.run_rows(self.root(rows) / "messages.jsonl", registry=self.registry)}
        self.assertEqual(got, {"no-call": [], "needs-reply": ["reply-queue"], "unused-reply": ["reply-queue"]})


class Oracles(Base):
    def test_clock_and_cleanup_restore_on_exception(self):
        start = A.START.astimezone(ZoneInfo("America/Los_Angeles"))
        self.assertEqual((start.strftime("%A %H:%M"), start.date().isoformat()), ("Sunday 09:00", "2026-11-08"))
        self.assertEqual((start + timedelta(hours=14, minutes=59)).strftime("%A"), "Sunday")
        self.assertEqual((start + timedelta(hours=15)).strftime("%A"), "Monday")  # the Pacific day boundary, not UTC's
        before_clock, tmp = content_model.datetime, Path(tempfile.gettempdir())
        owned = lambda: sorted(p.name for pattern in ("hass-h02-*", "acceptance-*") for p in tmp.glob(pattern))  # noqa: E731
        site, before_owned = REPO_ROOT / "storefront-mockup" / "assets" / "products", owned()
        before_assets = len(list(site.iterdir()))
        bad = good_row(seed={"store": {"town": 5}})  # a seed the content rules refuse
        with self.assertRaises(Exception):
            A.Session(bad, self.registry, SELFTEST_DIR)
        self.assertIs(content_model.datetime, before_clock)
        self.assertEqual(owned(), before_owned)
        self.assertEqual(len(list(site.iterdir())), before_assets)

    def test_byte_map_detects_untracked_assets_and_wrong_yes(self):
        sess = self.session(good_row())
        base = sess.baseline
        self.assertTrue(any(p.startswith(A.ASSET_DIR) for p in base["files"]) and "hass/content/store.json" in base["files"])
        sess.say("we're open till 7 on fridays now")
        self.assertEqual(sess.snapshot(), base)  # a proposal writes nothing
        sess.say("yes ffff")
        self.assertEqual(sess.snapshot(), base)  # a wrong code writes nothing
        orphan = sess.wt / A.ASSET_DIR / "orphan.jpg"
        orphan.write_bytes(b"x")
        self.assertNotEqual(sess.snapshot(), base)  # untracked, never committed: still seen
        orphan.unlink()
        self.assertEqual(sess.snapshot(), base)
        store = sess.wt / "hass" / "content" / "store.json"
        store.write_text(store.read_text("utf-8") + " ", "utf-8")
        self.assertNotEqual(sess.snapshot()["files"], base["files"])  # one stray byte in content
        store.write_text(store.read_text("utf-8").rstrip(" "), "utf-8")
        generated = sess.wt / "storefront-mockup" / "index.html"
        generated.write_text(generated.read_text("utf-8") + "<!-- x -->", "utf-8")
        self.assertNotEqual(sess.snapshot()["files"], base["files"])  # a generated file
        A._git(sess.wt, "checkout", "--", ".")
        self.assertEqual(sess.snapshot(), base)
        (sess.wt / "stray.txt").write_text("x", "utf-8")
        A._git(sess.wt, "add", "stray.txt")
        A._git(sess.wt, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "stray")
        self.assertNotEqual(sess.snapshot()["head"], base["head"])  # HEAD moved

    def test_exact_diff_and_residue_not_whole_file_exemptions(self):
        leftover = [{"file": "hass/content/store.json", "path": "town", "before": "A", "after": "A Leftover"}]
        none = {"content": [], "assets": {}}
        self.assertTrue(A.residue_matches([], {}, none))
        self.assertTrue(A.residue_matches(leftover, {}, {"content": [{"file": "hass/content/store.json", "path": "town"}], "assets": {}}))
        self.assertFalse(A.residue_matches(leftover, {}, none))  # an unpinned content entry
        self.assertFalse(A.residue_matches([], {A.ASSET_DIR + "photo-0123456789abcdef.jpg": "0" * 64}, none))  # an orphan picture outside the residue
        self.assertFalse(A.residue_matches(leftover, {}, {"content": [{"file": "hass/content/store.json"}], "assets": {}}))  # a whole file is not a pin
        self.assertFalse(A.residue_matches(leftover + [{"file": "hass/content/store.json", "path": "extra"}], {}, {"content": [{"file": "hass/content/store.json", "path": "town"}], "assets": {}}))  # an extra key
        self.assertFalse(A.residue_matches(leftover, {}, {"content": [{"file": "hass/content/store.json", "path": "town", "after": "other"}], "assets": {}}))

    def test_residue_is_compared_one_to_one(self):
        a = {"file": "hass/content/store.json", "path": "town", "before": "A", "after": "B"}
        b = {"file": "hass/content/store.json", "path": "tagline", "before": "C", "after": "D"}
        pin = lambda *entries: {"content": [dict(e) for e in entries], "assets": {}}  # noqa: E731
        self.assertTrue(A.residue_matches([a, b], {}, pin(a, b)))
        self.assertFalse(A.residue_matches([a, b], {}, pin(a, a)))  # two pins on a: the unpinned leftover b is not accepted
        self.assertFalse(A.residue_matches([a, b], {}, pin(a)))
        self.assertFalse(A.residue_matches([a], {}, pin(a, b)))  # a pin with no leftover
        self.assertFalse(A.residue_matches([a], {}, pin(a, a)))  # the same pin twice for one leftover
        self.assertFalse(A.residue_matches([a, dict(a)], {}, pin(a, a)))  # a repeated leftover key is never matched
        self.assertFalse(A.residue_matches([a, a], {}, pin(a)))
        self.assertFalse(A.residue_matches([a, b], {}, pin(a, {"file": a["file"], "path": "other"})))

    def test_expected_file_with_a_repeated_residue_key_is_refused(self):
        root = self.root([], expected={"dup": "good-draft-undo"})
        path = root / "expected" / "dup.json"
        data = json.loads(path.read_text("utf-8"))
        entry = {"file": "hass/content/store.json", "path": "town"}
        data["residue"]["content"] = [entry, dict(entry, after="x")]
        path.write_text(json.dumps(data), "utf-8")
        with self.assertRaises(A.InputError): A.load_expected(root, {"id": "dup"})
        data["residue"]["content"] = [entry]
        path.write_text(json.dumps(data), "utf-8")
        self.assertEqual(A.load_expected(root, {"id": "dup"})["residue"]["content"], [entry])

    def test_parsed_json_key_order_ignored_but_stale_generated_bytes_fail(self):
        shuffled = json.loads((SELFTEST_DIR / "expected" / "good-draft-undo.json").read_text("utf-8"))
        reordered = {k: shuffled[k] for k in reversed(list(shuffled))}
        reordered["diff"] = [dict(reversed(list(e.items()))) for e in shuffled["diff"]]
        rows = [good_row(id="reordered", expect={"skills": ["shop.hours"], "dispositions": ["proposed"], "expected": "reordered.json", "undo": True}),
                good_row(id="stale-site", skill="shop.hours", skill_version=1, expect={"skills": ["shop.hours"], "dispositions": ["proposed"], "expected": "stale-site.json", "undo": True})]
        rows[1]["fault"] = "undo-stale-generated"
        root = self.root(rows, expected={"stale-site": "good-draft-undo"})
        (root / "expected").mkdir(exist_ok=True)
        (root / "expected" / "reordered.json").write_text(json.dumps(reordered, indent=1), "utf-8")
        got = {r.id: r.codes for r in A.run_rows(root / "messages.jsonl", selftest=True, registry=self.registry)}
        self.assertEqual(got, {"reordered": [], "stale-site": ["undo-not-identical"]})

    def test_duplicate_does_not_apply_or_reply_twice(self):
        sess = self.session(good_row())
        sess.say("we're open till 7 on fridays now")
        approve, _d, _t = sess.say(f"yes {sess.drafts()[-1]['code']}")
        head, snap, counts, sent = sess.snapshot()["head"], sess.snapshot(), sess.counts(), len(sess.out.sent)
        self.assertEqual(sess.replay(approve), "duplicate")
        self.assertEqual((sess.snapshot(), sess.counts(), len(sess.out.sent)), (snap, counts, sent))
        self.assertEqual(sess.snapshot()["head"], head)
        with mock.patch.object(A.Session, "replay", return_value="applied"):  # a delivery that is not seen as a duplicate fails the row
            [res] = A.run_rows(self.root([good_row()], expected={"row-a": "good-draft-undo"}) / "messages.jsonl", registry=self.registry)
        self.assertEqual(res.codes, ["duplicate-effect"])

    def test_privacy_detects_canaries_in_nonempty_logs(self):
        text = "we're open till 7 on fridays now"
        sess = self.session(good_row())
        sess.say(text)
        audit = sess.conv.db.execute("SELECT count(*) FROM interpreter_audit").fetchone()[0]
        stage = sess.stage_path.read_text("utf-8")
        self.assertTrue(audit >= 1 and stage.count("\n") >= 2)  # not empty placeholders
        self.assertEqual(A.privacy_problems(sess, [text]), [])
        with open(sess.stage_path, "a", encoding="utf-8") as f: f.write(json.dumps({"stage": "x", "t": 1, "id": "abc", "note": text}) + "\n")
        self.assertEqual(A.privacy_problems(sess, [text]), ["privacy-leak"])
        sess.stage_path.write_text(stage, "utf-8")
        for canary in (A.OWNER, A.CHAT, str(sess.wt)):
            sess.conv.db.execute("UPDATE interpreter_audit SET primary_error = ?", (canary,))
            self.assertEqual(A.privacy_problems(sess, [text]), ["privacy-leak"], canary)
        sess.conv.db.execute("UPDATE interpreter_audit SET primary_error = NULL")
        sess.conv.db.execute("DELETE FROM interpreter_audit")
        self.assertEqual(A.privacy_problems(sess, [text]), ["audit-missing"])  # a model call without its audit row

    def test_record_exclusive_and_confined(self):
        row = [r for r in A.load_rows(A.SELFTEST_ROWS, selftest=True) if r["id"] in ("good-draft-undo", "good-question", "good-exchange")]
        root = self.root(row)
        rows = root / "messages.jsonl"
        before = rows.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            candidate = A.record_row("good-draft-undo", rows_path=rows, fixture_root=root, selftest=True)
        written = root / "expected" / "good-draft-undo.json"
        self.assertEqual(written.read_text("utf-8"), candidate)
        self.assertEqual(json.loads(candidate), json.loads((SELFTEST_DIR / "expected" / "good-draft-undo.json").read_text("utf-8")))
        self.assertEqual(rows.read_bytes(), before)  # never edits the rows
        kept = written.read_bytes()
        with self.assertRaises(A.InputError): A.record_row("good-draft-undo", rows_path=rows, fixture_root=root, selftest=True)
        self.assertEqual(written.read_bytes(), kept)  # never overwritten
        target = root / "outside.json"
        os.symlink(target, root / "expected" / "good-exchange.json")  # a dangling symlink is never followed
        with self.assertRaises(A.InputError): A.record_row("good-exchange", rows_path=rows, fixture_root=root, selftest=True)
        self.assertFalse(target.exists())
        with self.assertRaises(A.InputError): A.record_row("good-question", rows_path=rows, fixture_root=root, selftest=True)  # proposes nothing
        with self.assertRaises(A.InputError): A.record_row("no-such-row", rows_path=rows, fixture_root=root, selftest=True)
        other = self.root(row)
        elsewhere = Path(tempfile.mkdtemp(prefix="acc-elsewhere-"))
        self.addCleanup(shutil.rmtree, elsewhere, True)
        os.symlink(elsewhere, other / "expected")  # a symlinked expected folder
        with self.assertRaises(A.InputError): A.record_row("good-draft-undo", rows_path=other / "messages.jsonl", fixture_root=other, selftest=True)
        self.assertEqual(list(elsewhere.iterdir()), [])
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(A.main(["--rows", str(rows), "--record", "good-question"]), 2)  # exit 2, nothing written


class Refusals(Base):
    def bad(self, **changes):
        with self.assertRaises(A.InputError, msg=str(changes)):
            A.validate_row(good_row(**changes))

    def test_lowered_threshold_and_bad_schema_refused(self):
        with self.assertRaises(TypeError): A.THRESHOLDS["diff"] = 0.5
        lowered = {**A.THRESHOLDS, "diff": 0.5}
        with self.assertRaises(A.InputError): A.run_rows(A.SELFTEST_ROWS, selftest=True, thresholds=lowered, registry=self.registry)
        for flags in (["--threshold", "0.5"], ["--selftest", "--min-diff", "0.9"], ["--allow-failures"], ["--lower-bar"], ["--bogus"], ["--rows"]):
            with contextlib.redirect_stderr(io.StringIO()): self.assertEqual(A.main(flags), 2, flags)
        with mock.patch.object(A, "DEFAULT_ROWS", Path(tempfile.gettempdir()) / "no-such-acceptance-rows.jsonl"), \
                mock.patch.object(A, "run_rows") as ran, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(A.main([]), 2)  # a missing default file is refused, with no fall back to the self-test
            ran.assert_not_called()
        self.bad(schema_version=0)
        self.bad(unknown_field=1)
        self.bad(id="Bad Id")
        self.bad(tag="loud")
        self.bad(skill="none")  # none needs a null version
        self.bad(texts=[])
        self.bad(replies=["not an object"])
        self.bad(fault="write-on-prepare")  # a fault only exists in the self-test fixtures
        self.bad(expect={"skills": ["shop.hours"], "dispositions": ["proposed"], "expected": "../x.json"})
        self.bad(expect={"skills": ["shop.hours"], "dispositions": ["proposed"]})  # a proposed row names its expected file
        self.bad(expect={"skills": ["shop.hours"], "dispositions": ["question"], "expected": "row-a.json"})
        self.bad(expect={"skills": ["item.hide"], "dispositions": ["question"]})  # the row's own skill is among the allowed ones
        self.bad(expect={"skills": ["shop.hours"], "dispositions": ["proposed", "proposed"], "expected": "row-a.json"})
        self.bad(expect={"skills": ["shop.hours"], "dispositions": ["proposed"], "expected": "row-a.json", "surprise": 1})
        for fixture in ("../a.jpg", "/abs/a.jpg", "a/../b.jpg", "a.gif", "a\\b.jpg"):
            self.bad(photos=[{"turn": 0, "fixture": fixture}])
        self.bad(photos=[{"turn": 3, "fixture": "p/a.jpg"}])
        self.bad(offsets=[99999])
        self.bad(seed={"unknown": {}})
        self.bad(setup=[{"op": "x"}])
        self.bad(texts=[""])  # an empty text is only for a photo turn
        A.validate_row(good_row(texts=[""], photos=[{"turn": 0, "fixture": "p/a.jpg"}]))

    def test_bad_files_refused_before_any_run(self):
        def run(rows, **kw):
            return A.run_rows(self.root(rows, **kw) / "messages.jsonl", registry=self.registry)
        with mock.patch.object(A, "Session") as session:
            with self.assertRaises(A.InputError): run([])  # an empty corpus
            with self.assertRaises(A.InputError): run([good_row(), good_row()])  # a duplicate id
            with self.assertRaises(A.InputError): run([good_row(skill_version=99)])  # a stale skill version
            with self.assertRaises(A.InputError): run([good_row()])  # the expected file is missing
            with self.assertRaises(A.InputError): run([good_row(texts=[""], photos=[{"turn": 0, "fixture": "photos/missing.jpg"}])], expected={"row-a": "good-draft-undo"})
            with self.assertRaises(A.InputError): run([good_row(fault="undo-leaves")], expected={"row-a": "good-draft-undo"})  # fault in an ordinary file
            session.assert_not_called()
        bad_file = self.root([])
        (bad_file / "messages.jsonl").write_text("{not json}\n", "utf-8")
        with self.assertRaises(A.InputError): A.run_rows(bad_file / "messages.jsonl", registry=self.registry)

    def test_thresholds_are_the_spec_bar(self):
        self.assertEqual(dict(A.THRESHOLDS), {"structural": 1.0, "outcome": 1.0, "diff": 1.0, "undo": 1.0, "wrong_drafts": 0,
                                              "unstated_or_invented": 0, "pre_approval_writes": 0})
        ok, bad = A.Result("a"), A.Result("b")
        ok.dispositions, bad.dispositions = ["proposed"], ["proposed"]
        bad.fail("wrong-diff")
        self.assertTrue(A.summarize([ok])["met"] and A.summarize([ok])["partial"])
        self.assertFalse(A.summarize([ok, bad])["met"])
        for code in ("write-before-yes", "unstated-claim", "undo-not-identical", "wrong-skill"):
            worse = A.Result("c")
            worse.fail(code)
            self.assertFalse(A.summarize([ok, worse])["met"], code)


class Pictures(Base):
    def setUp(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is needed for synthetic images")
        self.Image = Image
        self.tmp = Path(tempfile.mkdtemp(prefix="acc-pic-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def picture(self, name, size, fmt="JPEG", color=(255, 255, 255), extra=None):
        path = self.tmp / A.ASSET_DIR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        self.Image.new("RGB", size, color).save(path, fmt)
        if extra is not None:
            data = path.read_bytes()
            path.write_bytes(data[:2] + extra + data[2:])  # a JPEG segment right after the start marker
        return A.ASSET_DIR + name

    def check(self, rel, spec=None, house=True, originals=("0123456789abcdef" + "0" * 48,)):
        return A.picture_problems({rel: "x"}, self.tmp, {"picture": spec} if spec else {}, house, set(originals))

    def test_product_photo_vs_hero_rules(self):
        wide = self.picture("photo-0123456789abcdef.jpg", (600, 300))
        self.assertIn("a product picture is not square", self.check(wide, {"kind": "product", "house": "off"}))
        self.assertEqual(self.check(wide, {"kind": "hero", "house": "off", "type": "jpeg", "size": [600, 300]}), [])  # the hero is exempt
        self.assertIn("picture size is not the expected size", self.check(wide, {"kind": "hero", "size": [800, 800]}))
        square = self.picture("photo-0123456789abcdef.jpg", (800, 800))
        self.assertIn("picture does not pass the house check", self.check(square, {"kind": "product", "house": "pass"}))  # a blank frame is never clean
        self.assertEqual(self.check(square, {"kind": "product", "house": "warn"}), [])
        self.assertEqual(self.check(square, {"kind": "product", "house": "off"}), [])
        png = self.picture("photo-0123456789abcdef.png", (800, 800), "PNG")
        self.assertIn("picture is not the expected type", self.check(png, {"kind": "product", "type": "jpeg", "house": "off"}))
        self.assertIn("picture name is not photo-<sha16> of a photo that was sent", self.check(square, {"house": "off"}, originals=("f" * 64,)))
        self.assertIn("picture name is not photo-<sha16> of a photo that was sent", self.check(self.picture("other.jpg", (8, 8)), {"house": "off"}))
        self.assertIn("picture type does not match its name", self.check(self.picture("photo-0123456789abcdef.png", (8, 8), "JPEG"), {"house": "off"}))

    @staticmethod
    def exif(tags, order="II", nxt=0):
        """A JPEG APP1 Exif segment whose IFD0 holds the given tag numbers (zero values)."""
        end = "little" if order == "II" else "big"
        ifd = len(tags).to_bytes(2, end) + b"".join(t.to_bytes(2, end) + (3).to_bytes(2, end) + (1).to_bytes(4, end) + bytes(4) for t in tags) + nxt.to_bytes(4, end)
        body = b"Exif\0\0" + order.encode() + (42).to_bytes(2, end) + (8).to_bytes(4, end) + ifd
        return b"\xff\xe1" + (len(body) + 2).to_bytes(2, "big") + body

    def test_metadata_and_location_in_a_picture_fail(self):
        tagged = self.picture("photo-0123456789abcdef.jpg", (800, 800), extra=self.exif([0x0112]))
        self.assertIn("picture carries metadata", self.check(tagged, {"house": "off"}, house=True))  # the house render carries none
        self.assertEqual(self.check(tagged, {"house": "off"}, house=False), [])  # a plain web copy may keep its orientation tag
        big = self.picture("photo-0123456789abcdef.jpg", (800, 800), extra=self.exif([0x0112], order="MM"))
        self.assertEqual(self.check(big, {"house": "off"}, house=False), [])
        gps = b"\xff\xe1" + (len(b"Exif\0\0GPS") + 2).to_bytes(2, "big") + b"Exif\0\0GPS"
        located = self.picture("photo-0123456789abcdef.jpg", (800, 800), extra=gps)
        self.assertIn("picture carries location data", self.check(located, {"house": "off"}, house=False))

    def test_numeric_exif_gps_tag_is_location_data(self):
        for order in ("II", "MM"):
            for tags in ([0x8825], [0x0112, 0x8825]):  # GPSInfo alone, and next to the orientation tag
                located = self.picture("photo-0123456789abcdef.jpg", (800, 800), extra=self.exif(tags, order=order))
                self.assertNotIn(b"GPS", (self.tmp / located).read_bytes())  # no ASCII marker: only the numeric tag says it
                got = self.check(located, {"house": "off"}, house=False)
                self.assertIn("picture carries location data", got, (order, tags))
                self.assertIn("picture carries metadata", got)
        thumb = self.picture("photo-0123456789abcdef.jpg", (800, 800), extra=self.exif([0x0112], nxt=8 + 2 + 12 + 4))  # a second IFD in the chain is not orientation only
        self.assertIn("picture carries metadata", self.check(thumb, {"house": "off"}, house=False))

    def test_plain_copy_allows_only_a_clean_orientation_block(self):
        for name, extra in (("camera tags", self.exif([0x0112, 0x010F])), ("truncated", b"\xff\xe1\x00\x0cExif\0\0II*\0"),
                            ("xmp", b"\xff\xe1" + (len(b"http://ns.adobe.com/xap/1.0/\0x") + 2).to_bytes(2, "big") + b"http://ns.adobe.com/xap/1.0/\0x"),
                            ("no tags", self.exif([]))):
            pic = self.picture("photo-0123456789abcdef.jpg", (800, 800), extra=extra)
            self.assertIn("picture carries metadata", self.check(pic, {"house": "off"}, house=False), name)

    def test_photo_row_goes_through_the_media_binding_and_the_house_render(self):
        plain = {"id": "lemons-plain", "schema_version": 1, "tag": "photo", "skill": "item.picture", "skill_version": 2,
                 "texts": ["here is a better picture of the lemons"], "replies": [{"skill": "item.picture", "slots": {"item": "lemons"}}],
                 "photos": [{"turn": 0, "fixture": "photos/jar-white-sheet.jpg"}],
                 "expect": {"skills": ["item.picture"], "dispositions": ["proposed"], "expected": "lemons-plain.json", "undo": True,
                            "picture": {"kind": "product", "type": "jpeg", "house": "off"}, "reply_contains": ["I'll use the photo as you took it"]}}
        house = {**plain, "id": "lemons-house", "house_render": True,
                 "expect": {"skills": ["item.picture"], "dispositions": ["proposed"], "expected": "lemons-house.json", "undo": True,
                            "picture": {"kind": "product", "type": "jpeg", "size": [800, 800], "house": "pass"}}}
        root = self.root([plain, house], photos=["jar-white-sheet.jpg"])
        rows = root / "messages.jsonl"
        with contextlib.redirect_stderr(io.StringIO()):
            recorded = {rid: json.loads(A.record_row(rid, rows_path=rows, fixture_root=root, registry=self.registry)) for rid in ("lemons-plain", "lemons-house")}
        for rec in recorded.values():
            [(path, sha)] = rec["assets"].items()
            self.assertRegex(path, r"assets/products/photo-2cec1911a5900242\.jpg$")  # named for the photo the owner sent
            self.assertEqual(rec["residue"]["assets"], rec["assets"])  # the picture file stays after undo, pinned exactly
        self.assertNotEqual(recorded["lemons-plain"]["assets"], recorded["lemons-house"]["assets"])  # the house render changes the bytes
        got = {r.id: (r.codes, r.dispositions) for r in A.run_rows(rows, registry=self.registry)}
        self.assertEqual(got, {"lemons-plain": ([], ["proposed"]), "lemons-house": ([], ["proposed"])})
        path = root / "expected" / "lemons-plain.json"  # a wrong picture hash in the expectation fails
        tampered = json.loads(path.read_text("utf-8"))
        tampered["assets"] = {k: "0" * 64 for k in tampered["assets"]}
        path.write_text(json.dumps(tampered), "utf-8")
        [res] = A.run_rows(rows, registry=self.registry, only={"lemons-plain"})
        self.assertEqual(res.codes, ["wrong-diff"])


# -- AV1109-17: the Primary corpus (one row per registered skill) ---------------------------------------------------
# First example sentence of each catalog entry (SKILLS-SPEC section 3, docs/hass/skills/specials.md and social.md), tags such as (p) removed.
FIRST_SENTENCES = {
    'answer.site': 'what time do we close saturday?',
    'backlog.log': 'can you order more eggs from the farm',
    'front.banner': 'banner: Come say hello from tomorrow through Sunday',
    'front.faq': 'Questions: Is parking nearby? Yes, right behind the shop.',
    'front.page': 'create the Getting here page: Parking is right behind the shop.',
    'front.sections': 'hide the newsletter part',
    'hike.add': 'add a hike Saturday at 8am, Mill Creek trailhead, easy, bring water',
    'hike.cancel': 'cancel the Point Buchon hike, rained out - we will pick a new date soon',
    'hike.edit': 'change the Cass Hill meeting point to the upper lot',
    'hike.recap': 'recap: 12 people, great morning',
    'hike.repeat': 'do the Cass Hill hike again on the 29th at 9',
    'hike.reschedule': 'can we push the Morro Rock Beach Stroll back to 10am, the tide is lower later',
    'item.add': 'new honey from Cal Poly, goes on the pantry shelf',
    'item.edit': 'rename the Hass avocado to Hass avocados',
    'item.hide': 'hide the plums',
    'item.picture': 'new picture for the lemons',
    'item.restore': 'bring back the lemons',
    'maker.add': 'add a maker: Bee Happy Farm in Atascadero, they keep bees on the hill, beehappyfarm.com',
    'maker.edit': "update Etto's story: they started in a small kitchen and now dry pasta slowly",
    'maker.hide': 'we stopped carrying Etto',
    'maker.restore': 'Etto is back',
    'page.about': 'change the about text to: Michael has been buying produce for 30 years and knows every grower',
    'page.home': 'change the headline to Fresh from the coast. Picked this week.',
    'page.photo': "use this for the home page, it's the front of the shop",
    'report.shelf': 'morning report',
    'shop.contact': 'our new number is 805-555-0100',
    'shop.hours': "we're open till 7 on fridays now",
    'shop.notice': "put a notice up: we're closed Thanksgiving, back Friday",
    'social.hike': 'announcement for the Cass Hill hike',
    'social.item': 'write an instagram post for the honey',
    'social.maker': "write a meet the maker post for Linn's",
    'social.recap': "write the thank-you post for Saturday's hike",
    'specials.add': 'put the avocado honey on special this week, 2 for 5 dollars',
    'specials.clear_expired': 'clear out the old specials',
    'specials.edit': 'extend the honey special to next Sunday',
    'specials.remove': 'take the special off',
    'specials.show': "what are this week's specials",
    'stock.checked': 'I checked the selection today: the avocados are in, the eggs are limited, the sourdough is sold out',
    'stock.clear': 'stop showing the eggs as sold out',
    'stock.restock': 'more honey coming Thursday',
    'stock.set': 'eggs are out',
}
PHOTO_SOURCES = {  # the eight synthetic photos of #504 (reports/hass/newitem-1/synthetic): five clean, three warned
    "jar-white-sheet.jpg": True, "bottle-grey-wall-tilted.jpg": True, "jar-phone-rotated.jpg": True, "bottle-bench-png.png": True,
    "jar-cutout-alpha.png": True, "bag-bench-small.jpg": False, "jar-dark-wood.jpg": False, "bag-red-cloth.jpg": False}
# Rows pinned to a dependency behaviour that blocks the draft; each must be fixed by its owner and re-recorded (README, "Held rows").
HELD = {"primary-page-about": "question", "primary-maker-edit": "question", "primary-stock-set": "question",
        "photo-bag-bench-small": "not-drafted", "photo-jar-dark-wood": "not-drafted", "photo-bag-red-cloth": "not-drafted"}


class PrimaryCorpus(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.rows = A.load_rows(A.DEFAULT_ROWS)
        cls.results = A.run_rows(A.DEFAULT_ROWS, registry=cls.registry)

    def primaries(self, rows=None):
        return [r for r in (rows or self.rows) if r["tag"] == "primary"]

    def coverage_problems(self, rows):
        names = [r["skill"] for r in self.primaries(rows)]
        reg = {s.name: s for s in self.registry.active()}  # a retired skill (page.faq, AVB-19-B2) keeps its name, not a row
        problems = [f"missing {n}" for n in sorted(set(reg) - set(names))] + [f"unknown {n}" for n in sorted(set(names) - set(reg))]
        problems += [f"duplicate {n}" for n in sorted({n for n in names if names.count(n) > 1})]
        problems += [f"stale {r['skill']}" for r in self.primaries(rows) if r["skill"] in reg and r["skill_version"] != reg[r["skill"]].version]
        return problems

    def test_primary_set_equals_registry_once(self):
        self.assertEqual(self.coverage_problems(self.rows), [])
        self.assertEqual(set(FIRST_SENTENCES), {s.name for s in self.registry.active()})  # a skill added later needs its sentence here too
        without = [r for r in self.rows if r["id"] != "primary-shop-hours"]
        self.assertEqual(self.coverage_problems(without), ["missing shop.hours"])
        stale = [dict(r, skill_version=2) if r["id"] == "primary-shop-hours" else r for r in self.rows]
        self.assertEqual(self.coverage_problems(stale), ["stale shop.hours"])
        self.assertEqual(self.coverage_problems(self.rows + [self.rows[0]]), [f"duplicate {self.rows[0]['skill']}"])

    def test_primary_first_sentence_matches_catalog(self):
        for r in self.primaries():
            self.assertEqual(r["texts"][0], FIRST_SENTENCES[r["skill"]], r["id"])
            self.assertEqual(r["id"], "primary-" + r["skill"].replace(".", "-"))

    def test_all_primary_rows_replay_real_dispatch_at_100_percent(self):
        self.assertEqual(len(self.results), len(self.rows))
        self.assertEqual([(r.id, r.codes) for r in self.results if not r.ok], [("acc-multi-01", ["wrong-disposition"])])  # AV1109-18: the one recorded genuine failure (README, "Known failures"); delete this entry when the router is fixed
        by_id = {r.id: r for r in self.results}
        self.assertEqual(by_id["primary-report-shelf"].dispositions, ["report"])  # an existing command: command precedence, no model call
        self.assertEqual(by_id["primary-report-shelf"].facts["model_calls"], 0)

    def test_expected_inventory_and_reviewed_declarations(self):
        want = {r["expect"]["expected"] for r in self.rows if r["expect"].get("expected")}
        have = {p.name for p in (A.FIXTURE_ROOT / "expected").glob("*.json") if not p.name.startswith("chain-")}  # chain has its own inventory/session
        self.assertEqual(want, have)  # every proposal has a golden, no orphan
        broken = self.root([dict(r) for r in self.rows if r["id"] == "primary-stock-clear"] and [r for r in self.rows if r["id"] == "primary-stock-clear"])
        (broken / "expected").mkdir()
        golden = json.loads((A.FIXTURE_ROOT / "expected" / "primary-stock-clear.json").read_text("utf-8"))
        golden["diff"][0]["before"] = "limited"  # a corrupted golden fails the exact diff
        (broken / "expected" / "primary-stock-clear.json").write_text(json.dumps(golden), "utf-8")
        [res] = A.run_rows(broken / "messages.jsonl", registry=self.registry)
        self.assertEqual(res.codes, ["wrong-diff"])

    def test_photo_rows_eight_unique_five_clean_three_warned(self):
        photo_rows = [r for r in self.rows if r.get("photos") and r["tag"] in ("primary", "photo")]  # AV1109-18: the forty rows' own photo turn is not one of the eight
        fixtures = sorted(Path(r["photos"][0]["fixture"]).name for r in photo_rows)
        self.assertEqual(sorted(PHOTO_SOURCES), fixtures)
        for name, clean in PHOTO_SOURCES.items():
            self.assertEqual((A.FIXTURE_ROOT / "photos" / name).read_bytes(), (SYNTHETIC / name).read_bytes(), name)  # the committed source bytes
        warned = [r for r in photo_rows if Path(r["photos"][0]["fixture"]).name not in {n for n, c in PHOTO_SOURCES.items() if c}]
        self.assertEqual(len(warned), 3)
        self.assertEqual(len([r for r in photo_rows if r["tag"] == "primary"]), 3)  # item.add, item.picture, page.photo
        by_id = {r.id: r for r in self.results}
        for r in photo_rows:
            if r in warned: continue
            self.assertEqual(by_id[r["id"]].facts["pictures"], 1, r["id"])

    def test_warned_fallback_never_bypasses_installer_or_approval(self):
        # D6 (AV1109-05) is unresolved: a warned photo is NOT drafted today. When the owner-approved fallback lands these rows
        # fail here and must be re-recorded with the warning shown before a fresh yes; they are never silently passed.
        by_id = {r.id: r for r in self.results}
        for rid, disp in HELD.items():
            self.assertEqual(by_id[rid].dispositions[-1], disp, rid)
            self.assertEqual(by_id[rid].facts.get("pictures", 0), 0, rid)
            self.assertNotIn("expected", next(r for r in self.rows if r["id"] == rid)["expect"], rid)


if __name__ == "__main__":
    unittest.main()

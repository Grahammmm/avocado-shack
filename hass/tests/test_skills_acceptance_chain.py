"""Full offline acceptance chain plus bounded real-session safety negatives."""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from hass.skills import acceptance_run as A, load_skills


def mini():
    def row(n, skill, text, replies, disposition):
        rid = f"chain-{n:02d}"
        expect = {"skills": [skill, "none"], "dispositions": [disposition]}
        if disposition == "proposed": expect.update(expected=rid + ".json", undo=True)
        return {"id": rid, "schema_version": 1, "tag": "turns", "skill": skill,
                "skill_version": None if skill == "none" else 1, "texts": [text], "replies": replies, "expect": expect}
    hours = ["Monday–Thursday 9am–6pm", "Friday 9am–7pm", "Saturday 9am–5pm · Closed Sunday"]
    rows = [row(1, "item.hide", "hide an item", [{"skill": "item.hide", "slots": {}}], "question"),
            row(2, "item.hide", "the lemons", [{"skill": "item.hide", "slots": {"items": "lemons"}}], "proposed"),
            row(3, "shop.hours", "we're open till 7 on fridays now", [{"skill": "shop.hours", "slots": {"hours": hours}}], "proposed"),
            row(4, "none", "status", [], "status")]
    rows[1]["expect"]["ops"] = [{"op": "product.hide", "args": {"id": "photo-product-017"}}]
    rows[2]["expect"]["ops"] = [{"op": "store.set_hours", "args": {"hours": hours}}]
    rows[0]["expect"]["request"] = {"skill": "item.hide", "slots": {}, "asked_slot": "items", "calls": [], "attachments": []}
    return rows


class Chain(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.registry = load_skills()

    def fixture(self):
        tmp = tempfile.TemporaryDirectory(prefix="chain-mini-")
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "expected").mkdir()
        self.write_rows(root, mini())
        # Hand-reviewed independent deltas: hide active lemons; change Friday only.
        # The inverse swaps presence/value, retaining exactly the same changed-file set.
        for n, source in ((2, A.FIXTURE_ROOT / "expected/primary-item-hide.json"),
                          (3, A.SELFTEST_ROWS.parent / "expected/good-draft-undo.json")):
            forward = json.loads(source.read_text())
            (root / f"expected/chain-{n:02d}.json").write_text(json.dumps(forward))
            inverse = copy.deepcopy(forward)
            for e in inverse["diff"]: e["before"], e["after"] = e["after"], e["before"]
            (root / f"expected/chain-undo-{n:02d}.json").write_text(json.dumps(inverse))
        return root

    def write_rows(self, root, rows):
        (root / "chain-mini.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def run_chain(self, root): return A.run_chain(root / "chain-mini.jsonl", registry=self.registry)

    def test_one_session_current_baselines_and_reverse_originals(self):
        root = self.fixture()
        seen = []
        original = A.Session._open
        def opened(sess, registry):
            seen.append(sess)
            return original(sess, registry)
        with mock.patch.object(A.Session, "_open", opened): results = self.run_chain(root)
        self.assertEqual(len(seen), 1)
        self.assertEqual([(r.id, r.codes) for r in results], [(f"chain-{n:02d}", []) for n in (1, 2, 3, 4)] + [(f"chain-undo-{n:02d}", []) for n in (3, 2)])
        facts = results[-1].facts
        self.assertEqual((facts["requests"], facts["originals"], facts["inverses"]), (4, 2, 2))
        self.assertEqual(facts["deliveries"], facts["requests"] + facts["controls"])
        self.assertEqual(facts["residue"], {"content": [], "assets": {}})

    def test_bad_order_empty_schema_mixed_modes_refuse_before_scratch(self):
        root = self.fixture()
        variants = [[], list(reversed(mini())), mini() + [mini()[0]]]
        for key, value in (("schema_version", 2), ("tag", "primary"), ("texts", []), ("texts", ["a", "b"]), ("photos", {}), ("skill_version", 99)):
            rows = mini(); rows[0][key] = value; variants.append(rows)
        rows = mini(); rows[1]["seed"] = {}; variants.append(rows)
        rows = mini(); del rows[0]["expect"]["request"]; variants.append(rows)
        with mock.patch.object(A, "Session") as session:
            for rows in variants:
                self.write_rows(root, rows)
                with self.assertRaises(A.InputError): self.run_chain(root)
            for flags in (["--rows", "x"], ["--rows", ""], ["--selftest"], ["--record", "chain-02"], ["--record", ""]):
                with contextlib.redirect_stderr(io.StringIO()): self.assertEqual(A.main(["--chain", str(root / "chain-mini.jsonl"), *flags]), 2)
            session.assert_not_called()
        with self.assertRaises(A.InputError): A.validate_row(mini()[0])

    def test_corrupt_middle_golden_identifies_step_before_undo(self):
        root = self.fixture(); p = root / "expected/chain-03.json"
        data = json.loads(p.read_text()); data["diff"][0]["after"] = ["wrong"]
        p.write_text(json.dumps(data))
        results = self.run_chain(root)
        self.assertEqual((results[-1].id, results[-1].codes), ("chain-03", ["wrong-diff"]))

    def test_duplicate_and_privacy_fail_real_phases(self):
        for phase in ("forward", "approval", "undo"):
            root = self.fixture()
            def hit(text): return (phase == "forward" and text == "hide an item" or phase == "approval" and text.startswith("yes ") or phase == "undo" and text.startswith("undo "))
            original = A.Session.replay
            def replay(sess, msg): return "not-duplicate" if hit(msg.text) else original(sess, msg)
            with mock.patch.object(A.Session, "replay", replay): results = self.run_chain(root)
            self.assertIn("duplicate-effect", results[-1].codes, phase)
            say = A.Session.say
            def leak(sess, text, **kw):
                out = say(sess, text, **kw)
                if hit(text):
                    with sess.stage_path.open("a") as f: f.write(json.dumps({"stage": "x", "note": A.OWNER}) + "\n")
                return out
            with mock.patch.object(A.Session, "say", leak): results = self.run_chain(root)
            self.assertIn("privacy-leak", results[-1].codes, phase)

    def test_wrong_yes_and_preapproval_write_cannot_be_hidden_by_undo(self):
        root = self.fixture(); say = A.Session.say
        def writes(sess, text, **kw):
            out = say(sess, text, **kw)
            if text.startswith("yes ") and out[1] != "approved": (sess.wt / "stray.txt").write_text("synthetic")
            return out
        with mock.patch.object(A.Session, "say", writes): results = self.run_chain(root)
        self.assertIn("write-before-yes", results[-1].codes)

    def test_request_boundary_and_continuation_identity(self):
        root = self.fixture(); say = A.Session.say
        def stale(sess, text, **kw):
            out = say(sess, text, **kw)
            if text == "hide an item": sess.conv.db.execute("UPDATE open_requests SET slots_json = ?", (json.dumps({"maker": "stale"}),))
            return out
        with mock.patch.object(A.Session, "say", stale): results = self.run_chain(root)
        self.assertEqual(results[-1].codes, ["request-leak"])

    def test_reverse_target_corruption_is_not_final_tree_acceptance(self):
        root = self.fixture(); say = A.Session.say
        def corrupt(sess, text, **kw):
            out = say(sess, text, **kw)
            if text.startswith("undo "): sess.conv.db.execute("UPDATE drafts SET ops_json = '[]' WHERE row_id = ?", (sess.drafts()[-1]["row_id"],))
            return out
        with mock.patch.object(A.Session, "say", corrupt): results = self.run_chain(root)
        self.assertIn("undo-order", results[-1].codes)

    def test_exact_residue_stale_generated_orphan_and_dirty(self):
        for fault in ("key", "orphan", "generated", "dirty"):
            root = self.fixture(); final = A._chain_final
            def inject(sess, res, *args):
                if fault == "key":
                    p = sess.wt / "hass/content/store.json"
                    data = json.loads(p.read_text()); data["town"] = "Synthetic town"
                    p.write_text(json.dumps(data))
                elif fault == "orphan": (sess.wt / A.ASSET_DIR / "orphan.jpg").write_bytes(b"synthetic")
                elif fault == "generated":
                    with (sess.wt / "storefront-mockup/index.html").open("a") as f: f.write("stale")
                else: (sess.wt / "stray.txt").write_text("synthetic")
                return final(sess, res, *args)
            with mock.patch.object(A, "_chain_final", inject): results = self.run_chain(root)
            self.assertTrue({"residue-undeclared", "undo-not-identical"} & set(results[-1].codes), (fault, results[-1].codes))

    def test_cancelled_expired_and_stale_approval_fail_without_false_success(self):
        from datetime import timedelta
        for fault in ("cancelled", "expired", "stale"):
            root = self.fixture(); say = A.Session.say
            def interrupt(sess, text, **kw):
                if text.startswith("yes ") and any(d["code"] == text[4:] for d in sess.drafts()):
                    if fault == "cancelled":
                        sess.conv.db.execute("UPDATE drafts SET state = 'cancelled' WHERE code = ?", (text[4:],))
                    elif fault == "expired": sess.now += timedelta(minutes=31)
                    else:
                        p = sess.wt / "hass/content/products.json"
                        data = json.loads(p.read_text())
                        # Change the very record the pending hide targets.
                        target = next(x for x in data["products"] if x["id"] == "photo-product-017")
                        target["description"] = "Synthetic conflicting edit."
                        p.write_text(json.dumps(data))
                        A._git(sess.wt, "add", "hass/content/products.json")
                        A._git(sess.wt, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "synthetic stale base")
                return say(sess, text, **kw)
            with mock.patch.object(A.Session, "say", interrupt): results = self.run_chain(root)
            self.assertIn("apply-failed", results[-1].codes, (fault, results[-1].codes))
            self.assertEqual(results[-1].facts["inverses"], 0)

    def test_one_session_twenty_four_requests_then_thirteen_reverse_undos(self):
        path = A.FIXTURE_ROOT / "chain.jsonl"
        rows = A.load_chain(path, fixture_root=A.FIXTURE_ROOT)
        opened, private = [], []
        original_open, original_close = A.Session._open, A.Session.close
        def track_open(sess, registry):
            opened.append(sess)
            return original_open(sess, registry)
        def inspect_close(sess):
            try:
                private.extend(dict(r) for r in sess.conv.db.execute(
                    "SELECT text, state FROM backlog ORDER BY id"))
                self.assertEqual(len(sess.drafts()), 26)
                drafts = sess.drafts()
                self.assertEqual([d["state"] for d in drafts[:13]], ["reverted"] * 13)
                self.assertTrue(all(d["state"] in ("applied", "verified") for d in drafts[13:]))
            finally:
                original_close(sess)
        with mock.patch.object(A.Session, "_open", track_open), mock.patch.object(A.Session, "close", inspect_close):
            results = A.run_chain(path, registry=self.registry)
        self.assertEqual(len(opened), 1)
        numbers = (3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 16, 18, 20)
        ids = [f"chain-{n:02d}" for n in range(1, 25)] + [f"chain-undo-{n:02d}" for n in reversed(numbers)]
        self.assertEqual([(r.id, r.codes) for r in results], [(rid, []) for rid in ids])
        summary = A.summarize(results)
        self.assertTrue(summary["met"])
        for measure in ("structural", "outcome", "diff", "undo"):
            self.assertEqual(summary["measures"][measure], 1.0)
        facts = results[-1].facts
        self.assertEqual({k: facts[k] for k in ("requests", "controls", "deliveries", "originals", "inverses")},
                         {"requests": 24, "controls": 128, "deliveries": 152, "originals": 13, "inverses": 13})
        self.assertEqual(private, [{"text": rows[-1]["texts"][0], "state": "open"}])
        self.assertEqual(facts["residue"], {
            "content": [
                {"file": "hass/content/community.json", "path": "events[hike-2026-11-21-pebble-loop-hike]",
                 "sha256": "b5e4b7c481e6876d20865f59d5b70eaf295a348a266582d5f4b210c8f169ef49"},
                {"file": "hass/content/makers.json", "path": "makers.Pebble Kitchen",
                 "sha256": "b6065e84386363b9f720175e573329a37c0b345ea262a05cc25bbd34da4b1604"},
                {"file": "hass/content/products.json", "path": "products[photo-product-175]",
                 "sha256": "82bdb794dffb91937e8545fa866b6924be24c2403add5a658ce17c172e2819b5"}],
            "assets": {
                "storefront-mockup/assets/products/photo-2cec1911a5900242.jpg": "6de89b6af9589b8749e9fb1bbe578df8912050df3d8caa2a11e8926297962782",
                "storefront-mockup/assets/products/photo-91c700264e60552f.jpg": "47c973da2b315c19c9ac922d3963e271d62ca93b50f0f17e9257ea449e80fd0b"}})
        self.assertEqual({p.name for p in (A.FIXTURE_ROOT / "expected").glob("chain-undo-*.json")},
                         {f"chain-undo-{n:02d}.json" for n in numbers})

    def test_forward_fixture_inventory(self):
        rows = A.load_chain(A.FIXTURE_ROOT / "chain.jsonl", fixture_root=A.FIXTURE_ROOT)
        self.assertEqual([r["id"] for r in rows], [f"chain-{n:02d}" for n in range(1, 25)])
        numbers = (3, 4, 5, 6, 7, 8, 11, 12, 13, 14, 16, 18, 20)
        want = {f"chain-{n:02d}.json" for n in numbers}
        self.assertEqual({r["expect"]["expected"] for r in rows if r["expect"].get("expected")}, want)
        self.assertEqual({p.name for p in (A.FIXTURE_ROOT / "expected").glob("chain-*.json") if not p.name.startswith("chain-undo-")}, want)

    def test_missing_inverse_stops_after_forward_before_any_undo(self):
        root = self.fixture()
        (root / "expected/chain-undo-03.json").unlink()
        say = A.Session.say
        deliveries = []
        def observed(sess, text, **kw):
            deliveries.append(text)
            return say(sess, text, **kw)
        with mock.patch.object(A.Session, "say", observed): results = self.run_chain(root)
        self.assertEqual([(r.id, r.codes) for r in results],
                         [(f"chain-{n:02d}", []) for n in range(1, 5)] + [("chain-undo-03", ["missing-undo-golden"])])
        self.assertFalse(any(t.startswith("undo ") for t in deliveries))
        self.assertEqual(results[-1].facts["inverses"], 0)
        # An existing malformed inverse is still rejected before scratch.
        (root / "expected/chain-undo-03.json").write_text("{}")
        with mock.patch.object(A, "Session") as session:
            with self.assertRaises(A.InputError): self.run_chain(root)
            session.assert_not_called()

    def test_slotless_plan_question_pins_exact_question_and_state(self):
        root = self.fixture()
        rows = mini()[:2]
        rows[0].update(skill="page.home", texts=["keep the headline, change the intro"],
                       replies=[{"skill": "page.home", "slots": {}}])
        question = "What should the headline or the intro say?"
        rows[0]["expect"] = {"skills": ["page.home", "none"], "dispositions": ["question"],
                             "request": {"skill": "page.home", "slots": {}, "asked_slot": None,
                                         "calls": [], "attachments": [], "question": question}}
        rows[1].update(skill="page.home", texts=["intro: Come browse our shelves. Say hello."],
                       replies=[{"skill": "page.home", "slots": {"intro": "Come browse our shelves. Say hello."}}])
        rows[1]["expect"] = {"skills": ["page.home"], "dispositions": ["proposed"], "undo": True,
                             "expected": "chain-02.json", "ops": [{"op": "store.set_intro", "args": {"text": "Come browse our shelves. Say hello."}}]}
        self.write_rows(root, rows)
        # Stop on the first question by corrupting its exact question pin.
        rows[0]["expect"]["request"]["question"] = "Wrong question"
        self.write_rows(root, rows)
        self.assertEqual(self.run_chain(root)[-1].codes, ["request-leak"])
        del rows[0]["expect"]["request"]["question"]
        self.write_rows(root, rows)
        with self.assertRaises(A.InputError): self.run_chain(root)

    def test_readonly_continuation_closes_request_without_false_leak(self):
        root = self.fixture()
        rows = mini()[:2]
        for row in rows: row.update(skill="social.item")
        rows[0].update(texts=["write an instagram caption for the honey"], replies=[{"skill": "social.item", "slots": {"item": "honey"}}])
        rows[0]["expect"] = {"skills": ["social.item", "none"], "dispositions": ["question"], "request": {
            "skill": "social.item", "slots": {}, "asked_slot": "item", "calls": [], "attachments": []}}
        rows[1].update(texts=["the lemons instead"], replies=[{"skill": "social.item", "slots": {"item": "lemons"}}])
        rows[1]["expect"] = {"skills": ["social.item", "none"], "dispositions": ["answer"], "reply_contains": ["I haven't posted anything."]}
        self.write_rows(root, rows)
        self.assertEqual([r.codes for r in self.run_chain(root)], [[], []])
        say = A.Session.say
        def stale(sess, text, **kw):
            out = say(sess, text, **kw)
            if out[1] == "answer": sess.conv.db.execute("UPDATE open_requests SET state = 'open'")
            return out
        with mock.patch.object(A.Session, "say", stale): results = self.run_chain(root)
        self.assertIn("request-leak", results[-1].codes)

    def test_cli_exits_and_sanitized_summary(self):
        root = self.fixture(); output = io.StringIO()
        with contextlib.redirect_stdout(output): self.assertEqual(A.main(["--chain", str(root / "chain-mini.jsonl")]), 0)
        for secret in (str(root), A.OWNER, A.CHAT, *[r["texts"][0] for r in mini()[:3]]): self.assertNotIn(secret, output.getvalue())
        failure = A.Result("chain-01"); failure.fail("wrong-diff")
        with mock.patch.object(A, "run_chain", return_value=[failure]), contextlib.redirect_stdout(io.StringIO()): self.assertEqual(A.main(["--chain", "x"]), 1)


class Prerequisites(unittest.TestCase):
    def row(self, name):
        return copy.deepcopy(next(r for r in A.load_rows(A.DEFAULT_ROWS) if r['id'] == name))

    def test_restore_hidden_by_name_and_undo(self):
        r = A.run_row(self.row('primary-item-restore'), fixture_root=A.FIXTURE_ROOT)
        self.assertEqual(r.codes, [])
        self.assertEqual(r.dispositions, ['proposed'])
        self.assertEqual(r.facts['undo'], 'identical')

    def test_hidden_stays_refused_for_edit_and_held_for_restore(self):
        r = self.row('primary-item-restore')
        r['skill'] = 'item.edit'
        r['texts'] = ['change the lemons description to: Bright fruit.']
        r['replies'] = [{'skill': 'item.edit', 'slots': {'item': 'lemons', 'description': 'Bright fruit.'}}]
        r['expect'] = {'skills': ['item.edit', 'none'], 'dispositions': ['refused'], 'reply_contains': ['hidden']}
        self.assertEqual(A.run_row(r, fixture_root=A.FIXTURE_ROOT).codes, [])
        r = self.row('acc-refuse-04')
        self.assertEqual(A.run_row(r, fixture_root=A.FIXTURE_ROOT).codes, [])

    def test_reschedule_undo_restores_exact_bytes(self):
        r = A.run_row(self.row('primary-hike-reschedule'), fixture_root=A.FIXTURE_ROOT)
        self.assertEqual(r.codes, [])
        self.assertEqual(r.facts['undo'], 'identical')

    def test_missing_guest_counts_still_refuses_reschedule_undo_without_write(self):
        r = self.row('primary-hike-reschedule')
        s = A.Session(r, load_skills(), A.FIXTURE_ROOT)
        self.addCleanup(s.close)
        self.assertEqual(s.say(r['texts'][0])[1], 'proposed')
        self.assertEqual(s.say('yes ' + s.drafts()[-1]['code'])[1], 'approved')
        (s.repo.state / 'guests.sqlite3').unlink()
        before = s.snapshot()
        self.assertEqual(s.say('undo')[1], 'not-drafted')
        self.assertEqual(s.snapshot(), before)


if __name__ == '__main__': unittest.main()

"""AV1109-18: the forty non-primary offline acceptance rows (SKILLS-SPEC 4.3) and the group counts.

Every row is synthetic and replays recorded interpreter replies through the real Conversation, Dispatcher, Editor and sitegen on a scratch
worktree (hass/skills/acceptance_run.py, unchanged logic except the sender and paused-approval controls). Nothing here is a human acceptance.
"""
import collections
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from hass.content_model import REPO_ROOT
from hass.skills import acceptance_run as A, load_skills

TEMPLATE = REPO_ROOT / "reports" / "hass" / "SKILLS-ACCEPTANCE-TEMPLATE.md"
WANT = {"vague": 10, "typo": 8, "multi": 8, "refuse": 8, "turns": 6}
IDS = [f"acc-{tag}-{n:02d}" for tag, count in WANT.items() for n in range(1, count + 1)]
# Rows pinned to today's behaviour where the real code asks and the row says it should (acc-turns-04: a topic change never drafts the old ask).
PINNED_QUESTION = {"acc-turns-04": "question"}
# Rows that genuinely FAIL today (SKILLS-SPEC 4.3 asks for a draft, the code does not give one). They keep their spec expectation and are
# recorded here, not accepted: when the owner fixes the code the row passes, this test fails, and the entry is deleted (README, "Known failures").
KNOWN_FAILURES = {"acc-multi-01": ["wrong-disposition"]}


def group_problems(rows, registry_names):
    """Row-id problems of the forty: missing, duplicate, unknown tag, double tag, extra non-primary rows. Primary/photo rows are not counted."""
    new = [r for r in rows if r["id"].startswith("acc-")]
    problems = [f"missing {i}" for i in IDS if i not in {r["id"] for r in new}] + [f"extra {r['id']}" for r in new if r["id"] not in IDS]
    problems += [f"duplicate {i}" for i, n in collections.Counter(r["id"] for r in new).items() if n > 1]
    for r in new:
        tag = r["tag"]
        if tag not in WANT: problems.append(f"unknown tag {r['id']}")
        elif r["id"] != f"acc-{tag}-" + r["id"].rsplit("-", 1)[1]: problems.append(f"wrong group {r['id']}")
    counts = collections.Counter(r["tag"] for r in new)
    if counts != collections.Counter(WANT): problems.append(f"counts {dict(counts)}")
    names = [r["skill"] for r in rows if r["tag"] == "primary"]
    if set(names) != set(registry_names): problems.append("primary set differs from the registry")
    return problems


class Groups(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.registry = load_skills()
        cls.rows = A.load_rows(A.DEFAULT_ROWS)
        cls.new = [r for r in cls.rows if r["id"].startswith("acc-")]
        cls.by_id = {r["id"]: r for r in cls.new}
        cls.results = {r.id: r for r in A.run_rows(A.DEFAULT_ROWS, registry=cls.registry, only=set(IDS))}

    def play(self, rid):
        row = self.by_id[rid]
        sess = A.Session(row, self.registry, A.FIXTURE_ROOT)
        self.addCleanup(sess.close)
        photos, offsets, senders = A.load_photos(row, A.FIXTURE_ROOT), row.get("offsets") or [0] * len(row["texts"]), row.get("senders") or ["owner"] * len(row["texts"])
        out = [sess.say(t, photo=photos.get(i), minutes=1 + offsets[i], sender=A.STRANGER if senders[i] == "stranger" else A.OWNER) for i, t in enumerate(row["texts"])]
        return sess, out

    def ops(self, sess):
        return [o["op"] for o in json.loads(sess.drafts()[-1]["ops_json"])]

    def test_exact_forty_exclusive_groups(self):
        names = set(self.registry.skills)
        self.assertEqual(group_problems(self.rows, names), [])
        self.assertEqual(collections.Counter(r["tag"] for r in self.new), collections.Counter(WANT))
        self.assertEqual(len(self.new), 40)
        self.assertEqual(len([r for r in self.rows if r["tag"] == "primary"]), len(names))  # registry-derived, not the historical 32/72
        self.assertEqual(len(self.rows), len(names) + len([r for r in self.rows if r["tag"] == "photo"]) + 40)
        some = self.new[0]
        self.assertEqual(group_problems([r for r in self.rows if r is not some], names), [f"missing {some['id']}", "counts " + str(dict(collections.Counter(r["tag"] for r in self.new if r is not some)))])
        self.assertIn(f"duplicate {some['id']}", group_problems(self.rows + [some], names))
        self.assertIn(f"unknown tag {some['id']}", group_problems([dict(r, tag="primary") if r is some else r for r in self.rows], names))
        self.assertIn("extra acc-vague-11", group_problems(self.rows + [dict(some, id="acc-vague-11")], names))
        self.assertTrue(any(p.startswith("wrong group") for p in group_problems([dict(r, tag="typo") if r is some else r for r in self.rows], names)))

    def test_all_forty_recorded_cases_pass(self):
        self.assertEqual(sorted(self.results), sorted(IDS))
        self.assertEqual({i: r.codes for i, r in self.results.items() if not r.ok}, KNOWN_FAILURES)  # genuine failures are recorded, never passed
        self.assertFalse(A.summarize(list(self.results.values()))["met"])  # so the thresholds are honestly not met until the owner fixes them
        for rid in IDS:  # no row was skipped: every recorded reply was used and every disposition is the one the row names
            if rid not in KNOWN_FAILURES: self.assertEqual(self.results[rid].dispositions, self.by_id[rid]["expect"]["dispositions"], rid)
        goldens = {p.stem for p in (A.FIXTURE_ROOT / "expected").glob("acc-*.json")}
        self.assertEqual(goldens, {r["id"] for r in self.new if r["expect"].get("expected")})  # proposed rows only: no empty goldens, no orphans

    def test_spec_expectations_are_not_weakened(self):
        multi = self.by_id["acc-multi-01"]  # all three shelf-check slots are in the message: zero questions, one exact approved draft, undo
        self.assertEqual(multi["expect"], {"skills": ["stock.checked", "none"], "dispositions": ["proposed"], "expected": "acc-multi-01.json", "undo": True})
        self.assertEqual(sorted(multi["replies"][0]["slots"]), ["in", "limited", "out"])
        self.assertEqual(self.results["acc-multi-01"].codes, ["wrong-disposition"])  # the router tie is the real failure
        self.assertEqual(self.results["acc-multi-01"].dispositions, ["question"])
        golden = json.loads((A.FIXTURE_ROOT / "expected" / "acc-multi-01.json").read_text("utf-8"))
        self.assertEqual([d["path"] for d in golden["diff"] if d["path"].endswith(".available")],
                         [f"products[photo-product-{n}].available" for n in ("017", "056", "076")])
        self.assertEqual([d["after"] for d in golden["diff"] if d["path"].endswith(".available")], ["yes", "no", "limited"])
        for rid in IDS:  # every row that ends in a proposal also runs the real undo and its own yes: no row opts out
            if self.by_id[rid]["expect"].get("expected"): self.assertIs(self.by_id[rid]["expect"].get("undo"), True, rid)
        for rid in ("acc-turns-02", "acc-turns-05"):
            self.assertEqual(self.results[rid].facts["undo"], "identical", rid)

    def test_vague_and_hostile_never_draft(self):
        for rid in [i for i in IDS if i.startswith(("acc-vague", "acc-refuse-01", "acc-refuse-03", "acc-refuse-04", "acc-refuse-05", "acc-refuse-06", "acc-refuse-07"))]:
            sess, out = self.play(rid)
            self.assertEqual(sess.drafts(), [], rid)  # every turn: no draft table row at all
            self.assertEqual(sess.snapshot(), sess.baseline, rid)
            self.assertNotIn("proposed", [o[1] for o in out], rid)
        for rid in [i for i in IDS if i.startswith("acc-vague")]:
            self.assertTrue(all(o[1] in ("question", "refused", "backlog") for o in self.play(rid)[1]), rid)
            self.assertLessEqual(len(self.play(rid)[1][-1][2]), 3, rid)  # one reply, not a draft

    def test_stranger_never_reaches_interpreter(self):
        sess, out = self.play("acc-refuse-07")
        self.assertEqual((sess.interp.calls, [o[1] for o in out], [o[2] for o in out]), (0, ["ignored"], [[]]))
        self.assertEqual((sess.drafts(), len(sess.out.sent), sess.conv.db.execute("SELECT count(*) FROM outbox").fetchone()[0]), ([], 0, 0))
        self.assertEqual(sess.snapshot(), sess.baseline)
        self.assertEqual(sess.observed, [])  # no skill ran: nothing was planned, asked or logged to the backlog

    def test_pause_blocks_apply(self):
        sess, out = self.play("acc-refuse-08")
        self.assertEqual([o[1] for o in out], ["pause", "proposed"])
        code = sess.drafts()[-1]["code"]
        _m, disposition, _t = sess.say(f"yes {code}")
        self.assertEqual((disposition, sess.snapshot() == sess.baseline, sess.drafts()[-1]["state"]), ("paused", True, "proposed"))
        self.assertEqual(self.results["acc-refuse-08"].facts["approval"], "paused")

    def test_multi_item_is_one_complete_draft(self):
        want = {"acc-multi-02": 2, "acc-multi-03": 2, "acc-multi-04": 3, "acc-multi-05": 2, "acc-multi-06": 2, "acc-multi-07": 2, "acc-multi-08": 2}
        for rid, n in want.items():
            sess, _out = self.play(rid)
            self.assertEqual(len(sess.drafts()), 1, rid)  # one independently approvable draft
            self.assertGreaterEqual(len(self.ops(sess)), n, rid)
            self.assertLessEqual(len(self.ops(sess)), 20, rid)
        sess, _out = self.play("acc-multi-04")
        self.assertEqual(self.ops(sess), ["product.hide"] * 3)
        golden = json.loads((A.FIXTURE_ROOT / "expected" / "acc-multi-04.json").read_text("utf-8"))
        self.assertEqual(len(golden["diff"]), 3)
        tmp = Path(tempfile.mkdtemp(prefix="acc-groups-"))  # a corrupted golden (one hidden product dropped) fails the exact diff
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "expected").mkdir()
        golden["diff"] = golden["diff"][:2]
        (tmp / "expected" / "acc-multi-04.json").write_text(json.dumps(golden), "utf-8")
        (tmp / "messages.jsonl").write_text(json.dumps(self.by_id["acc-multi-04"]) + "\n", "utf-8")
        [res] = A.run_rows(tmp / "messages.jsonl", registry=self.registry)
        self.assertEqual(res.codes, ["wrong-diff"])

    def test_claim_absent_from_owner_is_rejected(self):
        row = self.by_id["acc-refuse-02"]
        self.assertIn("organic", json.dumps(row["replies"]))  # the recorded reply does carry the claim the owner never made
        sess, out = self.play("acc-refuse-02")
        self.assertEqual(sess.drafts()[-1]["state"], "proposed")
        self.assertNotIn("organic", sess.drafts()[-1]["ops_json"].casefold())
        self.assertNotIn("1990", sess.drafts()[-1]["ops_json"])
        self.assertIn("Left off", out[-1][2][0])
        self.assertNotIn("organic", " ".join(row["texts"]).casefold())  # the claim is the interpreter's alone: the owner's words never carry it
        self.assertNotIn("1990", " ".join(row["texts"]))

    def test_turns_revision_topic_and_expiry_are_isolated(self):
        sess, out = self.play("acc-turns-03")  # a correction supersedes the waiting draft: the old code cannot apply
        states = [d["state"] for d in sess.drafts()]
        self.assertEqual(states[-1], "proposed")
        self.assertNotIn("proposed", states[:-1])
        old = sess.drafts()[0]["code"]
        sess.say(f"yes {old}")
        self.assertEqual(sess.snapshot(), sess.baseline)
        self.assertEqual(sess.drafts()[-1]["state"], "proposed")
        self.assertIn("Friday 9am–8pm", json.dumps(self.results["acc-turns-03"].row["replies"], ensure_ascii=False))
        golden = json.loads((A.FIXTURE_ROOT / "expected" / "acc-turns-03.json").read_text("utf-8"))
        self.assertIn("8pm", json.dumps(golden, ensure_ascii=False))
        self.assertNotIn("9am–7pm", json.dumps(golden, ensure_ascii=False))  # only the corrected value changes
        sess, out = self.play("acc-turns-05")  # late short answer after 30 minutes: no old slots, then a fresh complete request drafts
        self.assertEqual([o[1] for o in out], ["question", "question", "proposed"])
        self.assertEqual(self.by_id["acc-turns-05"]["offsets"][1], 31)
        self.assertGreater(self.by_id["acc-turns-05"]["offsets"][1], 30)
        self.assertEqual(sess.interp.calls, 3)  # the late "10am" went to the model again: nothing was answered from the expired request
        sess, out = self.play("acc-turns-04")  # a topic change never turns the old hike ask into a draft
        self.assertEqual([d for d in sess.drafts() if d["state"] == "proposed"], [])
        sess, out = self.play("acc-turns-06")  # photo first, words later: the stored photo is consumed by the real dispatch
        self.assertEqual(out[0][1], "photo-question")
        self.assertEqual(out[-1][1], "proposed")
        self.assertEqual(self.results["acc-turns-06"].facts["pictures"], 1)
        sess, out = self.play("acc-turns-01")
        self.assertEqual([o[1] for o in out], ["question", "question", "proposed"])
        self.assertEqual(len(sess.drafts()), 1)

    def test_group_report_counts_once_and_scrubs_text(self):
        text = TEMPLATE.read_text("utf-8")
        rows = {m[0]: (int(m[1]), int(m[2])) for m in re.findall(r"^\| (vague|typo|multi|refuse|turns) \| (\d+) \| (\d+) \|", text, re.M)}
        failed = {g: sum(1 for i, r in self.results.items() if not r.ok and self.by_id[i]["tag"] == g) for g in WANT}
        measured = {g: (n, failed[g]) for g, n in collections.Counter(r["tag"] for r in self.new).items()}
        self.assertEqual(rows, measured)  # counted once each by its single primary tag, with the failures actually executed
        self.assertEqual(failed, {"vague": 0, "typo": 0, "multi": 1, "refuse": 0, "turns": 0})
        self.assertIn("acc-multi-01", text)  # the known failure is named in the report, not hidden
        self.assertIn("synthetic", text.casefold())
        self.assertIn("offline", text.casefold())
        self.assertIn("human", text.casefold())
        for r in self.new:  # no owner sentence is printed in the report
            for t in r["texts"]:
                if len(t) > 12: self.assertNotIn(t, text, r["id"])


if __name__ == "__main__":
    unittest.main()

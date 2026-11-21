"""Offline contract tests for the NPP receipt evidence boundary."""

import json
import unittest

from hass.npp.evidence import Evidence, role_for, validate


_AT = "2000-01-01T00:00:00Z"
_CHANGE = "fixture:edit-1"
_DRAFT = "0a" * 32
_COMMIT = "aBcD012"


def _collected():
    evidence = Evidence()
    evidence.stage("S13", 4, 5, "fallback", "use-original")
    evidence.stage("S1", 0, 0, "ok")
    evidence.model("picture", "fixture-provider:picture-2", "fixture-provider:picture-2")
    evidence.model("identify", "fixture/model-1", "fixture/model-2")
    evidence.model("edit_map", "fixture-model-3", None)
    for code in ("use-original", "retry", "use-original"):
        evidence.fallback(code)
    evidence.check("private-cost", "pass", "match")
    evidence.check("private-count", "fail", "no-match")
    evidence.check("card", "pass")
    evidence.approval(1, "G", _AT, _CHANGE, _DRAFT)
    evidence.publish(_CHANGE, _COMMIT, "seen")
    return evidence


# Each row corrupts one otherwise valid argument. Exercise the same rule at
# both boundaries: rejecting imported documents does not protect the builder.
_VALID_CALLS = {
    "stages": ("stage", dict(stage="S1", started_ms=0, ended_ms=1, outcome="ok", code="ready")),
    "models": ("model", dict(step="picture", pinned="fixture:picture", returned="fixture:picture")),
    "fallbacks": ("fallback", dict(code="retry")),
    "checks": ("check", dict(name="card", verdict="pass", private="match")),
    "approval": ("approval", dict(version=1, role="Mike", approved_at=_AT, change_id=_CHANGE, draft_hash=_DRAFT)),
    "publish": ("publish", dict(change_id=_CHANGE, commit=_COMMIT, live_verify="pending")),
}
_BAD_VALUES = (
    ("stages", "stage", "S0"),
    ("stages", "stage", "S14"),
    ("stages", "stage", "S01"),
    ("stages", "outcome", "pending"),
    ("stages", "started_ms", -1),
    ("stages", "ended_ms", -1),
    ("stages", "started_ms", 2),  # Reversed, but both times are nonnegative.
    ("stages", "ended_ms", "1"),
    ("stages", "started_ms", True),
    ("stages", "ended_ms", float("nan")),
    ("stages", "code", ".needs-leading-alnum"),
    ("models", "step", "Picture"),
    ("models", "pinned", None),
    ("models", "returned", []),
    ("fallbacks", "code", "a" * 49),
    ("checks", "name", "card\n"),
    ("checks", "verdict", "ok"),
    ("checks", "private", "unknown"),
    ("approval", "version", 0),
    ("approval", "version", True),
    ("approval", "role", "g"),
    ("approval", "approved_at", -1),
    ("approval", "approved_at", "2000-02-30T00:00:00Z"),
    ("approval", "approved_at", "2000-01-01T00:00:00+00:00"),
    ("approval", "change_id", ""),
    ("approval", "change_id", "x" * 65),
    ("approval", "draft_hash", "abc123"),
    ("approval", "draft_hash", "a" * 65),
    ("publish", "change_id", "fixture/edit"),
    ("publish", "commit", "deadbeeg"),
    ("publish", "live_verify", "ok"),
    # Synthetic canaries: cost, reserved fictional phone, reserved mailbox,
    # caption text, and a home prefix embedded in an otherwise valid model ID.
    ("checks", "private", "$0.00"),
    ("approval", "role", "+12025550100"),
    ("models", "returned", "fixture@example.invalid"),
    ("models", "pinned", "Synthetic caption canary"),
    ("models", "returned", "fixture/home/demo"),
)


def _invalid_calls():
    for index, (section, field, value) in enumerate(_BAD_VALUES):
        method, valid = _VALID_CALLS[section]
        yield index, section, field, method, valid, {**valid, field: value}, value


class EvidenceTests(unittest.TestCase):
    def test_c1_collect(self):
        # Dropped records, ignored optional arguments or stale singular records
        # would erase part of a later job's evidence.
        evidence = _collected()
        doc = evidence.doc()
        self.assertEqual(doc["stages"][0], dict(stage="S13", started_ms=4, ended_ms=5,
                                                outcome="fallback", code="use-original"))
        self.assertEqual(doc["checks"], [dict(name="private-cost", verdict="pass", private="match"),
                                          dict(name="private-count", verdict="fail", private="no-match"),
                                          dict(name="card", verdict="pass", private=None)])
        self.assertEqual(doc["approval"], dict(version=1, role="G", approved_at=_AT,
                                              change_id=_CHANGE, draft_hash=_DRAFT))
        self.assertEqual(doc["publish"], dict(change_id=_CHANGE, commit=_COMMIT, live_verify="seen"))
        evidence.approval(2, "owner", 0, "fixture:edit-2", _DRAFT)
        evidence.publish("fixture:edit-2")
        self.assertEqual(evidence.doc()["approval"]["version"], 2)
        self.assertEqual(evidence.doc()["publish"], dict(change_id="fixture:edit-2", commit=None, live_verify=None))
        for n in range(1, 14):
            for outcome in ("ok", "fallback", "failed", "skipped"):
                evidence.stage(f"S{n}", 0, 0.5, outcome)
        for live_verify in ("pending", "failed"):
            evidence.publish("fixture:edit-2", live_verify=live_verify)
            self.assertEqual(evidence.doc()["publish"]["live_verify"], live_verify)
        self.assertEqual(validate(evidence.doc()), [])

    def test_c2_doc_shape(self):
        # C2: detect a renamed key, stage reordering, duplicate fallbacks, or
        # treating an absent provider ID as drift.
        self.assertEqual(Evidence().doc(), dict(evidence_version=1, stages=[], models=[],
                                               fallbacks=[], checks=[], approval=None, publish=None))
        doc = _collected().doc()
        self.assertEqual(set(doc), set(Evidence().doc()))
        self.assertEqual([row["stage"] for row in doc["stages"]], ["S13", "S1"])
        self.assertEqual(doc["stages"][1], dict(stage="S1", started_ms=0, ended_ms=0,
                                                outcome="ok", code=None))
        self.assertEqual(doc["models"], [
            dict(step="picture", pinned="fixture-provider:picture-2", returned="fixture-provider:picture-2", drift=False),
            dict(step="identify", pinned="fixture/model-1", returned="fixture/model-2", drift=True),
            dict(step="edit_map", pinned="fixture-model-3", returned=None, drift=False),
        ])
        self.assertEqual(doc["fallbacks"], ["retry", "use-original"])
        self.assertEqual(validate(doc), [])

    def test_c3_role(self):
        # Returning the configured name verbatim or stripping whitespace would
        # bypass the exact-name allowlist.
        for name, expected in (("g", "G"), ("mIkE", "Mike"), (" Mike", "owner"),
                               ("Mike Jr", "owner"), ("fixture@example.invalid", "owner"),
                               ("+12025550100", "owner"), (12, "owner"), (None, "owner")):
            self.assertEqual(role_for("fixture-chat", {"fixture-chat": name}), expected)
        self.assertEqual(role_for("Mike", {}), "owner")
        self.assertEqual(role_for("fixture-chat", None), "owner")

    def test_c4_validate_rejects(self):
        # Reject independently corrupted JSON, not just output of Evidence.
        for index, section, field, method, valid, bad, _ in _invalid_calls():
            with self.subTest(case=index, section=section, field=field):
                evidence = Evidence()
                getattr(evidence, method)(**valid)
                doc = evidence.doc()
                self.assertEqual(validate(doc), [])
                if section == "fallbacks":
                    doc[section][0] = bad[field]
                else:
                    row = doc[section][0] if isinstance(doc[section], list) else doc[section]
                    row[field] = bad[field]
                    if section == "models":
                        row["drift"] = row["returned"] is not None and row["returned"] != row["pinned"]
                self.assertTrue(validate(doc))
        for section in (None, "stages", "models", "checks", "approval", "publish"):
            with self.subTest(extra_key_in=section):
                doc = _collected().doc()
                row = doc if section is None else doc[section]
                if isinstance(row, list):
                    row = row[0]
                row["extra-fixture-field"] = "synthetic"
                problems = validate(doc)
                self.assertTrue(problems)
                self.assertNotIn("extra-fixture-field", str(problems))
        for section, bad in (("fallbacks", [dict(extra="synthetic")]), ("stages", {}),
                             ("approval", []), ("evidence_version", 2), ("evidence_version", True)):
            with self.subTest(wrong_shape_or_version=section):
                doc = _collected().doc()
                doc[section] = bad
                self.assertTrue(validate(doc))
        doc = _collected().doc()
        doc["models"][2]["drift"] = True
        self.assertTrue(validate(doc))
        self.assertTrue(validate(None))

    def test_c5_refuse_at_call(self):
        # The same invalid input must fail before it can affect a populated
        # receipt. Error text must not quote the rejected text or unknown data.
        evidence = _collected()
        before = evidence.doc()
        for index, section, field, method, _, bad, value in _invalid_calls():
            with self.subTest(case=index, section=section, field=field):
                with self.assertRaises(ValueError) as raised:
                    getattr(evidence, method)(**bad)
                if isinstance(value, str) and value:
                    self.assertNotIn(value, str(raised.exception))
                self.assertEqual(evidence.doc(), before)

    def test_c6_deterministic(self):
        # A snapshot must not leave writable aliases that would change the next
        # serialization even when no collector was called.
        evidence = _collected()
        snapshot = evidence.doc()
        expected = json.dumps(snapshot, sort_keys=True, allow_nan=False).encode()
        snapshot["models"][0]["pinned"] = "changed-by-reader"
        snapshot["checks"].clear()
        snapshot["approval"]["version"] = 3
        self.assertEqual(json.dumps(evidence.doc(), sort_keys=True, allow_nan=False).encode(), expected)
        self.assertEqual(json.dumps(_collected().doc(), sort_keys=True, allow_nan=False).encode(), expected)


if __name__ == "__main__":
    unittest.main()

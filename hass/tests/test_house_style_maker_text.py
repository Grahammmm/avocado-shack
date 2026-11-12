"""RF2311-10: check_maker rejects schema-invalid name/place/story text (same policy as content_model) and never raises."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass import house_style as hs  # noqa: E402
from hass.content_model import TEXT_LIMITS  # noqa: E402

SPEC = hs.load_spec()
GOOD = {"name": "Fixture Farm", "place": "Cambria, California",
        "story": "Fixture Farm makes pantry goods in a small workshop. The family packs each batch by hand."}
FIELDS = ("name", "place", "story")


def check(rec, **kw):
    return hs.check_maker(rec, SPEC, **kw)


def text_gate(out):
    return next(c for c in out["checks"] if c["name"] == "plain text")


def with_(field, value):
    rec = dict(GOOD)
    rec[field] = value
    return rec


class MakerTextTests(unittest.TestCase):
    def assert_hard_fail(self, rec, label):
        out = check(rec)
        gate = text_gate(out)
        self.assertFalse(gate["ok"], label)
        self.assertTrue(gate["hard"], label)
        self.assertEqual(gate["detail"], "invalid maker text", label)
        self.assertFalse(out["pass"], label)
        self.assertIn("plain text", out["hard_failures"], label)
        self.assertEqual(len(out["checks"]), 8, label)

    def test_blank_whitespace_and_control_maker_text_hard_fail(self):
        for label, rec in {
            "empty name": with_("name", ""),
            "space name": with_("name", "   "),
            "leading name": with_("name", " Fixture Farm"),
            "trailing place": with_("place", "Cambria, California "),
            "leading story": with_("story", " " + GOOD["story"]),
            "nul name": with_("name", "Farm\x00"),
            "zero-width place": with_("place", "Cambria,\u200b California"),
            "bidi story": with_("story", GOOD["story"].replace("small", "sm\u202eall")),
        }.items():
            with self.subTest(label):
                self.assert_hard_fail(rec, label)

    def test_nonstring_and_missing_text_return_complete_failed_results(self):
        for field in FIELDS:
            for bad in (None, True, 42, ["x"], {"a": 1}):
                with self.subTest(field=field, value=repr(bad)):
                    self.assert_hard_fail(with_(field, bad), field)
            with self.subTest(field=field, value="missing"):
                rec = {k: v for k, v in GOOD.items() if k != field}
                out = check(rec)
                self.assertFalse(text_gate(out)["ok"])
                self.assertFalse(out["pass"])
                self.assertEqual(len(out["checks"]), 8)

    def test_text_length_boundaries_use_existing_maker_limits(self):
        for field in FIELDS:
            limit = TEXT_LIMITS["maker"][field]
            with self.subTest(field=field, edge="limit"):
                self.assertTrue(text_gate(check(with_(field, "a" * limit)))["ok"])
            with self.subTest(field=field, edge="over"):
                self.assert_hard_fail(with_(field, "a" * (limit + 1)), field)
        self.assertEqual([TEXT_LIMITS["maker"][f] for f in FIELDS], [80, 60, 600])

    def test_forbidden_text_and_unicode_policy_matches_canonical_validator(self):
        for tok in ("<", ">", "$", "{{", "}}"):
            for field in FIELDS:
                with self.subTest(token=tok, field=field):
                    self.assert_hard_fail(with_(field, f"Fixture{tok}Farm"), field)
        for ok_name in ("Caf\u00e9 No. 5", "Mary\u2019s Farm", "Fa\u00e7ade 2 Farm"):
            with self.subTest(name=ok_name):
                self.assertTrue(text_gate(check(with_("name", ok_name)))["ok"])

    def test_valid_records_preserve_full_results_and_other_checks(self):
        out = check(GOOD)
        self.assertTrue(out["pass"], out)
        self.assertEqual(text_gate(out)["detail"], "ok")
        self.assertEqual([c["name"] for c in out["checks"]],
                         ["fields name, place, story (+url)", "plain text", "limits", "url is public https or absent",
                          "place like 'Town, California'", "key equals name",
                          "story length like the others", "story ends with a full stop"])
        self.assertEqual(out, check(GOOD))
        self.assertTrue(check({**GOOD, "url": "https://example.com/"})["pass"])
        self.assertFalse(check({**GOOD, "url": "http://example.com/"})["pass"])
        self.assertFalse(next(c for c in check(GOOD, key="Other")["checks"] if c["name"] == "key equals name")["ok"])

    def test_original_values_are_validated_without_input_repair(self):
        rec = with_("name", " Fixture Farm")
        before = copy.deepcopy(rec)
        first = check(rec)
        self.assertEqual(rec, before)
        self.assertEqual(first, check(rec))
        self.assertEqual(rec["name"], " Fixture Farm")
        num = with_("story", 42)
        check(num)
        self.assertEqual(num["story"], 42)


if __name__ == "__main__":
    unittest.main()

"""RF0600-12: description scoring keeps owner-text line breaks as clause boundaries."""
import copy
import json
import os
import subprocess
import sys
import unittest

from hass import claims, house_style

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DESC = "Organic honey from Fixture Farm. Spoon a little onto toast."
NAME = "no unstated claim term"


def check(owner, desc=DESC):
    return house_style.check_description(desc, owner_text=owner)


def claim_ok(res):
    return next(c for c in res["checks"] if c["name"] == NAME)["ok"]


def gate(owner):
    draft = {"ops": [{"op": "set"}], "records": [{"collection": "products", "key": "synthetic-product",
                                                 "before": {"description": ""}, "after": {"description": DESC}}]}
    return claims.unstated(draft, owner, {})


class OwnerClauseTests(unittest.TestCase):
    def test_previous_line_negator_does_not_deny_organic(self):
        res = check("not local\norganic")
        self.assertTrue(claim_ok(res))
        self.assertTrue(res["pass"])
        self.assertEqual(gate("not local\norganic"), [])

    def test_supported_line_separators_keep_gate_parity(self):
        for sep in ("\n", "\r\n", "\r", "\u2028", "\u2029", "\n\n", "\n "):
            owner = "not local" + sep + "organic"
            self.assertTrue(claim_ok(check(owner)), repr(sep))
            self.assertEqual(gate(owner), [], repr(sep))
        self.assertTrue(claim_ok(check("not local\norganic\n")))
        self.assertTrue(claim_ok(check("\n\nnot local\n\norganic")))

    def test_same_line_denial_and_three_word_window_unchanged(self):
        for owner in ("not organic", "not local organic", "not very organic", "not really very organic",
                      "isn't organic"):
            self.assertFalse(claim_ok(check(owner)), owner)
            self.assertEqual(claim_ok(check(owner)), gate(owner) == [], owner)
        self.assertTrue(claim_ok(check("not local; organic")))
        self.assertTrue(claim_ok(check("organic")))

    def test_claim_on_new_line_still_honors_its_own_negator(self):
        self.assertFalse(claim_ok(check("not local\nnot organic")))
        self.assertTrue(claim_ok(check("not organic\norganic")))
        self.assertTrue(claim_ok(check("organic\nnot organic")))
        self.assertEqual(claim_ok(check("organic\nnot organic")), gate("organic\nnot organic") == [])
        self.assertEqual(claim_ok(check("or\nganic")), gate("or\nganic") == [])

    def test_unaffected_results_and_inputs_are_pure(self):
        spec = house_style.load_spec()
        spec0 = copy.deepcopy(spec)
        for owner in ("organic", "", None, "Ｏrganic", "no claims here"):
            a = house_style.check_description(DESC, spec, owner_text=owner)
            b = house_style.check_description(DESC, spec, owner_text=owner)
            self.assertEqual(a, b)
        self.assertEqual(spec, spec0)
        self.assertFalse(claim_ok(house_style.check_description(DESC, spec, owner_text=None)))
        self.assertTrue(claim_ok(house_style.check_description("Honey on toast.", spec, owner_text=None)))
        owner = "not local\norganic"
        copy_owner = str(owner)
        check(owner)
        self.assertEqual(owner, copy_owner)

    def test_check_text_cli_keeps_json_and_exit_contract(self):
        def run(owner):
            return subprocess.run([sys.executable, "-B", "hass/house_style.py", "check-text", DESC, "--owner", owner],
                                  cwd=ROOT, capture_output=True, text=True)
        ok = run("not local\norganic")
        self.assertEqual((ok.returncode, ok.stderr), (0, ""))
        self.assertEqual(json.loads(ok.stdout), check("not local\norganic"))
        bad = run("not organic")
        self.assertEqual((bad.returncode, bad.stderr), (1, ""))
        self.assertEqual(json.loads(bad.stdout), check("not organic"))


if __name__ == "__main__":
    unittest.main()

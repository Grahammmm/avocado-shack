"""RF1200-7 (H01/H13): the store hours/address limits live in the content validator, one constant set.

In-memory copies of the committed store and a throwaway writer repo (test_store_ops.StoreRepo) only.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import copy
import json
import unittest
import unittest.mock

from hass import content_model
from hass.content_model import load_and_validate, load_content, validate_store
from hass.ops import store as store_ops
from hass.tests.test_editor import git
from hass.tests.test_store_ops import SET_ADDRESS, SET_HOURS, StoreTestCase, _req

STORE = load_content().store


def problems_for(**changes):
    store = copy.deepcopy(STORE)
    store.update(changes)
    problems = []
    validate_store(problems, store)
    return problems


def lines(n, width=20):
    return [f"Line {i} ".ljust(width, "x") for i in range(n)]


class ValidatorLimitTests(unittest.TestCase):
    def test_committed_content_passes(self):
        load_and_validate()
        self.assertEqual(problems_for(), [])

    def test_boundaries_valid(self):
        self.assertEqual(problems_for(hours=lines(7)), [])
        self.assertEqual(problems_for(hours=["a" * 60, "Closed Sunday"]), [])
        self.assertEqual(problems_for(streetAddress="s" * 80, town="t" * 80), [])

    def test_over_limits_one_named_problem_each(self):
        self.assertEqual(problems_for(hours=lines(8)), ["store.hours: at most 7 lines"])
        self.assertEqual(problems_for(hours=["Closed Sunday", "a" * 61]),
                         ["store.hours[1]: longer than 60 characters"])
        self.assertEqual(problems_for(streetAddress="s" * 81), ["store.streetAddress: longer than 80 characters"])
        self.assertEqual(problems_for(town="t" * 81), ["store.town: longer than 80 characters"])

    def test_messages_follow_the_constants(self):
        with unittest.mock.patch.object(content_model, "MAX_HOURS_LINES", 2), \
                unittest.mock.patch.object(content_model, "MAX_ADDRESS_PART", 5):
            self.assertEqual(problems_for(hours=lines(3), streetAddress="Main", town="Morro Bay"),
                             ["store.town: longer than 5 characters", "store.hours: at most 2 lines"])

    def test_repeat_is_exact(self):
        self.assertEqual(problems_for(hours=["Closed Sunday", "Closed Sunday"]),
                         ["store.hours[1]: repeats an earlier line"])
        self.assertEqual(problems_for(hours=["Closed Sunday", "x", "Closed Sunday", "Closed Sunday"]),
                         ["store.hours[2]: repeats an earlier line", "store.hours[3]: repeats an earlier line"])
        self.assertEqual(problems_for(hours=["Closed Sunday", "closed sunday", "CLOSED SUNDAY"]), [])

    def test_unicode_length_is_characters_not_bytes(self):
        line = "Monday–Friday 9am–6pm · " + "x" * 36
        self.assertEqual(len(line), 60)
        self.assertGreater(len(line.encode("utf-8")), 60)
        self.assertEqual(problems_for(hours=[line]), [])
        self.assertEqual(problems_for(hours=[line + "·"]), ["store.hours[0]: longer than 60 characters"])
        self.assertEqual(problems_for(streetAddress="–" * 80), [])

    def test_wrong_types_stay_one_problem(self):
        self.assertEqual(problems_for(hours="x" * 200), ["store.hours: must be a non-empty list of lines"])
        self.assertEqual(problems_for(hours=[]), ["store.hours: must be a non-empty list of lines"])
        self.assertEqual(problems_for(streetAddress=["s" * 200]), ["store.streetAddress: must be a string"])
        self.assertEqual(problems_for(hours=[5, 5]), ["store.hours[0]: must be a string",
                                                      "store.hours[1]: must be a string"])


class OpsAndEditorTests(StoreTestCase):
    def test_ops_share_the_one_constant_set(self):
        for name in ("MAX_HOURS_LINES", "MAX_HOURS_LINE", "MAX_ADDRESS_PART"):
            self.assertIs(getattr(store_ops, name), getattr(content_model, name))

    def test_op_refusals_unchanged(self):
        repo = self.repo()
        cases = [((SET_HOURS, {"hours": lines(8)}), "at most 7 hours lines"),
                 ((SET_HOURS, {"hours": ["a" * 61]}), "hours line 0 is longer than 60 characters"),
                 ((SET_HOURS, {"hours": ["Closed", "Closed"]}), "hours lines must not repeat"),
                 ((SET_ADDRESS, {"town": "t" * 81}), "town is longer than 80 characters")]
        for op, reason in cases:
            out = repo.prepare(_req(op))
            self.assertEqual((out["result"], out.get("reason")), ("refused", reason), op)
        self.assertEqual(repo.drafts(), [])

    def test_editor_gate_rejects_bad_store_on_disk_for_unrelated_op(self):
        repo = self.repo()
        store = repo.store()
        store["hours"] = lines(8)
        (repo.wt / "hass/content/store.json").write_text(json.dumps(store, ensure_ascii=False), "utf-8")
        git(repo.wt, "commit", "-q", "-am", "hand edit")
        out = repo.prepare(_req((SET_ADDRESS, {"streetAddress": "1023 Example Street"})))
        self.assertEqual(out["result"], "invalid", out)
        self.assertIn("store.hours: at most 7 lines", out["problems"])
        self.assertEqual(repo.drafts(), [])


if __name__ == "__main__":
    unittest.main()

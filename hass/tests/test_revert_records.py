"""H06 tests: ``history.revert`` refuses an unreadable or malformed change record instead of raising (RF1200-3).

Each case applies a real store change in a throwaway StoreRepo (temp repo + temp state dir, fixture content only),
then damages ``<state>/changes/<id>.json`` and checks that undo answers ``refused`` and writes nothing.
Run: python3 -m unittest discover -s hass/tests -t . -v
"""

import json

from hass.tests.test_store_ops import NEW_HOURS, REVERT, SET_HOURS, StoreTestCase, _req

STORE = "hass/content/store.json"
SECRET = "Owner private note 7731"


class RevertRecordTests(StoreTestCase):
    def setUp(self):
        self.repo_ = self.repo()
        self.original = self.repo_.store()["hours"]
        self.change_id = self.repo_.run((SET_HOURS, {"hours": NEW_HOURS}))["change_id"]
        self.path = self.repo_.state / "changes" / f"{self.change_id}.json"
        self.record = json.loads(self.path.read_text("utf-8"))

    def write(self, data):
        self.path.write_bytes(data if isinstance(data, bytes) else json.dumps(data).encode("utf-8"))

    def assert_refused(self, reason):
        """Undo is refused with exactly ``reason``; no draft, no content change, record bytes untouched."""
        repo = self.repo_
        drafts, content, head, record = repo.drafts(), repo.read(STORE), repo.head(), self.path.read_bytes()
        result = repo.prepare(_req((REVERT, {"changeId": self.change_id})))
        self.assertEqual(result["result"], "refused", result)
        self.assertEqual(result["reason"], reason)
        self.assertEqual((repo.drafts(), repo.read(STORE), repo.head(), repo.status()), (drafts, content, head, ""))
        self.assertEqual(self.path.read_bytes(), record)
        self.assertEqual(repo.store()["hours"], NEW_HOURS)
        return result

    def with_records(self, records):
        return {**self.record, "records": records}

    def test_happy_path_unchanged(self):
        self.repo_.run((REVERT, {"changeId": self.change_id}))
        self.assertEqual(self.repo_.store()["hours"], self.original)
        self.assertEqual(json.loads(self.path.read_text("utf-8"))["revertedBy"][:4], "chg-")

    def test_truncated_json_is_unreadable(self):
        raw = self.path.read_bytes()
        self.write(raw[: len(raw) // 2])
        self.assert_refused(f"{self.change_id} record is unreadable")

    def test_empty_file_is_unreadable(self):
        self.write(b"")
        self.assert_refused(f"{self.change_id} record is unreadable")

    def test_not_utf8_is_unreadable(self):
        self.write(b"\xff\xfe{")
        self.assert_refused(f"{self.change_id} record is unreadable")

    def test_wrong_top_level_type_is_malformed(self):
        for data in ([], "text", 7, None):
            with self.subTest(data=data):
                self.write(data)
                if data is None:  # JSON null reads as "no change"; pins existing behaviour
                    self.assert_refused(f"unknown change {self.change_id}")
                else:
                    self.assert_refused(f"{self.change_id} record is malformed")

    def test_bad_records_are_malformed(self):
        good = self.record["records"][0]
        cases = {
            "records a dict": self.with_records({"0": good}),
            "records a string": self.with_records("store"),
            "record not a dict": self.with_records([good, ["store", "store"]]),
            "missing after": self.with_records([{k: v for k, v in good.items() if k != "after"}]),
            "missing before": self.with_records([{k: v for k, v in good.items() if k != "before"}]),
            "missing key": self.with_records([{k: v for k, v in good.items() if k != "key"}]),
            "collection secrets": self.with_records([{**good, "collection": "secrets"}]),
            "collection a list": self.with_records([{**good, "collection": ["store"]}]),
            "key an int": self.with_records([{**good, "key": 1}]),
            "good then bad": self.with_records([good, {**good, "key": None}]),
        }
        for name, data in cases.items():
            with self.subTest(name):
                self.write(data)
                self.assert_refused(f"{self.change_id} record is malformed")

    def test_malformed_wins_over_state_checks(self):
        # a well-formed record that is not applied keeps its existing reason; a malformed one is malformed first
        self.write({**self.record, "state": "draft"})
        self.assert_refused(f"{self.change_id} is not an applied change")
        self.write({**self.record, "state": "draft", "records": {}})
        self.assert_refused(f"{self.change_id} record is malformed")

    def test_absent_or_empty_records_keep_existing_refusal(self):
        for data in ({k: v for k, v in self.record.items() if k != "records"}, self.with_records([])):
            with self.subTest(data=sorted(data)):
                self.write(data)
                self.assert_refused(f"{self.change_id} touched no records")

    def test_directory_at_record_path_is_unreadable(self):  # RF1800-1: a folder is a damaged record, not "unknown"
        self.path.unlink()
        self.path.mkdir()
        result = self.repo_.prepare(_req((REVERT, {"changeId": self.change_id})))
        self.assertEqual((result["result"], result["reason"]), ("refused", f"{self.change_id} record is unreadable"))
        self.assertEqual(self.repo_.store()["hours"], NEW_HOURS)

    def test_reason_names_only_the_change_id(self):
        good = self.record["records"][0]
        for data in (self.with_records([{**good, "collection": "secrets", "before": SECRET, "after": SECRET}]),
                     {**self.with_records([{**good, "key": 3}]), "note": SECRET},
                     json.dumps({"note": SECRET}).encode("utf-8")[:-2]):
            with self.subTest(data=str(data)[:40]):
                self.write(data)
                result = self.repo_.prepare(_req((REVERT, {"changeId": self.change_id})))
                self.assertEqual(result["result"], "refused", result)
                self.assertIn(self.change_id, result["reason"])
                self.assertNotIn(SECRET, json.dumps(result))
                self.assertNotIn(str(self.repo_.state), json.dumps(result))


if __name__ == "__main__":
    import unittest

    unittest.main()

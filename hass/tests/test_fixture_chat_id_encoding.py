"""RF0330-11 (H09): a fixture `id` that is JSON-valid but not UTF-8 text (a lone surrogate escape) is refused by
physical line before any message is handled or queued: `fixture_chat: fixture line <n>: id must be UTF-8 text`
(exit 2). Run: python3 -B -m unittest hass.tests.test_fixture_chat_id_encoding -v
"""

import json
import tempfile
import unittest
from pathlib import Path

from hass.conversation import Inbound
from hass.fixture_chat import FixtureAdapter
from hass.inbox import Inbox
from hass.tests import test_fixture_chat_rows as rows
from hass.tests.test_fixture_chat_queue import PAIR, START, line

BAD = "fixture line {}: id must be UTF-8 text"
ROW = rows.ROW
SURROGATES = [r"\ud800", r"\udbff", r"\udc00", r"\udfff", r"x\ud800", r"\udc00x", r"x\udfffy", r"\udc00\ud800",
              r"\ud800\ud800", r"\ud800x\udc00", "SYNTHETIC-CANARY-\\ud800"]


def text_of(*rows_):  # real ASCII JSON escapes, one row per line; a str is taken as a raw line
    return "".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows_)


def escaped(raw_id):  # the row JSON with the id written as raw escape text, as a fixture file would hold it
    return json.dumps({**ROW, "id": "@@"}).replace('"@@"', '"' + raw_id + '"')


class FixtureIdEncodingTests(unittest.TestCase):
    fresh, run_cli, query = rows.FixtureRowTests.fresh, rows.FixtureRowTests.run_cli, rows.FixtureRowTests.query
    refused = rows.FixtureRowTests.refused

    def adapter(self, text, photos=None):
        folder = tempfile.TemporaryDirectory(prefix="hass-idenc-")
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "fixture.jsonl"
        path.write_text(text, "utf-8")
        return FixtureAdapter(path, photos=photos)

    def test_lone_surrogate_ids_refuse_at_row_admission(self):
        for raw in SURROGATES:
            with self.subTest(raw=raw):
                self.assertIsInstance(json.loads(escaped(raw))["id"], str)  # valid JSON, so only the new check refuses
                with self.assertRaises(ValueError) as caught:
                    self.adapter(escaped(raw) + "\n").inbound()
                self.assertEqual(str(caught.exception), BAD.format(1))

    def test_later_bad_id_direct_handles_no_good_prefix(self):
        repo, head = self.fresh()
        text = text_of(PAIR[0], "", escaped(r"\ud800"), PAIR[1])
        run = self.run_cli(repo, [], text=text)
        self.refused(run, BAD.format(3), repo, head)
        self.assertEqual(self.query(repo, "conversation", "SELECT * FROM messages"), [])

    def test_later_bad_id_queue_enqueues_and_drains_nothing(self):
        repo, head = self.fresh()
        old = Inbound(provider_id="old-1", chat=PAIR[0]["chat"], sender=PAIR[0]["sender"], text="hello",
                      received_at="2026-11-02T09:30:00-08:00")
        inbox = Inbox(repo.state, start_at=START)
        self.assertEqual(inbox.enqueue(old), "queued")
        inbox.close()
        before = self.query(repo, "inbox", "SELECT * FROM inbound")
        run = self.run_cli(repo, [], "--queue", START, text=text_of(PAIR[0], "", escaped(r"\udfff"), PAIR[1]))
        self.refused(run, BAD.format(3), repo, head)
        self.assertEqual(self.query(repo, "inbox", "SELECT * FROM inbound"), before)
        self.assertEqual([r[0] for r in self.query(repo, "inbox", "SELECT state FROM inbound")], ["pending"])

    def test_valid_unicode_pair_integer_and_duplicates_keep_identity(self):
        ids = ["caf\u00e9", "cafe\u0301", "\u6f22\u5b57-1", "\U0001f600", json.loads('"\\ud83d\\ude00x"'), 7, "dup", "dup"]
        found = [r.provider_id for r in self.adapter(text_of(*[{**ROW, "id": i} for i in ids])).inbound()]
        self.assertEqual(found, ["caf\u00e9", "cafe\u0301", "\u6f22\u5b57-1", "\U0001f600", "\U0001f600x", "7", "dup", "dup"])
        repo, _ = self.fresh()
        both = [{**PAIR[0], "id": "dup"}, {**PAIR[0], "id": "dup"}, {**PAIR[1], "id": "\u6f22\u5b57-2"}]
        run = self.run_cli(repo, both)
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        stored = self.query(repo, "conversation", "SELECT provider_id FROM messages ORDER BY provider_id")
        self.assertEqual(stored, [("dup",), ("\u6f22\u5b57-2",)])

    def test_id_error_precedence_and_private_diagnostic(self):
        for rows_, message in [
            ([{k: v for k, v in ROW.items() if k != "id"}, escaped(r"\ud800")], "fixture line 1: " + rows.ID),
            ([{**ROW, "id": ""}, escaped(r"\ud800")], "fixture line 1: " + rows.ID),
            ([{**ROW, "id": 1.5}, escaped(r"\ud800")], "fixture line 1: " + rows.ID),
            ([ROW, json.dumps({**ROW, "id": "SYNTHETIC-CANARY-\ud800", "sender": 5}), json.dumps({**ROW, "id": ""})],
             BAD.format(2)),
        ]:
            with self.subTest(message=message):
                repo, head = self.fresh()
                run = self.run_cli(repo, [], text=text_of(*rows_))
                self.refused(run, message, repo, head)
                for leaked in ("SYNTHETIC-CANARY", "utf-8", "codec", "surrogate", "ud800", "Traceback", "fixture.jsonl"):
                    self.assertNotIn(leaked, run.stderr)
        repo, head = self.fresh()  # the new message also precedes a later invalid field in the same row
        bad_sender = json.dumps({**ROW, "id": "SYNTHETIC-CANARY-\ud800", "sender": 5})
        self.refused(self.run_cli(repo, [], text=text_of(bad_sender)), BAD.format(1), repo, head)

    def test_unrelated_payload_and_photo_mapping_controls_unchanged(self):
        meta = json.dumps({**ROW, "id": "ok-1", "meta": {"note": "\ud800"}, "extra": ["\udfff"]})
        self.assertEqual([r.provider_id for r in self.adapter(text_of(meta)).inbound()], ["ok-1"])
        folder = tempfile.TemporaryDirectory(prefix="hass-idenc-photos-")
        self.addCleanup(folder.cleanup)
        (Path(folder.name) / "one.jpg").write_bytes(b"IMG-ONE")
        row = {**ROW, "id": "caf\u00e9-\U0001f600", "photos": ["one.jpg"]}
        adapter = self.adapter(text_of(row), photos=folder.name)
        (message,) = adapter.inbound()
        self.assertEqual((message.provider_id, message.attachments), ("caf\u00e9-\U0001f600", 1))
        self.assertEqual(list(adapter.names), ["caf\u00e9-\U0001f600"])
        self.assertEqual(adapter.fetch("caf\u00e9-\U0001f600", 1), [b"IMG-ONE"])


if __name__ == "__main__":
    unittest.main()

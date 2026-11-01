"""NB-AV-13 (H09) demo v2: a stored test photo through hass/fixture_chat.py --photos, from photo to undo.
Photo + caption -> question; the same photo again -> named, no second draft; owner fills the description -> draft;
yes -> applied (checked with a screenshot when a previewer is given); history; undo; yes. PhotoRepo harness (temp Git
repo, private media root outside it); nothing is downloaded or sent.
Run: python3 -B -m unittest hass.tests.test_demo_transcript_photo -v
"""

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from hass import conversation
from hass.conversation import PHOTO_QUESTION
from hass.content_model import REPO_ROOT
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import CHAT, SETTINGS
from hass.tests.test_set_photo import ALT, FIXTURES as MEDIA, PID, PhotoRepo, _settings

FIXTURES = REPO_ROOT / "hass" / "tests" / "fixtures"
DEMO, MAPPING = FIXTURES / "conversation-demo-photo.jsonl", FIXTURES / "conversation-demo-photo-interpreter.json"
SHA = hashlib.sha256((MEDIA / "pixel.jpg").read_bytes()).hexdigest()
CODE, INSTALLED = SHA[:4], f"assets/products/photo-{SHA[:16]}.jpg"
ASKED = f"{PHOTO_QUESTION} Reply with the product and description (draft {CODE})."
QUESTION = "Please provide: imageAlt"  # the editor's question when the caption names only the product
KINDS = (ASKED, QUESTION, "That photo is already in draft ", "Draft ", "Applied and checked ", "Applied ",
         "Recent changes:", "Undo ")
EXPECTED = [ASKED, QUESTION, "That photo is already in draft ", "Draft ", "Applied ", "Recent changes:", "Undo ",
            "Applied "]
REFUSED = "fixture_chat: fixture line 1: photos must name regular files directly inside --photos\n"


class PhotoDemoTranscriptTests(unittest.TestCase):
    def fresh(self):
        repo = PhotoRepo()
        self.addCleanup(repo.cleanup)
        _settings(repo, **SETTINGS, mediaRoot=str(repo.media))
        return repo

    def run_cli(self, repo, fixture=DEMO, photos=MEDIA):
        return subprocess.run([sys.executable, "-B", str(REPO_ROOT / "hass" / "fixture_chat.py"), "--state",
                               str(repo.state), "--fixture", str(fixture), "--interpreter", str(MAPPING),
                               "--photos", str(photos)], capture_output=True, text=True, cwd=REPO_ROOT)

    def lines(self, repo, rows):  # a fixture of some demo rows (or rows changed from them) in the repo's temp dir
        path = repo.state.parent / "fixture.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
        return path

    def demo_rows(self):
        return [json.loads(s) for s in DEMO.read_text("utf-8").splitlines()]

    def transcript(self, repo, fixture=DEMO):
        run = self.run_cli(repo, fixture)
        self.assertEqual((run.returncode, run.stderr), (0, ""))
        rows = [json.loads(line) for line in run.stdout.splitlines()]
        self.assertEqual({(r["chat"], tuple(r["attachments"])) for r in rows} - {(CHAT, ())}, set())
        return [r["text"] for r in rows]

    def kind(self, text):
        return next((k for k in KINDS if text.startswith(k)), text)

    def query(self, repo, sql):
        db = sqlite3.connect(repo.state / "conversation.sqlite3")
        db.row_factory = sqlite3.Row
        try:
            return db.execute(sql).fetchall()
        finally:
            db.close()

    def originals(self, repo, sub="originals"):  # every file under the media root's sub folder ("" for all of it)
        root = repo.media / sub
        return sorted(p for p in root.rglob("*") if p.is_file()) if root.exists() else []

    def test_photo_round_trip_applies_and_undo_restores(self):
        repo = self.fresh()
        before = repo.product(PID)
        texts = self.transcript(repo)
        self.assertEqual([self.kind(t) for t in texts], EXPECTED)
        edit, undo = self.query(repo, "SELECT * FROM drafts ORDER BY row_id")  # the second sending: no second draft
        self.assertEqual(edit["code"], CODE)
        self.assertEqual(texts[2], f"That photo is already in draft {CODE}. {texts[1]}")
        self.assertTrue(texts[3].startswith(f"Draft {CODE}:"), texts[3])
        self.assertTrue(texts[4].startswith(f"Applied {CODE}:"), texts[4])
        self.assertIn(f"{CODE} applied: products {PID}", texts[5])
        self.assertTrue(texts[6].startswith(f"Undo {CODE}:\nDraft {undo['code']}:"), texts[6])
        self.assertTrue(texts[7].startswith(f"Applied {undo['code']}:"), texts[7])
        self.assertEqual((edit["state"], json.loads(undo["ops_json"])[0]["op"]), ("reverted", "history.revert"))
        after = repo.product(PID)
        self.assertEqual((after["image"], after.get("imageAlt")), (before["image"], before.get("imageAlt")))
        self.assertEqual(len(self.originals(repo)), 2)  # one original (+ its sidecar) for two sendings
        messages = {r["provider_id"]: r["disposition"] for r in self.query(repo, "SELECT * FROM messages")}
        self.assertEqual(len(messages), 7)  # the redelivered photo-demo-1 added no record, fetch or reply
        self.assertEqual((messages["photo-demo-1"], messages["photo-demo-2"]), ("needs-details", "photo-duplicate"))
        self.assertEqual(len(self.query(repo, "SELECT * FROM outbox")), len(texts))

    def test_yes_installs_the_photo_with_the_owners_text(self):
        repo = self.fresh()
        texts = self.transcript(repo, self.lines(repo, self.demo_rows()[:4]))
        self.assertEqual([self.kind(t) for t in texts], EXPECTED[:5])
        self.assertEqual((repo.product(PID)["image"], repo.product(PID)["imageAlt"]), (INSTALLED, ALT))
        self.assertTrue((repo.wt / "storefront-mockup" / INSTALLED).is_file())

    def test_stranger_photo_is_ignored_and_stores_nothing(self):
        repo = self.fresh()
        row = {**self.demo_rows()[0], "sender": "stranger@example.invalid"}
        self.assertEqual(self.transcript(repo, self.lines(repo, [row])), [])
        self.assertEqual([tuple(r) for r in self.query(repo, "SELECT provider_id, disposition FROM messages")],
                         [("photo-demo-1", "ignored")])
        self.assertEqual((self.originals(repo, ""), self.query(repo, "SELECT * FROM drafts")), ([], []))

    def test_photo_names_outside_the_folder_are_refused_before_anything_runs(self):
        folder = tempfile.TemporaryDirectory(prefix="hass-photos-")
        self.addCleanup(folder.cleanup)
        photos = Path(folder.name)
        (photos / "link.jpg").symlink_to(MEDIA / "pixel.jpg")
        path, row = photos / "fixture.jsonl", self.demo_rows()[0]
        for bad in ([".."], ["../media/pixel.jpg"], ["media/pixel.jpg"], ["link.jpg"], ["missing.jpg"], [""],
                    "pixel.jpg", [7], [str(MEDIA / "pixel.jpg")]):
            with self.subTest(bad=bad):
                path.write_text(json.dumps({**row, "photos": bad}) + "\n", "utf-8")
                with self.assertRaises(ValueError) as caught:
                    FixtureAdapter(path, photos=str(MEDIA if bad != ["link.jpg"] else photos)).inbound()
                self.assertEqual(f"fixture_chat: {caught.exception}\n", REFUSED)
        repo = self.fresh()
        run = self.run_cli(repo, self.lines(repo, [{**row, "photos": ["link.jpg"]}]), photos=photos)
        self.assertEqual((run.returncode, run.stdout, run.stderr), (2, "", REFUSED))
        self.assertEqual((self.query(repo, "SELECT * FROM messages"), self.originals(repo, "")), ([], []))

    def test_without_photos_flag_the_field_is_ignored(self):
        path = Path(self.fresh().state.parent) / "fixture.jsonl"
        path.write_text(json.dumps({**self.demo_rows()[0], "photos": ["../x"]}) + "\n", "utf-8")
        [msg] = FixtureAdapter(path).inbound()
        self.assertEqual(msg.attachments, 0)

    def test_previewer_checked_reply_carries_one_screenshot(self):
        repo = self.fresh()
        png = repo.state / "shot.png"
        png.write_bytes(b"png")
        previewer = mock.Mock(capture=lambda files, target, out: {"ok": True, "png": str(png), "error": None})
        adapter = FixtureAdapter(self.lines(repo, self.demo_rows()[:4]), photos=str(MEDIA))
        conv = conversation.Conversation(str(repo.state), conversation.Editor(repo.state),
                                         conversation.FixtureInterpreter(json.loads(MAPPING.read_text("utf-8"))),
                                         lambda: datetime.now(timezone.utc), previewer, photos=adapter)
        for message in adapter.inbound(): conv.handle(message)
        conv.flush(adapter)
        checked = adapter.sent[-1]
        self.assertTrue(checked["text"].startswith(f"Applied and checked {CODE}:"), checked["text"])
        self.assertEqual(checked["attachments"], [str(png)])
        self.assertEqual(self.query(repo, f"SELECT state FROM drafts WHERE code = '{CODE}'")[0]["state"], "verified")


if __name__ == "__main__":
    unittest.main()

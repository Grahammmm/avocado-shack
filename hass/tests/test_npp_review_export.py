"""Offline contract tests for the review export CLI and its shared redactor."""

import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

from scripts.hass.npp_review_export import redact


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_review_export.py"
DAY = "2031-02-03"


class NppReviewExportTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.source = self.root / "source.jsonl"
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()
        self.out = self.root / "review.jsonl"
        self.events()

    def run_cli(self, *extra, out=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--export", str(self.source), "--receipts", str(self.receipts),
             "--since", DAY, "--out", str(out or self.out), *extra],
            capture_output=True, text=True, check=False, timeout=15, cwd=self.root,
        )

    def assert_pass(self, result, events, jobs):
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines()[-1], f"PASS npp_review_export {events} events {jobs} jobs")

    def events(self, *overrides):
        with self.source.open("w", encoding="utf-8") as source:
            for override in overrides:
                event = dict(utc=f"{DAY}T08:45:00+00:00", chat="sample-chat-b", sender="sample-sender",
                             direction="in", kind="text", text="Try a shorter title", attachments=[],
                             disposition="question", provider_id="sample-provider", reply_to="sample-reply")
                source.write(json.dumps(event | override) + "\n")

    def receipt(self, job="feed", **override):
        path = self.receipts / job / "receipt.json"
        path.parent.mkdir(exist_ok=True)
        row = dict(job_id=job, state="card_out", segments=[dict(accepted_at=f"{DAY}T08:45:00+00:00",
                   ended_at=None, outcome=None)], versions=[dict(n=2, state="building", image_variant=None),
                   dict(n=1, state="delivered", image_variant="raw", image_sha256="unused-digest")])
        path.write_text(json.dumps(row | override), encoding="utf-8")
        return path

    def test_c1_shape(self):
        # C1: reject field passthrough, time/order drift, aliases sorted by ID, or flattened versions.
        self.events(dict(utc="2031-02-02T23:59:00Z", chat="old-chat"),
                    dict(kind="photo", attachments=["photo-hash-a", "photo-hash-b"]),
                    dict(chat="sample-chat-a", utc="2031-02-04T01:00:00Z", direction="out", disposition="queued"),
                    dict(direction="out", text="Use this title", disposition="queued"))
        self.receipt()
        self.assert_pass(self.run_cli(), 3, 1)
        first = dict(day=DAY, chat="chat-1", dir="in", kind="photo", text_redacted="Try a shorter title",
                     attachments=2, disposition="question")
        self.assertEqual([json.loads(line) for line in self.out.read_text().splitlines()], [
            first, first | dict(day="2031-02-04", chat="chat-2", dir="out", kind="text", attachments=0,
                                disposition="queued"),
            first | dict(dir="out", kind="text", text_redacted="Use this title", attachments=0, disposition="queued"),
            dict(job="feed", state="card_out", segments=1, versions=[dict(n=2, state="building", image_variant=None),
                 dict(n=1, state="delivered", image_variant="raw")]),
        ])

    def test_c2_redaction(self):
        # C2: replacing digits only leaves whole spoken amounts, contacts and street names in the review.
        reserved_phone = "(" + "202" + ") " + "555" + "-" + "0147"
        cases = [
            ("83471", "<n>"), ("12,345.67", "<n>"), ("３９８", "<n>"), ("A892Z", "A<n>Z"),
            ("twenty five", "<n>"), ("three fifty", "<n>"), ("NINETY-NINE", "<n>"),
            ("half a dozen", "<n>"), ("two hundred", "<n> <n>"),
            ("3 bucks", "<n> <money>"), ("$75.41", "<money><n>"), ("USD twenty", "<money> <n>"),
            ("fake+listing@example.invalid", "<email>"),
            (reserved_phone, "<phone>"), ("+1 " + reserved_phone + " ext. 89", "<phone>"),
            ("https://listing.example.invalid/p/77?secret=sample", "<url>"),
            ("www.listing.example.invalid/p", "<url>"), ("listing.example.invalid/p", "<url>"),
            ("814 Quorble Wisp Street Apt B", "<address>"), ("Quorble Wisp Street", "<address>"),
            ("Use the softer title", "Use the softer title"),
        ]
        for private, expected in cases:
            with self.subTest(text=private):
                self.assertEqual(redact(private), expected)

        cost, qty = "$75.41", "twenty five"
        email, street = "fake+listing@example.invalid", "814 Quorble Wisp Street Apt B"
        chat, sender = "synthetic-chat-key", "synthetic-sender-key"
        self.events(dict(chat=chat, sender=sender, text=f"cost {cost}; qty {qty}; call {reserved_phone}; "
                         f"email {email}; {street}", cost=cost, quantity=qty),
                    dict(chat=chat, sender="sample-bot", direction="out", text=f"Review {chat}; note from {sender}."))
        self.receipt(cost=cost, quantity=qty, chat=chat, sender=sender,
                     segments=[dict(contact=email, address=street)])
        result = self.run_cli()
        self.assert_pass(result, 2, 1)
        rendered = self.out.read_text()
        for canary in (cost, "75.41", qty, reserved_phone, email, street, "Quorble Wisp", chat, sender):
            with self.subTest(canary=canary):
                self.assertNotIn(canary, rendered + result.stdout + result.stderr)
        one, two, _ = map(json.loads, rendered.splitlines())
        self.assertEqual(one["text_redacted"], "cost <money><n>; qty <n>; call <phone>; email <email>; <address>")
        self.assertEqual(two["text_redacted"], "Review <id>; note from <id>.")

    def test_c3_private_output(self):
        # C3: catch stale/wide modes, silent clobber, and a worktree reached through an alias.
        self.events({})
        self.assert_pass(self.run_cli(), 1, 0)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
        previous = self.out.read_bytes()
        self.events(dict(text="A different title"))
        result = self.run_cli()
        self.assertEqual((result.returncode, result.stdout), (1, "FAIL output-exists\n"))
        self.assertEqual(self.out.read_bytes(), previous)
        self.out.chmod(0o644)
        self.assert_pass(self.run_cli("--force"), 1, 0)
        self.assertNotEqual(self.out.read_bytes(), previous)
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)

        # Marker fixtures mirror normal and linked worktrees without needing Git subprocesses.
        for linked in (False, True):
            work = self.root / ("linked" if linked else "checkout")
            nested = work / "ignored"
            nested.mkdir(parents=True)
            if linked:
                (work / ".git").write_text("gitdir: ../synthetic-gitdir\n")
            else:
                (work / ".git").mkdir()
            alias = self.root / (work.name + "-alias")
            alias.symlink_to(nested, target_is_directory=True)
            for parent in (nested, alias):
                with self.subTest(parent=parent.name):
                    out = parent / "review.jsonl"
                    result = self.run_cli("--force", out=out)
                    self.assertEqual((result.returncode, result.stdout), (1, "FAIL output-in-worktree\n"))
                    self.assertFalse(out.exists())

    def test_c4_bad_receipt(self):
        # C4: an intact job still exports if a nearby receipt has the wrong shape; no receipt is repaired in place.
        good = self.receipt()
        bad = self.receipt("bade", versions=[dict(n=True, state="delivered", image_variant="raw")])
        malformed = self.receipt("dead")
        malformed.write_text("{not-json")
        self.events({})
        inputs = (good, bad, malformed, self.source)
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in inputs]
        result = self.run_cli()
        self.assert_pass(result, 1, 1)
        self.assertEqual(result.stdout.splitlines()[:-1], ["NOTE bad-receipt bade", "NOTE bad-receipt dead"])
        self.assertEqual(json.loads(self.out.read_text().splitlines()[-1])["job"], "feed")
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in inputs], before)
        result = self.run_cli("--force", out=bad)
        self.assertEqual((result.returncode, result.stdout.splitlines()[-1]), (1, "FAIL output-is-input"))
        self.assertEqual(bad.read_bytes(), before[1][0])

    def test_c5_exit(self):
        # C5: distinguish a valid empty export, invalid inputs, and argument parser failures.
        self.assert_pass(self.run_cli(), 0, 0)
        self.assertEqual(self.out.read_bytes(), b"")
        self.out.unlink()
        for content in (b'{"sample-malformed"', b'[]\n', b'\xff', b'{"utc":"2031-02-03"}\n'):
            with self.subTest(content=content):
                self.source.write_bytes(content)
                result = self.run_cli()
                self.assertEqual((result.returncode, result.stdout, result.stderr), (1, "FAIL bad-export\n", ""))
                self.assertFalse(self.out.exists())
        self.source.unlink()
        result = self.run_cli()
        self.assertEqual((result.returncode, result.stdout), (1, "FAIL bad-export\n"))
        for args in (("--since", "2031-02-30"), ("--since", "20310203"), ("--unknown",)):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage:", result.stderr)
                self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Offline, source-bound characterization. No model qualification or apply mode."""
import argparse
import contextlib
import hashlib

import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SCRATCH = REPO.parent / "old56-fixtures"
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO))
ACTIVE, ATTEMPTS, READS = False, [], set()
PROMPT = "Synthetic retention probe. Return a JSON object. Never apply changes."


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local(name):
    p = Path(name)
    if p.is_absolute() or not p.parts or any(x in ("..", ".") for x in p.parts):
        raise ValueError("package-relative path required")
    p = ROOT / p
    if any(q.is_symlink() for q in [p, *p.parents]):
        raise ValueError("symlink refused")
    if not p.resolve().is_relative_to(ROOT):
        raise ValueError("path escape")
    return p


def pairs(items):
    out = {}
    for k, v in items:
        if k in out: raise ValueError("duplicate key")
        out[k] = v
    return out


def load(path):
    doc = json.loads(path.read_text(), object_pairs_hook=pairs,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    if not isinstance(doc, dict) or type(doc.get("schema_version")) is not int or doc["schema_version"] != 1:
        raise ValueError("schema version")
    return doc


def stamp(text):
    if not isinstance(text, str): raise ValueError("timestamp")
    at = datetime.fromisoformat(text)
    if at.tzinfo is None: raise ValueError("aware timestamp required")
    return at


def fixtures():
    doc = load(local("fixtures.json"))
    if set(doc) != {"schema_version", "identity", "at", "request", "answer", "correction", "expected"}:
        raise ValueError("fixture shape")
    if doc["identity"] != "synthetic-owner-generic-context": raise ValueError("fixture identity")
    stamp(doc["at"])
    if not all(isinstance(doc[k], str) and 0 < len(doc[k]) <= 1000 for k in ("request", "answer", "correction")):
        raise ValueError("fixture text")
    if doc["expected"] != {"earlier_after_answer": [doc["request"]],
                            "earlier_after_correction": [doc["request"], doc["answer"]],
                            "cancelled_recent": False, "expired_recent": False, "other_owner_reads": False,
                            "duplicate_transport_calls": 0, "stale_applies": False,
                            "real_model": "REAL_MODEL_UNVERIFIED"}: raise ValueError("fixture expectations")
    return doc


def audit(event, args):
    if not ACTIVE: return
    bad = False
    if event == "open" and not isinstance(args[0], int):
        p = Path(args[0]).resolve()
        mode, flags = args[1], args[2]
        writing = (isinstance(mode, str) and any(x in mode for x in "wax+")) or bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT))
        allowed = p.is_relative_to(SCRATCH) if writing else (
            p.is_relative_to(REPO) or p.is_relative_to(SCRATCH) or
            p.is_relative_to(Path(sys.base_prefix) / "lib") or
            p.is_relative_to(Path(sys.prefix) / "lib") or
            p.is_relative_to(Path("/usr/share/zoneinfo")) or p == Path(os.devnull))
        bad = not allowed
        if allowed and not writing and p.is_relative_to(REPO) and p.is_file(): READS.add(p)
    elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.rename", "os.symlink", "shutil.rmtree"}:
        indices = (0, 1) if event == "os.rename" else (1,) if event == "os.symlink" else (0,)
        for index in indices:
            value = args[index]
            if isinstance(value, int): continue
            p = Path(value)
            fd_index = 2 + index if event == "os.rename" else 2 if event in {"os.mkdir", "os.chmod"} else 1
            fd = args[fd_index] if len(args) > fd_index else None
            if not p.is_absolute() and isinstance(fd, int) and fd >= 0:
                p = Path(os.readlink(f"/proc/self/fd/{fd}")) / p
            # Check the directory entry, not a fixture's read-only asset symlink target.
            if not (p.parent.resolve() / p.name).is_relative_to(SCRATCH): bad = True
    elif event == "sqlite3.connect":
        bad = not Path(args[0]).resolve().is_relative_to(SCRATCH)
    elif event.startswith("socket."): bad = True
    elif event == "subprocess.Popen":
        argv = args[1]
        bad = not (isinstance(argv, list) and len(argv) > 3 and argv[:2] == ["git", "-C"]
                   and Path(argv[2]).resolve().is_relative_to(SCRATCH)
                   and argv[3] in {"init", "config", "add", "commit", "worktree", "rev-parse", "status", "symbolic-ref", "rev-list", "diff", "log", "show"})
    if bad:
        ATTEMPTS.append(event)
        raise PermissionError("offline fixture boundary")


sys.addaudithook(audit)


@contextlib.contextmanager
def isolated():
    global ACTIVE
    if any(p.is_symlink() for p in [SCRATCH, *SCRATCH.parents]):
        raise ValueError("fixture scratch symlink")
    if SCRATCH.resolve().parent != REPO.parent.resolve(): raise ValueError("fixture root")
    SCRATCH.mkdir(mode=0o700, exist_ok=True)
    old, old_temp = ACTIVE, tempfile.tempdir
    ACTIVE, tempfile.tempdir = True, str(SCRATCH)
    try:
        yield
    finally:
        ACTIVE, tempfile.tempdir = old, old_temp


class RecordingTransport:
    def __init__(self):
        self.calls, self.reply = [], {"question": "Which day should change?"}

    def __call__(self, url, body, headers, timeout):
        self.calls.append(json.loads(body))
        return 200, json.dumps({"done": True, "message": {"content": json.dumps(self.reply)}}).encode()

    def fields(self):
        return json.loads(self.calls[-1]["messages"][1]["content"])


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.guard = isolated()
        self.guard.__enter__()
        self.addCleanup(self.guard.__exit__, None, None, None)
        from hass.tests.test_conversation import ConversationTestCase
        from hass.interpreter_local import LocalInterpreter
        self.fx = ConversationTestCase()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.tx = RecordingTransport()
        self.fx.conv.db.close()
        self.fx.interp = LocalInterpreter("http://127.0.0.1:11434", "synthetic-only", PROMPT,
                                          transport=self.tx, clock=lambda: self.fx.now)
        self.fx.conv = self.fx.open()
        self.addCleanup(lambda: self.fx.conv.db.close())
        self.data = fixtures()

    def ask(self, text=None, **kw):
        text = text or self.data["request"]
        result = self.fx.say(text, **kw)
        self.fx.replies()  # recording FixtureAdapter, never a send
        return result

    def test_generic_non_hike_question_and_short_answer_keep_needed_context(self):
        self.assertEqual(self.ask(), "question")
        self.assertEqual(self.ask(self.data["answer"]), "question")
        fields = self.tx.fields()
        self.assertEqual(fields["message"], self.data["answer"])
        self.assertEqual(fields["recent"]["earlier"], self.data["expected"]["earlier_after_answer"])
        self.assertEqual(fields["recent"]["question"], self.tx.reply["question"])
        self.ask(self.data["correction"])
        self.assertEqual(self.tx.fields()["recent"]["earlier"], self.data["expected"]["earlier_after_correction"])
        self.assertEqual(self.fx.commits(), 0)

    def test_recreated_conversation_binds_same_owner_request(self):
        self.ask()
        row = self.fx.conv.requests.get(self.fx.conv.settings["ownerChat"], self.fx.now)
        self.fx.conv.db.close()
        self.fx.conv = self.fx.open()
        self.assertEqual(self.ask(self.data["answer"]), "question")
        self.assertEqual(self.tx.fields()["recent"]["earlier"], row["texts"])
        self.assertIsNone(self.fx.conv.requests.get("other-owner", self.fx.now))
        before = len(self.tx.calls)
        self.assertEqual(self.ask("other text", sender="other@example.invalid"), "ignored")
        self.assertEqual(len(self.tx.calls), before)

    def test_cancel_expiry_other_owner_and_turn_limit_prevent_stale_context(self):
        from hass import conversation
        self.ask(pid="original")
        before = len(self.tx.calls)
        self.assertEqual(self.ask(pid="original"), "duplicate")
        self.assertEqual(len(self.tx.calls), before)
        self.ask("no")
        self.ask(self.data["answer"])
        self.assertNotIn("recent", self.tx.fields())
        self.fx.now += timedelta(minutes=31)
        self.ask(self.data["correction"])
        self.assertNotIn("recent", self.tx.fields())
        for i in range(7): self.ask(f"The description wording number {i} " + "x" * 850)
        earlier = self.tx.fields()["recent"]["earlier"]
        self.assertLessEqual(len(earlier), conversation.ASK_TURNS)
        self.assertLessEqual(sum(map(len, earlier)), conversation.ASK_CHARS)
        self.assertNotIn(self.data["request"], earlier)
        self.assertIsNone(self.fx.conv.requests.get("other-owner", self.fx.now))

    def test_operation_arguments_and_version_guard_not_invented_or_auto_applied(self):
        from hass.tests.test_conversation import _ops
        from hass.tests.test_editor import HOURS, NEW_HOURS, DESC, _req
        self.tx.reply = _ops((HOURS, {"hours": NEW_HOURS}))
        self.assertEqual(self.ask("Change the opening hours"), "proposed")
        old = self.fx.drafts()[0]
        self.tx.reply = {"question": "Which day should change?"}
        self.ask("And the next wording")
        pending = self.tx.fields()["pending"]
        self.assertEqual(pending[0]["ops"], [{"op": HOURS, "args": {"hours": NEW_HOURS}}])
        self.assertEqual(self.fx.commits(), 0)
        other = self.fx.repo.prepare(_req((DESC, {"id": "photo-product-001", "description": "Picked this week."})))
        self.assertEqual(self.fx.repo.apply(other["draft"])["result"], "applied")
        head = self.fx.repo.head()
        self.ask(f"yes {old['code']}")
        self.assertEqual(self.fx.drafts()[0]["reason"], "stale")
        self.assertEqual(self.fx.repo.head(), head)
        self.assertEqual(self.fx.drafts()[-1]["state"], "proposed")
        self.assertEqual(self.fx.editor.applies, 1)  # one stale attempt, never a successful apply

    def test_fixture_pass_cannot_claim_real_model_acceptance(self):
        sources = load(local("SOURCES.json"))
        validate_sources(sources)
        forged = {**sources, "real_model_status": "VERIFIED"}
        with self.assertRaises(ValueError): validate_sources(forged)
        with self.assertRaises(ValueError): validate_sources({**sources, "actual_transcripts": [{}]})
        for forged in ({**sources, "runtime": {"model": "invented"}},
                       {**sources, "captured_at": "2026-11-15"},
                       {**sources, "source_sha256": {"../escape": "0" * 64}},
                       {**sources, "extra": True}):
            with self.assertRaises(ValueError): validate_sources(forged)
        self.assertEqual(self.data["expected"]["real_model"], "REAL_MODEL_UNVERIFIED")

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        for name in ("../RESULT.md", "/etc/passwd", "../../../../.local/share/avocado-shack"):
            with self.assertRaises(ValueError): local(name)
        # Symlink fixture stays in task scratch; local() also checks all parent symlinks.
        link = SCRATCH / "rejected-link"
        link.symlink_to(ROOT)
        self.addCleanup(link.unlink)
        with mock.patch.object(sys.modules[__name__], "ROOT", SCRATCH):
            with self.assertRaisesRegex(ValueError, "symlink"): local("rejected-link/RESULT.md")
        for raw in ('{"schema_version":1,"schema_version":1}', '{"schema_version":2}', '{'):
            p = SCRATCH / "bad.json"
            p.write_text(raw)
            with self.assertRaises(ValueError): load(p)
        before = list(ATTEMPTS)
        import socket
        with self.assertRaises(PermissionError): socket.socket()
        self.assertEqual(ATTEMPTS[len(before):], ["socket.__new__"])
        del ATTEMPTS[len(before):]  # explicit deciding negative, not an unexpected attempt
        for action in (lambda: open("/etc/passwd"), lambda: open(REPO / "forbidden-write", "w"),
                       lambda: os.mkdir(REPO / "forbidden-directory")):
            with self.assertRaises(PermissionError): action()
            self.assertEqual(len(ATTEMPTS), 1)
            ATTEMPTS.clear()
        with self.assertRaises(ValueError): stamp("2026-11-15")
        self.assertEqual(ATTEMPTS, [])


def validate_sources(doc):
    if set(doc) != {"schema_version", "captured_at", "runtime", "prompt_sha256", "real_model_status", "actual_transcripts", "missing_coverage", "source_sha256"}:
        raise ValueError("source shape")
    stamp(doc["captured_at"])
    if doc["real_model_status"] != "REAL_MODEL_UNVERIFIED" or doc["actual_transcripts"] != []:
        raise ValueError("no separately admitted actual transcript; real-model claims refused")
    if doc["runtime"] != {"model": "synthetic-only", "provider": "recording-transport", "kind": "offline-fixture"}:
        raise ValueError("runtime identity")
    if doc["prompt_sha256"] != hashlib.sha256(PROMPT.encode()).hexdigest(): raise ValueError("prompt binding")
    if doc["missing_coverage"] != ["actual model request/response bytes", "per-turn actual-model expectations", "owner semantic acceptance"]:
        raise ValueError("coverage")
    for name, sha in doc["source_sha256"].items():
        if not re.fullmatch(r"[0-9a-f]{64}", sha): raise ValueError("digest")
        p = REPO / name
        if Path(name).is_absolute() or ".." in Path(name).parts or not p.resolve().is_relative_to(REPO) or p.is_symlink():
            raise ValueError("source path")
        if digest(p) != sha: raise ValueError("source drift: " + name)


def check(result, sources):
    fixtures()
    doc, bases = load(local(sources)), load(local("BASES.json"))
    validate_sources(doc)
    if set(bases) != {"schema_version", "inspected_main", "candidate_only", "installed", "no_apply", "source_sha256"}:
        raise ValueError("bases shape")
    if not re.fullmatch(r"[0-9a-f]{40}", bases["inspected_main"]): raise ValueError("base identity")
    if (bases["candidate_only"], bases["installed"], bases["no_apply"]) != (True, False, True): raise ValueError("boundary")
    if bases["source_sha256"] != doc["source_sha256"]: raise ValueError("source binding")
    required = {"hass/conversation.py", "hass/interpreter_local.py", "hass/skills/openreq.py"}
    if not required <= doc["source_sha256"].keys(): raise ValueError("missing consumers")
    text = local(result).read_text()
    marker = "<!-- OLD56-RECEIPT\n"
    if text.count(marker) != 1: raise ValueError("receipt missing/duplicate")
    receipt = json.loads(text.split(marker)[1].split("\n-->")[0], object_pairs_hook=pairs)
    expected = {"schema_version": 1, "synthetic_tests": 6, "failures": 0,
                "real_model_status": "REAL_MODEL_UNVERIFIED", "status": "CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED",
                "base": bases["inspected_main"], "sources_sha256": digest(local(sources))}
    if receipt != expected: raise ValueError("report identity/count/coverage")
    print("CHECK PASS: 6 synthetic checks; REAL_MODEL_UNVERIFIED; CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check")
    parser.add_argument("--sources")
    args = parser.parse_args()
    try:
        if args.self_test and not args.check and not args.sources:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(ContextTests)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            if result.wasSuccessful(): print("SELF-TEST PASS: 6 synthetic checks; REAL_MODEL_UNVERIFIED")
            return 0 if result.wasSuccessful() else 1
        if args.check and args.sources and not args.self_test:
            check(args.check, args.sources)
            return 0
        parser.print_usage()
        return 2
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("REFUSED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

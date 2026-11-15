#!/usr/bin/env python3
"""Offline OLD-59 candidate. No install, real provider guarantee, or live mode."""
import argparse
import base64
import hashlib
import importlib

import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest

from datetime import datetime

ROOT = Path(__file__).absolute().parent
REPO = ROOT.parents[2]
sys.dont_write_bytecode = True
CHAT = "iMessage;-;fixture@example.invalid"
NOW = 1794787200
BLOCKED = []
ACTIVE = False


def beneath(root, value):
    path = Path(value)
    if not path.is_absolute(): path = root / path
    if ".." in path.parts or not path.is_relative_to(root): raise ValueError("path-escape")
    for entry in (path, *path.parents):
        if entry.is_symlink(): raise ValueError("symlink")
    if not path.resolve().is_relative_to(root): raise ValueError("path-escape")
    return path


def fence(event, args):
    if not ACTIVE: return
    denied = event.startswith(("socket.", "subprocess.", "os.system", "os.exec", "os.spawn"))
    if event in ("open", "sqlite3.connect"):
        value = args[0]
        if isinstance(value, (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(value)).absolute()
            flags = args[2] if event == "open" else os.O_RDWR
            write = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            allowed = [ROOT / ".fixtures"] if write else [ROOT, REPO / "hass", REPO / "mac", REPO / ".github/workflows/check.yml", Path(sys.base_prefix) / "lib", Path("/usr/share/zoneinfo")]
            denied = not any(path.is_relative_to(p) for p in allowed)
            if not denied:
                try: beneath(next(p for p in allowed if path.is_relative_to(p)), path)
                except ValueError: denied = True
    if event in ("os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.rename", "os.symlink", "os.link"):
        try: beneath(ROOT / ".fixtures", Path(args[0]).absolute().parent if event == "os.remove" else Path(args[0]).absolute())
        except (ValueError, TypeError): denied = True
        if event == "os.symlink":
            try: beneath(ROOT / ".fixtures", Path(args[1]).absolute())
            except ValueError: denied = True
        if event in ("os.rename", "os.link"): denied = True
    if denied:
        BLOCKED.append(event)
        raise PermissionError("offline-boundary")


sys.addaudithook(fence)


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def pairs(items):
    out = {}
    for key, value in items:
        if key in out: raise ValueError("duplicate-key")
        out[key] = value
    return out


def document(name):
    data = json.loads(beneath(ROOT, name).read_text(), object_pairs_hook=pairs)
    if type(data) is not dict or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema")
    return data


def bindings(sources="SOURCES.json"):
    bases, src = document("BASES.json"), document(sources)
    if set(bases) != {"schema_version", "main", "candidate_only", "installed", "no_apply", "digests"}: raise ValueError("base-schema")
    if not re.fullmatch(r"[0-9a-f]{40}", bases["main"]) or (bases["candidate_only"], bases["installed"], bases["no_apply"]) != (True, False, True): raise ValueError("base-boundary")
    if set(src) != {"schema_version", "main", "captured_at", "digests", "missing", "provider_guarantee"}: raise ValueError("source-schema")
    if src["main"] != bases["main"] or src["digests"] != bases["digests"]: raise ValueError("source-binding")
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00", src["captured_at"]): raise ValueError("timestamp")
    datetime.fromisoformat(src["captured_at"])
    if src["missing"] != ["real provider idempotency guarantee", "live reconciliation", "owner semantic acceptance"] or src["provider_guarantee"] != "UNKNOWN/HOLD": raise ValueError("coverage")
    if not bases["digests"]: raise ValueError("missing-sources")
    for name, expected in bases["digests"].items():
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(beneath(REPO, name)) != expected: raise ValueError("digest")
    return bases


def fixtures():
    data = document("fixtures.json")
    if set(data) != {"schema_version", "synthetic", "idempotency_contract", "item", "expected"} or data["synthetic"] is not True: raise ValueError("fixture-schema")
    if data["idempotency_contract"] != "SYNTHETIC ONLY: repeated key returns the original receipt; not a BlueBubbles guarantee": raise ValueError("fixture-contract")
    item(data["item"])
    if data["expected"] != {"baseline_attempts": 2, "baseline_accepted": 2, "idempotent_attempts": 2, "idempotent_accepted": 1, "unknown_attempts": 1, "unknown_accepted": 1}: raise ValueError("fixture-expectations")
    return data


def item(value):
    if type(value) is not dict or set(value) != {"id", "chat", "text", "pictures"}: raise ValueError("item-schema")
    if type(value["id"]) is not int or value["id"] <= 0 or value["chat"] != CHAT: raise ValueError("identity")
    if type(value["text"]) is not str or not value["text"] or type(value["pictures"]) is not int or not 0 <= value["pictures"] <= 2: raise ValueError("payload")
    return value


class Crash(BaseException): pass
class Hold(BaseException): pass
class NotAccepted(Exception): pass


class RecordingProvider:
    def __init__(self, idempotent=False):
        self.idempotent, self.attempts, self.accepted, self.receipts = idempotent, [], [], {}
        self.fail = self.crash = False

    def send(self, key, payload):
        self.attempts.append(key)
        if self.fail: raise NotAccepted()
        if not self.idempotent or key not in self.receipts:
            self.accepted.append((key, payload))
            self.receipts[key] = "fixture-receipt-" + str(len(self.accepted))
        if self.crash: raise Crash()
        return self.receipts[key]


class Protocol:
    """One serialized fixture consumer. SENDING is durable BEFORE transport."""
    def __init__(self, path, provider):
        self.db = sqlite3.connect(beneath(ROOT / ".fixtures", path), isolation_level=None)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS intent(identity TEXT PRIMARY KEY,chat TEXT,digest TEXT,key TEXT,state TEXT,receipt TEXT)")
        self.provider = provider

    def identity(self, reply, part, payload):
        item(reply)
        identity = f"{reply['id']}:{part}"
        hashed = hashlib.sha256(payload).hexdigest()
        key = hashlib.sha256(json.dumps([identity, reply["chat"], hashed]).encode()).hexdigest()
        self.db.execute("INSERT OR IGNORE INTO intent VALUES (?,?,?,?,'READY',NULL)", (identity, reply["chat"], hashed, key))
        row = self.db.execute("SELECT chat,digest,key,state,receipt FROM intent WHERE identity=?", (identity,)).fetchone()
        if row[:3] != (reply["chat"], hashed, key): raise Hold("payload-conflict")
        return identity, row

    def send(self, reply, part, payload, disposition="ready"):
        if disposition not in ("ready", "cancelled", "expired", "stale"): raise ValueError("disposition")
        if disposition != "ready": raise Hold(disposition)
        identity, row = self.identity(reply, part, payload)
        if row[3] == "RECEIPT": return row[4]
        if row[3] == "UNKNOWN/HOLD": raise Hold("reconciliation-required")
        if row[3] == "SENDING" and not self.provider.idempotent:
            self.db.execute("UPDATE intent SET state='UNKNOWN/HOLD' WHERE identity=?", (identity,))
            raise Hold("ambiguous")
        self.db.execute("UPDATE intent SET state='SENDING' WHERE identity=?", (identity,))
        try: receipt = self.provider.send(row[2], payload)
        except NotAccepted:
            self.db.execute("UPDATE intent SET state='READY' WHERE identity=?", (identity,))
            raise
        except Exception:
            self.db.execute("UPDATE intent SET state='UNKNOWN/HOLD' WHERE identity=?", (identity,))
            raise Hold("ambiguous") from None
        self.db.execute("UPDATE intent SET state='RECEIPT',receipt=? WHERE identity=?", (receipt, identity))
        return receipt


def production():
    sys.path.insert(0, str(REPO))
    module = importlib.import_module("mac.hass_forwarder")
    bound = document("BASES.json")["digests"]
    for name, mod in tuple(sys.modules.items()):
        path = getattr(mod, "__file__", None)
        if path and name.split(".")[0] in ("hass", "mac"):
            relative = str(Path(path).relative_to(REPO))
            if relative not in bound or digest(Path(path)) != bound[relative]: raise ValueError("unbound-helper")
    return module


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.data = fixtures()
        self.reply = self.data["item"].copy()
        directory = beneath(ROOT, ".fixtures")
        directory.mkdir(exist_ok=True, mode=0o700)
        self.root = Path(tempfile.mkdtemp(dir=directory))
        def cleanup():
            for path in self.root.iterdir(): path.unlink()
            self.root.rmdir()
        self.addCleanup(cleanup)
        self.mod = production()

    def protocol(self, provider):
        obj = Protocol(self.root / "intent.sqlite3", provider)
        self.addCleanup(obj.db.close)
        return obj

    def forwarder(self, provider, protocol=None, crash_stage=False, replies=None, crash_picture=None):
        key = self.root / "synthetic-key"
        key.write_text("63" * 32)
        key.chmod(0o600)
        cfg = dict(ownerChat=CHAT, receiverUrl="http://fixture.invalid", secretFile=str(key), bbPort=1234, bbPasswordFile=str(self.root / "never-read"))
        spool = self.mod.Spool(self.root, NOW)
        self.addCleanup(spool.db.close)
        outer, replies = self, replies or [self.reply]
        class Sender:
            def send(self, chat, text, attachments=()):
                reply = next(r for r in replies if (r["chat"], r["text"]) == (chat, text))
                payload = json.dumps([text, len(attachments)]).encode()
                if protocol: return protocol.send({k: reply[k] for k in outer.reply}, "text", payload)
                return provider.send("baseline", payload)
        class Attachment:
            def send_png(self, chat, data, filename):
                rid, idx = map(int, re.fullmatch(r"hass-(\d+)-(\d+)\.png", filename).groups())
                reply = next(r for r in replies if r["id"] == rid)
                provider.crash = idx == crash_picture
                return protocol.send({k: reply[k] for k in outer.reply}, f"picture-{idx}", data)
        def transport(url, body=None):
            req = self.mod.relay.unseal_control(body, bytes.fromhex("63" * 32), now=NOW, seen=set())
            if req["op"] == "pull": out = dict(op="replies", items=replies)
            elif req["op"] == "picture":
                data = self.mod.relay.PNG_SIG + b"synthetic" + bytes([req["idx"]])
                out = dict(op="picture", id=req["id"], idx=req["idx"], sha256=hashlib.sha256(data).hexdigest(), b64=base64.b64encode(data).decode())
            elif req["op"] == "ack":
                outer.acks.extend(req["ids"])
                out = dict(op="acked", ids=req["ids"])
            else: raise AssertionError("unexpected transport")
            return self.mod.relay.seal_control(out, bytes.fromhex("63" * 32), now=NOW, nonce=os.urandom(16).hex())
        def stage(event, rid):
            if crash_stage and event == "bb-send-end": raise Crash()
        self.acks = []
        f = self.mod.Forwarder(cfg, spool, lambda: NOW, transport, Sender(), attach=Attachment(), stage=stage)
        return f

    def test_provider_accept_then_crash_before_local_sent_is_reproduced(self):
        provider = RecordingProvider()
        f = self.forwarder(provider, crash_stage=True)
        with self.assertRaises(Crash): f.pull()
        self.assertEqual((len(provider.accepted), f.spool.status()["sent"], self.acks), (1, 0, []))
        f.spool.db.close()
        self.forwarder(provider).pull()
        self.assertEqual((len(provider.attempts), len(provider.accepted)), (self.data["expected"]["baseline_attempts"], self.data["expected"]["baseline_accepted"]))
        print("BASELINE attempts=2 accepted=2 local_sent_after_crash=0")

    def test_restart_of_fixture_uses_same_intent_identity(self):
        provider = RecordingProvider()
        protocol = self.protocol(provider)
        f = self.forwarder(provider, protocol, crash_stage=True)
        with self.assertRaises(Crash): f.pull()
        original = protocol.db.execute("SELECT key,receipt FROM intent").fetchone()
        protocol.db.close()
        f.spool.db.close()
        reopened = self.protocol(provider)
        restarted = self.forwarder(provider, reopened)
        restarted.pull()
        restarted.pull()
        self.assertEqual(reopened.db.execute("SELECT key,receipt FROM intent").fetchone(), original)
        self.assertEqual((len(provider.attempts), len(provider.accepted), restarted.spool.status()["sent"]), (1, 1, 1))

    def test_documented_idempotent_provider_receipt_deduplicates(self):
        provider = RecordingProvider(idempotent=True)
        provider.crash = True
        protocol = self.protocol(provider)
        with self.assertRaises(Crash): self.forwarder(provider, protocol).pull()
        receipt = next(iter(provider.receipts.values()))
        protocol.db.close()
        provider.crash = False
        reopened = self.protocol(provider)
        self.forwarder(provider, reopened).pull()
        self.assertEqual(provider.attempts[0], provider.attempts[1])
        self.assertEqual((len(provider.attempts), len(provider.accepted)), (self.data["expected"]["idempotent_attempts"], self.data["expected"]["idempotent_accepted"]))
        self.assertEqual(reopened.db.execute("SELECT receipt FROM intent").fetchone()[0], receipt)
        print("SYNTHETIC_IDEMPOTENT attempts=2 accepted=1 same_key=true same_receipt=true")

    def test_unknown_provider_outcome_holds_without_auto_resend_or_false_sent(self):
        provider = RecordingProvider()
        provider.crash = True
        protocol = self.protocol(provider)
        f = self.forwarder(provider, protocol)
        with self.assertRaises(Crash): f.pull()
        protocol.db.close()
        f.spool.db.close()
        reopened = self.protocol(provider)
        later = dict(self.reply, id=2, text="later")
        f = self.forwarder(provider, reopened, replies=[self.reply, later])
        for _ in range(2):
            with self.assertRaises(Hold): f.pull()
        self.assertEqual((len(provider.attempts), len(provider.accepted), f.spool.status()["sent"], self.acks), (self.data["expected"]["unknown_attempts"], self.data["expected"]["unknown_accepted"], 0, []))
        self.assertEqual(reopened.db.execute("SELECT state,receipt FROM intent").fetchall(), [("UNKNOWN/HOLD", None)])
        print("AMBIGUOUS attempts=1 accepted=1 state=UNKNOWN/HOLD sent=0 acked=0 later_sent=0")

    def test_pre_accept_failure_payload_conflict_and_picture_partial_completion(self):
        provider = RecordingProvider()
        protocol = self.protocol(provider)
        provider.fail = True
        f = self.forwarder(provider, protocol)
        with self.assertRaises(NotAccepted): f.pull()
        self.assertEqual((provider.accepted, self.acks), ([], []))
        provider.fail = False
        f.pull()
        with self.assertRaises(Hold): protocol.send(self.reply, "text", b"changed")
        with self.assertRaises(ValueError): protocol.send(dict(self.reply, chat="other"), "text", b"payload")
        for disposition in ("cancelled", "expired", "stale"):
            with self.subTest(disposition=disposition), self.assertRaises(Hold): protocol.send(dict(self.reply, id=3), "text", b"blocked", disposition)
        self.assertEqual(len(provider.accepted), 1)
        self.reply.update(id=4, pictures=2)
        png = self.mod.relay.PNG_SIG + b"synthetic"
        shots = [dict(idx=i, sha256=hashlib.sha256(png + bytes([i])).hexdigest(), size=len(png) + 1) for i in range(2)]
        wire = dict(self.reply, shots=shots)
        f = self.forwarder(provider, protocol, replies=[wire], crash_picture=1)
        with self.assertRaises(Crash): f.pull()
        count = len(provider.accepted)
        protocol.db.close()
        f.spool.db.close()
        protocol = self.protocol(provider)
        restarted = self.forwarder(provider, protocol, replies=[wire])
        with self.assertRaises(Hold): restarted.pull()
        self.assertEqual(len(provider.accepted), count)
        self.assertEqual(restarted.spool.db.execute("SELECT idx FROM sent_pics WHERE reply_id=4").fetchall(), [(0,)])
        self.assertEqual(self.acks, [])
        self.reply.update(id=5, pictures=1)
        provider.crash = False
        completed = self.forwarder(provider, protocol, replies=[dict(self.reply, shots=shots[:1])])

        completed.pull()
        completed.pull()
        self.assertEqual(completed.spool.db.execute("SELECT idx FROM sent_pics WHERE reply_id=5").fetchall(), [(0,)])
        self.assertEqual(self.acks, [5, 5])
        self.assertEqual(len(provider.accepted), count + 2)

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        before = list(BLOCKED)
        for path in ("../RESULT.md", "/home/user/.local/share/protected", "/tmp/spool"):
            with self.subTest(path=path), self.assertRaises(ValueError): beneath(ROOT, path)
        target, link = self.root / "target", self.root / "link"
        target.write_text("synthetic")
        link.symlink_to(target)
        with self.assertRaises(ValueError): beneath(ROOT, link)
        for raw in ('{"schema_version":1,"schema_version":1}', '{broken'):
            with self.assertRaises(ValueError): json.loads(raw, object_pairs_hook=pairs)
        for changed in (dict(self.reply, id=True), dict(self.reply, id=-1), dict(self.reply, pictures=-1), dict(self.reply, extra=1)):
            with self.assertRaises(ValueError): item(changed)
        fake = self.root / "invalid.json"
        for invalid in ({"schema_version": 2}, {"schema_version": True}):
            fake.write_text(json.dumps(invalid))
            with self.assertRaises(ValueError): document(fake)
        src = document("SOURCES.json")
        for changed in (dict(src, captured_at="not-time"), dict(src, provider_guarantee="PASS"), dict(src, extra=1), dict(src, missing=[])):
            fake.write_text(json.dumps(changed))
            with self.assertRaises(ValueError): bindings(fake)
        report = (ROOT / "RESULT.md").read_text()
        for changed in (report.replace('"baseline_accepted": 2', '"baseline_accepted": 1'), report.replace('"provider_guarantee": "UNKNOWN/HOLD"', '"provider_guarantee": "PASS"')):
            fake.write_text(changed)
            with self.assertRaises(ValueError): check(fake, "SOURCES.json")
        self.assertEqual(BLOCKED, before)


def check(result, sources):
    bases = bindings(sources)
    fixtures()
    text = beneath(ROOT, result).read_text()
    header, _, _ = text.partition("\n```json\n")
    if header != "# AUDINV-OLD-59 RESULT": raise ValueError("report-schema")
    raw = text.split("\n```json\n", 1)[1].split("\n```", 1)[0]
    report = json.loads(raw, object_pairs_hook=pairs)
    expected = dict(schema_version=1, main=bases["main"], status="CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED", provider_guarantee="UNKNOWN/HOLD", baseline_attempts=2, baseline_accepted=2, idempotent_attempts=2, idempotent_accepted=1, unknown_attempts=1, unknown_accepted=1, source_digests=bases["digests"])
    if report != expected: raise ValueError("report-binding-or-counts")
    print("CHECK PASS: schema=1 exact source bindings/counts; UNKNOWN/HOLD retained; not semantic acceptance")


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--self-test", action="store_true")
    group.add_argument("--check")
    parser.add_argument("--sources")
    args = parser.parse_args()
    if bool(args.check) != bool(args.sources): parser.error("--sources required only with --check")
    global ACTIVE
    ACTIVE = True
    try:
        bindings(args.sources or "SOURCES.json")
        if args.self_test:

            suite = unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests)
            result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
            if BLOCKED: raise ValueError("unexpected-side-effect")
            return 0 if result.wasSuccessful() else 1
        check(args.check, args.sources)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        print("INVALID:", type(error).__name__, str(error), file=sys.stderr)
        return 1


if __name__ == "__main__": sys.exit(main())

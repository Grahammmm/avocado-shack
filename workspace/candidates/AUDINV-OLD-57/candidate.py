#!/usr/bin/env python3
"""Offline synthetic ingress characterization; no live/apply mode. Embedded local-only tests."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
import unittest
from urllib.parse import urlsplit, parse_qs, unquote

sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parent
REPO = ROOT.parents[2]
sys.path.insert(0, str(REPO))
NOW = datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc)
IDENTITY = {"owner": "synthetic-owner", "chat": "synthetic-chat", "message": "synthetic-message", "attachment": "synthetic-attachment"}
ATTEMPTS = []


def contained(root, name):
    p = Path(name)
    if p.is_absolute() or not p.parts or any(x in (".", "..") for x in p.parts):
        raise ValueError("unsafe relative path")
    path = root / p
    if any(x.is_symlink() for x in (root, *root.parents, path, *path.parents)):
        raise ValueError("symlink path")
    if root.resolve() not in path.resolve().parents:
        raise ValueError("path escape")
    return path


def pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out


def loads(text):
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: fail("nonfinite JSON"))


def fail(message):
    raise ValueError(message)


def shape(obj, keys):
    if not isinstance(obj, dict) or set(obj) != set(keys):
        fail("unknown or missing fields")


def version(obj):
    if type(obj.get("schema_version")) is not int or obj["schema_version"] != 1:
        fail("unknown schema")


def aware(value):
    if not isinstance(value, str):
        fail("invalid timestamp")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None or dt.utcoffset() is None:
        fail("timestamp must be zoned")
    return dt


def approval(doc):
    shape(doc, ["schema_version", *IDENTITY, "count", "status", "received_at", "expires_at"])
    version(doc)
    if any(type(doc[k]) is not str or doc[k] != v for k, v in IDENTITY.items()):
        fail("identity mismatch")
    if type(doc["count"]) is not int or doc["count"] != 1:
        fail("attachment-count")
    if doc["status"] != "approved":
        fail("not approved")
    received, expires = aware(doc["received_at"]), aware(doc["expires_at"])
    if not received <= NOW < expires or (NOW - received).total_seconds() > 300:
        fail("stale or expired")


def load_helpers():
    from hass import media, bridge_photos, newitem_render
    from hass.ops import OpContext, Refused
    from hass.ops.photos import install
    return media, bridge_photos, newitem_render, OpContext, Refused, install


def clean_fixture(root):
    # shutil.rmtree uses relative dir-fd opens, which cannot be attributed by Python's open audit event.
    for folder, dirs, files in os.walk(root, topdown=False, followlinks=False):
        for name in files: (Path(folder) / name).unlink()
        for name in dirs:
            path = Path(folder) / name
            path.unlink() if path.is_symlink() else path.rmdir()
    root.rmdir()


class FixtureTransport:
    """Recording-only responses; no socket, URL opener or arbitrary callback."""
    def __init__(self, data, meta=None, status=200):
        self.data, self.status, self.calls = data, status, []
        self.meta = meta if meta is not None else {"data": {
            "guid": IDENTITY["message"], "owner": IDENTITY["owner"], "chat": IDENTITY["chat"],
            "attachments": [{"guid": IDENTITY["attachment"], "totalBytes": len(data)}]}}

    def __call__(self, url, headers, timeout, limit):
        self.calls.append((urlsplit(url).path, limit))  # never record even the synthetic password
        p = urlsplit(url)
        if (p.scheme != "http" or p.netloc != "127.0.0.1:1" or p.fragment
                or parse_qs(p.query).get("password") != ["synthetic-not-a-credential"]):
            fail("unexpected fixture request")
        if p.path.startswith("/api/v1/message/"):
            if unquote(p.path.split("/")[-1]) != IDENTITY["message"]:
                fail("message mismatch")
            return self.status, (self.meta if isinstance(self.meta, str) else json.dumps(self.meta)).encode()
        if p.path != "/api/v1/attachment/synthetic-attachment/download":
            fail("attachment mismatch")
        return self.status, self.data


def ingress(doc, transport, scratch):
    approval(doc)  # before root access, credential fixture creation or transport
    if type(transport) is not FixtureTransport:
        fail("fixture transport required")
    scratch = Path(scratch)
    if scratch.is_symlink() or scratch.resolve() != scratch or not scratch.is_dir():
        fail("explicit real scratch required")
    if scratch.parent.parent != REPO.parent.resolve() or not scratch.parent.name.startswith("old57-fixture-"):
        fail("scratch outside task-owned fixture")
    media, photos, _, OpContext, Refused, install = load_helpers()
    token = scratch / "synthetic-token"
    if not token.exists():
        token.write_text("synthetic-not-a-credential", encoding="utf-8")
        token.chmod(0o600)
    def checked_fixture(url, headers, timeout, limit):
        status, body = transport(url, headers, timeout, limit)
        if headers["Accept"] == "application/json" and 200 <= status < 300:
            if len(body) > limit: return status, body  # production helper owns cap refusal
            data = loads(body).get("data", {})
            if any(data.get(k) != doc[v] for k, v in (("guid", "message"), ("owner", "owner"), ("chat", "chat"))):
                fail("response identity mismatch")
            items = data.get("attachments")
            if not isinstance(items, list) or len(items) != doc["count"] or items[0].get("guid") != doc["attachment"]:
                fail("response attachment mismatch")
        return status, body
    source = photos.BlueBubblesPhotos("http://127.0.0.1:1", token, transport=checked_fixture)
    data, = source.fetch(doc["message"], doc["count"])
    media.check_photo(data)  # all refusals precede original/web/asset writes
    root = scratch / "media"
    original = media.store_original(root, data, received_at=doc["received_at"], source="synthetic-approved")
    ctx = OpContext(NOW, scratch / "site", {"mediaRoot": str(root)})
    target = install(ctx, original["sha256"], "Synthetic colored phone-photo chart")
    if isinstance(target, Refused):
        fail(target.reason)
    # The real production consumer queues only the sanitized bytes; nothing is published or committed.
    return original, ctx.assets, target


def image(kind="jpeg", orientation=1):
    media, _, renderer, *_ = load_helpers()
    Image, *_ = renderer._modules()
    im = Image.new("RGB", (48, 32))
    palette = [(240,20,20), (20,230,20), (20,20,240), (230,220,20), (220,20,220), (20,220,220)]
    im.putdata([palette[(y // 16) * 3 + x // 16] for y in range(32) for x in range(48)])
    stream = io.BytesIO()
    im.save(stream, "JPEG" if kind == "jpeg" else "PNG", quality=95)
    raw = stream.getvalue()
    # Synthetic real TIFF entries for device/date/GPS; never copied from a phone.
    def n(x, size): return x.to_bytes(size, "little")
    tags = [(0x112, 3, 1, n(orientation, 2) + b"\0\0"),
            (0x10f, 2, 8, n(74, 4)), (0x132, 2, 20, n(82, 4)), (0x8825, 4, 1, n(0, 4))]
    tiff = b"II*\0" + n(8, 4) + n(4, 2) + b"".join(n(t, 2) + n(k, 2) + n(c, 4) + v for t, k, c, v in tags)
    tiff += bytes(4) + bytes(12) + b"FakeCam\0" + b"2026:11:15 23:00:00\0" + b"GPS synthetic-device"
    if kind == "jpeg":
        body = b"Exif\0\0" + tiff
        return raw[:2] + b"\xff\xe1" + n(len(body) + 2, 2)[::-1] + body + raw[2:]
    import zlib
    body = b"eXIf" + tiff if orientation != 1 else b"tEXt" + b"Comment\0GPS FakeCam synthetic-device"
    chunk = n(len(body) - 4, 4)[::-1] + body + zlib.crc32(body).to_bytes(4, "big")
    return raw[:-12] + chunk + raw[-12:]


def fixtures():
    doc = loads(contained(ROOT, "fixtures.json").read_text())
    shape(doc, ["schema_version", "approval", "orientation_pixels", "negative", "missing"])
    version(doc)
    approval(doc["approval"])
    if set(doc["orientation_pixels"]) != {str(i) for i in range(2, 9)}:
        fail("incomplete orientation coverage")
    for matrix in doc["orientation_pixels"].values():
        if not isinstance(matrix, list) or sorted(x for row in matrix for x in row) != list(range(6)):
            fail("bad independent pixel oracle")
    if doc["missing"] != ["real-phone", "needed-owner-format", "live-fetch", "replacement-trial", "owner-acceptance"]:
        fail("missing coverage concealed")
    names = set()
    for case in doc["negative"]:
        if not isinstance(case, dict) or set(case) - {"name", "approval", "status", "response", "declared", "expected", "max_calls"}:
            fail("unsupported fixture flag")
        if case["name"] in names or type(case["max_calls"]) is not int or not 0 <= case["max_calls"] <= 2:
            fail("invalid or duplicate fixture")
        names.add(case["name"])
    return doc


def check(result_name, source_name):
    # Validate both paths before either is opened.
    rp, sp = contained(ROOT, result_name), contained(ROOT, source_name)
    result = rp.read_text().split("```json\n")
    if len(result) != 2 or "\n```" not in result[1]: fail("one result schema required")
    report = loads(result[1].split("\n```", 1)[0])
    sources = loads(sp.read_text())
    bases = loads(contained(ROOT, "BASES.json").read_text())
    for doc in (report, sources, bases): version(doc)
    shape(report, ["schema_version", "status", "sources_sha256", "base", "source_count", "tests", "coverage"])
    shape(bases, ["schema_version", "main", "candidate_only", "installed", "apply", "digests"])
    shape(sources, ["schema_version", "captured_at", "base", "kind", "digests", "missing", "historical"])
    aware(sources["captured_at"])
    if not re.fullmatch(r"[0-9a-f]{40}", bases["main"]): fail("invalid base")
    if bases["candidate_only"] is not True or bases["installed"] is not False or bases["apply"] is not False:
        fail("no-apply boundary")
    if report["status"] != "CANDIDATE_ONLY / REVIEW_REQUIRED / NOT_INSTALLED": fail("false status")
    if report["sources_sha256"] != hashlib.sha256(sp.read_bytes()).hexdigest(): fail("source binding")
    if report["base"] != sources["base"] or sources["base"] != bases["main"]: fail("base binding")
    if sources["kind"] != "synthetic-only" or sources["digests"] != bases["digests"]: fail("source map")
    load_helpers()
    required = {str(Path(str(m.__file__)).resolve().relative_to(REPO)) for n, m in tuple(sys.modules.items())
                if n == "hass" or n.startswith("hass.") if getattr(m, "__file__", None)}
    required.add("workspace/candidates/AUDINV-OLD-57/fixtures.json")
    if set(bases["digests"]) != required: fail("incomplete helper closure")
    if type(report["source_count"]) is not int or report["source_count"] != len(bases["digests"]): fail("count")
    for name, digest in bases["digests"].items():
        if not (name.startswith("hass/") and name.endswith(".py") or name == "workspace/candidates/AUDINV-OLD-57/fixtures.json"):
            fail("unapproved source path")
        path = contained(REPO, name)
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            fail("stale source")
    doc = fixtures()
    if sources["missing"] != doc["missing"]: fail("missing evidence")
    if report["tests"] != 6 or type(report["tests"]) is not int: fail("test count")
    expected = {"synthetic-jpeg-2-8": "PASS_LOCAL", "synthetic-png": "PASS_LOCAL", "heic": "NOT SUPPORTED"}
    expected.update({k: "UNKNOWN/HOLD" for k in doc["missing"]})
    if report["coverage"] != expected: fail("false coverage")
    print("CHECK PASS: exact source bindings; 6 local tests; UNKNOWN/HOLD retained; no apply authority")


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="old57-fixture-", dir=REPO.parent.resolve())).resolve()
        self.addCleanup(clean_fixture, self.tmp)
        self.scratch = self.tmp / "case"
        self.scratch.mkdir(mode=0o700)
        self.doc = fixtures()["approval"].copy()

    def run_image(self, data):
        return ingress(self.doc, FixtureTransport(data), self.scratch)

    def test_injected_approved_attachment_reaches_real_media_consumer(self):
        for kind in ("jpeg", "png"):
            raw = image(kind)
            rec, assets, target = self.run_image(raw)
            self.assertEqual(Path(rec["path"]).read_bytes(), raw)
            self.assertEqual(stat.S_IMODE(Path(rec["path"]).stat().st_mode), 0o600)
            side = loads(Path(rec["path"]).with_suffix(".json").read_text())
            self.assertEqual((side["source"], side["received_at"]), ("synthetic-approved", self.doc["received_at"]))
            self.assertNotIn(b"FakeCam", assets[target])
            self.assertNotIn(b"GPS", assets[target])
            self.assertFalse((self.scratch / "site").exists())
            again, _, _ = self.run_image(raw)
            self.assertTrue(again["duplicate"])

    def test_synthetic_jpeg_orientation_2_to_8_has_no_private_metadata(self):
        media, _, renderer, *_ = load_helpers()
        Image, *_ = renderer._modules()
        for value, oracle in fixtures()["orientation_pixels"].items():
            with self.subTest(orientation=value):
                rec, assets, target = self.run_image(image(orientation=int(value)))
                out = assets[target]
                original = Path(rec["path"]).read_bytes()
                for leak in (b"FakeCam", b"2026:", b"GPS", b"synthetic-device"):
                    self.assertIn(leak, original)
                    self.assertNotIn(leak, out)
                segs, _ = media._jpeg_split(out)
                self.assertEqual([s for m, s in segs if m == 0xe1], [media.ORIENT_APP1(int(value))])
                upright, _, turned = renderer._upright(out)  # production orientation-consuming render path
                base = Image.open(io.BytesIO(original)).convert("RGB")
                # Independent six-label asymmetric pixel oracle; no EXIF-aware oracle/helper.
                labels = Image.new("RGB", (3, 2))
                labels.putdata([base.getpixel((x, y)) for y in (8, 24) for x in (8, 24, 40)])
                expected_size = (32, 48) if int(value) >= 5 else (48, 32)
                self.assertEqual(upright.size, expected_size)
                self.assertTrue(turned)
                expected = [labels.getpixel((n % 3, n // 3)) for row in oracle for n in row]
                actual = [upright.getpixel((x, y)) for y in range(8, upright.height, 16) for x in range(8, upright.width, 16)]
                # Independently stated colored-cell oracle tolerates JPEG's small boundary artifacts.
                self.assertTrue(all(max(abs(a-b) for a, b in zip(p, q)) < 18 for p, q in zip(actual, expected)))

    def test_unsupported_heic_keeps_original_untouched_and_requests_retake(self):
        media, *_ = load_helpers()
        data = b"\x00\x00\x00\x18ftypheic" + bytes(12)
        before = hashlib.sha256(data).hexdigest()
        with self.assertRaises(media.Refused) as cm: self.run_image(data)
        self.assertEqual(cm.exception.code, "unsupported-type")
        self.assertIn("Most Compatible", cm.exception.reply)
        self.assertEqual(hashlib.sha256(data).hexdigest(), before)
        self.assertFalse((self.scratch / "media").exists())
        with self.assertRaises(media.Refused) as cm: self.run_image(image("png", 6))
        self.assertEqual(cm.exception.code, "needs-rotation")
        self.assertFalse((self.scratch / "media").exists())

    def test_wrong_owner_redirect_bad_count_oversize_and_truncation_fail_closed(self):
        media, photos, *_ = load_helpers()
        for case in fixtures()["negative"]:
            with self.subTest(case=case["name"]):
                doc, data = self.doc.copy(), image()
                transport = FixtureTransport(data)
                for k, v in case.get("approval", {}).items(): doc[k] = v
                if "status" in case: transport.status = case["status"]
                if "response" in case: transport.meta["data"].update(case["response"])
                if "declared" in case: transport.meta["data"]["attachments"][0]["totalBytes"] = case["declared"]
                if case["name"] == "truncated": transport.data = data[:-2]
                if case["name"] == "byte-cap": transport.data = bytes(media.MAX_BYTES + 1)
                with self.assertRaises((ValueError, photos.BridgeError, media.Refused)) as cm:
                    ingress(doc, transport, self.scratch)
                self.assertEqual(getattr(cm.exception, "code", "value-error"), case["expected"])
                self.assertLessEqual(len(transport.calls), case["max_calls"])
                self.assertFalse((self.scratch / "media").exists())

    def test_existing_supported_path_is_not_replaced_or_live_fetched(self):
        media, photos, *_ = load_helpers()
        transport = FixtureTransport(image())
        before = hashlib.sha256(Path(str(media.__file__)).read_bytes()).hexdigest()
        ingress(self.doc, transport, self.scratch)
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(hashlib.sha256(Path(str(media.__file__)).read_bytes()).hexdigest(), before)
        for base in ("http://example.invalid:80", "http://127.0.0.1:1/x", "http://127.0.0.1:1?x=y"):
            with self.assertRaises(ValueError): photos.BlueBubblesPhotos(base, self.scratch / "synthetic-token", transport=transport)
        with self.assertRaises(ValueError): ingress(self.doc, lambda *a: None, self.scratch)
        self.assertEqual(len(transport.calls), 2)

    def test_schema_path_escape_symlink_and_side_effect_boundary(self):
        for text in ('{"schema_version":1,"schema_version":1}', '{', '{"x":NaN}'):
            with self.assertRaises(ValueError): loads(text)
        for patch in ({"schema_version": 2}, {"schema_version": True}, {"live": True}, {"received_at": "bad"}):
            doc = {**self.doc, **patch}
            transport = FixtureTransport(image())
            with self.assertRaises(ValueError): ingress(doc, transport, self.scratch)
            self.assertEqual(transport.calls, [])
        link = self.scratch / "link"
        link.symlink_to(ROOT, target_is_directory=True)
        for name in ("../RESULT.md", "/etc/passwd", "link/RESULT.md"):
            with self.assertRaises(ValueError): contained(self.scratch, name)
        for root in (ROOT, self.scratch / "link"):
            transport = FixtureTransport(image())
            with self.assertRaises(ValueError): ingress(self.doc, transport, root)
            self.assertEqual(transport.calls, [])
        with self.assertRaises(ValueError): check("../RESULT.md", "SOURCES.json")
        # Exercise the real artifact checker on task-local copies, never mutate immutable receipts.
        from unittest.mock import patch
        for name in ("fixtures.json", "BASES.json", "SOURCES.json", "RESULT.md"):
            (self.scratch / name).write_bytes(contained(ROOT, name).read_bytes())
        text = (self.scratch / "RESULT.md").read_text()
        for old, new in (("UNKNOWN/HOLD", "PASS_LOCAL"), ('"tests": 6', '"tests": 0'),
                         ('"source_count":', '"extra": 1, "source_count":')):
            (self.scratch / "RESULT.md").write_text(text.replace(old, new))
            with patch.dict(globals(), ROOT=self.scratch), self.assertRaises(ValueError):
                check("RESULT.md", "SOURCES.json")
        (self.scratch / "RESULT.md").write_text(text)
        with patch.dict(globals(), ROOT=self.scratch):
            with self.assertRaises(ValueError): check("RESULT.md", "link/SOURCES.json")
            check("RESULT.md", "SOURCES.json")  # positive control: negatives are not unrelated checker errors
        self.assertEqual(ATTEMPTS, [])  # invalid inputs rejected before disallowed I/O is attempted


def fence(event, args, package=ROOT):
    if event.startswith(("socket.", "subprocess.")) or event in ("os.system", "os.exec", "os.fork"):
        ATTEMPTS.append(event)
        raise PermissionError("offline boundary")
    if event in ("os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.link", "os.rename", "os.symlink"):
        paths = args[:2] if event in ("os.link", "os.rename") else args[1:2] if event == "os.symlink" else args[:1]
        for path in paths:
            p = Path(os.fsdecode(path)).absolute()
            # Do not resolve the final component: an owned test symlink is unlinked, never followed.
            if REPO.parent.resolve() not in p.parents or not any(x.startswith("old57-fixture-") for x in p.parts):
                ATTEMPTS.append(event)
                raise PermissionError("offline mutation boundary")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        p = Path(os.fsdecode(args[0])).absolute()
        flags = args[2] or 0
        write = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        fixture = REPO.parent.resolve() in p.resolve().parents and any(x.startswith("old57-fixture-") for x in p.parts)
        permitted = fixture or (not write and (REPO / "hass" in p.parents or package in p.parents
                    or any(Path(x) in p.parents for x in (sys.base_prefix, sys.prefix, "/usr/lib", "/usr/local/lib"))))
        if not permitted:
            ATTEMPTS.append(("open", str(p), bool(write)))
            raise PermissionError("offline path boundary")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--check")
    parser.add_argument("--sources")
    args = parser.parse_args()
    if args.self_test and not args.check and not args.sources:
        sys.addaudithook(fence)
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(CandidateTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if ATTEMPTS: fail("disallowed I/O attempted")
        print(f"SELF-TEST {'PASS' if result.wasSuccessful() else 'FAIL'}: {result.testsRun} named local-only synthetic tests; disallowed I/O: {len(ATTEMPTS)}")
        return 0 if result.wasSuccessful() else 1
    if args.check and args.sources and not args.self_test:
        check(args.check, args.sources)
        return 0
    parser.print_usage()
    return 2


if __name__ == "__main__":
    try: sys.exit(main())
    except (ValueError, OSError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        sys.exit(1)

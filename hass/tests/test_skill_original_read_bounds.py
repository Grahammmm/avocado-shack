"""RF1036-13: the shared original-photo reader (item_add._original) re-enforces media.MAX_BYTES at the disk-read boundary.

A stored original is read through an open stream bounded at MAX_BYTES + 1; anything longer is refused (None) before it is
hashed or reviewed. The trusted ctx.photo_bytes callback's result is length-checked before it is copied (what happens inside
the callback is not bounded here). item.add advice and item.picture keep their existing fallbacks for an unavailable original.
Run: python3 -B -m unittest hass.tests.test_skill_original_read_bounds -v
"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hass import media
from hass.content_model import REPO_ROOT, load_and_validate
from hass.skills import item_add, item_picture as ip

CAP = 64  # a scoped miniature MAX_BYTES; the real cap is exercised once below
JAR = REPO_ROOT / "reports/hass/newitem-1/synthetic/jar-white-sheet.jpg"
CONTENT = load_and_validate(REPO_ROOT / "hass" / "content", REPO_ROOT / "storefront-mockup")
LEMONS = "photo-product-017"


def sha_of(data):
    return hashlib.sha256(data).hexdigest()


def raw(path):
    with open(path, "rb") as handle:
        return handle.read()


class Spy:
    """Wraps a real binary stream: records read sizes and closes; refuses the unbounded read APIs."""

    def __init__(self, real, fail=None):
        self.real, self.reads, self.closes, self.fail = real, [], 0, fail

    def read(self, size=-1):
        self.reads.append(size)
        if self.fail:
            raise self.fail
        if size is None or size < 0:
            raise AssertionError("unbounded read")
        return self.real.read(size)

    def close(self):
        self.closes += 1
        self.real.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def __getattr__(self, name):
        if name in ("readall", "readlines", "readline", "readinto"):
            raise AssertionError("unbounded read API " + name)
        return getattr(self.real, name)


class Store:
    """A throwaway media_root with the real originals/<prefix>/<sha>.<ext> layout, plus a spy on Path.open."""

    def __init__(self, test):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root, self.spies, self.opens, self.before_open, self.fail = Path(tmp.name), [], 0, None, None
        real_open = Path.open
        store = self

        def spy_open(path, mode="r", *a, **kw):
            if "originals" not in path.parts or mode != "rb":
                return real_open(path, mode, *a, **kw)
            store.opens += 1
            if store.before_open:
                store.before_open(path)
            spy = Spy(real_open(path, mode, *a, **kw), fail=store.fail)
            store.spies.append(spy)
            return spy

        for patcher in (mock.patch.object(Path, "open", spy_open),
                        mock.patch.object(Path, "read_bytes", side_effect=AssertionError("read_bytes used"))):
            patcher.start()
            test.addCleanup(patcher.stop)

    def put(self, sha, data, ext="jpg"):
        folder = self.root / "originals" / sha[:2]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{sha}.{ext}").write_bytes(data)
        return folder / f"{sha}.{ext}"

    def ctx(self, **extra):
        return SimpleNamespace(today="2026-11-08", content=CONTENT, texts=["the lemons"], media_root=str(self.root), **extra)


class FilesystemBounds(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(media, "MAX_BYTES", CAP)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = Store(self)

    def test_filesystem_cap_is_checked_before_hash_and_review(self):
        data = b"x" * (CAP + 1)
        sha = sha_of(data)
        for ext in ("jpg", "png"):
            path = self.store.put(sha, data, ext)
            with mock.patch.object(item_add, "picture_review") as review, \
                    mock.patch.object(item_add.hashlib, "sha256", side_effect=AssertionError("refused bytes were hashed")):
                self.assertIsNone(item_add._original(self.store.ctx(), sha))
                self.assertEqual(item_add._picture_notes(self.store.ctx(), sha), ())
            review.assert_not_called()
            self.assertEqual(raw(path), data)  # source untouched
            path.unlink()
        self.assertTrue(self.store.spies)
        for spy in self.store.spies:
            self.assertEqual(spy.reads, [CAP + 1])  # one explicit bounded read, nothing drained
            self.assertEqual(spy.closes, 1)

    def test_exact_cap_and_small_matching_originals_keep_exact_bytes(self):
        for size in (CAP, CAP - 10, 1):
            data = bytes(range(size)) if size < 256 else b"y" * size
            sha = sha_of(data)
            self.store.put(sha, data)
            self.assertEqual(item_add._original(self.store.ctx(), sha), data)
        data = b"z" * 10
        self.store.put("a" * 64, data)  # name does not match the content: hash check still refuses
        self.assertIsNone(item_add._original(self.store.ctx(), "a" * 64))
        self.store.put(sha_of(b""), b"")  # empty file named by its own digest: the unchanged bytes result
        self.assertEqual(item_add._original(self.store.ctx(), sha_of(b"")), b"")
        self.assertIsNone(item_add._original(self.store.ctx(), "b" * 64))  # missing
        self.assertIsNone(item_add._original(SimpleNamespace(), "b" * 64))  # no way to read

    def test_growth_after_metadata_cannot_escape_actual_read_limit(self):
        final = b"g" * (CAP + 1)  # the digest of the grown file matches its name: only the length guard can refuse it
        sha = sha_of(final)
        path = self.store.put(sha, b"g" * 3)  # a small genuine file when first looked at

        def grow(opened):
            self.assertTrue(opened.is_file())  # the genuine metadata check has already happened
            opened.write_bytes(final)  # and now it is longer than the cap, with a digest that matches its name

        self.store.before_open = grow
        with mock.patch.object(item_add, "picture_review") as review:
            self.assertIsNone(item_add._original(self.store.ctx(), sha))
            self.assertEqual(item_add._picture_notes(self.store.ctx(), sha), ())
        review.assert_not_called()
        self.assertEqual(len(self.store.spies), 2)
        for spy in self.store.spies:
            self.assertEqual(spy.reads, [CAP + 1])
            self.assertEqual(spy.closes, 1)
        self.assertEqual(raw(path), final)

    def test_read_error_closes_owned_stream_and_keeps_none(self):
        data = b"e" * 10
        sha = sha_of(data)
        path = self.store.put(sha, data)
        self.store.fail = OSError("PATHCANARY " + str(path))
        before = path.stat().st_mtime_ns
        with mock.patch("builtins.print") as printed:
            self.assertIsNone(item_add._original(self.store.ctx(), sha))
        printed.assert_not_called()
        self.assertEqual(self.store.opens, 1)  # no fallback to the png sibling or a second read
        self.assertEqual(len(self.store.spies), 1)
        self.assertEqual(self.store.spies[0].closes, 1)
        self.assertEqual(self.store.spies[0].reads, [CAP + 1])
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), [path.name])
        self.assertEqual(path.stat().st_mtime_ns, before)
        self.assertEqual(raw(path), data)


class CallbackBounds(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(media, "MAX_BYTES", CAP)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_callback_oversize_rejected_before_bytes_copy_or_review(self):
        for make in (bytes, bytearray):
            for size, expected in ((CAP, b"c" * CAP), (CAP - 1, b"c" * (CAP - 1)), (CAP + 1, None)):
                calls = []

                def photo_bytes(sha, value=make(b"c" * size)):
                    calls.append(sha)
                    return value

                with mock.patch.object(item_add, "picture_review", return_value=((), ())) as review:
                    ctx = SimpleNamespace(photo_bytes=photo_bytes)
                    got = item_add._original(ctx, "d" * 64)
                    item_add._picture_notes(ctx, "d" * 64)
                self.assertEqual(got, expected)
                self.assertIs(type(got), bytes if expected is not None else type(None))
                self.assertEqual(len(calls), 2)  # once per call above
                self.assertEqual(review.call_count, 0 if expected is None else 1)
                if expected is not None:
                    self.assertEqual(review.call_args.args[0], expected)
        for empty in (None, b"", bytearray()):
            ctx = SimpleNamespace(photo_bytes=lambda sha, v=empty: v)
            self.assertIsNone(item_add._original(ctx, "d" * 64))


class SharedCallers(unittest.TestCase):
    def test_shared_item_picture_and_add_fallbacks_are_unchanged(self):
        self.assertIs(ip._original, item_add._original)
        with mock.patch.object(media, "MAX_BYTES", CAP):
            store = Store(self)
            data = b"x" * (CAP + 1)
            sha = sha_of(data)
            store.put(sha, data)
            slots = {"item": LEMONS, "photo": sha, "image_alt": "Lemons in a bowl"}
            with mock.patch.object(item_add, "picture_review") as review, mock.patch.object(ip, "picture_review") as ip_review:
                self.assertEqual(item_add._picture_notes(store.ctx(), sha), ())
                with self.assertRaises(ip.Refusal) as caught:
                    ip.plan_picture(slots, store.ctx())
                self.assertEqual(caught.exception.reply, ip.NO_PHOTO)
                self.assertEqual(ip.review(store.ctx(), sha), ((), (ip.NOT_CHECKED,)))
            review.assert_not_called()
            ip_review.assert_not_called()

            # a bad (over-limit) jpg does not fall through to a good png sibling
            good = b"good!"
            gsha = sha_of(good)
            store.put(gsha, b"j" * (CAP + 1), "jpg")
            store.put(gsha, good, "png")
            self.assertIsNone(item_add._original(store.ctx(), gsha))

    def test_valid_original_still_reaches_review_with_its_bytes_and_flag(self):
        data = JAR.read_bytes()
        self.assertLessEqual(len(data), media.MAX_BYTES)
        sha = sha_of(data)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "originals" / sha[:2]
            folder.mkdir(parents=True)
            (folder / f"{sha}.jpg").write_bytes(data)
            ctx = SimpleNamespace(media_root=tmp, house_render=True)
            with mock.patch.object(item_add, "picture_review", return_value=(("ok",), ())) as review, \
                    mock.patch.object(ip, "picture_review", return_value=(("ok",), ())) as ip_review:
                self.assertEqual(item_add._picture_notes(ctx, sha), ("ok",))
                self.assertEqual(ip.review(ctx, sha), (("ok",), ()))
            for call in review.call_args_list + ip_review.call_args_list:
                self.assertEqual(call.args, (data, True))
            self.assertEqual((review.call_count, ip_review.call_count), (1, 1))


if __name__ == "__main__":
    unittest.main()

"""Exercise the offline chat-page CLI with synthetic transcript and image copies."""

import base64
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/hass/npp_chat_page.py"
CHAT = "fixture-chat-private"
SENDER = "fixture-sender-private"
TEXT = "fixture-text-private"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB9sAAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0fixture-photo\xff\xd9"  # Signature fixture; no decoder needed.


class PageTags(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.tags = []
        self.feed(page)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def attrs(self, tag):
        return [attrs for name, attrs in self.tags if name == tag]


def event(id=1, **changes):
    return dict(id=id, utc="2000-01-01T00:00:00Z", chat=CHAT, sender=SENDER,
                direction="in", kind="text", text=TEXT, attachments=[], disposition="queued",
                provider_id=None, reply_to=None, draft_code=None) | changes


class NppChatPageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.inputs = self.root / "input"
        self.inputs.mkdir()
        self.copy = self.inputs / "pictures"
        self.copy.mkdir()
        self.export = self.inputs / "events.jsonl"
        self.out = self.root / "page.html"
        self.export_events(event())

    def export_events(self, *events):
        self.export.write_text("".join(json.dumps(row) + "\n" for row in events), encoding="utf-8")

    def run_cli(self, *args, out=None, umask=-1, required=True):
        command = [sys.executable, "-B", str(SCRIPT)]
        if required:
            command += ["--export", str(self.export), "--attachments", str(self.copy),
                        "--out", str(self.out if out is None else out)]
        result = subprocess.run([*command, *args], cwd=self.root, capture_output=True,
                                text=True, timeout=10, umask=umask)
        for private in (str(self.root), str(SCRIPT), CHAT, SENDER, TEXT):
            self.assertNotIn(private, result.stdout + result.stderr)
        return result

    def assert_pass(self, result, count=1):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.splitlines()[-1], f"PASS npp_chat_page {count} events")
        return self.out.read_text(encoding="utf-8")

    def assert_fail(self, result, reason):
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        self.assertEqual(result.stdout.splitlines(), [f"FAIL {reason}", "FAIL npp_chat_page"])

    def attachment(self, data, filename="{sha}", contents=None):
        sha = hashlib.sha256(data).hexdigest()
        (self.copy / filename.format(sha=sha)).write_bytes(data if contents is None else contents)
        return sha

    def test_c1_page_order_and_escape(self):
        # A reader that trusts file order, drops a chat filter, or treats text as markup fails here.
        self.export_events(event(10, direction="out", text='last <img src="nope"> & "quote"'),
                           event(4, chat="fixture-other-chat", text="unselected message"),
                           event(2, utc="<when>", sender="<fixture-speaker>", text="first <script>"))
        page = self.assert_pass(self.run_cli(), count=3)
        self.assertIn("unselected message", page)
        page = self.assert_pass(self.run_cli("--chat", CHAT, "--force"), count=2)
        tags = PageTags(page)
        self.assertEqual(tags.attrs("article"), [{"class": "bubble in"}, {"class": "bubble out"}])
        self.assertLess(page.index("first &lt;script&gt;"), page.index("last &lt;img"))
        self.assertIn("&lt;fixture-speaker&gt; · &lt;when&gt;", page)
        self.assertIn("&lt;img src=&quot;nope&quot;&gt; &amp; &quot;quote&quot;", page)
        self.assertNotIn("unselected message", page)
        self.assertFalse(tags.attrs("script") or tags.attrs("img"))
        self.assertRegex(page, r"\.in\s*\{[^}]*margin-right: auto")
        self.assertRegex(page, r"\.out\s*\{[^}]*margin-left: auto")

    def test_c2_attachments_verified(self):
        # A matching name, a plausible header, or a correct hash alone is not verification.
        png = self.attachment(PNG, "card-{sha}.png")
        jpg = self.attachment(JPEG)
        self.attachment(JPEG, contents=b"bad alias")  # A bad bare file cannot mask a valid copy.
        self.attachment(JPEG, "{sha}.bin")
        bare = self.attachment(JPEG + b"bare fixture")
        wrong = self.attachment(PNG + b"expected", "{sha}.png", contents=PNG)
        not_image = self.attachment(b"<svg>not an image</svg>", "card-{sha}.png")
        truncated = self.attachment(b"\x89PNG", "{sha}.png")
        absent = "0" * 64
        missing = (wrong, not_image, truncated, absent)
        self.export_events(event(1, kind="photo", attachments=[png, jpg, bare, *missing]),
                           event(2, direction="out", attachments=[absent]))
        result = self.run_cli()
        page = self.assert_pass(result, count=2)
        tags = PageTags(page)
        images = [attrs["src"] for attrs in tags.attrs("img")]
        self.assertEqual(len(images), 3)
        for uri, mime, data in zip(images, ("png", "jpeg", "jpeg"), (PNG, JPEG, JPEG + b"bare fixture")):
            prefix, encoded = uri.split(",", 1)
            self.assertEqual(prefix, f"data:image/{mime};base64")
            self.assertEqual(base64.b64decode(encoded, validate=True), data)
        for sha in missing:
            self.assertIn(f"picture {sha[:8]} not in copy", page)
        self.assertCountEqual(result.stdout.splitlines()[:-1],
                              [f"NOTE missing-attachment {sha[:8]}" for sha in missing])
        self.assertFalse(any("href" in attrs for _, attrs in tags.tags))
        self.assertNotIn(str(self.copy), page)
        self.assertRegex(page, r"img\s*\{[^}]*max-width: 100%")

    def test_c3_markers(self):
        # Mark the actual outbound lines, not an inbound yes or the whole multi-line bubble.
        png = self.attachment(PNG, "card-{sha}.png")
        self.export_events(event(1, text="yes fade-2\nPosted: inbound"),
                           event(2, direction="out", text="Fixture edit\nReply yes fade-2, or edit.",
                                 attachments=[png]),
                           event(3, direction="out", text="Posted: https://example.invalid/card"))
        page = self.assert_pass(self.run_cli(), count=3)
        header = page.split("</header>", 1)[0]
        self.assertIn("1 messages in · 2 messages out · 1 pictures", header)
        self.assertIn('<div class="message">yes fade-2</div>', page)
        self.assertIn('<div class="message">Posted: inbound</div>', page)
        self.assertIn('<div class="message">Fixture edit</div>', page)
        self.assertIn('<div class="message marker approval">Reply yes fade-2, or edit.</div>', page)
        self.assertIn('<div class="message marker posted">Posted: https://example.invalid/card</div>', page)

    def test_c4_private_output(self):
        # A direct open can inherit a wide mode, clobber by default, or follow aliases into git.
        for umask in (0o000, 0o777):
            with self.subTest(umask=umask):
                page = self.assert_pass(self.run_cli(out=self.out.name, umask=umask))
                self.assertIn(TEXT, page)
                self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
                self.out.unlink()
        self.out.write_bytes(b"prior fixture output")
        self.out.chmod(0o644)
        self.assert_fail(self.run_cli(), "output exists (use --force)")
        self.assertEqual(self.out.read_bytes(), b"prior fixture output")
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o644)
        self.assert_pass(self.run_cli("--force"))
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o600)
        for linked in (False, True):
            with self.subTest(linked=linked):
                worktree = self.root / ("linked" if linked else "checkout")
                nested = worktree / "nested" / "deep"
                nested.mkdir(parents=True)
                marker = worktree / ".git"
                if linked:
                    marker.write_text("gitdir: synthetic\n", encoding="utf-8")
                else:
                    marker.mkdir()
                alias = self.root / f"alias-{linked}"
                alias.symlink_to(nested, target_is_directory=True)
                for parent in (nested, alias):
                    dest = parent / "private.html"
                    self.assert_fail(self.run_cli("--force", out=dest), "output inside git worktree")
                    self.assertFalse(dest.exists())
        leaf = self.root / "linked-output.html"
        leaf.symlink_to(self.out)
        saved = self.out.read_bytes()
        self.assert_fail(self.run_cli("--force", out=leaf), "output must be a regular file")
        self.assertTrue(leaf.is_symlink())
        self.assertEqual(self.out.read_bytes(), saved)

    def test_c5_bad_input(self):
        # Bad rows after a good row must not leave even a partial private page.
        self.export.unlink()
        self.assert_fail(self.run_cli(), "export unavailable")
        self.assertFalse(self.out.exists())
        good = json.dumps(event()) + "\n"
        for bad, reason in ((TEXT, "invalid export JSON"), ('{"id":2}', "invalid event"),
                            (json.dumps(event(2, attachments=["../not-a-hash"])), "invalid event")):
            with self.subTest(reason=reason):
                self.export.write_text(good + bad + "\n", encoding="utf-8")
                self.assert_fail(self.run_cli(), reason)
                self.assertFalse(self.out.exists())

    def test_c6_read_only(self):
        # Neither rendering nor a forced output pointed back into a copy may mutate it.
        png = self.attachment(PNG, "{sha}.png")
        self.export_events(event(kind="photo", attachments=[png]))

        def snapshot():
            return {path.relative_to(self.inputs): (path.stat().st_mtime_ns,
                     path.read_bytes() if path.is_file() else None)
                    for path in (self.inputs, *self.inputs.rglob("*"))}

        before = snapshot()
        self.assert_pass(self.run_cli())
        self.assertEqual(snapshot(), before)
        for dest in (self.export, self.copy / "new.html", self.copy / f"{png}.png"):
            self.assert_fail(self.run_cli("--force", out=dest), "output overlaps inputs")
        self.assertEqual(snapshot(), before)

    def test_c7_usage(self):
        # Usage failures must not be mistaken for input failures or echo private values.
        for args in ((), ("--unrecognized", CHAT, str(self.root)), ("--chat",)):
            with self.subTest(args=args):
                result = self.run_cli(*args, required=bool(args))
                self.assertEqual((result.returncode, result.stdout), (2, ""))
                self.assertIn("usage: npp_chat_page", result.stderr)
                self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()

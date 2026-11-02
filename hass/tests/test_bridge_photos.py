"""AV2022-09 (H10) tests: BlueBubblesPhotos.fetch(guid, n) returns a message's attachment bytes from loopback
BlueBubbles: 20 MiB cap, URL rules as the sender, no proxy/redirect, the password never in an error.
Fake transports only: nothing listens, connects or downloads.
Run: python3 -m unittest hass.tests.test_bridge_photos -v"""

import json, os, tempfile, unittest, urllib.request  # noqa: E401
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

from hass import bridge_photos, conversation, media
from hass.bridge import BridgeError, _NoRedirect
from hass.bridge_photos import BlueBubblesPhotos
from hass.conversation import PHOTO_QUESTION, AttachmentPending, Inbound
from hass.fixture_chat import FixtureAdapter
from hass.tests.test_conversation import CHAT, OWNER, SETTINGS, T0
from hass.tests.test_set_photo import FIXTURES, PhotoRepo, _settings

JPG = (FIXTURES / "pixel.jpg").read_bytes()
PASSWORD, BASE = "s3cret-pw", "http://127.0.0.1:1234"


def _meta(*items):
    return 200, json.dumps({"status": 200, "data": {"attachments": list(items)}}).encode()


class FakeTransport:
    """Answers the metadata GET with `meta` and each download with files[<attachment guid>]; records every call."""

    def __init__(self, meta=None, files=None, exc=None):
        self.meta, self.exc, self.calls = meta or _meta({"guid": "att-1", "totalBytes": len(JPG)}), exc, []
        self.files = files if files is not None else {"att-1": (200, JPG)}

    def __call__(self, url, headers, timeout, limit):
        self.calls.append((url, headers, timeout, limit))
        if self.exc: raise self.exc(url)
        parts = urlsplit(url).path.split("/")
        return self.files[unquote(parts[4])] if parts[3] == "attachment" else self.meta


class PhotosTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.pw = Path(tmp.name) / "password"
        self.pw.write_text(PASSWORD + "\n")
        os.chmod(self.pw, 0o600)

    def photos(self, fake):
        return BlueBubblesPhotos(BASE, self.pw, transport=fake)

    def fails(self, fake, code, guid="msg-1", n=1):
        with self.assertRaises(BridgeError) as ctx: self.photos(fake).fetch(guid, n)
        exc = ctx.exception
        self.assertEqual(exc.code, code)
        for text in (str(exc), repr(exc.args)):
            self.assertFalse(PASSWORD in text or "password=" in text, text)
        self.assertEqual((exc.__cause__, exc.__context__), (None, None))
        return exc

    def test_one_attachment_downloaded_password_only_in_query(self):
        fake = FakeTransport()
        data = self.photos(fake).fetch("msg-1", 1)
        self.assertEqual(data, [JPG])
        self.assertEqual(media.check_photo(data[0]), "jpeg")
        paths = [urlsplit(u).path for u, *_ in fake.calls]
        self.assertEqual(paths, ["/api/v1/message/msg-1", "/api/v1/attachment/att-1/download"])
        for url, headers, timeout, _ in fake.calls:
            self.assertTrue(url.startswith(BASE + "/api/v1/"))
            self.assertEqual(parse_qs(urlsplit(url).query)["password"], [PASSWORD])
            self.assertNotIn(PASSWORD, urlsplit(url).path + repr(headers))
            self.assertEqual(timeout, 20)
        self.assertEqual(parse_qs(urlsplit(fake.calls[0][0]).query)["with"], ["attachment"])
        self.assertEqual([c[3] for c in fake.calls], [bridge_photos.META_LIMIT, media.MAX_BYTES])

    def test_fewer_attachments_than_asked_is_count_error_without_download(self):
        self.fails(fake := FakeTransport(), "attachment-count", n=2)
        self.assertEqual(len(fake.calls), 1)

    def test_size_cap(self):
        self.fails(FakeTransport(files={"att-1": (200, b"x" * (media.MAX_BYTES + 1))}), "too-large")
        exact = b"x" * media.MAX_BYTES
        fake = FakeTransport(meta=_meta({"guid": "att-1", "totalBytes": media.MAX_BYTES}),
                             files={"att-1": (200, exact)})
        self.assertEqual(self.photos(fake).fetch("msg-1", 1), [exact])
        self.fails(fake := FakeTransport(meta=_meta({"guid": "att-1", "totalBytes": media.MAX_BYTES + 1})), "too-large")
        self.assertEqual(len(fake.calls), 1)
        self.fails(FakeTransport(files={"att-1": (200, b"")}), "empty")

    def test_http_and_transport_failures_never_carry_the_password(self):
        self.assertEqual(self.fails(FakeTransport(meta=(404, b"")), "http-error").status, 404)
        self.assertEqual(self.fails(FakeTransport(files={"att-1": (500, b"")}), "http-error").status, 500)
        self.fails(FakeTransport(exc=OSError), "transport-error")
        self.fails(FakeTransport(meta=(301, b"")), "http-error")

    def test_unreadable_password_file_makes_no_transport_call(self):
        def group_readable(): os.chmod(self.pw, 0o640)
        def symlink():
            target = self.pw.with_name("real")
            os.replace(self.pw, target)
            os.symlink(target, self.pw)
        def empty(): self.pw.write_text("  \n")
        for change in (group_readable, symlink, empty):
            with self.subTest(change.__name__):
                self.setUp()
                photos = self.photos(fake := FakeTransport())
                change()
                with self.assertRaises(BridgeError) as ctx: photos.fetch("msg-1", 1)
                self.assertEqual(ctx.exception.code, "password-unreadable")
                self.assertEqual(fake.calls, [])

    def test_base_url_must_be_loopback_with_port_and_nothing_else(self):
        for url in ("http://10.0.0.5:1234", "http://user:pw@127.0.0.1:1234", "http://127.0.0.1:1234/api",
                    "http://127.0.0.1", "ftp://127.0.0.1:1234", None):
            with self.subTest(url), self.assertRaises(ValueError): BlueBubblesPhotos(url, self.pw)

    def test_guid_and_count_are_checked(self):
        fake = FakeTransport()
        for guid, n in (("", 1), ("g" * 201, 1), (None, 1), ("m", 0), ("m", 11), ("m", True), ("m", "1")):
            with self.subTest(guid=guid, n=n), self.assertRaises(ValueError): self.photos(fake).fetch(guid, n)
        self.assertEqual(fake.calls, [])

    def test_bad_metadata(self):
        self.fails(FakeTransport(meta=(200, b"<html>")), "not-json")
        self.fails(FakeTransport(meta=(200, b"[" * 100000)), "not-json")
        self.fails(FakeTransport(meta=(200, b'{"status": 200}')), "shape")
        self.fails(FakeTransport(meta=(200, b"[]")), "shape")
        self.fails(FakeTransport(meta=_meta({"totalBytes": 3})), "shape")
        self.fails(FakeTransport(meta=(200, b"x" * (bridge_photos.META_LIMIT + 1))), "too-large")

    def test_guids_are_one_percent_encoded_path_segment(self):
        fake = FakeTransport(meta=_meta({"guid": "a/b?c"}), files={"a/b?c": (200, JPG)})
        self.photos(fake).fetch("x/y?password=z", 1)
        message, download = (urlsplit(u) for u, *_ in fake.calls)
        self.assertEqual(message.path, "/api/v1/message/x%2Fy%3Fpassword%3Dz")
        self.assertEqual(download.path, "/api/v1/attachment/a%2Fb%3Fc/download")
        self.assertEqual(parse_qs(message.query), {"with": ["attachment"], "password": [PASSWORD]})
        self.assertEqual(parse_qs(download.query), {"password": [PASSWORD]})

    def test_default_transport_has_no_proxy_and_no_redirect(self):
        handlers = bridge_photos._OPENER.handlers  # ProxyHandler({}) opens nothing, so neither it nor the
        self.assertFalse([h for h in handlers if isinstance(h, urllib.request.ProxyHandler)])  # env default is kept
        self.assertTrue(any(isinstance(h, _NoRedirect) for h in handlers))
        response = mock.MagicMock(status=200)
        response.__enter__.return_value = response
        response.read.return_value = b"abc"
        with mock.patch.object(bridge_photos._OPENER, "open", return_value=response) as opened:
            self.assertEqual(bridge_photos._urllib_transport(BASE + "/x", {}, 5, 7), (200, b"abc"))
        response.read.assert_called_once_with(8)
        self.assertEqual(opened.call_args.args[0].get_method(), "GET")

    def test_timeout_must_be_int_seconds_1_to_120(self):  # RF1500-13
        message = "timeout must be a whole number of seconds from 1 to 120"
        for bad in (0, -1, 121, 20.5, "20", None, True, False):
            with self.subTest(timeout=bad):
                with self.assertRaises(ValueError) as ctx:
                    BlueBubblesPhotos(BASE, self.pw, transport=FakeTransport(), timeout=bad)
                self.assertEqual(str(ctx.exception), message)
                for leak in ("127.0.0.1", "1234", str(self.pw), "password"):
                    self.assertNotIn(leak, str(ctx.exception))
        for good in (1, 120):
            with self.subTest(timeout=good):
                fake = FakeTransport()
                BlueBubblesPhotos(BASE, self.pw, transport=fake, timeout=good).fetch("msg-1", 1)
                self.assertEqual([c[2] for c in fake.calls], [good, good])
        with self.assertRaises(ValueError) as ctx:  # bad URL and bad timeout: the URL message wins
            BlueBubblesPhotos("http://10.0.0.5:1234", self.pw, timeout=0)
        self.assertIn("base_url", str(ctx.exception))


class ConversationWiringTests(unittest.TestCase):
    def setUp(self):
        self.repo = PhotoRepo()
        self.addCleanup(self.repo.cleanup)
        _settings(self.repo, **SETTINGS, mediaRoot=str(self.repo.media))
        self.pw = self.repo.media.parent / "bb-password"
        self.pw.write_text(PASSWORD)
        os.chmod(self.pw, 0o600)

    def conv(self, fake):
        photos = BlueBubblesPhotos(BASE, self.pw, transport=fake)
        conv = conversation.Conversation(str(self.repo.state), conversation.Editor(self.repo.state), None,
                                         lambda: T0, photos=photos)
        self.addCleanup(conv.db.close)
        return conv

    def say(self, conv):
        return conv.handle(Inbound("msg-1", CHAT, OWNER, "", received_at=T0.isoformat(), attachments=1))

    def test_photo_message_asks_the_photo_question(self):
        fake = FakeTransport()
        self.assertEqual(self.say(conv := self.conv(fake)), "photo-draft")
        conv.flush(out := FixtureAdapter())
        self.assertTrue(out.sent[-1]["text"].startswith(PHOTO_QUESTION))
        self.assertEqual(urlsplit(fake.calls[0][0]).path, "/api/v1/message/msg-1")

    def test_transport_failure_takes_the_retry_path(self):
        conv = self.conv(FakeTransport(exc=OSError))
        with self.assertRaises(AttachmentPending): self.say(conv)
        self.assertEqual(list(conv.db.execute("SELECT code FROM drafts")), [])

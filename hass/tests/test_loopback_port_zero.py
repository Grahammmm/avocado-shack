"""RF0110-3 (H05/H08): loopback URL checks refuse an explicit port 0, so a mistyped URL fails at setup.
No network (fake transport, no socket). Run: python3 -m unittest discover -s hass/tests -t . -v"""

import tempfile, unittest  # noqa: E401
from pathlib import Path

from hass.bridge import BlueBubblesSender
from hass.interpreter_local import URL_ERROR, LocalInterpreter, check_url
from hass.label_reader import LabelReader

BASE_URL_ERROR = "base_url must be http(s)://127.0.0.1:<port> or http(s)://localhost:<port>"


class NoCall:
    """A transport that records any call; none is expected."""
    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return 200, b"{}"


class InterpreterPortZeroTests(unittest.TestCase):
    def test_port_zero_refused_with_url_error(self):
        for url in ("http://127.0.0.1:0", "http://localhost:0/", "http://[::1]:0", "http://127.0.0.1:00"):
            with self.subTest(url=url), self.assertRaises(ValueError) as caught:
                check_url(url)
            self.assertEqual(str(caught.exception), URL_ERROR)

    def test_ports_one_to_65535_and_no_port_still_accepted(self):
        for url, want in (("http://127.0.0.1", "http://127.0.0.1"), ("http://127.0.0.1:1", "http://127.0.0.1:1"),
                          ("http://localhost:11434/", "http://localhost:11434"),
                          ("http://[::1]:65535", "http://[::1]:65535")):
            with self.subTest(url=url):
                self.assertEqual(check_url(url), want)

    def test_interpreter_and_label_reader_refuse_port_zero_before_any_call(self):
        for build in (lambda t: LocalInterpreter("http://127.0.0.1:0", "m", "p", transport=t),
                      lambda t: LabelReader("http://127.0.0.1:0", "m", transport=t)):
            transport = NoCall()
            with self.assertRaises(ValueError) as caught:
                build(transport)
            self.assertEqual(str(caught.exception), URL_ERROR)
            self.assertEqual(transport.calls, [])


class SenderPortZeroTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix="hass-port0-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)

    def test_port_zero_refused_before_password_file_is_read(self):
        missing = self.folder / "no-such-password"  # never created: the URL check must come first
        for url in ("http://127.0.0.1:0", "https://localhost:0"):
            transport = NoCall()
            with self.subTest(url=url), self.assertRaises(ValueError) as caught:
                BlueBubblesSender(url, missing, transport=transport)
            self.assertEqual(str(caught.exception), BASE_URL_ERROR)
            self.assertEqual(transport.calls, [])

    def test_nonzero_port_still_accepted(self):
        path = self.folder / "password"
        path.write_text("fixture-password-not-real\n", "utf-8")
        path.chmod(0o600)
        sender = BlueBubblesSender("http://127.0.0.1:1234", path, transport=NoCall())
        self.assertEqual(repr(sender), "BlueBubblesSender('http://127.0.0.1:1234')")

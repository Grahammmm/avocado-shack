"""BlueBubblesPhotos refuses an explicit zero port at setup, like BlueBubblesSender. Offline: only the private-file seam is patched."""
import unittest
from unittest import mock

from hass import bridge_photos
from hass.bridge_photos import BlueBubblesPhotos

URL_ERROR = "base_url must be http(s)://127.0.0.1:<port> or http(s)://localhost:<port>"
TIMEOUT_ERROR = "timeout must be a whole number of seconds from 1 to 120"
HOSTS = ("127.0.0.1", "localhost")
SCHEMES = ("http", "https")


class PhotoSourcePortZeroTests(unittest.TestCase):
    def build(self, url, timeout=20, private=None):
        """(source or None, error or None, private-file spy, transport spy)."""
        spy = private or mock.Mock(return_value="/inert/password")
        transport = mock.Mock()
        with mock.patch.object(bridge_photos, "_private_file", spy):
            try:
                return BlueBubblesPhotos(url, "/inert/password", transport=transport, timeout=timeout), None, spy, transport
            except ValueError as exc:
                return None, exc, spy, transport

    def assertUrlRefused(self, url, **kw):
        source, err, spy, transport = self.build(url, **kw)
        self.assertIsNone(source, url)
        self.assertEqual(str(err), URL_ERROR, url)
        spy.assert_not_called()
        transport.assert_not_called()

    def test_zero_port_refused_for_each_existing_host_and_scheme(self):
        for scheme in SCHEMES:
            for host in HOSTS:
                url = f"{scheme}://{host}:0"
                with self.subTest(url):
                    self.assertUrlRefused(url)

    def test_zero_spellings_and_root_slash_are_not_default_ports(self):
        for scheme in SCHEMES:
            for host in HOSTS:
                for port in ("0", "00", "000"):
                    for slash in ("", "/"):
                        url = f"{scheme}://{host}:{port}{slash}"
                        with self.subTest(url):
                            self.assertUrlRefused(url)

    def test_nonzero_boundary_ports_preserve_normalization(self):
        for scheme in SCHEMES:
            for host in HOSTS:
                for port in (1, 1234, 65535):
                    for slash in ("", "/"):
                        url = f"{scheme}://{host}:{port}{slash}"
                        with self.subTest(url):
                            source, err, spy, transport = self.build(url, timeout=7)
                            self.assertIsNone(err)
                            self.assertEqual(source._base, f"{scheme}://{host}:{port}")
                            self.assertEqual(repr(source), f"BlueBubblesPhotos('{scheme}://{host}:{port}')")
                            self.assertEqual(source._timeout, 7)
                            spy.assert_called_once_with("/inert/password")
                            transport.assert_not_called()

    def test_existing_url_refusals_and_precedence_stay_fixed(self):
        bad = ("http://127.0.0.1", "http://127.0.0.1:", "http://127.0.0.1:abc", "http://127.0.0.1:-1",
               "http://127.0.0.1:65536", "http://10.0.0.5:1234", "ftp://127.0.0.1:1234",
               "http://user:pw@127.0.0.1:1234", "http://127.0.0.1:1234/api", "http://127.0.0.1:1234?x=1",
               "http://127.0.0.1:1234#frag", None)
        for url in bad:
            with self.subTest(url):
                self.assertUrlRefused(url)
        # URL error wins over both an invalid timeout and an unusable password file
        failing = mock.Mock(side_effect=ValueError("private file refused"))
        self.assertUrlRefused("http://127.0.0.1:0", timeout=0, private=failing)

    def test_valid_url_keeps_file_then_timeout_validation(self):
        failing = mock.Mock(side_effect=ValueError("private file refused"))
        source, err, spy, _ = self.build("http://127.0.0.1:1234", timeout=0, private=failing)
        self.assertIsNone(source)
        self.assertEqual(str(err), "private file refused")
        spy.assert_called_once()
        for timeout in (0, 121, True, 1.5, "5"):
            with self.subTest(timeout=timeout):
                source, err, _, _ = self.build("http://127.0.0.1:1234", timeout=timeout)
                self.assertIsNone(source)
                self.assertEqual(str(err), TIMEOUT_ERROR)
        for timeout in (1, 120):
            source, err, _, _ = self.build("http://localhost:1234", timeout=timeout)
            self.assertIsNone(err)
            self.assertEqual(source._timeout, timeout)
        source, err, _, _ = self.build("http://localhost:1234")
        self.assertIsNone(err)
        self.assertEqual(source._timeout, 20)


if __name__ == "__main__":
    unittest.main()

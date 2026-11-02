"""AVB-04 (H03) tests: maker and source links must be real public https:// web addresses.

content_model._https refuses no host, a dotless host, an IP-literal or private-name host, user:password, an explicit
port, a URL over 500 characters, any backslash (a browser ends the host there) and a host that is not plain ASCII
letters/digits/hyphens/dots, each with one named reason that never echoes the value. Fixture content only
(throwaway Git repo via test_catalog_ops.CatalogRepo); no DNS lookups.
Run: python3 -m unittest hass.tests.test_https_links -v
"""

import unittest

from hass.content_model import _https, load_and_validate, CONTENT_DIR, SITE_DIR
from hass.tests.test_catalog_ops import CatalogTestCase

NEW = {"key": "Test Farm", "name": "Test Farm", "place": "Somewhere, California", "story": "Grows things."}


def reason_for(url):
    problems = []
    _https(problems, "w", url)
    if not problems:
        return None
    prefix, suffix = "w: must be a public https:// web address (", ")"
    assert problems[0].startswith(prefix) and problems[0].endswith(suffix), problems
    return problems[0][len(prefix):-len(suffix)]


class HttpsReasonTests(unittest.TestCase):
    def check(self, reason, *urls):
        for url in urls:
            with self.subTest(url=url[:60]):
                self.assertEqual(reason_for(url), reason)

    def test_no_host_and_dotless_host(self):
        self.check("no host", "https://", "https:///about", "https://[::1", "https://.")
        self.check("host has no dot", "https://x", "https://farm/about", "https://x.")

    def test_ip_literals(self):
        self.check("IP address", "https://127.0.0.1/a", "https://[::1]/", "https://10.0.0.5", "https://8.8.8.8/",
                   "https://127.1/", "https://2130706433/", "https://[2001:db8::1]/")

    def test_backslash_is_refused_because_a_browser_ends_the_host_there(self):
        # urlsplit keeps "\.farm.com" inside a dotted hostname; a browser reads \ as / and goes to 127.0.0.1/localhost
        self.check("backslash", "https://127.0.0.1\\.farm.com/", "https://localhost\\.farm.com/",
                   "https://[::1]\\.farm.com/", "https://farm.com\\@127.0.0.1/", "https://farm.com/a\\b",
                   "https://\\\\localhost/")

    def test_ip_literals_a_browser_would_read(self):
        self.check("IP address", "https://127.0.0.0x1/", "https://0x7f.0.0.1/", "https://farm.0x/", "https://a.0X7F/")

    def test_host_characters_a_browser_may_rewrite(self):
        self.check("host characters", "https://127.0.0.1%2e/", "https://127.0.0.\u30021/", "https://a.localhost\u3002/",
                   "https://\uff4cocalhost.farm.com/", "https://my_farm.com/", "https://farm..com/", "https://.farm.com/",
                   "https://b\u00fccher.com/")

    def test_user_or_password_never_echoed(self):
        self.check("user or password", "https://user:pw@farm.example", "https://user@farm.example", "https://@farm.com")
        problems = []
        _https(problems, "w", "https://sekrit:hunter2@farm.example/x")
        self.assertNotIn("sekrit", problems[0])
        self.assertNotIn("hunter2", problems[0])
        self.assertNotIn("farm.com", problems[0])

    def test_explicit_port(self):
        self.check("port", "https://farm.com:8443/", "https://farm.com:99999/", "https://farm.com:443",
                   "https://[2001:db8::1]:443/")

    def test_private_names(self):
        self.check("private name", "https://shop.local", "https://localhost", "https://localhost/a", "https://LOCALHOST",
                   "https://localhost.", "https://a.localhost", "https://db.internal", "https://a.invalid",
                   "https://a.test", "https://a.example", "https://Shop.LOCAL/")

    def test_length_limit_is_500(self):
        base = "https://farm.com/"
        self.assertIsNone(reason_for(base + "a" * (500 - len(base))))
        self.assertEqual(reason_for(base + "a" * (501 - len(base))), "too long")

    def test_ordinary_addresses_accepted(self):
        for url in ("https://www.example-farm.com/about?x=1#y", "https://example.com", "https://farm.co.uk/a/b",
                    "https://farm.com./", "https://shop-localhost.com", "https://notlocal.com", "https://my.test.farm.org/",
                    "https://xn--bcher-kva.com/", "https://0x7f.farm.com/0x1", "https://127.farm.com/a%5Cb"):
            with self.subTest(url=url):
                self.assertIsNone(reason_for(url))

    def test_older_checks_still_apply_first(self):
        for url in ("http://farm.com", "https://farm.com/a b", "https://farm.com/<x>", 'https://farm.com/"', None, 5):
            problems = []
            _https(problems, "w", url)
            self.assertEqual(problems, ["w: must be an https:// URL without spaces or quotes"])


class MakerLinkOpTests(CatalogTestCase):
    def refused_reason(self, repo, op, args):
        (problem,) = self.assertRejected(repo, "invalid", (op, args))["problems"]
        self.assertTrue(problem.endswith("must be a public https:// web address (" + self.reason + ")"), problem)
        return problem

    def test_maker_add_refuses_each_bad_link_and_makers_json_is_unchanged(self):
        repo = self.repo()
        before = repo.read("hass/content/makers.json")
        for self.reason, url in (("no host", "https://"), ("host has no dot", "https://x"),
                                 ("IP address", "https://127.0.0.1/a"), ("IP address", "https://[::1]/"),
                                 ("user or password", "https://user:pw@farm.example"), ("port", "https://farm.com:8443/"),
                                 ("port", "https://farm.com:99999/"), ("private name", "https://shop.local"),
                                 ("private name", "https://localhost"),
                                 ("backslash", "https://127.0.0.1\\.farm.com/"),
                                 ("backslash", "https://localhost\\.farm.com/"),
                                 ("IP address", "https://127.0.0.0x1/"), ("host characters", "https://127.0.0.1%2e/"),
                                 ("too long", "https://farm.com/" + "a" * 500)):
            with self.subTest(url=url[:40]):
                problem = self.refused_reason(repo, "maker.add", {**NEW, "url": url})
                self.assertIn("maker.add.url", problem)
                self.assertNotIn(url[8:] or "-", problem)
        self.assertEqual(repo.read("hass/content/makers.json"), before)

    def test_maker_add_accepts_a_public_address(self):
        repo = self.repo()
        url = "https://www.example-farm.com/about?x=1#y"
        repo.run(("maker.add", {**NEW, "url": url}))
        self.assertEqual(repo.makers()["Test Farm"]["url"], url)

    def test_maker_edit_refuses_a_bad_link_and_leaves_the_maker(self):
        repo = self.repo()
        key = "Test Farm"
        repo.run(("maker.add", {**NEW, "url": "https://farm.com/a"}))
        before = repo.read("hass/content/makers.json")
        for self.reason, url in (("port", "https://farm.com:8443/"), ("IP address", "https://192.168.1.2/"),
                                 ("private name", "https://farm.internal/"),
                                 ("backslash", "https://127.0.0.1\\.farm.com/"),
                                 ("backslash", "https://localhost\\.farm.com/")):
            with self.subTest(url=url):
                self.refused_reason(repo, "maker.edit", {"key": key, "url": url})
        self.assertEqual(repo.read("hass/content/makers.json"), before)
        repo.run(("maker.edit", {"key": key, "url": "https://www.example-farm.com/about?x=1#y"}))
        self.assertEqual(repo.makers()[key]["url"], "https://www.example-farm.com/about?x=1#y")


class CheckoutContentTests(unittest.TestCase):
    def test_every_link_in_the_checkout_content_still_validates(self):
        content = load_and_validate(CONTENT_DIR, SITE_DIR)
        self.assertTrue(content.makers)
        for key, maker in content.makers.items():
            self.assertIsNone(reason_for(maker["url"]), key)


if __name__ == "__main__":
    unittest.main()

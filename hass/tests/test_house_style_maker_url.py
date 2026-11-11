"""RF0415-12: the maker style URL check uses the content validator's public-https rules."""
import copy
import unittest

from hass import content_model, house_style

BASE = {"name": "Fixture Farm", "place": "Cambria, California",
        "story": "Fixture Farm makes pantry goods in a small workshop. The family packs each batch by hand."}
NAME = "url is public https or absent"


def run(**extra):
    return house_style.check_maker(dict(BASE, **extra), key="Fixture Farm")


def url_check(res):
    return next(c for c in res["checks"] if c["name"] == NAME)


def real_ok(value):
    problems = []
    content_model._https(problems, "u", value)
    return not problems


class MakerUrlTests(unittest.TestCase):
    def test_scheme_prefix_is_not_public_url(self):
        self.assertTrue(run()["pass"])
        for u in ("https://localhost/x", "https://127.0.0.1/x", "https://", "https://farm.com:443/x",
                  "https://farm.com/bad path"):
            res = run(url=u)
            c = url_check(res)
            self.assertFalse(c["ok"] if "ok" in c else c["pass"], u)
            self.assertTrue(c["hard"])
            self.assertFalse(res["pass"], u)

    def test_absent_is_valid_present_null_is_invalid(self):
        self.assertTrue(self.passed(run()))
        for v in (None, "", True, 42, ["https://farm.com"], {"a": 1}):
            rec = dict(BASE, url=v)
            before = copy.deepcopy(rec)
            self.assertFalse(self.passed(house_style.check_maker(rec, key="Fixture Farm")), repr(v))
            self.assertEqual(rec, before)

    @staticmethod
    def passed(res):
        return bool(url_check(res).get("ok", url_check(res).get("pass")))

    def test_public_https_controls_and_length_boundary(self):
        long_ok = "https://farm.com/" + "a" * (500 - len("https://farm.com/"))
        for u, want in (("https://farm.com/p?q=1#f", True), ("https://xn--bcher-kva.example.com/", True),
                        (long_ok, True), (long_ok + "a", False),
                        ("https://farm.com\\@evil.com/", False), ("https://[::1]/x", False),
                        ("https://2130706433/", False), ("https://farm.com%2e/", False)):
            self.assertEqual(self.passed(run(url=u)), want, u)
            self.assertEqual(real_ok(u), want, u)


if __name__ == "__main__":
    unittest.main()

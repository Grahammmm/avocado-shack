"""HASS-LIVE-ADD-2: hass.maker_site, the one polite read of a maker's own page, and the story drafted from it.

No network anywhere: ``fetch`` is given a recorded ``get(url, headers, timeout) -> (status, content type, bytes)`` that serves
the pages in hass/tests/fixtures/maker_site, the wall clock and the sleep are injected, and the real ``_http_get`` is only
exercised with a fake opener. Anything that would reach a socket fails the test.
Run: python3 -B -m unittest hass.tests.test_maker_site -v
"""
import io
import unittest
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from unittest import mock

from hass import live_policy, maker_site as ms

FIXTURES = Path(__file__).parent / "fixtures" / "maker_site"
HARBOR = (FIXTURES / "harbor-lane.html").read_bytes()
CLAIMS_ONLY = (FIXTURES / "claims-only.html").read_bytes()
ADDRESS = "https://harborlane.example/about"
ROBOTS = "https://harborlane.example/robots.txt"
DAY = date(2026, 11, 9)
HTML = "text/html; charset=utf-8"
REAL_GET = ms._http_get  # setUp swaps the module attribute for a tripwire; the opener underneath is faked in the tests that use this


class Recorded:
    """A recorded ``get``: answers from a dict of url -> (status, kind, body), 404 for the rest, and keeps every call."""

    def __init__(self, pages=None):
        self.pages, self.calls = dict(pages or {}), []

    def __call__(self, url, headers, timeout):
        self.calls.append((url, dict(headers), timeout))
        return self.pages.get(url, (404, "", b""))

    @property
    def urls(self):
        return [call[0] for call in self.calls]


class Clock:
    """A wall clock that only moves when the injected sleep does."""

    def __init__(self, now=1000.0):
        self.now, self.slept = now, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class SiteTestCase(unittest.TestCase):
    def setUp(self):
        ms._LAST.clear(), ms._CACHE.clear()
        self.addCleanup(ms._LAST.clear), self.addCleanup(ms._CACHE.clear)
        for target in (mock.patch.object(ms, "_http_get", side_effect=AssertionError("network used")),
                       mock.patch("socket.getaddrinfo", side_effect=AssertionError("network used")),
                       mock.patch("urllib.request.urlopen", side_effect=AssertionError("network used"))):
            target.start(), self.addCleanup(target.stop)
        self.clock = Clock()

    def fetch(self, get, url=ADDRESS, **kw):
        return ms.fetch(url, get=get, sleep=self.clock.sleep, clock=self.clock, today=DAY, **kw)

    def page(self, body=HARBOR, robots=(404, "", b"")):
        return Recorded({ROBOTS: robots, ADDRESS: (200, HTML, body)})


class TheRead(SiteTestCase):
    def test_a_page_comes_back_with_its_address_the_day_and_its_readable_text(self):
        get = self.page()
        page = self.fetch(get)
        self.assertEqual((page["url"], page["retrieved"]), (ADDRESS, "2026-11-09"))
        self.assertIn("Harbor Lane makes small-batch fruit jam and relish in a shared kitchen in Morro Bay.", page["blocks"])
        self.assertEqual(page["blocks"][0], page["blocks"][0].strip())
        self.assertEqual(get.urls, [ROBOTS, ADDRESS])  # robots.txt first, then the one page
        text = " ".join(page["blocks"])
        for left_out in ("window.track", "font:16px", "Home", "Shop now", "We ship to you", "<"):  # script, style, nav, footer
            self.assertNotIn(left_out, text)

    def test_every_request_says_who_it_is_and_carries_nothing_else(self):
        get = self.page()
        self.fetch(get)
        for _url, headers, timeout in get.calls:
            self.assertEqual(set(headers), {"User-Agent", "Accept"})
            self.assertEqual(headers["User-Agent"], ms.USER_AGENT)
            self.assertEqual(timeout, ms.TIMEOUT)

    def test_a_bare_address_becomes_https_and_a_fragment_is_dropped(self):
        get = self.page()
        self.assertEqual(self.fetch(get, "harborlane.example/about#top")["url"], ADDRESS)
        self.assertEqual(self.fetch(get, "  https://harborlane.example/about  ", cache=False)["url"], ADDRESS)

    def test_the_description_meta_comes_first(self):
        self.assertEqual(ms.extract(HARBOR.decode())[0], "Harbor Lane makes small-batch fruit jam and relish in a shared kitchen in Morro Bay.")

    def test_a_page_that_is_not_there_or_not_html_or_empty_cannot_be_used(self):
        cases = {
            "not found": (Recorded({ROBOTS: (404, "", b""), ADDRESS: (404, HTML, b"gone")}), "unreachable"),
            "server error": (Recorded({ADDRESS: (500, HTML, b"oops")}), "unreachable"),
            "no answer": (Recorded({ADDRESS: (0, "", b"")}), "unreachable"),
            "empty body": (Recorded({ADDRESS: (200, HTML, b"")}), "unreachable"),
            "a pdf": (Recorded({ADDRESS: (200, "application/pdf", b"%PDF-1.4 ...")}), "unreadable"),
            "no text": (Recorded({ADDRESS: (200, HTML, b"<html><body><script>x=1</script><div>just a div</div></body></html>")}), "unreadable"),
        }
        for label, (get, code) in cases.items():
            with self.subTest(label=label), self.assertRaises(ms.PageError) as caught:
                self.fetch(get, cache=False)
            self.assertEqual(caught.exception.code, code)
            self.assertEqual(caught.exception.reply, ms.CODES[code])

    def test_every_reply_for_mike_is_plain_words(self):
        from hass import voice
        for code, reply in ms.CODES.items():
            with self.subTest(code=code):
                self.assertEqual(voice.check(reply), [], reply)


class RobotsTxt(SiteTestCase):
    def test_a_site_that_disallows_reading_is_refused_and_its_page_is_never_asked_for(self):
        for rules in ("User-agent: *\nDisallow: /\n", "User-agent: *\nDisallow: /about\n", f"User-agent: {ms.USER_AGENT.split('/')[0]}\nDisallow: /\n"):
            with self.subTest(rules=rules):
                get = self.page(robots=(200, "text/plain", rules.encode()))
                with self.assertRaises(ms.PageError) as caught:
                    self.fetch(get, cache=False)
                self.assertEqual((caught.exception.code, caught.exception.reply), ("refused", ms.CODES["refused"]))
                self.assertEqual(get.urls, [ROBOTS])

    def test_a_robots_file_that_allows_this_page_is_followed(self):
        get = self.page(robots=(200, "text/plain", b"User-agent: *\nDisallow: /cart\nDisallow: /checkout\n"))
        self.assertEqual(self.fetch(get)["url"], ADDRESS)
        self.assertEqual(get.urls, [ROBOTS, ADDRESS])

    def test_forbidden_robots_is_a_refusal_but_missing_or_broken_robots_is_not(self):
        for status in (401, 403):
            with self.subTest(status=status), self.assertRaises(ms.PageError) as caught:
                self.fetch(self.page(robots=(status, "", b"")), cache=False)
            self.assertEqual(caught.exception.code, "refused")
        for status in (404, 410, 500, 0):
            with self.subTest(status=status):
                self.assertEqual(self.fetch(self.page(robots=(status, "", b"")), cache=False)["url"], ADDRESS)


class TheAddress(SiteTestCase):
    def test_an_address_that_is_not_a_public_https_website_is_refused_before_any_request(self):
        for bad in ("http://harborlane.example/about", "ftp://harborlane.example/about", "javascript:alert(1)", "file:///etc/passwd",
                    "https://localhost/about", "https://localhost:8443/", "https://127.0.0.1/about", "https://10.0.0.5/about",
                    "https://192.168.1.20/", "https://169.254.169.254/latest/meta-data", "https://[::1]/about", "https://2130706433/",
                    "https://intranet/about", "https://user:secret@harborlane.example/about", "https://harborlane.example:8443/about",
                    "https://harborlane.example/" + "a" * 300, "", "   ", "not an address", None):
            with self.subTest(address=bad):
                get = Recorded()
                with self.assertRaises(ms.PageError) as caught:
                    self.fetch(get, bad, cache=False)
                self.assertEqual(caught.exception.code, "address")
                self.assertEqual(get.calls, [])

    def test_without_a_recorded_get_a_host_that_is_not_public_is_not_contacted(self):
        """The real read resolves the host first; a name that points inside is never opened (the network patches would fail)."""
        for resolved in ("127.0.0.1", "10.1.2.3", "169.254.169.254", "::1", "192.168.0.9"):
            with self.subTest(resolved=resolved), mock.patch.object(ms.socket, "getaddrinfo", return_value=[(2, 1, 6, "", (resolved, 443))]):
                with self.assertRaises(ms.PageError) as caught:
                    ms.fetch("https://harborlane.example/about", sleep=self.clock.sleep, clock=self.clock, cache=False)
                self.assertEqual(caught.exception.code, "unreachable")
        with mock.patch.object(ms.socket, "getaddrinfo", side_effect=OSError("no such host")):
            with self.assertRaises(ms.PageError):
                ms.fetch("https://harborlane.example/about", sleep=self.clock.sleep, clock=self.clock, cache=False)
        self.assertEqual(self.clock.slept, [])


class Redirects(SiteTestCase):
    WWW = "https://www.harborlane.example/about"
    WWW_ROBOTS = "https://www.harborlane.example/robots.txt"

    def go(self, pages):
        get = Recorded(pages)
        return get, self.fetch(get, cache=False)

    def test_a_redirect_to_another_site_or_a_weaker_address_is_refused(self):
        for new in ("https://elsewhere.example/about", "https://harborlane.example.evil.example/", "http://harborlane.example/about",
                    "https://user@harborlane.example/about", "https://harborlane.example:8443/about", "ftp://harborlane.example/x",
                    "https://localhost/", "//elsewhere.example/about", "https://127.0.0.1/"):
            with self.subTest(new=new), self.assertRaises(ms.PageError) as caught:
                ms._hop(ADDRESS, new)
            self.assertEqual(caught.exception.code, "unreachable")
            get = Recorded({ROBOTS: (404, "", b""), ADDRESS: (302, "", b"", new)})
            with self.subTest(read=new), self.assertRaises(ms.PageError) as caught:
                self.fetch(get, cache=False)
            self.assertEqual((caught.exception.code, get.urls), ("unreachable", [ROBOTS, ADDRESS]))  # the other address is never asked

    def test_a_redirect_inside_the_same_site_is_followed(self):
        self.assertEqual(ms._hop(ADDRESS, "https://harborlane.example/our-story"), "https://harborlane.example/our-story")
        self.assertEqual(ms._hop(ADDRESS, "/our-story#top"), "https://harborlane.example/our-story")
        self.assertEqual(ms._hop(ADDRESS, self.WWW), self.WWW)
        self.assertEqual(ms._hop(self.WWW, ADDRESS), ADDRESS)

    def test_a_followed_redirect_is_checked_against_the_robots_file_of_where_it_lands(self):
        rules = (200, "text/plain", b"User-agent: *\nDisallow: /private\n")
        get = Recorded({ROBOTS: rules, ADDRESS: (301, "", b"", "/private"), "https://harborlane.example/private": (200, HTML, HARBOR)})
        with self.assertRaises(ms.PageError) as caught:
            self.fetch(get, cache=False)
        self.assertEqual((caught.exception.code, get.urls), ("refused", [ROBOTS, ADDRESS]))  # /private is never requested

    def test_a_redirect_to_an_allowed_page_is_read_and_each_request_waits_its_gap(self):
        get, page = self.go({ROBOTS: (404, "", b""), ADDRESS: (302, "", b"", "/our-story"), "https://harborlane.example/our-story": (200, HTML, HARBOR)})
        self.assertEqual(page["url"], ADDRESS)
        self.assertEqual(get.urls, [ROBOTS, ADDRESS, "https://harborlane.example/our-story"])
        self.assertEqual(self.clock.slept, [ms.MIN_GAP] * 2)  # robots, the first answer and the hop are each a request

    def test_a_hop_between_the_bare_name_and_www_reads_the_robots_file_of_the_new_host(self):
        get, _page = self.go({ROBOTS: (404, "", b""), ADDRESS: (301, "", b"", self.WWW), self.WWW_ROBOTS: (404, "", b""), self.WWW: (200, HTML, HARBOR)})
        self.assertEqual(get.urls, [ROBOTS, ADDRESS, self.WWW_ROBOTS, self.WWW])
        refused = Recorded({ROBOTS: (404, "", b""), ADDRESS: (301, "", b"", self.WWW), self.WWW_ROBOTS: (200, "text/plain", b"User-agent: *\nDisallow: /\n")})
        with self.assertRaises(ms.PageError) as caught:
            self.fetch(refused, cache=False)
        self.assertEqual((caught.exception.code, refused.urls), ("refused", [ROBOTS, ADDRESS, self.WWW_ROBOTS]))

    def test_a_robots_file_may_redirect_inside_the_site_but_not_off_it(self):
        get, _page = self.go({ROBOTS: (301, "", b"", self.WWW_ROBOTS), self.WWW_ROBOTS: (404, "", b""), ADDRESS: (200, HTML, HARBOR)})
        self.assertEqual(get.urls, [ROBOTS, self.WWW_ROBOTS, ADDRESS])
        away = Recorded({ROBOTS: (302, "", b"", "https://elsewhere.example/robots.txt")})
        with self.assertRaises(ms.PageError):
            self.fetch(away, cache=False)
        self.assertEqual(away.urls, [ROBOTS])

    def test_redirects_have_a_cap_and_a_redirect_without_a_place_is_unreachable(self):
        loop = {ROBOTS: (404, "", b"")} | {f"https://harborlane.example/{n}": (302, "", b"", f"/{n + 1}") for n in range(10)} | {ADDRESS: (302, "", b"", "/1")}
        get = Recorded(loop)
        with self.assertRaises(ms.PageError) as caught:
            self.fetch(get, cache=False)
        self.assertEqual(caught.exception.code, "unreachable")
        self.assertEqual(len(get.urls) - 1, ms.MAX_REDIRECTS + 1)  # robots.txt, the page and MAX_REDIRECTS hops, then it stops
        with self.assertRaises(ms.PageError):
            self.fetch(Recorded({ROBOTS: (404, "", b""), ADDRESS: (302, "", b"")}), cache=False)

    def test_a_hop_to_a_host_that_is_not_public_is_never_opened(self):
        """The real read: the first host is public, the www name it redirects to resolves inside, so only the first is asked."""
        answers = {"harborlane.example": "93.184.216.34", "www.harborlane.example": "10.0.0.5"}
        opened = []

        def real(url, headers, timeout):
            opened.append(url)
            return (301, "", b"", self.WWW) if url == ADDRESS else (404, "", b"", "")

        with mock.patch.object(ms, "_http_get", real), mock.patch.object(
                ms.socket, "getaddrinfo", side_effect=lambda host, port, **kw: [(2, 1, 6, "", (answers[host], 443))]):
            with self.assertRaises(ms.PageError) as caught:
                ms.fetch(ADDRESS, sleep=self.clock.sleep, clock=self.clock, cache=False)
        self.assertEqual((caught.exception.code, opened), ("unreachable", [ROBOTS, ADDRESS]))

    def test_the_real_read_follows_no_redirect_itself_and_uses_no_proxy_or_cookies(self):
        class Opener:
            def open(self, request, timeout=None):
                raise urllib.error.HTTPError(request.full_url, 302, "Found", {"Location": "https://harborlane.example/next"}, None)

        seen = []
        with mock.patch.object(urllib.request, "build_opener", side_effect=lambda *handlers: seen.extend(handlers) or Opener()):
            self.assertEqual(REAL_GET(ADDRESS, {}, 5), (302, "", b"", "https://harborlane.example/next"))
        self.assertEqual([type(h) for h in seen], [urllib.request.ProxyHandler, ms._PinnedHandler, ms._NoRedirect])  # no cookie or auth handler
        self.assertEqual(seen[0].proxies, {})
        request = urllib.request.Request(ADDRESS)
        self.assertIsNone(ms._NoRedirect().redirect_request(request, io.BytesIO(b""), 302, "Found", {}, "https://harborlane.example/next"))

    def test_the_real_connection_goes_only_to_an_address_it_just_checked(self):
        for resolved, ok in (("93.184.216.34", True), ("10.0.0.5", False), ("127.0.0.1", False)):
            with self.subTest(resolved=resolved):
                conn = ms._PinnedHTTPS("harborlane.example", timeout=5)
                with mock.patch.object(ms.socket, "getaddrinfo", return_value=[(2, 1, 6, "", (resolved, 443))]), \
                        mock.patch.object(ms.socket, "create_connection") as connect, \
                        mock.patch.object(ms.ssl, "create_default_context") as tls:
                    if ok:
                        conn.connect()
                        connect.assert_called_once_with((resolved, 443), 5)  # the checked address, not the name again
                        tls.return_value.wrap_socket.assert_called_once_with(connect.return_value, server_hostname="harborlane.example")
                    else:
                        with self.assertRaises(OSError):
                            conn.connect()
                        connect.assert_not_called()


class SizeCap(SiteTestCase):
    def test_the_real_read_never_takes_more_than_the_cap(self):
        asked = []

        class Response(io.BytesIO):
            status, headers = 200, {"Content-Type": HTML}

            def read(self, size=-1):
                asked.append(size)
                return super().read(size)

            def __enter__(self):
                return self

        class Opener:
            def open(self, request, timeout=None):
                return Response(b"<p>" + b"x" * (3 * ms.MAX_BYTES))

        with mock.patch.object(urllib.request, "build_opener", return_value=Opener()):
            status, kind, body, where = REAL_GET(ADDRESS, {}, 5)
        self.assertEqual((status, kind, where, asked), (200, HTML, "", [ms.MAX_BYTES]))
        self.assertEqual(len(body), ms.MAX_BYTES)

    def test_text_after_the_cap_is_never_read(self):
        late = b"<p>Harbor Lane keeps a tiny stall at the late end of this page.</p>"
        filler = b"<p>" + b"padding " * 20 + b"</p>"
        body = b"<html><body><p>Harbor Lane makes small-batch fruit jam in Morro Bay.</p>" + filler * (ms.MAX_BYTES // len(filler) + 2) + late
        self.assertGreater(len(body), ms.MAX_BYTES)
        page = self.fetch(Recorded({ROBOTS: (404, "", b""), ADDRESS: (200, HTML, body)}))
        self.assertIn("Harbor Lane makes small-batch fruit jam in Morro Bay.", page["blocks"])
        self.assertFalse([b for b in page["blocks"] if "late end" in b])

    def test_a_page_that_will_not_parse_is_a_page_with_nothing_usable(self):
        self.assertEqual(ms.extract("<<<<>>>>"), [])
        with self.assertRaises(ms.PageError):
            self.fetch(Recorded({ADDRESS: (200, HTML, b"<<<< >>>>")}), cache=False)


class RateLimit(SiteTestCase):
    def test_two_requests_to_one_host_are_at_least_the_gap_apart(self):
        get = self.page()
        self.fetch(get)  # robots.txt, then the page: the page waits the full gap after robots.txt
        self.assertEqual(self.clock.slept, [ms.MIN_GAP])
        self.fetch(get, cache=False)  # robots.txt again straight after the page: waits; the page after it waits too
        self.assertEqual(self.clock.slept, [ms.MIN_GAP] * 3)
        self.assertEqual(get.urls, [ROBOTS, ADDRESS, ROBOTS, ADDRESS])

    def test_a_request_after_the_gap_does_not_wait(self):
        get = self.page()
        self.fetch(get)
        self.clock.now += ms.MIN_GAP + 0.5
        self.clock.slept.clear()
        ms._wait("harborlane.example", self.clock.sleep, self.clock)
        self.assertEqual(self.clock.slept, [])

    def test_a_partial_gap_waits_only_what_is_left(self):
        ms._wait("harborlane.example", self.clock.sleep, self.clock)
        self.clock.now += 0.5
        ms._wait("harborlane.example", self.clock.sleep, self.clock)
        self.assertEqual(self.clock.slept, [ms.MIN_GAP - 0.5])

    def test_each_host_has_its_own_gap(self):
        other = "https://another.example/about"
        get = Recorded({ROBOTS: (404, "", b""), ADDRESS: (200, HTML, HARBOR), "https://another.example/robots.txt": (404, "", b""),
                        other: (200, HTML, HARBOR)})
        self.fetch(get)
        slept = list(self.clock.slept)
        self.fetch(get, other)
        self.assertEqual(self.clock.slept[len(slept):], [ms.MIN_GAP])  # only its own robots.txt -> page gap, none for the first host

    def test_the_same_address_inside_one_request_is_read_once(self):
        get = self.page()
        first = self.fetch(get)
        self.assertIs(self.fetch(get), first)
        self.assertEqual(get.urls, [ROBOTS, ADDRESS])
        self.clock.now += ms.CACHE_SECONDS + 1  # a stale copy is read again
        self.fetch(get)
        self.assertEqual(get.urls, [ROBOTS, ADDRESS, ROBOTS, ADDRESS])

    def test_reader_is_the_context_function_for_one_address(self):
        get = self.page()
        with mock.patch.object(ms, "_wait") as wait:  # the gap itself is tested above; the default sleep is bound at import
            read = ms.reader(get=get, today=DAY)
            self.assertEqual(read(ADDRESS)["retrieved"], "2026-11-09")
        self.assertEqual(wait.call_count, 2)  # robots.txt and the page


class TheStory(unittest.TestCase):
    def blocks(self, markup):
        return {"url": ADDRESS, "retrieved": "2026-11-09", "blocks": ms.extract(markup.decode() if isinstance(markup, bytes) else markup)}

    def test_the_harbor_lane_page_gives_two_short_claim_free_house_sentences(self):
        page = self.blocks(HARBOR)
        story = ms.draft_story("Harbor Lane", page)
        self.assertEqual(story["sentences"], [
            "Harbor Lane makes small-batch fruit jam and relish in a shared kitchen in Morro Bay.",
            "Harbor Lane cooks every batch in small pots, a few jars at a time."])
        self.assertEqual(story["from"], ["Harbor Lane makes small-batch fruit jam and relish in a shared kitchen in Morro Bay.",
                                         "We cook every batch in small pots, a few jars at a time."])
        text = " ".join(story["sentences"])
        self.assertLessEqual(len(story["sentences"]), ms.MAX_SENTENCES)
        self.assertLessEqual(len(text), ms.MAX_CHARS)
        for left_out in ("2019", "organic", "best", "award", "555", "@", "ship", "Every jar", "local growers", "!", "?"):
            self.assertNotIn(left_out, text)
        self.assertEqual(live_policy._protected(text)[1], set())  # the live gate finds no claim in it
        for source in story["from"]:  # every sentence is traceable: it is on the page
            self.assertIn(source, " ".join(page["blocks"]))

    def test_a_page_with_only_claims_and_first_person_talk_gives_no_story(self):
        page = self.blocks(CLAIMS_ONLY)
        self.assertTrue(page["blocks"])
        self.assertIsNone(ms.draft_story("Fern Hollow", page))

    def test_a_page_with_no_blocks_or_the_wrong_name_gives_no_story(self):
        self.assertIsNone(ms.draft_story("Harbor Lane", {"blocks": []}))
        self.assertIsNone(ms.draft_story("Harbor Lane", {}))
        named = {"blocks": ["Harbor Lane makes small-batch fruit jam in a shared kitchen.", "Harbor Lane fills each jar by hand."]}
        self.assertIsNone(ms.draft_story("Someone Else", named))  # a sentence about another maker is not used

    def test_words_mike_already_said_are_not_said_twice(self):
        page = self.blocks(HARBOR)
        said = "Harbor Lane makes small-batch fruit jam and relish in a shared kitchen in Morro Bay."
        story = ms.draft_story("Harbor Lane", page, said=said)
        self.assertEqual(story["sentences"], ["Harbor Lane cooks every batch in small pots, a few jars at a time."])

    def test_the_story_is_cut_at_two_sentences(self):
        page = {"blocks": ["Harbor Lane makes jam in a shared kitchen in Morro Bay.", "Harbor Lane sells relish at the Saturday market.",
                           "Harbor Lane fills each jar by hand in small batches."]}
        story = ms.draft_story("Harbor Lane", page)
        self.assertEqual(len(story["sentences"]), ms.MAX_SENTENCES)
        self.assertEqual(story["sentences"], page["blocks"][:2])

    def test_a_sentence_is_used_only_when_it_passes_every_rule(self):
        name = "Harbor Lane"
        good = "Harbor Lane makes small-batch fruit jam in a shared kitchen."
        self.assertEqual(ms.usable(good, name), good)
        self.assertEqual(ms.usable("We make small-batch fruit jam in a shared kitchen.", name), "They make small-batch fruit jam in a shared kitchen.")
        self.assertEqual(ms.usable("Our recipes come from the family cookbook.", name), "Their recipes come from the family cookbook.")
        self.assertEqual(ms.usable("Harbor Lane\u2019s jars are filled by hand every week.", name), "Harbor Lane's jars are filled by hand every week.")
        rules = {
            "too short": "Harbor Lane makes jam.",
            "too long": "Harbor Lane makes jam and relish and pickles " + "and more " * 25 + "today.",
            "no full stop": "Harbor Lane makes small-batch fruit jam in a shared kitchen",
            "exclamation": "Harbor Lane makes small-batch fruit jam in a shared kitchen!",
            "question": "Does Harbor Lane make small-batch fruit jam in a shared kitchen?",
            "quotation": 'Harbor Lane makes "small-batch" fruit jam in a shared kitchen.',
            "a link": "Harbor Lane is described at https://harborlane.example in a shared kitchen.",
            "an address": "Harbor Lane writes to hello@harborlane.example about jam in a shared kitchen.",
            "a number": "Harbor Lane fills 300 jars by hand in a shared kitchen each week.",
            "a price": "Harbor Lane sells small-batch fruit jam for $9 in a shared kitchen.",
            "hype": "Harbor Lane makes the best small-batch fruit jam in a shared kitchen.",
            "origin": "Harbor Lane makes jam with organic fruit in a shared kitchen.",
            "health": "Harbor Lane makes jam that is good for your heart in a shared kitchen.",
            "award": "Harbor Lane makes award-winning jam in a shared kitchen in Morro Bay.",
            "first person inside": "Harbor Lane makes jam because we love small-batch fruit and relish.",
            "you": "Harbor Lane makes jam that you can spread on small-batch bread by hand.",
            "not about the maker": "Small-batch fruit jam is cooked in a shared kitchen in Morro Bay.",
            "we plus the name": "We started Harbor Lane with one pot and a stack of family recipes.",
            "contact": "Harbor Lane takes orders on (805) 555-0100 for jam in a shared kitchen.",
        }
        for label, sentence in rules.items():
            with self.subTest(rule=label):
                self.assertIsNone(ms.usable(sentence, name), sentence)

    def test_the_provenance_record_keeps_the_address_the_day_and_the_source_sentences(self):
        page = {**self.blocks(HARBOR), "url": ADDRESS, "retrieved": "2026-11-09"}
        story = ms.draft_story("Harbor Lane", page)
        record = ms.record(page, story)
        self.assertEqual(record, {"source": ADDRESS, "retrieved": "2026-11-09", "from": story["from"],
                                  "story": " ".join(story["sentences"])})
        self.assertNotIn("blocks", record)  # the page text itself is not kept
        record["from"].append("x")
        self.assertEqual(len(story["from"]), 2)


if __name__ == "__main__":
    unittest.main()

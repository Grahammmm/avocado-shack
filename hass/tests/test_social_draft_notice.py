"""AV1104-07 tests: social_draft.build_notice and --notice draft a caption for the home notice the saved content shows today.
Run: python3 -B -m unittest hass.tests.test_social_draft_notice -v

Synthetic content only. Each test names the contract it protects and the believable bug that fails it. Nothing is posted.
"""
import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hass import social_draft
from hass.content_model import Content

TAGS = "\n\n#AvocadoShack #MorroBay"
STORE = {"name": "Avocado Shack", "streetAddress": "2190 Main Street", "town": "Morro Bay"}
TEXT = "We are closed for Thanksgiving. Happy holidays!"
NOON = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)  # 12:00 PST, Tuesday 2026-11-24


def content(notice: object = "absent", **store):
    s = {**STORE, **store}
    if notice != "absent": s["notice"] = notice
    return Content(products=[], makers={}, community={}, store=s)


def refused(reason):
    return {"draft": False, "reason": reason}


def caption(window, text=TEXT):
    return f"{text}\n{window}\nAvocado Shack\n2190 Main Street, Morro Bay.{TAGS}"


LEGACY = {"text": TEXT, "until": "2026-11-26"}
RANGE = {"text": TEXT, "from": "2026-11-23", "until": "2026-11-26"}


class BuildNoticeTests(unittest.TestCase):
    def test_caption_legacy_and_explicit_range(self):
        """The caption is the owner's words, the days in words, the store lines and the two fixed tags; a first day adds 'from'.
        Bug caught: a reworded notice, ISO dates, a missing store line, or a first day never named."""
        c = content(dict(LEGACY))
        before = copy.deepcopy(c.store)
        self.assertEqual(social_draft.build_notice(c, NOON), {"draft": True, "caption": caption("through Thursday, November 26")})
        self.assertEqual(c.store, before)  # read-only
        self.assertEqual(social_draft.build_notice(content(dict(RANGE)), NOON),
                         {"draft": True, "caption": caption("from Monday, November 23 through Thursday, November 26")})
        odd = "Closed # 1 day?! (really) - see you soon"  # owner punctuation is kept exactly
        self.assertEqual(social_draft.build_notice(content({"text": odd, "until": "2026-11-26"}), NOON)["caption"].splitlines()[0], odd)

    def test_active_window_is_inclusive_and_pacific(self):
        """Both boundary days show; before the first day, after the last day or with no notice is 'no notice on the website'.
        Bug caught: UTC date used instead of Pacific, an off-by-one at either end, or a scheduled notice promoted early."""
        none = refused("no notice on the website")
        at = lambda day, hh=12, mm=0: datetime.fromisoformat(f"{day}T{hh:02}:{mm:02}:00-08:00")  # noqa: E731
        self.assertEqual(social_draft.build_notice(content(), NOON), none)  # no notice saved
        self.assertEqual(social_draft.build_notice(content(dict(RANGE)), at("2026-11-22", 23, 59)), none)  # not yet
        self.assertTrue(social_draft.build_notice(content(dict(RANGE)), at("2026-11-23", 0, 0))["draft"])  # first day
        self.assertTrue(social_draft.build_notice(content(dict(RANGE)), at("2026-11-26", 23, 59))["draft"])  # last day
        self.assertEqual(social_draft.build_notice(content(dict(RANGE)), at("2026-11-27", 0, 0)), none)  # expired
        self.assertTrue(social_draft.build_notice(content(dict(LEGACY)), at("2026-10-01"))["draft"])  # legacy: shown until its last day
        same = {"text": TEXT, "from": "2026-11-26", "until": "2026-11-26"}
        self.assertEqual(social_draft.build_notice(content(same), at("2026-11-26"))["caption"].splitlines()[1],
                         "from Thursday, November 26 through Thursday, November 26")
        # 2026-11-27 03:00 UTC is still the 26th in Pacific: the last day; 08:00 UTC is the 27th
        self.assertTrue(social_draft.build_notice(content(dict(LEGACY)), datetime(2026, 11, 27, 3, 0, tzinfo=timezone.utc))["draft"])
        self.assertEqual(social_draft.build_notice(content(dict(LEGACY)), datetime(2026, 11, 27, 8, 0, tzinfo=timezone.utc)), none)
        # DST: PDT (UTC-7) midnight is 07:00 UTC
        summer = {"text": TEXT, "until": "2026-07-04"}
        self.assertTrue(social_draft.build_notice(content(summer), datetime(2026, 7, 5, 6, 59, tzinfo=timezone.utc))["draft"])
        self.assertEqual(social_draft.build_notice(content(summer), datetime(2026, 7, 5, 7, 0, tzinfo=timezone.utc)), none)

    def test_unreadable_shapes_and_refusals(self):
        """Malformed content is 'cannot read content' (never a traceback or a guessed caption); bad text or store lines name what is incomplete.
        Bug caught: a crash on a null notice or a bad date, a blank store street filled with a hard-coded one."""
        bad = refused("cannot read content")
        for notice in (None, "text", [], {}, {"text": TEXT}, {"text": TEXT, "until": "2026-11-31"}, {"text": TEXT, "until": "26-11-2026"},
                       {"text": 5, "until": "2026-11-26"}, {"text": TEXT, "from": "2026-11-27", "until": "2026-11-26"},
                       {"text": TEXT, "from": "bad", "until": "2026-11-26"}, {"text": TEXT, "until": "2026-11-26", "extra": 1}):
            with self.subTest(notice=notice):
                self.assertEqual(social_draft.build_notice(content(notice), NOON), bad)
        self.assertEqual(social_draft.build_notice(Content(products=[], makers={}, community={}, store=[]), NOON), bad)  # type: ignore[arg-type]
        for text in ("", "  ", "two\nlines", "bell\x07", "a\u2028b"):
            with self.subTest(text=text):
                self.assertEqual(social_draft.build_notice(content({"text": text, "until": "2026-11-26"}), NOON), refused("notice record incomplete"))
        for field in ("name", "streetAddress", "town"):
            for value in (None, 7, "", " ", "x\ny"):
                with self.subTest(field=field, value=value):
                    c = content(dict(LEGACY), **{field: value})
                    self.assertEqual(social_draft.build_notice(c, NOON), refused("store record incomplete"))
        gone = content(dict(LEGACY))
        del gone.store["town"]
        self.assertEqual(social_draft.build_notice(gone, NOON), refused("store record incomplete"))

    def test_tags_accounts_and_length_in_every_field(self):
        """A # or @ (ASCII, full-width, small-form) followed by a word character is refused in the notice or any store line, never rewritten;
        a caption over MAX_CAPTION is refused, one at the limit is kept. Bug caught: a hashtag or account leaking into Michael's caption."""
        tagged = refused("free text has a hashtag or account name")
        for mark in ("#", "@", "\uff03", "\uff20", "\ufe5f", "\ufe6b"):
            for where in ("notice", "name", "streetAddress", "town"):
                with self.subTest(mark=mark, where=where):
                    value = f"Open {mark}sale"
                    c = content({"text": value, "until": "2026-11-26"}) if where == "notice" else content(dict(LEGACY), **{where: value})
                    self.assertEqual(social_draft.build_notice(c, NOON), tagged)
        self.assertTrue(social_draft.build_notice(content({"text": "Open # now @ noon", "until": "2026-11-26"}), NOON)["draft"])  # isolated marks
        window = "through Thursday, November 26"
        room = social_draft.MAX_CAPTION - len(caption(window, text=""))
        exact = social_draft.build_notice(content({"text": "x" * room, "until": "2026-11-26"}), NOON)
        self.assertEqual(len(exact["caption"]), social_draft.MAX_CAPTION)
        self.assertEqual(social_draft.build_notice(content({"text": "x" * (room + 1), "until": "2026-11-26"}), NOON), refused("caption too long"))


class NoticeCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        for name, doc in (("products", {"products": []}), ("makers", {"makers": {}}), ("community", {}), ("store", {**STORE, "notice": LEGACY})):
            (self.dir / f"{name}.json").write_text(json.dumps({"schemaVersion": 1, **doc}), "utf-8")

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try: code = social_draft.main(list(argv), self.dir, self.dir)
            except SystemExit as exc: code = exc.code
        return code, out.getvalue()

    def test_cli_exclusive_json_and_refusals(self):
        """--notice is one more exclusive mode: exit 0 with the caption JSON, 1 with a refusal, 2 for a conflict or a naive --now; files unchanged.
        Bug caught: --notice accepted beside a product, a naive --now guessed in the host zone, or content rewritten."""
        before = {p.name: p.read_bytes() for p in self.dir.iterdir()}
        code, out = self.run_cli("--notice", "--now", "2026-11-24T12:00:00-08:00")
        self.assertEqual((code, json.loads(out)), (0, {"draft": True, "caption": caption("through Thursday, November 26")}))
        code, out = self.run_cli("--notice", "--now", "2026-11-24T20:00:00Z")
        self.assertEqual(code, 0)
        code, out = self.run_cli("--notice", "--now", "2026-11-27T12:00:00-08:00")
        self.assertEqual((code, json.loads(out)), (1, refused("no notice on the website")))
        for argv in ((), ("--notice", "p1"), ("p1", "--notice"), ("--notice", "--hike", "h1"), ("--maker", "k", "--notice"),
                     ("--notice", "--recap", "h1"), ("--notice", "--now", "2026-11-24T12:00:00")):
            self.assertEqual(self.run_cli(*argv), (2, ""), argv)
        self.assertEqual({p.name: p.read_bytes() for p in self.dir.iterdir()}, before)
        (self.dir / "store.json").write_text("{bad", "utf-8")
        code, out = self.run_cli("--notice", "--now", "2026-11-24T12:00:00-08:00")
        self.assertEqual((code, json.loads(out)), (1, refused("cannot read content")))


if __name__ == "__main__":
    unittest.main()

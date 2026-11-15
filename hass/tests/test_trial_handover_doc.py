"""AV0007-09 (H18/H25): docs/hass/TRIAL.md covers the owner tasks Hass can do, and HANDOVER.md links it and lists the
public-site decisions without recording any. Stdlib, offline: no live model, phone or request is used as an oracle.
Run: python3 -m unittest hass.tests.test_trial_handover_doc -v
"""
import re
import unittest
from pathlib import Path

from hass.content_model import MAX_NOTICE, MAX_NOTICE_DAYS
from hass.ops import load_registry
from hass.ops.routes import ROUTE_EDITABLE
from hass.tests.test_commands_doc import verb
from hass.tests.test_route_add import NEW

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "hass"
TRIAL, HANDOVER = DOCS / "TRIAL.md", DOCS / "HANDOVER.md"
NEW_TASKS = {22: "notice", 23: "notice", 24: "photo", 25: "route idea", 26: "route idea", 27: "route idea"}
OLD_DECISIONS = ("H07", "H19", "H21", "H22", "H23")
PUBLIC_ROWS = {"H25-domain": 3, "H25-forms": 4, "H25-logo": 1}
# (file the link points to, line) -> text that line must contain, so a moved anchor fails here.
ANCHORS = {("docs/hass/FEATURES.md", 53): "| H25 |", ("HERMES_HANDOFF.txt", 47): "logo",
           ("HERMES_HANDOFF.txt", 50): "DNS change", ("HERMES_HANDOFF.txt", 129): "PUBLIC TRIAL SUNSET",
           ("storefront-mockup/README.md", 47): "no email delivery", ("storefront-mockup/README.md", 49): "unsubscribe",
           ("docs/hass/SIGNUP-OPTIONS.md", 1): "# Signup options"}


def task_rows(doc: str) -> dict:
    """{task number: (task, send cell, success cell)} for each `| N | ...` table row."""
    out = {}
    for line in doc.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if line.startswith("| ") and len(cells) == 4 and cells[0].isdigit():
            assert int(cells[0]) not in out, f"task {cells[0]} appears twice"
            out[int(cells[0])] = tuple(cells[1:])
    return out


def record_ids(doc: str) -> list:
    block = doc.split("```text\n", 1)[1].split("```", 1)[0]
    return [int(m[1]) for ln in block.splitlines() if (m := re.match(r"(\d+)\. \S", ln))]


def sent_messages(send_cell: str) -> list:
    return re.findall(r"`([^`]+)`", send_cell)


def missing_phrases(doc: str, phrases) -> list:
    return [p for p in phrases if p.lower() not in doc.lower()]


def handover_rows(doc: str) -> dict:
    out = {}
    for line in doc.split("## Open decisions", 1)[1].splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split(" | ")]
        if line.startswith("| ") and len(cells) == 4 and cells[0] not in ("Id", "---"):
            out[cells[0]] = cells
    return out


def local_links(text: str) -> list:
    """(target path relative to the repo root, line or None) for every relative markdown link in text."""
    out = []
    for path, anchor in re.findall(r"\]\(([^)#\s]+)(?:#L(\d+))?\)", text):
        if not path.startswith(("http", "mailto")):
            out.append(((DOCS / path).resolve().relative_to(ROOT).as_posix(), int(anchor) if anchor else None))
    return out


def h21_problems(handover: str) -> list:
    """Why the H21 row does not link the retention options page while staying an open Owner / G decision."""
    rows = handover_rows(handover)
    if "H21" not in rows:
        return ["no H21 row"]
    _, text, whose, source = rows["H21"]
    problems = []
    if whose.split(" (")[0] != "Owner / G":
        problems.append("H21 is not Owner / G")
    if "retention" not in text.lower():
        problems.append("H21 no longer names retention")
    for link in ("[FEATURES.md line 49](FEATURES.md#L49)", "[Retention options](RETENTION-OPTIONS.md)"):
        if link not in source:
            problems.append(f"H21 source lacks {link}")
    problems += [f"{key} links the retention options page" for key, cells in rows.items()
                 if key != "H21" and "RETENTION-OPTIONS" in cells[3]]
    return problems


def h25_forms_problems(handover: str) -> list:
    """Why the H25-forms row does not link the signup options page while staying an open Owner / G decision."""
    rows = handover_rows(handover)
    if "H25-forms" not in rows:
        return ["no H25-forms row"]
    _, text, whose, source = rows["H25-forms"]
    problems = []
    if whose != "Owner / G":
        problems.append("H25-forms is not Owner / G")
    if "signup forms send to" not in text:
        problems.append("H25-forms no longer asks what the forms send to")
    for link in ("[Signup options](SIGNUP-OPTIONS.md#L1)", "[storefront-mockup/README.md line 47](../../storefront-mockup/README.md#L47)",
                 "[line 49](../../storefront-mockup/README.md#L49)", "[FEATURES.md line 53](FEATURES.md#L53)"):
        if link not in source:
            problems.append(f"H25-forms source lacks {link}")
    problems += [f"{key} links the signup options page" for key, cells in rows.items()
                 if key != "H25-forms" and "SIGNUP-OPTIONS" in cells[3]]
    return problems


class TrialHandoverDocTests(unittest.TestCase):
    def setUp(self):
        self.trial, self.handover = TRIAL.read_text("utf-8"), HANDOVER.read_text("utf-8")
        self.rows = task_rows(self.trial)

    def test_proposal_and_real_phone_caveats_preserved(self):
        self.assertTrue(self.trial.startswith("# Owner trial (H18) - proposal\n"))
        self.assertIn("**Proposal, needs Michael and G to agree. Nothing here has been tried on Michael's phone.**",
                      self.trial)
        self.assertIn("this page does not make it", self.trial)
        self.assertIn("7 days of normal use or", self.trial)
        labels = r"(Date|Phone/app|Message sent|Reply received \(yes/no\)|Result|Notes):"
        for line in self.trial.split("```text\n", 1)[1].split("```", 1)[0].splitlines():  # every record still blank
            filled = re.sub(labels, "", re.sub(r"^(\d+\. .*?(?=\s+Date:))?", "", line))
            self.assertEqual(filled.strip(), "", line)
        self.assertNotRegex(self.trial, r"(?i)Result:\s*(worked|did not|unclear)\b")

    def test_new_tasks_and_blank_records_match(self):
        self.assertEqual(sorted(self.rows), list(range(1, 28)))
        ids = record_ids(self.trial)
        self.assertEqual(ids, list(range(1, 28)))
        for number, word in NEW_TASKS.items():
            self.assertIn(word, " ".join(self.rows[number][:2]).lower(), f"task {number}")
        self.assertEqual(self.rows[11][0], "Edit a route idea")
        self.assertIn("Change the Cass Hill route difficulty", self.rows[11][1])
        self.assertIn("Edit a route idea", self.trial.split("```text\n", 1)[1])
        self.assertEqual(self.rows[8][0], "Change the intro, headline or story")  # not a notice or photo row
        for name in ("Set a home-page notice", "Clear the home-page notice", "Set a home-page photo",
                     "Add a route idea", "Hide a route idea", "Bring back a route idea"):
            self.assertIn(name, [r[0] for r in self.rows.values()])

    def test_examples_are_change_requests_and_approval_is_explicit(self):
        self.assertIsNotNone(verb("yes a1b2"))  # the checker really recognises a command
        for number in NEW_TASKS:
            task, send, success = self.rows[number]
            messages = sent_messages(send)
            self.assertTrue(messages, f"task {number} quotes no message")
            for message in messages:
                self.assertIsNone(verb(message), f"task {number} message parses as a command: {message}")
            if number != 24:
                self.assertEqual(len(messages), 1, f"task {number}")
            self.assertIn("`yes", success, f"task {number}")
        self.assertIn("Send one JPEG or PNG photo", self.rows[24][1])
        self.assertIn("Use this photo on the home page: crates of ripe avocados by the front door", self.rows[24][1])
        self.assertIn("Put a notice on the home page saying Closed for a team meeting, through <last day>", self.rows[22][1])
        self.assertIn("Hass may ask", self.rows[24][2])  # missing details are asked for, not guessed
        self.assertIn("Hass may ask", self.rows[25][2])
        self.assertIn("Nothing applies until `yes <code>`", self.trial)
        self.assertIn("each\ntask needs its own approval", self.trial)
        self.assertIn("does not promise the\nexact words Hass will use", self.trial)
        self.assertIn("(COMMANDS.md, `yes <code>`)", self.trial)

    def test_documented_ops_exist_with_current_arguments(self):
        registry = load_registry()
        expected = {"store.set_notice": {"text", "from", "until"},  # AV2152-08: optional first day "store.clear_notice": set(),
                    "store.set_home_image": {"photo", "imageAlt"}, "route.hide": {"id"}, "route.restore": {"id"},
                    "route.add": set(ROUTE_EDITABLE) | {"sourceUrl", "sourceName"}}
        for name, args in expected.items():
            with self.subTest(op=name):
                self.assertIn(name, registry)
                self.assertEqual(set(registry[name].args), args)
        send = self.rows[25][1].casefold()
        for field in ROUTE_EDITABLE:  # the doc example supplies every text field of the synthetic fixture
            self.assertIn(NEW[field].casefold().rstrip("."), send, field)
        self.assertIn(NEW["sourceUrl"], self.rows[25][1])
        self.assertIn(NEW["sourceName"], self.rows[25][1])
        self.assertIn(f"{MAX_NOTICE} characters", self.trial)
        self.assertIn(f"{MAX_NOTICE_DAYS} days ahead", self.trial)
        source = "".join((ROOT / "hass" / "ops" / f).read_text("utf-8") for f in ("home.py", "routes.py"))
        for quoted in ("there is no notice", "uses this route; change that hike first"):
            self.assertIn(quoted, source)  # the op still refuses with these words
            self.assertIn(quoted, self.trial)  # and the doc quotes them
        for link in ("../../hass/ops/home.py", "../../hass/ops/routes.py", "COMMANDS.md"):
            self.assertIn(f"]({link})", self.trial)
            self.assertTrue((DOCS / link).resolve().is_file(), link)

    def test_handover_trial_link_and_three_open_public_rows(self):
        step4 = next(ln for ln in self.handover.splitlines() if ln.startswith("4. "))
        self.assertIn("[TRIAL.md](TRIAL.md)", step4)
        self.assertTrue((DOCS / "TRIAL.md").is_file())
        self.assertIn("proposal", step4)
        self.assertIn("Michael and G", step4)
        self.assertIn("FEATURES.md#L41", step4)
        self.assertNotIn("not in the repo yet", self.handover)
        self.assertNotIn("once one exists", self.handover)
        self.assertIn("separate authorization", next(ln for ln in self.handover.splitlines() if ln.startswith("5. ")))
        rows = handover_rows(self.handover)
        self.assertEqual(list(rows), list(OLD_DECISIONS) + list(PUBLIC_ROWS))
        for decision, links in PUBLIC_ROWS.items():
            _, text, whose, source = rows[decision]
            self.assertEqual(whose.split(" (")[0], "Owner / G")
            targets = local_links(source)
            self.assertGreaterEqual(len(targets), links, decision)
            for path, line in targets:
                lines = (ROOT / path).read_text("utf-8").splitlines()
                self.assertTrue(line and 1 <= line <= len(lines), f"{decision}: {path}#L{line}")
                if (path, line) in ANCHORS:
                    self.assertIn(ANCHORS[(path, line)].lower(), lines[line - 1].lower(), f"{decision}: {path}#L{line}")
        cited = {key for decision in PUBLIC_ROWS for key in local_links(rows[decision][3])}
        self.assertEqual(cited, set(ANCHORS))  # every cited source line is one the test checked
        for line in self.handover.splitlines():  # no link anywhere in the page points at a missing file or line
            for path, anchor in local_links(line):
                self.assertTrue((ROOT / path).is_file(), path)
                if anchor:
                    self.assertLessEqual(anchor, len((ROOT / path).read_text("utf-8").splitlines()), f"{path}#L{anchor}")

    def test_h21_links_retention_options_without_closing_decision(self):
        self.assertEqual(h21_problems(self.handover), [])
        options = (DOCS / "RETENTION-OPTIONS.md").read_text("utf-8")
        self.assertTrue(options.startswith("# How long to keep private data (H21)"))
        self.assertIn("This page records no decision", options)
        feature_line = (ROOT / "docs/hass/FEATURES.md").read_text("utf-8").splitlines()[48]
        self.assertTrue(feature_line.startswith("| H21 |") and "Needs G: owner retention periods" in feature_line)
        rows = handover_rows(self.handover)
        self.assertEqual(rows["H21"][1], "Message and media retention periods")
        self.assertEqual(list(rows), list(OLD_DECISIONS) + list(PUBLIC_ROWS))  # no new row, same order
        self.assertIn(("docs/hass/RETENTION-OPTIONS.md", None), local_links(rows["H21"][3]))
        link = "[Retention options](RETENTION-OPTIONS.md)"
        self.assertEqual(self.handover.count(link), 1)
        moved = self.handover.replace(f", {link}", "").replace("| H22 | Usage and spending limit; support, recovery"
                                                              " and account record kept privately | Owner / G | ",
                                                              f"| H22 | Usage and spending limit; support, recovery and account record kept privately"
                                                              f" | Owner / G | {link}, ")
        self.assertEqual(h21_problems(moved), [f"H21 source lacks {link}", "H22 links the retention options page"])
        wrong_anchor = self.handover.replace("FEATURES.md#L49)", "FEATURES.md#L50)")
        self.assertIn("H21 source lacks [FEATURES.md line 49](FEATURES.md#L49)", h21_problems(wrong_anchor))
        self.assertEqual(h21_problems(self.handover.replace(link, "")),
                         [f"H21 source lacks {link}"])
        self.assertEqual(h21_problems(self.handover.replace("| H21 |", "| H21x |")), ["no H21 row"])

    def test_h25_forms_links_signup_options_without_closing_decision(self):
        self.assertEqual(h25_forms_problems(self.handover), [])
        options = (DOCS / "SIGNUP-OPTIONS.md").read_text("utf-8")
        self.assertTrue(options.startswith("# Signup options — an open decision\n"))
        self.assertIn("records no decision", options)
        rows = handover_rows(self.handover)
        self.assertEqual(list(rows), list(OLD_DECISIONS) + list(PUBLIC_ROWS))  # no new row, same order
        self.assertEqual(rows["H25-forms"][1], "What the signup forms send to, how delivery and unsubscribe are handled, and the matching privacy text")
        self.assertIn((("docs/hass/SIGNUP-OPTIONS.md"), 1), local_links(rows["H25-forms"][3]))
        self.assertTrue(rows["H25-forms"][3].index("FEATURES.md#L53") < rows["H25-forms"][3].index("SIGNUP-OPTIONS.md#L1"))
        self.assertIn("[Retention options](RETENTION-OPTIONS.md)", rows["H21"][3])  # the H21 link is left as it was
        link = "[Signup options](SIGNUP-OPTIONS.md#L1)"
        self.assertEqual(self.handover.count(link), 1)
        self.assertEqual(h25_forms_problems(self.handover.replace(f", {link}", "")), [f"H25-forms source lacks {link}"])
        moved = self.handover.replace(f", {link}", "").replace("| H25-logo | Which logo is the final one | Owner / G | ",
                                                               f"| H25-logo | Which logo is the final one | Owner / G | {link}, ")
        self.assertEqual(h25_forms_problems(moved), [f"H25-forms source lacks {link}", "H25-logo links the signup options page"])
        self.assertEqual(h25_forms_problems(self.handover.replace("| H25-forms |", "| H25-formsx |")), ["no H25-forms row"])
        self.assertIn("H25-forms is not Owner / G", h25_forms_problems(self.handover.replace(
            "matching privacy text | Owner / G |", "matching privacy text | Michael |")))
        shifted = options.replace("# Signup options", "Intro\n# Signup options", 1).splitlines()[0]
        self.assertNotIn(ANCHORS[("docs/hass/SIGNUP-OPTIONS.md", 1)].lower(), shifted.lower())  # a shifted heading fails the anchor check

    def test_no_public_site_decision_is_recorded(self):
        new_rows = "\n".join(" ".join(handover_rows(self.handover)[d]) for d in PUBLIC_ROWS).lower()
        for chosen in ("slofishreport", "avoshack", "shopify", "cloudflare", "netlify", "github pages", "mailchimp",
                       "@", "http"):
            self.assertNotIn(chosen, new_rows)
        self.assertIn("is not a chosen destination", new_rows)
        self.assertIn("records no decision", self.handover)
        self.assertIn("**Checklist only. No step below has been signed off;", self.handover)

    def test_date_source_and_visibility_limits_not_overpromised(self):
        phrases = ("Pacific time", "160 characters", "60 days ahead", "Hass refuses a past or too-distant day",
                   "there is no notice", "Hass may ask for any missing detail or the source before a draft",
                   "a link is not fetched", "does not prove the route's facts", "undated", "takes no\n  RSVPs",
                   "is not a hike", "uses this route; change that hike first", "do not look for a way around the refusal",
                   "does not delete the idea", "own approval", "not on the website until", "fixture-only placeholders",
                   "replace it with their own verified route")
        self.assertEqual(missing_phrases(self.trial.replace("\n  ", " ").replace("\n", " "),
                                         [p.replace("\n  ", " ") for p in phrases]), [])
        self.assertEqual(missing_phrases("", phrases), list(phrases))  # a doc without them fails
        self.assertNotIn("a hike", self.rows[25][1].lower().replace("not a hike", ""))  # the route is never called a hike
        self.assertNotRegex(self.rows[25][1].lower(), r"\b(rsvp|on saturday|at \d+ ?(am|pm))\b")  # undated, no RSVP


if __name__ == "__main__":
    unittest.main()

"""RF1120-8: each listed unit has one BUILD_LEDGER.md section with a 40-hex merge SHA, a test command naming existing
test files and no phone, e-mail or message text (RF1058-11 canaries)."""

import re
import subprocess
import unittest

from hass.content_model import REPO_ROOT
from hass.tests.test_output_hygiene import CANARIES
from hass.tests.test_support_doc import private_data

UNITS = ("RF1035-7", "RF1058-11", "RF1105-28", "RF1105-29", "RF1105-30", "RF1120-7",
         "RF1105-11", "RF1105-13", "RF1130-5", "RF1130-6", "RF1130-7", "RF1140-7")  # RF1200-8 roll-up
UNITS += tuple(f"AV1537-{n:02d}" for n in range(1, 16))  # AV1537-16 roll-up
UNITS += tuple(f"AV1737-{n:02d}" for n in range(1, 16))  # AV1737-16 roll-up
UNITS += tuple(f"RF1650-{n}" for n in (1, 2, 3, 4, 5, 8))  # RF1650-9 roll-up
UNITS += ("RF1740-6", "RF1740-7")  # RF1740-8 roll-up (RF1740-5 is superseded: no merge, see test_superseded_unit_has_no_merge)
UNITS += tuple(f"AV1102-{n:02d}" for n in range(1, 17))  # AV1102-17 roll-up (sections in id order; the ledger has no issue headings)
UNITS += tuple(f"AV1222-{n:02d}" for n in range(1, 16))  # AV1222-16 roll-up (id order; the ledger has no issue headings)
UNITS += tuple(f"AV2022-{n:02d}" for n in range(1, 15))  # AV2022-15 roll-up
UNITS += tuple(f"AV1322-{n:02d}" for n in range(1, 16))  # AV1322-16 roll-up
UNITS += tuple(f"AV0022-{n:02d}" for n in range(1, 17) if n != 5)  # AV0022-17 roll-up (id order; AV0022-05 was closed unmerged, see test_unmerged_unit_has_no_section)
UNITS += tuple(f"AV1422-{n:02d}" for n in range(1, 15))  # AV1422-15 roll-up (id order; the ledger has no issue headings)
LABEL = ("Label facts are only a question", "Maker, organic and origin are never read from a photo")
WORDS = {"AV1737-03": ("Reactions never approve", "Edited text is not read"), "AV1737-15": ("Live inbox replacement stays attended",),
         "AV1737-14": ("The detail is free MB and the store name, never a path",)}  # AV1737-16 edge path 5
WORDS |= {"RF1650-1": ("are not editable",), "RF1650-3": ("a redo is not offered",)}  # RF1650-9 edge path 5
WORDS |= {"RF1740-6": ("fails closed",), "RF1740-7": ("names no path or sha",)}  # RF1740-8 edge path 5
WORDS |= {"AV1102-08": ("Design changes stay unbuilt",), "AV1102-09": ("A note is never proof of a claim",),
          "AV1102-12": ("Suggestion only; nothing stored",), "AV1102-15": ("Proposal only; the trial is not run",)}  # AV1102-17 edge path 5
WORDS |= {"AV1222-10": ("The cost is private; it is never on the website",), "AV1222-11": ("Draft only; nothing is posted",),
          "AV1222-15": ("No visible change",)}  # AV1222-16 edge path 5
WORDS |= {"AV2022-05": ("Audio is refused, never transcribed or stored",),
          "AV2022-09": ("BlueBubbles is loopback-only with no password in errors",),
          "AV2022-13": ("Retention reports counts only and deletes nothing",)}
WORDS |= {"AV0022-01": ("sideways photos keep only the Orientation tag (no location, camera or date)",),
          "AV0022-14": ("health only reports unused photo copies and deletes nothing",),
          "AV0022-16": ("`--live` is operator-only and no model-quality claim is made",)}  # AV0022-17 edge path 5
WORDS |= {"AV1422-06": ("No invented guest count",), "AV1422-13": ("Docs only",), "AV1422-14": ("H25 stays a release step",)}  # AV1422-15 edge path 5
LEDGER = (REPO_ROOT / "BUILD_LEDGER.md").read_text(encoding="utf-8")
SHA = re.compile(r"\b[0-9a-f]{40}\b")
GIT_HEX = re.compile(r"\b(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")  # commit ids are not phone numbers
PRIVATE = re.compile("|".join([r"\+?\d{3}[ .)-]+\d{3}[ .-]\d{4}", r"\w+-canary-\d+", *map(re.escape, CANARIES)]))


def sections(text, unit):
    return [p for p in re.split(r"^(?=## )", text, flags=re.M) if re.match(rf"## [^\n]*\({re.escape(unit)}\)", p)]


def problems(text, tests=REPO_ROOT / "hass" / "tests"):
    out = []
    for u in UNITS:
        found = sections(text, u)
        clean = GIT_HEX.sub("", body := found[0] if len(found) == 1 else "")
        mods = [f"{m}.py" for m in re.findall(r"hass\.tests\.(test_\w+)", body)] + re.findall(r"-p '([^']+)'", body)
        out += [f"{u}: {len(found)} headings"] * (len(found) != 1) + [f"{u}: no merge sha"] * (not SHA.search(body))
        site = re.findall(r"storefront-mockup/[\w-]+-qa\.(?:py|cjs)\b", body)  # site units: their QA scripts
        out += [f"{u}: no test command"] * (not (mods + site)) + [f"{u}: missing {m}" for m in mods if not any(tests.glob(m))]
        out += [f"{u}: missing {s}" for s in site if not (tests.parents[1] / s).is_file()]
        out += [f"{u}: limit wording?"] * (not all(s in body for s in WORDS.get(u, ())))
        out += [f"{u}: private data"] * bool(private_data(clean) or PRIVATE.search(clean))
        out += [f"{u}: guests messaged?"] * (u == "RF1130-6" and "warned about in the draft, never messaged" not in body)
        out += [f"{u}: label facts?"] * (u == "AV1537-15" and not all(s in body for s in LABEL))
        out += [f"{u}: writer worktree?"] * (u == "AV1537-13" and "never restores onto the writer worktree" not in body)
    return out


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


class LedgerRF1120Tests(unittest.TestCase):
    def test_av1422_06_merge_date_is_pacific_date(self):
        # PR #393 merged 2026-11-05 02:43:33 UTC, still November 4 in Pacific time.
        heading = sections(LEDGER, "AV1422-06")[0].splitlines()[0]
        self.assertTrue(heading.endswith(" — November 4, 2026"), heading)

    def test_merge_shas_exist_in_history(self):
        if not (REPO_ROOT / ".git").exists() or git("rev-parse", "--is-shallow-repository") == "true":
            self.skipTest("no .git (tarball checkout) or shallow clone: merge history not available")
        for unit in UNITS:
            sha = SHA.findall(sections(LEDGER, unit)[0])[0]
            self.assertEqual(git("cat-file", "-t", sha), "commit", f"{unit} {sha}")
            self.assertTrue(git("show", "-s", "--format=%s", sha).endswith(f"rb/{unit.lower()}"), f"{unit} {sha}")

    def test_ledger_sections_complete_and_bad_ones_named(self):
        self.assertEqual(problems(LEDGER), [])
        one, last = sections(LEDGER, "RF1035-7")[0], sections(LEDGER, "RF1105-30")[0]
        cases = {"RF1035-7: 0 headings": LEDGER.replace("(RF1035-7)", "(RF1035-70)"),
                 "RF1035-7: 2 headings": LEDGER + "\n" + one,
                 "RF1035-7: no merge sha": LEDGER.replace(SHA.findall(one)[0], "6b92a6e"),
                 "RF1035-7: missing test_inbox_noncez.py": LEDGER.replace("test_inbox_nonces ", "test_inbox_noncez "),
                 "RF1120-7: missing test_nope*.py": LEDGER.replace("'test_statebackup*.py'", "'test_nope*.py'"),
                 "RF1105-30: no test command": LEDGER.replace(last, "## x (RF1105-30)\n" + "f" * 40 + "\n"),
                 "RF1130-6: guests messaged?": LEDGER.replace("never messaged", "messaged"),
                 "AV1537-07: 2 headings": LEDGER + "\n" + sections(LEDGER, "AV1537-07")[0],
                 "AV1537-15: 0 headings": LEDGER.replace("(AV1537-15)", "(AV1537-16)"),
                 "AV1537-12: no merge sha": LEDGER.replace(SHA.findall(sections(LEDGER, "AV1537-12")[0])[0], "4f33ef9"),
                 "AV1537-04: missing test_findz.py": LEDGER.replace("hass.tests.test_find ", "hass.tests.test_findz "),
                 "AV1537-15: label facts?": LEDGER.replace(LABEL[0], "Label facts fill the draft"),
                 "AV1537-15: label facts?|origin": LEDGER.replace(LABEL[1], "Maker, organic and origin are read"),
                 "AV1537-13: writer worktree?": LEDGER.replace("never restores onto", "may restore onto")}
        av = {u: sections(LEDGER, u)[0] for u in ("AV1737-01", "AV1737-09", "AV1737-13")}
        cases |= {"AV1737-01: 2 headings": LEDGER + "\n" + av["AV1737-01"], "AV1737-15: 0 headings": LEDGER.replace("(AV1737-15)", "(AV1737-150)"),
                  "AV1737-09: no merge sha": LEDGER.replace(SHA.findall(av["AV1737-09"])[0], "27aa3ef"),
                  "AV1737-13: no test command": LEDGER.replace(av["AV1737-13"], "## x (AV1737-13)\n" + "a" * 40 + "\n"),
                  "AV1737-12: missing storefront-mockup/nope-qa.py": LEDGER.replace("community-qa.py`", "nope-qa.py`"),
                  "AV1737-03: limit wording?": LEDGER.replace("Reactions never approve", "Reactions approve"),
                  "AV1737-03: limit wording?|edit": LEDGER.replace("Edited text is not read", "Edited text is read"),
                  "AV1737-14: limit wording?": LEDGER.replace("store name, never a path", "store path"),
                  "AV1737-15: limit wording?": LEDGER.replace("stays attended", "is automatic"),
                  "AV1737-07: private data": LEDGER.replace("(AV1737-07)", "(AV1737-07)\nmail owner@example.com")}
        cases |= {"RF1650-1: 2 headings": LEDGER + "\n" + sections(LEDGER, "RF1650-1")[0], "RF1650-4: 0 headings": LEDGER.replace("(RF1650-4)", "(RF1650-40)"),
                  "RF1650-8: no merge sha": LEDGER.replace(SHA.findall(sections(LEDGER, "RF1650-8")[0])[0], "dea25e3"),
                  "RF1650-5: missing test_media_timez.py": LEDGER.replace("hass.tests.test_media_time ", "hass.tests.test_media_timez "),
                  "RF1650-1: limit wording?": LEDGER.replace("are not editable", "are editable"), "RF1650-3: limit wording?": LEDGER.replace("a redo is not offered", "a redo is offered")}
        cases |= {"RF1740-6: 2 headings": LEDGER + "\n" + sections(LEDGER, "RF1740-6")[0], "RF1740-7: 0 headings": LEDGER.replace("(RF1740-7)", "(RF1740-70)"),
                  "RF1740-6: no merge sha": LEDGER.replace(SHA.findall(sections(LEDGER, "RF1740-6")[0])[0], "9a824cd"),
                  "RF1740-7: missing test_set_photo_folderz.py": LEDGER.replace("hass.tests.test_set_photo_folder ", "hass.tests.test_set_photo_folderz "),
                  "RF1740-6: limit wording?": LEDGER.replace("fails closed", "fails open"), "RF1740-7: limit wording?": LEDGER.replace("names no path or sha", "names the path"),
                  "RF1740-7: private data": LEDGER.replace("(RF1740-7)", "(RF1740-7)\nmail owner@example.com")}
        cases |= {"AV1102-01: 2 headings": LEDGER + "\n" + sections(LEDGER, "AV1102-01")[0], "AV1102-16: 0 headings": LEDGER.replace("(AV1102-16)", "(AV1102-160)"),
                  "AV1102-05: no merge sha": LEDGER.replace(SHA.findall(sections(LEDGER, "AV1102-05")[0])[0], "146b072"),
                  "AV1102-03: missing test_availability_words_pinz.py": LEDGER.replace("test_availability_words_pin ", "test_availability_words_pinz "),
                  "AV1102-02: missing storefront-mockup/nope-qa.cjs": LEDGER.replace("catalog-only-qa.cjs` run", "nope-qa.cjs` run"),
                  "AV1102-08: limit wording?": LEDGER.replace("Design changes stay unbuilt", "Design changes are built"),
                  "AV1102-09: limit wording?": LEDGER.replace("A note is never proof of a claim", "A note proves a claim"),
                  "AV1102-12: limit wording?": LEDGER.replace("Suggestion only; nothing stored", "Suggestion stored"),
                  "AV1102-15: limit wording?": LEDGER.replace("Proposal only; the trial is not run", "The trial is run"),
                  "AV1102-09: private data": LEDGER.replace("(AV1102-09)", "(AV1102-09)\nmail owner@example.com")}
        cases |= {"AV1222-01: 2 headings": LEDGER + "\n" + sections(LEDGER, "AV1222-01")[0], "AV1222-15: 0 headings": LEDGER.replace("(AV1222-15)", "(AV1222-150)"),
                  "AV1222-08: no merge sha": LEDGER.replace(SHA.findall(sections(LEDGER, "AV1222-08")[0])[0], "93b49a4"),
                  "AV1222-13: missing test_hidden_commandz.py": LEDGER.replace("hass.tests.test_hidden_command ", "hass.tests.test_hidden_commandz "),
                  "AV1222-14: missing storefront-mockup/nope-qa.cjs": LEDGER.replace("catalog-only-qa.cjs` against", "nope-qa.cjs` against"),
                  "AV1222-10: limit wording?": LEDGER.replace("it is never on the website", "it is on the website"),
                  "AV1222-11: limit wording?": LEDGER.replace("Draft only; nothing is posted", "The draft is posted"),
                  "AV1222-15: limit wording?": LEDGER.replace("No visible change", "A visible change"),
                  "AV1222-04: private data": LEDGER.replace("(AV1222-04)", "(AV1222-04)\ncall +1 555 123 4567")}
        cases |= {"AV2022-01: 2 headings": LEDGER + "\n" + sections(LEDGER, "AV2022-01")[0],
                  "AV2022-14: 0 headings": LEDGER.replace("(AV2022-14)", "(AV2022-140)"),
                  "AV2022-03: no merge sha": LEDGER.replace(SHA.findall(sections(LEDGER, "AV2022-03")[0])[0], "21e06ae"),
                  "AV2022-03: missing test_interpreter_today_missing.py": LEDGER.replace("hass.tests.test_interpreter_today -v", "hass.tests.test_interpreter_today_missing -v"),
                  "AV2022-05: limit wording?": LEDGER.replace("Audio is refused, never transcribed or stored", "Audio is stored"),
                  "AV2022-09: limit wording?": LEDGER.replace("BlueBubbles is loopback-only with no password in errors", "BlueBubbles is remote"),
                  "AV2022-13: limit wording?": LEDGER.replace("Retention reports counts only and deletes nothing", "Retention deletes rows")}
        cases |= {"AV0022-01: 2 headings": LEDGER + "\n" + sections(LEDGER, "AV0022-01")[0], "AV0022-16: 0 headings": LEDGER.replace("(AV0022-16)", "(AV0022-160)"),
                  "AV0022-10: no merge sha": LEDGER.replace(SHA.findall(sections(LEDGER, "AV0022-10")[0])[0], "004998d"),
                  "AV0022-09: missing test_proposal_photo_wordz.py": LEDGER.replace("hass.tests.test_proposal_photo_words ", "hass.tests.test_proposal_photo_wordz "),
                  "AV0022-01: limit wording?": LEDGER.replace("keep only the Orientation tag", "keep the camera tags"),
                  "AV0022-14: limit wording?": LEDGER.replace("health only reports unused photo copies and deletes nothing", "health deletes unused photo copies"),
                  "AV0022-16: limit wording?": LEDGER.replace("is operator-only and no model-quality claim is made", "is run by CI"),
                  "AV0022-12: private data": LEDGER.replace("(AV0022-12)", "(AV0022-12)\nmail owner@example.com")}
        cases |= {f"AV2022-08: private data|{leak}": LEDGER.replace("(AV2022-08)", "(AV2022-08)\n" + leak) for leak in
                  ("call +1 555 123 4567", "mail owner@example.com", "said quokka-canary-4242")}
        cases |= {f"RF1035-7: private data|{leak}": LEDGER.replace(one, one + leak + "\n") for leak in
                  ("call +1 555 123 4567", "mail owner@example.com", "said quokka-canary-4242", "+15550100777")}
        cases["AV1537-15: private data"] = LEDGER.replace("(AV1537-15)", "(AV1537-15)\ncall +1 555 123 4567")
        for want, text in cases.items():
            self.assertIn(want.split("|")[0], problems(text), want)

    def test_unmerged_unit_has_no_section(self):
        self.assertEqual(sections(LEDGER, "AV0022-05"), [], "AV0022-05 (PR #224) was closed unmerged: no placeholder section")
        self.assertIn("AV0022-05", sections(LEDGER, "AV0022-04")[0])  # the closure is named once, in AV0022-04's limits

    def test_superseded_unit_has_no_merge(self):
        found = sections(LEDGER, "RF1740-5")
        self.assertEqual(len(found), 1)
        self.assertIn("SUPERSEDED".lower(), found[0].lower())
        self.assertIn("AV1737-09", found[0])
        self.assertIn("b8e2769", found[0])
        self.assertIn("no PR exists", found[0])
        self.assertFalse(SHA.search(found[0].replace("27aa3ef5c1305a752517a276722f2049afd0bdd2", "")), "RF1740-5 has no merge of its own")
        self.assertFalse((REPO_ROOT / "hass" / "tests" / "test_hike_create_repeat.py").exists())

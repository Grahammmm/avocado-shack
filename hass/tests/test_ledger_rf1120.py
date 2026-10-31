"""RF1120-8: each listed unit has one BUILD_LEDGER.md section with a 40-hex merge SHA, a test command naming existing
test files and no phone, e-mail or message text (RF1058-11 canaries)."""

import re
import subprocess
import unittest

from hass.content_model import REPO_ROOT
from hass.tests.test_output_hygiene import CANARIES
from hass.tests.test_support_doc import private_data

UNITS = ("RF1035-7", "RF1058-11", "RF1105-28", "RF1105-29", "RF1105-30", "RF1120-7")
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
        out += [f"{u}: no test command"] * (not mods) + [f"{u}: missing {m}" for m in mods if not any(tests.glob(m))]
        out += [f"{u}: private data"] * bool(private_data(clean) or PRIVATE.search(clean))
    return out


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()


class LedgerRF1120Tests(unittest.TestCase):
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
                 "RF1105-30: no test command": LEDGER.replace(last, "## x (RF1105-30)\n" + "f" * 40 + "\n")}
        cases |= {f"RF1035-7: private data|{leak}": LEDGER.replace(one, one + leak + "\n") for leak in
                  ("call +1 555 123 4567", "mail owner@example.com", "said quokka-canary-4242", "+155****0777")}
        for want, text in cases.items():
            self.assertIn(want.split("|")[0], problems(text), want)

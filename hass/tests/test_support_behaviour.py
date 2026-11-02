"""AVB-17 (H19): the SUPPORT.md "Service and Mac behaviour" table names only real health check ids (stdlib, offline)."""
import re
import unittest

from hass.tests.test_support_doc import DOC, HEALTH, documented_ids, emitted_ids, private_data

TITLE = "## Service and Mac behaviour"
EVENTS = ("Agent Orange reboot", "Sandbox service crash", "Mac sleep", "Mac logout", "Mac reboot", "macOS update")
HEADER = ["Event", "Known", "Not yet measured", "Shows up as"]


def section_of(doc: str) -> str:
    start = doc.index(TITLE)
    end = doc.find("\n## ", start + 1)
    return doc[start:end if end != -1 else len(doc)]


def rows_of(section: str) -> list:
    rows = [[c.strip() for c in line.strip().strip("|").split("|")] for line in section.splitlines() if line.startswith("|")]
    return [r for r in rows if r != HEADER and not set("".join(r)) <= set("- ")]


def problems(doc: str, source: str) -> list:
    """Named failures: placement, missing/duplicate rows, made-up ids, empty or H07-less Mac cells."""
    if doc.count(TITLE + "\n") != 1:
        return ["section count: %d" % doc.count(TITLE + "\n")]
    out = [] if doc.index("## Info lines") < doc.index(TITLE) < doc.index("## Restore") else ["section out of place"]
    rows = rows_of(section_of(doc))
    names = [r[0] for r in rows]
    out += ["missing row: " + e for e in EVENTS if e not in names]
    out += ["duplicate row: " + e for e in EVENTS if names.count(e) > 1]
    for r in rows:
        ids = re.findall(r"`([^`]+)`", r[3])
        out += ["unknown id: " + i for i in ids if i not in emitted_ids(source)]
        if not ids and "no health check" not in r[3]:
            out.append("no id or 'no health check': " + r[0])
        if r[0].startswith("Mac") and "H07" not in r[2]:
            out.append("no H07 in not-yet-measured: " + r[0])
    return out


SOURCE, TEXT = HEALTH.read_text("utf-8"), DOC.read_text("utf-8")
SECTION = section_of(TEXT)


def edited(old: str, new: str) -> str:
    return TEXT.replace(SECTION, SECTION.replace(old, new, 1))


class SupportBehaviourTest(unittest.TestCase):
    def test_real_doc_has_no_problems(self):
        self.assertEqual(problems(TEXT, SOURCE), [])
        self.assertEqual(sorted(r[0] for r in rows_of(SECTION)), sorted(EVENTS))

    def test_section_sits_between_info_lines_and_restore_once(self):
        self.assertLess(TEXT.index("## Info lines"), TEXT.index(TITLE))
        self.assertLess(TEXT.index(TITLE), TEXT.index("## Restore"))
        self.assertEqual(problems(TEXT.replace(SECTION, "") + "\n" + SECTION, SOURCE), ["section out of place"])
        self.assertEqual(problems(TEXT + "\n" + SECTION, SOURCE), ["section count: 2"])
        self.assertEqual(problems(TEXT.replace(SECTION, ""), SOURCE), ["section count: 0"])

    def test_missing_and_duplicate_rows_are_named(self):
        row = next(l for l in SECTION.splitlines() if l.startswith("| Mac sleep |"))
        self.assertEqual(problems(edited(row + "\n", ""), SOURCE), ["missing row: Mac sleep"])
        self.assertEqual(problems(edited(row + "\n", row + "\n" + row + "\n"), SOURCE), ["duplicate row: Mac sleep"])

    def test_every_shown_id_is_a_real_check(self):
        for r in rows_of(SECTION):
            for i in re.findall(r"`([^`]+)`", r[3]):
                self.assertIn(i, emitted_ids(SOURCE), r[0])
        self.assertEqual(problems(edited("`outbox-stuck`", "`mac-asleep`"), SOURCE), ["unknown id: mac-asleep"])
        self.assertEqual(problems(edited("no health check", "nothing"), SOURCE), ["no id or 'no health check': Sandbox service crash"])

    def test_mac_rows_say_h07_has_not_run(self):
        for r in rows_of(SECTION):
            if r[0].startswith("Mac"):
                self.assertIn("H07", r[2])
        row = next(l for l in SECTION.splitlines() if l.startswith("| Mac logout |"))
        self.assertEqual(problems(edited(row, row.replace("H07", "H08")), SOURCE), ["no H07 in not-yet-measured: Mac logout"])
        blank = row.replace("What the bridge does after logout; the H07 compatibility check has not run.", " ")
        self.assertEqual(problems(edited(row, blank), SOURCE), ["no H07 in not-yet-measured: Mac logout"])

    def test_section_is_private_and_leaves_headings_alone(self):
        self.assertEqual(private_data(SECTION), [])
        self.assertNotIn("/home", SECTION)
        self.assertEqual(documented_ids(TEXT), documented_ids(TEXT.replace(SECTION, "")))


if __name__ == "__main__":
    unittest.main()

"""AV1922-07 (H21): docs/hass/RETENTION-OPTIONS.md explains the open retention choice without making it. Stdlib, offline:
it reads the page and repository sources only; no database, state dir, model or request is opened.
Run: python3 -m unittest hass.tests.test_retention_options_doc -v
"""
import re
import unittest
from pathlib import Path

from hass.conversation import TRANSITIONS

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs" / "hass"
PAGE = DOCS / "RETENTION-OPTIONS.md"
CLASSES = ("Inbox", "Messages", "Outbox", "Drafts", "Approvals", "Closed memory rows", "Screenshots", "Photo originals",
           "Photo web copies", "Backups")
HEADER = ["Class", "Holds (kinds of field)", "Read today by", "After 7 days", "After 30 days", "After 90 days"]
LOOK_BACK = {3: "week", 4: "month", 5: "quarter"}  # column -> the look-back word that cell must use
# Each caveat is (name, a phrase the page must say). The phrases are written here from the sources, not from the page.
CAVEATS = {
    "report is read-only": "always prints `deletes: 0`",
    "strictly older": "strictly older than the report time minus N elapsed days",
    "not a calendar policy": "not a Pacific calendar-day policy",
    "oldest is not overdue": "`oldest` is the oldest dated item the report found, not the oldest item past the cutoff",
    "screenshot age basis": "the file's last-changed time",
    "backup age basis": "the UTC time in the backup folder's name",
    "closed memory age basis": "the time it was forgotten, else the time it was replaced",
    "unreadable times": "counts nowhere",
    "undated": "`undated`",
    "orphans": "`webOrphans`",
    "absent is not zero": "Absent is not zero",
    "unavailable": "`unavailable`",
    "complete is not verified": "not a verified restore point",
    "active memory excluded": "Current (active) rows are not counted here",
    "open drafts include undoable": "applied and checked (an applied or checked change can still be undone)",
    "open work is not safe": "Open work (waiting, approved, applied, checked) is never safe to remove by age",
    "waiting inbox rows": "Waiting rows are still not safe to remove by age",
    "unsent replies": "waiting replies older than a week would never be sent",
    "rows versus files": "the report counts the database rows, not those files",
    "audit log is separate": "History reads the separate audit log",
    "other copies": "Backups keep copies of what the current state no longer holds",
    "no erasure claim": "nothing here is a claim of global erasure",
    "support rules": "stop and ask before deleting or editing a database or a backup",
}
ANCHORS = {("hass/retention.py", 11): "owner action 4", ("docs/hass/FEATURES.md", 49): "| H21 |",
           ("docs/hass/TRIAL.md", 128): "## What counts as done", ("docs/hass/TRIAL.md", 141): "## Reviewing the trial"}
# SUPPORT.md is edited often, so it is linked by heading, never by line number. Each heading anchor must exist and its
# section must still say the phrase the page relies on. (TRIAL.md and the source files keep checked line anchors above.)
HEADING_ONLY = ("docs/hass/SUPPORT.md",)
SECTIONS = {("docs/hass/SUPPORT.md", "inbox-integrity"): "Recreating the queue needs a new start point",
            ("docs/hass/SUPPORT.md", "memory-invariant"): "forgotten fact's text still stored",
            ("docs/hass/SUPPORT.md", "disk-low"): "never delete or rotate backups",
            ("docs/hass/SUPPORT.md", "restore"): "statebackup.py verify BACKUP"}
CORE_SOURCES = ("hass/retention.py", "hass/conversation.py", "hass/statebackup.py", "docs/hass/SUPPORT.md")
READERS = ("hass/inbox.py", "hass/memory.py", "hass/media.py", "hass/editor.py", "hass/ops/history.py", "hass/health.py",
           "hass/trial_summary.py", "docs/hass/TRIAL.md")
QUESTION_WORDS = ("period", "protected", "undo", "trial review", "originals", "undated", "backups", "other copies", "responsible")
POLICY = (r"\bwill be deleted\b", r"\bwill (?:be )?(?:purged|removed|erased)\b", r"\bDELETE\s+FROM\b", r"\brm\s+-", r"\bshutil\b",
          r"\bsystemctl\b", r"\bcrontab\b", r"\bfind\b[^\n]*-delete", r"\bunlink\b", r"--delete\b",
          r"\b(?:chosen|selected|agreed|approved) (?:retention )?period (?:is|will be|of)\b", r"\bretention period (?:is|of) \d",
          r"\bdefault (?:period|retention) is\b", r"\bdecided on\b", r"\bdecision date\s*:", r"\banswers?\s*:\s*\d", r"\bsigned off by\b")
PRIVATE = (r"[\w.+-]+@[\w-]+\.[\w.]+", r"\+?\d[\d ().-]{8,}\d", r"\b[0-9a-f]{12,}\b", r"/(?:home|Users|var|tmp|etc)/",
           r"~/", r"\bchg-[0-9a-f]{6,}", r"\bhass-state-\d{8}T", r"\bact-[0-9a-f]{6,}")


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def matrix(doc: str) -> list:
    return [[c.strip() for c in line.strip().strip("|").split(" | ")] for line in doc.splitlines()
            if line.startswith("| ") and not line.startswith("| ---")]


def matrix_problems(doc: str) -> list:
    rows = matrix(doc)
    if not rows or rows[0] != HEADER:
        return ["header is not the six expected columns"]
    problems = [f"class order is {[r[0] for r in rows[1:]]}"] if [r[0] for r in rows[1:]] != list(CLASSES) else []
    for row in rows[1:]:
        if len(row) != 6:
            problems.append(f"{row[0]}: {len(row)} cells")
            continue
        for col in (1, 2):
            if len(row[col]) < 60:
                problems.append(f"{row[0]}: {HEADER[col]} cell is thin")
        for col, word in LOOK_BACK.items():
            if word not in row[col].lower():
                problems.append(f"{row[0]}: {HEADER[col]} does not name its look-back")
        if "if later deleted" not in row[3].lower():
            problems.append(f"{row[0]}: 7-day cell is not conditional")
        if len({row[3], row[4], row[5]}) != 3:
            problems.append(f"{row[0]}: consequence cells repeat")
    return problems


def caveat_problems(doc: str) -> list:
    text = squash(doc).replace("**", "").lower()
    return [name for name, phrase in CAVEATS.items() if squash(phrase).lower() not in text]


def policy_problems(doc: str) -> list:
    return [p for p in POLICY if re.search(p, doc, re.I)] + [p for p in (r"\bwe chose\b", r"\bis hereby\b") if re.search(p, doc, re.I)]


def private_problems(text: str) -> list:
    return [p for p in PRIVATE if re.search(p, text)]


def question_problems(doc: str) -> list:
    if "## Questions Michael and G must answer" not in doc:
        return ["no questions section"]
    block = doc.split("## Questions Michael and G must answer", 1)[1].split("\n## ", 1)[0]
    items = re.findall(r"^(\d+)\. (.+)$", block, re.M)
    problems = [] if [n for n, _ in items] == [str(i) for i in range(1, 10)] else ["questions are not numbered 1-9"]
    problems += [f"question {n} is not a question" for n, text in items if "?" not in text]
    return problems + [f"nobody is asked about {w}" for w in QUESTION_WORDS if w not in block.lower()]


def sections(text: str) -> dict:
    """Markdown headings -> section text, keyed by the GitHub-style slug of the heading."""
    out, slug = {}, None
    for line in text.splitlines():
        m = re.match(r"#{1,6}\s+(.*?)\s*$", line)
        if m:
            slug = re.sub(r"[^\w\s-]", "", m.group(1).lower()).strip().replace(" ", "-")
            out[slug] = ""
        elif slug is not None:
            out[slug] += line + "\n"
    return out


def link_problems(doc: str) -> list:
    problems, seen = [], set()
    for path, anchor in re.findall(r"\]\(([^)#\s]+)(?:#([\w-]+))?\)", doc):
        if path.startswith(("http", "mailto")):
            continue
        target = (DOCS / path).resolve()
        rel = target.relative_to(ROOT).as_posix()
        seen.add(rel)
        if not target.is_file():
            problems.append(f"{path} is not a file")
        elif anchor and rel in HEADING_ONLY:
            body = sections(target.read_text("utf-8")).get(anchor)
            if body is None:
                problems.append(f"{path}#{anchor} is not a heading (link SUPPORT.md by heading, not line number)")
            elif (rel, anchor) not in SECTIONS:
                problems.append(f"{path}#{anchor} is not a checked section")
            elif SECTIONS[rel, anchor].lower() not in body.lower():
                problems.append(f"{path}#{anchor} moved")
        elif anchor:
            if not re.fullmatch(r"L\d+", anchor):
                problems.append(f"{path}#{anchor} is not a line anchor")
                continue
            anchor = anchor[1:]
            lines = target.read_text("utf-8").splitlines()
            if not 1 <= int(anchor) <= len(lines):
                problems.append(f"{path}#L{anchor} is past the end")
            elif (rel, int(anchor)) not in ANCHORS:
                problems.append(f"{path}#L{anchor} is not a checked anchor")
            elif ANCHORS[rel, int(anchor)].lower() not in lines[int(anchor) - 1].lower():
                problems.append(f"{path}#L{anchor} moved")
    problems += [f"{need} is not linked" for need in CORE_SOURCES + READERS if need not in seen]
    return problems


class RetentionOptionsDocTests(unittest.TestCase):
    def setUp(self):
        self.doc = PAGE.read_text("utf-8")

    def test_retention_matrix_covers_each_class_and_three_periods(self):
        self.assertEqual(matrix_problems(self.doc), [])
        lines = self.doc.splitlines()
        no_backups = "\n".join(ln for ln in lines if not ln.startswith("| Backups |"))
        self.assertEqual(matrix_problems(no_backups)[0][:12], "class order ")
        no_90 = "\n".join(ln.rsplit(" | ", 1)[0] + " |" if ln.startswith("| ") else ln for ln in lines)
        self.assertNotEqual(matrix_problems(no_90), [])
        emptied = re.sub(r"(?m)^\| Backups \| .*?(?= \| `statebackup)", "| Backups | x", self.doc)
        self.assertIn("Backups: Holds (kinds of field) cell is thin", matrix_problems(emptied))
        no_look_back = "\n".join(ln.replace("month", "while") if ln.startswith("| Inbox |") else ln for ln in lines)
        self.assertIn("Inbox: After 30 days does not name its look-back", matrix_problems(no_look_back))
        self.assertEqual(len(matrix(self.doc)), 11)  # the header and the ten classes

    def test_age_basis_unknown_and_live_work_caveats(self):
        self.assertEqual(caveat_problems(self.doc), [])
        plain = self.doc.replace("**", "")
        for name, phrase in CAVEATS.items():
            with self.subTest(name):
                self.assertIn(phrase, plain)
                self.assertEqual(caveat_problems(plain.replace(phrase, "")), [name])
        retention = (ROOT / "hass" / "retention.py").read_text("utf-8")
        for fact in ('doc["deletes"] = 0', "when < cutoff", "COALESCE(forgotten_at, superseded_at)", "not counted)",
                     "st_mtime", 'e.name.endswith(".png")', '"undated"', "_web_orphans"):
            self.assertIn(fact, retention)
        self.assertEqual(set(TRANSITIONS), {"needs-details", "proposed", "approved", "applied", "verified"})  # the report's open drafts
        self.assertIn("NAME_RE", (ROOT / "hass" / "statebackup.py").read_text("utf-8"))
        self.assertIn("1-31", (DOCS / "TRIAL.md").read_text("utf-8"))  # the longest trial summary range the page quotes

    def test_no_policy_or_erasure_claim_and_questions_remain_open(self):
        self.assertEqual(policy_problems(self.doc), [])
        self.assertEqual(question_problems(self.doc), [])
        for phrase in ("records no decision, selects no period, deletes nothing and authorizes no cleanup", "not chosen defaults",
                       "no deletion step enforces a retention period", "Git history", "the owner's phone",
                       "Nothing on this page is a policy, a default, a sign-off or a decision date"):
            self.assertIn(phrase.lower(), squash(self.doc).replace("**", "").lower())
        for bad in ("The chosen period is 30 days.", "Messages will be deleted after 30 days.", "Run DELETE FROM drafts;",
                    "Then rm -rf the folder.", "The retention period is 90 days.", "Add a crontab line.", "Answer: 7 days"):
            with self.subTest(bad):
                self.assertNotEqual(policy_problems(self.doc + "\n" + bad), [])
        self.assertNotEqual(question_problems(re.sub(r"(?m)^7\. .*\n", "", self.doc)), [])
        self.assertNotEqual(question_problems(self.doc.replace("\n9. ", "\n")), [])
        self.assertEqual(private_problems(self.doc), [])  # no contact, id or state path; the checker's own proof:
        for sample in ("write to someone@example.org", "call +1 555 010 0199", "id 0123456789abcdef", "/home/someone/state",
                       "chg-0123456789ab", "hass-state-20260101T000000Z"):
            with self.subTest(sample):
                self.assertNotEqual(private_problems(sample), [])

    def test_sources_are_local_existing_and_trial_is_proposed(self):
        self.assertEqual(link_problems(self.doc), [])
        self.assertNotIn("](http", self.doc)
        self.assertNotEqual(link_problems(self.doc + "\n[x](../../hass/no_such_file.py)"), [])
        self.assertNotEqual(link_problems(self.doc.replace("retention.py#L11", "retention.py#L99999")), [])
        self.assertNotEqual(link_problems(self.doc.replace("retention.py#L11", "retention.py#L12")), [])
        self.assertNotEqual(link_problems(self.doc.replace("](SUPPORT.md#restore)", "](SUPPORT.md#restore-steps)")), [])
        self.assertNotEqual(link_problems(self.doc.replace("](SUPPORT.md#restore)", "](SUPPORT.md#paused-long)")), [])
        self.assertNotEqual(link_problems(self.doc.replace("](SUPPORT.md#restore)", "](SUPPORT.md#L220)")), [])
        self.assertNotEqual(link_problems(self.doc.replace("](SUPPORT.md#restore)", "](SUPPORT.md#problems)")), [])
        self.assertNotEqual(link_problems(self.doc.replace("(../../hass/statebackup.py)", "(../../hass/statebackup.pyx)")), [])
        trial = squash(self.doc.split("## The trial review", 1)[1].split("\n## ", 1)[0])
        for phrase in ("It is a proposal; no real-phone trial has been completed", "accept ranges up to 31 days",
                       "is not generated from these stores", "deleting them shortens the evidence available"):
            self.assertIn(phrase, trial)
        self.assertTrue(self.doc.startswith("# How long to keep private data (H21) - options and questions\n"))
        self.assertIn("**Open decision for Michael and G.", self.doc)


if __name__ == "__main__":
    unittest.main()

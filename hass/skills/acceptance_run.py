"""AV1109-16 (SKILLS-SPEC card 18 and 4.3): the offline acceptance engine, run on recorded interpreter replies.

    python3 -B hass/skills/acceptance_run.py [--rows FILE] [--selftest] [--record ROW]

Each row of messages.jsonl (one message or a short exchange, a recorded interpreter reply per model call, an expected
disposition) goes through the REAL Conversation, Dispatcher, skills registry, Editor, sitegen and claims on a throwaway
writer worktree and state dir, with a frozen clock (Sunday 2026-11-08 09:00 Pacific, one minute per message) and a synthetic
owner. Only the interpreter (recorded), the screenshot and the outbound chat are in-memory stand-ins. Nothing live is touched.
Per row it asserts SKILLS-SPEC 4.3 items 1-5 and 7-9 (item 6, the live browser preview, is the live runner's):

  1 routing        the skill that actually ran (observed, not the row's claim) is expected or a listed alternative
  2 disposition    exact production disposition per message, required question or reply fragments
  3 no write       content, generated site files and assets/products are byte-identical (and HEAD and the tree are
                   clean) after each message and after a wrong yes
  4 exact diff     after `yes <code>`: committed content diff, changed-file set and new picture hashes equal expected/<id>.json
  5 content rules  content validation, TEXT_LIMITS, no price or size nobody said, no invented capacity or difficulty,
                   no unstated claim, picture name, type, size, metadata and house check
  7 undo           `undo` then its own `yes`: the tree equals the start except the exact residue the row pins
  8 duplicate      the same provider id after every message and approval changes nothing
  9 privacy        no owner text, sender, chat or path in interpreter_audit or the stage log

Exit 0: every assertion met. 1: an assertion failed. 2: malformed row, fixture, flag or setup. The thresholds below are
constants: nothing lowers them (an unknown or weakening flag, or a policy override in the API, is refused). A machine-valid
row is never a human-accepted one; a partial or `--selftest` run is never the full-site acceptance (SKILLS-POS-0's bar).
Reported results carry the row id, the observed skill, the disposition and assertion codes only.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.content_model import REPO_ROOT  # noqa: E402

SCHEMA_VERSION = 1
FIXTURE_ROOT = REPO_ROOT / "hass" / "tests" / "fixtures" / "skills-acceptance"
DEFAULT_ROWS = FIXTURE_ROOT / "messages.jsonl"
SELFTEST_ROWS = FIXTURE_ROOT / "_selftest" / "messages.jsonl"
START = datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc)  # Sunday 09:00 PST: "Saturday" and "the 29th" are fixed
OWNER, CHAT = "acceptance-owner@example.invalid", "chat-acceptance-owner"
TTL_SECONDS = 1800  # 4.3: the 30-minute approval window
TAGS = ("primary", "vague", "typo", "multi", "turns", "refuse", "photo", "selftest")
SELFTEST_ROWS_N, SELFTEST_FAULTS_N = 8, 4

# -- thresholds (SKILLS-SPEC 4.3, offline recorded mode): constants this module refuses to lower ----------------------
THRESHOLDS = MappingProxyType({"structural": 1.0, "outcome": 1.0, "diff": 1.0, "undo": 1.0,
                               "wrong_drafts": 0, "unstated_or_invented": 0, "pre_approval_writes": 0})
LIVE_BARS = MappingProxyType({"outcome": 0.90, "diff": 0.90, "wrong_drafts_per_run": 0, "unstated_or_invented": 0,  # documented for card 19,
                              "pre_approval_writes": 0, "undo": 1.0, "cpu_fallback_outcome": 0.70})  # never evaluated here

# assertion codes: each result lists the codes it failed with
CODES = ("wrong-skill", "wrong-disposition", "wrong-reply", "reply-queue", "write-before-yes", "apply-failed", "wrong-diff",
         "edit-undeclared", "content-rule", "unstated-claim", "bad-picture", "undo-not-identical", "residue-undeclared",
         "duplicate-effect", "privacy-leak", "audit-missing", "harness-error", "request-leak", "undo-order", "missing-undo-golden")
OUTCOME_CODES = {"wrong-skill", "wrong-disposition", "wrong-reply", "reply-queue"}
DIFF_CODES = {"wrong-diff", "edit-undeclared", "apply-failed"}
UNDO_CODES = {"undo-not-identical", "residue-undeclared", "missing-undo-golden"}
CONTENT_CODES = {"content-rule", "unstated-claim", "bad-picture"}
STRUCTURAL_CODES = {"request-leak", "undo-order", "write-before-yes", "duplicate-effect", "privacy-leak", "audit-missing", "harness-error"} | UNDO_CODES | CONTENT_CODES

STRANGER = "stranger-acceptance@example.invalid"  # AV1109-18: a sender who is not an owner (the Conversation ignores it before any model call)
ROW_KEYS = {"id", "schema_version", "tag", "skill", "skill_version", "texts", "replies", "expect", "setup", "seed", "photos", "house_render", "offsets", "senders"}
SELFTEST_ONLY = {"fault", "must_fail"}
EXPECT_KEYS = {"skills", "dispositions", "reply_contains", "reply_not_contains", "expected", "undo", "picture", "approval"}
PICTURE_KEYS = {"kind", "type", "size", "house"}
EXPECTED_KEYS = {"schema_version", "diff", "files", "assets", "residue"}
FAULTS = ("write-on-prepare", "undo-leaves", "undo-stale-generated", "undo-dirty", "leak-stage")  # self-test only: a path that writes unasked / an undo that leaves a trace, a stale site file or an untracked file / a stage line that carries the owner's words
EDITOR_FAULTS = FAULTS[:4]  # the testkit's own editor faults, reused unchanged
ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
FIXTURE_PATH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,200}\.(?:jpg|jpeg|png)")
SHA_RE = re.compile(r"[0-9a-f]{64}")
ASSET_DIR = "storefront-mockup/assets/products/"
PHOTO_NAME_RE = re.compile(r"photo-([0-9a-f]{16})\.(jpg|png)")
MONEY_RE = re.compile(r"[$€£]\s*\d|\b\d+(?:\.\d\d)?\s*(?:dollars?|bucks|usd)\b|\bper\s+(?:lb|pound|oz|ounce|kg|dozen)\b", re.I)
SIZE_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:oz|ounces?|lbs?|pounds?|kg|grams?|g|ml|l|litres?|liters?|inch(?:es)?|cm|mm)\b", re.I)
PRICE_PERMITTED = ("specials.add", "specials.edit")  # the deal line of a special is the one place a price may appear (docs/hass/skills/specials.md)


class InputError(ValueError):
    """A malformed row, fixture, flag or setup: exit 2. The message never holds owner text or a path."""


# -- rows ---------------------------------------------------------------------------------------------------------
def _bad(row_id, why):
    raise InputError(f"row {row_id}: {why}")


def _safe_rel(value, pattern=None):
    return (isinstance(value, str) and bool(value) and not value.startswith(("/", "~")) and "\\" not in value and ".." not in Path(value).parts
            and "\x00" not in value and (pattern is None or pattern.fullmatch(value) is not None))


def validate_row(row, *, selftest=False):
    """The closed row schema, version 1. Raises InputError; returns the row."""
    if not isinstance(row, dict): raise InputError("a row must be a JSON object")
    rid = row.get("id")
    if not (isinstance(rid, str) and ID_RE.fullmatch(rid)): raise InputError("a row id is a safe name: [a-z0-9][a-z0-9_-]*")
    extra = set(row) - ROW_KEYS - (SELFTEST_ONLY if selftest else set())
    if extra: _bad(rid, "unknown field " + ", ".join(sorted(map(str, extra))) + (" (fault and must_fail exist only in the self-test fixtures)" if extra & SELFTEST_ONLY else ""))
    for k in ("schema_version", "tag", "skill", "skill_version", "texts", "replies", "expect"):
        if k not in row: _bad(rid, f"missing {k}")
    if row["schema_version"] != SCHEMA_VERSION or type(row["schema_version"]) is not int: _bad(rid, f"stale schema_version (this engine reads {SCHEMA_VERSION})")
    if row["tag"] not in TAGS: _bad(rid, "tag must be one of " + ", ".join(TAGS))
    skill, version = row["skill"], row["skill_version"]
    if not (isinstance(skill, str) and (skill == "none" or re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", skill))): _bad(rid, "skill is a skill name or none")
    if (skill == "none") != (version is None) or (version is not None and (type(version) is not int or version < 1)): _bad(rid, "skill_version is a positive integer, or null for skill none")
    texts, replies = row["texts"], row["replies"]
    if not (isinstance(texts, list) and 1 <= len(texts) <= 12 and all(isinstance(t, str) and len(t) <= 4000 for t in texts)): _bad(rid, "texts is 1 to 12 strings")
    if not (isinstance(replies, list) and len(replies) <= 30 and all(isinstance(r, dict) for r in replies)): _bad(rid, "replies is a list of recorded reply objects")
    photos = row.get("photos", [])
    if not (isinstance(photos, list) and len(photos) <= len(texts) and all(isinstance(p, dict) and set(p) == {"turn", "fixture"} for p in photos)): _bad(rid, "photos is a list of {turn, fixture}")
    turns = [p["turn"] for p in photos]
    if not all(type(t) is int and 0 <= t < len(texts) for t in turns) or len(set(turns)) != len(turns): _bad(rid, "photo turn must be a distinct owner-turn index")
    if not all(_safe_rel(p["fixture"], FIXTURE_PATH_RE) for p in photos): _bad(rid, "photo fixture must be a safe relative .jpg or .png path")
    if any(not t.strip() and i not in turns for i, t in enumerate(texts)): _bad(rid, "an empty text is only allowed for a photo turn")
    if "house_render" in row and type(row["house_render"]) is not bool: _bad(rid, "house_render is true or false")
    senders = row.get("senders")
    if senders is not None and not (isinstance(senders, list) and len(senders) == len(texts) and all(s in ("owner", "stranger") for s in senders)): _bad(rid, "senders is owner or stranger, one per text")
    offsets = row.get("offsets")
    if offsets is not None and not (isinstance(offsets, list) and len(offsets) == len(texts) and all(type(o) is int and 0 <= o <= 2880 for o in offsets)): _bad(rid, "offsets is one bounded minute count (0-2880) per text")
    setup, seed = row.get("setup"), row.get("seed")
    if setup is not None and not (isinstance(setup, list) and setup and all(isinstance(o, dict) and set(o) == {"op", "args"} for o in setup)): _bad(rid, "setup is a list of {op, args}")
    if seed is not None and not (isinstance(seed, dict) and all(k in ("products", "makers", "community", "store") and isinstance(v, dict) for k, v in seed.items())): _bad(rid, "seed is {products|makers|community|store: {top-level key: value}}")
    _validate_expect(rid, row, len(texts))
    if row.get("fault") not in (None, *FAULTS): _bad(rid, "unknown fault")
    if "must_fail" in row and row["must_fail"] not in CODES: _bad(rid, "must_fail is an assertion code")
    return row


def _validate_expect(rid, row, n_turns):
    expect = row["expect"]
    if not isinstance(expect, dict): _bad(rid, "expect is an object")
    if set(expect) - EXPECT_KEYS: _bad(rid, "unknown expect field " + ", ".join(sorted(set(expect) - EXPECT_KEYS)))
    for k in ("skills", "dispositions"):
        if k not in expect: _bad(rid, f"expect.{k} is required")
    skills, disp = expect["skills"], expect["dispositions"]
    if not (isinstance(skills, list) and skills and all(isinstance(s, str) for s in skills)): _bad(rid, "expect.skills lists the allowed skills (none for a command or question path)")
    if row["skill"] not in skills: _bad(rid, "skill must be one of expect.skills")
    if not (isinstance(disp, list) and len(disp) == n_turns and all(isinstance(d, str) and d for d in disp)): _bad(rid, "expect.dispositions is one disposition per text")
    for k in ("reply_contains", "reply_not_contains"):
        if k in expect and not (isinstance(expect[k], list) and all(isinstance(s, str) and s for s in expect[k])): _bad(rid, f"expect.{k} is a list of fragments")
    proposed = disp[-1] == "proposed"
    ref = expect.get("expected")
    if expect.get("approval", "paused") != "paused": _bad(rid, "expect.approval is paused (the one approval refusal the engine knows)")
    if expect.get("approval") == "paused" and (not proposed or ref is not None or expect.get("undo")): _bad(rid, "a paused-approval row ends in a proposal, has no expected file and no undo")
    if proposed and expect.get("approval") is None and ref != f"{rid}.json": _bad(rid, "a proposed row names its expected file: expected is <id>.json")
    if not proposed and ref is not None: _bad(rid, "only a proposed row has an expected file")
    if "undo" in expect and type(expect["undo"]) is not bool: _bad(rid, "expect.undo is true or false")
    if expect.get("undo") and not proposed: _bad(rid, "undo needs a proposed row")
    if "picture" in expect:
        pic = expect["picture"]
        if not (isinstance(pic, dict) and set(pic) <= PICTURE_KEYS and pic.get("kind", "product") in ("product", "hero") and pic.get("house", "off") in ("off", "pass", "warn")
                and pic.get("type", "jpeg") in ("jpeg", "png") and (pic.get("size") is None or (isinstance(pic["size"], list) and len(pic["size"]) == 2 and all(type(x) is int for x in pic["size"])))):
            _bad(rid, "expect.picture is {kind: product|hero, type: jpeg|png, size: [w, h], house: off|pass|warn}")
        if pic.get("house") == "warn" and not expect.get("reply_contains"): _bad(rid, "a warned picture names the warning the owner must see (reply_contains)")
        if not row.get("photos"): _bad(rid, "expect.picture needs a photo")


def load_rows(path, *, selftest=False):
    """Every row of a JSONL file, validated; an empty corpus, a duplicate id or a bad line is an InputError."""
    try: lines = Path(path).read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError): raise InputError("the rows file cannot be read") from None
    rows = []
    for n, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"): continue
        try: row = json.loads(line)
        except ValueError: raise InputError(f"line {n}: not JSON") from None
        rows.append(validate_row(row, selftest=selftest))
    if not rows: raise InputError("the corpus has no rows")
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)): raise InputError("duplicate row id")
    return rows


def expected_path(fixture_root, row_id):
    """expected/<id>.json inside the fixture root; refuses a symlinked fixture root, expected folder or file."""
    root = Path(fixture_root)
    folder = root / "expected"
    for p in (root, folder):
        if p.is_symlink(): raise InputError("a symlinked fixture folder is refused")
    return folder / f"{row_id}.json"


def load_expected(fixture_root, row):
    path = expected_path(fixture_root, row["id"])
    if path.is_symlink() or not path.is_file(): raise InputError(f"row {row['id']}: expected/{row['id']}.json is missing (record it with --record and check it by hand)")
    try: data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError): raise InputError(f"row {row['id']}: expected file is not JSON") from None
    ok = (isinstance(data, dict) and set(data) == EXPECTED_KEYS and type(data["schema_version"]) is int and data["schema_version"] == SCHEMA_VERSION and isinstance(data["diff"], list)
          and all(isinstance(e, dict) and isinstance(e.get("file"), str) and isinstance(e.get("path"), str) for e in data["diff"])
          and isinstance(data["files"], list) and all(_safe_rel(f) for f in data["files"])
          and isinstance(data["assets"], dict) and all(_safe_rel(k) and isinstance(v, str) and SHA_RE.fullmatch(v) for k, v in data["assets"].items())
          and isinstance(data["residue"], dict) and set(data["residue"]) == {"content", "assets"} and isinstance(data["residue"]["content"], list)
          and all(isinstance(e, dict) and isinstance(e.get("file"), str) and isinstance(e.get("path"), str) for e in data["residue"]["content"])
          and isinstance(data["residue"]["assets"], dict) and all(_safe_rel(k) and isinstance(v, str) and SHA_RE.fullmatch(v) for k, v in data["residue"]["assets"].items()))
    if not ok: raise InputError(f"row {row['id']}: expected file does not follow expected schema {SCHEMA_VERSION}")
    if _residue_keys(data["residue"]["content"]) is None: raise InputError(f"row {row['id']}: expected residue names the same file and path twice")
    return data


# -- results ------------------------------------------------------------------------------------------------------
class Result:
    """What one row did. Only the id, observed skills, dispositions, assertion codes and counts: never owner text, a sender or a path."""

    def __init__(self, row_id):
        self.id, self.codes, self.skills, self.dispositions, self.facts, self.row, self.recorded = row_id, [], [], [], {}, {}, None

    def fail(self, code):
        assert code in CODES, code
        if code not in self.codes: self.codes.append(code)

    @property
    def ok(self): return not self.codes

    def line(self):
        return f"{'PASS' if self.ok else 'FAIL'}  {self.id:<32} skill={','.join(self.skills) or 'none'} disposition={','.join(self.dispositions)}" + ("" if self.ok else "  [" + "] [".join(self.codes) + "]")


# -- the scratch world --------------------------------------------------------------------------------------------
class ReplyQueueError(RuntimeError):
    """The model was called when no recorded reply was left."""


class RecordedInterpreter:
    """Plays the next recorded reply for each model call: only when Conversation actually calls the interpreter (a command or a
    cheap answer never does). Replies are never keyed by the message text and never turned into ops: the dispatcher reads them raw."""

    last_backend, last_error = "recorded", ""  # the conversation's own audit row: backend, no error

    def __init__(self, replies):
        self.queue, self.calls = [copy.deepcopy(r) for r in replies], 0

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        self.calls += 1
        if not self.queue: raise ReplyQueueError("no recorded reply left")
        return self.queue.pop(0)


class FixturePhotos:
    """The photo source: the provider id of a message maps to the fixture bytes. Conversation._photo does the rest."""

    def __init__(self): self.by_id = {}

    def fetch(self, provider_id, n):
        if provider_id not in self.by_id: raise OSError("no fixture for that message")
        return [self.by_id[provider_id]]


def _sha(data): return hashlib.sha256(data).hexdigest()


def _git(cwd, *args, check=True):
    from hass.skills import testkit
    return testkit._git(cwd, *args, check=check)


class Session:
    """A throwaway writer worktree + state dir + the real Conversation with a recorded interpreter. Always ``close()`` it."""

    def __init__(self, row, registry, fixture_root, *, selftest=False):
        self.row, self.fixture_root, self.selftest = row, Path(fixture_root), selftest
        self.now = START
        self._clock = lambda: self.now
        self.n, self.owned, self.repo, self.conv, self.photos = 0, [], None, None, None
        self.stage_path, self.observed = None, []
        self.canaries = []
        try: self._open(registry)
        except BaseException:  # a seed or setup that does not validate must not leave the scratch repo behind
            self.close()
            raise

    # -- setup ---------------------------------------------------------------------------------------------------
    def _open(self, registry):
        from hass import conversation, editor, stagelog
        from hass.fixture_chat import FixtureAdapter
        from hass.skills import testkit
        from hass.tests.test_editor import WriterRepo
        row = self.row
        with testkit._clock_scope(self._clock):
            self.repo = WriterRepo()
            self.wt = self.repo.wt
            self.media_root = tempfile.mkdtemp(prefix="acceptance-media-")
            tmp = tempfile.mkdtemp(prefix="acceptance-stage-")
            self.owned += [self.media_root, tmp]
            self.stage_path = Path(tmp) / "stages.jsonl"
            self._own_assets()  # copied into the writer: nothing is ever written through the default asset symlink
            cfg = json.loads((self.repo.state / "config.json").read_text("utf-8"))
            settings = {"ownerSenders": [OWNER], "ownerChat": CHAT, "approvalTtlSeconds": TTL_SECONDS, "skills": {"mode": "both"},
                        "mediaRoot": self.media_root, "houseRender": row.get("house_render") is True}
            # Synthetic empty RSVP store: undo must retain the real fail-closed guest-count gate.
            guest_db = self.repo.state / "guests.sqlite3"
            with sqlite3.connect(guest_db) as db:
                db.execute("CREATE TABLE rsvps (event_id TEXT, party_size INTEGER)")
            settings["guestCountsDb"] = str(guest_db)
            editor._write_json(self.repo.state / "config.json", {**cfg, "settings": settings})
            self.out = FixtureAdapter()
            if row.get("seed"): testkit.Scratch._seed(self, copy.deepcopy(row["seed"]))
            self.previewer = testkit.RecordingPreviewer()
            self.editor = testkit._fault_editor(testkit._clocked_editor(self), self, str(self.repo.state), row.get("fault") if row.get("fault") in EDITOR_FAULTS else None)
            if row.get("setup"): testkit.Scratch._setup(self, copy.deepcopy(row["setup"]))
            self.interp = RecordedInterpreter(row["replies"])
            self.photos = FixturePhotos() if row.get("photos") else None
            self.conv = conversation.Conversation(str(self.repo.state), self.editor, self.interp, self._clock, self.previewer, photos=self.photos,
                                                  skills=self._spied(registry))
            self.Inbound = conversation.Inbound
            if self.conv.dispatch is not None: self._patch_dispatch()
        self.stagelog = stagelog.StageLog(self.stage_path, clock=lambda: self.now.timestamp())
        self.base_head = _git(self.wt, "rev-parse", "HEAD").strip()
        self.baseline = self.snapshot()

    def _own_assets(self):
        site = REPO_ROOT / "storefront-mockup" / "assets"
        assets = self.wt / "storefront-mockup" / "assets"
        assets.unlink()
        (assets / "products").mkdir(parents=True)
        for entry in site.iterdir():
            if entry.name != "products": (assets / entry.name).symlink_to(entry)
        for entry in (site / "products").iterdir(): shutil.copyfile(entry, assets / "products" / entry.name)
        _git(self.wt, "add", "-A")
        _git(self.wt, "-c", "user.name=acceptance", "-c", "user.email=acceptance@example.invalid", "commit", "-q", "-m", "own assets/products folder")

    def _spied(self, registry):
        """The production registry with each skill's plan wrapped to note that it ran (the observed skill); read-only and backlog
        answers are noted through the dispatcher's own hooks. Behaviour is unchanged."""
        import dataclasses
        from functools import wraps
        from hass.skills.model import Registry
        seen = self.observed

        def spy(skill):
            original = skill.plan

            @wraps(original)
            def plan(slots, ctx):
                seen.append(skill.name)
                return original(slots, ctx)
            return dataclasses.replace(skill, plan=plan)
        return Registry(skills={n: spy(s) for n, s in registry.skills.items()})

    def _patch_dispatch(self):
        d, seen = self.conv.dispatch, self.observed
        read_only, backlog = d._read_only, d._backlog

        def ro(msg, now, req, skill, *a, **k):
            seen.append(skill.name)
            return read_only(msg, now, req, skill, *a, **k)

        def bl(*a, **k):
            seen.append("none")
            return backlog(*a, **k)
        d._read_only, d._backlog = ro, bl

    # -- observing -----------------------------------------------------------------------------------------------
    def snapshot(self):
        """Exact relative path -> sha256 of every content JSON, every generated site file and every file under assets/products
        (untracked ones too), plus HEAD and the porcelain status."""
        from hass.editor import GENERATED_PATHS
        wt, files = self.wt, {}
        for p in sorted((wt / "hass" / "content").glob("*.json")): files[p.relative_to(wt).as_posix()] = _sha(p.read_bytes())
        for rel in GENERATED_PATHS:
            p = wt / rel
            files[rel] = _sha(p.read_bytes()) if p.is_file() else "absent"
        assets = wt / ASSET_DIR
        for p in sorted(assets.rglob("*")):
            if p.is_symlink(): files[p.relative_to(wt).as_posix()] = "symlink:" + os.readlink(p)
            elif p.is_file(): files[p.relative_to(wt).as_posix()] = _sha(p.read_bytes())
        return {"files": files, "head": _git(self.wt, "rev-parse", "HEAD").strip(), "status": _git(self.wt, "status", "--porcelain").strip()}

    def counts(self):
        audit = self.conv.db.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='interpreter_audit'").fetchone()[0]
        return (len(self.drafts()), self.conv.db.execute("SELECT count(*) FROM outbox").fetchone()[0], len(self.out.sent),
                self.conv.db.execute("SELECT count(*) FROM interpreter_audit").fetchone()[0] if audit else 0, self.interp.calls)

    def drafts(self): return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    # -- saying --------------------------------------------------------------------------------------------------
    def say(self, text, *, photo=None, minutes=1, sender=OWNER):
        """One message through Conversation.handle + flush (the owner's unless ``sender`` says otherwise). Returns (Inbound, disposition, reply texts)."""
        from hass.skills import testkit
        self.n += 1
        self.now += timedelta(minutes=minutes)
        pid = f"acc-{self.n}"
        if photo is not None: self.photos.by_id[pid] = photo
        msg = self.Inbound(pid, CHAT, sender, text, False, "new", self.now.isoformat(), 1 if photo is not None else 0)
        with testkit._clock_scope(self._clock):
            self.stagelog("accepted", pid)
            calls = self.interp.calls
            disposition = self.conv.handle(msg)
            if self.interp.calls != calls: self.stagelog("interp-end", pid)
            self.stagelog("handled", pid, **({"text": text} if self.row.get("fault") == "leak-stage" else {}))  # the fault: a leaking log line
            before = len(self.out.sent)
            self.conv.flush(self.out)
        return msg, disposition, [r["text"] for r in self.out.sent[before:]]

    def replay(self, msg):
        """Deliver the same provider id again. Returns the disposition."""
        from hass.skills import testkit
        with testkit._clock_scope(self._clock):
            disposition = self.conv.handle(msg)
            self.conv.flush(self.out)
        return disposition

    def close(self):
        try:
            if self.conv is not None: self.conv.db.close()
        finally:
            try:
                if self.repo is not None: self.repo.cleanup()
            finally:
                for p in self.owned: shutil.rmtree(p, ignore_errors=True)


# -- the checks of one row ----------------------------------------------------------------------------------------
def _entries(files, new, old):
    return {p: h for p, h in new.items() if p.startswith(ASSET_DIR) and old.get(p) != h}


def _norm_entries(entries): return sorted(entries, key=lambda e: (e["file"], e["path"]))


def _subset(want, got):
    if isinstance(want, dict): return isinstance(got, dict) and all(k in got and _subset(v, got[k]) for k, v in want.items())
    return want == got


def _declared(skill_names, registry):
    from hass.skills import testkit
    out = []
    for n in skill_names:
        if n in registry.skills: out += testkit._declared_edits(registry.skills[n])
    return out


def _strings(value):
    if isinstance(value, str): yield value
    elif isinstance(value, dict):
        for v in value.values(): yield from _strings(v)
    elif isinstance(value, list):
        for v in value: yield from _strings(v)


def _field_of(path):
    m = re.search(r"(?:\]|\.)([A-Za-z_]+)$", path)
    return m.group(1) if m else path


def content_problems(entries, texts, skill_names, wt):
    """4.3 item 5: the applied content validates, each changed text is within TEXT_LIMITS, no price or size nobody said, no invented
    capacity or difficulty or sign-up. Owner text is a source of truth only for words he said."""
    from hass.content_model import TEXT_LIMITS, ContentError, load_and_validate
    problems = []
    try: load_and_validate(wt / "hass" / "content", wt / "storefront-mockup")
    except ContentError: problems.append("content no longer validates")
    said = "\n".join(texts).casefold()
    price_ok = any(n in PRICE_PERMITTED for n in skill_names)
    for e in entries:
        after = e.get("after")
        if after is None: continue
        field = _field_of(e["path"])
        for s in _strings(after):
            if MONEY_RE.search(s) and not (price_ok and "special" in e["path"].lower()): problems.append(f"a price in {field}")
            for m in SIZE_RE.finditer(s):
                if m.group(0).casefold() not in said: problems.append(f"a size nobody said in {field}")
        limits = TEXT_LIMITS.get(_kind_of(e), {})
        if isinstance(after, str) and field in limits and len(after) > limits[field]: problems.append(f"{field} is over its text limit")
        records = after if isinstance(after, dict) and "id" in after else {field: after}
        for key, value in records.items():
            if key == "capacity" and value is not None and str(value) not in re.findall(r"\d+", said): problems.append("a capacity nobody said")
            if key == "difficulty" and value is not None and str(value).casefold() not in said: problems.append("a difficulty nobody said")
            if key == "rsvpEnabled" and value is True and not re.search(r"rsvp|sign.?up|reserve|book", said): problems.append("sign-up turned on without being asked")
    return problems


def _kind_of(e):
    p = e["path"]
    return "product" if p.startswith("products") else "maker" if p.startswith("makers") else "event" if p.startswith("events") else "routeIdea" if p.startswith("routeIdeas") else "store" if e["file"].endswith("store.json") else "club"


def _exif_kind(tiff):
    """'orientation' for a well-formed TIFF/Exif block whose only tag is Orientation (0x0112), 'gps' when any IFD in its chain carries
    the GPSInfo pointer (0x8825), else 'other' (more tags, a next IFD, or a block that cannot be parsed: never trusted)."""
    order = {b"II": "little", b"MM": "big"}.get(bytes(tiff[:2]))
    if order is None or int.from_bytes(tiff[2:4], order) != 42 or len(tiff) < 8: return "other"
    off, seen, tags, nexts = int.from_bytes(tiff[4:8], order), set(), set(), []
    while off and off not in seen and len(seen) < 8:
        seen.add(off)
        if off + 2 > len(tiff): return "other"
        count = int.from_bytes(tiff[off:off + 2], order)
        end = off + 2 + 12 * count
        if end + 4 > len(tiff): return "other"
        tags |= {int.from_bytes(tiff[off + 2 + 12 * k:off + 4 + 12 * k], order) for k in range(count)}
        off = int.from_bytes(tiff[end:end + 4], order)
        nexts.append(off)
    if 0x8825 in tags: return "gps"
    return "orientation" if tags == {0x0112} and nexts == [0] else "other"


def _image_info(data):
    """(type, width, height, metadata problems) read from the bytes; no image library needed."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h, i, meta = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big"), 8, []
        while i + 8 <= len(data):
            n, kind = int.from_bytes(data[i:i + 4], "big"), data[i + 4:i + 8]
            if kind in (b"eXIf", b"tEXt", b"iTXt", b"zTXt"): meta.append(kind.decode("ascii"))
            if kind == b"eXIf" and _exif_kind(data[i + 8:i + 8 + n]) == "gps": meta.append("exif-gps")
            i += 12 + n
        return "png", w, h, meta
    if data[:2] == b"\xff\xd8":
        i, w, h, meta, framed = 2, 0, 0, [], False
        while i + 4 <= len(data):
            if data[i] != 0xFF: meta.append("segment-bad"); break  # not a marker: never trusted as clean
            while data[i + 1] == 0xFF and i + 4 <= len(data): i += 1  # legal FF fill bytes before a marker are not the marker
            if i + 4 > len(data) or data[i + 1] == 0xFF: meta.append("segment-bad"); break  # only fill left: truncated
            marker, n = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
            if marker == 0xDA: break  # entropy-coded data follows: stop before it
            if n < 2 or i + 2 + n > len(data): meta.append("segment-bad"); break  # impossible or truncated length
            if marker == 0xE1:  # APP1: only an Exif block holding nothing but the orientation tag is the plain-copy exception
                payload = data[i + 4:i + 2 + n]
                kind = _exif_kind(payload[6:]) if payload[:6] == b"Exif\0\0" else "other"
                meta.append("segment-e1" if kind == "orientation" else "exif-gps" if kind == "gps" else "segment-e1-other")
            elif marker in (0xED, 0xFE): meta.append(f"segment-{marker:02x}")
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC) and not framed:
                if n < 9: meta.append("segment-bad"); break
                h, w, framed = int.from_bytes(data[i + 5:i + 7], "big"), int.from_bytes(data[i + 7:i + 9], "big"), True
            i += 2 + n
        return "jpeg", w, h, meta
    return None, 0, 0, ["unreadable"]


def picture_problems(new_assets, wt, expect, house_render, originals):
    """4.3 item 5, pictures: name photo-<sha16>.<ext> from a photo the owner sent, type and size, no metadata, the house check.
    A home hero is exempt from the product-square rule; warned pictures are never reported clean."""
    spec = (expect or {}).get("picture") or {}
    kind, house = spec.get("kind", "product"), spec.get("house", "pass" if house_render else "off")
    problems = []
    for rel in sorted(new_assets):
        name = rel.rsplit("/", 1)[-1]
        m = PHOTO_NAME_RE.fullmatch(name)
        if m is None or m.group(1) not in {s[:16] for s in originals}: problems.append("picture name is not photo-<sha16> of a photo that was sent")
        data = (wt / rel).read_bytes()
        typ, w, h, meta = _image_info(data)
        if typ is None or (m is not None and (typ == "jpeg") != (m.group(2) == "jpg")): problems.append("picture type does not match its name")
        if spec.get("type") and typ != spec["type"]: problems.append("picture is not the expected type")
        if meta and (house_render or any(x != "segment-e1" for x in meta)): problems.append("picture carries metadata")  # a plain web copy may keep only its orientation tag
        if b"GPS" in data or "exif-gps" in meta: problems.append("picture carries location data")  # the ASCII word, or the numeric GPSInfo tag of a parsed Exif block
        if spec.get("size") and [w, h] != spec["size"]: problems.append("picture size is not the expected size")
        if house_render and kind == "product" and w != h: problems.append("a product picture is not square")
        if house_render and kind == "product" and house != "off":
            from hass import house_style
            try: verdict = house_style.check_image(data)["pass"]
            except house_style.PillowMissing: raise InputError("house_render rows need Pillow") from None
            if house == "pass" and not verdict: problems.append("picture does not pass the house check")
            if house == "warn" and verdict: problems.append("picture was expected to be warned but passes the house check")
    return problems


def _confined_file(root, rel):
    """The fixture file ``rel`` under ``root``: no symlink on the way, and it is a regular file. None otherwise."""
    cur = Path(root)
    for part in Path(rel).parts:
        cur = cur / part
        if cur.is_symlink(): return None
    return cur if cur.is_file() else None


def load_photos(row, fixture_root):
    out = {}
    for p in row.get("photos", []):
        path = _confined_file(fixture_root, p["fixture"])
        if path is None: raise InputError(f"row {row['id']}: a photo fixture is missing or symlinked")
        out[p["turn"]] = path.read_bytes()
    return out


STAGE_WORDS = re.compile(r"\b(?:recorded|accepted|handled|interp-end)\b")


def privacy_problems(sess, texts):
    """4.3 item 9: owner text, sender, chat or a path in interpreter_audit or the stage log. Both must really hold lines when the
    model was called; the scan covers the lines as stored (the stage names and the backend word are the log's own and are not scanned)."""
    db, found, audit = sess.conv.db, [], []
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='interpreter_audit'").fetchone():
        audit = [tuple(r) for r in db.execute("SELECT * FROM interpreter_audit")]
    stage_rows = []
    if sess.stage_path.is_file():
        for line in sess.stage_path.read_text("utf-8").splitlines(): stage_rows.append(json.loads(line))
    if sess.interp.calls and not audit: found.append("audit-missing")
    if not stage_rows: found.append("audit-missing")
    blob = STAGE_WORDS.sub(" ", (json.dumps(audit, default=str) + "\n" + "\n".join(json.dumps({k: v for k, v in r.items() if k != "stage"}) for r in stage_rows)).casefold())
    words = {w for t in texts for w in re.findall(r"[a-z0-9']{5,}", t.casefold())} - {"recorded", "accepted", "handled"}
    canaries = {t.casefold() for t in texts if len(t) >= 4} | words | {OWNER.casefold(), CHAT.casefold(), str(sess.wt).casefold(), str(sess.repo.state).casefold(), str(sess.media_root).casefold()}
    if any(c and c in blob for c in canaries): found.append("privacy-leak")
    return found


def run_row(row, *, fixture_root, registry=None, selftest=False, observe=False):
    """Run one validated row. ``observe`` (the recorder) skips only the comparison with expected/<id>.json and collects what
    happened in ``result.recorded``. Returns a Result."""
    if registry is None:
        from hass.skills import load_skills
        registry = load_skills()
    validate_row(row, selftest=selftest)
    if row.get("fault") and not selftest: raise InputError("fault injection exists only in the self-test fixtures")
    skill = registry.skills.get(row["skill"]) if row["skill"] != "none" else None
    if row["skill"] != "none" and (skill is None or skill.version != row["skill_version"]): raise InputError(f"row {row['id']}: stale skill or skill version")
    expected = None if observe or not row["expect"].get("expected") else load_expected(fixture_root, row)
    photos = load_photos(row, fixture_root)
    res = Result(row["id"])
    res.row = row
    sess = Session(row, registry, fixture_root, selftest=selftest)
    try: _drive(row, sess, registry, res, expected, photos, observe)
    except ReplyQueueError: res.fail("reply-queue")
    except InputError: raise
    except Exception:  # noqa: BLE001 - a crash is a row result, never a raw exception string
        res.fail("harness-error")
    finally: sess.close()
    return res


def _drive(row, sess, registry, res, expected, photos, observe):
    expect, texts = row["expect"], row["texts"]
    base = sess.baseline
    msgs, dispositions, replies = [], [], []

    def duplicate(msg):
        before_snap, before_counts = sess.snapshot(), sess.counts()
        if sess.replay(msg) != "duplicate" or sess.snapshot() != before_snap or sess.counts() != before_counts: res.fail("duplicate-effect")

    offsets = row.get("offsets") or [0] * len(texts)
    senders = row.get("senders") or ["owner"] * len(texts)
    for i, text in enumerate(texts):
        msg, disposition, out = sess.say(text, photo=photos.get(i), minutes=1 + offsets[i], sender=STRANGER if senders[i] == "stranger" else OWNER)
        msgs.append(msg), dispositions.append(disposition), replies.append(out)
        res.dispositions = list(dispositions)
        if sess.snapshot() != base:  # nothing may change before a yes
            res.fail("write-before-yes")
            return
        duplicate(msg)
    seen = sorted(set(sess.observed)) or ["none"]
    res.skills = seen
    if not set(seen) <= set(expect["skills"]) or (row["skill"] != "none" and dispositions[-1] == "proposed" and row["skill"] not in seen): res.fail("wrong-skill")
    if dispositions != expect["dispositions"]: res.fail("wrong-disposition")
    final = "\n".join(replies[-1])
    for want in expect.get("reply_contains", []):
        if want.lower() not in final.lower(): res.fail("wrong-reply")
    for want in expect.get("reply_not_contains", []):
        if want.lower() in final.lower(): res.fail("wrong-reply")
    if sess.interp.queue: res.fail("reply-queue")
    res.facts.update(turns=len(texts), model_calls=sess.interp.calls)
    drafts = sess.drafts()
    if dispositions[-1] == "proposed" and drafts and drafts[-1]["state"] == "proposed" and expect.get("approval") == "paused":
        _approve_paused(sess, res, base, duplicate)
    elif dispositions[-1] == "proposed" and drafts and drafts[-1]["state"] == "proposed":
        _approve_and_check(row, sess, registry, res, expected, observe, base, texts, duplicate, seen)
    for code in privacy_problems(sess, texts): res.fail(code)


def _approve_paused(sess, res, base, duplicate):
    """AV1109-18, a paused store: the draft was proposed under the current policy, and the real `yes <code>` is refused with no write: the tree
    is the start tree, the draft is still waiting, and the same provider id again changes nothing."""
    draft = sess.drafts()[-1]
    msg, disposition, _texts = sess.say(f"yes {draft['code']}")
    if disposition != "paused": res.fail("wrong-disposition")
    if sess.snapshot() != base: res.fail("write-before-yes")
    if {r["code"]: r["state"] for r in sess.drafts()}.get(draft["code"]) != "proposed": res.fail("apply-failed")
    duplicate(msg)
    res.facts["approval"] = disposition


def _approve_and_check(row, sess, registry, res, expected, observe, base, texts, duplicate, seen):
    from hass import claims
    from hass.editor import GENERATED_PATHS
    from hass.skills import testkit
    expect, wt = row["expect"], sess.wt
    draft = sess.drafts()[-1]
    out = sess.editor.prepare(json.loads(draft["ops_json"]))  # the same draft again: the claims gate over the joined texts, as the conversation applies it
    if out.get("result") == "ok" and claims.unstated(out["draft"], " ".join(texts), sess.conv._makers(), sess.conv._routes(), sess.conv._sources()): res.fail("unstated-claim")
    wrong = next(f"{i:04x}" for i in range(65536) if f"{i:04x}" not in {d["code"] for d in sess.drafts()})
    sess.say(f"yes {wrong}")  # a well-formed code that names no draft never approves
    if sess.snapshot() != base:
        res.fail("write-before-yes")
        return
    approve, _disposition, _texts = sess.say(f"yes {draft['code']}")
    after = sess.snapshot()
    duplicate(approve)
    if {r["code"]: r["state"] for r in sess.drafts()}.get(draft["code"]) not in ("applied", "verified") or after["head"] == base["head"]:
        res.fail("apply-failed")
        return
    files, diff = testkit.tree_diff(wt, sess.base_head)
    assets = _entries(files, after["files"], base["files"])
    chosen = [n for n in seen if n != "none"]
    declared = _declared(chosen, registry)
    for e in diff:
        if not testkit.declared_covers(declared, e["file"], e["path"]): res.fail("edit-undeclared")
    for f in files:
        if f not in GENERATED_PATHS and not f.startswith("hass/content/") and not testkit._declared_picture(declared, f): res.fail("edit-undeclared")
    if content_problems(diff, texts, chosen, wt): res.fail("content-rule")
    originals = {_sha(b) for b in (sess.photos.by_id.values() if sess.photos else [])}
    if picture_problems(assets, wt, expect, row.get("house_render") is True, originals): res.fail("bad-picture")
    res.facts.update(files=len(files), diff=len(diff), pictures=len(assets))
    if expected is not None and (_norm_entries(diff) != _norm_entries(expected["diff"]) or files != sorted(expected["files"]) or assets != expected["assets"]): res.fail("wrong-diff")
    residue = None
    if expect.get("undo") and files: residue = _undo(sess, registry, res, expected, observe, base, after, chosen, duplicate)
    if observe: res.recorded = {"schema_version": SCHEMA_VERSION, "diff": _norm_entries(diff), "files": files, "assets": assets, "residue": residue or {"content": [], "assets": {}}}


def _residue_keys(entries):
    """{(file, path): entry}, or None when two entries share a key (a pin names one leftover once, a leftover is one entry)."""
    keyed = {(e.get("file"), e.get("path")): e for e in entries}
    return keyed if len(keyed) == len(entries) else None


def residue_matches(leftover, left_assets, want):
    """The leftover after undo against the residue the row pins, one to one: the same unique (file, path) entries, each with every pinned
    before / after, and exactly the same picture files and hashes. A repeated key on either side never matches (two pins on one path
    must not cover a second, unpinned leftover). There is no whole-file exemption."""
    left, pins = _residue_keys(leftover), _residue_keys(want["content"])
    if left is None or pins is None or left_assets != want["assets"] or set(left) != set(pins): return False
    return all(_subset(w, left[k]) for k, w in pins.items())


def _undo(sess, registry, res, expected, observe, base, after, chosen, duplicate):
    """`undo` then its own `yes`: the tree equals the start except the exact residue the row pins. Returns the residue found."""
    from hass import sitegen
    from hass.content_model import ContentError, load_and_validate
    from hass.editor import GENERATED_PATHS
    from hass.skills import testkit
    wt = sess.wt
    msg, disposition, _t = sess.say("undo")
    if disposition != "proposed": res.fail("undo-not-identical"); return None
    if sess.snapshot() != after: res.fail("write-before-yes"); return None
    duplicate(msg)
    code = sess.drafts()[-1]["code"]
    ok, _d, _t2 = sess.say(f"yes {code}")
    done = sess.snapshot()
    duplicate(ok)
    if {r["code"]: r["state"] for r in sess.drafts()}.get(code) not in ("applied", "verified"): res.fail("undo-not-identical"); return None
    ufiles, leftover = testkit.tree_diff(wt, sess.base_head)
    leftover, left_assets = _norm_entries(leftover), _entries(ufiles, done["files"], base["files"])
    problems = []
    if done["status"]: problems.append("the worktree is not clean")
    if [f for f in ufiles if not (f.startswith("hass/content/") and f.endswith(".json")) and f not in GENERATED_PATHS and f not in left_assets]: problems.append("a file outside content, site and assets differs")
    if [p for p in base["files"] if p.startswith(ASSET_DIR) and p not in done["files"]]: problems.append("a starting picture file is gone")
    try:
        # Check the restored site on the same fixture day that rendered it, not the host's later day.
        with testkit._clock_scope(sess._clock):
            stale = sitegen.stale_paths(load_and_validate(wt / "hass" / "content", wt / "storefront-mockup"), wt)
    except ContentError: stale = ["content invalid"]
    if stale: problems.append("generated site files are stale")
    residue = bool(leftover or left_assets)
    declares = any(testkit._residue_declared(registry.skills[n]) for n in chosen if n in registry.skills)
    want = None if observe or expected is None else expected["residue"]
    pinned_residue = bool(want and (want["content"] or want["assets"]))
    if problems: res.fail("undo-not-identical")
    if chosen and not declares and (residue or pinned_residue): res.fail("residue-undeclared")  # the skill's Undo sentence says nothing stays
    elif want is not None and not residue_matches(leftover, left_assets, want): res.fail("undo-not-identical")
    res.facts["undo"] = "residue" if residue else "identical"
    return {"content": leftover, "assets": left_assets}


# -- persistent chain ---------------------------------------------------------------------------------------------
def load_chain(path, *, fixture_root):
    """Closed chain admission, before scratch. 1..24 contiguous chain-NN turns (mini chains are test fixtures).

    Unlike isolated rows, questions may continue the same request. expect.request pins the exact
    {skill, slots, asked_slot, calls, attachments} for questions; completed tasks must have no live
    request. Plan questions without a slot additionally pin their exact question. Each proposal
    requires undo:true and a forward golden. Existing inverse goldens are preflighted; missing
    inverses fail closed at the reverse boundary, before any undo delivery. Only the
    first turn may seed/setup/select house rendering. Normal row admission is unchanged.
    """
    try: lines = Path(path).read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError): raise InputError("the chain file cannot be read") from None
    rows = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"): continue
        try: row = json.loads(line)
        except ValueError: raise InputError("chain line is not JSON") from None
        if not isinstance(row, dict): raise InputError("chain row must be an object")
        expect = row.get("expect")
        if not isinstance(expect, dict): raise InputError("chain expect must be an object")
        ordinary = copy.deepcopy(row)
        request = ordinary["expect"].pop("request", None)
        ops = ordinary["expect"].pop("ops", None)
        if expect.get("dispositions") == ["proposed"]:
            if not (isinstance(ops, list) and ops and all(isinstance(o, dict) and set(o) == {"op", "args"}
                    and isinstance(o["op"], str) and isinstance(o["args"], dict) for o in ops)):
                raise InputError("chain proposal pins its full intended ops and targets")
        elif ops is not None: raise InputError("only a chain proposal pins ops")
        # First-row photos use global forward-turn indices; validate their closed shape here,
        # while reusing ordinary validation for all other fields.
        photos = ordinary.pop("photos", [])
        if (not isinstance(photos, list) or any(not isinstance(p, dict) or set(p) != {"turn", "fixture"}
                or type(p["turn"]) is not int or not 0 <= p["turn"] < 24 or not _safe_rel(p["fixture"], FIXTURE_PATH_RE) for p in photos)
                or len({p["turn"] for p in photos}) != len(photos)):
            raise InputError("chain photos are distinct global request indices and safe fixtures")
        turn_texts = ordinary.get("texts")
        if ordinary["expect"].get("picture") or (isinstance(turn_texts, list) and turn_texts == [""]):
            ordinary["photos"] = [{"turn": 0, "fixture": "photo.jpg"}]
        validate_row(ordinary)
        rid = f"chain-{len(rows) + 1:02d}"
        if row["id"] != rid or len(rows) >= 24: raise InputError("chain ids must be contiguous chain-01..chain-24")
        if row["tag"] != "turns" or len(row["texts"]) != 1: _bad(rid, "chain has one request text and tag turns")
        if rows and any(k in row for k in ("setup", "seed", "photos", "house_render")): _bad(rid, "chain setup belongs only to the first turn")
        if any(k in row for k in ("offsets", "senders")) or "approval" in expect: _bad(rid, "chain uses the monotonic owner clock and named approvals")
        question = expect["dispositions"] == ["question"]
        if question:
            fields = {"skill", "slots", "asked_slot", "calls", "attachments"}
            if isinstance(request, dict) and request.get("asked_slot") is None: fields.add("question")
            if not (isinstance(request, dict) and set(request) == fields
                    and isinstance(request["skill"], str) and isinstance(request["slots"], dict)
                    and (isinstance(request["asked_slot"], str) and request["asked_slot"]
                         or request["asked_slot"] is None and isinstance(request.get("question"), str) and request["question"])
                    and isinstance(request["calls"], list) and isinstance(request["attachments"], list)):
                _bad(rid, "a question pins its exact request fields and one asked slot or plan question")
        elif request is not None: _bad(rid, "only questions pin a live request")
        if expect["dispositions"] == ["proposed"]:
            if expect.get("undo") is not True: _bad(rid, "every chain proposal must be undone")
            for key in (rid, rid.replace("chain-", "chain-undo-")):
                if key != rid and not os.path.lexists(expected_path(fixture_root, key)): continue
                golden = load_expected(fixture_root, {"id": key})
                for entry in golden["residue"]["content"]:
                    if not {"file", "path", "after"} <= set(entry) or set(entry) - {"file", "path", "before", "after"}: _bad(rid, "chain residue pins exact before and after")
        load_photos(row, fixture_root)
        rows.append(row)
    if not rows: raise InputError("the chain has no rows")
    if any(p["turn"] >= len(rows) for p in rows[0].get("photos", [])): raise InputError("chain photo turn is outside the chain")
    if rows[-1]["expect"]["dispositions"] == ["question"]: raise InputError("chain ends with an unfinished request")
    return rows


def _chain_request(sess):
    from hass.skills.openreq import OpenRequests
    store = OpenRequests(sess.conv.db)
    if not store.exists(): return None
    rows = sess.conv.db.execute("SELECT * FROM open_requests WHERE state IN ('open','drafted')").fetchall()
    if len(rows) > 1: raise AssertionError("multiple live requests")
    return store.get(CHAT, sess.now) if rows else None


def _chain_boundary(sess, res, expected=None, previous=None):
    req = _chain_request(sess)
    if expected is None:
        live = sess.conv.requests.exists() and sess.conv.db.execute("SELECT 1 FROM open_requests WHERE state IN ('open','drafted')").fetchone()
        if req is not None or live: res.fail("request-leak")
        if any(d["state"] == "proposed" for d in sess.drafts()): res.fail("request-leak")
    elif req is None or any(req.get(k) != v for k, v in expected.items()): res.fail("request-leak")
    if previous is not None and (req is None or req["request_id"] != previous): res.fail("request-leak")
    return req["request_id"] if req else None


def _chain_delta(sess, res, base, golden):
    from hass.skills import testkit
    after = sess.snapshot()
    files, diff = testkit.tree_diff(sess.wt, base["head"])
    assets = _entries(files, after["files"], base["files"])
    if (_norm_entries(diff) != _norm_entries(golden["diff"]) or files != sorted(golden["files"])
            or assets != golden["assets"]): res.fail("wrong-diff")
    if after["status"]: res.fail("undo-not-identical")


def _chain_final(sess, res, baseline, initial_head, golden, chosen, registry):
    from hass import sitegen
    from hass.content_model import load_and_validate
    from hass.editor import GENERATED_PATHS
    from hass.skills import testkit
    files, diff = testkit.tree_diff(sess.wt, initial_head)
    done = sess.snapshot()
    assets = _entries(files, done["files"], baseline["files"])
    want = golden["residue"]
    # Chains require equality, not the isolated engine's intentionally partial residue pins.
    if _norm_entries(diff) != _norm_entries(want["content"]) or assets != want["assets"]: res.fail("residue-undeclared")
    if (diff or assets) and not any(testkit._residue_declared(registry.skills[n]) for n in chosen): res.fail("residue-undeclared")
    if (done["status"] or any(f not in GENERATED_PATHS and not f.startswith("hass/content/") and f not in assets for f in files)
            or any(done["files"].get(p) != h for p, h in baseline["files"].items() if p.startswith(ASSET_DIR))):
        res.fail("undo-not-identical")
    if sitegen.stale_paths(load_and_validate(sess.wt / "hass/content", sess.wt / "storefront-mockup"), sess.wt): res.fail("undo-not-identical")
    # Only newly added hidden/cancelled records are public content residue; never an old field edit.
    for e in diff:
        after = e.get("after")
        kind = _kind_of(e)
        valid = (not e.get("before") and isinstance(after, dict) and (
            kind == "product" and after.get("status") == "hidden" and "available" not in after and "available_on" not in after
            or kind == "maker" and after.get("hidden") is True
            or kind == "event" and after.get("status") == "cancelled"))
        if not valid: res.fail("residue-undeclared")
    # No content values, prose, senders, absolute paths or runtime change ids in the public result.
    res.facts["residue"] = {"content": [{"file": e["file"], "path": e["path"], "sha256": _sha(json.dumps(e["after"], sort_keys=True).encode())} for e in diff], "assets": assets}


def run_chain(path, *, fixture_root=None, registry=None):
    """One real session, row-relative approvals, then a strict stack of named original undos.

    Returns Results in forward then reverse order; final facts carry distinct requests/controls/
    deliveries (duplicates included). No recorder or live path, and no immediate per-row undo.
    """
    from hass.skills import load_skills
    root = Path(fixture_root) if fixture_root is not None else Path(path).parent
    rows = load_chain(path, fixture_root=root)
    registry = registry if registry is not None else load_skills()
    for row in rows:
        skill = registry.skills.get(row["skill"])
        if row["skill"] != "none" and (skill is None or skill.version != row["skill_version"]): _bad(row["id"], "stale skill or skill version")
    seed = copy.deepcopy(rows[0])
    seed["replies"] = [r for row in rows for r in row["replies"]]
    sess = Session(seed, registry, root)
    results, stack, originals, inverses, chosen = [], [], [], [], set()
    counts = {"requests": 0, "controls": 0, "deliveries": 0}
    texts, task_texts, previous = [], [], None
    initial_head, baseline = sess.base_head, sess.baseline
    res = Result("chain-01")
    try:
        def duplicate(msg):
            before, c = sess.snapshot(), sess.counts()
            counts["controls"] += 1
            counts["deliveries"] += 1
            if sess.replay(msg) != "duplicate" or sess.snapshot() != before or sess.counts() != c: res.fail("duplicate-effect")

        # Inherited approval checks call say directly, so count every real delivery at this boundary.
        say = sess.say
        def counted(text, **kw):
            counts["deliveries"] += 1
            counts["controls"] += 1
            texts.append(text)
            return say(text, **kw)
        sess.say = counted
        photos = load_photos(rows[0], root)
        for index, row in enumerate(rows):
            res = Result(row["id"])
            results.append(res)
            res.row = row
            sess.observed.clear()
            base, ndrafts = sess.snapshot(), len(sess.drafts())
            task_texts += row["texts"]
            counts["requests"] += 1
            msg, disp, out = sess.say(row["texts"][0], photo=photos.get(index))
            counts["controls"] -= 1
            duplicate(msg)
            res.skills = sorted(set(sess.observed)) or ["none"]
            res.dispositions = [disp]
            if sess.snapshot() != base: res.fail("write-before-yes")
            expect = row["expect"]
            if [disp] != expect["dispositions"]: res.fail("wrong-disposition")
            if not set(res.skills) <= set(expect["skills"]): res.fail("wrong-skill")
            reply = "\n".join(out).lower()
            if any(w.lower() not in reply for w in expect.get("reply_contains", [])) or any(w.lower() in reply for w in expect.get("reply_not_contains", [])): res.fail("wrong-reply")
            req = _chain_request(sess)
            if previous is not None and (req is not None and req["request_id"] != previous
                                         or req is None and disp in ("question", "proposed")): res.fail("request-leak")
            if disp == "proposed":
                if len(sess.drafts()) != ndrafts + 1: res.fail("apply-failed")
                else:
                    draft = sess.drafts()[-1]
                    if json.loads(draft["ops_json"]) != expect["ops"]: res.fail("wrong-diff")
                    if row["skill"] not in res.skills: res.fail("wrong-skill")
                    golden = load_expected(root, row)
                    # Reuse the complete inherited claims/content/picture/declared-edit/approval checks
                    # relative to the current approved HEAD, without its immediate undo.
                    check_row = copy.deepcopy(row)
                    check_row["expect"]["undo"] = False
                    check_row["house_render"] = seed.get("house_render", False)
                    sess.base_head = base["head"]
                    _approve_and_check(check_row, sess, registry, res, golden, False, base, task_texts, duplicate, res.skills)
                    if sess.snapshot()["status"]: res.fail("apply-failed")
                    stack.append((row, draft))
                    originals.append(draft["change_id"])
                    chosen.update(n for n in res.skills if n in registry.skills)
            elif len(sess.drafts()) != ndrafts: res.fail("apply-failed")
            previous = _chain_boundary(sess, res, expect.get("request"), previous if disp == "question" else None)
            if disp != "question": task_texts = []
            for code in privacy_problems(sess, texts): res.fail(code)
            if not res.ok: return results
        if sess.interp.queue:
            res.fail("reply-queue")
            return results
        missing = [row["id"].replace("chain-", "chain-undo-") for row, _draft in reversed(stack)
                   if not os.path.lexists(expected_path(root, row["id"].replace("chain-", "chain-undo-")))]
        if missing:
            res = Result(missing[0])
            res.fail("missing-undo-golden")
            results.append(res)
            return results
        while stack:
            row, original = stack.pop()
            res = Result(row["id"].replace("chain-", "chain-undo-"))
            results.append(res)
            base, ndrafts = sess.snapshot(), len(sess.drafts())
            msg, disp, _ = sess.say(f"undo {original['code']}")
            res.dispositions = [disp]
            if disp != "proposed" or len(sess.drafts()) != ndrafts + 1:
                res.fail("undo-not-identical")
                return results
            draft = sess.drafts()[-1]
            ops = json.loads(draft["ops_json"])
            if ops != [{"op": "history.revert", "args": {"changeId": original["change_id"]}}]:
                res.fail("undo-order")
                return results
            if sess.snapshot() != base: res.fail("write-before-yes")
            duplicate(msg)
            wrong = next(c for c in ("ffff", "eeee", "dddd") if c not in {d["code"] for d in sess.drafts()})
            sess.say(f"yes {wrong}")
            if sess.snapshot() != base: res.fail("write-before-yes")
            approved, disp, _ = sess.say(f"yes {draft['code']}")
            duplicate(approved)
            if sess.drafts()[-1]["state"] not in ("applied", "verified") or sess.snapshot()["head"] == base["head"]: res.fail("undo-not-identical")
            change = sess.editor.show(original["change_id"]).get("change", {})
            if change.get("revertedBy") != draft["change_id"]: res.fail("undo-order")
            inverses.append(draft["change_id"])
            golden = load_expected(root, {"id": res.id})
            _chain_delta(sess, res, base, golden)
            _chain_boundary(sess, res)
            for code in privacy_problems(sess, texts): res.fail(code)
            if not stack: _chain_final(sess, res, baseline, initial_head, golden, chosen, registry)
            if not res.ok: return results
        if len(set(originals)) != len(originals) or len(set(inverses)) != len(originals) or set(originals) & set(inverses): res.fail("undo-order")
        if sess.interp.queue: res.fail("reply-queue")
        if not originals:
            empty = {"residue": {"content": [], "assets": {}}}
            _chain_final(sess, res, baseline, initial_head, empty, chosen, registry)
    except ReplyQueueError: res.fail("reply-queue")
    except InputError: raise
    except Exception: res.fail("harness-error")
    finally:
        res.facts.update(counts, originals=len(originals), inverses=len(inverses))
        sess.close()
    return results


# -- running files ------------------------------------------------------------------------------------------------
def _refuse_policy(thresholds):
    if thresholds is not None and dict(thresholds) != dict(THRESHOLDS): raise InputError("the acceptance thresholds are constants and cannot be changed")


def run_rows(path, *, fixture_root=None, registry=None, selftest=False, thresholds=None, only=None):
    """Load and validate every row (and every expected file) first, then run them. Returns the Results in row order."""
    _refuse_policy(thresholds)
    path = Path(path)
    fixture_root = Path(fixture_root) if fixture_root is not None else path.parent
    rows = load_rows(path, selftest=selftest)
    if registry is None:
        from hass.skills import load_skills
        registry = load_skills()
    for row in rows:  # everything that can be refused is refused before the first scratch repo
        skill = registry.skills.get(row["skill"]) if row["skill"] != "none" else None
        if row["skill"] != "none" and (skill is None or skill.version != row["skill_version"]): raise InputError(f"row {row['id']}: stale skill or skill version")
        if row["expect"].get("expected"): load_expected(fixture_root, row)
        load_photos(row, fixture_root)
    return [run_row(r, fixture_root=fixture_root, registry=registry, selftest=selftest) for r in rows if not only or r["id"] in only]


def summarize(results):
    """The measures against THRESHOLDS. ``met`` is true only when every one is met; ``partial`` is always true here: no offline run is the full-site acceptance."""
    n = len(results) or 1
    bad = lambda codes: sum(bool(set(r.codes) & codes) for r in results)  # noqa: E731
    proposed = [r for r in results if "proposed" in r.dispositions] or []
    undo = [r for r in results if "undo" in r.facts]
    m = {"structural": 1 - bad(STRUCTURAL_CODES) / n, "outcome": 1 - bad(OUTCOME_CODES) / n,
         "diff": 1 - (bad(DIFF_CODES) / len(proposed) if proposed else 0), "undo": 1 - (bad(UNDO_CODES) / len(undo) if undo else 0),
         "wrong_drafts": sum("wrong-disposition" in r.codes and "proposed" in r.dispositions for r in results),
         "unstated_or_invented": sum(bool({"unstated-claim", "content-rule"} & set(r.codes)) for r in results),
         "pre_approval_writes": sum("write-before-yes" in r.codes for r in results)}
    return {"rows": len(results), "measures": m, "met": all(m[k] >= v if isinstance(v, float) else m[k] <= v for k, v in THRESHOLDS.items()), "partial": True}


# -- record --------------------------------------------------------------------------------------------------------
def record_row(row_id, *, rows_path, fixture_root, registry=None, selftest=False):
    """Observe an actual scratch approval and undo of one row and write ONLY its missing expected/<id>.json (exclusive, no symlink
    followed). Never overwrites, never edits messages.jsonl. Returns the candidate text for a person to check: it is not evidence
    that the row is correct."""
    rows = load_rows(rows_path, selftest=selftest)
    row = next((r for r in rows if r["id"] == row_id), None)
    if row is None: raise InputError("no such row")
    if not row["expect"].get("expected"): raise InputError("this row does not propose a change, so it has no expected file")
    root = Path(fixture_root)
    path = expected_path(root, row_id)
    if root.resolve() not in path.resolve().parents or path.is_symlink() or os.path.lexists(path): raise InputError("expected/<id>.json already exists (or is unsafe): it is never overwritten")
    if registry is None:
        from hass.skills import load_skills
        registry = load_skills()
    res = run_row(row, fixture_root=root, registry=registry, selftest=selftest, observe=True)
    if res.codes or res.recorded is None: raise InputError("the row failed on its own assertions (" + ", ".join(res.codes) + "): nothing was recorded")
    text = json.dumps(res.recorded, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    folder = path.parent
    if folder.is_symlink(): raise InputError("a symlinked expected folder is refused")
    folder.mkdir(exist_ok=True)
    try: fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    except OSError: raise InputError("expected/<id>.json already exists (or is unsafe): it is never overwritten") from None
    with os.fdopen(fd, "w", encoding="utf-8") as f: f.write(text)
    return text


# -- CLI -----------------------------------------------------------------------------------------------------------
def judge_selftest(results, rows):
    """A row without must_fail has to pass; a row with must_fail has to fail with exactly that code. The counts are checked here, not by eye."""
    if len(rows) != SELFTEST_ROWS_N or sum("must_fail" in r for r in rows) != SELFTEST_FAULTS_N: raise InputError(f"the self-test is {SELFTEST_ROWS_N} rows, {SELFTEST_FAULTS_N} of them faults")
    out = []
    for r in results:
        want = r.row.get("must_fail")
        out.append((r, r.ok if want is None else (not r.ok and r.codes == [want]), want))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hass/skills/acceptance_run.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False)
    ap.add_argument("--chain", metavar="FILE")
    ap.add_argument("--rows", metavar="FILE")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--record", metavar="ROW")

    argv = list(sys.argv[1:] if argv is None else argv)
    if any(re.search(r"thresh|toler|lower|relax|allow|skip|ignore|min|loose|weak", a, re.I) for a in argv if a.startswith("-")):
        print("acceptance: the thresholds are constants; no flag changes them", file=sys.stderr)
        return 2
    try: args = ap.parse_args(argv)
    except SystemExit as exc: return 2 if exc.code else 0
    try:
        if args.chain is not None:
            if args.rows is not None or args.record is not None or args.selftest: raise InputError("--chain is exclusive with --rows, --record and --selftest")
            results = run_chain(args.chain)
            for result in results: print(result.line())
            if results: print("chain: " + json.dumps(results[-1].facts, sort_keys=True))
            print("Offline recorded chain only; machine-valid output still requires human review.")
            return 0 if results and all(r.ok for r in results) else 1
        if args.selftest:
            if args.rows: raise InputError("--selftest runs only its own eight rows")
            rows_path = SELFTEST_ROWS
        else:
            rows_path = Path(args.rows) if args.rows else DEFAULT_ROWS
            if not rows_path.is_file(): raise InputError("the rows file does not exist (there is no automatic fallback to the self-test)")
        root = rows_path.parent
        if args.record:
            print(record_row(args.record, rows_path=rows_path, fixture_root=root, selftest=args.selftest), end="")
            print("acceptance: candidate only. A person checks it by hand; it is not evidence that the row is right.", file=sys.stderr)
            return 0
        results = run_rows(rows_path, fixture_root=root, selftest=args.selftest)
        if args.selftest:
            judged = judge_selftest(results, [r.row for r in results])
            for r, ok, want in judged: print(("PASS (as expected)" if want is None and ok else f"FAILED as expected [{want}]" if ok else "WRONG") + f"  {r.id:<28} {', '.join(r.codes) or 'no problems'}")
            bad = sum(not ok for _r, ok, _w in judged)
            print(f"acceptance self-test: {SELFTEST_ROWS_N} rows, {SELFTEST_FAULTS_N} faults: " + ("the engine behaves" if not bad else f"{bad} rows did not do what they say") + ". This is not a full-site acceptance run.")
            return 1 if bad else 0
        for r in results: print(r.line())
        summary = summarize(results)
        print(f"acceptance: {summary['rows']} rows, offline recorded mode: " + ("every threshold met" if summary["met"] else "a threshold is not met") + ". A partial run is not the full-site acceptance; model-written text is read by a person.")
        return 0 if summary["met"] and all(r.ok for r in results) else 1
    except InputError as exc:
        print(f"acceptance: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

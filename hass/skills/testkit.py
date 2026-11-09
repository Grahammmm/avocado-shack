"""SKILLS-TK-1: the skill test kit. Every skill is tested the same way (reports/hass/SKILLS-SPEC.md, 2.9).

    python3 hass/skills/testkit.py run FILE.jsonl [--skills MODULE.py]   run one cases file (plan and case rows)
    python3 hass/skills/testkit.py selftest                              prove the kit itself on fixtures/skills/_selftest
    python3 hass/skills/testkit.py all                                   every cases file under fixtures/skills

Level 2, plan golden (row has `"plan": true`): slots in, exact ops out. No model, no git, no scratch state. Also
checks the plan contract: only registry ops, 1 to 20 of them, same answer twice, the slots are left untouched.

Level 3, case run (every other row): the row's texts go through the real Conversation, the real Editor (production
op registry), real sitegen and real claims, on a throwaway writer worktree and state dir (the one the H02 tests
use). A recorded interpreter reply plays for each text; a reply `{"skill", "slots"}` or `{"calls": [...]}` is turned
into ops by the skill's own `plan` (the stand-in for the dispatcher that SKILLS-FW-3 adds). The kit asserts:

  write-before-yes   nothing in the worktree changes (files, commits) before an approval, nor after a wrong code
  wrong-diff         the exact content diff (file, key path, before, after) and the files touched equal `expect`
  edit-undeclared    every changed key path is inside the skill's declared `edits`
  undo-not-identical after `undo` + approval the tree equals the start, except the row's declared `residue`
  residue-undeclared a leftover after undo that the skill does not declare in its `residue` sentence
  wrong-disposition / wrong-reply / wrong-ops / wrong-skill / wrong-preview / wrong-turn
  jargon             an owner reply that shows an id, an operation name or a technical word
  stale-row, bad-row the row was written for another skill version / is malformed

A model-written text is machine-valid here, never accepted: a human reads it (spec 2.9). Nothing live is touched:
no live state, no host.json, no network. Exit code 0 when every row did what it said, 1 otherwise, 2 unreadable input.
"""
import argparse
import copy
import importlib.util
import json
import re
import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from hass.content_model import REPO_ROOT  # noqa: E402
from hass import voice  # noqa: E402

FIXTURES = REPO_ROOT / "hass" / "tests" / "fixtures" / "skills"
OWNER, CHAT = "owner@example.invalid", "chat-testkit-owner"
SETTINGS = {"ownerSenders": [OWNER], "ownerChat": CHAT, "approvalTtlSeconds": 600}
START = datetime(2026, 11, 8, 17, 0, tzinfo=timezone.utc)  # Sunday 09:00 PST, as the acceptance suite freezes it
CODES = ("write-before-yes", "wrong-diff", "edit-undeclared", "undo-not-identical", "residue-undeclared",
         "wrong-disposition", "wrong-reply", "wrong-ops", "wrong-skill", "wrong-preview", "wrong-turn", "jargon",
         "stale-row", "bad-row", "bad-plan", "no-skill")
FAULTS = ("write-on-prepare", "undo-leaves", "undo-stale-generated", "undo-dirty", "skip-later-preview")  # self-test only: a path that writes unasked / an undo that leaves a trace, a stale site file or an untracked file / a revision whose preview is never requested
PLAN_KEYS = {"id", "plan", "kind", "slots", "ctx", "expect_ops", "expect_error", "version", "note", "must_fail"}
CASE_KEYS = {"id", "kind", "texts", "replies", "expect", "approve", "version", "note", "fault", "must_fail", "plan", "seed", "setup", "undo",
             "photos", "house_render"}
ASSET_DIR = "storefront-mockup/assets/products/"  # a picture file the editor commits; undo leaves it, unused (a declared residue)
EXPECT_KEYS = {"skill", "disposition", "dispositions", "question_contains", "reply_contains", "reply_not_contains",
               "left_off", "set_line", "ops", "diff", "files", "preview", "residue", "allow_words"}
KINDS = ("clean", "vague", "typo", "multi", "refuse", "photo", "turns")
PREVIEW_KINDS = {"product": {"product", "maker"}, "hike": {"event"}, "home": {"store", "maker"}, "picture": {"product", "store"}, "none": set()}  # a maker record previews as the "maker" target (hass/preview.py)
MAX_OPS = 20

# -- plain words -------------------------------------------------------------------------------------------------
RECORD_LINE = re.compile(r"^(?:(?:Applied|Undone|Undo)[^:\n]*: )?(?:products|makers|events|routeIdeas|store|club) \S.*?: ")  # conversation.py's own record lines
HEADER_LINE = re.compile(r"^(Draft|Applied|Undo|Undone) [0-9a-z]{3,10}\b.*:$")
JARGON = re.compile(
    r"\b(json|slots?|payload|args|arguments?|schema|null|undefined|nan|traceback|exception|pointer|sha\d*|commit|worktree|"
    r"sqlite|api|registry|skills?|regex|uuid|enum|boolean|ops?|parser|stderr|stdout)\b|\b(True|False|None)\b|"
    r"\b[a-z]+(?:-[a-z0-9]+)*-\d{2,}\b|\b[0-9a-f]{12,}\b|\bchg-[0-9a-f]+|[{}\[\]]|=>|"
    r"\b(?:product|store|maker|makers|hike|event|events|route|history|club|test|toy|stock|item|shop|page|social|report|"
    r"answer|backlog)\.[a-z_]{3,}\b", re.IGNORECASE)
JARGON_CASE_SENSITIVE = {"True", "False", "None"}


def plain_words_problems(text, allow=()):
    """Technical words, ids and operation names in an owner-facing reply. Draft record lines and the draft header
    are conversation.py's own house format and are not judged here; everything a skill adds (questions, refusals,
    `I set:` / `Left off:` lines) is. `allow` lists words one row may show (for example a product's own name)."""
    found, allowed = [], {a.lower() for a in allow}
    for line in text.splitlines():
        if RECORD_LINE.match(line) or HEADER_LINE.match(line.strip()): continue
        for m in JARGON.finditer(line):
            word = m.group(0)
            if word.lower() in allowed or (word.lower() in {"true", "false", "none"} and word not in JARGON_CASE_SENSITIVE): continue
            if any(word.lower() in a or a in word.lower() for a in allowed): continue
            found.append(word)
    return found


# -- diffs -------------------------------------------------------------------------------------------------------
def _items_by_id(items):
    keys = [x.get("id") for x in items if isinstance(x, dict)]
    return dict(zip(keys, items)) if len(keys) == len(items) and all(isinstance(k, str) for k in keys) and len(set(keys)) == len(keys) else None


def json_diff(before, after, path=""):
    """[{path, before?, after?}], key paths like `products[photo-product-001].description`. A key or list item that
    appears or disappears is one entry for the whole value; a list of plain values (opening hours) is one value."""
    if before == after: return []
    if isinstance(before, dict) and isinstance(after, dict):
        out = []
        for k in sorted(set(before) | set(after)):
            p = f"{path}.{k}" if path else k
            if k not in before: out.append({"path": p, "after": after[k]})
            elif k not in after: out.append({"path": p, "before": before[k]})
            else: out += json_diff(before[k], after[k], p)
        return out
    if isinstance(before, list) and isinstance(after, list):
        b, a = _items_by_id(before), _items_by_id(after)
        if b is not None and a is not None:
            out = []
            for k in sorted(set(b) | set(a)):
                p = f"{path}[{k}]"
                if k not in b: out.append({"path": p, "after": a[k]})
                elif k not in a: out.append({"path": p, "before": b[k]})
                else: out += json_diff(b[k], a[k], p)
            return out
    return [{"path": path, "before": before, "after": after}]


def _git(cwd, *args, check=True):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check).stdout


def tree_diff(wt, base, head="HEAD"):
    """(files that differ between two commits, content diff entries `{file, path, before?, after?}`)."""
    files = sorted(f for f in _git(wt, "diff", "--name-only", base, head).split("\n") if f)
    entries = []
    for f in files:
        if not (f.startswith("hass/content/") and f.endswith(".json")): continue
        old = _git(wt, "show", f"{base}:{f}", check=False)
        new = _git(wt, "show", f"{head}:{f}", check=False)
        for e in json_diff(json.loads(old) if old else None, json.loads(new) if new else None):
            entries.append({"file": f, **e})
    return files, sorted(entries, key=lambda e: (e["file"], e["path"]))


def declared_covers(declared, file, path):
    """Is the changed key path inside one of the skill's declared edits `(file, "products[id].available")`?"""
    for dfile, dpath in declared:
        if dfile != file: continue
        pattern = re.escape(re.sub(r"\[[A-Za-z_]+\]", "[*]", dpath)).replace(r"\[\*\]", r"(?:\[[^\]]+\]|\..+?)")  # [id] also matches a dict key (makers.Etto), which json_diff writes with a dot
        if re.fullmatch(pattern + r"(?:[.\[].*)?", path): return True
    return False


def _declared_edits(skill):
    out = []
    for e in getattr(skill, "edits", ()) or ():
        if isinstance(e, str) and "::" in e: e = tuple(e.split("::", 1))
        out.append((str(e[0]), str(e[1])))
    return out


def _residue_declared(skill):
    r = getattr(skill, "residue", None) or getattr(getattr(skill, "undo", None), "residue", None)  # a toy skill's residue, or a real Skill's Undo.residue
    return isinstance(r, str) and r.strip().lower().rstrip(".") not in ("", "none")


# -- results -----------------------------------------------------------------------------------------------------
class Result:
    def __init__(self, row_id, kind="", plan=False):
        self.id, self.kind, self.plan, self.problems, self.facts, self.row = row_id, kind, plan, [], {}, {}

    def fail(self, code, detail):
        assert code in CODES, code
        self.problems.append((code, str(detail)[:600]))

    @property
    def ok(self): return not self.problems

    @property
    def codes(self): return [c for c, _ in self.problems]

    def line(self):
        head = f"{'PASS' if self.ok else 'FAIL'}  {self.id:<28} {self.kind or ('plan' if self.plan else ''):<8}"
        if self.ok: return head + "  " + " ".join(f"{k}={v}" for k, v in self.facts.items())
        return head + "  " + "; ".join(f"[{c}] {d}" for c, d in self.problems)


# -- the scratch world -------------------------------------------------------------------------------------------
class RecordingPreviewer:
    """Stands in for the browser screenshot: records the preview request (what would be shown) and returns a tiny
    private file, so the proposal and the result checks go the normal path."""

    def __init__(self, skip_after=None):
        self.requests, self.skip_after, self.calls = [], skip_after, 0  # skip_after: self-test fault, later previews are never requested

    def capture(self, files, target, out_png, assets=None):
        self.calls += 1
        if self.skip_after is None or self.calls <= self.skip_after: self.requests.append(copy.deepcopy(dict(target)))
        p = Path(out_png)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"\x89PNG\r\n\x1a\n")
        return {"ok": True, "png": str(p), "checks": {}, "error": None}


class SkillInterpreter:
    """Plays the recorded reply for each text. A skill reply becomes ops through the skill's own plan code."""

    def __init__(self, mapping, skills, ctx_for):
        self.mapping, self.skills, self.ctx_for, self.used, self.errors = mapping, skills, ctx_for, [], []
        self.said = []  # the owner's texts so far: a skill's rules read them (the dispatcher's ctx.texts)
        self.chosen = []  # what the skills chose for the owner in this message (their SET_PHRASES): the `I set:` line
        self.notes = []  # the proposal-note lines of the message being answered (reset by Scratch.say)

    def _plan(self, call):
        skill = self.skills.get(call.get("skill"))
        if skill is None: raise KeyError(f"no skill named {call.get('skill')!r}")
        self.used.append(skill.name)
        slots, ctx = call.get("slots") or {}, self.ctx_for()
        ops = skill.plan(copy.deepcopy(slots), ctx)
        self._notes(skill, call)
        module = sys.modules.get(getattr(skill.plan, "__module__", ""))  # the skill module's own wording of its defaults (D8), when it has one
        phrases = (getattr(module, "SET_PHRASES", None) or {}).get(skill.name)
        if phrases: self.chosen += list(phrases(copy.deepcopy(slots), ctx))
        return ops

    def set_line(self):
        unique = list(dict.fromkeys(p for p in self.chosen if p))
        return "I set: " + "; ".join(unique) + ".\n" if unique else ""

    def _notes(self, skill, call):
        """The assumed proposal-notes contract: a skill module may define ``notes(name, slots, ctx)`` returning
        ``{say, set, warn}`` lines the dispatcher shows beside the draft. They are collected here, in that order and
        once each, so the row can assert what the owner would be shown (the live conversation does not show them yet)."""
        fn = getattr(sys.modules.get(getattr(skill.plan, "__module__", None)), "notes", None)
        if not callable(fn): return
        got = fn(skill.name, copy.deepcopy(call.get("slots") or {}), self.ctx_for())
        for key in ("say", "set", "warn"):
            for line in got.get(key, []):
                if line not in self.notes: self.notes.append(line)

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        reply = copy.deepcopy(self.mapping.get(text, {"unsupported": "Sorry, I can't do that yet."}))
        self.said.append(text)
        self.chosen = []
        try:
            if "skill" in reply: return {"ops": self._plan(reply), "revises": reply.get("revises")}
            if "calls" in reply:
                return {"ops": [op for c in reply["calls"] for op in self._plan(c)], "revises": reply.get("revises")}
        except Exception as exc:  # noqa: BLE001 - a plan that refuses is a row result, not a crash
            self.errors.append(f"{type(exc).__name__}: {exc}")
            return {"unsupported": getattr(exc, "reply", None) or "Sorry, I can't do that yet."}  # a refusal carries its fixed reply
        return reply


class SetupError(ValueError):
    """A row's `setup` ops were refused or did not apply."""


class Scratch:
    """A throwaway writer worktree + state dir + Conversation with the production Editor and op registry."""

    def __init__(self, mapping, skills, fault=None, seed=None, setup=None, photos=(), house_render=False):
        from hass import conversation, editor, media
        from hass.fixture_chat import FixtureAdapter
        from hass.tests.test_editor import WriterRepo  # the H02 throwaway repo the demo transcript uses
        self.repo = WriterRepo()
        self.media_root, self.house_render = None, bool(house_render)
        settings = dict(SETTINGS)
        if photos:  # a row's photos: stored originals in a private media root, found again by their sha256 in the row's slots
            import tempfile
            self.media_root = tempfile.mkdtemp(prefix="testkit-media-")
            for rel in photos:
                media.store_original(self.media_root, (REPO_ROOT / rel).read_bytes(), received_at=START.isoformat(), source="testkit")
            settings["mediaRoot"] = self.media_root
            self._real_assets()
        cfg = json.loads((self.repo.state / "config.json").read_text("utf-8"))
        editor._write_json(self.repo.state / "config.json", {**cfg, "settings": settings})
        self.wt, self.now, self.n, self.out = self.repo.wt, START, 0, FixtureAdapter()
        if seed: self._seed_or_clean(seed)
        self.interp = SkillInterpreter(mapping, skills, self._ctx)
        self.previewer = RecordingPreviewer(skip_after=1 if fault == "skip-later-preview" else None)
        self.turn_previews = []  # the preview requests each message caused, in message order
        self.editor = _fault_editor(conversation.Editor, self, str(self.repo.state), fault)
        if setup:
            try: self._setup(setup)
            except Exception:  # noqa: BLE001 - nothing else owns the throwaway repo yet
                self.repo.cleanup()
                raise
        self.conv = conversation.Conversation(str(self.repo.state), self.editor, self.interp, lambda: self.now, self.previewer)
        self._proposal_reply = self.conv._proposal_reply
        self.conv._proposal_reply = self._with_set_line  # the stand-in dispatcher's job: the `I set:` line goes in front of the proposal (FW-3: prefix=...)
        self.Inbound = conversation.Inbound

    def _real_assets(self):
        """The worktree's ``assets/products`` becomes a real folder (the editor refuses to write a picture into a symlinked one),
        the way the photo tests do it; the other asset entries stay links. Committed, so it is the row's base and never its diff."""
        import shutil
        site = REPO_ROOT / "storefront-mockup" / "assets"
        assets = self.repo.wt / "storefront-mockup" / "assets"
        assets.unlink()
        (assets / "products").mkdir(parents=True)
        for entry in site.iterdir():
            if entry.name == "products": continue
            (assets / entry.name).symlink_to(entry)
        for entry in (site / "products").iterdir():
            shutil.copyfile(entry, assets / "products" / entry.name)  # a listing image must be a regular file, not a link
        _git(self.repo.wt, "add", "-A")
        _git(self.repo.wt, "-c", "user.name=kit", "-c", "user.email=kit@example.invalid", "commit", "-q", "-m", "real assets/products folder")

    def _with_set_line(self, row, draft, prefix=""):
        line, self.interp.chosen = self.interp.set_line(), []  # once, and only for the message whose plan chose something
        return self._proposal_reply(row, draft, line + prefix)

    def _seed_or_clean(self, seed):
        try: self._seed(seed)
        except BaseException:  # a seed that does not validate must not leave the scratch repo behind
            self.repo.cleanup()
            raise

    def _seed(self, seed):
        """A row's `seed` ({content file: {top-level key: value}}, for example a hike that is already on the page) is
        written into the scratch content, validated, regenerated and committed BEFORE the row starts: the row's
        start state, so its undo check and its diff are measured from there."""
        from hass import sitegen
        from hass.content_model import load_and_validate
        for stem, keys in seed.items():
            path = self.wt / "hass" / "content" / f"{stem}.json"
            data = json.loads(path.read_text("utf-8"))
            data.update(copy.deepcopy(keys))
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
        content = load_and_validate(self.wt / "hass" / "content", self.wt / "storefront-mockup")  # a bad seed stops the row here
        sitegen.write_files(sitegen.render(content, self.wt / "hass" / "templates"), self.wt)
        _git(self.wt, "add", "-A")
        _git(self.wt, "-c", "user.name=kit", "-c", "user.email=kit@example.invalid", "commit", "-q", "-m", "seed")

    def _setup(self, ops):
        """A row's starting state (for example a hidden product): the ops go through the real editor, prepare then
        apply, before the row starts, so the row's base is the tree after them. They are never part of the row's diff."""
        out = self.editor.prepare(ops)
        if out.get("result") != "ok": raise SetupError(f"setup ops were not accepted: {json.dumps(out, sort_keys=True)[:200]}")
        done = self.editor.apply(out["draft"]["change_id"], out["draft"]["draft_hash"])
        if done.get("result") != "applied": raise SetupError(f"setup ops were not applied: {json.dumps(done, sort_keys=True)[:200]}")

    def _ctx(self):
        from hass.content_model import load_and_validate
        return types.SimpleNamespace(today="2026-11-08", now=self.now, texts=list(self.interp.said), media_root=self.media_root,
                                     house_render=self.house_render,
                                     content=load_and_validate(self.wt / "hass" / "content", self.wt / "storefront-mockup"))

    def say(self, text):
        from datetime import timedelta
        self.n += 1
        self.interp.chosen = []
        self.now += timedelta(minutes=1)
        msg = self.Inbound(f"tk-{self.n}", CHAT, OWNER, text, False, "new", self.now.isoformat())
        asked = len(self.previewer.requests)
        self.interp.notes = []
        disposition = self.conv.handle(msg)
        before = len(self.out.sent)
        self.conv.flush(self.out)
        self.turn_previews.append(self.previewer.requests[asked:])
        texts = [r["text"] for r in self.out.sent[before:]]
        if disposition == "proposed" and self.interp.notes: texts.append(voice.plain("\n".join(self.interp.notes)))  # the proposal notes, as the dispatcher will show them
        return disposition, texts

    def head(self): return _git(self.wt, "rev-parse", "HEAD").strip()

    def dirty(self): return _git(self.wt, "status", "--porcelain").strip()

    def drafts(self): return [dict(r) for r in self.conv.db.execute("SELECT * FROM drafts ORDER BY row_id")]

    def close(self):
        try: self.conv.db.close()
        finally:
            self.repo.cleanup()
            if self.media_root:
                import shutil
                shutil.rmtree(self.media_root, ignore_errors=True)


def _fault_editor(base, scratch, state, fault):
    if fault is None: return base(state)

    class FaultEditor(base):  # kit self-test only: what a broken skill path would do
        applies = 0

        def prepare(self, ops):
            out = super().prepare(ops)
            if fault == "write-on-prepare" and out.get("result") == "ok": super().apply(out["draft"]["change_id"], out["draft"]["draft_hash"])
            return out

        def apply(self, change_id, draft_hash):
            out = super().apply(change_id, draft_hash)
            self.applies += 1
            if fault == "undo-leaves" and self.applies == 2:  # a real, fully regenerated leftover: the site matches its content
                from hass import sitegen
                from hass.content_model import load_and_validate
                path = scratch.wt / "hass" / "content" / "store.json"
                data = json.loads(path.read_text("utf-8"))
                data["town"] = data["town"] + " Leftover"
                path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
                content = load_and_validate(scratch.wt / "hass" / "content", scratch.wt / "storefront-mockup")
                sitegen.write_files(sitegen.render(content, scratch.wt / "hass" / "templates"), scratch.wt)
                _git(scratch.wt, "-c", "user.name=kit", "-c", "user.email=kit@example.invalid", "commit", "-q", "-a", "-m", "leftover")
            if fault == "undo-stale-generated" and self.applies == 2:  # content restored, one generated file still shows the edit
                path = scratch.wt / "storefront-mockup" / "catalog-products.js"
                path.write_text(path.read_text("utf-8") + "// still the edited text\n", "utf-8")
                _git(scratch.wt, "-c", "user.name=kit", "-c", "user.email=kit@example.invalid", "commit", "-q", "-a", "-m", "stale")
            if fault == "undo-dirty" and self.applies == 2:  # nothing committed, an untracked file stays in the worktree
                (scratch.wt / "storefront-mockup" / "left-behind.txt").write_text("x", "utf-8")
            return out
    return FaultEditor(state)


# -- plan golden (level 2) ---------------------------------------------------------------------------------------
def run_plan_row(row, skills, skill=None, registry=None):
    res = Result(row.get("id", "?"), plan=True)
    bad = _row_problems(row, PLAN_KEYS, ("id", "slots"))
    if bad: res.fail("bad-plan", bad); return res
    if skill is None: res.fail("no-skill", "no skill for this cases file"); return res
    if registry is None:
        from hass.ops import load_registry
        registry = load_registry()
    ctx, slots = types.SimpleNamespace(**{"today": "2026-11-08", **(row.get("ctx") or {})}), row["slots"]
    before, given = copy.deepcopy(slots), copy.deepcopy(slots)
    try: ops = skill.plan(given, ctx)
    except Exception as exc:  # noqa: BLE001
        want = row.get("expect_error")
        if want is None: res.fail("bad-plan", f"plan raised {type(exc).__name__}: {exc}")
        elif want not in str(exc): res.fail("wrong-ops", f"plan refused with {str(exc)[:200]!r}, wanted text {want!r}")
        else: res.facts["refused"] = want
        return res
    if "expect_error" in row: res.fail("wrong-ops", "plan returned ops but the row expects a refusal"); return res
    if not isinstance(ops, list) or not 1 <= len(ops) <= MAX_OPS: res.fail("bad-plan", f"plan must return 1 to {MAX_OPS} ops"); return res
    for op in ops:
        if not isinstance(op, dict) or set(op) != {"op", "args"}: res.fail("bad-plan", "each op is {op, args}"); continue
        if op["op"] not in registry: res.fail("bad-plan", f"{op['op']} is not a registry op")
    if given != before: res.fail("bad-plan", "plan changed the slots it was given")
    try: again = skill.plan(copy.deepcopy(slots), copy.deepcopy(ctx))
    except Exception as exc:  # noqa: BLE001
        again = f"{type(exc).__name__}"
    if again != ops: res.fail("bad-plan", "plan is not pure: a second call gave another answer")
    if "expect_ops" not in row: res.fail("bad-row", "plan row without expect_ops or expect_error")
    elif ops != row["expect_ops"]: res.fail("wrong-ops", f"ops {json.dumps(ops, sort_keys=True)} != expected {json.dumps(row['expect_ops'], sort_keys=True)}")
    res.facts["ops"] = len(ops)
    return res


# -- case run (level 3) ------------------------------------------------------------------------------------------
def _row_problems(row, allowed, required):
    if not isinstance(row, dict): return "row must be a JSON object"
    missing = [k for k in required if k not in row]
    extra = sorted(set(row) - allowed)
    if missing: return f"missing {', '.join(missing)}"
    if extra: return f"unknown field {', '.join(extra)}"
    if isinstance(row.get("expect"), dict) and set(row["expect"]) - EXPECT_KEYS:
        return "unknown expect field " + ", ".join(sorted(set(row["expect"]) - EXPECT_KEYS))
    return None


def _subset(want, got):
    if isinstance(want, dict): return isinstance(got, dict) and all(k in got and _subset(v, got[k]) for k, v in want.items())
    return want == got


def run_case_row(row, skills, skill=None, selftest=False):
    res = Result(row.get("id", "?") if isinstance(row, dict) else "?", row.get("kind", "") if isinstance(row, dict) else "")
    bad = _row_problems(row, CASE_KEYS, ("id", "kind", "texts", "replies", "expect"))
    if not bad and row["kind"] not in KINDS: bad = f"kind must be one of {', '.join(KINDS)}"
    if not bad and not (isinstance(row["texts"], list) and row["texts"] and len(row["texts"]) == len(row["replies"])
                        and all(isinstance(t, str) and t for t in row["texts"]) and len(set(row["texts"])) == len(row["texts"])):
        bad = "texts must be distinct non-empty strings, one recorded reply each"
    if not bad and (("fault" in row or "must_fail" in row) and not selftest): bad = "fault / must_fail exist only for the kit self-test"
    if not bad and row.get("fault") not in (None, *FAULTS): bad = f"fault must be one of {', '.join(FAULTS)}"
    setup = row.get("setup") if isinstance(row, dict) else None
    if not bad and setup is not None and not (isinstance(setup, list) and setup and all(isinstance(o, dict) and set(o) == {"op", "args"} for o in setup)):
        bad = "setup is a list of {op, args} ops applied before the row starts"
    if not bad and "undo" in row and row["undo"] is not True: bad = "undo, when given, is true (the row ends in an approved draft that is undone)"
    if bad: res.fail("bad-row", bad); return res
    expect, mapping = row["expect"], dict(zip(row["texts"], row["replies"]))
    names = {c.get("skill") for r in row["replies"] for c in ([r] + list(r.get("calls", []))) if isinstance(c, dict) and "skill" in c}
    if skill is not None and "version" in row and getattr(skill, "version", None) not in (None, row["version"]):
        res.fail("stale-row", f"row written for version {row['version']}, skill is version {skill.version}"); return res
    seed = row.get("seed")
    if seed is not None and not (isinstance(seed, dict) and all(k in ("products", "makers", "community", "store") and isinstance(v, dict) for k, v in seed.items())):
        res.fail("bad-row", "seed must be {products|makers|community|store: {top-level key: value}}"); return res
    try: scratch = Scratch(mapping, skills, row.get("fault"), seed, setup, row.get("photos") or (), row.get("house_render") is True)
    except SetupError as exc: res.fail("bad-row", exc); return res
    except ValueError as exc:  # a row whose photos cannot be stored is a bad row with its own words; a refused seed has its own line
        res.fail("bad-row", exc if seed is None else f"the seed could not be applied: {type(exc).__name__}: {str(exc)[:200]}"); return res
    except Exception as exc:  # noqa: BLE001 - a seed the content rules refuse is a bad row, not a crash
        res.fail("bad-row", f"the seed could not be applied: {type(exc).__name__}: {str(exc)[:200]}"); return res
    try: _drive(row, expect, scratch, skills, skill, names, res)
    finally: scratch.close()
    if row.get("undo") is True and "undo" not in res.facts and res.ok: res.fail("wrong-turn", "the row says undo, but it did not end in an approved draft that was undone")
    return res


def _drive(row, expect, sc, skills, skill, names, res):
    base_head, dispositions, replies = sc.head(), [], []

    def untouched(when):
        if sc.head() != base_head or sc.dirty():
            res.fail("write-before-yes", f"the worktree changed {when}: " + (_git(sc.wt, "diff", "--name-only", base_head).strip().replace("\n", ", ") or sc.dirty())[:200])
            return False
        return True

    for text in row["texts"]:
        try: disposition, out = sc.say(text)
        except voice.VoiceError as exc:  # HASS-VOICE-1: strict mode refuses a reply that breaks the voice rules
            res.fail("jargon", f"owner reply breaks the voice rules: {str(exc)[:160]}"); return
        except Exception as exc:  # noqa: BLE001
            res.fail("wrong-turn", f"{type(exc).__name__}: {exc}"); return
        dispositions.append(disposition), replies.append(out)
        if not untouched(f"after the message {len(dispositions)} (no yes was sent)"): return
    if sc.interp.errors: res.facts["plan_refused"] = sc.interp.errors[0][:80]
    flat = [t for out in replies for t in out]
    final, last = dispositions[-1], "\n".join(replies[-1])
    res.facts["disposition"] = final
    _check_expect_text(row, expect, dispositions, final, last, flat, res)
    used = sorted(set(sc.interp.used))
    chosen = [skills[n] for n in used if n in skills] or ([skill] if skill is not None else [])  # the skills whose plan ran
    if "skill" in expect:
        want = expect["skill"] if isinstance(expect["skill"], list) else [expect["skill"]]
        if used != sorted(want): res.fail("wrong-skill", f"plan code of {used or 'no skill'} ran, expected {sorted(want)}")
    drafts = sc.drafts()
    proposed = final == "proposed" and drafts
    if not proposed:
        if expect.get("diff") or expect.get("ops"): res.fail("wrong-disposition", f"expected a draft, the message ended as {final!r}")
        return
    draft = drafts[-1]
    ops = json.loads(draft["ops_json"])
    if "ops" in expect and ops != expect["ops"]: res.fail("wrong-ops", f"draft ops {json.dumps(ops, sort_keys=True)[:300]} != expected")
    for key in ("diff", "files", "preview"):
        if key not in expect: res.fail("bad-row", f"a row that ends in a draft must say expect.{key}"); return
    _check_preview(expect, sc.turn_previews[len(row["texts"]) - 1], chosen[0] if chosen else None, res)
    # a wrong code never approves, and a draft that was never approved has written nothing
    try: sc.say("yes zzzz")
    except Exception as exc:  # noqa: BLE001
        res.fail("wrong-turn", f"{type(exc).__name__}: {exc}"); return
    if not untouched("after a yes with the wrong code"): return
    if row.get("approve") is False: return
    disposition, out = sc.say(f"yes {draft['code']}")
    flat += out
    files, diff = tree_diff(sc.wt, base_head)
    _check_diff(expect, files, diff, chosen, res)
    res.facts["diff"] = len(diff)
    if not files: return
    # undo: its own draft, its own yes; the tree must come back except the declared residue
    disposition, out = sc.say("undo")
    flat += out
    if disposition != "proposed": res.fail("wrong-turn", f"undo ended as {disposition!r}"); return
    disposition, out = sc.say(f"yes {sc.drafts()[-1]['code']}")
    flat += out
    ufiles, leftover = tree_diff(sc.wt, base_head)
    leftover = sorted(leftover + [{"file": f, "path": "(file)"} for f in ufiles if f.startswith(ASSET_DIR)],  # a picture file stays, unused
                      key=lambda e: (e["file"], e["path"]))
    wanted = expect.get("residue", [])
    hard = _undo_problems(sc, ufiles, leftover)
    if hard: res.fail("undo-not-identical", "; ".join(hard))
    elif not leftover:
        if wanted: res.fail("undo-not-identical", f"the row declares residue {wanted} but undo left nothing")
    elif chosen and not any(_residue_declared(s) for s in chosen):
        res.fail("residue-undeclared", "undo left " + _fmt(leftover) + " but the skill declares no residue")
    elif leftover != _norm(wanted, leftover):
        res.fail("undo-not-identical", "undo left " + _fmt(leftover) + f" but the row declares {_fmt(wanted)}")
    res.facts["undo"] = "identical" if not (hard or leftover) else "residue"
    words = sorted(set(expect.get("allow_words", [])))
    for text in flat:
        problems = plain_words_problems(text, words)
        if problems: res.fail("jargon", f"owner reply shows {sorted(set(problems))}: {text.splitlines()[0][:80]!r}")


def _undo_problems(sc, ufiles, leftover):
    """What the real worktree shows after undo, apart from a declared content residue: it is clean (nothing
    uncommitted or untracked), every file that is not content JSON is as at the start, the site files equal a fresh
    render of the restored content (the editor re-sorts keys, so they are judged against that render, not against
    the start's bytes)."""
    from hass.content_model import ContentError, load_and_validate
    from hass.editor import GENERATED_PATHS
    from hass import sitegen
    out = []
    if sc.dirty(): out.append("the worktree is not clean after undo: " + sc.dirty().replace("\n", ", ")[:160])
    contentish = lambda f: f.startswith("hass/content/") and f.endswith(".json")  # noqa: E731 - the editor re-sorts keys; judged parsed
    other = [f for f in ufiles if not contentish(f) and f not in GENERATED_PATHS and not f.startswith(ASSET_DIR)]
    if other: out.append("undo left these files different from the start: " + ", ".join(other))
    try:
        stale = sitegen.stale_paths(load_and_validate(sc.wt / "hass" / "content", sc.wt / "storefront-mockup"), sc.wt)
    except ContentError as exc:
        stale = [f"content invalid after undo: {exc}"]
    if stale: out.append("site files do not match the restored content: " + ", ".join(stale))
    return out


def _norm(wanted, actual):  # a declared residue entry names {file, path}; before / after are matched when given
    out = []
    for w in wanted:
        match = next((a for a in actual if a["file"] == w.get("file") and a["path"] == w.get("path")), None)
        out.append(match if match is not None and _subset(w, match) else w)
    return sorted(out, key=lambda e: (e["file"], e["path"]))


def _fmt(entries):
    return json.dumps(entries, sort_keys=True)[:300]


def _check_expect_text(row, expect, dispositions, final, last, flat, res):
    if "dispositions" in expect and dispositions != expect["dispositions"]:
        res.fail("wrong-disposition", f"dispositions {dispositions} != {expect['dispositions']}")
    if "disposition" in expect and final != expect["disposition"]:
        res.fail("wrong-disposition", f"ended as {final!r}, expected {expect['disposition']!r}")
    for key, label in (("question_contains", None), ("reply_contains", None)):
        for want in _as_list(expect.get(key)):
            if want.lower() not in last.lower(): res.fail("wrong-reply", f"{key}: {want!r} not in the reply {last[:160]!r}")
    for want in _as_list(expect.get("reply_not_contains")):
        if want.lower() in last.lower(): res.fail("wrong-reply", f"reply_not_contains: {want!r} is in the reply")
    for key, prefix in (("left_off", "Left off:"), ("set_line", "I set:")):
        for want in _as_list(expect.get(key)):
            lines = [ln for ln in last.splitlines() if ln.startswith(prefix)]
            if not any(want.lower() in ln.lower() for ln in lines): res.fail("wrong-reply", f"{key}: no '{prefix}' line with {want!r}")
    problems = plain_words_problems("\n".join(flat), expect.get("allow_words", []))
    if problems: res.fail("jargon", f"owner reply shows {sorted(set(problems))}")


def _as_list(v): return [] if v is None else v if isinstance(v, list) else [v]


def _check_preview(expect, requests, skill, res):
    """`requests` are the preview requests the message that made the final draft caused: the preview of the draft
    that is then approved, never an earlier one."""
    if not requests: res.fail("wrong-preview", "no preview was requested for the final proposal"); return
    last = requests[-1]
    res.facts["preview"] = last.get("kind")
    if not _subset(expect["preview"], last): res.fail("wrong-preview", f"preview request {json.dumps(last, sort_keys=True)[:200]} lacks {json.dumps(expect['preview'], sort_keys=True)}")
    kind = str(getattr(skill, "preview", "") or "").split(":")[0]
    if skill is not None and kind in PREVIEW_KINDS and last.get("kind") not in PREVIEW_KINDS[kind]:
        res.fail("wrong-preview", f"the skill previews {kind!r} but the request is for {last.get('kind')!r}")


def _declared_picture(declared, file):
    """A new picture file the editor commits is fine when the skill declares one: `(".../assets/products/photo-<sha16>.jpg", "file")`."""
    return file.startswith(ASSET_DIR) and any(
        d.startswith(ASSET_DIR) and re.fullmatch(re.sub(r"<[^>]+>", "[^/]+", re.escape(d)), file) for d, _p in declared)


def _check_diff(expect, files, diff, chosen, res):
    want = sorted(expect["diff"], key=lambda e: (e["file"], e["path"]))
    if diff != want: res.fail("wrong-diff", f"diff {_fmt(diff)} != expected {_fmt(want)}")
    if files != sorted(expect["files"]): res.fail("wrong-diff", f"files {files} != expected {sorted(expect['files'])}")
    if chosen:
        from hass.editor import GENERATED_PATHS
        declared = [d for s in chosen for d in _declared_edits(s)]
        for e in diff:
            if not declared_covers(declared, e["file"], e["path"]): res.fail("edit-undeclared", f"{e['file']} {e['path']} is outside the skill's declared edits")
        for f in files:
            if f not in GENERATED_PATHS and not f.startswith("hass/content/") and not _declared_picture(declared, f):
                res.fail("edit-undeclared", f"{f} is neither content nor a generated file")


# -- loading and running files -----------------------------------------------------------------------------------
def load_rows(path):
    rows = []
    for n, line in enumerate(Path(path).read_text("utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"): continue
        try: rows.append(json.loads(line))
        except ValueError: raise ValueError(f"{Path(path).name} line {n}: not JSON") from None
    ids = [r.get("id") for r in rows if isinstance(r, dict)]
    if len(ids) != len(set(ids)): raise ValueError(f"{Path(path).name}: duplicate row id")
    return rows


def load_skill_module(path):
    spec = importlib.util.spec_from_file_location("testkit_skills_" + Path(path).stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return tuple(mod.SKILLS)


def registry_skills():
    """The real registry (SKILLS-FW-1's load_skills) when it is present; none before that card is merged."""
    try:
        from hass.skills import load_skills
    except ImportError:
        return ()
    loaded = load_skills()
    return tuple(getattr(loaded, "skills", loaded).values()) if hasattr(getattr(loaded, "skills", None), "values") else tuple(loaded)


def skill_for(skills, path, rows):
    by_name = {s.name: s for s in skills}
    if Path(path).stem in by_name: return by_name[Path(path).stem]  # fixtures/skills/<group>/<name>.jsonl
    named = {c.get("skill") for r in rows if isinstance(r, dict) for c in ([x for x in r.get("replies", []) if isinstance(x, dict)])}
    named |= {c for r in rows if isinstance(r, dict) and r.get("plan") for c in [r.get("skill")] if c}
    named.discard(None)
    return by_name.get(next(iter(named))) if len(named) == 1 else None


def run_file(path, skills, selftest=False, only=None):
    rows, results = load_rows(path), []
    by_name = {s.name: s for s in skills}
    file_skill = skill_for(skills, path, rows)
    registry = None
    for row in rows:
        if only and row.get("id") not in only: continue
        if isinstance(row, dict) and row.get("plan"):
            skill = by_name.get(row.get("skill")) or file_skill
            if registry is None:
                from hass.ops import load_registry
                registry = load_registry()
            res = run_plan_row({k: v for k, v in row.items() if k != "skill"}, skills, skill, registry)
            if "must_fail" in row and not selftest: res.fail("bad-row", "fault / must_fail exist only for the kit self-test")
        else:
            skill = _row_skill(row, by_name, file_skill)
            res = run_case_row(row, by_name, skill, selftest)
        res.row = row
        results.append(res)
    return results


def _row_skill(row, by_name, file_skill):
    names = [c.get("skill") for r in row.get("replies", []) if isinstance(r, dict) for c in [r] + list(r.get("calls", [])) if isinstance(c, dict) and c.get("skill")]
    return by_name.get(names[0]) if names else file_skill


def judge_selftest(results):
    """Self-test verdict per row: a row without must_fail has to pass; a row with must_fail has to fail with exactly that code."""
    out = []
    for r in results:
        want = r.row.get("must_fail")
        ok = r.ok if want is None else (not r.ok and set(r.codes) == {want})
        out.append((r, ok, want))
    return out


def discover(root=FIXTURES, selftest=False):
    root = Path(root)
    return sorted(p for p in root.glob("*/*.jsonl") if selftest == p.parent.name.startswith("_"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="hass/skills/testkit.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("file")
    run.add_argument("--skills", metavar="MODULE.py")
    run.add_argument("--row", action="append")
    sub.add_parser("selftest")
    sub.add_parser("all")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "selftest": return _selftest()
        if args.cmd == "all":
            skills, bad = registry_skills(), 0
            files = discover()
            for f in files: bad += _print_file(f, run_file(f, skills))
            print(f"testkit: {len(files)} cases files, {'all passed' if not bad else f'{bad} rows failed'}")
            return 1 if bad else 0
        skills = load_skill_module(args.skills) if args.skills else registry_skills()
        return 1 if _print_file(args.file, run_file(args.file, skills, only=args.row)) else 0
    except (OSError, ValueError, KeyError, AttributeError, ImportError) as exc:
        print(f"testkit: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


def _print_file(path, results):
    print(f"== {Path(path).name}")
    for r in results: print(r.line())
    failed = sum(not r.ok for r in results)
    print(f"-- {len(results) - failed} passed, {failed} failed")
    return failed


def _selftest():
    folder = FIXTURES / "_selftest"
    skills, bad = load_skill_module(folder / "toy.py"), 0
    for path in sorted(folder.glob("*.jsonl")):
        print(f"== {path.name} (kit self-test: a row marked must_fail has to fail for exactly that reason)")
        for r, ok, want in judge_selftest(run_file(path, skills, selftest=True)):
            shown = "PASS (as expected)" if want is None and ok else f"FAILED as expected [{want}]" if ok else "WRONG"
            print(f"{shown:<28} {r.id:<28} {'; '.join(f'[{c}]' for c in r.codes) if r.codes else 'no problems'}")
            if not ok:
                for code, detail in r.problems: print(f"    [{code}] {detail}")
            bad += not ok
    print(f"testkit selftest: {'the kit behaves' if not bad else f'{bad} rows did not do what they say'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

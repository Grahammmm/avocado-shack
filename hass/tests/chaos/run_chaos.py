"""HASS-CHAOS-1: the drunk-owner regression suite. Sloppy owner conversations through the REAL Conversation, skills dispatcher,
router, editor (throwaway writer repo), till desk (recorded Clover fixture cache) and photo path, with the model calls on tape.

    python3 -B hass/tests/chaos/run_chaos.py [--case ID ...] [--out DIR]             # replay (default): no network, no model
    python3 -B hass/tests/chaos/run_chaos.py --record [--preview] [--case ID ...]      # re-record (private host only, see below)

Replay plays every model answer (interpreter, label reader, answer reader) and every card capture verdict back from
hass/tests/chaos/tapes/<case>.json in call order per turn; a call the tape does not hold answers "unsupported" and is
counted as a tape miss (the code now asks the model something it did not ask when the tape was made). Nothing is sent
anywhere: replies go to an in-memory adapter, and "publishing" is a commit in a temporary writer repo (counted, never pushed).

--record runs the live interpreter route of host.json (codex gpt-6.2-sol effort low timeout 12 s, fallback local Qwen 60 s,
inside cloud_codex.BUDGET) and writes new tapes. Budgets are enforced across processes with a lock file in --out:
--max-codex (default 150) Codex calls and --max-qwen (default 20) local Qwen calls. A local-route call past the Qwen budget
is sent to Codex instead and labelled `codex-sub` in the tape and results (the live service would have asked Qwen).
--preview uses the real private previewer (hass/preview.py, Node 22 via $NODE, Playwright under ~/.cache/avo-ci-playwright)
and keeps each card PNG in --out; without it captures are recorded/replayed verdicts only.

Each case (hass/tests/chaos/cases.json) lists turns and checks. Output: --out/results.json (per case and per turn:
replies, dispositions, seconds, models, check failures) and a one-line summary on stdout. Exit 0 when every check that is
not listed under the case's `known` failures passes, 1 otherwise. A `known` check that now passes is reported as `fixed`
so the case file can be updated.
"""
import argparse
import copy
import fcntl
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if __package__ in (None, ""):
    sys.path.insert(0, str(HERE.parents[2]))

from hass import conversation, editor as editor_mod, label_reader, voice  # noqa: E402
from hass.content_model import REPO_ROOT  # noqa: E402
from hass.skills import testkit  # noqa: E402

CASES, TAPES, PHOTOS = HERE / "cases.json", HERE / "tapes", HERE / "photos"
OWNER, STRANGER, CHAT = "owner-chaos@example.invalid", "stranger@example.invalid", "chat-chaos-owner"
START = datetime(2026, 11, 18, 1, 0, tzinfo=timezone.utc)  # Tue 2026-11-17 17:00 PST (G's live test evening)
LIVE_ITP = {"api": "codex", "model": "gpt-6.2-sol", "effort": "low", "timeout": 12,
            "fallback": {"api": "openai", "model": "qwen3.8:27b-thinkingcap-q6", "timeout": 60, "url": "http://127.0.0.1:8010"}}
CLOVER = {"environment": "production", "merchantId": "FAKEMERCH0001", "tokenFile": "/nowhere/production-read.token", "liveApproved": False}
ATTRS = ("last_error", "last_backend", "last_fallback", "last_primary_error", "last_seconds", "last_model")
PNG = b"\x89PNG\r\n\x1a\n"


# -- tape -------------------------------------------------------------------------------------------------------------
class Tape:
    """Per case: calls recorded as {turn, method, result, attrs, seconds, route}. Replay pops them per (turn, method) in order."""

    def __init__(self, case_id, mode):
        self.case_id, self.mode, self.turn, self.calls, self.misses, self.routes = case_id, mode, 0, [], 0, []
        self.queue = {}
        if mode == "replay":
            path = TAPES / f"{case_id}.json"
            for call in (json.loads(path.read_text("utf-8"))["calls"] if path.exists() else []):
                self.queue.setdefault((call["turn"], call["method"]), []).append(call)

    def take(self, method):
        q = self.queue.get((self.turn, method)) or []
        if not q:
            self.misses += 1
            return None
        call = q.pop(0)
        self.calls.append(call)
        return call

    def put(self, method, result, attrs, seconds, route):
        self.calls.append({"turn": self.turn, "method": method, "result": result, "attrs": attrs, "seconds": round(seconds, 3), "route": route})

    def save(self):
        TAPES.mkdir(exist_ok=True)
        (TAPES / f"{self.case_id}.json").write_text(json.dumps({"case": self.case_id, "calls": self.calls}, indent=1, ensure_ascii=False) + "\n", "utf-8")  # no sort_keys: reply key order feeds the draft


def _route(obj):
    """Which model answered a just-finished call: codex, qwen (live local route), codex-sub (Qwen budget spent) or none."""
    log = getattr(obj, "_chaos_routes", None)
    return "+".join(log) if log else "none"


class TapedInterpreter:
    def __init__(self, tape, real=None):
        self.tape, self.real = tape, real
        for a in ATTRS: setattr(self, a, None)

    def interpret(self, text, pending, notes=None, aliases=None, *, sent_at=None, recent=None):
        if self.tape.mode == "replay":
            call = self.tape.take("interpret")
            if call is None:
                for a in ATTRS: setattr(self, a, None)
                return {"unsupported": "Sorry, I can't do that yet."}
            for a in ATTRS: setattr(self, a, call["attrs"].get(a))
            return copy.deepcopy(call["result"])
        ROUTES.clear()
        started = time.monotonic()
        result = self.real.interpret(text, pending, notes, aliases, sent_at=sent_at, recent=recent)
        attrs = {a: getattr(self.real, a, None) for a in ATTRS}
        for a, v in attrs.items(): setattr(self, a, v)
        self.tape.put("interpret", result, attrs, time.monotonic() - started, "+".join(ROUTES) or "none")
        return copy.deepcopy(result)


class TapedLabels(label_reader.LabelReader):  # an instance check in conversation.py decides whether owner_text is passed
    def __init__(self, tape, real=None):  # noqa: D401 - deliberately no super().__init__: no model is built in replay
        self.tape, self.real = tape, real
        for a in ATTRS: setattr(self, a, None)

    def read(self, image_bytes, categories, owner_text=""):
        if self.tape.mode == "replay":
            call = self.tape.take("label")
            if call is None: return {"ok": False}
            for a in ATTRS: setattr(self, a, call["attrs"].get(a))
            return copy.deepcopy(call["result"])
        ROUTES.clear()
        started = time.monotonic()
        key = "label:" + hashlib.sha256(image_bytes).hexdigest() + ":" + owner_text
        hit = CACHE.get(key)
        result = copy.deepcopy(hit) if hit is not None else self.real.read(image_bytes, categories, owner_text=owner_text)
        attrs = {a: getattr(self.real, a, None) for a in ATTRS} if hit is None else {"last_backend": "cached"}
        if hit is None and not attrs.get("last_error"): CACHE.put(key, result)
        for a, v in attrs.items(): setattr(self, a, v)
        self.tape.put("label", result, attrs, time.monotonic() - started, "cached" if hit is not None else "+".join(ROUTES) or "none")
        return copy.deepcopy(result)


class TapedAnswers:
    def __init__(self, tape, real=None):
        self.tape, self.real, self.calls = tape, real, 0
        for a in ATTRS: setattr(self, a, None)

    def _one(self, method, *args):
        self.calls += 1
        if self.tape.mode == "replay":
            call = self.tape.take("answer." + method)
            if call is None: return {}
            for a in ATTRS: setattr(self, a, call["attrs"].get(a))
            return copy.deepcopy(call["result"])
        ROUTES.clear()
        started = time.monotonic()
        key = "answer." + method + ":" + json.dumps(args, default=str, ensure_ascii=False)
        hit = CACHE.get(key)
        result = copy.deepcopy(hit) if hit is not None else getattr(self.real, method)(*args)
        attrs = {a: getattr(self.real, a, None) for a in ATTRS} if hit is None else {"last_backend": "cached"}
        if hit is None and result and not attrs.get("last_error"): CACHE.put(key, result)
        for a, v in attrs.items(): setattr(self, a, v)
        self.tape.put("answer." + method, result, attrs, time.monotonic() - started, "cached" if hit is not None else "+".join(ROUTES) or "none")
        return copy.deepcopy(result)

    def fields(self, words): return self._one("fields", words)

    def read(self, key, words, today): return self._one("read", key, words, today)


class TapedPreviewer:
    """Card capture: the real private previewer when recording with --preview, else the recorded verdict (or a plain ok)."""

    def __init__(self, tape, real=None, png_dir=None):
        self.tape, self.real, self.png_dir, self.shots = tape, real, png_dir, []

    def capture(self, files, target, out_png, assets=None, **kwargs):
        p = Path(out_png)
        p.parent.mkdir(parents=True, exist_ok=True)
        if self.tape.mode == "replay" or self.real is None:
            call = self.tape.take("capture") if self.tape.mode == "replay" else None
            got = copy.deepcopy(call["result"]) if call else {"ok": True, "checks": {}, "error": None}
            if self.tape.mode == "record": self.tape.put("capture", got, {}, 0.0, "stub")
            p.write_bytes(PNG)
            got["png"] = str(p) if got.get("ok") else None
            return got
        started = time.monotonic()
        got = self.real.capture(files, target, out_png, assets=assets, **kwargs)
        keep = {k: v for k, v in got.items() if k != "png"}
        self.tape.put("capture", keep, {}, time.monotonic() - started, "browser")
        if got.get("ok") and got.get("png") and self.png_dir:
            dest = Path(self.png_dir) / f"turn{self.tape.turn}-{len(self.shots) + 1}.png"
            shutil.copyfile(got["png"], dest)
            self.shots.append(str(dest))
        return got


# -- live model route with budgets (record mode only) -----------------------------------------------------------------
ROUTES = []


class _Cache:
    """Record mode only: a label/answer read of the SAME input (photo bytes + owner text, or the same words) is answered from the
    first recorded reply (route `cached`), so the model budget is spent on new inputs. Shared across --jobs via a lock file."""

    def __init__(self): self.path = None

    def _io(self, fn):
        if self.path is None: return None
        with open(self.path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.seek(0)
            data = json.loads(fh.read() or "{}")
            out = fn(data)
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(data, ensure_ascii=False))
            return out

    def get(self, key): return self._io(lambda d: d.get(key))

    def put(self, key, value): self._io(lambda d: d.__setitem__(key, value))


CACHE = _Cache()


class Budget:
    def __init__(self, path, max_codex, max_qwen):
        self.path, self.max = Path(path), {"codex": max_codex, "qwen": max_qwen}

    def take(self, kind) -> bool:
        with open(self.path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.seek(0)
            used = json.loads(fh.read() or "{}")
            if used.get(kind, 0) >= self.max[kind]: return False
            used[kind] = used.get(kind, 0) + 1
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(used))
            return True


def _live_route(worktree, budget):
    """host.interpreter_builder's objects, with budget-counting wrappers around the codex runner and the local transports."""
    from hass import answer_reader, cloud_codex, host

    class CountingRunner(cloud_codex.Runner):
        def __call__(self, request):
            if not budget.take("codex"): return {"ok": False, "code": "usage"}
            ROUTES.append("codex-sub" if request.get("_sub") else "codex")
            request.pop("_sub", None)
            return super().__call__(request)

    runner = CountingRunner()

    class SubTransport(cloud_codex.CodexTransport):  # the Qwen budget is spent: the same request to Codex, no finance check
        def __call__(self, url, body, headers, timeout):
            data = json.loads(body)
            data["model"] = LIVE_ITP["model"]
            messages = data["messages"]
            system = "\n".join(m["content"] for m in messages if m["role"] == "system")
            parts = [p for m in messages if m["role"] == "user" for p in (m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}])]
            text = "\n".join(p["text"] for p in parts if p["type"] == "text")
            said = self.runner({"model": data["model"], "effort": self.effort, "instructions": system or text, "text": text if system else "",
                                "images": [p["image_url"]["url"] for p in parts if p["type"] == "image_url"], "timeout": min(timeout, 20), "_sub": True})
            if not (isinstance(said, dict) and said.get("ok") is True and isinstance(said.get("text"), str)):
                raise cloud_codex._Failed("codex-" + str(said.get("code") if isinstance(said, dict) else "hermes"))
            return 200, json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": said["text"]}}]}).encode()

    sub = SubTransport("low", runner)

    def guard(inner):
        def call(url, body, headers, timeout):
            if budget.take("qwen"):
                ROUTES.append("qwen")
                return inner(url, body, headers, timeout)
            return sub(url, body, headers, timeout)
        return call

    interp = host.interpreter_builder({"interpreter": LIVE_ITP}, worktree)()
    interp.primary.transport.runner = runner
    interp.fallback.transport = guard(interp.fallback.transport)
    labels = cloud_codex.reader(label_reader.LabelReader, LIVE_ITP, transport=cloud_codex.CodexTransport("low", runner))
    labels.fallback.transport = guard(labels.fallback.transport)
    answers = cloud_codex.reader(answer_reader.AnswerReader, LIVE_ITP, transport=cloud_codex.CodexTransport("low", runner))
    answers.fallback.transport = guard(answers.fallback.transport)
    return interp, labels, answers


# -- one case ----------------------------------------------------------------------------------------------------------
class Photos:
    def __init__(self): self.files = {}

    def fetch(self, provider_id, count): return [(PHOTOS / n).read_bytes() for n in self.files.get(provider_id, [])[:count]]


class Adapter:
    def __init__(self): self.sent = []

    def send(self, chat, text, attachments): self.sent.append({"chat": chat, "text": text, "attachments": list(attachments)})


def _full_site(wt):
    """The real storefront files the previewer needs (as test_publish_gate.real_previewer copies them), committed as the base."""
    for rel in testkit._git(REPO_ROOT, "ls-files", "storefront-mockup").splitlines():
        if not rel.startswith("storefront-mockup/assets/") and not (wt / rel).exists():
            (wt / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO_ROOT / rel, wt / rel)
    testkit._git(wt, "add", "-A")
    testkit._git(wt, "-c", "user.name=kit", "-c", "user.email=kit@example.invalid", "commit", "-q", "-m", "chaos: full fixture site")


def _real_assets(wt):
    site = REPO_ROOT / "storefront-mockup" / "assets"
    assets = wt / "storefront-mockup" / "assets"
    assets.unlink()
    (assets / "products").mkdir(parents=True)
    for entry in site.iterdir():
        if entry.name != "products": (assets / entry.name).symlink_to(entry)
    for entry in (site / "products").iterdir(): shutil.copyfile(entry, assets / "products" / entry.name)
    testkit._git(wt, "add", "-A")
    testkit._git(wt, "-c", "user.name=kit", "-c", "user.email=kit@example.invalid", "commit", "-q", "-m", "chaos: real assets/products")


def _illustration(_prompt, out, _timeout):  # stands in for gpt-image-2 (store-style picture); never a network call
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (800, 800), "#f2e9d7")
    ImageDraw.Draw(im).ellipse((220, 220, 580, 580), fill="#7aa35a", outline="#3d5a2a", width=6)
    im.save(out, "JPEG")
    return {"ok": True, "code": "ok"}


def _public_text(wt):
    try: return (wt / "storefront-mockup" / "catalog-products.js").read_text("utf-8")
    except OSError: return ""


def run_case(case, mode, out_dir, budget=None, preview=False):
    from hass.clover import cache, chat as clover_chat, sync
    from hass.tests.test_clover_client import fixture
    from hass.tests.test_editor import WriterRepo
    tape = Tape(case["id"], mode)
    clock = {"now": START}
    repo = WriterRepo()
    media_root = tempfile.mkdtemp(prefix="chaos-media-")
    case_dir = Path(out_dir) / case["id"]
    case_dir.mkdir(parents=True, exist_ok=True)
    try:
        wt = repo.wt
        _real_assets(wt)
        _full_site(wt)  # always: the draft codes hash the base commit, so replay must start from the tree the tapes were made on
        settings = {"ownerSenders": [OWNER], "ownerChat": CHAT, "approvalTtlSeconds": 3600, "interpreterDailyCap": 1000,
                    "liveSite": "fixture.example.invalid", "approvalNeedsCode": True, "mediaRoot": media_root, "itemIntake": True,
                    "skills": {"mode": "both"}}
        cfg = json.loads((repo.state / "config.json").read_text("utf-8"))
        editor_mod._write_json(repo.state / "config.json", {**cfg, "settings": settings})
        base = int(testkit._git(wt, "rev-list", "--count", "HEAD"))
        scratch = types.SimpleNamespace(_clock=lambda: clock["now"])
        editor = testkit._clocked_editor(scratch)(str(repo.state))
        real_interp = real_labels = real_answers = None
        # Built in BOTH modes (never called in replay): building the live route loads the content/registry the same way the
        # host does, and the draft codes depend on that; replay must start from the same process state as the recording.
        live = _live_route(str(wt), budget)
        if mode == "record": real_interp, real_labels, real_answers = live
        real_prev = None
        if mode == "record" and preview:
            from hass import preview as preview_mod
            real_prev = preview_mod.Previewer(wt, viewports=("phone",))  # env=None: it finds the pinned Playwright itself
            if isinstance(preview, str): real_prev.env["NODE"] = preview  # --node: the Node 22 the private previewer needs
        photos = Photos()
        conv = conversation.Conversation(str(repo.state), editor, TapedInterpreter(tape, real_interp), lambda: clock["now"],
                                         TapedPreviewer(tape, real_prev, case_dir), photos=photos, labels=TapedLabels(tape, real_labels))
        conv.answer_reader = TapedAnswers(tape, real_answers)
        conv.polish_transport = types.SimpleNamespace(generate=_illustration)
        rows, _ = sync.rows(fixture("items.json")["elements"], fixture("item_stocks.json")["elements"])
        cache.write_items(str(repo.state), rows, START - timedelta(minutes=5), cache.Identity(CLOVER["environment"], CLOVER["merchantId"]))
        conv.till = clover_chat.TillDesk(str(repo.state), CLOVER)
        adapter, turns, n = Adapter(), [], 0
        for turn in case["turns"]:
            n += 1
            tape.turn = n
            clock["now"] += timedelta(minutes=turn.get("gap_minutes", 1))
            words = turn["text"]
            if "{code}" in words or "{old_code}" in words:
                codes = [r["code"] for r in conv.db.execute("SELECT code FROM drafts ORDER BY row_id")]
                words = words.replace("{code}", codes[-1] if codes else "zzzz").replace("{old_code}", codes[0] if codes else "zzzz")
            pid = f"{case['id']}-{n}"
            if turn.get("photos"): photos.files[pid] = list(turn["photos"])
            msg = conversation.Inbound(pid, CHAT, STRANGER if turn.get("stranger") else OWNER, words, False, turn.get("kind", "new"),
                                       clock["now"].isoformat(), len(turn.get("photos", [])))
            before, calls_before = len(adapter.sent), len(tape.calls)
            started = time.monotonic()
            try:
                disposition = conv.handle(msg)
                conv.flush(adapter)
                error = None
            except Exception as exc:  # noqa: BLE001 - a crash is a finding, recorded and the case goes on
                disposition, error = "CRASH", f"{type(exc).__name__}: {exc}"[:300]
            seconds = time.monotonic() - started
            said = adapter.sent[before:]
            used = tape.calls[calls_before:]
            model_s = sum(c.get("seconds", 0) for c in used)
            turns.append({"n": n, "text": words, "photos": turn.get("photos", []), "stranger": bool(turn.get("stranger")),
                          "disposition": disposition, "error": error,
                          "replies": [voice.plain(s["text"]) for s in said], "attachments": [len(s["attachments"]) for s in said],
                          "seconds_local": round(seconds, 3), "seconds_model": round(model_s, 3),
                          "models": [{"method": c["method"], "route": c["route"], "backend": c["attrs"].get("last_backend"),
                                      "fallback": c["attrs"].get("last_fallback"), "error": c["attrs"].get("last_error"),
                                      "seconds": c.get("seconds")} for c in used]})
        commits = int(testkit._git(wt, "rev-list", "--count", "HEAD")) - base
        drafts = [dict(r) for r in conv.db.execute("SELECT code, state, summary, ops_json, base FROM drafts ORDER BY row_id")]
        public = _public_text(wt)
        products = json.loads(public.removeprefix("const catalog=").split(";\n", 1)[0])
        request = conv.requests.get(CHAT, clock["now"])
        intake = (request or {}).get("slots", {}).get("intake", {})
        conv.db.close()
        if mode == "record": tape.save()
        result = {"id": case["id"], "feature": case["feature"], "turns": turns, "commits": commits, "drafts": drafts,
                  "tape_misses": tape.misses, "pngs": sorted(str(p) for p in case_dir.glob("*.png"))}
        result["checks"] = check(case, result, public, products, intake)
        return result
    finally:
        repo.cleanup()
        shutil.rmtree(media_root, ignore_errors=True)


# -- checks ------------------------------------------------------------------------------------------------------------
def check(case, result, public, products, intake):
    """[(check id, passed, detail)]. Default rules for every case, then the case's own."""
    out = []
    want = case.get("checks", {})
    for t, spec in zip(result["turns"], case["turns"]):
        cid = f"t{t['n']}"
        if t["error"]: out.append((cid + ".crash", False, t["error"]))
        limit = spec.get("max_replies", 0 if spec.get("stranger") else 1)
        out.append((cid + ".replies", len(t["replies"]) <= limit, f"{len(t['replies'])} replies (max {limit})"))
        if not spec.get("stranger") and spec.get("min_replies", 1):
            out.append((cid + ".answered", len(t["replies"]) >= 1, f"{len(t['replies'])} replies"))
        joined = "\n".join(t["replies"]).lower()
        for s in spec.get("has_any", []) and [spec["has_any"]]:
            out.append((cid + ".has_any", any(x.lower() in joined for x in s), "wanted one of " + json.dumps(s)))
        for s in spec.get("lacks", []):
            out.append((cid + ".lacks:" + s, s.lower() not in joined, "must not say " + json.dumps(s)))
        if spec.get("no_echo") and t["text"].strip():  # owner words must never be pasted back into the listing
            out.append((cid + ".no_echo", t["text"].strip().lower() not in joined, "the owner's own message was copied into the reply/listing"))
        if "disposition" in spec:
            out.append((cid + ".disposition", t["disposition"] in spec["disposition"], f"{t['disposition']} not in {spec['disposition']}"))
        if "max_seconds" in spec:
            out.append((cid + ".speed", t["seconds_model"] <= spec["max_seconds"], f"model {t['seconds_model']} s > {spec['max_seconds']} s"))
    commits = want.get("commits", 0)
    out.append(("published", result["commits"] == commits, f"{result['commits']} publishes (want {commits})"))
    for s in want.get("public_lacks", []):
        out.append(("public_lacks:" + s, s.lower() not in public.lower(), "public catalog must not hold " + json.dumps(s)))
    for s in want.get("public_has", []):
        out.append(("public_has:" + s, s.lower() in public.lower(), "public catalog must hold " + json.dumps(s)))
    if "published_product" in want:
        expected = want["published_product"]
        matches = [p for p in products if p.get("name") == expected["name"]]
        out.append(("published_product", len(matches) == 1 and matches[0].get("sellingPrice") == expected["sellingPrice"],
                    "published product must have the edited selling price " + json.dumps(expected)))
    if "private_intake" in want:
        for key, value in want["private_intake"].items():
            out.append(("private_intake:" + key, intake.get(key) == value,
                        "saved private intake must match " + key + "=" + json.dumps(value)))
    if "drafts" in want:  # MAIN-RED: {state: [product names]} of the new-product drafts, and every draft has its own code
        out.append(("drafts_distinct", len({d["code"] for d in result["drafts"]}) == len(result["drafts"]),
                    "every draft must have its own code: " + json.dumps([d["code"] for d in result["drafts"]])))
        # blocking shape, independent of product names: exactly one draft per wanted name in each state, no other drafts,
        # and each draft is a single product.add
        shape = sorted(d["state"] for d in result["drafts"])
        wanted_shape = sorted(s for s, names in want["drafts"].items() for _ in names)
        adds = [sum(1 for op in json.loads(d["ops_json"]) if op.get("op") == "product.add") for d in result["drafts"]]
        out.append(("drafts_shape", shape == wanted_shape and all(n == 1 for n in adds),
                    f"drafts must be exactly {json.dumps(wanted_shape)} with one product.add each, got {json.dumps(shape)} / adds {json.dumps(adds)}"))
        for state, names in want["drafts"].items():
            got = sorted(op["args"].get("name", "") for d in result["drafts"] if d["state"] == state
                         for op in json.loads(d["ops_json"]) if op.get("op") == "product.add")
            out.append(("draft_products:" + state, got == sorted(names), f"{state} drafts must add {json.dumps(sorted(names))}, got {json.dumps(got)}"))
            seen = want.get("drafts_known_seen", {}).get(state)  # the one reproduced mismatch a known finding may excuse
            if seen is not None:
                out.append(("draft_products_known_shape:" + state, got in (sorted(names), sorted(seen)),
                            f"{state} drafts may only show the wanted {json.dumps(sorted(names))} or the reproduced {json.dumps(sorted(seen))}, got {json.dumps(got)}"))
    if "draft_card_turn" in want:
        turn = want["draft_card_turn"]
        replies = result["turns"][turn - 1]["replies"]
        marker = "All website card text:\n"
        cards = [s.split(marker, 1)[1].split("\nNothing changes until your yes.", 1)[0]
                 for s in replies if marker in s and "\nNothing changes until your yes." in s]
        adds = [op["args"] for d in result["drafts"] if d["state"] == "proposed"
                for op in json.loads(d["ops_json"]) if op.get("op") == "product.add"]
        def normalized(s): return " ".join(s.split())
        matched = False
        if len(cards) == 1 and len(adds) == 1:
            args, card = adds[0], cards[0]
            fields = [args.get(k) for k in ("name", "brand", "sellingPrice", "description")]
            if all(isinstance(v, str) and v.strip() for v in fields):
                name, brand, price, description = fields
                lines = [normalized(line) for line in card.splitlines() if line.strip()]
                matched = all(normalized(value) in lines for value in (name, brand, "$" + price)) and \
                    normalized(description) in normalized(card)
        out.append(("draft_card_matches", matched, "staged card must match the proposed product name, brand, price and description"))
    if "draft_public_lacks" in want:
        replies = result["turns"][-1]["replies"]
        marker = "All website card text:\n"
        cards = [s.split(marker, 1)[1].split("\nNothing changes until your yes.", 1)[0]
                 for s in replies if marker in s and "\nNothing changes until your yes." in s]
        proposed = [d for d in result["drafts"] if d["state"] == "proposed"]
        ops = [[{**op, "args": {k: v for k, v in op.get("args", {}).items() if k != "photo"}}
                for op in json.loads(d["ops_json"])] for d in proposed]
        out.append(("draft_public_exists", len(cards) == 1 and bool(ops), "expected a staged website card and proposed draft"))
        staged = json.dumps(ops, ensure_ascii=False).lower()
        for s in want["draft_public_lacks"]:
            out.append(("draft_public_lacks:" + s, len(cards) == 1 and bool(ops) and
                        s.lower() not in cards[0].lower() and s.lower() not in staged,
                        "staged website card and draft must not contain " + json.dumps(s)))
    if result["tape_misses"]: out.append(("tape", False, f"{result['tape_misses']} model call(s) not on the tape"))
    known = set(case.get("known", {}))
    return [{"id": c, "ok": ok, "detail": d, "known": c in known} for c, ok, d in out]


def verdict(result):
    bad = [c for c in result["checks"] if not c["ok"] and not c["known"]]
    fixed = [c for c in result["checks"] if c["ok"] and c["known"]]
    return bad, fixed


def load_cases(ids=None):
    cases = [c for c in json.loads(CASES.read_text("utf-8")) if "turns" in c]
    if ids: cases = [c for c in cases if c["id"] in set(ids)]
    return cases


def _fan_out(args, out):
    """--jobs N: round-robin the cases over N child processes of this script, then merge their results in case order."""
    import subprocess
    ids = [c["id"] for c in load_cases(args.case)]
    procs = []
    for j in range(args.jobs):
        mine = ids[j::args.jobs]
        if not mine: continue
        cmd = [sys.executable, "-B", str(Path(__file__).resolve()), "--out", str(out), "--part", f"part-{j}.json",
               "--max-codex", str(args.max_codex), "--max-qwen", str(args.max_qwen)]
        cmd += ["--record"] if args.record else []
        cmd += ["--preview"] if args.preview else []
        cmd += ["--node", args.node] if args.node else []
        for i in mine: cmd += ["--case", i]
        procs.append(subprocess.Popen(cmd))
    codes = [p.wait() for p in procs]
    merged = {}
    for j in range(args.jobs):
        part = out / f"part-{j}.json"
        if part.exists():
            for r in json.loads(part.read_text("utf-8")): merged[r["id"]] = r
    results = [merged[i] for i in ids if i in merged]
    (out / "results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"hass-chaos: merged {len(results)}/{len(ids)} cases from {len(procs)} jobs; worker exits {codes}")
    return 0 if all(c == 0 for c in codes) and len(results) == len(ids) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--case", action="append")
    ap.add_argument("--out")
    ap.add_argument("--max-codex", type=int, default=150)
    ap.add_argument("--max-qwen", type=int, default=20)
    ap.add_argument("--node", help="with --preview: path of the Node 22 binary (sets NODE for the previewer only)")
    ap.add_argument("--jobs", type=int, default=1, help="run the cases in N worker processes (same --out, shared budgets)")
    ap.add_argument("--part", help=argparse.SUPPRESS)  # a --jobs worker's own results file name
    args = ap.parse_args(argv)
    out = Path(args.out or tempfile.mkdtemp(prefix="hass-chaos-"))
    out.mkdir(parents=True, exist_ok=True)
    if args.jobs > 1:
        return _fan_out(args, out)
    budget = Budget(out / "budget.json", args.max_codex, args.max_qwen) if args.record else None
    if args.record: CACHE.path = out / "read-cache.json"
    preview = (args.node or True) if args.preview else False
    results, bad_total, fixed_total = [], 0, 0
    for case in load_cases(args.case):
        r = run_case(case, "record" if args.record else "replay", out, budget, preview)
        bad, fixed = verdict(r)
        bad_total, fixed_total = bad_total + len(bad), fixed_total + len(fixed)
        results.append(r)
        known_bad = [c for c in r["checks"] if not c["ok"] and c["known"]]
        print(f"{case['id']}: {'ok' if not bad and not known_bad else 'FAIL ' + ', '.join(c['id'] for c in bad) if bad else 'known failure: ' + ', '.join(c['id'] for c in known_bad)}"
              f"{' fixed: ' + ', '.join(c['id'] for c in fixed) if fixed else ''}", flush=True)
    name = args.part or ("results.json" if not args.case or len(args.case) != 1 else f"results-{args.case[0]}.json")
    (out / name).write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n", "utf-8")
    print(f"hass-chaos: cases={len(results)} unexpected_failures={bad_total} known_now_passing={fixed_total} out={out}")
    return 0 if bad_total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

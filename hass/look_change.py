"""HASS-SITE-LOOK-1: a website look-change draft from one owner request (PLAN-v2 D; no chat wiring, nothing published).

    python3 -B hass/look_change.py --repo WRITER_REPO --code CODE --ledger FILE --out DIR < request.txt

The request (stdin, never argv) and the six public design files at the writer repo's HEAD go to the Codex runner
(cloud_codex.Runner, gpt-6.1-sol, effort medium), which returns a unified diff; nothing else is sent. look_guard checks it;
it is applied in a temporary detached worktree of the writer repo (never the writer's checkout, never the live site), the
repo's own sitegen regenerates the pages, the result is committed there, and design_check, the site tests, house_style verify
and design_preview's four captures must pass. Only then is branch look/CODE made at that commit. Any failure prints
{"result": "refused:<reason>"} and leaves the writer's worktree, HEAD and branches as they were. At most 3 drafts (Codex
calls) a day, counted in --ledger; the release dailyCap/minIntervalSeconds still apply when a draft is published.
Prints ONE JSON line. Exit 0 ok, 1 refused."""
from __future__ import annotations

import argparse, contextlib, datetime, json, os, re, subprocess, sys, tempfile  # noqa: E401
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hass import cloud_codex, design_check, design_preview, look_guard  # noqa: E402

MODEL, EFFORT, DAILY = "gpt-6.1-sol", "medium", 3
TIMEOUT = 20  # PLAN-v2 says 120 s, but cloud_codex_hermes accepts 5-20 s only: the runner's own ceiling
CODE = re.compile(r"[a-z0-9][a-z0-9-]{0,23}")
SITE_TESTS = ("hass.tests.test_publish", "hass.tests.test_content", "hass.tests.test_style_no_commerce")
INSTRUCTIONS = ("You change the look of the Avocado Shack website. Answer with ONLY a unified diff (a/ and b/ paths) editing only "
                + ", ".join(look_guard.MODEL_FILES) + ". Never add a script, form, input, iframe, embed or object, an on*= "
                "attribute, a javascript: or off-site URL, or change a <head>, <meta> or <link> line. Keep every {{slot}}. Add no "
                "new words about the shop, its goods or prices.")


class Refused(Exception):
    pass


def git(top, *args, data=None) -> str:
    done = subprocess.run(["git", "-C", str(top), *args], input=data, capture_output=True, text=True,
                          env=dict(os.environ, GIT_OPTIONAL_LOCKS="0"))
    if done.returncode: raise Refused("apply" if args[0] == "apply" else "git")
    return done.stdout


def step(work, reason, *args) -> None:
    if subprocess.run([sys.executable, "-B", *args], cwd=work, capture_output=True).returncode: raise Refused(reason)


def charge(ledger: Path, today: str) -> None:
    """One draft counted for today before its Codex call; the fourth of a day is refused."""
    try: days = json.loads(ledger.read_text("utf-8"))
    except FileNotFoundError: days = []
    except ValueError: raise Refused("cap") from None
    days = [d for d in days if d == today] if isinstance(days, list) else None
    if days is None or len(days) >= DAILY: raise Refused("cap")
    ledger.with_name(ledger.name + ".tmp").write_text(json.dumps(days + [today]), "utf-8")
    os.replace(ledger.with_name(ledger.name + ".tmp"), ledger)


def ask(runner, request: str, files: dict) -> str:
    said = runner({"model": MODEL, "effort": EFFORT, "instructions": INSTRUCTIONS, "images": [], "timeout": TIMEOUT,
                   "text": "Request: " + request + "".join(f"\n\n=== {p} ===\n{b}" for p, b in files.items())})
    if not (isinstance(said, dict) and said.get("ok") is True and isinstance(said.get("text"), str)): raise Refused("codex")
    lines = said["text"].replace("\r\n", "\n").split("\n")
    body = lines[next((i for i, x in enumerate(lines) if x.startswith(("diff --git ", "--- "))), len(lines)):]
    while body and body[-1].strip() in ("", "```"): body.pop()
    if not body: raise Refused("empty")
    return "\n".join(body) + "\n"


def build(work: Path, diff: str, request: str, base: str, out: str, previewer) -> tuple[str, list]:
    """In the temporary worktree: apply, generate, re-guard what landed, commit, check and capture -> (head, captures)."""
    git(work, "apply", "--whitespace=nowarn", "-", data=diff)
    step(work, "generate", "hass/sitegen.py", "--write")
    if again := look_guard.check(git(work, "diff", base, "--", *look_guard.MODEL_FILES), request): raise Refused(again)
    git(work, "add", "-A")
    git(work, "-c", "user.name=Hass", "-c", "user.email=hass@localhost", "commit", "-q", "-m", "look draft")
    head = git(work, "rev-parse", "HEAD").strip()
    if design_check.check(base, head, str(work))[1]: raise Refused("design_check")
    step(work, "site_tests", "-m", "unittest", "-q", *SITE_TESTS)
    step(work, "house_style", "hass/house_style.py", "verify")
    with contextlib.chdir(work):
        code, doc = design_preview.run(base, head, out, previewer)
    if code or len(doc["captures"]) != 4: raise Refused("preview")
    return head, doc["captures"]


def draft(repo, code: str, request: str, ledger, out: str, runner=None, previewer=None, today=None) -> dict:
    repo = Path(repo).resolve()
    try:
        if not CODE.fullmatch(code or "") or not request.strip(): raise Refused("usage")
        if git(repo, "branch", "--list", "look/" + code).strip(): raise Refused("branch")
        base = git(repo, "rev-parse", "--verify", "HEAD^{commit}").strip()
        files = {p: git(repo, "show", f"{base}:{p}") for p in look_guard.MODEL_FILES}
        charge(Path(ledger), today or datetime.date.today().isoformat())
        diff = ask(runner or cloud_codex.Runner(), request, files)
        if reason := look_guard.check(diff, request): raise Refused(reason)
        with tempfile.TemporaryDirectory(prefix="hass-look-") as tmp:
            work = Path(tmp, "w")
            git(repo, "worktree", "add", "-q", "--detach", str(work), base)
            try: head, captures = build(work, diff, request, base, out, previewer)
            finally:
                subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(work)], capture_output=True)
                subprocess.run(["git", "-C", str(repo), "worktree", "prune"], capture_output=True)
        git(repo, "branch", "look/" + code, head)
    except Refused as exc: return {"result": f"refused:{exc}"}
    except design_check.Usage: return {"result": "refused:check"}
    except OSError: return {"result": "refused:io"}
    return {"result": "ok", "branch": "look/" + code, "base": base, "head": head, "captures": captures}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Draft a website look change on a private branch.")
    for flag in ("--repo", "--code", "--ledger", "--out"): ap.add_argument(flag, required=True)
    a = ap.parse_args(argv)
    print(json.dumps(doc := draft(a.repo, a.code, sys.stdin.read(), a.ledger, a.out)))
    return 0 if doc["result"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())

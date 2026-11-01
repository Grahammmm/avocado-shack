"""Install one applied change into the running website directory (SHOP-2).

    python3 hass/editor.py install CHANGE_ID --state DIR

Separate, checkable step after `apply`; the approval flow is unchanged. Only an `applied`, not-reverted change whose
commit is `hass content: <change_id>` installs. The files come FROM THE COMMIT (git blobs), never from the live
worktree: the site paths that commit added or modified, mapped from `storefront-mockup/` onto `settings.site_dir`.
Each file is staged in its target folder, fsynced and os.replace()d; the set is read back by SHA-256 and any
mismatch or error restores every previous byte. The outcome is stored as `install` in `<state>/changes/<id>.json`.
Writes nothing outside site_dir and that record. No network, no restart.
"""
import hashlib, os, re, subprocess, tempfile  # noqa: E401
from pathlib import Path

from hass import editor, sitegen
from hass.content_model import IMAGE_RE

PREFIX, TMP_PREFIX = sitegen.SITE_PREFIX, ".hass-install-"

def _blob(wt: Path, spec: str) -> bytes | None:
    out = subprocess.run(["git", "-C", str(wt), "cat-file", "blob", spec], capture_output=True)
    return out.stdout if out.returncode == 0 else None

def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents

def site_problem(raw, wt: Path, sdir: Path) -> str | None:
    """Why `raw` cannot be the install target (None if it can). Checked before any write."""
    if not raw or not isinstance(raw, str): return "settings.site_dir is not set"
    if not os.path.isabs(raw): return "site_dir must be an absolute path"
    if os.path.islink(raw) or Path(raw).resolve() != Path(os.path.normpath(raw)):
        return "site_dir must not be a symlink"
    site = Path(raw).resolve()
    if not site.is_dir(): return "site_dir does not exist"
    for root, what in ((wt.resolve(), "the writer worktree"), (editor._common_dir(wt), "the Git directory"),
                       (sdir.resolve(), "the state dir")):
        if _inside(site, root) or _inside(root, site): return f"site_dir must lie outside {what}"
    return None

def _site_paths(wt: Path, commit: str) -> tuple[list[str], str | None]:
    """Site files the commit added or modified (generated files and product photos only)."""
    out = editor._git(wt, "diff-tree", "-r", "--no-commit-id", "--name-status", f"{commit}^", commit, "--", PREFIX)
    if out.returncode: return [], "the change commit cannot be read"
    paths = []
    for line in out.stdout.splitlines():
        status, _, rel = line.partition("\t")
        if status not in ("A", "M") or not (rel in editor.GENERATED_PATHS or IMAGE_RE.fullmatch(rel[len(PREFIX):])):
            return [], f"the change commit has an unexpected site change: {status} {rel}"
        paths.append(rel)
    return sorted(paths), None if paths else "the change commit has no site files"

def _swap(tmp: str, target: Path) -> None:
    os.replace(tmp, target)

def _put(target: Path, data: bytes, mode: int) -> None:
    fd, tmp = tempfile.mkstemp(prefix=TMP_PREFIX, suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        _swap(tmp, target)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise

def _current(target: Path) -> bytes | None:
    if os.path.islink(target): raise OSError("site file is a symlink")
    return target.read_bytes() if target.is_file() else None

def _later_installed(sdir: Path, wt: Path, change_id: str, commit: str) -> str | None:
    for path in sorted((sdir / "changes").glob("chg-*.json")):
        inst = (editor._read(path) if path.stem != change_id else {}).get("install") or {}
        other = inst.get("commit") if inst.get("state") == "installed" else None
        if other and other != commit and editor._git(wt, "merge-base", "--is-ancestor", commit, other).returncode == 0:
            return path.stem
    return None

def install(change_id, *, state=None, now=None) -> dict:
    sdir, cfg, wt = editor._load(state)
    if not editor.CHANGE_ID_RE.fullmatch(str(change_id)): return {"result": "invalid", "problems": ["malformed change id"]}
    with editor._writer_lock(sdir) as held:
        return _install_locked(sdir, cfg, wt, change_id, now) if held else {"result": "busy"}

def _install_locked(sdir, cfg, wt, change_id, now) -> dict:
    rec_path = sdir / "changes" / f"{change_id}.json"
    rec = editor._read(rec_path) if rec_path.is_file() else None
    refuse = ("unknown change id" if rec is None and not (sdir / "drafts" / f"{change_id}.json").is_file()
              else "the change is not applied" if rec is None or rec.get("state") != "applied"
              else f"the change was reverted by {rec['revertedBy']}" if rec.get("revertedBy") else None)
    commit = (rec or {}).get("commit") or ""
    if not refuse and (not re.fullmatch(r"[0-9a-f]{40,64}", str(commit)) or editor._out(
            wt, "log", "-1", "--format=%s", commit, "--") != f"hass content: {change_id}"):
        refuse = "the change commit is not in the writer worktree"
    if refuse: return {"result": "refused", "reason": refuse}
    if problem := site_problem(cfg.get("settings", {}).get("site_dir"), wt, sdir):
        return {"result": "refused", "reason": problem}
    paths, problem = _site_paths(wt, commit)
    if problem: return {"result": "refused", "reason": problem}
    site = Path(cfg["settings"]["site_dir"]).resolve()
    want = {rel: _blob(wt, f"{commit}:{rel}") for rel in paths}
    if None in want.values(): return {"result": "refused", "reason": "the change commit cannot be read"}
    targets = {rel: site / rel[len(PREFIX):] for rel in paths}
    for rel in paths: sitegen._check_folders(site, rel[len(PREFIX):])
    prev = {rel: _current(targets[rel]) for rel in paths}
    done = {"commit": commit, "files": len(paths)}
    if (rec.get("install") or {}).get("state") == "installed" and rec["install"].get("commit") == commit \
            and all(prev[r] == want[r] for r in paths):
        return {"result": "already_installed", "change_id": change_id, **done}
    if later := _later_installed(sdir, wt, change_id, commit):
        return {"result": "refused", "reason": f"a later change is already installed: {later}"}
    modes = {rel: targets[rel].stat().st_mode & 0o777 if prev[rel] is not None else 0o644 for rel in paths}
    reason = None
    try:
        for rel in paths:
            targets[rel].parent.mkdir(parents=True, exist_ok=True)
            for stale in targets[rel].parent.glob(TMP_PREFIX + "*.tmp"): stale.unlink(missing_ok=True)
            _put(targets[rel], want[rel], modes[rel])
        bad = [rel for rel in paths if hashlib.sha256(_current(targets[rel]) or b"").digest()
               != hashlib.sha256(want[rel]).digest()]
        reason = f"readback mismatch: {bad[0]}" if bad else None
    except OSError as exc:
        reason = f"write failed: {type(exc).__name__}"
    if reason:
        for rel in paths:  # roll back every file to the bytes it had before this call
            if prev[rel] is None: targets[rel].unlink(missing_ok=True)
            elif _current(targets[rel]) != prev[rel]: _put(targets[rel], prev[rel], modes[rel])
        result = {"state": "failed", "reason": reason, "failed_at": editor._now(now), "commit": commit}
    else:
        result = {"state": "installed", "installed_at": editor._now(now), **done}
    editor._write_json(rec_path, {**rec, "install": result})
    return {"result": result["state"], "change_id": change_id, **{k: v for k, v in result.items() if k != "state"}}

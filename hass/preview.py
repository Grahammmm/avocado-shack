"""Hass private screenshot preview (H06): an isolated loopback copy of the site, phone + desktop captures.

    Previewer(worktree).capture(files, target, out_png) -> {"ok", "png", "checks", "error", "desktopPng"}

The copy holds the worktree's tracked ``storefront-mockup`` files (assets symlinked, not copied) with ``files``
(generated path -> bytes) laid over them. Its own ``community-server.py`` serves it on a free 127.0.0.1 port with a
fresh empty temp database and a minimal environment; ``hass/screenshot.cjs`` captures and checks the target page.
The server is always stopped and the copy removed. Screenshots are written 0600; nothing is published or sent.
"""
import http.client, json, os, shutil, socket, subprocess, sys, tempfile, time  # noqa: E401
from pathlib import Path, PurePosixPath

SCRIPT = Path(__file__).resolve().parent / "screenshot.cjs"
SITE, ASSETS = "storefront-mockup", "storefront-mockup/assets"
VIEWPORTS = ("phone", "desktop")
PASS_THROUGH = ("PLAYWRIGHT_MODULE", "CHROMIUM_PATH")
START_TIMEOUT, CAPTURE_TIMEOUT = 10.0, 90


def target_for(record: dict) -> dict:
    """The screenshot target for a touched record (the after value decides what the checks expect)."""
    after, collection = record.get("after") or {}, record.get("collection")
    if collection == "products":
        return {"kind": "product", "id": record.get("key"), "name": after.get("name", ""),
                "status": after.get("status"), "description": after.get("description")}
    if collection == "makers":
        return {"kind": "maker", "key": record.get("key"), "name": after.get("name") or "",
                "place": after.get("place") or "", "hidden": "hidden" in after}
    if collection == "store":
        return {"kind": "store", "hours": list(after.get("hours") or []),
                "streetAddress": after.get("streetAddress", ""), "town": after.get("town", "")}
    event = collection == "events"  # a hike: its key and recap let the check find it in past hikes / RSVP buttons
    return {"kind": "event", "title": after.get("title", ""), "status": after.get("status") if event else None,
            "id": (record.get("key") or "") if event else "", "recap": (after.get("recap") or "") if event else ""}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get_ok(port: int) -> bool:
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
        conn.request("GET", "/")
        ok = conn.getresponse().status == 200
        conn.close()
        return ok
    except OSError:
        return False


def _write_private(path: Path, data: bytes) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, 0o600)


def _write_overlay(tmp: Path, files: dict) -> None:
    """Lay ``files`` over the copy: every key is checked before any is written, and no link is ever written through."""
    root, plan = tmp.resolve(), []
    for rel, data in files.items():
        parts = PurePosixPath(rel).parts
        if len(parts) < 2 or parts[0] != SITE or ".." in parts:
            raise ValueError(f"preview file outside the site: {rel}")
        if parts[:2] == (SITE, "assets"):
            raise ValueError(f"preview file inside the linked assets folder: {rel}")
        path = ancestor = tmp.joinpath(*parts)
        while not os.path.lexists(ancestor):
            ancestor = ancestor.parent
        if not ancestor.resolve().is_relative_to(root):
            raise ValueError(f"preview file resolves outside the copy: {rel}")
        plan.append((path, data))
    for path, data in plan:
        path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return (lines[-1] if lines else "no output")[:200]


def _checks(stdout: str) -> dict | None:
    """The last stdout line's ``checks`` when it is a non-empty object of str -> bool; else None (bad output)."""
    lines = [line for line in (stdout or "").splitlines() if line.strip()]
    try:
        doc = json.loads(lines[-1]) if lines else None
    except (ValueError, RecursionError):
        return None
    checks = doc.get("checks") if isinstance(doc, dict) else None
    good = isinstance(checks, dict) and checks and all(type(k) is str and type(v) is bool for k, v in checks.items())
    return checks if good else None


class Previewer:
    def __init__(self, worktree, env=None, viewports=VIEWPORTS):
        self.viewports = tuple(viewports)
        self.worktree = Path(worktree).resolve()
        self.env = dict(os.environ if env is None else env)
        self.last_server = None  # {"pid", "port"} of the most recent preview server (for checks)

    def capture(self, files, target, out_png) -> dict:
        """Never raises: any failure comes back as ok False with a short error."""
        try:
            return self._capture(dict(files), dict(target), Path(out_png))
        except Exception as exc:  # noqa: BLE001 - the caller reports the error; a preview never blocks a reply
            return {"ok": False, "png": None, "checks": {}, "error": f"{type(exc).__name__}: {exc}"[:200]}

    def _copy_site(self, tmp: Path, files: dict) -> Path:
        listed = subprocess.run(["git", "-C", str(self.worktree), "ls-files", "-z", SITE],
                                capture_output=True, check=True).stdout.decode("utf-8").split("\0")
        for rel in filter(None, listed):
            if rel != ASSETS and not rel.startswith(ASSETS + "/"):
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.worktree / rel, tmp / rel)
        site = tmp / SITE
        site.mkdir(exist_ok=True)
        (site / "assets").symlink_to((self.worktree / ASSETS).resolve(), target_is_directory=True)
        _write_overlay(tmp, files)
        return site

    def _capture(self, files: dict, target: dict, out_png: Path) -> dict:
        if self.viewports not in (("phone",), VIEWPORTS):
            raise ValueError(f"unsupported viewports {self.viewports!r}"[:80])
        with tempfile.TemporaryDirectory(prefix="hass-preview-") as raw:
            tmp = Path(raw)
            site = self._copy_site(tmp, files)
            port, base = _free_port(), {k: self.env.get(k, "") for k in ("PATH", "HOME")}
            server_env = {**base, "AVOSHACK_COMMUNITY_DB": str(tmp / "fixture.sqlite3"),
                          "AVOSHACK_COMMUNITY_CONFIG": str(site / "community.json")}
            server = subprocess.Popen([sys.executable, str(site / "community-server.py"), "--port", str(port)],
                                      cwd=tmp, env=server_env, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.last_server = {"pid": server.pid, "port": port}
            runs = []  # (viewport, shot, checks or None when the run failed, failure text); phone first
            try:
                deadline = time.monotonic() + START_TIMEOUT
                while not _get_ok(port):
                    if server.poll() is not None or time.monotonic() > deadline:
                        return {"ok": False, "png": None, "checks": {}, "error": "preview server did not start"}
                    time.sleep(0.1)
                for name in self.viewports:
                    shot = tmp / ("shot.png" if name == "phone" else f"shot-{name}.png")
                    node_env = {**base, "PREVIEW_URL": f"http://127.0.0.1:{port}", "TARGET": json.dumps(target),
                                "OUT": str(shot), "VIEWPORT": name,
                                **{k: self.env[k] for k in PASS_THROUGH if self.env.get(k)}}
                    try:
                        proc = subprocess.run(["node", str(SCRIPT)], env=node_env, cwd=tmp, capture_output=True,
                                              text=True, timeout=CAPTURE_TIMEOUT)
                        ran = not proc.returncode and shot.is_file()
                        checks = _checks(proc.stdout) if ran else None
                        failure = None if checks is not None else (
                            "bad checks output" if ran else _last_line(proc.stderr or proc.stdout))
                    except Exception as exc:  # noqa: BLE001 - a desktop timeout/crash keeps the phone result
                        if name == "phone":
                            raise
                        checks, failure = None, f"{type(exc).__name__}: {exc}"[:200]
                    runs.append((name, shot, checks, failure))
                    if checks is None or any(passed is not True for passed in checks.values()):
                        break  # a failed phone run is reported as before; desktop is not run
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
            _name, shot, checks, failure = runs[0]
            if checks is None:
                return {"ok": False, "png": None, "checks": {}, "error": failure}
            _write_private(out_png, shot.read_bytes())
            error, extra = None, ({"desktopPng": None} if "desktop" in self.viewports else {})
            for _name, shot, more, failure in runs[1:]:
                if more is None:
                    error = "desktop: " + failure
                    continue
                extra["desktopPng"] = str(out_png.with_name(out_png.stem + "-desktop.png"))
                _write_private(Path(extra["desktopPng"]), shot.read_bytes())
                checks = {**checks, **{f"desktop:{key}": passed for key, passed in more.items()}}
        failed = sorted(name for name, passed in checks.items() if passed is not True)
        error = error or (("check failed: " + ", ".join(failed)) if failed else None)
        return {"ok": error is None, "png": str(out_png), "checks": checks, "error": error, **extra}

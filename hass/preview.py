"""Hass private screenshot preview (H06): an isolated loopback copy of the site, one phone-width Playwright capture.

    Previewer(worktree).capture(files, target, out_png) -> {"ok", "png", "checks", "error"}

The copy holds the worktree's tracked ``storefront-mockup`` files (assets symlinked, not copied) with ``files``
(generated path -> bytes) laid over them. Its own ``community-server.py`` serves it on a free 127.0.0.1 port with a
fresh empty temp database and a minimal environment; ``hass/screenshot.cjs`` captures and checks the target page.
The server is always stopped and the copy removed. Screenshots are written 0600; nothing is published or sent.
"""
import http.client, json, os, shutil, socket, subprocess, sys, tempfile, time  # noqa: E401
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "screenshot.cjs"
SITE, ASSETS = "storefront-mockup", "storefront-mockup/assets"
PASS_THROUGH = ("PLAYWRIGHT_MODULE", "CHROMIUM_PATH")
START_TIMEOUT, CAPTURE_TIMEOUT = 10.0, 90


def target_for(record: dict) -> dict:
    """The screenshot target for a touched record (the after value decides what the checks expect)."""
    after, collection = record.get("after") or {}, record.get("collection")
    if collection == "products":
        return {"kind": "product", "id": record.get("key"), "name": after.get("name", ""),
                "status": after.get("status"), "description": after.get("description")}
    if collection == "makers":
        return {"kind": "maker", "name": after.get("name", "")}
    if collection == "store":
        return {"kind": "store", "hours": list(after.get("hours") or [])}
    return {"kind": "event", "title": after.get("title", ""),
            "status": after.get("status") if collection == "events" else None}


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


def _last_line(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return (lines[-1] if lines else "no output")[:200]


class Previewer:
    def __init__(self, worktree, env=None):
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
        for rel, data in files.items():
            if not rel.startswith(SITE + "/") or ".." in Path(rel).parts:
                raise ValueError(f"preview file outside the site: {rel}")
            (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp / rel).write_bytes(data)
        return site

    def _capture(self, files: dict, target: dict, out_png: Path) -> dict:
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
            try:
                deadline = time.monotonic() + START_TIMEOUT
                while not _get_ok(port):
                    if server.poll() is not None or time.monotonic() > deadline:
                        return {"ok": False, "png": None, "checks": {}, "error": "preview server did not start"}
                    time.sleep(0.1)
                shot = tmp / "shot.png"
                node_env = {**base, "PREVIEW_URL": f"http://127.0.0.1:{port}", "TARGET": json.dumps(target),
                            "OUT": str(shot), **{k: self.env[k] for k in PASS_THROUGH if self.env.get(k)}}
                proc = subprocess.run(["node", str(SCRIPT)], env=node_env, cwd=tmp, capture_output=True,
                                      text=True, timeout=CAPTURE_TIMEOUT)
            finally:
                server.terminate()
                try:
                    server.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()
            if proc.returncode or not shot.is_file():
                return {"ok": False, "png": None, "checks": {}, "error": _last_line(proc.stderr or proc.stdout)}
            checks = json.loads(proc.stdout.strip().splitlines()[-1]).get("checks", {})
            _write_private(out_png, shot.read_bytes())
        failed = sorted(name for name, passed in checks.items() if passed is not True)
        return {"ok": not failed, "png": str(out_png), "checks": checks,
                "error": ("check failed: " + ", ".join(failed)) if failed else None}

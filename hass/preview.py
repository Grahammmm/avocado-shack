"""Hass private screenshot preview (H06): an isolated loopback copy of the site, phone + desktop captures.

    Previewer(worktree).capture(files, target, out_png) -> {"ok", "png", "checks", "error", "desktopPng"}

The copy holds the worktree's tracked ``storefront-mockup`` files (assets symlinked, not copied) with ``files``
(generated path -> bytes) laid over them. Its own ``community-server.py`` serves it on a free 127.0.0.1 port with a
fresh empty temp database and a minimal environment; ``hass/screenshot.cjs`` captures and checks the target page.
The server is always stopped and the copy removed. Screenshots are written 0600; nothing is published or sent.
A damaged change record gives the target ``{"kind": "unreadable"}``, refused before any copy or server.
"""
import http.client, json, os, shutil, socket, stat, subprocess, sys, tempfile, time  # noqa: E401
from pathlib import Path, PurePosixPath

from hass.content_model import DEFAULT_INTRO, shop_today
from hass.notice import live_text
SCRIPT = Path(__file__).resolve().parent / "screenshot.cjs"
SITE, ASSETS = "storefront-mockup", "storefront-mockup/assets"
VIEWPORTS = ("phone", "desktop")
PASS_THROUGH = ("PLAYWRIGHT_MODULE", "CHROMIUM_PATH")
START_TIMEOUT, CAPTURE_TIMEOUT = 10.0, 90


_FIELDS = {"products": ("name", "status", "description"), "makers": ("name", "place"),
           "store": ("streetAddress", "town"), "events": ("title", "status", "recap")}


def _readable(record) -> bool:
    """A dict record, a dict/None after, a text/None key and text/None read fields (store hours: a list of text)."""
    after = record.get("after") if isinstance(record, dict) else []
    after = {} if after is None else after
    if not isinstance(after, dict) or not isinstance(record.get("key"), (str, type(None))):
        return False
    collection = record.get("collection") if isinstance(record.get("collection"), str) else ""
    if collection == "store" and not isinstance(record.get("before"), (dict, type(None))):
        return False
    hours = after.get("hours") if collection == "store" else None
    if not (hours is None or isinstance(hours, list) and all(isinstance(h, str) for h in hours)):
        return False
    headline = after.get("headline") if collection == "store" else None
    if not (headline is None or isinstance(headline, list) and all(isinstance(h, str) for h in headline)):
        return False
    if collection == "store" and not all(isinstance(after.get(k), (str, type(None))) for k in ("story", "intro")):
        return False
    home = after.get("homeImage") if collection == "store" else None
    if not (home is None or isinstance(home, dict) and isinstance(home.get("image"), (str, type(None)))):
        return False
    notice = after.get("notice") if collection == "store" else None
    if not (notice is None or isinstance(notice, dict) and isinstance(notice.get("text"), (str, type(None)))):
        return False
    return all(isinstance(after.get(name), (str, type(None))) for name in _FIELDS.get(collection, ("title",)))


def target_for(record: dict, today=None, *, store=None) -> dict:
    """The screenshot target for a touched record (the after value decides what the checks expect).
    AV1222-02: with ``store`` an active product also expects sitegen's own availability word (str or None) and a
    changed photo expects its new src; ``today`` is the generation date of the files being checked."""
    if not _readable(record):
        return {"kind": "unreadable"}
    after, collection = record.get("after") or {}, record.get("collection")
    if collection == "products":
        target = {"kind": "product", "id": record.get("key"), "name": after.get("name", ""),
                  "status": after.get("status"), "description": after.get("description")}
        before = record.get("before")
        if after.get("status") == "active":  # a hidden product is only checked for being absent
            if store is not None:
                from hass.sitegen import availability_label  # the one place the word and the stale rule live
                target["availability"] = availability_label(after, store, today or shop_today())
            if isinstance(before, dict) and before.get("image") != after.get("image") and isinstance(after.get("image"), str):
                target["image"] = after["image"]
        return target
    if collection == "makers":
        return {"kind": "maker", "key": record.get("key"), "name": after.get("name") or "",
                "place": after.get("place") or "", "hidden": "hidden" in after}
    if collection == "store":
        from hass.sitegen import checked_line, phone_text  # lazy: sitegen is the one place the selection words live
        before = record.get("before") or {}
        line = ({"selectionLine": checked_line(after, today)} if today is not None and
                before.get("selection_checked_on") != after.get("selection_checked_on") else {})  # AV1222-03
        cleared = bool((record.get("before") or {}).get("homeImage")) and "homeImage" not in after  # shop photo back
        phone = ({"phone": phone_text(after["phone"]) if after.get("phone") else None}
                 if before.get("phone") != after.get("phone") else {})  # AV1222-04
        return {"kind": "store", **phone, **({"homeImageCleared": True} if cleared else {}), "hours": list(after.get("hours") or []),
                "streetAddress": after.get("streetAddress", ""), "town": after.get("town", ""),
                "headline": list(after.get("headline") or []), "story": after.get("story"),
                "intro": after.get("intro"), **line,
                "homeImage": (after.get("homeImage") or {}).get("image"), "notice": live_text(after.get("notice"), today)}
    if collection == "routeIdeas":  # AV1222-06: /hike shows a route title only on a linked hike's Route line or the sample invitation
        return {"kind": "route", "id": record.get("key") or "", "title": after.get("title", ""), "hidden": after.get("status") == "hidden"}
    event = collection == "events"  # a hike: its key and recap let the check find it in past hikes / RSVP buttons
    target = {"kind": "event", "title": after.get("title", ""), "status": after.get("status") if event else None,
              "id": (record.get("key") or "") if event else "", "recap": (after.get("recap") or "") if event else ""}
    if event and after.get("status") == "scheduled":  # AV1222-05: the card's date, Meet and places lines, and AV0207-01 fields
        before, cap = record.get("before") or {}, after.get("capacity")
        target.update(startsAt=after.get("startsAt"), meetingPoint=after.get("meetingPoint") or "",
                      capacity=cap if isinstance(cap, int) and not isinstance(cap, bool) else None,
                      rsvpEnabled=after.get("rsvpEnabled") is True,
                      changed={k: after[k] for k in ("meetTime", "meetingAddress", "returnTime", "walkTime")
                               if isinstance(after.get(k), str) and after[k].strip() and before.get(k) != after[k]})
        cleared = [k for k in ("meetTime", "meetingAddress", "returnTime", "walkTime")  # removed: the labeled line must be gone
                   if isinstance(before.get(k), str) and before[k].strip() and not (isinstance(after.get(k), str) and after[k].strip())]
        if cleared:
            target["cleared"] = cleared
    return target


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
    """Whole or not at all; a link or folder at the path is refused."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.path.lexists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
        raise OSError("screenshot path is not a regular file")
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


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


def _asset_plan(assets: dict) -> dict:
    """File name -> bytes for new photos; every key must be <site>/assets/products/<plain file name>."""
    plan = {}
    for rel, data in assets.items():
        parts = PurePosixPath(rel).parts
        if (len(parts) != 4 or parts[:3] != (SITE, "assets", "products") or parts[3] in ("", ".", "..")
                or not isinstance(data, bytes)):
            raise ValueError(f"preview photo outside assets/products: {rel}")
        plan[parts[3]] = data
    return plan


def _link_assets(dest: Path, real: Path, plan: dict) -> None:
    """A real assets folder of links to the tracked entries, with real products/ holding the new photos.
    Nothing is ever written through a link: a new photo replaces a link in the copy only."""
    dest.mkdir()
    for entry in real.iterdir():
        if entry.name != "products":
            (dest / entry.name).symlink_to(entry)
    products = dest / "products"
    products.mkdir()
    if (real / "products").is_dir():
        for entry in (real / "products").iterdir():
            if entry.name not in plan:
                (products / entry.name).symlink_to(entry)
    for name, data in plan.items():
        with os.fdopen(os.open(products / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as handle:
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


def _unshown(stdout: str) -> bool:
    """AV1222-06: the last stdout line says the route is shown nowhere on /hike (nothing was checked)."""
    lines = [line for line in (stdout or "").splitlines() if line.strip()]
    try:
        return json.loads(lines[-1]).get("unshown") is True if lines else False
    except (ValueError, RecursionError, AttributeError):
        return False


class Previewer:
    def __init__(self, worktree, env=None, viewports=VIEWPORTS):
        self.viewports = tuple(viewports)
        self.worktree = Path(worktree).resolve()
        self.env = dict(os.environ if env is None else env)
        self.last_server = None  # {"pid", "port"} of the most recent preview server (for checks)

    def capture(self, files, target, out_png, assets=None) -> dict:
        """Never raises: any failure comes back as ok False with a short error.
        ``assets`` (site path -> bytes, new product photos only) are laid into the copy's own assets folder."""
        try:
            return self._capture(dict(files), dict(target), Path(out_png), dict(assets or {}))
        except Exception as exc:  # noqa: BLE001 - the caller reports the error; a preview never blocks a reply
            return {"ok": False, "png": None, "checks": {}, "error": f"{type(exc).__name__}: {exc}"[:200]}

    def _copy_site(self, tmp: Path, files: dict, assets: dict | None = None) -> Path:
        listed = subprocess.run(["git", "-C", str(self.worktree), "ls-files", "-z", SITE],
                                capture_output=True, check=True).stdout.decode("utf-8").split("\0")
        for rel in filter(None, listed):
            if rel != ASSETS and not rel.startswith(ASSETS + "/"):
                (tmp / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.worktree / rel, tmp / rel)
        site = tmp / SITE
        site.mkdir(exist_ok=True)
        real_assets = (self.worktree / ASSETS).resolve()
        if assets:
            _link_assets(site / "assets", real_assets, _asset_plan(assets))
        else:
            (site / "assets").symlink_to(real_assets, target_is_directory=True)
        _write_overlay(tmp, files)
        return site

    def _capture(self, files: dict, target: dict, out_png: Path, assets: dict | None = None) -> dict:
        if target.get("kind") == "unreadable":  # a damaged change record: no copy, no server
            return {"ok": False, "png": None, "checks": {}, "error": "preview target unreadable"}
        if self.viewports not in (("phone",), VIEWPORTS):
            raise ValueError(f"unsupported viewports {self.viewports!r}"[:80])
        with tempfile.TemporaryDirectory(prefix="hass-preview-") as raw:
            tmp = Path(raw)
            site = self._copy_site(tmp, files, assets)
            port, base = _free_port(), {k: self.env.get(k, "") for k in ("PATH", "HOME")}
            server_env = {**base, "AVOSHACK_COMMUNITY_DB": str(tmp / "fixture.sqlite3"),
                          "AVOSHACK_COMMUNITY_CONFIG": str(site / "community.json")}
            server = subprocess.Popen([sys.executable, str(site / "community-server.py"), "--port", str(port)],
                                      cwd=tmp, env=server_env, stdin=subprocess.DEVNULL,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.last_server = {"pid": server.pid, "port": port}
            unshown = False
            runs = []  # (viewport, shot, checks or None when the run failed, failure text); phone first
            try:
                deadline = time.monotonic() + START_TIMEOUT
                while not _get_ok(port):
                    if server.poll() is not None or time.monotonic() > deadline:
                        return {"ok": False, "png": None, "checks": {}, "error": "preview server did not start"}
                    time.sleep(0.1)
                for name in self.viewports:
                    shot = tmp / ("shot.png" if name == "phone" else f"shot-{name}.png")
                    node_env = {**base, "PREVIEW_URL": f"http://127.0.0.1:{port}", "TARGET": json.dumps({**target, "defaultIntro": DEFAULT_INTRO} if target.get("kind") == "store" else target),
                                "OUT": str(shot), "VIEWPORT": name,
                                **{k: self.env[k] for k in PASS_THROUGH if self.env.get(k)}}
                    try:
                        proc = subprocess.run(["node", str(SCRIPT)], env=node_env, cwd=tmp, capture_output=True,
                                              text=True, timeout=CAPTURE_TIMEOUT)
                        ran = not proc.returncode and shot.is_file()
                        checks = _checks(proc.stdout) if ran else None
                        unshown = unshown or (name == "phone" and ran and _unshown(proc.stdout))
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
        return {"ok": error is None, "png": str(out_png), "checks": checks, "error": error, **extra,
                **({"unshown": True} if unshown and error is None else {})}

#!/usr/bin/env python3
"""HASS-RCV-1: the receiver host on AgentOrange. Subcommands (each takes --host host.json):
  serve        sealed POST /v1/inbound (store only) and POST /v1/relay (the Mac pulls replies) on a loopback or
               Tailscale address; allowedPeers only; never drains, never applies.
  work         drains the inbox through Receiver + Conversation; in `private` mode an owner `yes` is applied by the
               editor's single-writer path; every reply goes to the relay store for the Mac to pull.
  start-point  --at ISO: records the inbox start point once.
  check        validates host.json, the key file and the runtime identity; opens no socket.
Exit 0 ok, 2 config / secret / start point / runtime refused (one JSON line, field names only), 1 any other error.
Nothing prints message text, a sender, a chat id, a URL, a secret or a path.
"""
import argparse, base64, collections, ipaddress, json, logging, os, secrets, signal, socket, socketserver, stat, subprocess, sys, threading  # noqa: E401
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hass import bridge, conversation, editor as editor_mod, inbox as inbox_mod, interpreter_local, interpreter_prompt  # noqa: E402
from hass import preview, receiver, relay  # noqa: E402
from hass.content_model import load_content  # noqa: E402
from hass.ops import load_registry  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = logging.getLogger("hass.host")
MAX_HOST_JSON, MAX_BODY, ROUTES = 64 * 1024, 64 * 1024, ("/v1/inbound", "/v1/relay")
METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"})  # a logged method is one of these, never client text
KEYS = {"state", "secretFile", "listen", "allowedPeers", "approvals", "interpreter", "previewer", "runtimeCommit", "pictures", "release"}
PICTURES_PER_MIN = 10  # HASS-ATTACH-1: more picture requests in a minute get `gone` with no data
TAILSCALE = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))
LIVE_REASON = "live release is not installed"


class HostConfigError(Exception):
    """host.json is unusable. `fields` are field names only; `reason` is a fixed phrase or None."""
    def __init__(self, fields, reason=None):
        super().__init__(",".join(fields))
        self.fields, self.reason = list(fields), reason


class Refuse(Exception):
    def __init__(self, out):
        super().__init__(out["result"])
        self.out = out


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _private_json(path):
    try:
        st = os.lstat(path)
        ok = stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid() and not st.st_mode & 0o177 and st.st_size <= MAX_HOST_JSON
        data = Path(path).read_bytes() if ok else None
        cfg = json.loads(data.decode("utf-8"), object_pairs_hook=receiver._pairs, parse_constant=receiver._no_constant) if ok else None
    except (OSError, ValueError, RecursionError):
        cfg = None
    if not isinstance(cfg, dict): raise HostConfigError(["host"])
    return cfg


def _ip(value):
    try: return ipaddress.ip_address(value)
    except (ValueError, TypeError): return None


def _listen(value, allow_zero):
    host, _, port = value.rpartition(":") if isinstance(value, str) else ("", "", "")
    ip = _ip(host.strip("[]"))
    if ip is None or not port.isdigit() or not (1 if not allow_zero else 0) <= int(port) <= 65535: return None
    if ip.version == 6 and ip.ipv4_mapped: return None
    return (ip, int(port)) if ip.is_loopback or any(ip in net for net in TAILSCALE) else None


def load_host(path, allow_port_zero=False) -> dict:
    """host.json: a regular 0600 file of this user, <= 64 KiB, closed keys. Returns the config plus `addr`, `peers`."""
    raw = _private_json(path)
    bad = sorted(set(raw) - KEYS) + sorted(KEYS - {"previewer", "pictures", "release"} - set(raw))
    text = lambda v: isinstance(v, str) and 0 < len(v) <= 4096  # noqa: E731
    itp = raw.get("interpreter")
    peers = raw.get("allowedPeers")
    checks = {"pictures": type(raw.get("pictures", False)) is bool, "state": text(raw.get("state")), "secretFile": text(raw.get("secretFile")),
              "approvals": raw.get("approvals") in ("hold", "private", "live"),
              "previewer": type(raw.get("previewer", False)) is bool,
              "runtimeCommit": isinstance(raw.get("runtimeCommit"), str) and len(raw["runtimeCommit"]) == 40
              and all(c in "0123456789abcdef" for c in raw["runtimeCommit"]),
              "interpreter": isinstance(itp, dict) and set(itp) == {"url", "model"} and isinstance(itp["model"], str)
              and 0 < len(itp["model"]) <= 100,
              "allowedPeers": isinstance(peers, list) and all(_ip(p) for p in peers),
              "listen": _listen(raw.get("listen"), allow_port_zero) is not None}
    if checks["interpreter"]:
        try: interpreter_local.check_url(itp["url"])
        except ValueError: checks["interpreter"] = False
    bad += [name for name, ok in checks.items() if not ok and name not in bad]
    if not bad and not peers and not _listen(raw["listen"], allow_port_zero)[0].is_loopback: bad.append("allowedPeers")
    if raw.get("approvals") == "live":
        from hass.publish_live import release_config
        try: raw["release"] = release_config(raw.get("release"))
        except ValueError as exc: bad.append(str(exc))
        for name in ("previewer", "pictures"):
            if raw.get(name) is not True: bad.append(name)
        try:
            settings = conversation.load_settings(Path(raw["state"]))
            if settings.get("liveSite") != "theavocadoman.com": bad.append("liveSite")
            if settings.get("approvalNeedsCode") is not True: bad.append("approvalNeedsCode")
        except (conversation.ConfigError, KeyError, TypeError): bad.append("state")
    if bad: raise HostConfigError(bad)
    ip, port = _listen(raw["listen"], allow_port_zero)
    return {**raw, "addr": (str(ip), port), "peers": frozenset(str(_ip(p)) for p in peers), "previewer": raw.get("previewer", False),
            "pictures": raw.get("pictures", False), "hostDir": str(Path(path).resolve().parent)}


def runtime_problem(cfg, root=ROOT) -> bool:
    """D8: the checkout holding this host.py is at runtimeCommit, clean, and not the editor's writer worktree."""
    root = Path(root).resolve()

    def git(*args): return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    top, head, dirty = git("rev-parse", "--show-toplevel"), git("rev-parse", "HEAD"), git("status", "--porcelain")
    if top.returncode or head.returncode or dirty.returncode: return True
    if Path(top.stdout.strip()).resolve() != root or head.stdout.strip() != cfg["runtimeCommit"] or dirty.stdout.strip(): return True
    return Path(_worktree(cfg)).resolve() == root


def _worktree(cfg) -> str:
    if not Path(cfg["state"]).is_dir(): raise HostConfigError(["state"])
    try:
        sdir = editor_mod.open_state(cfg["state"])
        return editor_mod._read_config(sdir / "config.json")["worktree"]
    except editor_mod.UnsafeState: raise HostConfigError(["state"]) from None


# -- serve ---------------------------------------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    timeout = 10  # a slow client cannot hold the single-threaded server
    server_version, sys_version = "hass", ""

    def log_message(self, *args): pass

    def log_request(self, code="-", size="-"):  # method, known path and status only: no peer, body, header or query
        path = getattr(self, "path", "")
        method = getattr(self, "command", "")
        LOG.info("%s %s %s", method if method in METHODS else "-", path if path in ROUTES else "-", code)

    def _send(self, code, obj=None):
        data = b"" if obj is None else json.dumps(obj, sort_keys=True).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _guard(self) -> bool:
        peer = _ip(self.client_address[0].split("%")[0])
        if peer is None or str(peer) not in self.server.peers: return self._send(403) or False
        if self.command != "POST" or self.path not in ROUTES: return self._send(404) or False
        return True

    do_GET = do_PUT = do_DELETE = do_HEAD = do_PATCH = do_OPTIONS = do_POST = lambda self: self._handle()

    def _handle(self):
        if not self._guard(): return
        length = self.headers.get("Content-Length", "")
        if not length.isdigit(): return self._send(411)
        if int(length) > MAX_BODY: return self._send(413)
        body, srv = self.rfile.read(int(length)), self.server
        now = srv.clock()
        if self.path == "/v1/inbound":
            return self._send(200, {"result": srv.receiver.accept(body, secret=srv.secret, now=now)["result"]})
        try:
            env = json.loads(body, object_pairs_hook=receiver._pairs, parse_constant=receiver._no_constant)
            msg = relay.unseal_control(env, srv.secret, now=now, seen=srv.receiver.inbox.seen())
        except (ValueError, UnicodeDecodeError, RecursionError, bridge.EnvelopeError):
            return self._send(400, {"result": "rejected"})
        secs = int(now.timestamp())
        if msg["op"] == "pull": out = {"op": "replies", "items": srv.store.pull(msg["max"], secs)}
        elif msg["op"] == "ack": srv.store.ack(msg["ids"], secs); out = {"op": "acked", "ids": msg["ids"]}
        elif msg["op"] == "picture":
            while srv.pic_times and secs - srv.pic_times[0] >= 60: srv.pic_times.popleft()
            shot = None if len(srv.pic_times) >= PICTURES_PER_MIN else srv.store.picture(msg["id"], msg["idx"])
            srv.pic_times.append(secs)
            out = ({"op": "picture", "id": msg["id"], "idx": msg["idx"], "sha256": shot[0],
                    "b64": base64.b64encode(shot[1]).decode("ascii")} if shot else {"op": "gone", "id": msg["id"], "idx": msg["idx"]})
        else: return self._send(400, {"result": "rejected"})
        self._send(200, relay.seal_control(out, srv.secret, nonce=secrets.token_hex(16), now=now))


class Server(HTTPServer):
    def __init__(self, cfg, secret, rx, store, clock=_now):
        self.address_family = socket.AF_INET6 if ":" in cfg["addr"][0] else socket.AF_INET
        self.peers, self.secret, self.receiver, self.store, self.clock = cfg["peers"], secret, rx, store, clock
        self.pic_times = collections.deque()
        super().__init__(cfg["addr"], Handler)

    def server_bind(self):  # no reverse DNS lookup of the Tailscale address
        socketserver.TCPServer.server_bind(self)
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        LOG.warning("request failed: %s", sys.exc_info()[0].__name__)


# -- work ----------------------------------------------------------------------------------------------------------
class Worker:
    def __init__(self, conv, rx, store, worktree, build, clock=_now, shots_dir=None):
        self.conv, self.rx, self.worktree, self.build, self.clock = conv, rx, Path(worktree), build, clock
        self.sender = relay.RelaySender(store, conv.settings["ownerChat"], lambda: int(clock().timestamp()), shots_dir)
        self.rev = editor_mod.content_revision(self.worktree)
        handle = rx.handle

        def refreshed(msg, *a, **kw):  # an earlier message in the same drain may have applied a change
            self._refresh()
            return handle(msg, *a, **kw)
        rx.handle = refreshed

    def _refresh(self):
        if (rev := editor_mod.content_revision(self.worktree)) != self.rev:
            self.conv.interpreter, self.rev = self.build(), rev

    def cycle(self):
        """Rebuild the interpreter prompt when the content changed (before every message), drain the inbox, queue the replies."""
        self._refresh()
        self.rx.drain()
        if hasattr(self.conv.editor, "reconcile"): self.conv.editor.reconcile()
        self.conv.flush(self.sender)

    def run(self, stop):
        wait = 1
        while not stop.is_set():
            try:
                self.cycle()
                wait = 1
            except Exception as exc:  # noqa: BLE001 - class name only; the message stays pending (health: inbox-stuck)
                LOG.error("cycle failed: %s", type(exc).__name__)
                wait = min(60, wait * 2)
            stop.wait(wait)


def interpreter_builder(cfg, worktree):
    def build():
        prompt = interpreter_prompt.build(load_registry(), load_content(Path(worktree) / "hass" / "content"))
        return interpreter_local.LocalInterpreter(cfg["interpreter"]["url"], cfg["interpreter"]["model"], prompt)
    return build


def make_worker(cfg, store, *, editor=None, build=None, clock=_now) -> Worker:
    worktree = _worktree(cfg)
    build = build or interpreter_builder(cfg, worktree)
    if cfg["approvals"] == "live" and editor is None:
        from hass.publish_live import LiveEditor
        editor = LiveEditor(cfg["state"], cfg["release"], cfg["hostDir"], clock=clock)
    conv = conversation.Conversation(cfg["state"], editor or conversation.Editor(cfg["state"]), build(), clock,
                                     previewer=preview.Previewer(worktree) if cfg["previewer"] else None)
    if cfg["approvals"] == "live":
        conv.editor.conv = conv
        conv.editor.reconcile()
    rx = receiver.Receiver(state=inbox_mod.Inbox(cfg["state"], clock=clock), settings=conv,
                           apply=cfg["approvals"] in ("private", "live"))
    return Worker(conv, rx, store, worktree, build, clock, Path(cfg["state"]).resolve() / "screenshots" if cfg["pictures"] else None)


# -- commands ------------------------------------------------------------------------------------------------------
def _ready(args, root, need_start=True):
    cfg = load_host(args.host)
    if runtime_problem(cfg, root): raise Refuse({"result": "runtime-mismatch"})
    key = relay.read_key(cfg["secretFile"])
    if need_start:
        try: inbox_mod.Inbox(cfg["state"]).close()
        except ValueError: raise Refuse({"result": "no-start-point"}) from None
    return cfg, key


def _stopper():
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *a: stop.set())  # finish the current cycle, exit 0
    return stop


def _run(args, root, clock):
    if args.cmd == "start-point":
        cfg = load_host(args.host)
        _worktree(cfg)
        try: inbox_mod.Inbox(cfg["state"], start_at=args.at).close()
        except ValueError: raise Refuse({"result": "start-point-refused"}) from None
        return {"result": "ok", "start_at": args.at}
    cfg, key = _ready(args, root, need_start=args.cmd != "check")
    host_dir = Path(args.host).resolve().parent
    if args.cmd == "work":
        stop = _stopper()
        make_worker(cfg, relay.RelayStore(host_dir), clock=clock).run(stop)
    elif args.cmd == "serve":
        stop, rx = _stopper(), receiver.Receiver(state=inbox_mod.Inbox(cfg["state"], clock=clock), settings=None)
        srv = Server(cfg, key, rx, relay.RelayStore(host_dir), clock)
        srv.timeout = 1
        while not stop.is_set(): srv.handle_request()
    return {"result": "ok"}


def main(argv=None, *, root=ROOT, clock=_now) -> int:
    ap = argparse.ArgumentParser(prog="hass/host.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("serve", "work", "check", "start-point"):
        p = sub.add_parser(name)
        p.add_argument("--host", required=True)
        if name == "start-point": p.add_argument("--at", required=True)
    args = ap.parse_args(argv)
    try:
        out, code = _run(args, root, clock), 0
    except Refuse as exc: out, code = exc.out, 2
    except HostConfigError as exc:
        out, code = {"result": "refused", "reason": exc.reason} if exc.reason else {"result": "config", "fields": exc.fields}, 2
    except relay.KeyFileError as exc: out, code = {"result": "secret", "code": exc.code}, 2
    except Exception as exc:  # noqa: BLE001 - class name only
        out, code = {"result": "error", "error": type(exc).__name__}, 1
    print(json.dumps(out, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())

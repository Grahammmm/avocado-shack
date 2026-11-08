#!/usr/bin/env python3
"""Mac-side Hass forwarder. BlueBubbles REST shapes remain UNVERIFIED on a real Mac."""
import argparse, base64, functools, hashlib, hmac, ipaddress, json, os, re, secrets, signal, sqlite3, stat, sys, threading, time  # noqa: E401
import urllib.error, urllib.parse, urllib.request
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hass import bridge, bridge_attach, relay, stagelog  # noqa: E402
from hass.conversation import read_command, sender_key  # noqa: E402

MAX_BODY = 256 * 1024
MAX_REPLY, PIC_RETRY = 2621440, (10, 30)  # HASS-ATTACH-1: picture reply cap (2.5 MiB); waits after the 1st and 2nd failure
GAVE_UP = "The picture for that message didn't come through. What the message says is still right."
# HASS-FAST-1 (eyes ack). The ack is a single text "👀" to the owner chat through the existing send path (BlueBubbles' tapback
# endpoint needs the Private API, which stays off, and iMessage has no 👀 tapback anyway: see reports/hass/FAST-1.md).
ACK_TEXT = "\N{EYES}"
ACK_MAX_AGE = 120   # a message older than this when accepted (catch-up after sleep or an outage) is never acked
ACK_STALE = 30      # an ack still unsent this long after it was queued is dropped, not sent late
ACK_TIMEOUT = 4     # seconds one ack send may block the loop (an ack never waits the 10 s of a reply)
STATE_TTL = 2       # the host's "changes are paused" answer is trusted this long; older, failed or missing means ask again, and no ack until answered
PAUSE_HOLD = 60     # after the owner's own pause command, no ack for this long (the host has not read it yet)
PULL_SLOW, PULL_FAST, FAST_WINDOW = 5, 1, 180  # reply pull every 5 s, every 1 s for 3 minutes after an owner message
CATCH_UP_EVERY = 15  # was 60: the safety net that finds a message the BlueBubbles webhook did not announce
KEYS = {"ownerChat", "receiverUrl", "bbPort", "bbPasswordFile", "secretFile", "spoolDir", "webhookPort", "webhookTokenFile", "ack"}
NOTICE = "Hass can't reach its computer right now, so nothing has changed yet. Your messages are saved and will be handled when it's back."


def private_read(path, limit):
    """Bounded D5-style read; errors contain no user-controlled data."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o177 or st.st_size > limit:
                raise ValueError("private-file")
            data = os.read(fd, limit + 1)
        finally: os.close(fd)
        if len(data) > limit: raise ValueError("private-file")
        return data
    except OSError: raise ValueError("private-file") from None


def key_read(path):
    raw = private_read(path, 128)
    if not re.fullmatch(b"[0-9a-f]{64}\\n?", raw): raise ValueError("key-format")
    return bytes.fromhex(raw.decode().strip())


def load_config(path):
    cfg = json.loads(private_read(path, 16384))
    if type(cfg) is not dict or set(cfg) - KEYS or KEYS - {"webhookPort", "ack"} - set(cfg): raise ValueError("config")
    cfg.setdefault("webhookPort", 8796)
    if type(cfg.get("ack", True)) is not bool: raise ValueError("config")  # HASS-FAST-1: absent means on; false switches the 👀 off
    if not isinstance(cfg["ownerChat"], str) or not re.fullmatch(r"iMessage;-;[^;\s]+", cfg["ownerChat"]): raise ValueError("config")
    if any(type(cfg[k]) is not int or not 1 <= cfg[k] <= 65535 for k in ("bbPort", "webhookPort")): raise ValueError("config")
    for k in ("bbPasswordFile", "secretFile", "spoolDir", "webhookTokenFile"):
        if not isinstance(cfg[k], str) or not Path(cfg[k]).is_absolute(): raise ValueError("config")
    u = urllib.parse.urlsplit(cfg["receiverUrl"])
    try:
        addr = ipaddress.ip_address(u.hostname)
        allowed = addr == ipaddress.ip_address("127.0.0.1") or addr in ipaddress.ip_network("100.64.0.0/10")
    except ValueError:
        allowed = bool(u.hostname and re.fullmatch(r"[a-z0-9-]+(?:\.[a-z0-9-]+\.ts\.net)?", u.hostname))
    if not allowed or u.scheme != "http" or u.port != 8795 or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
        raise ValueError("receiver-url")
    cfg["receiverUrl"] = cfg["receiverUrl"].rstrip("/")
    key_read(cfg["secretFile"])
    key_read(cfg["webhookTokenFile"])
    if not private_read(cfg["bbPasswordFile"], 4096).strip(): raise ValueError("password-file")
    st = os.lstat(cfg["spoolDir"])
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700: raise ValueError("spool-dir")
    return cfg


def request_json(url, body=None, limit=1024 * 1024):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with bridge._OPENER.open(req, timeout=10) as r:
            raw = r.read(limit + 1)
            if len(raw) > limit: raise ValueError("response-size")
            return json.loads(raw)
    except Exception: raise bridge.BridgeError("transport-error") from None


class Spool:
    def __init__(self, directory, now):
        self.clock = time.time
        self.directory = directory
        path = Path(directory) / "spool.sqlite3"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o177: raise ValueError("spool-file")
        finally: os.close(fd)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS inbound(provider_id TEXT PRIMARY KEY,payload TEXT,state TEXT,tries INTEGER,"
            "next_try_at REAL,created_at REAL,done_at REAL);"
            "CREATE TABLE IF NOT EXISTS fetch(guid TEXT,event TEXT,created_at REAL,tries INTEGER DEFAULT 0,next_try_at REAL DEFAULT 0,PRIMARY KEY(guid,event));"
            "CREATE TABLE IF NOT EXISTS meta(name TEXT PRIMARY KEY,value REAL);"
            "CREATE TABLE IF NOT EXISTS sent(reply_id INTEGER PRIMARY KEY,sent_at REAL);"
            "CREATE TABLE IF NOT EXISTS sent_pics(reply_id INTEGER,idx INTEGER,sent_at REAL,PRIMARY KEY(reply_id,idx));"
            "CREATE TABLE IF NOT EXISTS pic_tries(reply_id INTEGER,idx INTEGER,tries INTEGER,next_try_at REAL,PRIMARY KEY(reply_id,idx));"
            "CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY,seen_at REAL);"
            "CREATE TABLE IF NOT EXISTS drops(reason TEXT PRIMARY KEY,count INTEGER);"
            "CREATE TABLE IF NOT EXISTS ack(provider_id TEXT PRIMARY KEY,state TEXT,created_at REAL,done_at REAL);")
        self.stage = stagelog.off  # HASS-FAST-1: the Forwarder swaps in a StageLog
        for name, value in (("start_ms", int(now * 1000)), ("last_seen_ms", int(now * 1000)), ("outage_since", 0), ("outage_notified", 0), ("last_rejected", 0),
                            ("hold_until", 0), ("fast_until", 0)):
            self.db.execute("INSERT OR IGNORE INTO meta VALUES (?,?)", (name, value))

    def get(self, name): return self.db.execute("SELECT value FROM meta WHERE name=?", (name,)).fetchone()[0]
    def set(self, name, value): self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (name, value))
    def __contains__(self, nonce): return self.db.execute("SELECT 1 FROM nonces WHERE nonce=?", (nonce,)).fetchone() is not None
    def add(self, nonce): self.db.execute("INSERT INTO nonces VALUES (?,?)", (nonce, self.clock()))
    def drop(self, reason):
        self.db.execute("INSERT INTO drops VALUES (?,1) ON CONFLICT(reason) DO UPDATE SET count=count+1", (reason,))

    def doorbell(self, event, now):
        if type(event) is not dict or type(event.get("type")) is not str or event["type"] not in bridge.EVENT_KINDS: return
        data = event.get("data")
        guid = data.get("guid") if type(data) is dict else None
        if isinstance(guid, str) and 0 < len(guid) <= 1024 and not bridge.SURROGATE_RE.search(guid):
            added = self.db.execute("INSERT OR IGNORE INTO fetch(guid,event,created_at) VALUES (?,?,?)", (guid, event["type"], now)).rowcount
            if added and event["type"] == "new-message": self.stage("webhook-in", guid)

    def accept(self, event, owner, now, via="webhook"):
        msg = bridge.normalize(event)
        if isinstance(msg, bridge.Drop): return self.drop(msg.reason)
        if msg.chat != owner: return self.drop("other-chat")
        ms = int(datetime.fromisoformat(msg.received_at).timestamp() * 1000)
        if ms < self.get("start_ms"): return self.drop("history")
        new = self.db.execute("INSERT OR IGNORE INTO inbound VALUES (?,?,'pending',0,0,?,NULL)",
                              (msg.provider_id, json.dumps(asdict(msg)), now)).rowcount
        if new:  # a repeat (webhook then catch-up, a replay, a restart) never reaches this line
            self.stage("accepted", msg.provider_id, via=via)
            self.owner_arrived(msg, owner, ms)

    def owner_arrived(self, msg, owner, ms):
        """HASS-FAST-1: a newly stored message from the owner's own address in the owner's one-to-one chat, sent just now,
        queues exactly one ack (INSERT OR IGNORE on the message id) and opens the fast reply pull. Never a stranger's, Hass's
        own (from_me), an edit or a reaction, or an old message found by catch-up. The pause command is noted here too."""
        try:
            address = owner.split(";", 2)[2]
            mine = (msg.kind == "new" and not msg.from_me and msg.chat == owner
                    and sender_key(msg.sender) is not None and sender_key(msg.sender) == sender_key(address))
            if not mine or self.clock() * 1000 - ms > ACK_MAX_AGE * 1000: return
            self.set("fast_until", self.clock() + FAST_WINDOW)
            cmd = read_command(msg.text) if msg.attachments == 0 else None
            if cmd and cmd[0] == "pause": self.set("hold_until", self.clock() + PAUSE_HOLD)
            self.db.execute("INSERT OR IGNORE INTO ack VALUES (?,'pending',?,NULL)", (msg.provider_id, self.clock()))
        except Exception:  # noqa: BLE001 - an ack is never worth losing the message that was just stored
            pass

    def status(self):
        counts = {s: self.db.execute("SELECT COUNT(*) FROM inbound WHERE state=?", (s,)).fetchone()[0] for s in ("pending", "done", "dropped")}
        counts.update(pending_fetch=self.db.execute("SELECT COUNT(*) FROM fetch").fetchone()[0],
                      dropped_events=self.db.execute("SELECT COALESCE(SUM(count),0) FROM drops").fetchone()[0],
                      sent=self.db.execute("SELECT COUNT(*) FROM sent").fetchone()[0], last_rejected=self.get("last_rejected"))
        return counts


class Forwarder:
    def __init__(self, cfg, spool, clock=time.time, transport=request_json, sender=None, attach=None, stage=None, acker=None):
        self.cfg, self.spool, self.clock, self.transport = cfg, spool, clock, transport
        spool.clock = clock
        self.stage = spool.stage = stage or stagelog.off  # HASS-FAST-1: read-only stage times (main() passes a StageLog)
        self.secret = key_read(cfg["secretFile"])
        self.sender = sender or bridge.BlueBubblesSender(f'http://127.0.0.1:{cfg["bbPort"]}', cfg["bbPasswordFile"])
        # The 👀 goes through the same send path, but one slow send may hold the loop only ACK_TIMEOUT seconds, not 10.
        self.acker = acker or (self.sender if sender else bridge.BlueBubblesSender(
            f'http://127.0.0.1:{cfg["bbPort"]}', cfg["bbPasswordFile"],
            transport=lambda url, body, headers, timeout: bridge._urllib_transport(url, body, headers, min(timeout, ACK_TIMEOUT))))
        self.attach = attach or bridge_attach.BlueBubblesAttachmentSender(
            f'http://127.0.0.1:{cfg["bbPort"]}', cfg["bbPasswordFile"], cfg["ownerChat"])
        self.big = functools.partial(request_json, limit=MAX_REPLY) if transport is request_json else transport
        self.next_poll = self.next_pull = self.next_state = 0
        self.query_offset, self.query_high = 0, 0
        self.paused, self.paused_at = None, 0  # the host's "changes are paused" answer and when it came (None: not known)

    def bb(self, path, body=None):
        password = private_read(self.cfg["bbPasswordFile"], 4096).decode().strip()
        sep = "&" if "?" in path else "?"
        return self.transport(f'http://127.0.0.1:{self.cfg["bbPort"]}{path}{sep}{urllib.parse.urlencode({"password": password})}', body)["data"]

    def post(self, path, env, big=False): return (self.big if big else self.transport)(self.cfg["receiverUrl"] + path, env)

    def fetch(self):
        row = self.spool.db.execute("SELECT guid,event,created_at,tries,next_try_at FROM fetch ORDER BY created_at,rowid LIMIT 1").fetchone()
        if row is None or row[4] > self.clock(): return
        guid, kind, created, tries, _ = row
        try:
            msg = self.bb("/api/v1/message/" + urllib.parse.quote(guid, safe="") + "?with=chats,handle,attachment")
            if type(msg) is not dict or msg.get("guid") != guid: raise ValueError("refetch-shape")
            with self.spool.db:
                self.spool.accept({"type": kind, "data": msg}, self.cfg["ownerChat"], created)
                self.spool.db.execute("DELETE FROM fetch WHERE guid=? AND event=?", (guid, kind))
        except (bridge.BridgeError, ValueError, KeyError, TypeError):
            self.spool.db.execute("UPDATE fetch SET tries=tries+1,next_try_at=? WHERE guid=? AND event=?",
                                  (self.clock() + min(300, 5 * 2 ** min(tries, 6)), guid, kind))

    def catch_up(self):
        cursor = int(self.spool.get("last_seen_ms"))
        query = {"chatGuid": self.cfg["ownerChat"], "after": cursor, "sort": "ASC", "limit": 50,
                 "with": ["chats", "handle", "attachment"]}
        # Keep the durable cursor fixed until a page is exhausted, including timestamp ties.
        if self.query_offset: query["offset"] = self.query_offset
        rows = self.bb("/api/v1/message/query", query)
        if type(rows) is not list: raise ValueError("query-shape")
        for msg in rows:
            if type(msg) is not dict or type(msg.get("dateCreated")) is not int: raise ValueError("query-shape")
        for msg in rows:
            self.spool.accept({"type": "new-message", "data": msg}, self.cfg["ownerChat"], self.clock(), via="poll")
            if type(msg.get("dateEdited")) is int and msg["dateEdited"] > 0:
                self.spool.accept({"type": "updated-message", "data": msg}, self.cfg["ownerChat"], self.clock(), via="poll")
            cursor = max(cursor, msg["dateCreated"])
        self.query_high = max(self.query_high, cursor)
        if len(rows) == 50: self.query_offset += 50
        else:
            self.spool.set("last_seen_ms", self.query_high)
            self.query_offset = 0
        self.next_poll = self.clock() + (0 if len(rows) == 50 else CATCH_UP_EVERY)

    def deliver(self):
        db, now = self.spool.db, self.clock()
        row = db.execute("SELECT rowid,payload,tries,next_try_at,created_at FROM inbound WHERE state='pending' ORDER BY created_at,rowid LIMIT 1").fetchone()
        if row is None or row[3] > now: return
        # A failed earlier refetch must not let later messages pass it.
        if db.execute("SELECT 1 FROM fetch WHERE created_at<=? LIMIT 1", (row[4],)).fetchone(): return
        try:
            inbound = bridge.Inbound(**json.loads(row[1]))
            env = bridge.seal(inbound, self.secret, nonce=secrets.token_hex(16), now=now)
            self.stage("post-start", inbound.provider_id)
            result = self.post("/v1/inbound", env)["result"]
            if result not in ("queued", "duplicate", "history", "rejected"): raise ValueError("post-shape")
            self.stage("post-end", inbound.provider_id)
        except (bridge.BridgeError, ValueError, KeyError, TypeError):
            db.execute("UPDATE inbound SET tries=tries+1,next_try_at=? WHERE rowid=?", (now + min(300, 5 * 2 ** min(row[2], 6)), row[0]))
            if not self.spool.get("outage_since"): self.spool.set("outage_since", now)
            if now - row[4] >= 600 and not self.spool.get("outage_notified"):
                self.sender.send(self.cfg["ownerChat"], NOTICE)
                self.spool.set("outage_notified", 1)
            return
        for name in ("outage_since", "outage_notified"): self.spool.set(name, 0)
        if result == "rejected":
            self.spool.set("last_rejected", now)
            db.execute("UPDATE inbound SET tries=tries+1,next_try_at=? WHERE rowid=?", (now + 60, row[0]))
        else:
            db.execute("UPDATE inbound SET state='done',payload=NULL,done_at=? WHERE rowid=?", (now, row[0]))

    def control(self, body, expected, big=False):
        env = relay.seal_control(body, self.secret, nonce=secrets.token_hex(16), now=self.clock())
        answer = relay.unseal_control(self.post("/v1/relay", env, big), self.secret, now=self.clock(), seen=self.spool)
        if answer["op"] not in (expected if type(expected) is tuple else (expected,)): raise ValueError("relay-op")
        return answer

    def fetch_picture(self, rid, shot):
        """The verified PNG bytes of one shot, or None when the host has none (gone) or the bytes do not match what was announced."""
        ans = self.control({"op": "picture", "id": rid, "idx": shot["idx"]}, ("picture", "gone"), True)
        if ans["op"] == "gone" or (ans["id"], ans["idx"]) != (rid, shot["idx"]): return None
        data = base64.b64decode(ans["b64"])
        ok = hashlib.sha256(data).hexdigest() == ans["sha256"] == shot["sha256"] and len(data) == shot["size"] and data.startswith(relay.PNG_SIG)
        return data if ok else None

    def deliver_shots(self, item):
        """Send each shot not yet done: True when every shot is sent or given up. A failure waits 10 s, then 30 s; the third gives up."""
        db, rid = self.spool.db, item["id"]
        for shot in item.get("shots", ()):
            key = (rid, shot["idx"])
            if db.execute("SELECT 1 FROM sent_pics WHERE reply_id=? AND idx=?", key).fetchone(): continue
            tries = db.execute("SELECT tries,next_try_at FROM pic_tries WHERE reply_id=? AND idx=?", key).fetchone() or (0, 0)
            if tries[1] > self.clock(): return False
            try:
                data = self.fetch_picture(rid, shot)
                if data is not None: self.attach.send_png(item["chat"], data, f"hass-{rid}-{shot['idx']}.png")
            except (bridge.BridgeError, ValueError, KeyError, TypeError):
                data, fails = b"", tries[0] + 1
                if fails < 3:
                    db.execute("INSERT OR REPLACE INTO pic_tries VALUES (?,?,?,?)", (*key, fails, self.clock() + PIC_RETRY[fails - 1]))
                    return False
            if not data: self.sender.send(item["chat"], GAVE_UP)  # gone, bad bytes or a third failure: said once
            db.execute("INSERT INTO sent_pics VALUES (?,?,?)", (*key, self.clock()))
        return True

    def pull(self):
        ids = []
        try:
            for item in self.control({"op": "pull", "max": 5}, "replies")["items"]:
                if item["chat"] != self.cfg["ownerChat"]: continue
                if not self.spool.db.execute("SELECT 1 FROM sent WHERE reply_id=?", (item["id"],)).fetchone():
                    self.stage("reply-pulled", item["id"])
                    self.stage("bb-send-start", item["id"])
                    self.sender.send(item["chat"], item["text"], (None,) * item["pictures"])
                    self.stage("bb-send-end", item["id"])
                    self.spool.db.execute("INSERT INTO sent VALUES (?,?)", (item["id"], self.clock()))
                if self.deliver_shots(item): ids.append(item["id"])
        finally:
            if ids: self.control({"op": "ack", "ids": ids}, "acked")

    def state(self):
        """HASS-FAST-1: ask the host whether changes are paused (a sealed read-only `state`). Any failure, including an
        older host that does not know the op, just leaves the answer unknown, which means no 👀 (never a guess)."""
        paused = None
        try: paused = self.control({"op": "state"}, "state")["paused"]
        except (bridge.BridgeError, bridge.EnvelopeError, ValueError, KeyError, TypeError): pass
        if type(paused) is bool: self.paused, self.paused_at = paused, self.clock()
        else: self.paused = None  # fail closed: a failed refresh never leaves the last "not paused" answer standing

    def ack_allowed(self, now):
        """(may send, final). A pause command just seen or a paused host is a final no; no fresh host answer is a no for now."""
        if now < self.spool.get("hold_until"): return False, True
        if self.paused is None or now - self.paused_at > STATE_TTL: return False, False
        return (not self.paused), True

    def ack(self):
        try: self._ack()
        except Exception: print("retry", file=sys.stderr)  # noqa: BLE001 - an ack can never stop the loop (a broken table, a full disk)

    def _ack(self):
        """HASS-FAST-1: send the 👀 for each owner message queued by Spool.owner_arrived, before delivery and before any
        model. At most once per message id: the row goes pending -> sending (committed before the send) -> sent | failed,
        and a row found `sending` after a crash is never sent again. A failure or timeout is recorded and ignored."""
        db = self.spool.db
        for _ in range(3):
            row = db.execute("SELECT provider_id,created_at FROM ack WHERE state='pending' ORDER BY created_at,rowid LIMIT 1").fetchone()
            if row is None: return
            now, (pid, created) = self.clock(), row

            def close(state): db.execute("UPDATE ack SET state=?,done_at=? WHERE provider_id=? AND state='pending'", (state, now, pid))
            if now - created > ACK_STALE: close("stale"); continue
            if not self.cfg.get("ack", True): close("off"); continue
            if now >= self.spool.get("hold_until"):
                self.state()  # ask the host for EVERY ack, never trust an earlier not-paused answer (own thread: a slow send cannot delay this)
                now = self.clock()
            allowed, final = self.ack_allowed(now)
            if not allowed:
                if final: close("paused"); continue
                return  # the host has not answered yet: wait (the row goes stale after ACK_STALE)
            if db.execute("UPDATE ack SET state='sending',done_at=? WHERE provider_id=? AND state='pending'", (now, pid)).rowcount != 1: continue
            self.stage("ack-start", pid)
            try:
                self.acker.send(self.cfg["ownerChat"], ACK_TEXT)
                state = "sent"
            except Exception:  # noqa: BLE001 - an ack never blocks, retries or leaks: the state records it, nothing else
                state = "failed"
            db.execute("UPDATE ack SET state=?,done_at=? WHERE provider_id=?", (state, self.clock(), pid))
            self.stage("ack-end", pid)

    def cycle(self, ack=True):
        """One pass. `ack=False` is the serve loop: acknowledgements run on their own thread (ack_loop), so a slow reply or
        picture send, or a failing 👀 send, never delays the other."""
        fast = self.clock() < self.spool.get("fast_until")  # an owner message arrived in the last FAST_WINDOW seconds
        if fast: self.next_pull = min(self.next_pull, self.clock() + PULL_FAST)  # do not finish a slow wait first
        for attr, delay, action in (("next_poll", CATCH_UP_EVERY, self.catch_up),
                                    ("next_pull", PULL_FAST if fast else PULL_SLOW, self.pull)):
            if self.clock() >= getattr(self, attr):
                setattr(self, attr, self.clock() + delay)
                try: action()
                except (bridge.BridgeError, bridge.EnvelopeError, ValueError, KeyError, TypeError): print("retry", file=sys.stderr)
        for action in ((self.fetch, self.ack, self.deliver) if ack else (self.fetch, self.deliver)):
            try: action()
            except (bridge.BridgeError, ValueError): print("retry", file=sys.stderr)
        self.spool.db.execute("DELETE FROM nonces WHERE seen_at<?", (self.clock() - 86400,))


def ack_loop(cfg, stop, stage=None, **kw):
    """HASS-FAST-1: the 👀 thread. Its own spool connection and Forwarder; the durable pending -> sending -> sent claim in the
    ack table (one atomic UPDATE) keeps it at most once per message however the two threads interleave."""
    spool = Spool(cfg["spoolDir"], kw.get("clock", time.time)())
    try:
        fwd = Forwarder(cfg, spool, stage=stage, **kw)
        while not stop.is_set():
            fwd.ack()
            stop.wait(0.1)
    finally: spool.db.close()


class Handler(BaseHTTPRequestHandler):
    timeout = 10
    def log_message(self, format, *args): pass
    def send_error(self, code, message=None, explain=None): self.respond(code)
    def respond(self, code):
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()
    def do_POST(self):
        if not hmac.compare_digest(self.path.encode(), ("/bb/" + self.server.token).encode()): return self.respond(404)
        size = self.headers.get("Content-Length", "")
        if not size.isdigit() or self.headers.get("Transfer-Encoding"): return self.respond(411)
        if int(size) > MAX_BODY: return self.respond(413)
        try:
            raw = self.rfile.read(int(size))
            if len(raw) != int(size): return self.respond(400)
            # The HTTP thread owns its connection; network retries never block the doorbell.
            spool = Spool(self.server.spool.directory, self.server.clock())
            spool.stage = self.server.spool.stage  # HASS-FAST-1: the doorbell's stage time goes to the same log
            try: spool.doorbell(json.loads(raw), self.server.clock())
            finally: spool.db.close()
        except (ValueError, RecursionError): return self.respond(400)
        self.respond(200)


class Server(HTTPServer):
    def __init__(self, cfg, spool, clock=time.time):
        self.spool, self.clock = spool, clock
        self.token = key_read(cfg["webhookTokenFile"]).hex()
        super().__init__(("127.0.0.1", cfg["webhookPort"]), Handler)
    def handle_error(self, request, client_address): print("request-error", file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("serve", "status", "check", "ackcheck"))
    ap.add_argument("--config", required=True)
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
        if args.command == "ackcheck":
            # HASS-FAST-1: GET only, no message, no react call. Says whether this BlueBubbles server could send a tapback at all.
            password = private_read(cfg["bbPasswordFile"], 4096).decode().strip()
            info = request_json(f'http://127.0.0.1:{cfg["bbPort"]}/api/v1/server/info?{urllib.parse.urlencode({"password": password})}')["data"]
            private, helper = info.get("private_api") is True, info.get("helper_connected") is True
            print(json.dumps({"ackMethod": "text", "helperConnected": helper, "privateApi": private, "tapbackPossible": private and helper}, sort_keys=True))
            return 0
        if args.command == "check":
            # GET only; even a 404 proves the receiver answered. No messages or relay operations.
            password = private_read(cfg["bbPasswordFile"], 4096).decode().strip()
            for url in (f'http://127.0.0.1:{cfg["bbPort"]}/api/v1/ping?{urllib.parse.urlencode({"password": password})}', cfg["receiverUrl"] + "/v1/inbound"):
                try:
                    with bridge._OPENER.open(url, timeout=10) as r: r.read(1)
                except urllib.error.HTTPError as e:
                    e.close()
                    if e.code != 404: raise ValueError("unreachable") from None
            print('{"reachable": 2}')
            return 0
        spool = Spool(cfg["spoolDir"], time.time())
        try:
            if args.command == "status": print(json.dumps(spool.status(), sort_keys=True))
            else:
                os.umask(0o077)
                fwd, stop = Forwarder(cfg, spool, stage=stagelog.StageLog(Path(cfg["spoolDir"]) / "stages.jsonl")), threading.Event()
                signal.signal(signal.SIGTERM, lambda *a: stop.set())
                signal.signal(signal.SIGINT, lambda *a: stop.set())
                with Server(cfg, spool) as srv:
                    thread = threading.Thread(target=srv.serve_forever, daemon=True)
                    thread.start()
                    acker = threading.Thread(target=ack_loop, args=(cfg, stop, fwd.stage), daemon=True)
                    acker.start()
                    try:
                        while not stop.is_set():
                            fwd.cycle(ack=False)
                            stop.wait(0.2)
                    finally:
                        stop.set()
                        srv.shutdown()
                        thread.join()
                        acker.join(timeout=15)
        finally: spool.db.close()
        return 0
    except Exception:
        print('{"error": 1}')
        return 2


if __name__ == "__main__": sys.exit(main())

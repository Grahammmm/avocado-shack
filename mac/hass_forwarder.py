#!/usr/bin/env python3
"""Mac-side Hass forwarder. BlueBubbles REST shapes remain UNVERIFIED on a real Mac."""
import argparse, base64, functools, hashlib, hmac, ipaddress, json, os, re, secrets, signal, sqlite3, stat, sys, threading, time  # noqa: E401
import subprocess, tempfile, urllib.error, urllib.parse, urllib.request
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

if __package__ in (None, ""): sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hass import bridge, bridge_attach, bridge_photos, media, relay, stagelog  # noqa: E402
from hass.conversation import parse_command, read_command, sender_key  # noqa: E402

MAX_BODY = 256 * 1024
MAX_REPLY, PIC_RETRY = 2621440, (10, 30)  # HASS-ATTACH-1: picture reply cap (2.5 MiB); waits after the 1st and 2nd failure
GAVE_UP = "The picture for that message didn't come through. What the message says is still right."
CARD_GAVE_UP = "I couldn't send the card. Please don't approve it yet."
# HASS-TAPBACK-1 (replaces the HASS-FAST-1 text 👀, which G rejected: "mark my message, don't send me a message"). The ack is ONE
# real iMessage tapback on the owner's message, through BlueBubbles' react endpoint (Private API). It is never a text: there is
# no text-ack code path left. BlueBubbles documents exactly six tapbacks (server source `possibleReactions`) and no emoji
# reaction, so the 👀 emoji is not offered; see reports/hass/TAPBACK-1.md.
TAPBACKS = ("love", "like", "dislike", "laugh", "emphasize", "question")  # the allowlist; never a "-name" (that REMOVES a tapback)
ACK_REACTION = "like"  # default thumbs up; config key ack_reaction picks another of TAPBACKS
REACT_PATH = "/api/v1/message/react"
GUID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")  # a message guid (a UUID in practice); anything else means no react call
PROBE_TTL, PROBE_FAIL_TTL = 30, 5  # seconds the Private API answer (or an unanswered probe) is reused before asking again
ACK_MAX_AGE = 120   # a message older than this when accepted (catch-up after sleep or an outage) is never acked
ACK_BUDGET = 2.0    # the tapback should be CONFIRMED sent this many seconds after the message was stored; one sent after it is recorded `late`
ACK_STALE = 10      # an ack still unsent this long after it was queued is recorded `stale` and not sent at all (a late tapback is sent until then)
ACK_TIMEOUT = 1.5   # seconds the react call itself may take (a reply send gets 10); with ACK_STATE_TIMEOUT: <= 2 s per attempt
ACK_STATE_TIMEOUT = 0.5  # seconds the fresh "paused?" question to the host (and the Private API probe) may take; no answer means no tapback
ACK_TICK = 0.25     # the ack thread also looks every this many seconds (a restart, a missed wake-up)
CATCH_UP_PAGE = 50  # the most messages one catch-up query returns, so the most owner messages one cycle can accept at once
ACK_WORKERS = CATCH_UP_PAGE  # one ack worker per pending message, up to the largest burst a cycle accepts: every attempt starts at once
ACK_CLAIM_STALE = 8  # a row left `checking` this long (a worker died before deciding) goes back to `pending`; nothing was sent
PULL_SLOW, PULL_FAST, FAST_WINDOW = 5, 1, 180  # reply pull every 5 s, every 1 s for 3 minutes after an owner message
CATCH_UP_EVERY = 15  # was 60: the safety net that finds a message the BlueBubbles webhook did not announce
KEYS = {"ownerChat", "receiverUrl", "bbPort", "bbPasswordFile", "secretFile", "spoolDir", "webhookPort", "webhookTokenFile", "ack", "ack_reaction", "gChat", "ownerChats"}  # HASS-OWNERS-2: ownerChats optional
MAX_OWNER_CHATS = 8
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
    if type(cfg) is not dict or set(cfg) - KEYS or KEYS - {"webhookPort", "ack", "ack_reaction", "gChat", "ownerChats"} - set(cfg): raise ValueError("config")
    cfg.setdefault("webhookPort", 8796)
    if type(cfg.get("ack", True)) is not bool: raise ValueError("config")  # absent means on; false switches the tapback off
    if "ack_reaction" in cfg and (type(cfg["ack_reaction"]) is not str or cfg["ack_reaction"] not in TAPBACKS): raise ValueError("config")  # HASS-TAPBACK-1: allowlist
    if not isinstance(cfg["ownerChat"], str) or not re.fullmatch(r"iMessage;-;[^;\s]+", cfg["ownerChat"]): raise ValueError("config")
    if "ownerChats" in cfg:  # HASS-OWNERS-2: several owners, each in their own one-to-one chat; ownerChat (the main one) is one of them
        chats = cfg["ownerChats"]
        if (type(chats) is not list or not 1 <= len(chats) <= MAX_OWNER_CHATS or not all(type(c) is str and re.fullmatch(r"iMessage;-;[^;\s]+", c) for c in chats)
                or len(set(chats)) != len(chats) or cfg["ownerChat"] not in chats): raise ValueError("config")
    if "gChat" in cfg and (not isinstance(cfg["gChat"], str) or cfg["gChat"] in owner_chats(cfg)  # HASS-VOICE-1: G's own one-to-one chat, optional, text only; never an owner chat
                           or not re.fullmatch(r"iMessage;-;[^;\s]+", cfg["gChat"])): raise ValueError("config")
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


def owner_chats(cfg):
    """HASS-OWNERS-2: every owner chat, the main `ownerChat` first. No `ownerChats` key: the one chat, as before."""
    main = cfg["ownerChat"]
    return (main, *(c for c in cfg.get("ownerChats", ()) if c != main))


def request_json(url, body=None, limit=1024 * 1024, timeout=10):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with bridge._OPENER.open(req, timeout=timeout) as r:
            raw = r.read(limit + 1)
            if len(raw) > limit: raise ValueError("response-size")
            return json.loads(raw)
    except Exception: raise bridge.BridgeError("transport-error") from None


def valid_guid(guid): return type(guid) is str and GUID_RE.fullmatch(guid) is not None


class BlueBubblesReactor:
    """HASS-TAPBACK-1: one tapback on one message, `POST /api/v1/message/react` on loopback BlueBubbles. Nothing else: it cannot
    send a text. A reaction outside TAPBACKS or a guid that is not a plain message guid raises ValueError BEFORE any network
    call. The password is read fresh from its private file and goes only in the `password` query parameter; errors carry no URL."""
    def __init__(self, base_url, password_file, transport=None, timeout=ACK_TIMEOUT):
        self.base, self.password_file, self.timeout = base_url.rstrip("/"), password_file, timeout
        self.transport = transport or bridge._urllib_transport

    def react(self, chat, guid, reaction):
        if reaction not in TAPBACKS or not valid_guid(guid) or type(chat) is not str or not chat: raise ValueError("react-args")
        try: password = private_read(self.password_file, 4096).decode().strip()
        except (ValueError, UnicodeDecodeError): password = ""
        if not password: raise bridge.BridgeError("password-unreadable")
        body = json.dumps({"chatGuid": chat, "selectedMessageGuid": guid, "reaction": reaction, "partIndex": 0}).encode()
        url = f"{self.base}{REACT_PATH}?{urllib.parse.urlencode({'password': password})}"
        try: status = self.transport(url, body, {"Content-Type": "application/json"}, self.timeout)
        except Exception: raise bridge.BridgeError("transport-error") from None  # noqa: BLE001 - its text may hold the URL
        if not (type(status) is int and 200 <= status < 300): raise bridge.BridgeError("http-error", status if type(status) is int else None)


class Spool:
    def __init__(self, directory, now, ready=False):
        """ready=True: the file and its tables already exist (an ack worker's own connection): no schema or meta writes."""
        self.clock = time.time
        self.directory = directory
        path = Path(directory) / "spool.sqlite3"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o177: raise ValueError("spool-file")
        finally: os.close(fd)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.stage = stagelog.off  # HASS-FAST-1: the Forwarder swaps in a StageLog
        if ready: return
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS inbound(provider_id TEXT PRIMARY KEY,payload TEXT,state TEXT,tries INTEGER,"
            "next_try_at REAL,created_at REAL,done_at REAL);"
            "CREATE TABLE IF NOT EXISTS fetch(guid TEXT,event TEXT,created_at REAL,tries INTEGER DEFAULT 0,next_try_at REAL DEFAULT 0,PRIMARY KEY(guid,event));"
            "CREATE TABLE IF NOT EXISTS meta(name TEXT PRIMARY KEY,value REAL);"
            "CREATE TABLE IF NOT EXISTS sent(reply_id INTEGER PRIMARY KEY,sent_at REAL);"
            "CREATE TABLE IF NOT EXISTS sent_pics(reply_id INTEGER,idx INTEGER,sent_at REAL,PRIMARY KEY(reply_id,idx));"
            "CREATE TABLE IF NOT EXISTS card_result(reply_id INTEGER PRIMARY KEY,outcome TEXT NOT NULL,sha256 TEXT,provider_guid TEXT);"
            "CREATE TABLE IF NOT EXISTS pic_tries(reply_id INTEGER,idx INTEGER,tries INTEGER,next_try_at REAL,PRIMARY KEY(reply_id,idx));"
            "CREATE TABLE IF NOT EXISTS nonces(nonce TEXT PRIMARY KEY,seen_at REAL);"
            "CREATE TABLE IF NOT EXISTS drops(reason TEXT PRIMARY KEY,count INTEGER);"
            "CREATE TABLE IF NOT EXISTS ack(provider_id TEXT PRIMARY KEY,state TEXT,created_at REAL,done_at REAL);"
            "CREATE TABLE IF NOT EXISTS photo_posts(at REAL);"
            "CREATE TABLE IF NOT EXISTS photo_jobs(guid TEXT,idx INTEGER,count INTEGER,body TEXT,tries INTEGER DEFAULT 0,"
            "next_try_at REAL DEFAULT 0,created_at REAL,done INTEGER DEFAULT 0,code TEXT,PRIMARY KEY(guid,idx));"
            "CREATE TABLE IF NOT EXISTS ack_chat(provider_id TEXT PRIMARY KEY,chat TEXT);")  # HASS-OWNERS-2: the owner chat a tapback goes back to
        for name, value in (("start_ms", int(now * 1000)), ("last_seen_ms", int(now * 1000)), ("outage_since", 0), ("outage_notified", 0), ("last_rejected", 0),
                            ("fast_until", 0), ("rejected_streak", 0)):
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

    def accept(self, event, owner, now, via="webhook", also=None):
        msg = bridge.normalize(event)
        if isinstance(msg, bridge.Drop): return self.drop(msg.reason)
        owners = (owner,) if isinstance(owner, str) else tuple(owner)  # HASS-OWNERS-2: one chat, or every owner chat
        if msg.chat not in owners and (also is None or msg.chat != also): return self.drop("other-chat")  # `also`: G's one chat, when set
        ms = int(datetime.fromisoformat(msg.received_at).timestamp() * 1000)
        if ms < self.get("start_ms"): return self.drop("history")
        new = self.db.execute("INSERT OR IGNORE INTO inbound VALUES (?,?,'pending',0,0,?,NULL)",
                              (msg.provider_id, json.dumps(asdict(msg)), now)).rowcount
        if new:  # a repeat (webhook then catch-up, a replay, a restart) never reaches this line
            self.stage("accepted", msg.provider_id, via=via)
            self.owner_arrived(msg, msg.chat if msg.chat in owners else owners[0], ms)  # an owner's own chat, else (G's chat) the main one: no ack

    def owner_arrived(self, msg, owner, ms):
        """HASS-FAST-1: a newly stored message from the owner's own address in the owner's one-to-one chat, sent just now,
        queues exactly one ack (INSERT OR IGNORE on the message id) and opens the fast reply pull. Never a stranger's, Hass's
        own (from_me), an edit or a reaction, or an old message found by catch-up. Whether changes are paused is NOT decided
        here: the ack thread asks the host fresh just before it sends (see Forwarder._ack)."""
        try:
            address = owner.split(";", 2)[2]
            mine = (msg.kind == "new" and not msg.from_me and msg.chat == owner
                    and sender_key(msg.sender) is not None and sender_key(msg.sender) == sender_key(address))
            if not mine or self.clock() * 1000 - ms > ACK_MAX_AGE * 1000: return
            self.set("fast_until", self.clock() + FAST_WINDOW)
            self.db.execute("INSERT OR IGNORE INTO ack VALUES (?,'pending',?,NULL)", (msg.provider_id, self.clock()))
            self.db.execute("INSERT OR IGNORE INTO ack_chat VALUES (?,?)", (msg.provider_id, owner))  # HASS-OWNERS-2: the tapback goes to this chat
        except Exception:  # noqa: BLE001 - an ack is never worth losing the message that was just stored
            pass

    def status(self):
        counts = {s: self.db.execute("SELECT COUNT(*) FROM inbound WHERE state=?", (s,)).fetchone()[0] for s in ("pending", "done", "dropped")}
        counts.update(pending_fetch=self.db.execute("SELECT COUNT(*) FROM fetch").fetchone()[0],
                      dropped_events=self.db.execute("SELECT COALESCE(SUM(count),0) FROM drops").fetchone()[0],
                      sent=self.db.execute("SELECT COUNT(*) FROM sent").fetchone()[0], last_rejected=self.get("last_rejected"))
        head = self.db.execute("SELECT created_at,tries FROM inbound WHERE state='pending' ORDER BY created_at,rowid LIMIT 1").fetchone()
        counts.update(oldest_pending_s=max(0, int(self.clock() - head[0])) if head else 0, head_tries=head[1] if head else 0,
                      rejected_streak=int(self.get("rejected_streak")))
        return counts


class CardAttachmentSender(bridge_attach.BlueBubblesAttachmentSender):
    """Reuse the validated multipart sender, but read the bounded provider result for tracked cards."""
    def __init__(self, base_url, password_file, owners):
        super().__init__(base_url, password_file, owners, self._result_transport)

    def send_png(self, chat, data, name):
        self.guid = None
        super().send_png(chat, data, name)
        return self.guid

    def _result_transport(self, url, body, headers, timeout):
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with bridge._OPENER.open(request, timeout=timeout) as response:
                if not 200 <= response.status < 300: return response.status
                raw = response.read(MAX_BODY + 1)
                if len(raw) > MAX_BODY: raise ValueError("attachment-result-limit")
                if raw:
                    result = json.loads(raw)
                    if type(result) is not dict: raise ValueError("attachment-result-shape")
                    status = result.get("status", response.status)
                    if type(status) is not int: raise ValueError("attachment-result-status")
                    if not 200 <= status < 300: return status
                    data = result.get("data")
                    guid = data.get("guid") if type(data) is dict else None
                    if relay.valid_receipt_guid(guid): self.guid = guid
                return response.status
        except urllib.error.HTTPError as exc:
            exc.close()
            return exc.code


class Forwarder:
    def __init__(self, cfg, spool, clock=time.time, transport=request_json, sender=None, attach=None, stage=None, reactor=None):
        self.cfg, self.spool, self.clock, self.transport = cfg, spool, clock, transport
        spool.clock = clock
        self.stage = spool.stage = stage or stagelog.off  # HASS-FAST-1: read-only stage times (main() passes a StageLog)
        self.secret = key_read(cfg["secretFile"])
        self.sender = sender or bridge.BlueBubblesSender(f'http://127.0.0.1:{cfg["bbPort"]}', cfg["bbPasswordFile"])
        # The tapback has its own object (it can only react, never send a text), its own short timeout and its own thread.
        self.reactor = reactor or BlueBubblesReactor(f'http://127.0.0.1:{cfg["bbPort"]}', cfg["bbPasswordFile"])
        self.probe_cache, self.probe_lock = None, threading.Lock()  # (valid until, blocker reason or None)
        self.attach = attach or bridge_attach.BlueBubblesAttachmentSender(
            f'http://127.0.0.1:{cfg["bbPort"]}', cfg["bbPasswordFile"], owner_chats(cfg))
        self.card_attach = attach or CardAttachmentSender(
            f'http://127.0.0.1:{cfg["bbPort"]}', cfg["bbPasswordFile"], owner_chats(cfg))
        self.big = functools.partial(request_json, limit=MAX_REPLY) if transport is request_json else transport
        self.quick = functools.partial(request_json, timeout=ACK_STATE_TIMEOUT) if transport is request_json else transport
        self.next_poll = self.next_pull = 0
        self.query_offset, self.query_high = 0, 0
        self.query_other = {}  # HASS-OWNERS-2: the other owner chats' page state
        self.ack_thread, self.ack_stop, self.ack_wake = None, threading.Event(), threading.Event()
        self.ack_live, self.ack_lock = set(), threading.Lock()
        self.photo_worker = None

    def bb(self, path, body=None):
        password = private_read(self.cfg["bbPasswordFile"], 4096).decode().strip()
        sep = "&" if "?" in path else "?"
        return self.transport(f'http://127.0.0.1:{self.cfg["bbPort"]}{path}{sep}{urllib.parse.urlencode({"password": password})}', body)["data"]

    def post(self, path, env, big=False, quick=False, timeout=None):
        transport = self.big if big else self.quick if quick else self.transport
        if timeout is not None and self.transport is request_json:
            return request_json(self.cfg["receiverUrl"] + path, env, limit=MAX_REPLY if big else 1024 * 1024, timeout=timeout)
        return transport(self.cfg["receiverUrl"] + path, env)

    def push_photos(self, msg):
        """One bounded worker: even a trickling socket cannot hold text or tapbacks."""
        if (msg.kind != "new" or msg.from_me or msg.chat not in owner_chats(self.cfg)
                or not re.fullmatch(r"iMessage;-;[^;\s]+", msg.chat)
                or sender_key(msg.sender) is None or sender_key(msg.sender) != sender_key(msg.chat.split(";", 2)[2])
                or not 1 <= msg.attachments <= media.MAX_PHOTOS_PER_MESSAGE
                or not bridge_photos._valid_guid(msg.provider_id)): return
        db = self.spool.db
        db.execute("DELETE FROM photo_jobs WHERE done=1 AND created_at<? AND NOT EXISTS (SELECT 1 FROM inbound WHERE provider_id=guid AND state='pending')", (self.clock() - 86400,))
        if (not db.execute("SELECT 1 FROM photo_jobs WHERE guid=?", (msg.provider_id,)).fetchone()
                and db.execute("SELECT COUNT(DISTINCT guid) FROM photo_jobs WHERE done=0").fetchone()[0] >= CATCH_UP_PAGE):
            raise ValueError("photo-queue-full")  # retain inbound; never accept text and discard its photo job
        db.executemany("INSERT OR IGNORE INTO photo_jobs(guid,idx,count,created_at) VALUES (?,?,?,?)",
                       [(msg.provider_id, i, msg.attachments, self.clock()) for i in range(msg.attachments)])
        self.retry_photos()

    def retry_photos(self):
        self.spool.db.execute("UPDATE photo_jobs SET done=1,body=NULL,code='expired' WHERE done=0 AND created_at<=?", (self.clock() - 1800,))
        if self.photo_worker is not None and self.photo_worker.is_alive(): return
        row = self.spool.db.execute("SELECT guid,count,tries FROM photo_jobs WHERE done=0 AND next_try_at<=? ORDER BY created_at,idx LIMIT 1", (self.clock(),)).fetchone()
        if row is None: return
        done, deadline = threading.Event(), time.monotonic() + 30
        def work():
            spool = Spool(self.spool.directory, self.clock(), ready=True)
            try: self._push_photos(*row[:2], deadline, spool)
            except Exception:  # fixed code only; the durable host outbox owns the single owner failure reply
                spool.db.execute("UPDATE photo_jobs SET tries=tries+1,next_try_at=?,code=COALESCE(code,'retry') WHERE guid=? AND done=0",
                                 (self.clock() + min(300, 30 * 2 ** min(row[2], 4)), row[0]))
            finally:
                spool.db.close()
                done.set()
        self.photo_worker = threading.Thread(target=work, name="hass-photo", daemon=True)
        self.photo_worker.start()
        done.wait(max(0, deadline - time.monotonic()))

    def _push_photos(self, guid, count, deadline, spool):
        def remaining():
            left = deadline - time.monotonic()
            if left <= 0: raise TimeoutError("photo-budget")
            return left
        def download(url, headers, timeout, limit):
            return bridge_photos._urllib_transport(url, headers, min(timeout, remaining()), limit)
        photos = bridge_photos.BlueBubblesPhotos(f'http://127.0.0.1:{self.cfg["bbPort"]}',
                                                self.cfg["bbPasswordFile"], transport=download, timeout=30)
        data, code = None, None
        for idx, saved, tries, created in spool.db.execute("SELECT idx,body,tries,created_at FROM photo_jobs WHERE guid=? AND done=0 ORDER BY idx", (guid,)).fetchall():
            if self.clock() - created >= 1800:
                spool.db.execute("UPDATE photo_jobs SET done=1,body=NULL,code='expired' WHERE guid=? AND idx=?", (guid, idx))
                continue
            if saved is None and data is None:
                try: data = photos.fetch(guid, count)
                except Exception as exc:
                    if tries < 3: raise
                    real = exc.code if isinstance(exc, bridge.BridgeError) else None
                    code = real if real == "too-large" or real in relay.FETCH_DIAG else "fetch-failed"
                    data = [None] * count
            stored = json.loads(saved) if saved is not None else None
            raw = data[idx] if stored is None else base64.b64decode(stored["b64"]) if stored["op"] == "photo" else None
            remaining()
            failure = stored.get("code") if stored is not None else code
            if raw is not None:
                try:
                    if media.sniff(raw) not in ("jpeg", "png") or len(raw) > relay.PHOTO_MAX:
                        with tempfile.TemporaryDirectory(prefix="hass-photo-") as tmp:
                            src, dst = Path(tmp) / "in", Path(tmp) / "out.jpg"
                            src.write_bytes(raw)
                            subprocess.run(["/usr/bin/sips", "-s", "format", "jpeg", "-s", "formatOptions", "85",
                                            "-Z", "4096", str(src), "--out", str(dst)],
                                           timeout=min(30, remaining()), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            with dst.open("rb") as stream: raw = stream.read(relay.PHOTO_MAX + 1)
                    failure = "too-large" if len(raw) > relay.PHOTO_MAX else None if media.sniff(raw) in ("jpeg", "png") else "unsupported-type"
                except subprocess.TimeoutExpired:
                    spool.db.execute("UPDATE photo_jobs SET code='conversion-timeout' WHERE guid=? AND idx=?", (guid, idx))
                    if tries < 3: raise
                    failure = "fetch-failed"
                except (subprocess.CalledProcessError, OSError):
                    failure = "too-large" if len(raw) > relay.PHOTO_MAX else "unsupported-type"
            body = {"op": "photo-refused" if failure else "photo", "guid": guid, "idx": idx, "count": count}
            if failure: body["code"] = failure
            else:
                assert raw is not None
                body.update(sha256=hashlib.sha256(raw).hexdigest(), b64=base64.b64encode(raw).decode("ascii"))
            if saved is not None: body = json.loads(saved)
            else: spool.db.execute("UPDATE photo_jobs SET body=?,code=? WHERE guid=? AND idx=?", (json.dumps(body), failure, guid, idx))
            now = self.clock()
            spool.db.execute("DELETE FROM photo_posts WHERE at<=?", (now - 60,))
            if spool.db.execute("SELECT COUNT(*) FROM photo_posts").fetchone()[0] >= 8:
                spool.db.execute("UPDATE photo_jobs SET next_try_at=?,code='rate-limit' WHERE guid=? AND done=0", (now + 60, guid))
                return
            env = relay.seal_control(body, self.secret, nonce=secrets.token_hex(16), now=now)
            spool.db.execute("INSERT INTO photo_posts VALUES (?)", (now,))
            sent = self.post("/v1/photo", env, big=True, timeout=remaining())
            answer = relay.unseal_control(sent, self.secret, now=self.clock(), seen=spool)
            if answer != {"op": "photo-ok", "guid": guid, "idx": idx}: raise ValueError("photo-reply")
            spool.db.execute("UPDATE photo_jobs SET done=1,body=NULL,code=? WHERE guid=? AND idx=?", (body.get("code"), guid, idx))

    def fetch(self):
        row = self.spool.db.execute("SELECT guid,event,created_at,tries,next_try_at FROM fetch ORDER BY created_at,rowid LIMIT 1").fetchone()
        if row is None or row[4] > self.clock(): return
        guid, kind, created, tries, _ = row
        try:
            msg = self.bb("/api/v1/message/" + urllib.parse.quote(guid, safe="") + "?with=chats,handle,attachment")
            if type(msg) is not dict or msg.get("guid") != guid: raise ValueError("refetch-shape")
            with self.spool.db:
                self.spool.accept({"type": kind, "data": msg}, owner_chats(self.cfg), created, also=self.cfg.get("gChat"))
                self.spool.db.execute("DELETE FROM fetch WHERE guid=? AND event=?", (guid, kind))
        except (bridge.BridgeError, ValueError, KeyError, TypeError):
            self.spool.db.execute("UPDATE fetch SET tries=tries+1,next_try_at=? WHERE guid=? AND event=?",
                                  (self.clock() + min(300, 5 * 2 ** min(tries, 6)), guid, kind))

    def catch_up(self):
        """Each owner chat is asked on its own (HASS-OWNERS-2), with its own cursor and page offset; the main chat keeps the
        original `last_seen_ms` cursor. One chat failing does not stop the others; the first failure is raised afterwards."""
        full, error = False, None
        for n, chat in enumerate(owner_chats(self.cfg)):
            try: full = self.catch_up_chat(chat, n == 0) or full
            except (bridge.BridgeError, bridge.EnvelopeError, ValueError, KeyError, TypeError) as exc: error = error or exc
        if error is not None: raise error
        self.next_poll = self.clock() + (0 if full else CATCH_UP_EVERY)

    def catch_up_chat(self, chat, main):
        """One page of one owner chat; True when the page was full (more may be waiting)."""
        name = "last_seen_ms" if main else "last_seen_ms." + hashlib.sha256(chat.encode()).hexdigest()[:16]
        if not main: self.spool.db.execute("INSERT OR IGNORE INTO meta VALUES (?,?)", (name, int(self.spool.get("start_ms"))))
        state = None if main else self.query_other.setdefault(chat, [0, 0])  # [page offset, highest cursor seen]
        offset, high = (self.query_offset, self.query_high) if main else state
        cursor = int(self.spool.get(name))
        query = {"chatGuid": chat, "after": cursor, "sort": "ASC", "limit": CATCH_UP_PAGE,
                 "with": ["chats", "handle", "attachment"]}
        # Keep the durable cursor fixed until a page is exhausted, including timestamp ties.
        if offset: query["offset"] = offset
        rows = self.bb("/api/v1/message/query", query)
        if type(rows) is not list: raise ValueError("query-shape")
        for msg in rows:
            if type(msg) is not dict or type(msg.get("dateCreated")) is not int: raise ValueError("query-shape")
        owners = owner_chats(self.cfg)
        for msg in rows:
            self.spool.accept({"type": "new-message", "data": msg}, owners, self.clock(), via="poll")
            if type(msg.get("dateEdited")) is int and msg["dateEdited"] > 0:
                self.spool.accept({"type": "updated-message", "data": msg}, owners, self.clock(), via="poll")
            cursor = max(cursor, msg["dateCreated"])
        high = max(high, cursor)
        if len(rows) == CATCH_UP_PAGE: offset += CATCH_UP_PAGE
        else:
            self.spool.set(name, high)
            offset = 0
        if main: self.query_offset, self.query_high = offset, high
        else: state[:] = [offset, high]
        return len(rows) == CATCH_UP_PAGE

    def notice_chat(self, payload):
        """HASS-OWNERS-2: the outage notice goes to the owner chat of the message that is stuck (the main chat for anything else)."""
        try: chat = json.loads(payload)["chat"]
        except (TypeError, ValueError, KeyError): chat = None
        return chat if chat in owner_chats(self.cfg) else self.cfg["ownerChat"]

    def deliver(self):
        db, now = self.spool.db, self.clock()
        row = db.execute("SELECT rowid,payload,tries,next_try_at,created_at FROM inbound WHERE state='pending' ORDER BY created_at,rowid LIMIT 1").fetchone()
        if row is None or row[3] > now: return
        # A failed earlier refetch must not let later messages pass it.
        if db.execute("SELECT 1 FROM fetch WHERE created_at<=? LIMIT 1", (row[4],)).fetchone(): return
        try:
            inbound = bridge.Inbound(**json.loads(row[1]))
            self.push_photos(inbound)  # durably queue before text can erase its payload
            env = bridge.seal(inbound, self.secret, nonce=secrets.token_hex(16), now=self.clock())
            self.stage("post-start", inbound.provider_id)
            result = self.post("/v1/inbound", env)["result"]
            if result not in ("queued", "duplicate", "history", "rejected"): raise ValueError("post-shape")
            self.stage("post-end", inbound.provider_id)
        except (bridge.BridgeError, ValueError, KeyError, TypeError):
            db.execute("UPDATE inbound SET tries=tries+1,next_try_at=? WHERE rowid=?", (now + min(300, 5 * 2 ** min(row[2], 6)), row[0]))
            if not self.spool.get("outage_since"): self.spool.set("outage_since", now)
            if now - row[4] >= 600 and not self.spool.get("outage_notified"):
                self.sender.send(self.notice_chat(row[1]), NOTICE)
                self.spool.set("outage_notified", 1)
            return
        for name in ("outage_since", "outage_notified"): self.spool.set(name, 0)
        if result == "rejected":
            self.spool.set("last_rejected", now)
            self.spool.set("rejected_streak", self.spool.get("rejected_streak") + 1)
            db.execute("UPDATE inbound SET tries=tries+1,next_try_at=? WHERE rowid=?", (now + 60, row[0]))
        else:
            self.spool.set("rejected_streak", 0)
            db.execute("UPDATE inbound SET state='done',payload=NULL,done_at=? WHERE rowid=?", (now, row[0]))

    def control(self, body, expected, big=False, spool=None, quick=False):
        env = relay.seal_control(body, self.secret, nonce=secrets.token_hex(16), now=self.clock())
        sent = self.post("/v1/relay", env, quick=True) if quick else self.post("/v1/relay", env, big)
        answer = relay.unseal_control(sent, self.secret, now=self.clock(), seen=spool or self.spool)
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

    def card_result(self, item):
        """None while retrying. Persist the exact outcome before making an ACK or sending the prompt."""
        db, rid = self.spool.db, item["id"]
        row = db.execute("SELECT outcome,sha256,provider_guid FROM card_result WHERE reply_id=?", (rid,)).fetchone()
        if row is None:
            outcome, digest, guid = "missing-file", None, None
            if item.get("shots"):
                key = (rid, 0)
                tries, retry_at = db.execute("SELECT tries,next_try_at FROM pic_tries WHERE reply_id=? AND idx=?", key).fetchone() or (0, 0)
                if retry_at > self.clock(): return None
                try:
                    data = self.fetch_picture(rid, item["shots"][0])
                    if data is not None:
                        guid = self.card_attach.send_png(item["chat"], data, f"hass-{rid}-0.png")
                        outcome, digest = "sent", hashlib.sha256(data).hexdigest()
                except (bridge.BridgeError, ValueError, KeyError, TypeError):
                    if tries + 1 < 3:
                        db.execute("INSERT OR REPLACE INTO pic_tries VALUES (?,?,?,?)", (*key, tries + 1, self.clock() + PIC_RETRY[tries]))
                        return None
                    outcome = "failed"
            if not relay.valid_receipt_guid(guid): guid = None
            row = (outcome, digest, guid)
            db.execute("INSERT INTO card_result VALUES (?,?,?,?)", (rid, *row))
        outcome, digest, guid = row
        return ({"outcome": outcome, "png_sha256": digest, "provider_guid": guid}
                if outcome == "sent" else {"outcome": outcome})

    def pull(self):
        ids, receipts = [], []
        try:
            for item in self.control({"op": "pull", "max": 5, "card_receipts": True}, "replies")["items"]:
                receipt = None
                if item.get("card"):
                    if item["chat"] not in owner_chats(self.cfg): continue
                    receipt = self.card_result(item)
                    if receipt is None: continue
                    if receipt["outcome"] != "sent": item = {**item, "text": CARD_GAVE_UP}
                if item["chat"] not in owner_chats(self.cfg) and not (item["chat"] == self.cfg.get("gChat") and item["pictures"] == 0): continue  # G's chat: text only
                if not self.spool.db.execute("SELECT 1 FROM sent WHERE reply_id=?", (item["id"],)).fetchone():
                    self.stage("reply-pulled", item["id"])
                    self.stage("bb-send-start", item["id"])
                    try:
                        self.sender.send(item["chat"], item["text"], (None,) * item["pictures"])
                    except Exception:  # noqa: BLE001 - G's chat must never hold back Mike's replies
                        if item["chat"] == self.cfg["ownerChat"]: raise
                        if item["chat"] != self.cfg.get("gChat"):  # HASS-OWNERS-2: another owner's chat: not given up, not holding back the rows behind it
                            self.stage("owner-send-failed", item["id"])
                            continue
                        self.stage("g-send-failed", item["id"])
                        ids.append(item["id"])  # given up on, so it is not handed out again and again ahead of Mike's rows
                        continue
                    self.stage("bb-send-end", item["id"])
                    self.spool.db.execute("INSERT INTO sent VALUES (?,?)", (item["id"], self.clock()))
                if receipt is not None: receipts.append({"op": "ack", "ids": [item["id"]], "receipt": receipt})
                elif self.deliver_shots(item): ids.append(item["id"])
        finally:
            if ids: self.control({"op": "ack", "ids": ids}, "acked")
            for ack in receipts: self.control(ack, "acked")

    # -- HASS-FAST-1 / HASS-TAPBACK-1: the ack (a real tapback). It runs on its own thread with its own SQLite connection, so nothing slow in the main loop
    # (a reply pull, a picture, a catch-up query, a post to the receiver) can delay it and a slow or failing react can
    # never delay the main loop. The only things the two share are the spool file (atomic row claims) and the nonce table.
    def tapback_blocker(self):
        """None when BlueBubbles says the Private API is on AND its helper is connected (the existing GET-only server/info
        probe, 0.5 s limit); otherwise the reason code: private_api_off, helper_disconnected, or private_api_unknown (no usable answer:
        fail closed). Reused for PROBE_TTL seconds (PROBE_FAIL_TTL for an unanswered probe) so a burst asks once."""
        with self.probe_lock:
            now = self.clock()
            if self.probe_cache is not None and self.probe_cache[0] > now: return self.probe_cache[1]
            try:
                password = private_read(self.cfg["bbPasswordFile"], 4096).decode().strip()
                info = self.quick(f'http://127.0.0.1:{self.cfg["bbPort"]}/api/v1/server/info?{urllib.parse.urlencode({"password": password})}')["data"]
                private, helper = info.get("private_api"), info.get("helper_connected")
                if type(private) is not bool or type(helper) is not bool: raise ValueError("info-shape")
                reason, ttl = (None if private and helper else "private_api_off" if not private else "helper_disconnected"), PROBE_TTL
            except Exception:  # noqa: BLE001 - unknown is not "on"
                reason, ttl = "private_api_unknown", PROBE_FAIL_TTL
            self.probe_cache = (now + ttl, reason)
            return reason

    def host_paused(self, spool):
        """True when changes are paused or a pause command is on its way; None when the host cannot be asked right now.
        Asked fresh before every tapback (nothing cached): the host reads its own pause flag and its unread queue, read-only."""
        try:
            paused = self.control({"op": "state"}, "state", spool=spool, quick=True)["paused"]
            return paused if type(paused) is bool else None
        except (bridge.BridgeError, bridge.EnvelopeError, ValueError, KeyError, TypeError):
            return None

    def pause_ahead(self, spool, created):
        """True when a pause command (or a message that cannot be read) is stored here and not yet handed to the host, or an
        earlier doorbell is still unresolved (what it says is unknown): the host cannot know about those, so no tapback yet."""
        db = spool.db
        if db.execute("SELECT 1 FROM fetch WHERE event='new-message' AND created_at<=? LIMIT 1", (created,)).fetchone(): return True
        for (payload,) in db.execute("SELECT payload FROM inbound WHERE state='pending'"):
            try:
                text = json.loads(payload)["text"]
                found = read_command(text) or parse_command(text)
            except (TypeError, ValueError, KeyError, AttributeError): return True
            if found and found[0] == "pause": return True
        return False

    def ack(self, spool=None):
        try: self._ack(spool or self.spool)
        except Exception: print("retry", file=sys.stderr)  # noqa: BLE001 - an ack can never stop the loop (a broken table, a full disk)

    def _ack(self, spool):
        """Inline path (no ack thread: unit tests and `ack()`): decide up to three pending rows one after another with
        _ack_row. Returns True when three were done (more may be waiting)."""
        db = spool.db
        for _ in range(3):
            row = db.execute("SELECT provider_id,created_at FROM ack WHERE state='pending' ORDER BY created_at,rowid LIMIT 1").fetchone()
            if row is None: return False
            if self._claim(spool, row[0]): self._ack_row(spool, *row)
        return True

    def _claim(self, spool, pid):
        """pending -> checking, atomic: exactly one caller (thread or process) gets True for a given message id."""
        return spool.db.execute("UPDATE ack SET state='checking',done_at=? WHERE provider_id=? AND state='pending'", (self.clock(), pid)).rowcount == 1

    def _ack_row(self, spool, pid, created):
        """Decide one claimed (`checking`) row, once and finally, and send its tapback if it is due. At most once per message id:
        checking -> sending (committed before the call) -> sent | late | react_failed, and a row found `sending` after a crash is
        never sent again. No tapback (and the state says why, and `ack_skipped reason=<state>` goes to the log) when the ack is
        switched off, when it is older than ACK_STALE, when the message guid or the configured reaction is not valid, when a
        pause command is ahead of it (stored here or queued at the host), when the host says paused, when it cannot be asked
        right now (fail closed), or when BlueBubbles reports the Private API off, its helper not connected or not answering.
        A failure or timeout is recorded and ignored; it is NEVER turned into a text. A tapback that was sent but not confirmed
        within ACK_BUDGET of the message being stored is recorded `late`, never `sent`: it is not counted as on time."""
        db = spool.db
        now = self.clock()

        def close(state):
            db.execute("UPDATE ack SET state=?,done_at=? WHERE provider_id=? AND state='checking'", (state, now, pid))
            print("ack_skipped", f"reason={state}", file=sys.stderr)  # a reason code only: no id, text, chat or sender
        if now - created > ACK_STALE: return close("stale")
        if not self.cfg.get("ack", True): return close("off")
        reaction = self.cfg.get("ack_reaction", ACK_REACTION)
        if reaction not in TAPBACKS: return close("bad_reaction")
        if not valid_guid(pid): return close("bad_guid")
        row = db.execute("SELECT chat FROM ack_chat WHERE provider_id=?", (pid,)).fetchone()  # HASS-OWNERS-2: back into the chat the message came from
        chat = row[0] if row and row[0] in owner_chats(self.cfg) else None if "ownerChats" in self.cfg else self.cfg["ownerChat"]
        if chat is None: return close("no_chat")
        if self.pause_ahead(spool, created): return close("paused")
        paused = self.host_paused(spool)
        if paused is not False: return close("paused" if paused else "unknown")
        blocker = self.tapback_blocker()
        if blocker is not None: return close(blocker)
        if db.execute("UPDATE ack SET state='sending',done_at=? WHERE provider_id=? AND state='checking'", (now, pid)).rowcount != 1: return
        self.stage("ack-start", pid)
        try:
            self.reactor.react(chat, pid, reaction)
            state = "sent"
        except Exception:  # noqa: BLE001 - an ack never blocks, retries or leaks: the state records it, nothing else
            state = "react_failed"
            print("ack_skipped", f"reason={state}", file=sys.stderr)
        done = self.clock()
        if state == "sent" and done - created > ACK_BUDGET: state = "late"
        db.execute("UPDATE ack SET state=?,done_at=? WHERE provider_id=?", (state, done, pid))
        self.stage("ack-end", pid, outcome=state)

    def ack_kick(self):
        """Tell the ack thread there is work; with no thread running (unit tests) do the work here instead."""
        if self.ack_thread is not None: self.ack_wake.set()
        else: self.ack()

    def start_ack(self):
        """Start the ack dispatcher thread (main() does; it owns its own spool connection, opened inside the thread)."""
        if self.ack_thread is not None: return
        self.ack_stop.clear()
        self.ack_thread = threading.Thread(target=self._ack_loop, name="hass-ack", daemon=True)
        self.ack_thread.start()

    def stop_ack(self):
        self.ack_stop.set()
        self.ack_wake.set()
        if self.ack_thread is not None: self.ack_thread.join(ACK_TIMEOUT + ACK_STATE_TIMEOUT + 2)
        self.ack_thread = None
        with self.ack_lock: live = list(self.ack_live)
        for worker in live: worker.join(ACK_TIMEOUT + ACK_STATE_TIMEOUT + 2)

    def _ack_loop(self):
        """The dispatcher: it only claims pending rows and starts one worker thread per claimed row, so every attempt starts
        at once instead of waiting behind the sends before it (a burst of four 0.8 s sends used to start at 0.1, 0.9, 1.7 and
        2.5 s). It never sends anything itself."""
        spool = None
        try:
            while not self.ack_stop.is_set():
                self.ack_wake.wait(ACK_TICK)
                self.ack_wake.clear()
                if self.ack_stop.is_set(): break
                try:
                    if spool is None:
                        spool = Spool(self.spool.directory, self.clock())
                        spool.clock, spool.stage = self.clock, self.stage
                    self._ack_dispatch(spool)
                except Exception:  # noqa: BLE001 - the thread outlives any single failure (a locked file, a full disk)
                    print("retry", file=sys.stderr)
        finally:
            if spool is not None:
                try: spool.db.close()
                except sqlite3.Error: pass

    def _ack_dispatch(self, spool):
        db = spool.db
        db.execute("UPDATE ack SET state='pending' WHERE state='checking' AND done_at<?", (self.clock() - ACK_CLAIM_STALE,))
        with self.ack_lock: room = ACK_WORKERS - len(self.ack_live)  # fewer than the pending rows only past one catch-up page; the rest follow as workers finish
        if room <= 0: return
        db.execute("BEGIN IMMEDIATE")  # one transaction claims the whole burst (pending -> checking, atomic: a row is claimed by exactly one caller)
        try:
            rows = db.execute("SELECT provider_id,created_at FROM ack WHERE state='pending' ORDER BY created_at,rowid LIMIT ?", (room,)).fetchall()
            db.executemany("UPDATE ack SET state='checking',done_at=? WHERE provider_id=? AND state='pending'", [(self.clock(), pid) for pid, _ in rows])
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        for pid, created in rows:
            worker = threading.Thread(target=self._ack_worker, args=(pid, created), name="hass-ack-worker", daemon=True)
            with self.ack_lock: self.ack_live.add(worker)
            try: worker.start()
            except RuntimeError:  # no thread could be started: nothing was sent, the row goes back and the next pass retries it
                with self.ack_lock: self.ack_live.discard(worker)
                db.execute("UPDATE ack SET state='pending' WHERE provider_id=? AND state='checking'", (pid,))

    def _ack_worker(self, pid, created):
        spool = None
        try:
            spool = Spool(self.spool.directory, self.clock(), ready=True)
            spool.clock, spool.stage = self.clock, self.stage
            self._ack_row(spool, pid, created)
        except Exception:  # noqa: BLE001 - one message's failure never touches another's
            print("retry", file=sys.stderr)
        finally:
            if spool is not None:
                try: spool.db.close()
                except sqlite3.Error: pass
            with self.ack_lock: self.ack_live.discard(threading.current_thread())
            self.ack_wake.set()  # a pending row may have been waiting for a free worker

    def cycle(self):
        fast = self.clock() < self.spool.get("fast_until")  # an owner message arrived in the last FAST_WINDOW seconds
        if fast: self.next_pull = min(self.next_pull, self.clock() + PULL_FAST)  # do not finish a slow wait first
        # Acceptance comes first (a webhook fetch, the catch-up poll) and the ack is kicked right after it, ahead of the
        # reply pull, the pictures and the post to the receiver, none of which can then delay the tapback.
        try: self.fetch()
        except (bridge.BridgeError, ValueError): print("retry", file=sys.stderr)
        self.ack_kick()
        if self.clock() >= self.next_poll:
            self.next_poll = self.clock() + CATCH_UP_EVERY
            try: self.catch_up()
            except (bridge.BridgeError, bridge.EnvelopeError, ValueError, KeyError, TypeError): print("retry", file=sys.stderr)
            finally: self.ack_kick()
        self.retry_photos()
        try: self.deliver()
        except (bridge.BridgeError, ValueError): print("retry", file=sys.stderr)
        if self.clock() >= self.next_pull:
            self.next_pull = self.clock() + (PULL_FAST if fast else PULL_SLOW)
            try: self.pull()
            except (bridge.BridgeError, bridge.EnvelopeError, ValueError, KeyError, TypeError): print("retry", file=sys.stderr)
        self.spool.db.execute("DELETE FROM nonces WHERE seen_at<?", (self.clock() - 86400,))


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
            # GET only, no message, no react call. Says whether this BlueBubbles server can send a tapback now (the runbook's check).
            password = private_read(cfg["bbPasswordFile"], 4096).decode().strip()
            info = request_json(f'http://127.0.0.1:{cfg["bbPort"]}/api/v1/server/info?{urllib.parse.urlencode({"password": password})}')["data"]
            private, helper = info.get("private_api") is True, info.get("helper_connected") is True
            version = info.get("server_version")
            if type(version) is not str or not re.fullmatch(r"[0-9A-Za-z.+-]{1,32}", version): version = None
            print(json.dumps({"ackMethod": "tapback", "ackReaction": cfg.get("ack_reaction", ACK_REACTION), "helperConnected": helper, "privateApi": private,
                              "serverVersion": version, "supportedReactions": list(TAPBACKS), "tapbackPossible": private and helper}, sort_keys=True))
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
                fwd.start_ack()
                signal.signal(signal.SIGTERM, lambda *a: stop.set())
                signal.signal(signal.SIGINT, lambda *a: stop.set())
                with Server(cfg, spool) as srv:
                    thread = threading.Thread(target=srv.serve_forever, daemon=True)
                    thread.start()
                    try:
                        while not stop.is_set():
                            fwd.cycle()
                            stop.wait(0.2)
                    finally:
                        fwd.stop_ack()
                        srv.shutdown()
                        thread.join()
        finally: spool.db.close()
        return 0
    except Exception:
        print('{"error": 1}')
        return 2


if __name__ == "__main__": sys.exit(main())

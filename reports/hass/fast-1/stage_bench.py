#!/usr/bin/env python3
"""HASS-FAST-1 stage bench. Synthetic messages only; nothing real is read, sent or restarted.

What runs for real: the Mac forwarder (mac/hass_forwarder.py: Spool, Forwarder.cycle with its real intervals, ack, state,
deliver, pull), the host Server (hass/host.py) answering the forwarder's sealed calls over a loopback socket, the Receiver,
the Worker + Conversation + Inbox + RelayStore (temp state dir and throwaway key), and the stage log (hass/stagelog.py).
What is a stand-in: BlueBubbles (a Python function; its send takes 0 s, a real AppleScript send adds about 1-3 s,
unmeasured here) and the model (FixtureInterpreter, 0 s: the real model time is measured by HASS-MODEL-1 and added in the
report, not simulated). The services run the way they do on the real machines: the forwarder cycle every 0.2 s with its 👀 on its own thread (real HTTP to
the host), the worker cycle every 1 s, and the host's HTTP server in its own thread answering the moment a request arrives.
(One lock stands in for the host's separate processes so the throwaway sqlite connections can be shared between threads.)

Run from the repo root:  python3.12 reports/hass/fast-1/stage_bench.py [--quick] > reports/hass/fast-1/stage-bench-results.json
The variant "before" sets the forwarder back to its pre-FAST-1 intervals (reply pull 5 s, catch-up poll 60 s, no 👀).
"""
import argparse, functools, json, os, sqlite3, sys, tempfile, threading, time, unittest  # noqa: E401
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from hass import host, receiver, stagelog  # noqa: E402
from hass.tests import test_host as host_tests  # noqa: E402
from hass.tests.test_bridge import OWNER_CHAT  # noqa: E402
from hass.tests.test_conversation import OWNER  # noqa: E402
from mac import hass_forwarder as fwd  # noqa: E402

RESULTS = []
sqlite3.connect = functools.partial(sqlite3.connect, check_same_thread=False)  # the throwaway host stores are shared by the bench's threads


def locked(lock, handle):
    def run(h):
        with lock: return handle(h)
    return run


class Bench(host_tests.HostCase):
    now = property(lambda self: datetime.now(timezone.utc), lambda self, value: None)  # real time for every service

    params = {}

    def runTest(self):
        p = self.params
        before = p["variant"] == "before"
        saved = fwd.PULL_FAST, fwd.CATCH_UP_EVERY
        self.addCleanup(lambda: setattr(fwd, "PULL_FAST", saved[0]) or setattr(fwd, "CATCH_UP_EVERY", saved[1]))
        if before: fwd.PULL_FAST, fwd.CATCH_UP_EVERY = fwd.PULL_SLOW, 60
        root = Path(tempfile.mkdtemp(prefix="fast1-bench-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(root, ignore_errors=True))
        root.chmod(0o700)
        for name, data in (("key", host_tests.KEY_HEX), ("token", "ab" * 32), ("password", "synthetic")):
            (root / name).write_text(data)
            (root / name).chmod(0o600)
        log = stagelog.StageLog(root / "stages.jsonl")
        cfg = host.load_host(self.host_json(listen="127.0.0.1:0"), allow_port_zero=True)
        work = self.worker(private=False)
        work.stage = log
        rx = receiver.Receiver(state=self.inbox, settings=None)
        rx.stage = log
        srv = host.Server(cfg, bytes.fromhex(host_tests.KEY_HEX), rx, self.store, self.clock, paused=lambda: host.paused_flag(self.repo.state))
        srv.timeout = 5
        self.addCleanup(srv.server_close)
        lock = threading.RLock()
        handle = host.Handler._handle
        host.Handler._handle = locked(lock, handle)
        self.addCleanup(lambda: setattr(host.Handler, "_handle", handle))
        serving = threading.Thread(target=srv.serve_forever, kwargs=dict(poll_interval=0.02), daemon=True)
        serving.start()
        self.addCleanup(lambda: (srv.shutdown(), serving.join()))
        fcfg = dict(ownerChat=OWNER_CHAT, receiverUrl=f"http://127.0.0.1:{srv.server_port}", bbPort=1, bbPasswordFile=str(root / "password"),
                    secretFile=str(root / "key"), webhookTokenFile=str(root / "token"), spoolDir=str(root), webhookPort=0, ack=not before)
        spool = fwd.Spool(root, time.time())
        self.addCleanup(spool.db.close)
        bb, sent = [], []

        def transport(url, body=None):
            if url.startswith(fcfg["receiverUrl"]): return fwd.request_json(url, body)
            if url.split("?")[0].endswith("/query"): return {"data": [m for m in bb if m["dateCreated"] > body["after"]]}
            return {"data": next(m for m in bb if m["guid"] == url.split("/api/v1/message/")[1].split("?")[0])}

        class Sender:
            def send(self, chat, text, attachments=()):
                time.sleep(p.get("send_s", 0))  # a BlueBubbles send that takes this long (0 in the default scenarios)
                sent.append((time.time(), text))
        # An ack would be a second Sender call; the bench tells them apart by text, the real code by the ack table.
        f = fwd.Forwarder(fcfg, spool, time.time, transport, Sender(), stage=log)
        f.quick = functools.partial(fwd.request_json, timeout=fwd.ACK_STATE_TIMEOUT)  # as the real default transport does
        f.start_ack()  # the 👀 goes out from its own thread, the way main() runs it
        self.addCleanup(f.stop_ack)
        guid = "bench-" + p["name"]
        started, send_at, next_worker, done_at = time.time(), None, 0.0, None
        while time.time() - started < p["limit"]:
            now = time.time()
            if send_at is None and now - started >= p["phase"]:
                send_at = now
                bb.append({"guid": guid, "dateCreated": int(now * 1000), "isFromMe": False, "handle": {"address": OWNER}, "chats": [{"guid": OWNER_CHAT}],
                           "text": p["text"], "attachments": []})
                log("sent", guid)
                if p["webhook"]: spool.doorbell({"type": "new-message", "data": {"guid": guid}}, now)
            f.cycle()
            if now >= next_worker:
                with lock: work.cycle()
                next_worker = now + 1.0
            replies = [s for s in sent if s[1] != fwd.ACK_TEXT]
            if send_at and replies and done_at is None: done_at = time.time()
            if done_at and time.time() - done_at > 1.5: break  # let a late duplicate (there must be none) show up
            time.sleep(0.2 if not p["webhook"] or send_at else 0.05)
        rows = [r for r in stagelog.read(root / "stages.jsonl")]
        (ident, stages), = [t for t in stagelog.table(rows) if t[0] == stagelog.short(guid)] or [(None, {})]
        accepted_via = next((r.get("via") for r in rows if r["stage"] == "accepted" and r["id"] == ident), None)
        if p.get("warm"): return
        RESULTS.append({"name": p["name"], "variant": p["variant"], "text": p["text"], "webhook": p["webhook"], "phase_s": p["phase"],
                        "via": accepted_via, "stages_s_after_sent": stages, "send_s": p.get("send_s", 0), "eyes_sent": sum(1 for s in sent if s[1] == fwd.ACK_TEXT),
                        "replies_sent": sum(1 for s in sent if s[1] != fwd.ACK_TEXT), "end_to_end_s": stages.get("bb-send-end")})


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="webhook-on scenarios only")
    args = ap.parse_args(argv)
    plan = [dict(variant="after", text="status", webhook=True, phase=1.0, limit=40, warm=True)]  # cold start (imports, first sqlite use): not recorded
    for variant in ("before", "after"):
        for text in ("status", "hours"):
            for phase in (2.0, 2.35, 2.7):  # three phases against the worker's 1 s tick
                plan.append(dict(variant=variant, text=text, webhook=True, phase=phase, limit=40))
        if not args.quick:  # the webhook never fires: only the catch-up poll finds the message (poll runs at start, then every N s)
            for phase in ((14.0, 44.0) if variant == "before" else (5.0, 11.0)):
                plan.append(dict(variant=variant, text="status", webhook=False, phase=phase, limit=phase + 90))
    for send_s in (0.5, 1.5):  # attempt versus confirmed send: the 👀 send itself takes this long (BlueBubbles' real time is unmeasured)
        plan.append(dict(variant="after", text="status", webhook=True, phase=2.0, limit=40, send_s=send_s))
    for n, p in enumerate(plan):
        p["name"] = f"{p['variant']}-{p['text']}-{'hook' if p['webhook'] else 'poll'}{p['phase']:g}-{n}"
        Bench.params = p
        result = unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0).run(Bench())
        if not result.wasSuccessful():
            print(json.dumps({"failed": p["name"], "errors": [str(e[1])[-400:] for e in result.errors + result.failures]}), file=sys.stderr)
            return 1
    print(json.dumps(RESULTS, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())

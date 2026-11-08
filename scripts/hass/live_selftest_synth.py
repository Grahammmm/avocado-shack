#!/usr/bin/env python3
"""HASS-LIVE-AUDIT-1: the synthetic half of scripts/hass/live_selftest.sh.

    python3 -B scripts/hass/live_selftest_synth.py [-v]

Drives the code of THIS checkout end to end with synthetic data only: the real Mac forwarder classes
(mac/hass_forwarder.py Spool + Forwarder, with a recording stand-in for BlueBubbles) post sealed envelopes over HTTP
to a real hass/host.py Server on 127.0.0.1 (an OS-assigned port), a real host Worker drains the inbox through the
Conversation and queues replies in the relay, and the forwarder pulls and acknowledges them over HTTP.
Everything lives in fresh temp dirs (a throwaway writer repo, state dir, host dir, spool dir and a throwaway key); no
live state, host file, key, model, BlueBubbles or network beyond loopback is touched, and nothing is sent anywhere.
The interpreter is the FixtureInterpreter (a fixed mapping); the live model round trip is a separate step of the
shell script (hass/interpreter_eval.py --live on synthetic cases).

Scenarios (one test each): forwarder -> receiver -> draft -> reply; status; reply-delivery recovery (a failed send
is retried once, and a lost ack never sends twice); stranger sender ignored (owner chat and other chat); cancelled
code does nothing; expired code does nothing. Exit 0 all passed, 1 a failure.
"""
import json, shutil, sys, tempfile, threading, unittest  # noqa: E401
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from hass import bridge, host, receiver, relay  # noqa: E402
from hass.tests.test_bridge import OWNER_CHAT  # noqa: E402
from hass.tests.test_conversation import T0  # noqa: E402
from hass.tests.test_host import KEY_HEX, HostCase  # noqa: E402
from hass.tests.test_receiver import NOW  # noqa: E402
from mac import hass_forwarder as fwd  # noqa: E402

KEY = bytes.fromhex(KEY_HEX)
STRANGER = "stranger@example.invalid"


class Phone:
    """Stands in for BlueBubbles on the Mac: records what would have been sent; `fail` makes the next sends fail."""
    def __init__(self):
        self.sent, self.fail = [], 0

    def send(self, chat, text, attachments=()):
        if self.fail:
            self.fail -= 1
            raise bridge.BridgeError("transport-error")
        self.sent.append((chat, text))

    def send_png(self, chat, data, name):
        self.sent.append((chat, f"<png {name}>"))


class LiveSelftest(HostCase):
    def setUp(self):
        super().setUp()
        self.phone = Phone()
        self.spool_dir = Path(tempfile.mkdtemp(prefix="hass-selftest-spool-"))
        self.spool_dir.chmod(0o700)
        self.addCleanup(lambda: shutil.rmtree(self.spool_dir, ignore_errors=True))
        self.keyfile = self.write(self.hostdir / "key", (KEY_HEX + "\n").encode())
        cfg = host.load_host(self.host_json(listen="127.0.0.1:0"), allow_port_zero=True)
        self.srv = host.Server(cfg, KEY, receiver.Receiver(state=self.inbox, settings=None), self.store, self.clock)
        self.srv.timeout = 0.05
        self.addCleanup(self.srv.server_close)
        self.mac_cfg = {"ownerChat": OWNER_CHAT, "receiverUrl": f"http://127.0.0.1:{self.srv.server_port}", "bbPort": 1,
                        "bbPasswordFile": "/nonexistent", "secretFile": str(self.keyfile), "spoolDir": str(self.spool_dir)}
        fwd.Spool(str(self.spool_dir), NOW - 60).db.close()  # the Mac's start point: one minute before the first message
        self.guid = 0

    # -- the Mac side, run in its own thread while this thread serves the host's requests ------------------------
    def mac(self, step, *args):
        box = {}

        def go():
            spool = fwd.Spool(str(self.spool_dir), self.now.timestamp())
            try:
                f = fwd.Forwarder(self.mac_cfg, spool, clock=lambda: self.now.timestamp(), sender=self.phone, attach=self.phone)
                box["out"] = getattr(f, step)(*args) if step != "accept" else spool.accept(*args)
            except Exception as exc:  # noqa: BLE001 - reported to the scenario, which decides
                box["error"] = type(exc).__name__
            finally:
                spool.db.close()
        thread = threading.Thread(target=go)
        thread.start()
        while thread.is_alive(): self.srv.handle_request()
        thread.join()
        return box

    def spool_counts(self):
        spool = fwd.Spool(str(self.spool_dir), self.now.timestamp())
        try: return spool.status()
        finally: spool.db.close()

    def at(self, seconds):
        self.now = T0 + timedelta(seconds=seconds)

    def owner_texts(self, text, sender="owner@example.invalid", chat=OWNER_CHAT):
        """A synthetic BlueBubbles webhook event reaches the Mac spool, then the forwarder posts it to the host."""
        self.guid += 1
        ev = self.event_from("new-message", guid=f"FAKE-SELFTEST-{self.guid:04d}", text=text,
                             dateCreated=int(self.now.timestamp()) * 1000, handle={"address": sender},
                             chats=[{"guid": chat}])
        self.mac("accept", ev, OWNER_CHAT, self.now.timestamp())
        return self.mac("deliver")

    def texts(self):
        return [t for _, t in self.phone.sent]

    # -- scenarios -----------------------------------------------------------------------------------------------
    def test_1_forwarder_to_receiver_draft_and_reply(self):
        work = self.worker(False)
        self.assertEqual(self.owner_texts("hours"), {"out": None})
        self.assertEqual(self.spool_counts()["done"], 1)  # the host answered `queued`
        work.cycle()
        [draft] = self.drafts()
        self.assertEqual(draft["state"], "proposed")
        self.assertEqual(self.mac("pull"), {"out": None})
        [reply] = self.texts()
        self.assertTrue(reply.startswith("Here's the change I'd make:\n"), reply)
        self.assertIn("Avocado Shack, the opening hours:", reply)
        self.assertTrue(reply.endswith("Reply yes to save it, or no to cancel. If something's wrong, tell me what to fix."), reply)
        self.assertEqual(self.store.status(), {"waiting": 0, "total": 1})  # pulled and acknowledged

    def test_2_status_gets_one_reply_and_no_draft(self):
        work = self.worker(False)
        self.owner_texts("status")
        work.cycle()
        self.mac("pull")
        self.assertEqual((len(self.texts()), self.drafts()), (1, []))

    def test_3_reply_delivery_recovers_and_never_sends_twice(self):
        work = self.worker(False)
        self.owner_texts("status")
        work.cycle()
        self.phone.fail = 1  # BlueBubbles down for the first try
        self.assertEqual(self.mac("pull"), {"error": "BridgeError"})
        self.assertEqual((self.texts(), self.store.status()["waiting"]), ([], 1))  # not acknowledged: still waiting
        self.at(30)
        self.mac("pull")
        self.assertEqual(self.texts(), [])  # handed out under 60 s ago: not handed again yet
        self.at(61)
        self.mac("pull")
        self.assertEqual((len(self.texts()), self.store.status()["waiting"]), (1, 0))
        # a lost ack: the host hands the same reply again; the Mac's sent table stops a second send
        self.store.db.execute("UPDATE relay SET acked_at = NULL, handed_at = NULL")
        self.at(130)
        self.mac("pull")
        self.assertEqual((len(self.texts()), self.store.status()["waiting"]), (1, 0))

    def test_4_stranger_is_ignored(self):
        work = self.worker(True)
        self.owner_texts("hours", sender=STRANGER)  # a stranger inside the owner chat: forwarded, ignored by the host
        self.owner_texts("hours", sender=STRANGER, chat=f"iMessage;-;{STRANGER}")  # another chat: dropped on the Mac
        work.cycle()
        self.mac("pull")
        counts = self.spool_counts()
        self.assertEqual((self.drafts(), self.relay_rows(), self.texts()), ([], [], []))
        self.assertEqual((counts["done"], counts["dropped_events"]), (1, 1))
        self.assertEqual((self.editor.applies, self.commits()), (0, 0))

    def test_5_cancelled_code_does_nothing(self):
        work = self.worker(True)  # private mode: a valid yes WOULD apply, so "nothing" is meaningful
        self.owner_texts("hours")
        work.cycle()
        code = self.drafts()[0]["code"]
        self.at(5)
        self.owner_texts(f"no {code}")
        work.cycle()
        self.at(10)
        self.owner_texts(f"yes {code}")
        work.cycle()
        self.mac("pull")
        self.assertEqual(self.drafts()[0]["state"], "rejected")
        self.assertEqual((self.editor.applies, self.commits()), (0, 0))
        self.assertEqual(len(self.texts()), 3)  # draft, cancelled, a reply to the late yes; each once

    def test_6_expired_code_does_nothing(self):
        work = self.worker(True)
        self.owner_texts("hours")
        work.cycle()
        code = self.drafts()[0]["code"]
        self.at(601)  # approvalTtlSeconds is 600 in these settings
        self.owner_texts(f"yes {code}")
        work.cycle()
        self.mac("pull")
        self.assertEqual(self.drafts()[0]["state"], "expired")
        self.assertEqual((self.editor.applies, self.commits()), (0, 0))
        self.assertEqual(len(self.texts()), 2)  # proposal, then the reply to the late yes
        self.assertEqual(self.texts()[-1], "That change timed out today at 9:10 am, so nothing changed. Tell me again if you still want it.")


if __name__ == "__main__":
    result = unittest.main(argv=[sys.argv[0], *sys.argv[1:]], exit=False).result
    print(json.dumps({"synthetic": "pass" if result.wasSuccessful() else "fail", "ran": result.testsRun,
                      "failed": len(result.failures) + len(result.errors)}, sort_keys=True))
    sys.exit(0 if result.wasSuccessful() else 1)

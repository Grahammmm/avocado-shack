"""RF0240-10 tests: an authenticated envelope whose body received_at the inbox cannot use (empty, junk, date-only, naive,
or outside representable UTC) is rejected as `shape` instead of raising from intake; the nonce rolls back, nothing is
drained, and authentication, replay and setup/storage errors keep their existing precedence. Synthetic fixtures only.
Run: python3 -B -m unittest hass.tests.test_receiver_received_time"""

import copy, json, sqlite3, unittest  # noqa: E401
from dataclasses import replace

from hass import bridge, inbox as inbox_mod, receiver
from hass.tests import test_receiver as base
from hass.tests.test_bridge import event
from hass.tests.test_receiver_atomic_intake import deny_insert_into

SHAPE = receiver._result("rejected", receiver.REJECTED["shape"])
INVALID = ["", "garbage", "2026-11-11", "2026-11-11T12:00:00"]
UNREPRESENTABLE = ["0001-01-01T00:00:00+23:00", "9999-12-31T23:59:59-23:00"]
FORMS = {"dict": lambda e: e, "str": json.dumps, "bytes": lambda e: json.dumps(e).encode(),
         "bytearray": lambda e: bytearray(json.dumps(e).encode())}


class ReceivedTimeTests(base.ReceiverTestCase):
    def envelope(self, received_at=None, nonce=None, secret=base.SECRET, now=base.NOW, **body):
        msg = bridge.normalize(event("new-message"))
        msg = replace(msg, **({"received_at": received_at} if received_at is not None else {}), **body)
        if nonce is None:
            self.nonce += 1
            nonce = f"{self.nonce:032x}"
        return bridge.seal(msg, secret, nonce=nonce, now=now)

    def durable(self):
        box = inbox_mod.Inbox(str(self.repo.state), None, clock=lambda: self.now)
        try:
            return ([tuple(r) for r in box.db.execute("SELECT nonce FROM nonces")],
                    [tuple(r) for r in box.db.execute("SELECT provider_id, state FROM inbound")])
        finally:
            box.close()

    def assert_untouched(self):
        self.assertFalse(self.inbox.db.in_transaction)
        self.assertEqual(self.durable(), ([], []))
        self.assertEqual((self.drafts(), self.editor.applies, self.reply.calls), ([], 0, []))

    def test_signed_invalid_received_time_is_shape_and_rolls_back(self):
        stages = []
        self.rx.stage = lambda *a: stages.append(a)
        for value in INVALID:
            for call in (self.rx.accept, self.rx.receive):
                with self.subTest(value=value, call=call.__name__):
                    self.assertEqual(call(json.dumps(self.envelope(value)), secret=base.SECRET, now=base.NOW), SHAPE)
                    self.assert_untouched()
        self.assertEqual(stages, [])

    def test_signed_utc_unrepresentable_offsets_are_shape(self):
        for value in UNREPRESENTABLE:
            for form, encode in FORMS.items():
                for call in (self.rx.accept, self.rx.receive):
                    with self.subTest(value=value, form=form, call=call.__name__):
                        out = call(encode(self.envelope(value)), secret=base.SECRET, now=base.NOW)
                        self.assertEqual(out, SHAPE)
                        self.assert_untouched()

    def test_corrected_message_can_reuse_rejected_nonce(self):
        bad = self.envelope("2026-11-11T12:00:00", nonce="ab" * 16)
        before = copy.deepcopy(bad)
        self.assertEqual(self.rx.accept(bad, secret=base.SECRET, now=base.NOW), SHAPE)
        self.assertEqual(bad, before)  # the sender's message is not repaired or replaced
        good = json.dumps(self.envelope(nonce="ab" * 16))
        self.assertEqual(self.rx.accept(good, secret=base.SECRET, now=base.NOW)["result"], "queued")
        again = self.rx.accept(good, secret=base.SECRET, now=base.NOW)
        self.assertEqual((again["result"], again["reason"]), ("duplicate", "this exact envelope was already received"))
        nonces, rows = self.durable()
        self.assertEqual((len(nonces), [r[1] for r in rows]), (1, ["pending"]))

    def test_timestamp_refusal_preserves_authentication_precedence(self):
        bad = "garbage"
        wrong_mac = self.envelope(bad, secret=b"another-throwaway-secret-0123456789abc")
        stale = self.envelope(bad, now=base.NOW - 3600)
        typed = self.envelope(bad)
        typed["body"]["attachments"] = "1"
        cases = [(wrong_mac, "mac"), (stale, "stale"), (typed, "shape")]
        for env, code in cases:
            with self.subTest(code=code):
                out = self.rx.accept(env, secret=base.SECRET, now=base.NOW)
                self.assertEqual(out, receiver._result("rejected", receiver.REJECTED[code]))
                self.assert_untouched()
        good = self.envelope()
        self.assertEqual(self.rx.accept(good, secret=base.SECRET, now=base.NOW)["result"], "queued")
        replayed = dict(self.envelope(bad, nonce=good["nonce"]))
        self.assertEqual(self.rx.accept(replayed, secret=base.SECRET, now=base.NOW)["result"], "duplicate")

    def test_storage_setup_and_clock_errors_still_propagate(self):
        with self.assertRaises(ValueError): self.rx.accept(self.envelope(), secret=b"short", now=base.NOW)
        original = self.inbox.enqueue
        self.inbox.enqueue = lambda msg: (_ for _ in ()).throw(ValueError("deliberate"))
        with self.assertRaisesRegex(ValueError, "deliberate"): self.rx.accept(self.envelope(), secret=base.SECRET, now=base.NOW)
        self.inbox.enqueue = original
        self.inbox.db.set_authorizer(deny_insert_into("inbound"))
        with self.assertRaises(sqlite3.DatabaseError): self.rx.accept(self.envelope(), secret=base.SECRET, now=base.NOW)
        self.inbox.db.set_authorizer(None)
        self.assert_untouched()
        self.inbox.db.execute("BEGIN")
        with self.assertRaises(RuntimeError): self.rx.accept(self.envelope("garbage"), secret=base.SECRET, now=base.NOW)
        self.inbox.db.execute("ROLLBACK")

    def test_valid_offsets_fractional_cutoff_and_history_unchanged(self):
        t0 = base.T0  # the recorded start point
        cases = [(t0.isoformat(), "queued"), (t0.astimezone(inbox_mod.timezone.utc).isoformat(), "duplicate"),
                 ("0001-01-01T00:00:00+00:00", "history"), ("9999-12-31T23:59:59.999999+00:00", "queued"),
                 ((t0 - inbox_mod.timedelta(microseconds=1)).isoformat(timespec="microseconds"), "history")]
        for n, (value, want) in enumerate(cases):
            pid = "same" if n < 2 else f"id-{n}"
            with self.subTest(value=value):
                out = self.rx.accept(self.envelope(value, provider_id=pid), secret=base.SECRET, now=base.NOW)
                self.assertEqual(out["result"], want)
        order = [r[0] for r in self.inbox.db.execute("SELECT provider_id FROM inbound ORDER BY received_at")]
        self.assertEqual(order, ["id-2", "id-4", "same", "id-3"])
        out = self.rx.receive(json.dumps(self.envelope(provider_id="fresh")), secret=base.SECRET, now=base.NOW)
        self.assertNotEqual(out["result"], "rejected")


if __name__ == "__main__":
    unittest.main()

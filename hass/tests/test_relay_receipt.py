"""Frozen card receipt contracts across the fixture host and Mac."""
import json
from datetime import timedelta

from hass import host, relay
from hass.tests import test_attach as fixture
from hass.tests.test_forwarder import KEY

DIGEST = relay.sha256(fixture.PNG).hexdigest()
PROMPT = "Post this? Reply yes a1b2-1, or tell me what to change."


class ReceiptTests(fixture.AttachCase):
    def setUp(self):
        super().setUp()
        self.addCleanup(self.store.db.close)
        worker = host.Worker(self.conv, self.srv.receiver, self.store, self.repo.wt,
                             lambda: self.interp, self.clock, self.shots)
        self.sender = worker.sender
        self.receipt_for = worker.receipt_for

    def queue_card(self, path, digest=DIGEST):
        self.conv.outbox.add(fixture.OWNER_CHAT, PROMPT, [path], ids_ok=True)
        row = self.conv.outbox.unsent()[-1]
        rid = self.sender.send_card(row['id'], row['chat'], row['text'], path, digest)
        self.assertEqual(self.receipt_for(row['id']), dict(state='pending', png_sha256=digest,
                                                          provider_guid=None, confirmed_at=None))
        self.assertIsNone(row['sent_at'])
        return row['id'], rid

    def test_probe_only_exact_sent_bytes_confirm_and_restart_preserves_binding(self):
        # A Mac pickup/ACK of a dropped PNG must not approve a text-only prompt.
        for mode in ('sent', 'gone', 'refused', 'replaced', 'provider-failed'):
            with self.subTest(mode=mode):
                path = (str(self.shots / 'missing.png') if mode == 'refused'
                        else self.shot(mode + '.png', fixture.PNG2 if mode == 'replaced' else fixture.PNG))
                oid, rid = self.queue_card(path)
                if mode == 'sent':
                    self.store.db.close()
                    self.srv.store = self.sender.store = restarted = relay.RelayStore(self.hostdir)
                    self.addCleanup(restarted.db.close)
                    self.assertEqual(self.sender.send_card(oid, fixture.OWNER_CHAT, PROMPT, path, DIGEST), rid)
                    with self.assertRaises(relay.RelayRefused):
                        self.sender.send_card(oid, fixture.OWNER_CHAT, PROMPT, path, '0' * 64)
                    self.assertEqual(self.receipt_for(oid)['state'], 'pending')
                if mode == 'gone':
                    self.srv.store.db.execute('UPDATE picture SET data=NULL WHERE relay_id=?', (rid,))
                self.attach_fail = mode == 'provider-failed'
                self.events.clear()
                self.now += timedelta(seconds=1, microseconds=5)
                self.f.pull()
                if self.attach_fail:
                    for _ in range(2):
                        self.assertEqual(self.receipt_for(oid)['state'], 'pending')
                        self.advance(61)
                        self.f.pull()
                sent = mode == 'sent'
                self.assertEqual(self.receipt_for(oid), dict(state='confirmed' if sent else 'failed', png_sha256=DIGEST,
                                                            confirmed_at=self.now.isoformat() if sent else None, provider_guid=None))
                self.assertEqual(self.srv.store.status()['waiting'], 0)
                self.assertEqual(self.texts(), [PROMPT if sent else fixture.fwd.CARD_GAVE_UP])
                if sent:
                    self.assertEqual([e[0] for e in self.events], ['png', 'text'])
                    self.assertEqual(self.multipart(self.pngs()[0])['attachment'][1], fixture.PNG)
                else:
                    self.assertEqual(len(self.pngs()), 3 if self.attach_fail else 0)

    def test_only_authenticated_handed_matching_receipts_confirm_and_legacy_ack_is_final(self):
        # Neither an envelope with invalid auth nor an ambiguous ACK can bind a card to a provider GUID.
        for mode in ('legacy', 'wrong-digest', 'match'):
            with self.subTest(mode=mode):
                oid, rid = self.queue_card(self.shot())
                good = {'op': 'ack', 'ids': [rid], 'receipt': {'outcome': 'sent', 'png_sha256': DIGEST,
                                                             'provider_guid': 'fixture-message-guid'}}
                nonce = lambda n: f'{rid * 100 + n:032x}'  # noqa: E731
                env = relay.seal_control(good, KEY, nonce=nonce(1), now=self.now)
                env['mac'] = '0' * 64
                self.assertEqual(self.post(self.srv, '/v1/relay', json.dumps(env).encode())[0], 400)
                self.control(good, nonce(2))  # valid signature, but not yet handed
                self.assertEqual(self.receipt_for(oid)['state'], 'pending')
                _, old = self.control({'op': 'pull', 'max': 5}, nonce(3))
                self.assertEqual(old['items'], [])  # old Mac never receives the approval prompt
                _, new = self.control({'op': 'pull', 'max': 5, 'card_receipts': True}, nonce(4))
                self.assertEqual([i['id'] for i in new['items']], [rid])
                first = ({'op': 'ack', 'ids': [rid]} if mode == 'legacy' else good if mode == 'match'
                         else {**good, 'receipt': {**good['receipt'], 'png_sha256': '0' * 64}})
                self.assertEqual(self.control(first, nonce(5)), (200, {'op': 'acked', 'ids': [rid]}))
                expected = dict(state={'legacy': 'unconfirmed', 'wrong-digest': 'failed', 'match': 'confirmed'}[mode],
                                png_sha256=DIGEST, provider_guid='fixture-message-guid' if mode == 'match' else None,
                                confirmed_at=self.now.isoformat(timespec='microseconds') if mode == 'match' else None)
                self.advance(1)
                self.control(good, nonce(6))  # retries never upgrade failed/legacy or re-stamp a confirmed send
                self.assertEqual(self.receipt_for(oid), expected)

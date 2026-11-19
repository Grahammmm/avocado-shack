"""Mac-side contracts for the provider result and durable outbound ACK retry."""
import io
import json
from unittest import mock

from hass import bridge, relay
from hass.tests import test_attach as fixture


class Response(io.BytesIO):
    status = 200


class ForwarderReceiptTests(fixture.AttachCase):
    def card_sender(self):
        return fixture.fwd.CardAttachmentSender('http://127.0.0.1:1234', self.cfg['bbPasswordFile'], fixture.OWNER_CHAT)

    def test_lost_ack_and_mac_restart_resend_receipt_without_resending_png_or_prompt(self):
        # A transient ACK outage must not replace the original successful provider result or upload twice.
        self.addCleanup(self.store.db.close)
        sha = relay.sha256(fixture.PNG).hexdigest()
        rid = self.relay_sender.send_card(42, fixture.OWNER_CHAT, 'card ready', self.shot(), sha)
        self.f.card_attach = self.card_sender()
        post = self.f.post

        def lose_ack(path, env, big=False):
            if env['body']['op'] == 'ack':
                self.assertEqual(env['body'], {'op': 'ack', 'ids': [rid], 'receipt': {
                    'outcome': 'sent', 'png_sha256': sha, 'provider_guid': 'fixture-msg-guid'}})
                raise bridge.BridgeError('transport-error')
            return post(path, env, big)

        response = Response(b'{"status":200,"data":{"guid":"fixture-msg-guid"}}')
        with mock.patch.object(bridge._OPENER, 'open', return_value=response) as provider:
            with mock.patch.object(self.f, 'post', lose_ack), self.assertRaises(bridge.BridgeError):
                self.f.pull()
            self.assertEqual(self.relay_sender.receipt_for(42)['state'], 'pending')
            self.spool.db.close()
            self.start()
            self.f.card_attach = self.card_sender()
            self.advance(61)
            self.f.pull()
            self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.texts(), ['card ready'])
        self.assertEqual(self.relay_sender.receipt_for(42), dict(state='confirmed', png_sha256=sha,
                                                                 provider_guid='fixture-msg-guid', confirmed_at=self.now.isoformat(timespec='microseconds')))

    def test_provider_guid_is_optional_but_body_failure_is_not_success(self):
        # A provider-side refusal can arrive in HTTP 200; a no-GUID success cannot inherit a previous GUID.
        sender = self.card_sender()
        responses = [Response(json.dumps(body).encode()) for body in (
            {'status': 200, 'data': {'guid': 'fixture-id'}}, {'status': 200},
            {'status': 500, 'data': {'guid': 'not-a-success'}})]
        with mock.patch.object(bridge._OPENER, 'open', side_effect=responses):
            args = (fixture.OWNER_CHAT, fixture.PNG, 'hass-1-0.png')
            self.assertEqual(sender.send_png(*args), 'fixture-id')
            self.assertIsNone(sender.send_png(*args))
            with self.assertRaises(bridge.BridgeError): sender.send_png(*args)

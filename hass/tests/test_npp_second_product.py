"""Observe the NPP photo route with real job, plan, outbox and approval handling."""
from concurrent.futures import Future
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zlib

from hass import conversation
from hass.npp import stages
from hass.npp.job import Card, Jobs

OWNER = 'owner@example.invalid'
CHAT = 'fixture-chat'
PRICE_QUESTION = "What's the selling price, and is that each or per lb?"
EDIT_QUESTION = "I didn't catch that change. What should it say?"
NOT_READY = "The card isn't ready to approve yet; use the code on it when it arrives."


def png(rgb):
    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data))

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0' + bytes(rgb))) + chunk(b'IEND', b''))


JAM, SOAP, JAM_AGAIN = (png(rgb) for rgb in ((90, 10, 40), (220, 210, 180), (94, 15, 45)))
NAMES = {JAM: 'Fixture Jam', SOAP: 'Fixture Soap', JAM_AGAIN: 'Fixture Jam'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SecondProductTests(unittest.TestCase):
    jobs: Jobs

    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory())).resolve()
        media = root / 'media'
        media.mkdir(mode=0o700)
        (root / 'config.json').write_text(json.dumps({'settings': {
            'ownerSenders': [OWNER], 'ownerChat': CHAT, 'npp': True,
            'approvalTtlSeconds': 3600, 'mediaRoot': str(media),
        }}), encoding='utf-8')
        self.now = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self.serial = 0
        self.steps, self.replies, self.receipts, self.drafts, self.reads = [], [], {}, {}, []
        self.editor = SimpleNamespace(show=lambda key: {'draft': self.drafts[key]}, apply=Mock(side_effect=self.deny))
        self.conv = conversation.Conversation(
            root, self.editor, SimpleNamespace(interpret=self.deny), lambda: self.now,
            photos=self, npp_stages=object(), npp_executor=self, npp_receipt_for=self.receipts.get,
        )
        self.addCleanup(self.conv.db.close)
        jobs = self.conv.npp
        assert jobs is not None
        self.jobs = jobs
        port = stages.ProductionStages(self.conv, conversation.npp_package.assets())
        self.enterContext(patch.object(port, 'catalog', return_value=SimpleNamespace(products=[], makers={})))
        self.enterContext(patch.object(port.identifier, 'read', side_effect=self.identify))
        port.mapper = self.deny
        self.enterContext(patch.object(stages.research_hermes, 'run', side_effect=self.deny))
        port.render_card = self.render
        port.persist = self.persist
        self.jobs.stages = port

    @staticmethod
    def deny(*args, **kwargs):
        raise AssertionError('unexpected fixture boundary call')

    def identify(self, photos):
        photos = tuple(photos)
        self.reads.append(photos)
        return SimpleNamespace(evidence={
            'item': NAMES[photos[0]], 'is_product': True, 'kind': 'food' if photos[0] != SOAP else 'non-food',
            'category_guess': 'pantry' if photos[0] != SOAP else 'general',
            'confidence': {'item': 1, 'category': 1}, 'has_person_or_screen': False,
        })

    def render(self, work, listing):
        # Only the picture/editor output is scripted; start/edit decisions and versioning are real.
        sha = work.request['attachments'][0]
        path = 'fixture.png'
        draft = {'change_id': f'fixture-{self.serial}', 'draft_hash': digest(json.dumps(listing).encode()),
                 'base': 'fixture-base', 'assets': {path: 'sha256:' + sha}, 'ops': [], 'records': []}
        return Card(draft, png((1, 2, self.serial)), 'raw', path, sha, candidate=True)

    def persist(self, draft):
        self.drafts[draft['change_id']] = draft
        return {'result': 'ok'}

    def submit(self, fn, *args):
        future = Future()
        self.steps.append((future, fn, args))
        return future

    def step(self):
        future, fn, args = self.steps.pop(0)
        future.set_result(fn(*args))
        return future.result()

    def send(self, chat, text, attachments):
        self.assertEqual((chat, attachments), (CHAT, []))
        self.replies.append(text)

    def send_card(self, row, chat, text, path, sha):
        self.assertEqual(chat, CHAT)
        self.assertEqual(digest(Path(path).read_bytes()), sha)
        self.replies.append(text)
        self.receipts[row] = dict(state='confirmed', png_sha256=sha, confirmed_at=self.now.isoformat(),
                                  provider_guid=f'fixture-card-{row}')

    def fetch(self, _pid, count):
        self.assertEqual(count, len(self.photos))
        return list(self.photos)

    def say(self, text='', *photos):
        self.now += timedelta(seconds=1)
        self.serial += 1
        self.photos = photos
        return self.conv.handle(conversation.Inbound(
            f'fixture-turn-{self.serial}', CHAT, OWNER, text, received_at=self.now.isoformat(), attachments=len(photos),
        ), apply=False, forwarded_at=self.now)

    def flush(self):
        self.conv.flush(self)

    def settle(self):
        for _ in range(6):
            self.flush()
            if self.steps:
                self.step()
        self.assertFalse(self.steps or self.jobs.running)

    def job(self):
        [job] = self.conv.db.execute('SELECT * FROM npp_jobs').fetchall()
        return job

    def version(self, n):
        return self.jobs.version(self.job()['job_id'], n)

    def ready(self, n):
        return f"Post this? Reply yes {self.job()['job_id']}-{n}, or tell me what to change."

    def yes(self, n):
        return self.say(f"yes {self.job()['job_id']}-{n}")

    def assert_reused(self, first, state, *photos):
        job = self.job()
        self.assertEqual((job['job_id'], job['open_request_id'], job['state'], job['closed_at']),
                         (first['job_id'], first['open_request_id'], state, None))
        self.assertEqual(job['photo_sha'], digest(photos[0]))
        request = self.jobs.request(job, self.now)
        assert request is not None
        self.assertEqual(request['attachments'], [digest(photo) for photo in photos])

    def test_c1_while_asking(self):
        # A second photo replaces the first in the open intake; it is neither ignored nor queued separately.
        self.assertEqual(self.say('', JAM), 'npp-working')
        self.settle()
        first = self.job()
        self.assertEqual((first['state'], self.replies), ('asking', [PRICE_QUESTION]))
        self.assertEqual(self.say('', SOAP), 'npp-working')
        self.assert_reused(first, 'working', SOAP)
        self.assertEqual(self.replies, [PRICE_QUESTION])
        self.settle()
        self.assert_reused(first, 'asking', SOAP)
        self.assertEqual(self.replies, [PRICE_QUESTION, PRICE_QUESTION])
        self.assertEqual(self.say('sell $8 each'), 'npp-working')
        self.settle()
        self.assert_reused(first, 'card_out', SOAP)
        self.assertEqual(self.reads, [(JAM,), (SOAP,), (SOAP,)])
        self.assertEqual(json.loads(self.version(1)['listing_json'])['name'], NAMES[SOAP])
        self.assertEqual(self.replies, [PRICE_QUESTION, PRICE_QUESTION, self.ready(1)])

    def test_c2_while_card_out(self):
        # A photo without a caption revokes the old approval even if no replacement card is built.
        self.say('sell $8 each', JAM)
        self.settle()
        first = self.job()
        self.assertEqual((first['state'], self.version(1)['state']), ('card_out', 'delivered'))
        self.assertEqual(self.yes(1), 'approval-held')  # eligible before the photo, but never applied
        self.flush()
        self.replies.clear()
        self.assertEqual(self.say('', SOAP), 'npp-working')
        self.assert_reused(first, 'editing', SOAP)
        self.assertEqual(self.version(1)['state'], 'superseded')
        self.assertEqual(self.replies, [])
        self.settle()
        self.assert_reused(first, 'asking', SOAP)
        self.assertIsNone(self.version(2))
        self.assertEqual(self.reads, [(JAM,)])  # an edit question, not a fresh identification
        self.assertEqual(self.yes(1), 'no-target')
        self.flush()
        self.assertEqual(self.replies, [EDIT_QUESTION, NOT_READY])
        self.assertEqual(self.conv.db.execute('SELECT count(*) FROM npp_approvals').fetchone()[0], 0)
        self.editor.apply.assert_not_called()

    def test_c3_while_building(self):
        # A photo during an edit render invalidates its ticket, even if the old render completes successfully.
        self.say('sell $8 each', JAM)
        self.settle()
        first = self.job()
        self.assertEqual(self.say('make it $9'), 'npp-working')
        self.flush()
        self.step()  # plan the edit
        self.flush()  # freeze version two
        self.flush()  # schedule its render but do not finish it
        self.assertEqual((self.job()['state'], self.version(2)['state']), ('editing', 'building'))
        self.assertEqual(self.say('', SOAP), 'npp-working')
        self.assert_reused(first, 'editing', SOAP)
        self.assertEqual(self.version(2)['state'], 'superseded')
        self.assertIsInstance(self.step(), Card)
        self.settle()
        self.assert_reused(first, 'asking', SOAP)
        self.assertIsNone(self.version(2)['outbox_id'])
        self.assertIsNone(self.version(3))
        self.assertEqual(len(self.drafts), 1)
        self.assertEqual(self.replies, [self.ready(1), EDIT_QUESTION])

    def test_c4_same_product_again(self):
        # A retaken picture accompanying a valid edit can replace the image without opening another job.
        self.say('sell $8 each', JAM)
        self.settle()
        first = self.job()
        self.assertEqual(first['state'], 'card_out')
        self.assertEqual(self.say('', JAM_AGAIN), 'npp-working')
        self.assert_reused(first, 'editing', JAM_AGAIN)
        self.assertEqual(self.version(1)['state'], 'superseded')
        self.settle()
        self.assert_reused(first, 'asking', JAM_AGAIN)
        self.assertIsNone(self.version(2))
        self.assertEqual(self.replies, [self.ready(1), EDIT_QUESTION])
        self.assertEqual(self.say('sell $9 each', JAM_AGAIN), 'npp-working')
        self.settle()
        self.assert_reused(first, 'card_out', JAM_AGAIN)
        new = self.version(2)
        self.assertEqual((new['parent_n'], new['state'], new['image_sha256']), (1, 'delivered', digest(JAM_AGAIN)))
        self.assertEqual(json.loads(new['listing_json'])['name'], NAMES[JAM])
        self.assertEqual(self.yes(1), 'no-target')
        self.flush()
        self.assertEqual(self.yes(2), 'approval-held')
        self.assertEqual(self.replies, [self.ready(1), EDIT_QUESTION, self.ready(2), 'That card was replaced.'])
        self.editor.apply.assert_not_called()

    def test_c5_two_products_one_message(self):
        # A multi-photo message is one intake, not two separate cards or a second-photo takeover.
        self.assertEqual(self.say('sell $8 each', JAM, SOAP), 'npp-working')
        first = self.job()
        self.assert_reused(first, 'working', JAM, SOAP)
        self.settle()
        self.assert_reused(first, 'card_out', JAM, SOAP)
        self.assertEqual(self.reads, [(JAM, SOAP)])
        card = self.version(1)
        self.assertEqual(json.loads(card['listing_json'])['photo'], digest(JAM))
        self.assertEqual((card['state'], card['image_sha256']), ('delivered', digest(JAM)))
        self.assertIsNone(self.version(2))
        self.assertEqual(self.replies, [self.ready(1)])

"""G's Gorilla label/price conversation, real draft/apply + private real-site card capture."""
import hashlib
import json
import shutil

import unittest
from pathlib import Path
from unittest import mock

from hass import live_policy, media, photo_polish, preview, product_claims
from hass.content_model import REPO_ROOT
from hass.ops import photos, Refused
from hass.tests import test_item_add_dispatch as base
from hass.tests.test_intake_simple import DETAILS
from hass.tests.test_label_reader import reader, recorded


class PublishGate(unittest.TestCase):
    def chat(self, details=DETAILS, settings=None):
        chat = base.Chat([base.JAR], None, {"itemIntake": True, **(settings or {})})
        chat.base_commits = int(base.testkit._git(chat.kit.wt, 'rev-list', '--count', 'HEAD'))
        chat.conv.labels, _ = reader(recorded(details))
        chat.conv.settings['liveSite'] = {'url': 'https://example.invalid'}
        # Real release predicate, sandbox writer: never connect to a live site.
        chat.conv._live_reasons = live_policy.check
        self.addCleanup(chat.close)
        return chat

    def product(self, chat):
        draft = chat.conv.editor.show(chat.drafts()[0]['change_id'])['draft']
        return next(r['after'] for r in draft['records'] if r['collection'] == 'products'), draft

    def test_exact_glue_photo_then_price_label_allowed_and_one_yes_applies_exact_copy(self):
        chat = self.chat()
        chat.say('', base.JAR)
        disposition, said = chat.say('$2')
        self.assertEqual(disposition, 'proposed', said)
        product, draft = self.product(chat)
        self.assertEqual(live_policy.check(draft), [])
        self.assertEqual(product['labelSource']['source'], 'label')
        self.assertIn('Made in USA', product['description'])
        self.assertIn(product['description'], said[0])
        code = chat.live()['draft_code']
        self.assertIn('yes ' + code, said[0])
        self.assertNotIn("can't put this", said[0])
        chat.say('yes ' + code)
        self.assertEqual(chat.commits(), 1)
        saved = json.loads((chat.kit.wt / 'hass/content/products.json').read_text())['products'][-1]
        self.assertEqual(saved['description'], product['description'])
        self.assertEqual(saved['image'], product['image'])
        self.assertNotIn('labelSource', (chat.kit.wt / 'storefront-mockup/catalog-products.js').read_text())

    def test_food_organic_label_is_quoted_but_owner_health_phrase_dropped_only(self):
        chat = self.chat({'name': 'Jam', 'brand': 'Test kitchen', 'category': 'pantry',
                          'description': 'Raspberry jam in a jar.', 'printed_claims': ['Organic']})
        chat.say('sell for $2', base.JAR)
        code = chat.live()['draft_code']
        disposition, said = chat.say('add: cures cancer. Good on toast.')
        self.assertEqual(disposition, 'proposed', said)
        product, draft = self.product(chat)
        self.assertIn('Label says: “Organic”', product['description'])
        self.assertIn('Good on toast.', product['description'])
        self.assertNotIn('cures cancer', product['description'])
        self.assertIn('Dropped from the listing: cures cancer.', said[0])
        self.assertIn('yes ' + code, said[0])
        self.assertEqual(live_policy.check(draft), [])

    def test_nonfood_label_features_allowed_but_forged_or_bare_food_claims_not(self):
        evidence = {'source': 'label', 'photo': 'a' * 64, 'text': ['Made in USA', 'The strongest glue']}
        for category, allowed in [('flowers', True), ('pantry', False)]:
            product = {'category': category, 'labelSource': evidence}
            self.assertEqual(not product_claims.protected('Made in USA. The strongest glue.', product)[1], allowed)
        product = {'category': 'pantry', 'labelSource': evidence}
        self.assertFalse(product_claims.protected('Label says: “Made in USA”.', product)[1])
        self.assertTrue(product_claims.protected('Label says: “Organic”.', product)[1])
        self.assertTrue(product_claims.protected('Call 805-555-1234.', {'category': 'flowers', 'labelSource': evidence})[1])

    def test_forged_label_text_without_photo_read_is_refused_by_editor(self):
        chat = self.chat()
        chat.say('sell for $2', base.JAR)
        ops = json.loads(chat.drafts()[0]['ops_json'])
        ops[0]['args']['labelText'].append('Cures everything')
        result = chat.conv.editor.prepare(ops)
        self.assertEqual(result['result'], 'refused', result)
        self.assertEqual(chat.commits(), 0)

    def test_image_generation_failure_uses_exact_owner_web_photo_and_still_approves(self):
        chat = self.chat(settings={'houseRender': True, 'photo_polish': True})
        # Exercise real decision store + failed transport, not a synthetic success JPEG.
        remember = product_claims.remember
        def fail(root, sha, details):
            remember(root, sha, details)
            photo_polish.run(root, sha, transport=lambda *a: {'ok': False, 'code': 'auth'})
        with mock.patch.object(product_claims, 'remember', side_effect=fail), mock.patch.object(photos, '_verdict', return_value=Refused('style failed')):
            disposition, said = chat.say('sell for $2', base.JAR)
            self.assertEqual(disposition, 'proposed', said)
            product, draft = self.product(chat)
            sha = chat.live()['slots']['photo']
            rendered = chat.conv.editor.render_draft(draft['change_id'])
            wanted = Path(media.web_copy(chat.conv.settings['mediaRoot'], sha)['path']).read_bytes()
            key = 'storefront-mockup/' + product['image']
            self.assertEqual(rendered['assets'][key], wanted)
            self.assertIn('Picture: your photo (styled picture failed: sign-in unavailable)', said[0])
            chat.say('yes ' + chat.live()['draft_code'])
            self.assertEqual(chat.commits(), 1)
            self.assertEqual((chat.kit.wt / key).read_bytes(), wanted)

    def test_render_failure_attaches_photo_and_never_contradicts_policy_on_retry(self):
        chat = self.chat()
        chat.conv.previewer.capture = mock.Mock(return_value={'ok': False, 'png': None, 'error': "Cannot find module 'playwright'"})
        _, said = chat.say('sell for $2', base.JAR)
        self.assertIn("couldn't render the website card", said[0])
        self.assertTrue(chat.out.sent[-1]['attachments'])
        self.assertIn('yes ' + chat.live()['draft_code'], said[0])
        chat.conv._live_reasons = lambda draft: ['protected sentences: contact']
        chat.now += base.timedelta(seconds=31)
        chat.conv.retry_previews()
        chat.conv.flush(chat.out)
        self.assertIn("can't put this", chat.out.sent[-1]['text'])
        self.assertNotIn('yes ' + chat.live()['draft_code'], chat.out.sent[-1]['text'])
        self.assertEqual(chat.conv.db.execute('SELECT COUNT(*) FROM preview_retry').fetchone()[0], 0)

    def test_real_generator_card_png_attached_and_edit_rerenders_same_code(self):
        chat = self.chat()
        for rel in base.testkit._git(REPO_ROOT, 'ls-files', 'storefront-mockup').splitlines():
            if not rel.startswith('storefront-mockup/assets/') and not (chat.kit.wt / rel).exists():
                (chat.kit.wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, chat.kit.wt / rel)
        base.testkit._git(chat.kit.wt, 'add', '-A')
        base.testkit._git(chat.kit.wt, 'commit', '-s', '-m', 'Full fixture site')
        chat.conv.previewer = preview.Previewer(chat.kit.wt, viewports=('phone',))
        _, said = chat.say('sell for $2', base.JAR)
        code = chat.live()['draft_code']
        sent = chat.out.sent[-1]
        self.assertIn('yes ' + code, sent['text'])
        self.assertNotIn("couldn't render", sent['text'])
        self.assertIn('All website card text:', sent['text'])
        self.assertIn('Link to this', sent['text'])
        attachment = Path(sent['attachments'][0])
        from PIL import Image
        with Image.open(attachment) as im:
            self.assertEqual(im.format, 'PNG')
            self.assertGreater(im.height, 300)
            self.assertLess(im.width, 390)  # actual product box, not the whole viewport
        before = hashlib.sha256(attachment.read_bytes()).hexdigest()
        chat.say('add: Useful for furniture.')
        self.assertEqual(chat.live()['draft_code'], code)
        sent = chat.out.sent[-1]
        self.assertIn('Useful for furniture.', sent['text'])
        self.assertNotEqual(hashlib.sha256(Path(sent['attachments'][0]).read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()

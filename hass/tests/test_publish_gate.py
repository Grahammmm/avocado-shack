"""G's Gorilla label/price conversation, real draft/apply + private real-site card capture."""
import hashlib
import json
import shutil

import unittest
from pathlib import Path
from unittest import mock

from hass import live_policy, media, photo_polish, preview, product_claims
from hass import statebackup
from hass.content_model import REPO_ROOT
from hass.interpret_check import PRICE_REPLY
from hass.ops import photos, Refused
from hass.skills import testkit
from hass.tests import test_item_add_dispatch as base
from hass.tests.test_intake_simple import DETAILS
from hass.tests.test_label_reader import reader, recorded


GLUE_CAPTION = 'Just bought 50 of these for $1. I will sell at $2'
LIVE_GLUE_CAPTION = 'Bought 100 of these for $1 each. Ill sell them for $2 each'
SOURCE_EDIT = 'Nice. Just change one thing “ask us about the source in the store”. You should get that info here. This is from “miners”'


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

    def real_previewer(self, chat):
        for rel in base.testkit._git(REPO_ROOT, 'ls-files', 'storefront-mockup').splitlines():
            if not rel.startswith('storefront-mockup/assets/') and not (chat.kit.wt / rel).exists():
                (chat.kit.wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO_ROOT / rel, chat.kit.wt / rel)
        base.testkit._git(chat.kit.wt, 'add', '-A')
        base.testkit._git(chat.kit.wt, 'commit', '-s', '-m', 'Full fixture site')
        chat.base_commits = int(base.testkit._git(chat.kit.wt, 'rev-list', '--count', 'HEAD'))
        chat.conv.previewer = preview.Previewer(chat.kit.wt, viewports=('phone',))

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

    def test_exact_glue_caption_is_one_listing_and_each_updates_the_same_code(self):
        chat = self.chat()
        # The legacy reader can refuse the price if the finance caption leaks to it.
        chat.script(GLUE_CAPTION, {'question': PRICE_REPLY})
        disposition, said = chat.say(GLUE_CAPTION, base.JAR)
        self.assertEqual(disposition, 'proposed', said)
        code, = [row['code'] for row in chat.drafts()]
        for words, price in ((None, '2.00'), ('$2 each', '2.00 each')):
            if words:
                disposition, said = chat.say(words)
            self.assertEqual(disposition, 'proposed', said)
            reply, = said
            self.assertIn('Price: $' + price, reply.splitlines())
            self.assertIn('Private (not shown on the website): cost $1.00, quantity 50', reply)
            self.assertIn('yes ' + code, reply)
            self.assertTrue(chat.out.sent[-1]['attachments'])
            product, draft = self.product(chat)
            self.assertEqual(product['sellingPrice'], price)
            self.assertNotIn('$1', product['description'])
            self.assertEqual(live_policy.check(draft), [])
        self.assertEqual(chat.asked, [])
        self.assertEqual(len(chat.drafts()), 1)
        self.assertEqual(chat.commits(), 0)

    def test_photo_label_does_not_replace_an_older_unsent_reply(self):
        chat = self.chat()
        earlier = 'An earlier reply still waiting to go out.'
        chat.conv.outbox.add(testkit.CHAT, earlier)
        disposition, (first, listing) = chat.say(GLUE_CAPTION, base.JAR)
        self.assertEqual(disposition, 'proposed')
        self.assertEqual(first, earlier)
        self.assertIn("Here's the listing:", listing)

    def test_live_source_edit_changes_only_source_under_same_code(self):
        chat = self.chat()
        self.real_previewer(chat)
        _, (initial,) = chat.say(LIVE_GLUE_CAPTION, base.JAR)
        self.assertIn('Source line: Ask us about the source in store.', initial)
        original, draft = self.product(chat)
        code = chat.live()['draft_code']
        for text, supplier in ((SOURCE_EDIT, 'Miners'), ('source is North Farm', 'North Farm'),
                               ('we get it from Ridge Farm', 'Ridge Farm')):
            disposition, (said,) = chat.say(text)
            self.assertEqual(disposition, 'proposed', said)
            self.assertEqual(chat.live()['draft_code'], code)
            product, revised = self.product(chat)
            self.assertEqual({k: v for k, v in product.items() if k != 'labelSource'},
                             {**{k: v for k, v in original.items() if k != 'labelSource'}, 'supplier': supplier})
            self.assertCountEqual(product['labelSource']['text'], original['labelSource']['text'])
            self.assertNotEqual(revised['draft_hash'], draft['draft_hash'])
            self.assertEqual(live_policy.check(revised), [])
            self.assertIn('From ' + supplier, said.split('All website card text:', 1)[1])
            self.assertIn(original['description'], said.split('All website card text:', 1)[1])
            self.assertNotIn('Just change one thing', said)
        for text in ('change that line', 'this is from Miners or Ridge Farm'):
            disposition, (question,) = chat.say(text)
            self.assertEqual(disposition, 'question')
            self.assertTrue(question.endswith('?') and question.count('?') == 1, question)
            self.assertFalse(chat.out.sent[-1]['attachments'])
            self.assertEqual(self.product(chat)[1]['draft_hash'], revised['draft_hash'])
        disposition, (protected,) = chat.say('source is Organic Ridge Farm')
        self.assertEqual(disposition, 'claim-question', protected)
        self.assertNotIn('Reply yes ' + code, protected)
        self.assertEqual(self.product(chat)[1]['draft_hash'], revised['draft_hash'])
        self.assertEqual(chat.commits(), 0)

    def test_label_read_has_no_pending_reply_even_with_finance_fallback(self):
        from types import SimpleNamespace
        for text, model_calls in ((LIVE_GLUE_CAPTION, 0), ('$1/sell $2', 0),
                                  ('Bought 100 of these for $1 each. I plan to sell at two bucks', 1)):
            with self.subTest(text=text):
                chat = self.chat()
                finance = mock.Mock(return_value={'price_cents': 200, 'cost_cents': 100, 'quantity': 100})
                chat.conv.answer_reader = SimpleNamespace(fields=finance)
                label = chat.conv.labels.read
                def observe(*args, **kwargs):
                    self.assertEqual(chat.conv.flush(chat.out), 0)
                    return label(*args, **kwargs)
                # A callback exception is intentionally caught: Wood Glue plus a
                # real proposed disposition below prove that the callback completed.
                with mock.patch.object(chat.conv.labels, 'read', side_effect=observe):
                    disposition, (said,) = chat.say(text, base.JAR)
                self.assertEqual(disposition, 'proposed', said)
                self.assertIn('Wood Glue', said)
                self.assertNotIn('Not read yet', said)
                self.assertIn('cost $1.00', said)
                self.assertEqual(finance.call_count, model_calls)
                self.assertEqual(chat.asked, [])
                self.doCleanups()

    def test_food_organic_label_is_quoted_but_owner_health_phrase_dropped_only(self):
        chat = self.chat({'name': 'Jam', 'brand': 'Test kitchen', 'category': 'pantry',
                          'description': 'Raspberry jam in a jar.', 'printed_claims': ['Organic']})
        chat.say('sell for $2', base.JAR)
        code = chat.live()['draft_code']
        disposition, said = chat.say('add: cures cancer. Good on toast.')
        self.assertEqual(disposition, 'proposed', said)
        product, draft = self.product(chat)
        self.assertIn('Label says: “Organic”', product['description'])
        self.assertIn('Features: Label says: “Organic”', said[0])
        self.assertNotIn('Label says: “”', said[0])
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

    def test_nonfood_new_and_existing_claims_require_exact_label_wording(self):
        for category in ('hardware', 'flowers', 'general'):
            for before in (None, {'category': category, 'description': 'A product.'}):
                for claim in ('Cures cancer.', 'Made in USA.', 'Organic.', 'Award-winning.'):
                    with self.subTest(category=category, before=before, claim=claim):
                        product = {'category': category, 'description': claim}
                        draft = {'ops': [{'op': 'product.add' if before is None else 'product.edit', 'args': {}}],
                                 'records': [{'collection': 'products', 'key': 'fixture', 'before': before, 'after': product}]}
                        self.assertTrue(live_policy.check(draft))
                        # Exact admitted label wording is the only non-food exception.
                        product['labelSource'] = {'source': 'label', 'photo': 'a' * 64, 'text': [claim]}
                        self.assertEqual(live_policy.check(draft), [])
                        product['description'] += ' Made in Mexico.'
                        self.assertTrue(live_policy.check(draft))
                        product['description'] = claim.swapcase()
                        self.assertTrue(live_policy.check(draft))
                        product['description'] = claim
                        product['labelSource']['source'] = 'owner'
                        self.assertTrue(live_policy.check(draft))

    def test_styled_image_and_failed_card_send_exact_frozen_pixels(self):
        import io
        from PIL import Image
        picture = io.BytesIO()
        Image.new('RGB', (800, 800), '#aabbcc').save(picture, 'JPEG')
        wanted = picture.getvalue()
        chat = self.chat(settings={'houseRender': True})
        chat.conv.previewer.capture = mock.Mock(return_value={'ok': False, 'png': None, 'error': 'capture failed'})
        with mock.patch.object(photos, '_verdict', return_value={'ok': True, 'jpeg': wanted}):
            _, said = chat.say('sell for $2', base.JAR)
            product, draft = self.product(chat)
            rendered = chat.conv.editor.render_draft(draft['change_id'])
            self.assertEqual(rendered['assets']['storefront-mockup/' + product['image']], wanted)
            sha = chat.live()['slots']['photo']
            self.assertNotEqual(Path(media.web_copy(chat.conv.settings['mediaRoot'], sha)['path']).read_bytes(), wanted)
            self.assertEqual(Path(chat.out.sent[-1]['attachments'][0]).read_bytes(), wanted)
            self.assertIn("couldn't render the website card", said[0])
            self.assertIn('yes ' + chat.live()['draft_code'], said[0])
            chat.say('yes ' + chat.live()['draft_code'])
            self.assertEqual(chat.commits(), 1)
            self.assertEqual((chat.kit.wt / 'storefront-mockup' / product['image']).read_bytes(), wanted)

    def test_missing_or_changed_frozen_image_cannot_be_approved(self):
        chat = self.chat()
        chat.conv.previewer.capture = mock.Mock(return_value={'ok': False, 'png': None, 'error': 'capture failed'})
        with mock.patch.object(chat.conv, '_listing_picture', return_value=None):
            _, said = chat.say('sell for $2', base.JAR)
        code = chat.live()['draft_code']
        self.assertNotIn('yes ' + code, said[0])
        self.assertEqual(chat.say('yes ' + code)[0], 'no-target')
        self.assertEqual(chat.commits(), 0)
        product, draft = self.product(chat)
        rendered = chat.conv.editor.render_draft(draft['change_id'])
        rendered['assets']['storefront-mockup/' + product['image']] = b'different pixels'
        with mock.patch.object(chat.conv.editor, 'render_draft', return_value=rendered):
            self.assertIsNone(chat.conv._listing_picture(draft, product))
            self.assertFalse(chat.conv._capture(draft)['ok'])

    def test_unsent_new_version_does_not_reuse_old_delivered_picture(self):
        chat = self.chat()
        chat.say('sell for $2', base.JAR)
        code = chat.live()['draft_code']
        old_hash = chat.drafts()[0]['draft_hash']
        with mock.patch.object(chat.conv, 'flush', return_value=0):
            chat.say('add: Useful for furniture.')
            self.assertNotEqual(chat.drafts()[0]['draft_hash'], old_hash)
            self.assertEqual(chat.say('yes ' + code)[0], 'no-target')
            self.assertEqual(chat.commits(), 0)
        chat.conv.flush(chat.out)
        self.assertEqual(chat.say('yes ' + code)[0], 'approved')
        self.assertEqual(chat.commits(), 1)

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
        # Exercise the real scheduling and decision store; no provider/network.
        chat.conv.polish_transport = mock.Mock(return_value={'ok': False, 'code': 'auth'})
        with mock.patch.object(photos, '_verdict', side_effect=AssertionError('fallback must be the owner photo')):
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
        chat.conv.polish_transport.assert_called_once()

    def test_styled_picture_finishes_before_freeze_and_is_reused_for_source_edit(self):
        from PIL import Image
        chat = self.chat(settings={'houseRender': True, 'photo_polish': True})
        transactions = []
        def edit(src, out, timeout):
            transactions.append(chat.conv.db.in_transaction)
            Image.new('RGB', (800, 800), '#e8d7b8').save(out, 'JPEG')
            return {'ok': True, 'code': 'ok'}
        chat.conv.polish_transport = mock.Mock(side_effect=edit)
        # Fidelity tests live in test_photo_polish. Here check which pixels the
        # actual Conversation/editor freeze and hand to the previewer.
        with mock.patch.object(photo_polish, 'gate', side_effect=lambda src, edited:
                               {'ok': True, 'jpeg': edited}) as gate:
            disposition, (said,) = chat.say(LIVE_GLUE_CAPTION, base.JAR)
            self.assertEqual(disposition, 'proposed', said)
            self.assertIn('Picture: styled from your photo.', said)
            original, styled = gate.call_args.args
            self.assertNotEqual(original, styled)
            _, (edited,) = chat.say(SOURCE_EDIT)
            self.assertIn('Picture: styled from your photo.', edited)
            gate.assert_called_once()
        chat.conv.polish_transport.assert_called_once()
        self.assertEqual(transactions, [False])
        product, draft = self.product(chat)
        assets = chat.conv.editor.render_draft(draft['change_id'])['assets']
        self.assertEqual(assets['storefront-mockup/' + product['image']], styled)

    def test_render_failure_answers_once_and_explicit_retry_rechecks_policy(self):
        chat = self.chat()
        chat.conv.previewer.capture = mock.Mock(return_value={'ok': False, 'png': None, 'error': "Cannot find module 'playwright'"})
        _, said = chat.say('sell for $2', base.JAR)
        self.assertIn("couldn't render the website card", said[0])
        self.assertTrue(chat.out.sent[-1]['attachments'])
        code, = [row['code'] for row in chat.drafts()]
        self.assertIn('yes ' + code, said[0])
        chat.now += base.timedelta(seconds=31)
        self.assertEqual(chat.conv.retry_previews(), 0)
        self.assertEqual(chat.conv.flush(chat.out), 0)
        chat.conv._live_reasons = lambda draft: ['protected sentences: contact']
        _, (retried,) = chat.say('?')
        self.assertIn("can't put this", retried)
        self.assertNotIn('yes ' + code, retried)

    def test_fallback_picture_survives_backup_verify_and_restore(self):
        chat = self.chat()
        chat.conv.previewer = mock.Mock()
        chat.conv.previewer.capture.return_value = {'ok': False, 'png': None, 'error': 'Please update your version of Node.js.'}
        disposition, (said,) = chat.say(GLUE_CAPTION, base.JAR)
        self.assertEqual(disposition, 'proposed')
        self.assertIn("couldn't render the website card", said)
        attached, = chat.out.sent[-1]['attachments']
        path = Path(attached)
        data = path.read_bytes()
        self.assertEqual(path.name, hashlib.sha256(data).hexdigest() + '.jpg')
        state = chat.conv.sdir
        out = state.parent / 'fallback-backups'
        out.mkdir(mode=0o700)
        backed = statebackup.create(state, out)
        self.assertEqual(backed['result'], 'ok', backed)
        backup = Path(backed['backup'])
        rel = path.relative_to(state)
        self.assertEqual((backup / rel).read_bytes(), data)
        self.assertEqual(statebackup.verify(backup)['result'], 'ok')
        drill = state.parent / 'fallback-drill'
        testkit._git(chat.kit.repo.main, 'worktree', 'add', '-b', 'hass/fallback-drill', str(drill))
        restored = state.parent / 'restored-state'
        result = statebackup.restore(backup, restored, drill)
        self.assertEqual(result['result'], 'ok', result)
        self.assertEqual((restored / rel).read_bytes(), data)

    def test_text_only_persimmons_generate_illustration_without_private_finances(self):
        chat = self.chat()
        from types import SimpleNamespace
        prompts = []
        def generate(prompt, out, timeout):
            prompts.append(prompt)
            from PIL import Image, ImageOps
            with Image.open(REPO_ROOT / base.JAR) as image:
                ImageOps.pad(image.convert('RGB'), (800, 800), color='ivory').save(out, 'JPEG')
            return {'ok': True, 'code': 'ok'}
        chat.conv.polish_transport = SimpleNamespace(generate=generate)
        text = 'add Fuyu persimmons'
        chat.script(text, base.reply(name='Fuyu persimmons', shelf='fruit',
                                    description='Fuyu persimmons are crisp and sweet. Slice and eat while firm.'))
        disposition, said = chat.say(text + '; bought 40 at $1.75, sell for $3.50')
        self.assertEqual(disposition, 'proposed', said)
        self.assertTrue(chat.live()['slots']['intake']['generated_picture'])
        self.assertEqual(len(prompts), 1)
        self.assertNotIn('1.75', prompts[0])
        self.assertNotIn('40', prompts[0])
        self.assertIn('generated illustration', said[0])
        self.assertTrue(chat.out.sent[-1]['attachments'])
        self.assertIn('yes ' + chat.live()['draft_code'], said[0])
        self.assertEqual(live_policy.check(self.product(chat)[1]), [])

    def test_text_only_generation_failure_offers_photo_without_confirmation(self):
        chat = self.chat()
        chat.script('add persimmons', base.reply(name='Persimmons', shelf='fruit'))
        disposition, said = chat.say('add persimmons; sell for $3.50')
        self.assertEqual(disposition, 'question', said)
        self.assertIn('Please send a photo', said[0])
        self.assertNotIn('yes ', said[0])
        self.assertEqual(chat.drafts(), [])

    def test_only_owner_typed_origin_or_organic_is_accepted_not_a_different_origin(self):
        owner = {'source': 'owner', 'photo': 'a' * 64, 'text': ['Organic', 'Made in USA']}
        product = {'category': 'fruit', 'ownerSource': owner}
        self.assertFalse(product_claims.protected('Organic persimmons. Made in USA.', product)[1])
        self.assertTrue(product_claims.protected('Made in Mexico.', product)[1])
        self.assertTrue(product_claims.protected('Cures cancer.', product)[1])
        self.assertTrue(product_claims.protected('Organic.', {'category': 'fruit'})[1])

    def test_exact_text_only_persimmon_units_generate_render_and_publish_frozen_picture(self):
        from types import SimpleNamespace
        from PIL import Image
        for unit, shown in (('lb', 'per lb'), ('each', 'each')):
            with self.subTest(unit=unit):
                chat = self.chat()
                self.real_previewer(chat)
                prompts = []
                def generate(prompt, out, timeout):
                    prompts.append(prompt)
                    # Offline transport fixture only; actual Codex route has a separate receipt.
                    Image.new('RGB', (800, 800), '#eab04a').save(out, 'JPEG')
                    return {'ok': True, 'code': 'ok'}
                chat.conv.polish_transport = SimpleNamespace(generate=generate)
                chat.script('add persimmons; Fuyu', base.reply(name='Persimmons', shelf='fruit',
                    description='Fuyu persimmons are sweet and crisp. Eat firm or let soften. Store in a cool place.'))
                disposition, said = chat.say('add persimmons, Fuyu, $3.50/' + unit + ', 40 lb in stock, cost $1.75')
                self.assertEqual(disposition, 'proposed', said)
                code = chat.live()['draft_code']
                self.assertIn('Price: $3.50 ' + shown, said[0].splitlines())
                self.assertIn('Private (not shown on the website): cost $1.75, quantity 40 lb', said[0].splitlines())
                self.assertIn('generated illustration', said[0])
                self.assertIn('All website card text:', said[0])
                self.assertIn('$3.50 ' + shown, said[0].split('All website card text:', 1)[1])
                self.assertNotIn("couldn't render", said[0])
                self.assertIn('yes ' + code, said[0])
                with Image.open(chat.out.sent[-1]['attachments'][0]) as image:
                    self.assertEqual(image.format, 'PNG')
                self.assertEqual(len(prompts), 1)
                self.assertNotIn('1.75', prompts[0])
                self.assertNotIn('40', prompts[0])
                product, draft = self.product(chat)
                self.assertEqual(product['description'], 'Fuyu persimmons are sweet and crisp. Eat firm or let soften. Store in a cool place.')
                self.assertIn('Website description: ' + product['description'], said[0])
                self.assertEqual(live_policy.check(draft), [])
                rendered = chat.conv.editor.render_draft(draft['change_id'])
                public = b'\n'.join(rendered['files'].values())
                self.assertNotIn(b'1.75', public)
                self.assertNotIn(b'40 lb', public)
                image_key = 'storefront-mockup/' + product['image']
                picture = rendered['assets'][image_key]
                chat.say('yes ' + code)
                self.assertEqual(chat.commits(), 1)
                self.assertEqual((chat.kit.wt / image_key).read_bytes(), picture)
                saved = json.loads((chat.kit.wt / 'hass/content/products.json').read_text())['products'][-1]
                self.assertEqual(saved['description'], product['description'])
                self.doCleanups()

    def test_photo_persimmon_typed_organic_and_origin_survive_real_claim_gate(self):
        chat = self.chat({'name': 'Persimmons', 'category': 'fruit', 'description': 'Sweet crisp Fuyu persimmons.'})
        chat.script('add persimmons; Fuyu; Organic; Made in USA', base.reply(name='Persimmons', shelf='fruit',
                    description='Organic Fuyu persimmons. Made in USA. Sweet and crisp.'))
        disposition, said = chat.say('add persimmons, Fuyu, Organic, Made in USA, $3.50/lb, 40 lb in stock, cost $1.75', base.JAR)
        self.assertEqual(disposition, 'proposed', said)
        product, draft = self.product(chat)
        self.assertIn('Organic', product['description'])
        self.assertIn('Made in USA', product['description'])
        self.assertEqual(product['ownerSource']['source'], 'owner')
        self.assertEqual(live_policy.check(draft), [])
        self.assertIn('Price: $3.50 per lb', said[0].splitlines())
        self.assertIn('yes ' + chat.live()['draft_code'], said[0])

    def test_generated_produce_prose_keeps_ordinary_copy_not_invented_claims_or_maker(self):
        chat = self.chat({})
        text = 'add Fuyu persimmons'
        chat.script(text, base.reply(name='Fuyu persimmons', shelf='fruit', maker='Invented Orchard',
                    description='Fuyu persimmons are sweet and crisp. Organic. Made in Spain. Cures cancer.'))
        disposition, said = chat.say(text + '; sell for $3.50', base.JAR)
        self.assertEqual(disposition, 'proposed', said)
        product, draft = self.product(chat)
        self.assertIn('sweet and crisp', product['description'])
        for phrase in ('Organic', 'Made in Spain', 'Cures cancer'):
            self.assertNotIn(phrase, product['description'])
            self.assertIn(phrase, said[0])  # explicitly disclosed as dropped, not silently lost
        self.assertEqual(product['brand'], 'Producer not identified')
        self.assertEqual(live_policy.check(draft), [])

    def test_real_generator_card_png_attached_and_edit_rerenders_same_code(self):
        chat = self.chat()
        self.real_previewer(chat)
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
            self.assertGreater(im.height, 200)
            self.assertLess(im.width, 390)  # actual product box, not the whole viewport
        before = hashlib.sha256(attachment.read_bytes()).hexdigest()
        chat.say('add: Useful for furniture.')
        self.assertEqual(chat.live()['draft_code'], code)
        sent = chat.out.sent[-1]
        self.assertIn('Useful for furniture.', sent['text'])
        self.assertNotEqual(hashlib.sha256(Path(sent['attachments'][0]).read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()

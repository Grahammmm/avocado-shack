"""AVB-19-B2: fixed private pages, FAQ lifecycle, current dispatch and real previews."""
import copy
import json
import os
import re
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from hass import editor, live_policy, preview, sitegen
from hass.content_model import INFO_PAGES, REPO_ROOT, load_content, validate_store
from hass.ops import OpContext, Refused, load_registry
from hass.skills import load_skills, router, skill_lint, testkit
from hass.skills.backlog import NO_FAQ
from hass.skills.front import FRONT_FAQ, FRONT_PAGE, plan_faq, plan_page
from hass.skills.shop import SkillStop
from hass.tests import test_front as front_fixture
from hass.tests import test_skill_dispatch as dispatch_fixture
from hass.tests.test_store_ops import StoreTestCase

PAGE = {'page':'about','title':'About the Shack','intro':'Hello neighbors',
        'paragraphs':['A small market where neighbors can stop and say hello.']}
FAQ = {'question':'Can we ask at the shop?','answer':'Yes, please say hello.'}


class PageTests(unittest.TestCase):
    def setUp(self):
        self.content = copy.deepcopy(load_content())
        self.ops = load_registry()
        self.ctx = OpContext(datetime(2026,11,8,17,tzinfo=timezone.utc), REPO_ROOT/'storefront-mockup', {})

    def apply(self, name, args):
        return self.ops[name].apply(self.content, args, self.ctx)

    def test_shown_hidden_fixed_paths_escaping_and_footer_only(self):
        baseline = sitegen.render(self.content)
        for path in INFO_PAGES:
            rel = sitegen.SITE_PREFIX + path + '/index.html'
            self.assertIn(b'Nothing here yet', baseline[rel])
            self.assertIn(b'content="noindex"', baseline[rel])
            self.assertNotIn(path+'/index.html',sitegen.publish_files(self.content,REPO_ROOT))
            args = {**PAGE, 'page':path,'title':'Hello & neighbors'} if path!='faq' else {'page':'faq','title':'Questions'}
            self.assertNotIsInstance(self.apply('store.set_page',args), Refused)
        files = sitegen.render(self.content)
        for rel, data in files.items():
            if rel.endswith('.html'):
                footer = re.search(r'<footer>.*?</footer>',data.decode())[0]
                for path in INFO_PAGES:
                    self.assertEqual(footer.count('href="/'+path+'/"'),1,rel)
                if rel in baseline:
                    self.assertEqual(re.search(rb'<nav.*?</nav>',data)[0],re.search(rb'<nav.*?</nav>',baseline[rel])[0])
        published = sitegen.publish_files(self.content,REPO_ROOT)
        self.assertTrue(all(path+'/index.html' in published for path in INFO_PAGES))
        self.assertIn(b'Hello &amp; neighbors',files['storefront-mockup/about/index.html'])
        value = copy.deepcopy(self.content.store['pageAbout'])
        self.apply('store.hide_page',{'page':'about'})
        self.assertEqual(self.content.store['pageAbout'],{**value,'shown':False})
        self.assertEqual(sitegen.render(self.content)['storefront-mockup/about/index.html'],baseline['storefront-mockup/about/index.html'])
        self.assertNotIn('about/index.html',sitegen.publish_files(self.content,REPO_ROOT))
        self.apply('store.set_page',{'page':'about'})
        self.assertEqual(self.content.store['pageAbout'],value)

    def test_faq_single_draft_folded_replace_last_remove_and_limit(self):
        before = copy.deepcopy(self.content.store)
        touched = self.apply('store.set_faq',FAQ)
        self.assertEqual(len(touched),1)
        self.assertEqual(set(self.content.store)-set(before),{'pageFaq'})
        value = self.content.store['pageFaq']
        self.assertTrue(value['shown'])
        self.apply('store.set_faq',{'question':FAQ['question'].upper(),'answer':'Please ask Michael.'})
        self.assertEqual(len(self.content.store['pageFaq']['entries']),1)
        text = sitegen.render(self.content)['storefront-mockup/faq/index.html'].decode()
        self.assertIn('<details><summary>'+FAQ['question'].upper()+'</summary><p>Please ask Michael.</p></details>',text)
        self.apply('store.remove_faq',{'question':FAQ['question']})
        self.assertEqual(self.content.store['pageFaq'],{'shown':False,'title':'Questions','entries':[]})
        for n in range(20):
            self.assertNotIsInstance(self.apply('store.set_faq',{'question':f'Question number {n}?','answer':'Ask us.'}),Refused)
        saved = copy.deepcopy(self.content.store)
        self.assertIsInstance(self.apply('store.set_faq',FAQ),Refused)
        self.assertEqual(self.content.store,saved)

    def test_refusals_malformed_schema_and_no_mutation(self):
        for edit in ({'title':'ab'},{'intro':'x'*301},{'paragraphs':[]},{'paragraphs':['short']},
                     {'paragraphs':PAGE['paragraphs']*7},{'intro':'hello\nthere'},{'intro':'example.com'},
                     {'intro':'a@b.com'},{'intro':'@someone'},{'intro':'<b>hello</b>'},{'intro':'Food $3'},
                     {'intro':'Hello {{name}}'},{'intro':'Hello\u200bthere'},{'page':'blog'}):
            self.assertIsInstance(self.apply('store.set_page',{**PAGE,**edit}),Refused,edit)
        self.assertIsInstance(self.apply('store.hide_page',{'page':'about'}),Refused)
        for edit in ({'question':'No mark'},{'question':'a?'},{'answer':'x'},{'answer':'x'*601},
                     {'answer':'example.com'},{'answer':'Half-price food'}):
            self.assertIsInstance(self.apply('store.set_faq',{**FAQ,**edit}),Refused,edit)
        self.assertIsInstance(self.apply('store.remove_faq',{'question':FAQ['question']}),Refused)
        self.assertFalse(any(key in self.content.store for key,_ in INFO_PAGES.values()))
        for key,_ in INFO_PAGES.values():
            for bad in ({},None,[],{'shown':True},{'title':'Hello','shown':False,'entries':[{}]}):
                problems=[]
                validate_store(problems,{**self.content.store,key:bad})
                self.assertTrue(problems,(key,bad))

    def test_private_plans_lint_cases_and_claims(self):
        reg = load_skills()
        self.assertEqual(len(reg.active()),41)
        self.assertIsNone(reg.get('page.faq'))
        self.assertEqual(skill_lint((FRONT_PAGE,FRONT_FAQ),self.ops,repo_root=REPO_ROOT),[])
        for skill in (FRONT_PAGE,FRONT_FAQ):
            results = testkit.run_file(REPO_ROOT/skill.cases,testkit.registry_skills())
            self.assertEqual([(r.id,r.problems) for r in results if not r.ok],[])
        for op in ('store.set_page','store.hide_page','store.set_faq','store.remove_faq'):
            self.assertIn(op,live_policy.PRIVATE)
            self.assertNotIn(op,live_policy.LIVE)
            got=live_policy.check({'ops':[{'op':op,'args':{}}],'records':[]})
            self.assertTrue(got,got)
        with self.assertRaises(SkillStop):
            plan_page({'template':'about',**{k:v for k,v in PAGE.items() if k!='page'},'title':'The best shop'}, {'texts':['Hello neighbors']})
        with self.assertRaises(SkillStop):
            plan_faq({**FAQ,'answer':'We are the best shop.'},{'texts':['Hello neighbors']})


class PageUndoTests(StoreTestCase):
    def test_creation_update_hide_undo_and_banner_link(self):
        repo = self.repo()
        baseline = repo.read('storefront-mockup/about/index.html')
        created = repo.run(('store.set_page',PAGE))
        original = repo.store()['pageAbout']
        changed = repo.run(('store.set_page',{'page':'about','intro':'Come say hello'}))
        repo.run(('history.revert',{'changeId':changed['change_id']}))
        self.assertEqual(repo.store()['pageAbout'],original)
        hidden = repo.run(('store.hide_page',{'page':'about'}))
        self.assertEqual(repo.store()['pageAbout'],{**original,'shown':False})
        repo.run(('history.revert',{'changeId':hidden['change_id']}))
        self.assertEqual(repo.store()['pageAbout'],original)
        today = date.today()  # the store ops read the real clock: a fixed window would end and be refused as already over
        repo.run(('store.set_banner',{'text':'Come say hello','start':today.isoformat(),
                                      'end':(today+timedelta(days=3)).isoformat(),'link':'about'}))
        repo.run(('history.revert',{'changeId':created['change_id']}))
        self.assertNotIn('pageAbout',repo.store())
        self.assertEqual(repo.read('storefront-mockup/about/index.html'),baseline)
        problems=[]
        validate_store(problems,repo.store())
        self.assertEqual(problems,[])
        self.assertNotIn('href="/about/"',repo.text('storefront-mockup/index.html'))
        self.assertIn('Come say hello',repo.text('storefront-mockup/index.html'))

    def test_faq_creation_later_entry_and_last_remove_undo(self):
        repo = self.repo()
        first = repo.run(('store.set_faq',FAQ))
        original = repo.store()['pageFaq']
        second = repo.run(('store.set_faq',{'question':'Another question?','answer':'Ask us.'}))
        repo.run(('history.revert',{'changeId':second['change_id']}))
        self.assertEqual(repo.store()['pageFaq'],original)
        last = repo.run(('store.remove_faq',{'question':FAQ['question']}))
        self.assertFalse(repo.store()['pageFaq']['shown'])
        repo.run(('history.revert',{'changeId':last['change_id']}))
        self.assertEqual(repo.store()['pageFaq'],original)
        repo.run(('history.revert',{'changeId':first['change_id']}))
        self.assertNotIn('pageFaq',repo.store())


class CurrentFaqDispatchTests(dispatch_fixture.SkillCase):
    SKILLS = tuple(load_skills().skills.values())

    def test_add_an_faq_reaches_model_without_old_refusal(self):
        self.assertIsNone(self.registry.get('page.faq'))
        # The bare ask names no question, so the model's question/answer are not his words: dispatch drops them and
        # front.faq asks for the question. Before the retirement this exact text got NO_FAQ from code, with no model call.
        self.script('add an FAQ',dispatch_fixture.skill_reply('front.faq',**FAQ))
        self.assertEqual(self.say('add an FAQ'),'question')
        self.assertEqual(self.replies(),['What is the question?'])
        self.assertEqual(len(self.asked),1)
        self.assertEqual((self.live()['skill'],self.live()['asked_slot']),('front.faq','question'))
        self.assertTrue(any(n=='front.faq' for n,_ in router.candidates('add an FAQ',skills=self.registry)))

    def test_an_faq_in_his_words_is_a_draft(self):
        text = 'add an FAQ: '+FAQ['question']+' '+FAQ['answer']
        self.script(text,dispatch_fixture.skill_reply('front.faq',**FAQ))
        self.assertEqual(self.say(text),'proposed')
        self.assertNotIn(NO_FAQ,' '.join(self.replies()))
        self.assertEqual([o['op'] for o in json.loads(self.drafts()[-1]['ops_json'])],['store.set_faq'])


@unittest.skipUnless(os.environ.get('PLAYWRIGHT_MODULE'),'PLAYWRIGHT_MODULE is not set')
class PageCaptures(StoreTestCase):
    # Reuse only the B1 fixture helpers (full-site worktree, shot directory, check assertions), not its test cases.
    setUp = front_fixture.FrontCaptureTests.setUp
    assertPassed = front_fixture.FrontCaptureTests.assertPassed

    def test_four_pages_phone_desktop(self):
        for path in INFO_PAGES:
            draft = self.r.run(('store.set_faq',FAQ)) if path=='faq' else self.r.run(('store.set_page',{**PAGE,'page':path,'title':INFO_PAGES[path][1]}))
            record = draft['records'][0]
            target = preview.target_for(record)
            files = {rel:self.r.read(rel) for rel in editor.GENERATED_PATHS}
            got = preview.Previewer(self.r.wt).capture(files,target,self.out/f'front.{path}.png')
            self.assertPassed(got,'pageTitle')

"""AVB-19 B1: home order, dated top strip, private ops, selective undo and skill cases."""
import copy
import re
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from hass import live_policy, notice, preview, sitegen
from hass.content_model import REPO_ROOT, default_sections, load_content, validate_store
from hass.ops import OpContext, Refused, load_registry
from hass.skills import load_skills, skill_lint, testkit
from hass.skills.front import FRONT_BANNER, FRONT_SECTIONS, plan_banner, plan_sections
from hass.skills.shop import SkillStop
from hass.tests.test_notice_specials_prestart import Tree, check, sp
from hass.tests.test_undo import H06TestCase

DAY = date(2026, 11, 8)
BANNER = {'text': 'Come say hello', 'start': '2026-11-09', 'end': '2026-11-12', 'link': 'visit'}
INDEX = 'storefront-mockup/index.html'
HIKE = 'storefront-mockup/hike/index.html'


class FrontTests(unittest.TestCase):
    def setUp(self):
        self.content = copy.deepcopy(load_content())
        self.ctx = OpContext(datetime(2026, 11, 8, 17, tzinfo=timezone.utc), REPO_ROOT/'storefront-mockup', {})
        self.ops = load_registry()

    def apply(self, name, args):
        return self.ops[name].apply(self.content, args, self.ctx)

    def test_absent_keys_preserve_existing_generated_bytes(self):
        self.assertNotIn('homeSections', self.content.store)
        self.assertNotIn('banner', self.content.store)
        for path, data in sitegen.render(self.content).items():
            self.assertEqual(data, (REPO_ROOT/path).read_bytes(), path)

    def test_sections_order_hidden_links_and_hero(self):
        self.apply('store.set_sections', {'order':['visit','newsletter','market','our-way'], 'hidden':['newsletter','our-way']})
        files = sitegen.render(self.content, today=DAY)
        home = files[INDEX].decode()
        self.assertEqual(re.findall(r'<section[^>]*\bid="([^"]+)"',home), ['visit','market'])
        self.assertLess(home.index('class="hero"'), home.index('id="visit"'))
        for path in (INDEX, HIKE):
            text = files[path].decode()
            for block in re.findall(r'<(?:nav|footer)\b.*?</(?:nav|footer)>',text):
                self.assertNotIn('#newsletter',block)
                self.assertNotIn('#our-way',block)
        self.assertIsInstance(self.apply('store.set_sections', {'order':['visit','newsletter','market','our-way'], 'hidden':['newsletter','our-way']}), Refused)
        self.apply('store.reset_sections', {})
        self.assertNotIn('homeSections',self.content.store)
        self.assertIsInstance(self.apply('store.reset_sections', {}), Refused)

    def test_ops_refuse_invalid_sections_and_banner_without_mutation(self):
        for args in ({'order':['market']*4}, {'order':['market','visit']},
                     {'order':['market','our-way','visit','newsletter'],'hidden':['visit']},
                     {'order':['market','our-way','visit','newsletter'],'hidden':['market']},
                     {'order':['market','our-way','visit','newsletter'],'hidden':['gallery']}):
            with self.subTest(args=args):
                self.assertIsInstance(self.apply('store.set_sections',args), Refused)
        for edit in ({'text':'ab'}, {'text':'12!'}, {'text':'word\nword'}, {'text':'x'*81}, {'text':'<b>hello</b>'},
                     {'text':'Hello {{name}}'}, {'text':'Hello\u200bworld'}, {'text':'Hello example.com'}, {'text':'Hello a@b.com'},
                     {'text':'Hello @someone'}, {'text':'Food $3'}, {'text':'Half-price food'}, {'end':'2026-02-30'},
                     {'end':'2026-11-08'}, {'end':'2026-12-11'}, {'start':'2027-02-01','end':'2027-02-02'},
                     {'link':'https://example.com'}, {'link':'about'}):
            with self.subTest(edit=edit):
                self.assertIsInstance(self.apply('store.set_banner', {**BANNER,**edit}), Refused)
        self.assertNotIn('banner',self.content.store)
        self.assertNotIn('homeSections',self.content.store)
        self.assertIsInstance(self.apply('store.clear_banner',{}),Refused)
        self.apply('store.set_banner',BANNER)
        self.assertIsInstance(self.apply('store.set_banner',BANNER),Refused)
        self.apply('store.clear_banner',{})
        self.assertNotIn('banner',self.content.store)

    def test_schema_dates_limits_links_and_escaped_words(self):
        for start,end in [('2026-11-08','2026-12-09'),('0001-01-01','0001-01-01'),('9999-12-31','9999-12-31')]:
            self.content.store['banner']={**BANNER,'start':start,'end':end,'text':'Come & say hello'}
            problems=[]
            validate_store(problems,self.content.store)
            self.assertEqual(problems,[])
        self.content.store['banner']={**BANNER,'text':'Come & say hello','link':'about'}
        text=sitegen.render(self.content,today=date(2026,11,9))[INDEX].decode()
        self.assertIn('Come &amp; say hello',text)
        self.assertNotIn('href="/about/"',text)
        self.content.store['banner']={**BANNER,'start':'2027-01-07','end':'2027-01-08'} # exactly 60 days ahead
        self.assertNotIsInstance(self.apply('store.set_banner',BANNER), Refused)

    def test_banner_initial_visibility_home_hike_and_404(self):
        baseline=sitegen.render(self.content,today=DAY)
        self.content.store['banner']=BANNER
        for day,live in [(DAY,False),(date(2026,11,9),True),(date(2026,11,12),True),(date(2026,11,13),False)]:
            files=sitegen.render(self.content,today=day)
            self.assertEqual(files['storefront-mockup/404.html'],baseline['storefront-mockup/404.html']) if 'storefront-mockup/404.html' in files else None
            for path in (INDEX,HIKE):
                text=files[path].decode()
                self.assertEqual('data-banner-default hidden' in text, live)
                self.assertEqual('data-end="2026-11-12" hidden' not in text, live)
                self.assertIn(notice.BANNER_JS,text)
                self.assertNotIn('effectiveDay',text)
                self.assertNotIn('setFixedTime',text)
        self.assertIn('new Date()',notice.BANNER_JS)

    def test_dated_artifacts_share_one_earlier_day(self):
        self.content.store['banner']=BANNER
        self.content.store['specials']=[sp(1,'2026-11-13','2026-11-20')]
        today=date(2026,11,15)
        for saved in [DAY,date(2026,11,9),date(2026,11,12),date(2026,11,13)]:
            with self.subTest(saved=saved), Tree(self.content,saved) as tree:
                self.assertEqual(check(self.content,tree.root,today),[])
        with Tree(self.content,today) as tree:
            mixed=sitegen.render(self.content,today=today,banner_today=date(2026,11,10))
            (tree.root/INDEX).write_bytes(mixed[INDEX])
            self.assertEqual(check(self.content,tree.root,today),[INDEX])

    def test_preview_changes_only_its_written_keys_and_one_effective_day(self):
        before=copy.deepcopy(self.content.store)
        after={**before,'banner':BANNER,'notice':{'text':'Hello neighbors','until':'2026-11-08'},
               'specials':[sp(1,'2026-11-09','2026-11-10')]}
        target=preview.target_for({'collection':'store','before':before,'after':after},DAY)
        self.assertEqual(target['effectiveDay'],'2026-11-09')
        self.assertEqual(target['banner'],{'text':'Come say hello','link':'/#visit'})
        self.assertEqual(target['specials'],[{'title':'Synthetic 1','deal':'Free sample 1'}])
        self.assertIsNone(target['notice'])
        unchanged=preview.target_for({'collection':'store','before':after,'after':{**after,'intro':'Hello'}},DAY)
        self.assertNotIn('banner',unchanged)
        self.assertNotIn('effectiveDay',unchanged)
        cleared=preview.target_for({'collection':'store','before':after,'after':before},DAY)
        self.assertIsNone(cleared['banner'])
        self.assertNotIn('effectiveDay',cleared)

    def test_skills_lint_cases_private_policy_and_claims(self):
        reg=load_skills()
        self.assertEqual(len(reg.active()),40)
        self.assertEqual(skill_lint(reg,self.ops),[])
        self.assertEqual(skill_lint((FRONT_SECTIONS,FRONT_BANNER),self.ops,repo_root=REPO_ROOT),[])
        for skill in (FRONT_SECTIONS,FRONT_BANNER):
            self.assertEqual((skill.pack,skill.targets,skill.approval_class,skill.sandbox,skill.logs,skill.who),
                             ('front',('site',),'A1','preview',('fields',),'owner'))
            results=testkit.run_file(REPO_ROOT/skill.cases,testkit.registry_skills())
            self.assertEqual([(r.id,r.problems) for r in results if not r.ok],[])
        for name in ['store.set_sections','store.reset_sections','store.set_banner','store.clear_banner']:
            self.assertIn(name,live_policy.PRIVATE)
            self.assertNotIn(name,live_policy.LIVE)
        with self.assertRaises(SkillStop):
            plan_banner(BANNER|{'text':'Certified organic food'}, {'today':DAY,'texts':['Come say hello']})
        self.assertTrue(plan_banner(BANNER|{'text':'Certified organic food'}, {'today':DAY,'texts':['Certified organic food']}))


class UndoFrontTests(H06TestCase):
    def setUp(self):
        super().setUp()
        from hass.tests.test_conversation import _ops
        self.interp.mapping.update({
            'sections': _ops(('store.set_sections',{'order':['visit','market','newsletter','our-way'],'hidden':['our-way']})),
            'reset sections': _ops(('store.reset_sections',{})),
            'banner': _ops(('store.set_banner',BANNER)),
            'banner2': _ops(('store.set_banner',BANNER|{'text':'Hello neighbors'})),
            'clear banner': _ops(('store.clear_banner',{})),
        })

    def undo(self, draft):
        self.assertEqual(self.say('undo '+draft['code']),'proposed')
        self.replies()
        self.assertEqual(self.say('yes'),'approved')
        self.replies()

    def flow(self,first,second,key):
        original=self.content('store')
        initial={p:(self.repo.wt/p).read_bytes() for p in (INDEX,HIKE)}
        created=self.apply(first)
        value=self.content('store')[key]
        removed=self.apply(second)
        self.assertNotIn(key,self.content('store'))
        self.undo(removed)
        self.assertEqual(self.content('store')[key],value)
        self.undo(created)
        self.assertEqual(self.content('store'),original)
        self.assertEqual({p:(self.repo.wt/p).read_bytes() for p in (INDEX,HIKE)},initial)
        created=self.apply(first)
        self.apply('hours')
        hours=self.content('store')['hours']
        self.undo(created)
        original['hours']=hours
        self.assertEqual(self.content('store'),original)

    def test_sections_and_reset_undo_exact_state_keep_later_hours(self):
        self.flow('sections','reset sections','homeSections')

    def test_banner_and_clear_undo_exact_state_keep_later_hours(self):
        self.flow('banner','clear banner','banner')

    def test_later_same_key_value_refuses_undo(self):
        created=self.apply('banner')
        self.apply('banner2')
        self.assertEqual(self.say('undo '+created['code']),'not-drafted')
        self.assertEqual(self.content('store')['banner']['text'],'Hello neighbors')

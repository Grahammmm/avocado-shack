"""An owner turn cannot become confirmation without a specific durable ask."""
from datetime import timedelta
import unittest

from hass.npp.job import Plan
from hass.tests import test_npp_job as fixture


class AnswerTests(unittest.TestCase):
    @staticmethod
    def ask(case, *ids):
        original = []

        def plan(work):
            original.append(work)
            return Plan(questions=tuple((qid, 'Is that right?') for qid in ids))

        case.stages.plan = plan
        case.say('sell $7 each', photos=1)
        case.work()
        return original

    def new_job(self):
        case = fixture.JobTests()
        self.addCleanup(case.doCleanups)
        case.setUp()
        return case

    def test_answer_bound_to_provider_and_question_not_text(self):
        # Catch lost polarity, wrong answer binding and accidental cancellation of near-maker no.
        for qid, word, answer in [('duplicate', 'yes', True), ('near_maker', 'no', False), ('duplicate', 'no', False)]:
            with self.subTest(qid=qid, word=word):
                job = self.new_job()
                seen = self.ask(job, qid)
                job.say(word, pid='bound-turn')
                job.work()
                db = job.conv.db
                self.assertEqual(tuple(db.execute('SELECT qid, provider_id, answer FROM npp_answers').fetchone()),
                                 (qid, 'bound-turn', answer))
                self.assertEqual(db.execute('SELECT answered_by FROM npp_questions').fetchone()[0], 'bound-turn')
                if qid == 'duplicate' and not answer:
                    self.assertEqual(job.job()['state'], 'cancelled')
                    job.assert_unpublished()
                else:
                    self.assertNotEqual(job.job()['state'], 'cancelled')
                    self.assertEqual(seen[-1].answers, {qid: answer})
                    self.assertEqual(seen[-1].request['texts'], seen[0].request['texts'])

    def test_unbound_yes_preserves_guard_and_cannot_confirm(self):
        # Catch accidental binding without a unique, durable, causally prior yes/no ask.
        for case in ('unrelated', 'ambiguous', 'old-turn', 'missing-outbox', 'coded'):
            with self.subTest(case=case):
                job = self.new_job()
                ids = {'ambiguous': ('duplicate', 'near_maker'), 'unrelated': ('selling_price',)}.get(case, ('duplicate',))
                seen = self.ask(job, *ids)
                if case == 'missing-outbox':
                    job.conv.db.execute('UPDATE npp_questions SET asked_outbox_id=-1')
                    job.conv.db.commit()
                if case == 'coded':
                    job.yes(1)
                else:
                    job.say('yes', accepted=job.now - timedelta(seconds=2) if case == 'old-turn' else None)
                job.work()
                self.assertFalse(job.conv.db.execute('SELECT 1 FROM npp_answers').fetchall())
                self.assertEqual(seen[-1].answers, {})
                self.assertEqual(len(seen), 1)
                assert job.conv.npp is not None
                self.assertEqual(job.transport.texts[-1], job.conv.npp.replies['guards']['not_ready'])
                job.assert_unpublished()

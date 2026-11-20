"""An owner turn cannot become confirmation without a specific durable ask."""
from datetime import timedelta

import pytest

from hass.npp.job import Plan
from hass.tests import test_npp_job as fixture


@pytest.fixture
def job():
    case = fixture.JobTests()
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


def ask(case, *ids):
    original = []

    def plan(work):
        original.append(work)
        return Plan(questions=tuple((qid, 'Is that right?') for qid in ids))

    case.stages.plan = plan
    case.say('sell $7 each', photos=1)
    case.work()
    return original


@pytest.mark.parametrize(('qid', 'word', 'answer'), [('duplicate', 'yes', True), ('near_maker', 'no', False),
                                                     ('duplicate', 'no', False)])
def test_answer_bound_to_provider_and_question_not_text(job, qid, word, answer):
    seen = ask(job, qid)
    job.say(word, pid='bound-turn')
    job.work()
    db = job.conv.db
    assert tuple(db.execute('SELECT qid, provider_id, answer FROM npp_answers').fetchone()) == (qid, 'bound-turn', answer)
    assert db.execute('SELECT answered_by FROM npp_questions').fetchone()[0] == 'bound-turn'
    if qid == 'duplicate' and not answer:
        assert job.job()['state'] == 'cancelled'
        job.assert_unpublished()
    else:
        assert job.job()['state'] != 'cancelled'
        assert seen[-1].answers == {qid: answer}
        assert seen[-1].request['texts'] == seen[0].request['texts']


@pytest.mark.parametrize('case', ['unrelated', 'ambiguous', 'old-turn', 'missing-outbox', 'coded'])
def test_unbound_yes_preserves_guard_and_cannot_confirm(job, case):
    ids = {'ambiguous': ('duplicate', 'near_maker'), 'unrelated': ('selling_price',)}.get(case, ('duplicate',))
    seen = ask(job, *ids)
    if case == 'missing-outbox':
        job.conv.db.execute('UPDATE npp_questions SET asked_outbox_id=-1')
        job.conv.db.commit()
    if case == 'coded':
        job.yes(1)
    else:
        job.say('yes', accepted=job.now - timedelta(seconds=2) if case == 'old-turn' else None)
    job.work()
    assert not job.conv.db.execute('SELECT 1 FROM npp_answers').fetchall()
    assert seen[-1].answers == {}
    assert len(seen) == 1
    assert job.transport.texts[-1] == job.conv.npp.replies['guards']['not_ready']
    job.assert_unpublished()

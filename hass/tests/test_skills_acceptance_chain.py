"""Chain prerequisites: restore resolves hidden items only in its own skill; undo retains guest safety."""
import copy
import json
import unittest

from hass.skills import acceptance_run as A, load_skills


class Prerequisites(unittest.TestCase):
    def row(self, name):
        return copy.deepcopy(next(r for r in A.load_rows(A.DEFAULT_ROWS) if r['id'] == name))

    def test_restore_hidden_by_name_and_undo(self):
        r = A.run_row(self.row('primary-item-restore'), fixture_root=A.FIXTURE_ROOT, observe=True)
        self.assertEqual(r.codes, [])
        self.assertEqual(r.dispositions, ['proposed'])
        self.assertEqual(r.facts['undo'], 'identical')

    def test_hidden_stays_refused_for_edit_and_held_for_restore(self):
        r = self.row('primary-item-restore')
        r['skill'] = 'item.edit'
        r['texts'] = ['change the lemons description to: Bright fruit.']
        r['replies'] = [{'skill': 'item.edit', 'slots': {'item': 'lemons', 'description': 'Bright fruit.'}}]
        r['expect'] = {'skills': ['item.edit', 'none'], 'dispositions': ['refused'], 'reply_contains': ['hidden']}
        self.assertEqual(A.run_row(r, fixture_root=A.FIXTURE_ROOT).codes, [])
        r = self.row('acc-refuse-04')
        self.assertEqual(A.run_row(r, fixture_root=A.FIXTURE_ROOT).codes, [])

    def test_reschedule_undo_restores_exact_bytes(self):
        r = A.run_row(self.row('primary-hike-reschedule'), fixture_root=A.FIXTURE_ROOT)
        self.assertEqual(r.codes, [])
        self.assertEqual(r.facts['undo'], 'identical')

    def test_missing_guest_counts_still_refuses_reschedule_undo_without_write(self):
        r = self.row('primary-hike-reschedule')
        s = A.Session(r, load_skills(), A.FIXTURE_ROOT)
        self.addCleanup(s.close)
        self.assertEqual(s.say(r['texts'][0])[1], 'proposed')
        self.assertEqual(s.say('yes ' + s.drafts()[-1]['code'])[1], 'approved')
        # Remove the synthetic count source, not the production check.
        (s.repo.state / 'guests.sqlite3').unlink()
        before = s.snapshot()
        self.assertEqual(s.say('undo')[1], 'not-drafted')
        self.assertEqual(s.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

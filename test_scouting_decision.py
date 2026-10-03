"""Scouting mail must be a durable decision, not a cosmetic reminder."""
import copy
import unittest

import inseason_scouting as ISS
import views
from session import Session


class ScoutingDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = Session.new('GB', seed=633).save()

    def fresh(self):
        session = Session.load(self.initial)
        session.stop = ('week', 1)
        session.L.week = 1
        session.L.phase = 'regular'
        return session

    def test_email_blocks_until_two_distinct_choices_or_scout_decision(self):
        session = self.fresh()
        state = copy.deepcopy(session.rng.bit_generator.state)
        session._ensure_scout_focus()
        messages = [m for m in session.L.inbox if m.get('kind') == 'scouting_focus']
        self.assertEqual(len(messages), 1)
        mid = messages[0]['id']
        self.assertTrue(any(b['kind'] == 'scouting_focus' for b in session.blocking()))
        self.assertTrue(next(r for r in views._inbox(session.L, limit=None)['rows'] if r['id'] == mid)['block'])
        session.ROSTER_MAX, session.ROSTER_MIN = 100, 0
        self.assertIn('scouting priorities', session.advance()['why'])
        self.assertFalse(session.inbox_scout_focus(mid, group1='QB', group2='QB')['ok'])
        self.assertTrue(any(b['kind'] == 'scouting_focus' for b in session.blocking()))
        self.assertTrue(session.inbox_scout_focus(mid, use_scout=True)['ok'])
        self.assertFalse(any(b['kind'] == 'scouting_focus' for b in session.blocking()))
        self.assertEqual(state, session.rng.bit_generator.state)

    def test_resolved_cycle_survives_mail_delete_and_reload(self):
        session = self.fresh()
        session._ensure_scout_focus()
        mid = next(m['id'] for m in session.L.inbox if m.get('kind') == 'scouting_focus')
        self.assertTrue(session.inbox_scout_focus(mid, group1='QB', group2='Receivers')['ok'])
        session.L.inbox = [m for m in session.L.inbox if m['id'] != mid]
        session._ensure_scout_focus()
        self.assertFalse(any(m.get('kind') == 'scouting_focus' for m in session.L.inbox))
        loaded = Session.load(session.save())
        self.assertTrue(ISS.decision_resolved(loaded.L, 1))
        loaded._ensure_scout_focus()
        self.assertFalse(any(m.get('kind') == 'scouting_focus' for m in loaded.L.inbox))


if __name__ == '__main__':
    unittest.main()

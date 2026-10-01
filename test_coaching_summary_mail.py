import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import inbox as IB
import league_notes as LN


class CoachingSummaryMail(unittest.TestCase):
    def league(self):
        return NS(year=2027, week=0, phase='offseason', user_team='GB', players={},
                  inbox=[], notes_sent={}, transactions=[],
                  teams={a: NS(abbr=a, division='NFC North', gm=NS(name='Coach'), staff={})
                         for a in ('GB', 'MIN')})

    def tx(self, league, kind, **fields):
        league.transactions.append(dict(year=2027, phase='offseason', team='MIN', kind=kind, **fields))

    def test_all_moves_have_their_own_row_and_correct_labels(self):
        league = self.league()
        self.tx(league, 'fire', coach='Former Coach')
        self.tx(league, 'gm_change', hired='New Coach')
        self.tx(league, 'staff_out', name='Poor Coordinator', role='dc', why='unit bottom-eight two years running')
        self.tx(league, 'staff_out', name='Promoted Coordinator', role='oc', why='hired as head coach by GB')
        self.tx(league, 'staff_out', name='Departing Coordinator', role='st', why='contract up, walked')
        self.tx(league, 'staff_in', name='New Coordinator', role='dc', why='from the pool')
        self.tx(league, 'staff_retire', name='Retiring Scout', role='scout')
        self.tx(league, 'staff_extend', name='Kept Coach', role='oc')
        before = copy.deepcopy(league.transactions)
        msg = LN.coaching_summary(league)
        rows = IB.body_rows(league, msg)
        self.assertIn('Hired (2)', rows)
        self.assertIn('Fired / released / replaced (2)', rows)
        self.assertIn('Other departures (3)', rows)
        for name in ('Former Coach', 'New Coach', 'Poor Coordinator', 'Promoted Coordinator',
                     'Departing Coordinator', 'New Coordinator', 'Retiring Scout'):
            self.assertEqual(sum(name in row for row in rows), 1)
        self.assertTrue(any('Promoted Coordinator — Promoted' in row for row in rows))
        self.assertTrue(any('Head Scout — Retiring Scout — Retired' in row for row in rows))
        self.assertNotIn('Kept Coach', msg['body'])
        self.assertEqual(league.transactions, before)
        self.assertFalse(IB.is_decision(msg))
        self.assertEqual(msg['payload']['link'], 'league:transactions')

    def test_search_is_not_a_completed_hire_and_vacancies_remain_visible(self):
        league = self.league()
        league.teams['MIN'].gm = None
        league.teams['GB'].staff = {'dc': None}
        self.tx(league, 'gm_search', waiting_on='Potential Coach')
        rows = IB.body_rows(league, LN.coaching_summary(league))
        self.assertIn('Hired (0)', rows)
        self.assertIn('Jobs still open (2)', rows)
        self.assertIn('Minnesota — Head Coach', rows)
        self.assertIn('Green Bay — Defensive Coordinator', rows)
        self.assertFalse(any('Potential Coach' in row for row in rows))

    def test_only_this_offseason_and_no_duplicate_events(self):
        league = self.league()
        self.tx(league, 'staff_in', name='New Coordinator', role='dc')
        league.transactions.append(dict(league.transactions[0]))
        league.transactions.append(dict(year=2026, phase='offseason', team='MIN', kind='hire', coach='Last Year'))
        league.transactions.append(dict(year=2027, phase='regular', team='MIN', kind='fire', coach='In Season'))
        body = LN.coaching_summary(league)['body']
        self.assertEqual(body.count('New Coordinator'), 1)
        self.assertNotIn('Last Year', body)
        self.assertNotIn('In Season', body)

    def test_once_after_deletion_and_save_load(self):
        from league import League
        league = League(2027)
        LN.coaching_summary(league)
        league.inbox.clear()
        restored = League.load(league.save())
        self.assertIsNone(LN.coaching_summary(restored))
        self.assertFalse(restored.inbox)
        restored.year = 2028
        self.assertIsNotNone(LN.coaching_summary(restored))

    def test_step_posts_after_pending_hires_are_resolved(self):
        from session import Session
        league = self.league()
        session = NS(L=league, rng=None)
        def black_monday(clubs):
            self.tx(league, 'fire', coach='Outgoing Coach')
            self.tx(league, 'gm_search', waiting_on='Incoming Coach')
            return [('MIN', 'offense')]
        session._black_monday = black_monday
        def carousel(*args, **kwargs):
            self.assertEqual(kwargs['new_head_coaches'], ['MIN'])
            self.assertFalse(league.inbox)
            self.tx(league, 'gm_change', hired='Incoming Coach')
        with patch('staff.carousel', side_effect=carousel):
            Session.step_coaching(session)
        self.assertEqual(len(league.inbox), 1)
        self.assertIn('Outgoing Coach — Fired', league.inbox[0]['body'])
        self.assertIn('Incoming Coach — Hired', league.inbox[0]['body'])


if __name__ == '__main__': unittest.main()

"""Mailbox data stays complete; FA depth is local to each request."""
import copy
import unittest
from unittest.mock import patch

import numpy as np
from gm_engine import GM
from league import Team
from session import Session
from test_cap_accounting import fixture, player
import views
import views_personnel as VP


class PagePreparationTests(unittest.TestCase):
    def session(self):
        league = fixture()
        for team in league.teams.values():
            team.gm = GM()
        return Session(league, np.random.default_rng(91), 'GB')

    def test_mailbox_matches_full_portal_and_keeps_all_messages(self):
        session = self.session()
        session.L.inbox = [dict(id=i, subject=f'Report {i}', body='Report body',
                               kind='news', status='unread', year=2026, week=1)
                           for i in range(1, 31)]
        before = copy.deepcopy(session.rng.bit_generator.state)
        session.blocking()  # establish any roster notice before comparing views
        full = copy.deepcopy(session).portal_full()
        with patch.object(views, '_matchup', side_effect=AssertionError('No matchup needed')):
            focused = session.inbox_view()
        self.assertEqual(focused, {k: full[k] for k in ('rail', 'inbox')})
        self.assertGreaterEqual(len(focused['inbox']['rows']), 30)
        self.assertEqual(session.rng.bit_generator.state, before)
        session.inbox_read(30)
        after = session.inbox_view()
        self.assertFalse(next(r for r in after['inbox']['rows'] if r['id'] == 30)['unread'])
        self.assertEqual(after['rail']['inbox_unread'], after['inbox']['unread'])

    def test_fa_reuses_depth_but_refreshes_after_roster_changes(self):
        session = self.session()
        league = session.L
        league.set_phase('free_agency')
        for i in range(5):
            p = player(league, f'fa{i}', team=None)
            league.free_agents.append(p.pid)
        original = Team.depth.fget
        calls = []
        def counted(team):
            calls.append(team.abbr)
            return original(team)
        with patch.object(VP, 'rail', return_value={}), patch.object(Team, 'depth', property(counted)):
            first = VP.free_agency(session, league, 'GB')
            self.assertEqual(calls.count('GB'), 1)
            self.assertTrue(all('Only 0 healthy' in r['hole'] for r in first['rows']))
            player(league, 'starter')
            player(league, 'backup')
            calls.clear()
            second = VP.free_agency(session, league, 'GB')
            self.assertEqual(calls.count('GB'), 1)
            self.assertTrue(all(r['hole'] is None for r in second['rows']))


if __name__ == '__main__':
    unittest.main()

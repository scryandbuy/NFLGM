"""The FA board uses the buyer's defensive front for its position filters."""

import unittest
from unittest.mock import patch
from types import SimpleNamespace

from gm_engine import GM
from test_cap_accounting import fixture, player
import views_personnel as VP


class FreeAgencyPositionViewTests(unittest.TestCase):
    def test_position_filter_can_reach_players_beyond_global_top_300(self):
        league = fixture()
        league.user_team = 'GB'
        league.set_phase('free_agency')
        for i in range(305):
            p = player(league, f'free-{i}', team=None)
            p.pos = 'WR'
            league.free_agents.append(p.pid)
        tight_end = player(league, 'available-te', team=None)
        tight_end.pos = 'TE'
        league.free_agents.append(tight_end.pid)
        with patch.object(VP, 'rail', return_value={}):
            board = VP.free_agency(SimpleNamespace(user_team='GB'), league, 'GB')
        self.assertEqual(board['count'], 306)
        self.assertEqual(len(board['rows']), 306)
        self.assertEqual([r['pid'] for r in board['rows'] if r['pos'] == 'TE'],
                         ['available-te'])

    def test_edge_recruits_into_a_rush_olb_role_only_in_odd_front(self):
        league = fixture()
        league.user_team = 'GB'
        league.set_phase('free_agency')
        team = league.teams['GB']
        team.gm = GM(def_front='3-4')
        edge = player(league, 'edge', team=None)
        edge.pos = 'LEDG'
        league.free_agents.append(edge.pid)
        with patch.object(VP, 'rail', return_value={}):
            odd = VP.free_agency(SimpleNamespace(user_team='GB'), league, 'GB')
            self.assertEqual(odd['rows'][0]['display_pos'], 'LOLB')
            self.assertEqual(odd['rows'][0]['filter_positions'], ['LOLB', 'ROLB'])
            self.assertIn('LOLB', [p['key'] for group in odd['position_filters']
                                   for p in group['positions']])
            team.gm.def_front = '4-3'
            even = VP.free_agency(SimpleNamespace(user_team='GB'), league, 'GB')
        self.assertEqual(even['rows'][0]['display_pos'], 'LEDG')
        self.assertIn('LEDG', even['rows'][0]['filter_positions'])
        self.assertNotIn('LOLB', even['rows'][0]['filter_positions'])


if __name__ == '__main__':
    unittest.main()

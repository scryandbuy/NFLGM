"""Later cuts stay claimable without adding another offseason calendar stop."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import waivers as WV
import practice_squad as PS
import franchise as F
from test_waiver_cap_claim import fixture


class SingleCutdownWindowTests(unittest.TestCase):
    def test_processing_opening_snapshot_leaves_later_cut_for_next_cycle(self):
        league, team, _, _, first = fixture(10)
        league.user_team = 'GB'
        later = copy.deepcopy(first); later.pid = 'later-cut'
        league.players[later.pid] = later
        opening = list(league.waivers)
        entry = dict(pid=later.pid, from_team='MIN', claims=[], user_notified=False, year=league.year, week=0)
        league.waivers.append(entry)
        with patch.object(WV, 'priority', return_value=['GB']), \
             patch('valuation.pool_from_league', return_value=None), \
             patch('valuation.value_player', return_value={'value': 1}):
            WV.process(league, np.random.default_rng(1), 0, entries=opening)
            self.assertEqual(league.waivers, [entry])
            self.assertIsNotNone(later.contract)
            WV.process(league, np.random.default_rng(1), 1)
        self.assertEqual(league.waivers, [])
        self.assertIsNone(later.contract)

    def test_squad_filling_and_rookie_cleanup_preserve_pending_claim(self):
        league, team, _, _, player = fixture(10)
        player.entry_year = league.year; player.draft_round = None
        league.free_agents = [player.pid]
        entry = copy.deepcopy(league.waivers[0])
        PS.fill_squads(league, np.random.default_rng(1))
        with patch('specialist_reserve.ensure'):
            F.clear_undrafted(league, np.random.default_rng(1), keep=0)
        self.assertEqual(league.waivers, [entry])
        self.assertIsNone(player.team)
        self.assertFalse(player.retired)
        self.assertIn(player.pid, league.free_agents)

    def test_batch_calendar_also_runs_only_one_claim_cycle(self):
        league, _, _, _, _ = fixture(10)
        new = dict(pid='later-cut', claims=[], user_notified=False)
        calls = []
        def repair(*_):
            calls.append(1)
            if len(calls) == 2: league.waivers.append(new)
            return [], 0
        def process(*_, entries):
            for entry in entries: league.waivers.remove(entry)
            return []
        with patch.object(F.CD, 'finalize', side_effect=repair), \
             patch.object(F.CD, 'violations', return_value=[]), \
             patch.object(WV, 'notify_user'), patch.object(WV, 'process', side_effect=process) as award:
            F.settle_final_rosters(league, np.random.default_rng(1))
        self.assertEqual(award.call_count, 1)
        self.assertEqual(league.waivers, [new])


if __name__ == '__main__':
    unittest.main()

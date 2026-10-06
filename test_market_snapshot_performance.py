"""Market reads reuse only one request's evidence, without changing prices."""
import copy
import unittest
from unittest.mock import patch

import pandas as pd
import valuation as VAL
from test_draft_planning import fixture


class MarketSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.league, self.team = fixture()
        self.league.stats[self.league.year] = {
            p.pid: dict(snaps=130 + i, pass_yds=200 + i * 3,
                        pass_td=i % 4, ints=i % 3, rush_yds=i * 7,
                        rec_yds=i * 5, sacks=i % 6, tackles=i * 2,
                        pb_snaps=160 + i, pb_wins=120 + i,
                        rb_snaps=100 + i, rb_wins=70 + i,
                        sacks_allowed=i % 4, pressures_allowed=i % 7)
            for i, p in enumerate(self.league.players.values())}
        # Enough same-position peers for real percentiles, including ties.
        for pos in ('WR', 'LT', 'QB'):
            original = self.team.by_pos(pos)[0]
            for i in range(8):
                p = copy.deepcopy(original); p.pid = f'extra-{pos}-{i}'
                p.name = p.pid; p.retired = i == 7
                self.league.players[p.pid] = p
                self.league.stats[self.league.year][p.pid] = dict(
                    self.league.stats[self.league.year][original.pid])
        self.league.stats[self.league.year]['WR1']['snaps'] = 1
        self.league.stats[self.league.year]['LT1']['pb_snaps'] = 1

    def unshared_pool(self):
        original = VAL.live_production
        def unshared(league, player, season=None, **kwargs):
            return original(league, player, season)
        with patch.object(VAL, 'live_production', side_effect=unshared):
            return VAL.pool_from_league(self.league)

    def test_pool_matches_independent_player_reads(self):
        before = copy.deepcopy(self.league.stats)
        expected = self.unshared_pool()
        actual = VAL.pool_from_league(self.league)
        pd.testing.assert_frame_equal(actual, expected, check_exact=True)
        self.assertEqual(before, self.league.stats)

    def test_next_read_uses_new_stats_and_player_positions(self):
        before = VAL.pool_from_league(self.league)
        self.league.stats[self.league.year]['WR0']['rec_yds'] += 10000
        self.league.player('extra-WR-0').pos = 'TE'
        self.league.player('extra-WR-1').retired = True
        after = VAL.pool_from_league(self.league)
        pd.testing.assert_frame_equal(after, self.unshared_pool(), check_exact=True)
        self.assertFalse(before.equals(after))

    def test_historical_season_and_missing_lines(self):
        self.league.stats[self.league.year - 1] = copy.deepcopy(
            self.league.stats[self.league.year])
        del self.league.stats[self.league.year - 1]['WR0']
        peers = {}
        for p in self.league.players.values():
            self.assertEqual(VAL.live_production(self.league, p, self.league.year - 1),
                             VAL.live_production(self.league, p, self.league.year - 1,
                                                 peers_by_position=peers))


if __name__ == '__main__': unittest.main()

"""Street quotes reuse comps only while their source snapshot is unchanged."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import trades as TR
import valuation as VAL

class StreetPoolTests(unittest.TestCase):
    def test_one_pool_per_table_and_fresh_after_roster_release(self):
        players = {str(i): SimpleNamespace(pid=str(i), pos='WR', ovr=80-i,
                    ratings={}, retired=False) for i in range(6)}
        league = SimpleNamespace(year=2026, week=7, free_agents=list(players)[:5],
                                 player=players.get)
        viewer = SimpleNamespace()
        snapshots = [object(), object()]
        seen = []
        def quote(league, player, side, rng, pool):
            self.assertEqual(side, 'agent'); self.assertIsNone(rng)
            seen.append(pool)
            return {'apy': 2.5}
        with patch.object(VAL, 'pool_from_league', side_effect=snapshots) as build, \
             patch.object(VAL, 'value_player', side_effect=quote), \
             patch('gm_engine.scheme_fit', return_value=0), \
             patch('practice_squad.squad', return_value=[]):
            self.assertEqual(TR._street_alternative(league, viewer, players['0']), (80, 2.5))
            TR._street_alternative(league, viewer, players['1'])
            self.assertEqual(build.call_count, 1)
            self.assertEqual(seen, [snapshots[0]] * 4)
            # A completed trade may release a player and change the comp market.
            league.free_agents.append('5')
            TR._street_alternative(league, viewer, players['0'])
            self.assertEqual(build.call_count, 2)
            self.assertEqual(seen[4:], [snapshots[1]] * 4)

if __name__ == '__main__': unittest.main()

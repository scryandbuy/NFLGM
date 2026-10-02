"""Role-specific ratings must reach the live game, with bounded effects."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import events as E
import game as G
import plays as P
import rosters as R
import schemes as S


class RemainingAttributeTests(unittest.TestCase):
    def test_scramble_pursuit_and_neutral_context(self):
        for seed in range(100):
            def result(defenders):
                return E.resolve_scramble({'pid': 'Q'}, defenders, 80,
                                          np.random.default_rng(seed), P.rate)
            self.assertEqual(result([]), result([{'pid': 'D'}]))
            for attr in ('speed_rating', 'pursuit_rating', 'tackle_rating'):
                low = result([{'pid': 'D', attr: 20}])['yards']
                high = result([{'pid': 'D', attr: 99}])['yards']
                self.assertGreaterEqual(low, high)
            defender = {'pid': 'D', 'pursuit_rating': 99}
            self.assertEqual(result([defender]), result([defender, defender]))
            self.assertLessEqual(result([defender])['yards'], 80)

    def test_zone_catch_uses_zone_contest(self):
        class Fixed:
            def random(self): return .5
        for attr in ('zone_cover_rating', 'jump_rating', 'tackle_rating'):
            self.assertTrue(P.resolve_catch({}, {attr: 20}, True, Fixed(), in_man=False))
            self.assertFalse(P.resolve_catch({}, {attr: 99}, True, Fixed(), in_man=False))
        for attr in ('man_cover_rating', 'press_rating'):
            for seed in range(50):
                self.assertEqual(P.resolve_catch({}, {attr: 20}, True, np.random.default_rng(seed), in_man=False),
                                 P.resolve_catch({}, {attr: 99}, True, np.random.default_rng(seed), in_man=False))
        for seed in range(100):
            self.assertEqual(P.resolve_catch({}, {}, True, np.random.default_rng(seed)),
                             P.resolve_catch({}, {}, True, np.random.default_rng(seed), in_man=False))

    def test_lineman_can_limit_scramble_from_pursuit(self):
        def yards(rating):
            defenders = [{'pid': 'edge', 'pos': 'LEDG', 'pursuit_rating': rating,
                          'speed_rating': rating, 'tackle_rating': rating},
                         {'pid': 'corner', 'pos': 'CB'}]
            return sum(E.resolve_scramble({'pid': 'Q'}, defenders, 80,
                       np.random.default_rng(seed), P.rate)['yards'] for seed in range(100))
        self.assertLess(yards(99), yards(20))

    def test_kickoff_neutral_and_skill_effects(self):
        def kick(kicker, seed):
            return G.kickoff({}, np.random.default_rng(seed), P.rate, kicker=kicker)
        for seed in range(100):
            self.assertEqual(kick(None, seed), kick({}, seed))
        for attr in ('kick_power_rating', 'kick_acc_rating'):
            low = [kick({attr: 20}, s) for s in range(1000)]
            high = [kick({attr: 99}, s) for s in range(1000)]
            self.assertGreater(sum(x.get('touchback', False) for x in high),
                               sum(x.get('touchback', False) for x in low))
            self.assertTrue(all(0 <= x['new_yardline'] <= 100 for x in low + high))

    def test_live_game_supplies_players_and_coverage(self):
        league = R.load_league()
        co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(d, di, sd, ytg, r, secs_left=secs_left, **kw)
        cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(oc, d, di, r, yards_to_endzone=ytg, **kw)
        with patch.object(E, 'resolve_scramble', wraps=E.resolve_scramble) as scramble, \
             patch.object(P, 'resolve_catch', wraps=P.resolve_catch) as catch, \
             patch.object(G, 'kickoff', wraps=G.kickoff) as kickoff:
            for seed in range(4):
                G.play_game(copy.deepcopy(league['GB']), copy.deepcopy(league['DEN']),
                            np.random.default_rng(800 + seed), P.resolve_play, co, cd, P.rate, week=1)
        self.assertGreater(scramble.call_count, 0)
        self.assertTrue(all(c.args[1] for c in scramble.call_args_list))
        self.assertTrue(all(any(p.get('pos') in ('DT', 'LEDG', 'REDG', 'LE', 'RE')
                                for p in c.args[1]) for c in scramble.call_args_list))
        self.assertEqual({bool(c.kwargs['in_man']) for c in catch.call_args_list}, {True, False})
        self.assertTrue(all(c.kwargs['kicker'].get('pid') for c in kickoff.call_args_list))


if __name__ == '__main__':
    unittest.main()

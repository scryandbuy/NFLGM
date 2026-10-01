"""Conversion intent must reach reads and routes without guaranteeing a gain."""
import unittest
from collections import Counter
from unittest.mock import patch

import numpy as np
import game as G
import plays as P
import playcall as PC
import rosters as R
import schemes as S
import targets as T


class FourthDownRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.teams = R.load_league()

    def play(self, seed, need=16, down=4, depth='short', concept='curl_flat', rushers=4):
        rng = np.random.default_rng(seed)
        oc = dict(is_pass=True, personnel='11', depth=depth, concept=concept,
                  down=down, ydstogo=need, play_action=False, shotgun=True,
                  protection_pref='empty')
        dc = S.call_defense(oc, down, need, rng, yards_to_endzone=16)
        dc.update(rushers=rushers, blitzers=max(0, rushers - 4), sim_pressure=False)
        return P._pass_play(self.teams['GB'], self.teams['DEN'], oc, dc, 16, rng)

    def test_leading_team_still_calls_for_conversion_on_fourth(self):
        for lead in (-14, -5, 5, 14):
            self.assertEqual(PC.pick_job(4, 16, 30, lead, 40, np.random.default_rng(1)), 'chains')
        self.assertEqual(PC.pick_job(4, 25, 40, 5, 40, np.random.default_rng(1)), 'explosive')
        self.assertEqual(PC.pick_job(3, 16, 30, 5, 40, np.random.default_rng(1)), 'clock')

    def test_depth_is_set_before_protection_not_after_completion(self):
        for down, expected in ((1, 'short'), (2, 'short'), (3, 'short'), (4, 'medium')):
            with patch.object(S, 'choose_protection', wraps=S.choose_protection) as protection:
                self.play(1, down=down)
            self.assertEqual(protection.call_args.args[2], expected)

    def test_reads_favor_conversion_route_but_keep_pressure_outlet(self):
        pairs = [dict(receiver=dict(pid='wr', pos='WR'), defender={}, separation=.42, route_air=17),
                 dict(receiver=dict(pid='hb', pos='HB'), defender={}, separation=.9, route_air=2.6)]
        counts = []
        for pressure in (0, 1):
            rng = np.random.default_rng(7)
            selected = [T.select_target(pairs, {}, 'dagger', rng, lambda *a: .8,
                        down=4, ydstogo=16, pressure=pressure) for _ in range(800)]
            counts.append(Counter((r[0]['pid'], r[2]) for r in selected))
        protected_outlets = sum(n for (pid, _), n in counts[0].items() if pid == 'hb')
        self.assertGreater(protected_outlets, 0)
        self.assertLess(protected_outlets, 240)
        self.assertGreater(sum(n for (_, kind), n in counts[1].items() if kind == 'checkdown'),
                           sum(n for (_, kind), n in counts[0].items() if kind == 'checkdown'))

    def test_earlier_down_target_choices_ignore_conversion_metadata(self):
        pairs = [dict(receiver=dict(pid=str(i), pos='WR'), defender={}, separation=.3 + i * .2,
                      route_air=2 + i * 10) for i in range(3)]
        for down in (1, 2, 3):
            for seed in range(30):
                a = T.select_target(pairs, {}, 'dagger', np.random.default_rng(seed), lambda *a: .8)
                b = T.select_target(pairs, {}, 'dagger', np.random.default_rng(seed), lambda *a: .8,
                                    down=down, ydstogo=16, pressure=1)
                self.assertEqual(a, b)

    def test_actual_passes_retain_stops_incompletions_sacks_and_interceptions(self):
        plays = [self.play(seed) for seed in range(250)]
        kinds = Counter(p['type'] for p in plays)
        for kind in ('complete', 'incomplete', 'sack', 'interception', 'drop'):
            self.assertGreater(kinds[kind], 0)
        complete = [p for p in plays if p['type'] == 'complete']
        self.assertTrue(any(p['yards'] < 16 for p in complete))
        self.assertTrue(any(p['touchdown'] for p in complete))
        for p in complete:
            self.assertAlmostEqual(p['yards'], p['air'] + p['yac'], delta=.11)
        # The drive layer still ends a failed conversion; it cannot award the
        # required distance merely because a fourth-down pass was completed.
        stopped = next(p for p in complete if p['yards'] < 15)
        dr = G.Drive({}, {}, 16, 38, 4, -5, None)
        dr.down, dr.togo = 4, 16
        self.assertFalse(G._advance(dr, stopped['yards']))
        self.assertEqual(dr.down, 5)

    def test_explicit_screens_and_blitz_hot_routes_stay_short(self):
        screens = [self.play(seed, concept='screen') for seed in range(60)]
        self.assertTrue(any(p['type'] == 'complete' and p['air'] < 0 for p in screens))
        self.assertTrue(all(p.get('depth') == 'short' for p in screens))
        hot = [self.play(seed, rushers=7) for seed in range(100)]
        self.assertTrue(any(p['type'] == 'complete' and p['yards'] < 16 for p in hot))
        self.assertTrue(any(p.get('depth') == 'short' and p.get('pressured') for p in hot))

    def test_failed_catch_does_not_receive_conversion_yards(self):
        with patch.object(P, 'resolve_catch', return_value=False):
            outcomes = [self.play(seed) for seed in range(40)]
        self.assertTrue(any(p['type'] == 'drop' for p in outcomes))
        self.assertFalse(any(p['type'] == 'complete' or p.get('touchdown') for p in outcomes))

    def test_yards_needed_reaches_receiver_routes_before_throw(self):
        for need in (3, 11, 16):
            captured = []
            original = T.select_target
            def read(pairs, *args, **kwargs):
                captured.extend(dict(p) for p in pairs)
                return original(pairs, *args, **kwargs)
            with patch.object(T, 'select_target', side_effect=read):
                for seed in range(20):
                    self.play(seed, need=need, depth='medium')
                    if captured: break
            primary = [p for p in captured if p['receiver'].get('pos') not in ('HB', 'FB')
                       and not p.get('late')]
            self.assertTrue(primary)
            self.assertTrue(all(p['route_air'] >= need for p in primary))
            self.assertTrue(all(p['route_air'] <= 18 for p in primary))


if __name__ == '__main__':
    unittest.main()

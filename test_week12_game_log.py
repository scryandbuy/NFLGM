"""GB-LA Week 12: urgency, conversion calls, and punt spot accounting."""
import unittest
import re
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import game
import schemes
import playcall
import ticker
import test_game_clock_decisions as clocks


class Week12Log(unittest.TestCase):
    def test_multi_score_urgency_preserves_other_situations(self):
        for seconds, margin, quarter, urgent in (
            (390, -9, 4, True), (391, -9, 4, False),
            (540, -21, 4, True), (541, -21, 4, False),
            (690, -28, 4, True), (691, -28, 4, False),
            (60, -8, 4, False), (60, 14, 4, False),
            (60, -21, 2, False), (0, -21, 4, False)):
            with self.subTest(seconds=seconds, margin=margin, quarter=quarter):
                self.assertEqual(game.multi_score_urgency(seconds, margin, quarter), urgent)
        for result in ('complete', 'sack', 'scramble', 'run'):
            self.assertEqual(game.play_seconds(result, hurry=True, urgent=True), 14)
            self.assertEqual(game.play_seconds(result, hurry=True, urgent=True, timeout=True), 6)
            self.assertGreater(game.play_seconds(result, hurry=True), 14)

    def test_live_and_batch_drives_keep_multi_score_pace(self):
        helper = clocks.ClockDecisions()
        helper.setUp()
        for live in (False, True):
            with self.subTest(live=live):
                dr, _, _ = helper.drive(
                    [dict(type='scramble', yards=1), dict(type='complete', yards=19),
                     dict(type='incomplete', yards=0)],
                    start=20, clock=120, quarter=4, wall=None, diff=-21,
                    own=0, other=0, live=live)
                snaps = [p for p in dr.log if p.get('down')]
                self.assertEqual([p['clock'] for p in snaps], [120, 106])
                self.assertEqual(dr.result, 'Touchdown')
                self.assertEqual(dr.clock, 100)

    def test_fourth_down_screen_frequency_tracks_conversion_distance(self):
        counts = {}
        with patch.object(schemes, 'pass_rate', return_value=1):
            for distance in (2, 5, 10, 16):
                rng = np.random.default_rng(12)
                calls = [schemes.call_offense(4, distance, -7, 60, rng)
                         for _ in range(2500)]
                counts[distance] = sum(c['concept'] == 'screen' for c in calls)
        self.assertGreater(counts[2], 80)
        self.assertGreater(counts[5], 0)
        self.assertLess(counts[5], counts[2] * .3)
        self.assertLess(counts[10], counts[2] * .15)
        self.assertEqual(counts[16], 0)

    def test_pressure_concept_and_audible_cannot_bypass_screen_choice(self):
        off = dict(qb=None)
        rng = np.random.default_rng(12)
        for _ in range(100):
            self.assertNotEqual(playcall.call_pass(off, 'protect', lambda *a: .7,
                rng, pressure_risk=.9, allow_screen=False), 'screen')
        with patch.object(playcall, 'read_the_look', return_value=dict(
                looks_heavy=True, looks_light=False, looks_man=False)):
            for _ in range(100):
                call, _ = playcall.audible(dict(is_pass=True, concept='mesh', allow_screen=False),
                    {}, off, lambda *a: .7, rng, latitude=100)
                self.assertNotEqual(call['concept'], 'screen')

    def test_punt_narration_reconciles_to_receiving_spot(self):
        league = SimpleNamespace(player=lambda pid: None)
        rng = np.random.default_rng(12)
        kinds = set()
        for i in range(1000):
            origin = 35 + (i % 61)
            punt = game.punt(origin, {}, {}, rng, lambda *a: .7)
            if punt.get('blocked') or punt.get('touchback'):
                continue
            kinds.add(punt['how'])
            self.assertEqual(origin - punt['display_gross'] + punt['display_ret'],
                             100 - ticker._field_round(punt['new_yardline']))
            text = ticker.play_line(league, punt, 'GB', 'LA')['text']
            gross = int(re.search(r'Punt, (\d+) yards', text)[1])
            returned = re.search(r'returned (\d+) yard', text)
            ret = int(returned[1]) if returned else 0
            self.assertEqual(origin - gross + ret,
                             100 - ticker._spot_yards(punt['new_yardline']))
            if punt['how'] == 'fair_catch':
                self.assertEqual(ret, 0)
            if punt['how'] == 'return':
                if punt['ret']:
                    self.assertIn(f"returned {ret} yard", text)
        self.assertEqual(kinds, {'return', 'fair_catch', 'downed'})

    def test_legacy_punt_logs_still_render(self):
        text = ticker.play_line(SimpleNamespace(player=lambda pid: None),
            dict(type='punt', gross=48.4, ret=7.9, how='return', new_yardline=79), 'GB', 'LA')['text']
        self.assertIn('Punt, 48 yards, returned 8 yards', text)


if __name__ == '__main__':
    unittest.main()

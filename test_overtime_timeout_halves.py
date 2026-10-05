"""Playoff OT timeout halves through the real, bounded overtime driver.

2026 NFL Rule 16-1-4(g): three team timeouts per overtime half.
Rule 4-5-4 Note 2: the previous excess injury timeout must be in that half.
https://static.www.nfl.com/image/upload/fl_attachment/league/tqivdkzt9mu6wdgsh1ku.pdf
Only possessions are stubbed; timeout spending and injury administration are real.
"""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import game as G


class OvertimeTimeoutHalves(unittest.TestCase):
    def setUp(self):
        G.LAST_KICKOFF.clear()

    def five_periods(self, action, *, live=False):
        """One finite possession per period; the fifth ends with a winning FG."""
        entries = []

        def drive(*args, **kw):
            period = len(entries) + 1
            self.assertLessEqual(period, 5, 'bounded fixture must finish in OT5')
            tos = kw['timeouts']
            entry = dict(period=period, raw_quarter=args[4],
                         clock_period=kw['clock_period'], clock=args[3],
                         pos=kw['pos'], left=dict(tos.left),
                         prior_excess=dict(getattr(tos, 'injury_excess', {})))
            entries.append(entry)
            action(period, tos, kw, entry)
            return NS(result='Field goal' if period == 5 else 'Punt',
                      points=3 if period == 5 else 0,
                      clock=800 if period == 5 else 0,
                      yardline=50, next_yardline=65, down=2, togo=8,
                      log=[], plays=3)

        def live_drive(*args, **kw):
            result = drive(*args, **kw)
            yield ('snap', result)
            return result

        with patch.object(G, 'kickoff_for', return_value={
                'new_yardline': 65, 'touchback': True}), \
             patch.object(G, 'run_drive', side_effect=drive), \
             patch.object(G, 'drive_steps', side_effect=live_drive):
            gen = G.overtime_steps({}, {}, dict(home=20, away=20),
                np.random.default_rng(23), None, None, None, lambda *a: .7,
                playoffs=True, first='away', live=live)
            while True:
                try:
                    next(gen)
                except StopIteration as done:
                    score, drives, ending = done.value
                    break
        self.assertEqual(len(drives), 5)
        self.assertEqual(score, dict(home=20, away=23))
        self.assertEqual(ending, 'decided')
        self.assertEqual([e['raw_quarter'] for e in entries], [5] * 5)
        self.assertEqual([e['clock_period'] for e in entries], [1, 2, 3, 4, 1])
        self.assertEqual([e['clock'] for e in entries], [900] * 5)
        return entries

    @staticmethod
    def spend(period, tos, kw, entry):
        # Leave 2/1 after each half's first period, exhaust in its second.
        attempts = (1, 2) if period in (1, 3) else (2, 1)
        entry['used'] = {side: [tos.use(side) for _ in range(count)]
                         for side, count in zip(('home', 'away'), attempts)}

    def test_ot1_to_ot2_preserves_used_timeouts(self):
        for live in (False, True):
            with self.subTest(live=live):
                entries = self.five_periods(self.spend, live=live)
                self.assertEqual(entries[0]['left'], dict(home=3, away=3))
                self.assertEqual(entries[1]['left'], dict(home=2, away=1))

    def test_ot3_and_ot5_restore_legal_timeout_opportunities(self):
        for live in (False, True):
            with self.subTest(live=live):
                entries = self.five_periods(self.spend, live=live)
                for index in (2, 4):
                    with self.subTest(period=index + 1):
                        # Actual use must succeed: retaining zero inventory
                        # wrongly denies a timeout, beyond a metadata mismatch.
                        self.assertTrue(entries[index]['used']['home'][0])
                        self.assertTrue(entries[index]['used']['away'][0])
                        self.assertEqual(entries[index]['left'], dict(home=3, away=3))

    def test_ot3_to_ot4_preserves_used_timeouts(self):
        def spend_third(period, tos, kw, entry):
            if period == 3:
                self.assertTrue(tos.use('home'))
                self.assertTrue(tos.use('away'))
        for live in (False, True):
            with self.subTest(live=live):
                entries = self.five_periods(spend_third, live=live)
                self.assertEqual(entries[3]['left'], dict(home=2, away=2))

    def test_prior_half_excess_does_not_create_new_half_five_yard_penalty(self):
        def injuries(period, tos, kw, entry):
            if period not in (2, 4):
                return
            pos = kw['pos']  # Same team in OT2 and OT4, raw quarter always 5.
            while tos.use(pos):
                pass
            spots = []
            for _ in range(2):
                dr = NS(quarter=5, clock_period=kw['clock_period'],
                        _two_min=True, result=None, clock=30, yardline=50.,
                        togo=8., down=2, first_downs=0, score_diff=0, log=[])
                self.assertTrue(G._injury_timeout(dr, [{'side': 'off'}],
                    dict(type='incomplete', yards=0), tos, pos, None, 30))
                spots.append((dr.yardline, [x.get('penalty') for x in dr.log
                                           if x['type'] == 'penalty']))
            entry['injury_spots'] = spots
        for live in (False, True):
            with self.subTest(live=live):
                entries = self.five_periods(injuries, live=live)
                # First excess in EACH half is unpenalized; a second excess
                # in that same half still has the existing five-yard cost.
                self.assertEqual(entries[1]['injury_spots'],
                                 [(50., []), (55., ['Delay of Game'])])
                self.assertEqual(entries[3]['injury_spots'],
                                 [(50., []), (55., ['Delay of Game'])])
                self.assertEqual(entries[2]['prior_excess'], {})
                self.assertEqual(entries[4]['prior_excess'], {})


if __name__ == '__main__':
    unittest.main()

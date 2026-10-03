"""Regressions from the GB–ARI Week 10 play log."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np

import events
import game
import ticker


class Week10GameLogTests(unittest.TestCase):
    def test_last_first_half_fourth_and_long_takes_reachable_kick(self):
        for draw in (0.0, 0.999999):
            decision = game.fourth_down_decision(
                21, 10, -4, 1809, NS(random=lambda: draw),
                half_seconds_left=9)
            self.assertEqual(decision, 'field_goal')

    def test_failed_fourth_down_does_not_spend_offensive_timeout(self):
        offense = dict(qb=dict(pid='qb', pos='QB'), rb=dict(pid='rb', pos='HB'),
                       wr=[dict(pid='wr', pos='WR')], te=[], ol=[], p={}, k={})
        defense = dict(db=[], lb=[], dl=[])
        outcomes = iter([dict(type='incomplete', yards=0)] * 3 +
                        [dict(type='sack', yards=-3)])
        timeouts = game.Timeouts()
        timeouts.left = dict(home=1, away=0)
        game.LAST_KICKOFF.clear()
        with patch.object(events, 'penalty_check', return_value=None), \
             patch.object(events, 'fumble_check', return_value=None), \
             patch.object(game, 'field_units', side_effect=lambda roster, *a, **k: (roster, {})), \
             patch.object(game, 'fourth_down_decision', return_value='go'), \
             patch.object(game, 'end_of_half_plan', return_value=None), \
             patch('playcall.audible', side_effect=lambda oc, *a, **k: (oc, None)):
            drive = game.run_drive(
                offense, defense, 21, 1833, 2, -4, np.random.default_rng(2),
                lambda *a: next(outcomes),
                lambda *a, **k: dict(is_pass=True, personnel='11', depth='short'),
                lambda *a, **k: dict(personnel='nickel', front_family='4-3'),
                lambda *a: .7, timeouts=timeouts, half_end=1800)
        self.assertEqual(drive.result, 'Turnover on downs')
        self.assertEqual(timeouts.left['home'], 1)
        self.assertFalse(any(play['type'] == 'timeout' for play in drive.log))

    def test_fractional_goal_and_play_text_read_consistently(self):
        names = {'qb': 'Michael Penix Jr.', 'beaten': 'Jager Burton Jr.'}
        league = NS(player=lambda pid: NS(name=names[pid]) if pid in names else None)
        td = ticker.play_line(league, dict(type='complete', passer='qb', yards=.3,
                                           touchdown=True, yardline=.3), 'GB', 'ARI')['text']
        self.assertIn('touchdown', td.lower())
        self.assertIn('inside the 1', td)
        self.assertNotIn('no gain', td)
        short = ticker.play_line(league, dict(type='run', yards=1.9,
                                              yardline=2.3), 'GB', 'ARI')['text']
        self.assertIn('to inside the 1', short)
        self.assertNotIn('for 2 yards', short)
        sack = ticker.play_line(league, dict(type='sack', passer='qb', beaten='beaten',
                                             yards=-.2), 'GB', 'ARI')['text']
        self.assertIn('at the line of scrimmage', sack)
        self.assertNotIn('Jr..', sack)
        pressure = ticker.play_line(league, dict(type='complete', passer='qb',
                                                 pressured=True, yards=5), 'GB', 'ARI')['text']
        self.assertNotIn('Jr..', pressure)
        punt = ticker.play_line(league, dict(type='punt', gross=48, ret=1,
                                             how='return'), 'GB', 'ARI')['text']
        self.assertIn('returned 1 yard.', punt)


if __name__ == '__main__':
    unittest.main()

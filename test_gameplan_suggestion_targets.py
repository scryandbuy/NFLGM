"""Manual plan edits must not move the assistant's independent reference."""
import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import gameplan as GP
import gameplan_week as GW
import views_gameplan as V


class SuggestionTargets(unittest.TestCase):
    def setUp(self):
        self.base = GP.Gameplan()
        self.league = NS(year=2029, user_week_plan=None, player=lambda pid: None,
            teams={'GB': NS(staff={}, active=lambda: []), 'MIN': NS(depth={'WR': []})})
        self.session = NS(stop=('week', 1), runner=None, played=False,
                          _opponent=lambda week: ('MIN', False))
        self.report = dict(coach={}, protection_choice=dict(value='half_slide', why='Matchup'),
            suggestions=[dict(side=side, text='Advice '+key, why='Matchup', changes={key: .05})
                         for side, key, *_ in V.LEANS])
        for target, name, value in ((V, 'rail', {}), (V, '_base_plan', self.base),
                                    (GW, 'opponent_report', self.report)):
            p = patch.object(target, name, return_value=value)
            p.start(); self.addCleanup(p.stop)

    def view(self):
        return V.this_week(self.session, self.league, 'GB')

    def advice(self):
        v = self.view()
        return ([(r['key'], r['ghost'], r['ghost_word']) for r in v['leans']],
                [s['target'] for s in v['suggestions']])

    def test_every_slider_moves_user_value_only_at_both_extremes(self):
        original = self.advice()
        for lean in self.view()['leans']:
            for value in (lean['min'], lean['max']):
                with self.subTest(key=lean['key'], value=value):
                    V.act_set_lean(self.session, self.league, 'GB', lean['key'], value)
                    current = next(r for r in self.view()['leans'] if r['key'] == lean['key'])
                    self.assertAlmostEqual(current['value'], value, places=3)
                    self.assertEqual(self.advice(), original)

    def test_accept_skip_undo_save_reload_and_reopen_keep_reference(self):
        original = self.advice()
        for action, args in ((V.act_take, (0,)), (V.act_skip, (1,)),
                             (V.act_untake, (0,)), (V.act_take, (0,))):
            action(self.session, self.league, 'GB', *args)
            self.assertEqual(self.advice(), original)
        V.act_set_decision(self.session, self.league, 'GB', 'protection', 'half_slide')
        V.act_save(self.session, self.league, 'GB')
        self.league.user_week_plan = json.loads(json.dumps(self.league.user_week_plan))
        self.assertEqual(self.advice(), original)
        V.act_reopen(self.session, self.league, 'GB')
        V.act_reset(self.session, self.league, 'GB')
        self.assertEqual(self.advice(), original)

    def test_apply_marker_matches_engine_without_moving_advice(self):
        original = self.advice()
        for lean in self.view()['leans']:
            V.act_set_lean(self.session, self.league, 'GB', lean['key'], lean['ghost'])
            applied = GW.apply_changes(self.base.copy(), self.base, self.league.user_week_plan['changes'])
            self.assertAlmostEqual(getattr(applied, lean['key']), lean['ghost'], places=3)
        self.assertEqual(self.advice(), original)

    def test_stacked_advice_clamps_to_same_limits_as_actual_plan(self):
        self.base.blitz_rate = .98
        self.report['suggestions'] = [dict(side='defence', text=f'Pressure {i}', why='Matchup',
                                           changes={'blitz_rate': .08}) for i in range(2)]
        before = copy.deepcopy(self.base.__dict__)
        lean = next(r for r in self.view()['leans'] if r['key'] == 'blitz_rate')
        self.assertEqual(lean['ghost'], 1.)
        V.act_take(self.session, self.league, 'GB', 0)
        self.assertEqual(next(r for r in self.view()['leans'] if r['key'] == 'blitz_rate')['ghost'], 1.)
        self.assertEqual(self.base.__dict__, before)


if __name__ == '__main__':
    unittest.main()

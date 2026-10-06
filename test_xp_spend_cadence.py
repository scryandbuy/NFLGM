"""CPU spending cadence preserves earnings, savings, and user control."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
from league import Player
import targets as TG
import xp_spend as XS


def fixture():
    def player(pid):
        return Player(pid, pid, 'WR', 23,
                      {key: 70.0 for key in TG.DEPTH_WEIGHTS['WR']},
                      potential=95)
    cpu, auto, manual = (player(pid) for pid in ('cpu', 'auto', 'manual'))
    XS.set_auto(auto)
    gm = NS(dev_belief=.5, patience=.5)
    league = NS(year=2027, teams={
        'CPU': NS(gm=gm, roster=[cpu], record=(0, 0, 0)),
        'USER': NS(gm=gm, roster=[auto, manual], record=(0, 0, 0)),
    })
    return league, cpu, auto, manual


class XPSpendingCadenceTests(unittest.TestCase):
    def test_cpu_schedule_includes_playoffs_and_user_auto_remains_weekly(self):
        league, cpu, auto, manual = fixture()
        rng = np.random.default_rng(1)
        with patch.object(XS, 'spend_player', return_value=[]) as spend:
            for week in range(1, 23):
                spend.reset_mock()
                XS.spend_week(league, week, rng, user_team='USER')
                expected = ([] if week == 9 else ['cpu', 'auto']
                            if week in (3, 6, 10, 12, 15, 18, 21) else ['auto'])
                self.assertEqual([c.args[0].pid for c in spend.call_args_list], expected)
                for call in spend.call_args_list:
                    self.assertEqual(call.kwargs['year'], 2027)
                    self.assertEqual(call.kwargs['source'],
                                     'AI' if call.args[0] is cpu else 'Assistant')
        for p in (cpu, auto, manual):
            self.assertEqual(p.xp_spent['_weeks'], 22)

    def test_deadline_banks_xp_and_following_week_spends_after_reload(self):
        league, cpu, auto, manual = fixture()
        rng = np.random.default_rng(41)
        for p in (cpu, auto, manual): p.xp = 30000
        state = copy.deepcopy(rng.bit_generator.state)
        self.assertEqual(XS.spend_week(league, 9, rng, user_team='USER'), {})
        self.assertEqual(rng.bit_generator.state, state)
        for p in (cpu, auto, manual):
            self.assertEqual(p.xp, 30000)
            self.assertEqual(p.ovr, 70)
            self.assertEqual(p.xp_spent['_weeks'], 1)
        league = copy.deepcopy(league)
        spent = XS.spend_week(league, 10, rng, user_team='USER')
        self.assertIn('cpu', spent)
        self.assertIn('auto', spent)
        self.assertNotIn('manual', spent)
        self.assertLess(league.teams['CPU'].roster[0].xp, 30000)
        self.assertEqual(league.teams['USER'].roster[1].xp, 30000)

    def test_xp_accumulates_then_real_purchases_spend_the_bank(self):
        league, cpu, _, _ = fixture()
        rng = np.random.default_rng(2)
        before_rng = copy.deepcopy(rng.bit_generator.state)
        before_ratings = dict(cpu.ratings)
        for week in (1, 2):
            cpu.xp += 10000
            cpu.xp_spent['_earned'] = {'game': week * 10000}
            self.assertEqual(XS.spend_week(league, week, rng), {})
            self.assertEqual(cpu.xp, week * 10000)
            self.assertEqual(cpu.ratings, before_ratings)
            self.assertEqual(rng.bit_generator.state, before_rng)
            self.assertEqual(XS._weekly_rate(cpu), 10000)
        cpu.xp += 10000
        actions = XS.spend_week(league, 3, rng)
        self.assertIn('cpu', actions)
        self.assertLess(cpu.xp, 30000)
        self.assertGreater(cpu.ovr, 70)

    def test_saved_physical_target_survives_skipped_weeks_and_state_copy(self):
        league, cpu, _, _ = fixture()
        cpu.xp = 10000
        cpu.xp_spent['_saving_for'] = 'speed_rating'
        rng = np.random.default_rng(3)
        XS.spend_week(league, 1, rng)
        # Cadence depends on the league week, not new transient runtime state.
        restored = copy.deepcopy(league)
        XS.spend_week(restored, 2, rng)
        saved = restored.teams['CPU'].roster[0]
        self.assertEqual(saved.xp, 10000)
        self.assertEqual(saved.xp_spent['_saving_for'], 'speed_rating')
        with patch.object(XS, 'spend_player', return_value=[]) as spend:
            XS.spend_week(restored, 3, rng)
            self.assertIn(saved, [c.args[0] for c in spend.call_args_list])

    def test_new_season_does_not_spend_early_and_retired_players_are_skipped(self):
        league, cpu, _, _ = fixture()
        rng = np.random.default_rng(4)
        with patch.object(XS, 'spend_player', return_value=[]) as spend:
            for week in (0, 1, 2):
                XS.spend_week(league, week, rng)
            spend.assert_not_called()
            cpu.retired = True
            previous_weeks = cpu.xp_spent['_weeks']
            XS.spend_week(league, 3, rng)
            self.assertNotIn(cpu, [c.args[0] for c in spend.call_args_list])
            self.assertEqual(cpu.xp_spent['_weeks'], previous_weeks)


if __name__ == '__main__':
    unittest.main()

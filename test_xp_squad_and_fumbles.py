"""Squad development uses ordinary spending rules; turnovers reduce event XP."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import health as H
import practice as PR
import targets as TG
import xp as XP
import xp_spend as XS
from game import StatBook
from league import Player


def player(pid='reserve', pos='RG', potential=90):
    return Player(pid, pid, pos, 22,
                  dict({key: 70. for key in TG.DEPTH_WEIGHTS[pos]},
                       injury_rating=80., tough_rating=80.),
                  potential=potential, team='A', entry_year=2028)


def fixture(*squad):
    team = NS(abbr='A', roster=[], practice_squad=list(squad), depth={},
              gm=NS(dev_belief=.5, patience=.5), record=(0, 0, 0))
    return NS(year=2028, teams={'A': team}), team


class SquadXPTests(unittest.TestCase):
    def test_real_practice_earnings_become_purchases_on_cpu_cadence(self):
        p = player()
        league, team = fixture(p)
        runner = NS(states={'A': NS(cond=H.Condition(), jaded={}, last_snaps={},
                                  snaps={}, out=set())},
                    desks={}, rng=np.random.default_rng(17))
        rng = np.random.default_rng(18)
        q = {'units': {u: {'intensity': 'standard', 'reps': 'development'}
                       for u in PR.UNITS}, 'focus': [p.pid]}
        with patch.object(PR, 'BASE_INJURY_RISK', 0):
            for week in range(1, 7):
                PR.resolve(league, runner, 'A', week, q)
                bank, ratings = p.xp, dict(p.ratings)
                actions = XS.spend_week(league, week, rng)
                if week % 3:
                    self.assertEqual(actions, {})
                    self.assertEqual((p.xp, p.ratings), (bank, ratings))
        buys = p.xp_spent.get('_purchases', [])
        self.assertTrue(buys)
        self.assertTrue(all(x['week'] in (3, 6) and x['source'] == 'AI' for x in buys))
        self.assertGreater(p.xp_spent['_earned']['practice'], 0)
        self.assertGreater(p.ovr, 70)
        self.assertEqual(p.xp_spent['_weeks'], 6)
        self.assertEqual(team.roster, [])
        self.assertEqual(team.practice_squad, [p])

    def test_squad_ceiling_stops_saving_target_until_unlock_is_affordable(self):
        p = player(potential=70)
        league, _ = fixture(p)
        p.xp_spent['_saving_for'] = 'strength_rating'
        p.xp = XP.unlock_cost(p) - 1
        ratings = dict(p.ratings)
        XS.spend_week(league, 3, np.random.default_rng(2))
        self.assertEqual(p.ratings, ratings)
        self.assertEqual(p.potential, 70)
        self.assertFalse(p.xp_spent.get('_purchases'))
        p.xp += 5001
        XS.spend_week(league, 6, np.random.default_rng(2))
        purchases = p.xp_spent['_purchases']
        self.assertEqual(purchases[0]['kind'], 'unlock')
        self.assertTrue(any(x['kind'] == 'buy' for x in purchases))
        self.assertGreater(p.potential, 70)
        self.assertLessEqual(p.ovr, p.potential)

    def test_user_squad_auto_toggle_is_weekly_and_manual_balance_is_preserved(self):
        auto, manual = player('auto'), player('manual')
        league, _ = fixture(auto, manual)
        auto.xp = manual.xp = 10000
        XS.set_auto(auto)
        before_manual = copy.deepcopy(manual.xp_spent)
        actions = XS.spend_week(league, 1, np.random.default_rng(3), user_team='A')
        self.assertIn(auto.pid, actions)
        self.assertNotIn(manual.pid, actions)
        self.assertLess(auto.xp, 10000)
        self.assertEqual(manual.xp, 10000)
        self.assertEqual(manual.xp_spent, dict(before_manual, _weeks=1))
        self.assertTrue(all(x['source'] == 'Assistant' for x in auto.xp_spent['_purchases']))
        XS.set_auto(auto, False)
        before = (auto.xp, dict(auto.ratings))
        XS.spend_week(league, 2, np.random.default_rng(3), user_team='A')
        self.assertEqual((auto.xp, auto.ratings), before)

    def test_duplicate_membership_spends_and_counts_once_retired_is_skipped(self):
        p, retired = player(), player('retired')
        p.xp = retired.xp = 10000
        retired.retired = True
        league, team = fixture(p, p, retired)
        team.roster = [p]
        control = copy.deepcopy(league)
        control.teams['A'].practice_squad = []
        expected = XS.spend_week(control, 3, np.random.default_rng(4))
        actual = XS.spend_week(league, 3, np.random.default_rng(4))
        self.assertEqual(actual, expected)
        self.assertEqual(p.xp_spent['_weeks'], 1)
        self.assertEqual(p.xp, control.teams['A'].roster[0].xp)
        self.assertEqual(retired.xp, 10000)
        self.assertEqual(retired.xp_spent, {})

    def test_te_squad_spending_uses_existing_role_selection(self):
        p = player(pos='TE')
        league, team = fixture(p)
        p.xp = 10000
        import offense_roles as OR
        with patch.object(OR, 'te_development_role', wraps=OR.te_development_role) as role:
            XS.spend_week(league, 3, np.random.default_rng(6))
        self.assertTrue(role.called)
        self.assertTrue(all(c.args == (p, team) for c in role.call_args_list))
        self.assertTrue(p.xp_spent.get('_purchases'))


class FumbleXPTests(unittest.TestCase):
    def test_canonical_legacy_and_mixed_lines_pay_each_penalty_once(self):
        cases = [
            ({'fumbles': 2, 'fumbles_lost': 1}, -260),
            ({'fum': 2, 'fum_lost': 1}, -260),
            ({'fumbles': 2, 'fum': 7, 'fumbles_lost': 1, 'fum_lost': 8}, -260),
            ({'fumbles': 0, 'fum': 7, 'fumbles_lost': 0, 'fum_lost': 8}, 0),
            ({'fumbles': 1, 'fum_lost': 1}, -200),
            ({'fum': 1, 'fumbles_lost': 1}, -200),
        ]
        for line, expected in cases:
            with self.subTest(line=line):
                before = dict(line)
                self.assertEqual(XP.event_xp(line), expected)
                self.assertEqual(line, before)

    def test_recorded_fumble_reduces_real_game_credit_without_alias_double_charge(self):
        p = player(pos='HB')
        book = StatBook()
        book.record_fumble({'fumble_by': p.pid, 'fumble_lost': True})
        line = dict(book.p[p.pid], rush_att=10, rush_yds=45)
        clean = dict(line, fumbles=0, fumbles_lost=0)
        dirty_player, clean_player = copy.deepcopy(p), copy.deepcopy(p)
        dirty = XP.credit(dirty_player, XP.game_xp(dirty_player, line, 2028), 'game')
        ordinary = XP.credit(clean_player, XP.game_xp(clean_player, clean, 2028), 'game')
        expected_penalty = XP.credit(copy.deepcopy(p),
            200 * (1 + XP.PERFORMANCE_BONUS[p.dev] * XP.learning_relief(p)) * XP.modifier(p), 'game')
        self.assertAlmostEqual(ordinary - dirty, expected_penalty)
        self.assertAlmostEqual(dirty_player.xp_spent['_earned']['game'], dirty)
        self.assertEqual(XP.event_xp(book.p[p.pid]), -200)


if __name__ == '__main__':
    unittest.main()

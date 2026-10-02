"""An older player can earn a bridge deal without an automatic age veto."""
import unittest
from unittest.mock import patch

import numpy as np
import extensions as EXT
import retention_plan as RP
from cap_engine import Contract
from test_draft_planning import fixture, set_grade


def veteran_club(age=33.5, grade=85.945, replacement=55., youth=.5):
    L, t = fixture()
    L.set_phase('offseason'); t.picks = []; t.cap.cap = 500.; t.gm.youth = youth
    p = L.player('LT0'); p.contract = None; p.age = age
    set_grade(p, grade); set_grade(L.player('LT1'), replacement); t.sync_cap()
    return L, t, p


QUOTE = dict(ask=17.7, offer=17.7, years=1, discount=.07)


class VeteranRetentionTests(unittest.TestCase):
    def assess(self, L, t, p, quote=None, window='middling'):
        with patch.object(EXT, 'terms', return_value=quote or QUOTE), \
             patch.object(RP.TE, 'window', return_value=window):
            return RP.assess(L, t, p)

    def test_old_starting_tackle_gets_candidate_review_and_real_one_year_deal(self):
        # Controlled Ronald Rodgers-like profile; audit had him affordable but
        # skipped outright at age >33. Not an exact league replay.
        for age in (33.5, 35.5):
            with self.subTest(age=age):
                L, t, p = veteran_club(age=age)
                self.assertIn(p.pid, [q.pid for q, _ in RP.candidates(L, t)])
                plan = self.assess(L, t, p)
                self.assertTrue(plan['affordable'])
                self.assertEqual(plan['decision'], 'retain')
                self.assertIn('short_term_veteran', plan['reasons'])
                with patch.object(EXT, 'terms', return_value=QUOTE):
                    result = EXT.ai_round(L, np.random.default_rng(313))
                self.assertIn(p.name, [r[1] for r in result])
                self.assertEqual(p.contract.years, 1)

    def test_youth_preference_changes_decision_when_a_successor_is_ready(self):
        decisions = []
        for youth in (.2, .8):
            L, t, p = veteran_club(grade=85., replacement=78., youth=youth)
            row = self.assess(L, t, p)
            self.assertTrue(row['affordable'])
            decisions.append(row['decision'])
        self.assertEqual(decisions, ['retain', 'let_walk'])

    def test_team_window_changes_bridge_choice(self):
        L, t, p = veteran_club(grade=85., replacement=79., youth=.5)
        self.assertEqual(self.assess(L, t, p, window='win_now')['decision'], 'retain')
        self.assertEqual(self.assess(L, t, p, window='rebuilding')['decision'], 'let_walk')

    def test_decline_price_and_budget_each_can_prevent_extension(self):
        L, t, p = veteran_club(age=37., grade=76., replacement=72.)
        row = self.assess(L, t, p)
        self.assertEqual(row['decision'], 'let_walk')
        self.assertIn('prefer_veteran_replacement', row['reasons'])
        L, t, p = veteran_club()
        row = self.assess(L, t, p, dict(QUOTE, ask=45., offer=10.))
        self.assertEqual(row['decision'], 'let_walk')
        self.assertIn('price_gap', row['reasons'])
        t.cap.cap = 50.; t.sync_cap()
        row = self.assess(L, t, p)
        self.assertFalse(row['affordable'])
        self.assertEqual(row['decision'], 'let_walk')

    def test_pursuit_uses_short_term_and_keeps_agent_acceptance(self):
        L, t, p = veteran_club(youth=.8)
        long_ask = dict(QUOTE, years=5)
        with patch.object(EXT, 'terms', return_value=long_ask), \
             patch.object(EXT, 'negotiate_ai', wraps=EXT.negotiate_ai) as negotiate:
            row = RP.assess(L, t, p)
            result = EXT._pursue_retention(L, t, p, np.random.default_rng(313))
        self.assertEqual(row['years'], 1)
        self.assertEqual(negotiate.call_args.args[2:4], (17.7, 1))
        self.assertEqual(result['result'], 'countered')
        self.assertIsNone(p.contract)

    def test_good_veteran_can_get_two_years_but_no_long_term_commitment(self):
        L, t, p = veteran_club(youth=.2)
        row = self.assess(L, t, p, dict(QUOTE, years=4))
        self.assertEqual(row['years'], 2)
        p.contract = Contract(2, [1., 1.])
        later = self.assess(L, t, p, dict(QUOTE, years=4))
        self.assertLess(later['veteran_projected_grade'], row['veteran_projected_grade'])
        self.assertLessEqual(later['years'], 2)

    def test_keep_for_current_run_does_not_authorize_bad_veteran_extension(self):
        L, t, p = veteran_club(age=37., grade=76., replacement=72.)
        p.contract = Contract(1, [1.]); L.set_phase('regular'); L.week = 8
        with patch.object(EXT, 'terms', return_value=QUOTE), \
             patch.object(RP.TE, 'window', return_value='win_now'), \
             patch.object(EXT, 'negotiate_ai', wraps=EXT.negotiate_ai) as negotiate:
            result = EXT._pursue_retention(L, t, p, np.random.default_rng(313))
        self.assertEqual(result['result'], 'refused')
        negotiate.assert_not_called()
        self.assertEqual(p.contract.years, 1)

    def test_closed_agent_and_hidden_longevity_do_not_get_overridden(self):
        L, t, p = veteran_club()
        before = L.save()
        low = self.assess(L, t, p)
        self.assertEqual(L.save(), before)
        p.longevity = 2.0
        high = self.assess(L, t, p)
        self.assertEqual(low, high)
        L.negotiations = [dict(pid=p.pid, team=t.abbr, kind='extension', state='declined')]
        with patch.object(EXT, 'terms', return_value=QUOTE):
            result = EXT._pursue_retention(L, t, p, np.random.default_rng(313))
        self.assertEqual(result['result'], 'refused')
        self.assertIsNone(p.contract)

    def test_successor_is_projected_over_the_same_horizon(self):
        L, t, p = veteran_club(replacement=80.)
        L.player('LT1').age = 36.
        one = self.assess(L, t, p)
        self.assertLess(one['veteran_projected_replacement'], 80.)
        p.contract = Contract(2, [1., 1.])
        later = self.assess(L, t, p)
        self.assertLess(later['veteran_projected_replacement'], one['veteran_projected_replacement'])


if __name__ == '__main__':
    unittest.main()

"""Season-opening recovery uses real ability, consent and funded contracts."""
import unittest
from unittest.mock import patch

import cutdown as CD
import roster_needs as RN
from cap_engine import Contract
import test_cutdown_kicker as kicker_tests
import test_roster_cap_recovery as recovery_tests


class FinalRosterRecoveryTests(unittest.TestCase):
    def test_missing_center_can_train_own_surplus_with_normal_tax(self):
        league, team = recovery_tests.RecoveryTests.roster(self)
        for center in team.by_pos('C'): center.pos = 'LT'
        report = RN.assess(team)
        native = {r['player'].pid: r['player'].pos for r in report['assignments']
                  if r['player'] is not None and r['role'] == r['player'].pos}
        ids = {p.pid for p in team.active()}
        ratings = {p.pid: dict(p.ratings) for p in team.active()}
        self.assertTrue(CD._cross_train_line(league, team, RN.assess(team)))
        self.assertEqual({p.pid for p in team.active()}, ids)
        self.assertEqual({p.pid: p.ratings for p in team.active()}, ratings)
        self.assertTrue(all(league.player(pid).pos == pos for pid, pos in native.items()))
        self.assertFalse(CD.violations(league))
        changed = [p for p in team.active() if p.transition]
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0].pos, 'C')
        self.assertGreater(changed[0].transition['penalty'], 0)
        self.assertFalse(CD._cross_train_line(league, team, RN.assess(team)))

    def test_recovery_never_moves_user_linemen(self):
        league, team = recovery_tests.RecoveryTests.roster(self)
        team.by_pos('C')[0].pos = 'LT'; league.user_team = team.abbr
        before = league.save()
        self.assertFalse(CD._cross_train_line(league, team, RN.assess(team)))
        self.assertEqual(league.save(), before)

    def market_fixture(self):
        helper = kicker_tests.KickerRecoveryTests()
        league, team = helper.fixture()
        kicker = helper.punter(league, team, pid='paid-kicker'); kicker.pos = 'K'
        punter = helper.punter(league, team, pid='paid-punter')
        return league, team, kicker, punter

    def test_native_kicker_gets_actual_ask_and_only_one_funded_departure(self):
        league, team, kicker, punter = self.market_fixture()
        ask = dict(accepts=False, reason='seeking_market_contract', annual_offer=1.3, annual_ask=2.3)
        with patch('replacement_contracts.minimum_acceptance', return_value=ask):
            self.assertTrue(CD._market_kicker_recovery(league, team, RN.assess(team)))
        self.assertEqual(kicker.team, team.abbr)
        self.assertAlmostEqual(kicker.contract.base[0], 2.3)
        self.assertIsNone(punter.team)
        self.assertFalse(CD.violations(league))
        self.assertEqual(len([r for r in league.transactions if r['kind'] == 'release']), 1)

    def test_paid_punter_conversion_requires_real_kicking_skills(self):
        league, team, kicker, punter = self.market_fixture()
        kicker.retired = True
        ratings = dict(punter.ratings)
        ask = dict(accepts=False, reason='seeking_market_contract', annual_offer=1.3, annual_ask=2.3)
        with patch('replacement_contracts.minimum_acceptance', return_value=ask):
            self.assertTrue(CD._market_kicker_recovery(league, team, RN.assess(team)))
        self.assertEqual(punter.pos, 'K')
        self.assertEqual(punter.ratings, ratings)
        self.assertGreater(punter.transition['penalty'], 0)
        self.assertFalse(CD.violations(league))

    def test_rejected_recovery_does_not_release_or_change_anyone(self):
        for reason in ('unfunded', 'recent_release', 'unqualified'):
            league, team, kicker, punter = self.market_fixture()
            ask = dict(accepts=False, reason='seeking_market_contract', annual_offer=1.3, annual_ask=2.3)
            if reason == 'unfunded':
                for p in team.active(): p.contract = Contract(1, [.1])
                team.sync_cap(); team.cap.cap = team.cap.charges(team.phase)
            elif reason == 'recent_release':
                ask = dict(accepts=False, reason='recent_release')
            else:
                kicker.retired = True
                punter.ratings['kick_acc_rating'] = 40
            before = league.save()
            with patch('replacement_contracts.minimum_acceptance', return_value=ask):
                self.assertFalse(CD._market_kicker_recovery(league, team, RN.assess(team)))
            self.assertEqual(league.save(), before)


if __name__ == '__main__':
    unittest.main()

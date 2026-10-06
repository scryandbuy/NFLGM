"""Discounted annual quotes cannot undercut the floor; late pay stays prorated."""
import copy
import unittest
from unittest.mock import patch, PropertyMock

import fa_demand as FD
import min_salary as MS
import market as MK
import negotiations as NG
import contract_offer as CO
import league_notes as LN
from cap_engine import CAP, Contract
from gm_engine import GM
from league import League
from test_cap_accounting import fixture, player


class VeteranMinimumTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture(); self.L.user_team = 'GB'; self.L.week = 17
        for t in self.L.teams.values():
            t.gm = GM(); t.cap.paid_week = 16
        self.p = player(self.L, 'veteran', team=None)
        self.p.accrued = 8
        self.L.free_agents.append(self.p.pid)

    def test_discount_stops_at_each_experience_floor_and_keeps_market_above_it(self):
        for accrued in (0, 1, 2, 3, 5, 8):
            self.p.accrued = accrued
            floor = MS.player_minimum(self.L, self.p)
            for week in range(1, 19):
                self.L.week = week
                self.assertEqual(FD.asking(self.L, self.p, .01), floor)
                self.assertGreaterEqual(MS.minimum_quote(self.L, self.p, floor), floor)
            self.assertAlmostEqual(FD.asking(self.L, self.p, 20), round(20 * .95 ** 17, 3))

    def test_saved_ask_and_counter_repaired_even_without_week_change(self):
        t = dict(id=1, pid=self.p.pid, kind='fa_inseason', state='countered',
                 ask=.3, years=1, counter=dict(apy=.3, years=1),
                 unsigned_factor=FD.factor(self.L, self.p))
        self.L.negotiations = [t]
        NG._threads(self.L)
        floor = MS.player_minimum(self.L, self.p)
        self.assertGreaterEqual(t['ask'], floor)
        self.assertGreaterEqual(t['counter']['apy'], floor)
        before = copy.deepcopy(t)
        NG._threads(self.L)
        self.assertEqual(before, t)

    def test_below_minimum_rejected_before_signing_or_negotiation_changes(self):
        t = dict(id=1, pid=self.p.pid, team='GB', kind='fa_inseason', state='open',
                 ask=3., years=1, offers=[], patience=3, counter=None)
        self.L.negotiations = [t]
        result = NG.make_offer(self.L, 1, .3, 1)
        self.assertFalse(result['ok']); self.assertIn('Annual salary', result['why'])
        self.assertEqual(t['offers'], []); self.assertEqual(t['patience'], 3)
        with self.assertRaisesRegex(ValueError, 'Annual salary'):
            MK.signing_terms(self.L, self.p, self.L.teams['GB'], .3, 1, CAP[2026])
        self.assertIsNone(self.p.team)

    def test_reference_discounts_cannot_lower_minimum(self):
        floor = MS.player_minimum(self.L, self.p)
        offer = dict(apy=floor, years=1, bonus=0, front_load=.5)
        result = CO.assess(self.L, self.p, self.L.teams['GB'], offer, floor * .8, 1, 'fa_inseason')
        self.assertEqual(result['reference_package']['apy'], floor)
        self.assertAlmostEqual(result['reference_package']['bonus'], 0)

    def test_old_pending_offer_reopens_without_changing_user_price(self):
        t = dict(id=1, pid=self.p.pid, team='GB', kind='fa_inseason', state='waiting',
                 ask=.3, years=1, offers=[dict(apy=.3, years=1, bonus=0)], due=18)
        self.L.negotiations = [t]
        NG._threads(self.L)
        self.assertEqual(t['state'], 'open')
        self.assertIsNone(t['due'])
        self.assertEqual(t['offers'][-1]['apy'], .3)
        self.assertIsNone(self.p.team)

    def test_old_counter_keeps_bonus_without_spending_base_minimum(self):
        t = dict(id=1, pid=self.p.pid, team='GB', kind='fa_inseason', state='countered',
                 ask=.3, years=1, offers=[], counter=dict(apy=.3, years=1, bonus=.1),
                 unsigned_factor=FD.factor(self.L, self.p))
        self.L.negotiations = [t]
        NG._threads(self.L)
        st = MK.signing_terms(self.L, self.p, self.L.teams['GB'], t['counter']['apy'], 1,
                              CAP[2026], bonus=t['counter']['bonus'])
        self.assertAlmostEqual(st['signing_bonus'], .1)
        self.assertGreaterEqual(st['base'][0], MS.player_minimum(self.L, self.p) * st['fraction'])

    def test_counter_search_stays_above_floor(self):
        floor = MS.player_minimum(self.L, self.p)
        t = dict(kind='fa_inseason', team='GB', ask=2., years=1)
        offer = dict(apy=2., years=1, bonus=0, front_load=.5, promises=[])
        with patch('staff.recruit_pull', return_value=(1.5, .9)):
            result = NG._counter_package(self.L, self.p, t, offer)
        self.assertGreaterEqual(result['apy'], floor)

    def test_week17_signing_logs_annual_rate_and_remaining_cash(self):
        annual = MS.minimum_quote(self.L, self.p, .01)
        offer = MK.Offer('MIN', self.p.pid, annual, 1, [], bonus=0, front_load=.5)
        MK.sign(self.L, self.p, offer, CAP[2026], market_apy=annual)
        tx = self.L.transactions[-1]
        self.assertEqual(tx['apy'], annual)
        self.assertEqual(tx['cash_this_season'], round(annual * 2 / 18, 3))
        self.assertLess(tx['cash_this_season'], MS.player_minimum(self.L, self.p))
        with patch.object(type(self.p), 'ovr', new_callable=PropertyMock, return_value=90):
            LN.transactions(self.L, 17)
        body = self.L.inbox[-1]['body']
        self.assertIn(f'${annual:.2f}m a year', body)
        self.assertIn('for the rest of this season', body)
        self.assertNotIn('1 years', body)
        loaded = League.load(self.L.save())
        self.assertEqual(loaded.transactions[-1]['apy'], annual)

    def test_direct_minimum_signing_log_annualizes_prorated_pay(self):
        floor = MS.player_minimum(self.L, self.p)
        self.L.sign(self.p.pid, 'GB', Contract(1, [floor], signed=2026))
        self.assertAlmostEqual(self.L.transactions[-1]['apy'], floor)

    def test_minimum_uses_contract_start_year(self):
        self.L.set_phase('offseason'); self.L.season_closed_year = 2026
        self.L.cap_history = {2026:301.2, 2027:330.}
        self.assertEqual(MS.player_minimum(self.L, self.p), MS.minimum_salary(8, 330.))

    def test_default_bonus_and_payment_shape_preserve_every_base_floor(self):
        self.L.set_phase('free_agency')
        self.p.accrued = 3
        for shape in (0., .5, 1.):
            annual = MS.minimum_quote(self.L, self.p, .01, 3)
            st = MK.signing_terms(self.L, self.p, self.L.teams['GB'], annual, 3, CAP[2026], shape)
            self.assertAlmostEqual(sum(st['base']) + st['signing_bonus'], annual * 3, places=3)
            for base, floor in zip(st['base'], MS.contract_minima(self.L, self.p, 3)):
                self.assertGreaterEqual(base + 1e-9, floor)

    def test_explicit_bonus_cannot_consume_minimum_and_cpu_can_decline(self):
        floor = MS.player_minimum(self.L, self.p)
        with self.assertRaisesRegex(ValueError, 'minimum base salaries'):
            MK.signing_terms(self.L, self.p, self.L.teams['GB'], floor, 1, CAP[2026], bonus=.1)
        offer = MK.Offer('MIN', self.p.pid, .3, 1, [])
        decision = MK.acquisition_read(self.L, self.L.teams['MIN'], self.p, offer, 8., 3.)
        self.assertFalse(decision['approved'])
        self.assertEqual(offer.apy, .3)  # Never silently increase a GM's spending.


if __name__ == '__main__': unittest.main()

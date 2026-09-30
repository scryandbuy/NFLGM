import collections
import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import numpy as np
import contract_terms as CT
import extensions as EXT
import market
import negotiations as NG
import negotiation_engine as NE
from cap_engine import Contract
from test_cap_accounting import fixture, player


class ContractTermTests(unittest.TestCase):
    def specimen(self, pid, pos='WR', age=26, ovr=90, left=0):
        return N(pid=pid, pos=pos, age=age, ovr=ovr, traits={}, contract=Contract(left, [1]*left))

    def test_core_free_agents_have_real_term_variety_not_rounded_mean(self):
        counts = collections.Counter(CT.preferred_years(self.specimen(str(i)), 2026, 24, 301.2, comp_years=3)
                                     for i in range(400))
        self.assertTrue({1, 2, 3, 4, 5}.issubset(counts))
        self.assertGreater(counts[4] + counts[5], 130)
        self.assertLess(counts[4] + counts[5], 300)

    def test_elite_qb_extensions_include_six_seven_but_older_backs_do_not(self):
        years = [CT.preferred_years(self.specimen(str(i), 'QB', left=1), 2026, 50, 301.2, extension=True)
                 for i in range(300)]
        self.assertIn(6, years)
        self.assertIn(7, years)
        for i in range(100):
            p = self.specimen(str(i), 'HB', age=30, left=1)
            self.assertEqual(CT.preferred_years(p, 2026, 14, 301.2, extension=True), 1)

    def test_old_elite_te_can_seek_four_years_and_minimum_vets_stay_short(self):
        years = [CT.preferred_years(self.specimen(str(i), 'TE', age=31, left=1), 2026, 24, 301.2, extension=True)
                 for i in range(200)]
        self.assertIn(4, years)
        self.assertLessEqual(max(years), 4)
        cheap = [CT.preferred_years(self.specimen(str(i), ovr=65), 2026, 1.2, 301.2) for i in range(200)]
        self.assertGreater(cheap.count(1), 120)
        self.assertLessEqual(max(cheap), 3)

    def test_reading_terms_is_stable_across_reload_future_years_and_rng(self):
        p = self.specimen('unchanged', left=1)
        before = copy.deepcopy(p.__dict__)
        np.random.seed(17)
        rng_before = np.random.get_state()
        for year in (2026, 2036, 2056, 2066):
            a = CT.preferred_years(p, year, 24, 301.2, extension=True)
            b = CT.preferred_years(copy.deepcopy(p), year, 240, 3012, extension=True)
            self.assertEqual(a, b)  # cap shares, not fixed-dollar thresholds
        self.assertEqual(p.__dict__.keys(), before.keys())
        self.assertEqual(p.traits, before['traits'])
        np.testing.assert_equal(np.random.get_state(), rng_before)

    def test_five_year_extension_fits_when_cash_total_exceeds_one_year_room(self):
        L = fixture(); t = L.teams['GB']; t.gm = N(restructure_depth=.5)
        p = player(L, contract=Contract(1, [1]))
        player(L, 'other', contract=Contract(7, [80]*7))
        caps = {year: 100 for year in range(2026, 2035)}
        t.cap.cap = 100
        with patch.dict(EXT.CAP, caps):
            self.assertGreater(10*5, EXT.next_year_room(t, 100) + 10*.35)
            self.assertTrue(EXT.can_afford_extension(L, t, p, 10, 5))
            L.players['other'].contract.base[4] = 99
            self.assertFalse(EXT.can_afford_extension(L, t, p, 10, 5))

    def test_extension_replaces_its_existing_commitment(self):
        L = fixture(); t = L.teams['GB']; t.gm = N(restructure_depth=.5)
        p = player(L, contract=Contract(2, [1, 40]))
        player(L, 'other', contract=Contract(7, [55]*7))
        with patch.dict(EXT.CAP, {year: 100 for year in range(2026, 2035)}), \
             patch('cap_accounting.next_year_ledger', return_value=(100, 95, 0, 0)):
            self.assertTrue(EXT.can_afford_extension(L, t, p, 5, 5))

    def test_ai_round_actually_signs_affordable_five_year_extension(self):
        L = fixture(); L.user_team = 'MIN'; t = L.teams['GB']
        t.gm = N(restructure_depth=.5, youth=.5)
        p = player(L, contract=Contract(1, [1]))
        player(L, 'commitments', contract=Contract(7, [80]*7))
        t.cap.cap = 100
        with patch.dict(EXT.CAP, {year: 100 for year in range(2026, 2035)}), \
             patch.object(EXT, 'terms', return_value=dict(ask=10, offer=10, years=5, discount=.07)), \
             patch('gm_engine.scheme_fit', return_value=0), \
             patch('inbox.reconcile'):
            signed = EXT.ai_round(L, N(random=lambda: 0))
        self.assertEqual(len(signed), 1)
        self.assertEqual(signed[0][-1], 5)
        self.assertEqual(p.contract.years, 6)  # original year plus five new years
        self.assertGreaterEqual(t.cap_space, 0)

    def test_long_term_bonus_is_still_prorated_only_five_years(self):
        L = fixture(); p = player(L, contract=Contract(1, [1]))
        c = EXT.build(p, 7, 20, 301.2, N(restructure_depth=.5), L)
        self.assertEqual(c.years, 8)
        self.assertEqual(c.bonus_at(5), 0)
        self.assertAlmostEqual(sum(c.base) + sum(c.bonus_schedule), 141)

    def test_agent_open_preserves_five_year_request_and_inseason_stays_one(self):
        L = fixture(); L.user_team = 'GB'
        p = player(L, team=None)
        L.free_agents.append(p.pid)
        with patch('valuation.value_player', return_value=dict(apy=20, years=5)):
            L.set_phase('free_agency')
            opened = NG.open_talks(L, p.pid, 'fa_offseason')
            self.assertEqual(opened['years'], 5)
            L.negotiations = []
            L.set_phase('regular')
            self.assertEqual(NG.open_talks(L, p.pid, 'fa_inseason')['years'], 1)

    def test_extension_terms_do_not_cap_older_players_at_three(self):
        L = fixture(); p = player(L); p.age = 31
        with patch('valuation.value_player', return_value=dict(apy=20, years=4)):
            self.assertEqual(EXT.terms(L, p, np.random.default_rng(1))['years'], 4)

    def test_term_preference_is_used_by_offer_utility(self):
        row = dict(age=25, preferred_years=5)
        prof = dict(w=dict(total=0, years=1, winning=0, role=0, home=0, tax=0))
        u = lambda years: NE.utility(dict(apy=10, years=years), row, prof, {}, 10)
        self.assertGreater(u(5), u(2))
        self.assertEqual(CT.term_premium(5, 5), 1)
        self.assertGreater(CT.term_premium(2, 5), 1)

    def test_tender_conversion_reads_terms_dict_and_preserves_long_term(self):
        L = fixture(); L.user_team = 'GB'
        p = player(L, team='MIN', contract=Contract(1, [1]))
        p.fa_class = 'tendered'
        p.ratings = {'throw_power_rating': 99, 'short_accuracy_rating': 99, 'medium_accuracy_rating': 99,
                     'deep_accuracy_rating': 99, 'awareness_rating': 99}
        with patch.object(EXT, 'terms', return_value=dict(ask=10, offer=10, years=5, discount=.07)), \
             patch.object(EXT, 'can_afford_extension', return_value=True), \
             patch.object(EXT, 'extend', return_value=dict(result='accepted')) as extend, \
             patch.object(market, 'power', return_value=100):
            result = market.convert_tenders(L, N(random=lambda: 0), 1, user_team='GB')
        self.assertIn(p, result)
        self.assertEqual(extend.call_args.args[2:4], (10, 5))


if __name__ == '__main__':
    unittest.main()

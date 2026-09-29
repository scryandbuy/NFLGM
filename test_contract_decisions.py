import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

from cap_engine import Contract
from league import contract_to_dict
from test_cap_accounting import fixture, player
import extensions as EX
import negotiations as NG
import views_club as VC
import views_personnel as VP


class ContractDecisionTests(unittest.TestCase):
    def setup_deal(self, phase='regular', closed=False):
        L = fixture()
        L.set_phase(phase)
        if closed: L.season_closed_year = L.year
        L.teams['GB'].gm = N(restructure_depth=.5)
        p = player(L, contract=Contract(2, [20, 25], signing_bonus=20, void_years=2))
        return L, p

    def test_preview_matches_signed_extension_including_bonus_and_old_years(self):
        for phase, closed in [('regular', False), ('offseason', True), ('free_agency', False)]:
            for bonus in (None, 0, 9, 36):
                with self.subTest(phase=phase, bonus=bonus):
                    L, p = self.setup_deal(phase, closed)
                    before = copy.deepcopy(contract_to_dict(p.contract))
                    preview = VP.act_offer_preview(L, 'GB', p.pid, 12, 3, bonus=bonus, front_load=.85)
                    self.assertTrue(preview['ok'])
                    self.assertEqual(contract_to_dict(p.contract), before)
                    thread = dict(pid=p.pid, team='GB', kind='extension', log=[], state='open')
                    offer = dict(apy=12, years=3, bonus=bonus, front_load=.85)
                    with patch.object(EX, 'terms', return_value=dict(ask=12, discount=0, years=3)):
                        result = NG._accept(L, thread, offer, how='agreed', quiet=True)
                    self.assertTrue(result['ok'], result)
                    self.assertEqual(preview['years'], list(range(2026, 2031)))
                    self.assertEqual(preview['hits'], [round(p.contract.cap_hit(i), 3) for i in range(5)])
                    self.assertEqual(p.contract.base[:2], before['base'])
                    self.assertEqual(preview['total'], 36)
                    if bonus is not None:
                        self.assertAlmostEqual(p.contract.sb, 20 + bonus)
                        self.assertAlmostEqual(sum(p.contract.base[2:]) + bonus, 36)
                    if closed: self.assertEqual(p.contract.bonus_at(0), 5)

    def test_invalid_bonus_does_not_change_contract(self):
        L, p = self.setup_deal()
        before = contract_to_dict(p.contract)
        for bonus in (-1, 37, float('nan')):
            self.assertFalse(VP.act_offer_preview(L, 'GB', p.pid, 12, 3, bonus=bonus)['ok'])
        self.assertEqual(contract_to_dict(p.contract), before)

    def test_preview_shows_retained_void_year_charge_at_expiry(self):
        L, p = self.setup_deal()
        p.contract = Contract(1, [5], signing_bonus=20, void_years=4)
        preview = VP.act_offer_preview(L, 'GB', p.pid, 8, 1, bonus=0)
        c = EX.build(p, 1, 8, 301.2, L.teams['GB'].gm, L, bonus=0)
        p.contract = c
        self.assertEqual(preview['hits'], [9, 12, 12])
        self.assertEqual(preview['expiry_year'], 2028)
        L.advance_contracts()
        L.advance_contracts()
        self.assertEqual(L.teams['GB'].cap.dead, preview['hits'][-1])

    def test_free_agent_preview_still_matches_signing(self):
        import market
        L, p = self.setup_deal()
        L.teams['GB'].roster.remove(p)
        p.contract = None
        p.team = None
        L.teams['GB'].cap.paid_week = 9
        preview = VP.act_offer_preview(L, 'GB', p.pid, 8, 2, bonus=4)
        market.sign(L, p, market.Offer('GB', p.pid, 8, 2), 301.2, bonus=4)
        self.assertEqual(preview['hits'], [round(p.contract.cap_hit(i), 3) for i in range(2)])
        self.assertTrue(preview['prorated'])

    def test_cut_display_and_result_match_ledger_in_each_phase(self):
        for phase, expected in [('offseason', (10, 20)), ('free_agency', (10, 20)), ('regular', (30, 0))]:
            with self.subTest(phase=phase):
                L, p = self.setup_deal(phase)
                p.contract = Contract(3, [18]*3, signing_bonus=30)
                row = VC._row(N(runner=None), L, L.teams['GB'], p)
                self.assertEqual((row['penalty'], row['penalty_next']), expected)
                result = VC.act_cut(L, 'GB', p.pid)
                self.assertEqual((result['penalty'], result['penalty_next']), expected)
                self.assertEqual((L.teams['GB'].cap.dead, L.teams['GB'].cap.dead_next), expected)

    def test_squad_waiver_message_reports_both_years(self):
        for accrued in (1, 5):
            with self.subTest(accrued=accrued):
                L, p = self.setup_deal('offseason')
                p.contract = Contract(3, [18]*3, signing_bonus=30)
                p.accrued = accrued
                result = VC.act_to_squad(L, 'GB', p.pid)
                self.assertTrue(result['ok'], result)
                self.assertIn('$10.0m this year and $20.0m next year', result['line'])
                self.assertEqual((L.teams['GB'].cap.dead, L.teams['GB'].cap.dead_next), (10, 20))

    def test_player_card_agrees_with_roster_and_release(self):
        from session import Session
        s = Session.new('GB', seed=41)
        s.L.set_phase('offseason')
        p = s.L.teams['GB'].roster[0]
        p.contract = Contract(3, [18]*3, signing_bonus=30)
        card = VC.card(s, s.L, p.pid)
        self.assertEqual((card['contract']['penalty'], card['contract']['penalty_next']), (10, 20))
        self.assertEqual((card['contract']['by_year'][0]['penalty'], card['contract']['by_year'][0]['penalty_next']), (10, 20))
        result = VC.act_cut(s.L, 'GB', p.pid)
        self.assertEqual(result['penalty'], card['contract']['penalty'])
        self.assertEqual(result['penalty_next'], card['contract']['penalty_next'])


if __name__ == '__main__':
    unittest.main()

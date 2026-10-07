import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace as N
import numpy as np
from test_cap_accounting import fixture, player
from league import League
from cap_engine import Contract
import tags as TG
import extensions as EXT
import negotiations as NG
import views_personnel as VP


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture()
        self.L.user_team = 'GB'
        self.L.set_phase('offseason')
        self.rfa = player(self.L, 'rfa'); self.rfa.accrued = 3
        self.other = player(self.L, 'other'); self.other.accrued = 3
        self.ufa = player(self.L, 'ufa')
        self.young_rfa = player(self.L, 'young_rfa'); self.young_rfa.accrued = 2

    def test_tenders_explicit_persistent_and_withdrawable(self):
        self.assertFalse(TG.user_resign_sheet(self.L)['rfa'][0]['tender'])
        self.assertTrue(TG.user_tender(self.L, 'rfa')['ok'])
        pending = TG.pending_tender_cost(self.L)
        self.assertGreater(pending, 0)
        self.assertTrue(TG.user_tender(self.L, 'rfa')['ok'])
        self.assertEqual(TG.pending_tender_cost(self.L), pending)
        loaded = League.load(self.L.save()); loaded.user_team = 'GB'
        self.assertEqual(loaded.user_tenders, ['rfa'])
        self.assertEqual(TG.pending_tender_cost(loaded), pending)
        self.assertTrue(TG.user_tender(loaded, 'rfa', False)['ok'])
        self.assertEqual(TG.pending_tender_cost(loaded), 0)

    def test_tender_activation_keeps_offer_sheet_rights_and_untendered_walks(self):
        TG.user_tender(self.L, 'rfa')
        TG.run(self.L, np.random.default_rng(7))
        self.assertEqual(self.rfa.fa_class, 'tendered')
        self.assertEqual(self.rfa.contract.years, 1)
        self.assertEqual(self.rfa.tender_team, 'GB')
        self.assertIn('rfa', self.L.free_agents)
        self.assertIsNone(self.other.team)
        self.assertEqual(self.other.fa_class, 'UFA')
        self.assertIsNone(self.young_rfa.team)
        self.assertEqual(self.young_rfa.fa_class, 'UFA')
        self.assertTrue(EXT.eligible(self.rfa, self.L))
        self.assertEqual(TG.user_resign_sheet(self.L)['rfa'], [])

    def test_reject_wrong_class_team_and_closed_window(self):
        self.assertFalse(TG.user_tender(self.L, 'ufa')['ok'])
        self.assertTrue(TG.user_tender(self.L, 'young_rfa')['ok'])
        rival = player(self.L, 'rival', team='MIN'); rival.accrued = 3
        self.assertFalse(TG.user_tender(self.L, 'rival')['ok'])
        self.assertFalse(TG.user_tag(self.L, 'rfa')['ok'])
        self.L.tags_done_year = self.L.year
        self.assertFalse(TG.user_tag(self.L, 'ufa')['ok'])
        self.assertFalse(TG.user_tender(self.L, 'rfa')['ok'])

    def test_tag_moves_to_extensions_and_only_one_can_be_used(self):
        expected = TG.tag_price(self.ufa, 301.2)
        self.assertTrue(TG.user_tag(self.L, 'ufa')['ok'])
        self.assertEqual(self.ufa.contract.cap_hit(0), expected)
        another = player(self.L, 'ufa2')
        self.assertFalse(TG.user_tag(self.L, another.pid)['ok'])
        self.assertFalse(TG.user_tag(self.L, 'none')['ok'])
        with patch.object(VP, 'rail', return_value={}):
            self.assertNotIn('ufa', [r['pid'] for r in VP.retain(None, self.L, 'GB')['ufa']])
        self.assertTrue(EXT.eligible(self.ufa, self.L))

    def test_young_restricted_player_can_be_tendered_and_other_can_walk(self):
        self.assertEqual(self.young_rfa.accrued, 2)
        self.assertIn('young_rfa', [r['pid'] for r in TG.user_resign_sheet(self.L)['rfa']])
        self.assertTrue(TG.user_tender(self.L, 'young_rfa')['ok'])
        TG.run(self.L, np.random.default_rng(4))
        self.assertEqual(self.young_rfa.fa_class, 'tendered')
        self.assertEqual(self.young_rfa.tender_team, 'GB')
        self.assertIn(self.young_rfa.pid, self.L.free_agents)
        self.assertIsNone(self.other.team)
        self.assertEqual(self.other.fa_class, 'UFA')

    def test_old_exclusive_rights_labels_normalize_on_load(self):
        self.young_rfa.fa_class = 'ERFA'
        signed = player(self.L, 'old_signed'); signed.accrued = 2
        signed.contract = Contract(years=1, base=[1.5], signing_bonus=0, signed=self.L.year)
        signed.fa_class = 'exclusive_rights'
        street = player(self.L, 'old_street', team=None); street.accrued = 2
        street.fa_class = 'ERFA'; self.L.free_agents.append(street.pid)
        loaded = League.load(self.L.save())
        self.assertEqual(loaded.player('young_rfa').fa_class, 'RFA')
        self.assertEqual(loaded.player('old_signed').fa_class, 'under_contract')
        self.assertIsNotNone(loaded.player('old_signed').contract)
        self.assertEqual(loaded.player('old_street').fa_class, 'UFA')
        self.assertIn('old_street', [p.pid for p in TG.classify(loaded)['UFA']])

    def test_cap_reserves_pending_tenders(self):
        price = TG.tender_price(self.rfa, 301.2)
        with patch.object(TG, 'power', return_value=price + .01):
            self.assertTrue(TG.user_tender(self.L, 'rfa')['ok'])
            self.assertFalse(TG.user_tender(self.L, 'other')['ok'])
            self.assertFalse(TG.user_tag(self.L, 'ufa')['ok'])

    def test_expired_player_can_negotiate_and_sign_without_existing_contract(self):
        self.L.teams['GB'].gm = N(restructure_depth=.5)
        self.assertTrue(EXT.eligible(self.ufa, self.L))
        with patch.object(EXT, 'terms', return_value=dict(ask=5, discount=0, years=3)):
            opened = NG.open_talks(self.L, 'ufa', 'extension')
            self.assertTrue(opened['ok'], opened)
            thread = NG.find(self.L, opened['thread'])
            result = NG._accept(self.L, thread, dict(apy=5, years=3, bonus=3), 'agreed', quiet=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.ufa.contract.years, 3)
        self.assertEqual(TG.user_resign_sheet(self.L)['ufa'], [])

    def test_legacy_save_preserves_old_tender_choices(self):
        data = json.loads(self.L.save()); data.pop('user_tenders')
        data['_user_team'] = 'GB'; data['user_no_tender'] = ['other']
        loaded = League.load(json.dumps(data))
        self.assertEqual(loaded.user_tenders, ['rfa'])

    def test_tendered_extension_clears_market_and_matching_rights(self):
        self.L.teams['GB'].gm = N(restructure_depth=.5)
        TG.user_tender(self.L, 'rfa')
        TG.run(self.L, np.random.default_rng(8))
        thread = dict(pid='rfa', team='GB', kind='extension', state='open', log=[])
        with patch.object(EXT, 'terms', return_value=dict(ask=5, discount=0, years=3)):
            result = NG._accept(self.L, thread, dict(apy=5, years=3, bonus=3), 'agreed', quiet=True)
        self.assertTrue(result['ok'], result)
        self.assertNotIn('rfa', self.L.free_agents)
        self.assertIsNone(self.rfa.tender_team)
        self.assertEqual(self.rfa.fa_class, 'under_contract')

    def test_advance_blocks_if_pending_tenders_stop_fitting(self):
        from session import Session
        import inbox
        TG.user_tender(self.L, 'rfa')
        s = Session(self.L, np.random.default_rng(8), 'GB')
        s.stop = ('offseason', next(i for i, x in enumerate(s.OFFSEASON) if x[1] == 'step_extensions'))
        with patch.object(TG, 'power', return_value=0), patch.object(inbox, 'reconcile'):
            blocks = s.blocking()
        self.assertTrue(any(b.get('go') == '#personnel/retain' and b['kind'] == 'cap' for b in blocks))


if __name__ == '__main__': unittest.main()

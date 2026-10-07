import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
from test_cap_accounting import fixture, player
import views_personnel as VP
import negotiations as NG

class InvalidExtensionPreviewTests(unittest.TestCase):
    def setUp(self):
        self.L=fixture(); self.L.user_team='GB'; self.L.set_phase('offseason')
        self.L.teams['GB'].gm=N(restructure_depth=.5)
        self.p=player(self.L,contract=None)
        offer=dict(apy=.5,years=1,bonus=.1,front_load=.5,promises=[])
        self.t=dict(id=1,pid=self.p.pid,team='GB',kind='extension',state='countered',
                    offers=[dict(offer)],counter=dict(offer),ask=2,years=1,patience=3,
                    opened=100,mood='open',due=None,log=[])
        self.L.negotiations=[self.t]

    def test_expired_contract_counter_cannot_crash_page_or_change_terms(self):
        before=copy.deepcopy(self.t)
        with patch.object(VP,'rail',return_value={}):
            view=VP.extensions(None,self.L,'GB')
        preview=view['threads'][0]['offer_cap_preview']
        self.assertFalse(preview['ok'])
        self.assertIn('Annual salary must be at least',preview['why'])
        self.assertEqual(self.t,before)
        self.assertIsNone(self.p.contract)

    def test_below_minimum_counter_still_cannot_be_accepted(self):
        before=copy.deepcopy(self.t)
        result=VP.act_match_counter(self.L,'GB',1)
        self.assertFalse(result['ok'])
        self.assertIsNone(self.p.contract)
        self.assertEqual(self.t,before)

    def test_valid_expired_counter_can_still_sign(self):
        self.t['counter'].update(apy=3,bonus=.1)
        with patch('extensions.terms', return_value=dict(ask=3,offer=3,years=1,discount=0)):
            result=VP.act_match_counter(self.L,'GB',1)
        self.assertTrue(result['ok'],result)
        self.assertEqual(self.t['state'],'accepted')
        self.assertAlmostEqual(self.p.contract.base[0],2.9)

    def test_valid_expired_contract_preview_still_has_cap_schedule(self):
        result=VP.act_offer_preview(self.L,'GB',self.p.pid,3,1,bonus=.1,front_load=.5)
        self.assertTrue(result['ok'],result)
        self.assertEqual(len(result['hits']),1)
        self.assertEqual(result['years'],[2026])
        self.assertAlmostEqual(result['total'],3)

if __name__=='__main__': unittest.main()

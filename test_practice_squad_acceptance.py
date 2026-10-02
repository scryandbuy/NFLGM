"""Veteran PS willingness preserves the active market and user/CPU parity."""
import unittest
from unittest.mock import patch
import numpy as np
from league import Player
from cap_engine import Contract
from test_draft_planning import fixture
import targets as TG
import practice_squad as PS

class PracticeAcceptanceTests(unittest.TestCase):
    def setup_player(self,grade=84):
        L,t=fixture();t.cap.cap=500;t.sync_cap();L.free_agents=[]
        p=Player('waiting_vet','Waiting Veteran','LT',34,
                 {k:grade for k in TG.DEPTH_WEIGHTS['LT']})
        p.accrued=11;L.players[p.pid]=p;L.free_agents.append(p.pid)
        return L,t,p

    def test_strong_veteran_declines_for_user_and_cpu_without_mutation(self):
        for user in (None,'MIN'):
            L,t,p=self.setup_player();L.user_team=user
            before=list(L.transactions)
            self.assertFalse(PS.sign_to_squad(L,t.abbr,p.pid))
            self.assertIn(p.pid,L.free_agents);self.assertIsNone(p.team)
            self.assertIsNone(p.contract);self.assertNotIn(p,PS.squad(t))
            self.assertEqual(L.transactions,before)
            self.assertEqual(PS.squad_acceptance(L,p)['reason'],'seeking_active_contract')

    def test_fill_preserves_veteran_for_later_active_signing(self):
        L,t,p=self.setup_player()
        self.assertEqual(PS.fill_squads(L,np.random.default_rng(8)),0)
        self.assertIn(p.pid,L.free_agents)
        L.sign(p.pid,t.abbr,Contract(1,[3.]))
        self.assertIn(p,t.active());self.assertNotIn(p.pid,L.free_agents)
        self.assertNotIn(p,PS.squad(t))

    def test_marginal_veteran_accepts_existing_squad_terms(self):
        L,t,p=self.setup_player(70)
        self.assertTrue(PS.sign_to_squad(L,t.abbr,p.pid))
        self.assertIn(p,PS.squad(t));self.assertIsNone(p.contract)
        self.assertNotIn(p.pid,L.free_agents);self.assertEqual(PS.ps_charge(t),0)

    def test_refused_demotion_keeps_active_contract(self):
        L,t,p=self.setup_player();L.sign(p.pid,t.abbr,Contract(1,[3.]))
        original=p.contract
        self.assertFalse(PS.sign_to_squad(L,t.abbr,p.pid))
        self.assertIn(p,t.roster);self.assertIs(p.contract,original)

    def test_clear_starter_young_player_declines_but_development_player_accepts(self):
        for grade, expected in ((87, False), (85, False), (76, True)):
            L,t,p=self.setup_player(grade);p.age=22;p.accrued=0
            self.assertEqual(PS.sign_to_squad(L,t.abbr,p.pid),expected)
            self.assertEqual(p.pid in L.free_agents,not expected)
            self.assertEqual(p in PS.squad(t),expected)

    def test_young_path_and_specialist_normalization(self):
        L,t,p=self.setup_player();p.accrued=1
        self.assertTrue(PS.squad_acceptance(L,p)['accepts'])
        p.accrued=11;p.pos='P'
        with patch('draft.common_scale',return_value=70):
            self.assertTrue(PS.squad_acceptance(L,p)['accepts'])
        with patch('draft.common_scale',return_value=84):
            self.assertFalse(PS.squad_acceptance(L,p)['accepts'])

if __name__=='__main__':unittest.main()

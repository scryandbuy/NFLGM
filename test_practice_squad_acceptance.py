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
    def setup_player(self,grade=84,pos='LT'):
        L,t=fixture();t.cap.cap=500;t.sync_cap();L.free_agents=[]
        p=Player('waiting_vet','Waiting Veteran',pos,34,
                 {k:grade for k in TG.DEPTH_WEIGHTS[pos]})
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

    def test_recent_active_specialists_refuse_even_when_normalized_grade_is_low(self):
        for pos,grade,line in (('P',88.8,{'punts':74}),
                               ('K',91.5,{'fg_att':49,'fg_made':46})):
            L,t,p=self.setup_player(grade,pos)
            p.career[L.year-1]=line
            with patch('draft.common_scale',return_value=72):
                self.assertFalse(PS.squad_acceptance(L,p)['accepts'])
                self.assertFalse(PS.sign_to_squad(L,t.abbr,p.pid))
            self.assertIn(p.pid,L.free_agents)
            self.assertIsNone(p.team)

    def test_recently_used_receiver_refuses_but_fringe_veteran_accepts(self):
        L,t,p=self.setup_player(77.7,'WR')
        p.career[L.year-1]={'snaps':672,'tgt':86,'rec':54}
        self.assertFalse(PS.squad_acceptance(L,p)['accepts'])
        self.assertFalse(PS.sign_to_squad(L,t.abbr,p.pid))
        p.ratings={k:70 for k in TG.DEPTH_WEIGHTS['WR']}
        self.assertTrue(PS.squad_acceptance(L,p)['accepts'])
        self.assertTrue(PS.sign_to_squad(L,t.abbr,p.pid))
        self.assertIn(p,PS.squad(t))

    def test_recent_young_starter_also_seeks_active_role(self):
        L,t,p=self.setup_player(77.7,'WR')
        p.age=24;p.accrued=2
        p.career[L.year-1]={'snaps':672,'tgt':86}
        self.assertFalse(PS.squad_acceptance(L,p)['accepts'])
        p.career.clear()
        self.assertTrue(PS.squad_acceptance(L,p)['accepts'])

    def test_old_production_does_not_permanently_block_squad_offer(self):
        L,t,p=self.setup_player(77.7,'WR')
        p.career[L.year-2]={'snaps':900,'tgt':100}
        self.assertTrue(PS.squad_acceptance(L,p)['accepts'])

    def test_empty_market_does_not_force_a_recent_starter_onto_squad(self):
        L,t,p=self.setup_player(77.7,'WR')
        p.career[L.year-1]={'snaps':672,'tgt':86}
        self.assertEqual(PS.fill_squads(L,np.random.default_rng(8)),0)
        self.assertEqual(PS.squad(t),[])
        self.assertIn(p.pid,L.free_agents)

    def test_fill_uses_fringe_players_and_reaches_legal_squad_size(self):
        L,t,strong=self.setup_player(77.7,'WR')
        strong.career[L.year-1]={'snaps':672,'tgt':86}
        for i in range(18):
            p=Player(f'candidate{i}',f'Candidate {i}','WR',22 if i<12 else 30,
                     {k:70 for k in TG.DEPTH_WEIGHTS['WR']},
                     accrued=0 if i<12 else 6)
            L.players[p.pid]=p;L.free_agents.append(p.pid)
        self.assertEqual(PS.fill_squads(L,np.random.default_rng(8)),16)
        self.assertEqual(len(PS.squad(t)),16)
        self.assertEqual(sum(not PS.is_young(p) for p in PS.squad(t)),4)
        self.assertNotIn(strong,PS.squad(t))
        self.assertIn(strong.pid,L.free_agents)

    def test_veteran_limit_and_full_squad_remain_enforced(self):
        L,t,p=self.setup_player(70,'WR')
        for i in range(6):
            veteran=Player(f'vet{i}',f'Vet {i}','WR',30,
                           {k:70 for k in TG.DEPTH_WEIGHTS['WR']},accrued=5)
            PS.squad(t).append(veteran)
        self.assertFalse(PS.can_add(t,p))
        for i in range(10):
            youngster=Player(f'young{i}',f'Young {i}','WR',22,
                             {k:70 for k in TG.DEPTH_WEIGHTS['WR']})
            PS.squad(t).append(youngster)
        self.assertEqual(len(PS.squad(t)),16)
        self.assertFalse(PS.can_add(t,youngster))

    def test_marginal_squad_receiver_can_cover_game_day_shortage(self):
        L,t,p=self.setup_player(70,'WR')
        self.assertTrue(PS.sign_to_squad(L,t.abbr,p.pid))
        for q in [q for q in t.roster if q.pos=='WR'][:2]:
            q.out_until=4
        L.set_phase('regular');L.week=1
        moves=PS.elevate_for_coverage(L,t,1)
        self.assertTrue(any(p.pid in str(move) for move in moves))

if __name__=='__main__':unittest.main()

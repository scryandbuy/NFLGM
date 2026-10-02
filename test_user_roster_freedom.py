"""User control and CPU parity at transaction and game boundaries."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from cap_engine import Contract
from test_trade_roster_limit import fixture
import extensions as E
import practice_squad as PS
import trade_engine as TE
import game_availability as GA
from league import League, Player

class FreedomTests(unittest.TestCase):
    def test_dead_money_preference_is_cpu_only_but_cap_is_not(self):
        asset = dict(kind='player', dead_now=8, inherit=1, out_hit=10)
        offer = dict(a_sends=[asset], a_gets=[])
        self.assertEqual(TE.cap_blocks(offer,10,100), 'a_dead_money')
        self.assertIsNone(TE.cap_blocks(offer,10,100,user_a=True))
        self.assertEqual(TE.cap_blocks(offer, -3,100,user_a=True), 'a_cannot_fit')
        reverse=dict(a_sends=[],a_gets=[asset])
        self.assertIsNone(TE.cap_blocks(reverse,100,10,user_b=True))
        self.assertEqual(TE.cap_blocks(reverse,100,10), 'b_dead_money')

    def test_veteran_extension_and_cpu_timing(self):
        L, _, _ = fixture(); p=L.player('GB-QB-0')
        p.contract=Contract(5,[1]*5,signed=2026)
        p.draft_year=2020; p.draft_round=1
        self.assertTrue(E.eligible(p,L))
        self.assertFalse(E.ai_eligible(p,L))
        c=E.build(p,3,5,301.2,L.teams['GB'].gm,L,bonus=3)
        self.assertEqual(c.years,8)
        self.assertEqual(c.base[:5],p.contract.base)

    def test_rookie_calendar_drafted_and_undrafted(self):
        L,_,_=fixture(); p=L.player('GB-QB-0'); p.draft_year=2026
        p.contract=Contract(4,[1]*4,signed=2026)
        for draft_round, ready in ((1,2028),(None,2027)):
            p.draft_round=draft_round; L.year=ready; L.set_phase('regular'); L.week=18
            self.assertFalse(E.eligible(p,L))
            L.set_phase('playoffs'); self.assertTrue(E.eligible(p,L))
            L.set_phase('offseason'); L.season_closed_year=ready
            self.assertTrue(E.eligible(p,L))
            L.year=ready+1; L.season_closed_year=ready
            self.assertTrue(E.eligible(p,L))
            L.year=ready; L.season_closed_year=ready-1
            self.assertFalse(E.eligible(p,L))

    def test_promotions_and_poaching_allow_overflow_without_cuts(self):
        for user in ('GB',None):
            for poach in (False,True):
                L,_,_=fixture(); L.user_team=user
                src='MIN' if poach else 'GB'
                p=Player('squad','Squad','WR',24,{},team=src,accrued=1)
                L.players[p.pid]=p; PS.squad(L.teams[src]).append(p)
                ok=PS.poach(L,'GB',p.pid,2) if poach else PS.call_up(L,'GB',p.pid)
                self.assertTrue(ok)
                self.assertEqual(len(L.teams['GB'].active()),54)
                self.assertFalse(any(t['kind']=='release' for t in L.transactions))
                self.assertGreaterEqual(L.teams['GB'].cap_space,0)
                loaded=League.load(L.save())
                self.assertEqual(len(loaded.teams['GB'].active()),54)

    def test_insufficient_cap_rejects_acquisitions_for_both(self):
        for user in ('GB',None):
            for mode in ('trade','callup','poach'):
                L,star,pick=fixture(); L.user_team=user
                team=L.teams['GB']; team.cap.cap=53; team.cap.rollover=0; team.sync_cap()
                self.assertAlmostEqual(team.cap_space,0)
                if mode=='trade':
                    with self.assertRaises(ValueError): L.trade('GB','MIN',[pick],[star.pid])
                    self.assertEqual(star.team,'MIN'); self.assertEqual(pick.owner,'GB')
                else:
                    src='GB' if mode=='callup' else 'MIN'
                    p=Player('squad','Squad','WR',24,{},team=src,accrued=1)
                    L.players[p.pid]=p; PS.squad(L.teams[src]).append(p)
                    self.assertFalse(PS.call_up(L,'GB',p.pid) if mode=='callup' else PS.poach(L,'GB',p.pid,2))
                    self.assertIn(p,PS.squad(L.teams[src]))
                self.assertEqual(len(team.active()),53)

    def test_future_cap_overage_does_not_block_user_or_cpu_trade(self):
        from cap_accounting import next_year_ledger
        for user in ('GB', None):
            L, star, pick = fixture(); L.user_team=user
            star.contract=Contract(2,[1,1000],signed=L.year)
            L.teams['MIN'].sync_cap()
            L.trade('GB','MIN',[pick],[star.pid])
            self.assertEqual(star.team,'GB')
            self.assertGreaterEqual(L.teams['GB'].cap_space,0)
            limit, committed, _, _=next_year_ledger(L,L.teams['GB'])
            self.assertGreater(committed,limit)

    def test_second_specialist_is_user_choice(self):
        L,_,_=fixture(); team=L.teams['GB']
        PS.squad(team).append(NS(pos='K',accrued=0))
        p=NS(pos='P',accrued=0)
        self.assertTrue(PS.can_add(team,p))
        self.assertFalse(PS.can_add(team,p,by_ai=True))
        team.practice_squad=[NS(pos='WR',accrued=5) for _ in range(6)]
        self.assertFalse(PS.can_add(team,NS(pos='P',accrued=5)))

    def test_game_gate_blocks_user_overflow_before_roster_build(self):
        L,star,pick=fixture(); L.user_team='GB'; L.trade('GB','MIN',[pick],[star.pid])
        with self.assertRaises(GA.FieldabilityError): GA.ensure(L,L.teams['GB'],None,2)

    def test_cpu_cleanup_failure_does_not_partially_cut(self):
        L,star,pick=fixture(); L.trade('GB','MIN',[pick],[star.pid])
        with patch.object(PS,'locked',return_value=True):
            with self.assertRaises(GA.FieldabilityError): GA.settle_roster(L,L.teams['GB'],2)
        self.assertEqual(len(L.teams['GB'].active()),54)
        self.assertFalse(any(t['kind']=='release' for t in L.transactions))

if __name__=='__main__': unittest.main()

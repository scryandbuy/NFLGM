"""Identical financial forecasts may reuse work, never change trade choices."""
import copy
import unittest
from unittest.mock import patch

import financial_plan as FP
import roster_needs as RN
import trades as TR
from session import Session


class TradeFundingReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial=Session.new('GB',seed=45).save()

    def setUp(self):
        self.s=Session.load(self.initial);self.L=self.s.L;self.L.user_team=None
        self.a,self.b=self.L.teams['GB'],self.L.teams['DEN']
        self.sent=next(p for p in self.a.picks if p.year==2026 and p.round==7)
        self.equivalent=copy.copy(self.sent);self.equivalent.original='CLE'
        self.a.picks.insert(self.a.picks.index(self.sent)+1,self.equivalent)
        self.received=next(p for p in self.b.picks if p.year==2026 and p.round==7)

    def check(self, sent, received, cache=None, **kwargs):
        return TR._financial_trade(self.L,self.a,self.b,[sent],[received],cache,**kwargs)

    def test_equivalent_pick_owners_reuse_identical_forecast_without_mutation(self):
        cache={}
        with patch.object(FP,'evaluate',wraps=FP.evaluate) as evaluate:
            first=self.check(self.sent,self.received,cache)
            calls=evaluate.call_count
            after_first=self.s.save()
            second=self.check(self.equivalent,self.received,cache)
            self.assertEqual(evaluate.call_count,calls)
        self.assertGreater(calls,0)
        self.assertEqual(first,second)
        self.assertEqual(self.s.save(),after_first)
        self.assertEqual(second,self.check(self.equivalent,self.received))

    def test_different_future_slot_is_not_reused(self):
        later=copy.copy(self.received);later.selection=230
        cache={}
        with patch.object(FP,'evaluate',wraps=FP.evaluate) as evaluate:
            self.check(self.sent,self.received,cache)
            before=evaluate.call_count
            optimized=self.check(self.sent,later,cache)
            self.assertGreater(evaluate.call_count,before)
        self.assertEqual(optimized,self.check(self.sent,later))

    def test_distinct_pick_costs_reuse_roster_work_but_new_players_do_not(self):
        cache={}
        later=copy.copy(self.received);later.selection=230
        with patch.object(FP,'prepare_snapshot',wraps=FP.prepare_snapshot) as prepare:
            self.check(self.sent,self.received,cache)
            count=prepare.call_count
            self.check(self.sent,later,cache)
            self.assertEqual(prepare.call_count,count)
            player=min((p for p in self.b.active() if p.pos=='WR'),
                       key=lambda p:p.contract.remaining_proration(0))
            TR._financial_trade(self.L,self.a,self.b,[self.sent],[player.pid],cache)
            self.assertGreater(prepare.call_count,count)

    def test_new_negotiation_rebuilds_after_contract_change(self):
        self.check(self.sent,self.received,{})
        self.a.roster[0].contract.base[0] += 12
        with patch.object(FP,'prepare_snapshot',wraps=FP.prepare_snapshot) as prepare:
            refreshed=self.check(self.sent,self.received,{})
            self.assertGreater(prepare.call_count,0)
        self.assertEqual(refreshed,self.check(self.sent,self.received))

    def test_reusing_completed_roster_assessment_preserves_gain_and_funding(self):
        target=min((p for p in self.b.active() if p.pos=='WR'),
                   key=lambda p:p.contract.remaining_proration(0))
        gains={self.a.abbr:RN.assess(self.a,self.a.active()+[target])['score']-RN.assess(self.a)['score'],
               self.b.abbr:RN.assess(self.b,[p for p in self.b.active() if p is not target])['score']-RN.assess(self.b)['score']}
        with patch.object(FP,'evaluate',wraps=FP.evaluate) as plain:
            expected=TR._financial_trade(self.L,self.a,self.b,[self.sent],[target.pid])
        self.assertGreater(plain.call_count,0)
        with patch.object(RN,'assess',wraps=RN.assess) as assess, \
             patch.object(FP,'evaluate',wraps=FP.evaluate) as reused:
            actual=TR._financial_trade(self.L,self.a,self.b,[self.sent],[target.pid],roster_gains=gains)
        self.assertEqual(actual,expected)
        self.assertEqual([c.kwargs['gain'] for c in plain.call_args_list],
                         [c.kwargs['gain'] for c in reused.call_args_list])
        assess.assert_not_called()


class PreparedFinancialProjectionTests(unittest.TestCase):
    def test_full_forecasts_match_across_phases_ledgers_and_pick_costs(self):
        from test_draft_planning import fixture
        from cap_engine import Contract
        from league import DraftPick
        for phase in ('regular','free_agency','offseason'):
            L,t=fixture();L.set_phase(phase)
            if phase=='offseason':L.season_closed_year=L.year
            t.cap.paid_week=8;t.cap.dead=1.375;t.cap.dead_next=2.125
            t.ir=[t.roster[0]]
            t.roster[1].contract=Contract(2,[8.25,9.75],sb=7.1,void_years=2)
            arrival=copy.deepcopy(t.roster[2]);arrival.pid='arrival'
            pending=copy.deepcopy(t.roster[3]);pending.pid='pending'
            changes=dict(additions=[(arrival,Contract(3,[2.5,4.25,6.75]))],
                         removals=[t.roster[4].pid],
                         pending=[(pending,Contract(2,[1.25,2.5]))])
            fixed=FP.prepare_snapshot(L,t,**changes);frozen=copy.deepcopy(fixed)
            before=L.save()
            for picks in ([],t.picks,
                          [DraftPick(L.year+i,r,'MIN','MIN',selection=slot)
                           for i,r,slot in ((0,1,4),(1,2,None),(0,7,224))]):
                with self.subTest(phase=phase,picks=len(picks)):
                    expected=FP.evaluate(L,t,**changes,picks=picks,gain=12)
                    actual=FP.evaluate(L,t,**changes,picks=picks,gain=12,prepared_after=fixed)
                    self.assertEqual(actual,expected)
                    actual['after']['years'][0]['funded_room']=-999
                    self.assertEqual(FP.snapshot(L,t,**changes,picks=picks,prepared=fixed),expected['after'])
            self.assertEqual(fixed,frozen)
            self.assertEqual(L.save(),before)


if __name__=='__main__': unittest.main()

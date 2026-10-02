"""Coach changes must reach roster decisions, not just the displayed scheme.

Constructed rosters isolate role demand. Owner selection is pinned to a supplied
new coach; the actual hire, conversion, bid and cutdown paths remain in use.
Market-price mocks hold price constant to test preference, not economic balance.
"""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import coaching_pool as CP
import gm_engine as GE
import roster_needs as RN
import cutdown as CD
import market
import trades
from test_draft_planning import fixture, set_grade
from test_personnel_package_decisions import offense_fixture, assets


def hire(L,t,front,personnel):
    incoming=copy.deepcopy(t.gm)
    incoming.name='Transition Coach';incoming.def_front=front;incoming.off_personnel=personnel
    with patch.object(CP,'owner_hire',return_value=(incoming,{})):
        CP.fire_and_hire(L,t,np.random.default_rng(42))
    return incoming


class CoachTransitionDecisions(unittest.TestCase):
    def test_hire_installs_odd_front_without_wholesale_turnover(self):
        L,t=fixture();t.gm.def_front='4-3';t.scheme=GE.scheme_of(t.gm)
        before=RN.assess(t);ids={p.pid for p in t.roster}
        coach=hire(L,t,'3-4','11');after=RN.assess(t)
        self.assertIs(t.gm,coach);self.assertEqual(t.scheme,GE.scheme_of(coach))
        self.assertEqual(ids,{p.pid for p in t.roster})
        self.assertFalse(any(e['kind'] in ('release','sign') for e in L.transactions))
        self.assertNotIn('NT',{r['role'] for r in before['assignments']})
        self.assertIn('NT',{r['role'] for r in after['assignments']})
        self.assertIn('RILB',{r['role'] for r in after['assignments']})
        for variant in {r['variant'] for r in after['package_assignments']}:
            rows=[r for r in after['package_assignments'] if r['variant']==variant]
            self.assertEqual(len({r['player'].pid for r in rows if r['player']}),11)

    def test_new_personnel_changes_fa_and_trade_priority(self):
        L,t,wr,te,qb=offense_fixture('10');pool=[wr,te,qb]
        old=trades.package_trade_targets(t,assets(pool),RN.assess(t))
        self.assertEqual(old[0]['pid'],wr.pid)
        ids={p.pid for p in t.roster};hire(L,t,'4-3','12')
        after=RN.assess(t)
        ranked=trades.package_trade_targets(t,assets(pool),after)
        self.assertEqual(ranked[0]['pid'],te.pid)
        with patch.object(market.VAL,'pool_from_league',return_value={}), \
             patch.object(market.VAL,'value_player',return_value={'apy':10,'years':1}), \
             patch.object(market,'power',return_value=100):
            bids=market.ai_bids(L,pool,1,np.random.default_rng(7))
        self.assertEqual(next(iter(bids)),te.pid)
        self.assertEqual(ids,{p.pid for p in t.roster})

    def test_retention_loss_responds_to_new_job(self):
        L,t,wr,te,qb=offense_fixture('10')
        reserve=L.player('TE1');set_grade(reserve,80)
        old=RN.departure_loss(t,reserve)
        hire(L,t,'4-3','12')
        new=RN.departure_loss(t,reserve)
        self.assertGreater(new,old)
        self.assertIn(reserve,t.roster)

    def test_new_coach_recomputes_retention_without_forced_turnover(self):
        import retention_plan as RP
        import extensions as EXT
        from cap_engine import Contract
        L,t,wr,te,qb=offense_fixture('10')
        p=L.player('TE1');set_grade(p,80)
        p.contract=Contract(1,[1.],signed=2026)
        t.picks=[];t.cap.cap=500;t.sync_cap()
        quote=dict(ask=10.,offer=10.,years=3,discount=.07)
        with patch.object(EXT,'terms',return_value=quote):
            old=RP.assess(L,t,p)
            old_candidates={q.pid:r for q,r in RP.candidates(L,t)}
            hire(L,t,'4-3','12')
            new=RP.assess(L,t,p)
            new_candidates={q.pid:r for q,r in RP.candidates(L,t)}
        self.assertGreater(new['role_share'],old['role_share'])
        self.assertGreater(new['departure_loss'],old['departure_loss'])
        self.assertIn(p.pid,new_candidates)
        self.assertGreater(new_candidates[p.pid]['importance'],old_candidates.get(p.pid,{}).get('importance',-1e9))
        self.assertEqual(new['decision'],'retain')
        self.assertIn(p,t.roster)
        self.assertEqual(p.contract.years,1)  # a recommendation is not a signing

    def test_post_hire_cutdown_keeps_complete_packages_and_core(self):
        for front,personnel in [('3-4','12'),('4-3','10')]:
            with self.subTest(front=front,personnel=personnel):
                L,t=fixture();t.gm.def_front='4-3' if front=='3-4' else '3-4'
                hire(L,t,front,personnel)
                before=RN.assess(t);coverage=RN.essential_coverage(t,report=before)
                keep=RN.select_cutdown(t,CD.rows_for(t),53)
                retained=[p for p in t.active() if p.pid in keep]
                after=RN.assess(t,retained)
                self.assertEqual(len(keep),53)
                self.assertTrue(RN.coverage_not_worse(coverage,RN.essential_coverage(t,report=after)))
                self.assertFalse(after['uncovered'])
                for pos in ('QB','C','LT','LG','RG','RT','K','P','LS'):
                    self.assertTrue(any(p.pos==pos for p in retained),pos)
                self.assertGreaterEqual(len(keep & {p.pid for p in t.roster}),53)

if __name__=='__main__':unittest.main()

"""A read-only counter search may reuse context, never a later request."""
import copy
import unittest
from contextlib import ExitStack
from unittest.mock import patch
import numpy as np

from cap_engine import Contract
from league import DraftPick, Team
from test_draft_planning import fixture, set_grade
import trades as TR
import trade_engine as TE
import trade_portfolio as TP
import views_personnel as VP


class AskSnapshotTests(unittest.TestCase):
    def test_negotiation_callbacks_are_pure_and_cached_search_matches_default(self):
        L,a=fixture();L.user_team='GB'
        for p in a.roster:p.contract=Contract(1,[1.]);p.age=27.
        b=Team('DEN','Continental West','Continental');b.league=L
        b.gm=copy.deepcopy(a.gm);b.record=[2,14,0];L.teams[b.abbr]=b
        L.set_phase('free_agency')
        p=copy.deepcopy(a.by_pos('HB')[0]);p.pid='arrival';p.team=b.abbr
        p.age=28.;p.contract=Contract(3,[10.]*3);set_grade(p,93)
        b.roster.append(p);L.players[p.pid]=p
        a.picks += [DraftPick(2026,r,str(r),a.abbr) for r in range(1,8)]
        callbacks={name:getattr(TR,name) for name in
                   ('package_football','_portfolio_trade_check','_financial_trade')}
        counts={name:0 for name in callbacks}
        def guard(name):
            def checked(*args,**kwargs):
                saved=L.save()
                result=callbacks[name](*args,**kwargs)
                self.assertEqual(L.save(),saved,name)
                counts[name]+=1
                return result
            return checked
        with patch.object(TR.VAL,'value_player',return_value={'apy':14}), ExitStack() as stack:
            for name in callbacks:stack.enter_context(patch.object(TR,name,side_effect=guard(name)))
            for phase,cleanup in (('free_agency',{}),('regular',{a.abbr:['HB2']})):
                L.set_phase(phase);L.week=2
                if phase=='regular':
                    for pick in a.picks:pick.year=L.year
                # Production currently returns no immediate cleanup in any
                # phase. Also exercise a supplied nonempty cleanup projection
                # so its temporary ledger cannot contaminate cached rosters.
                with patch.object(L,'_trade_roster_releases',return_value=cleanup):
                    target=TR.player_asset(L,b,p,[],None,need=True,viewer=a)
                    target['package_gain']=TP.RN.move_gain(a,p)
                    args=(L,a,b,target,TR.persona(a.gm),TR.persona(b.gm),
                          TR.context(a),TR.context(b),a.cap_space,b.cap_space,[])
                    old_counts=dict(counts)
                    with patch.object(TR,'remember_trade_rejection',
                                      wraps=TR.remember_trade_rejection) as remember:
                        # Both searches start with the same rejection memory.
                        # Repeat with the resulting memory to exercise live
                        # rejection checks as well as its first initialization.
                        for attempt in range(2):
                            notes=copy.deepcopy(getattr(L,'league_notes_sent',{}))
                            saved=L.save()
                            seed=np.random.default_rng(71)
                            actual=TR._negotiate(*args,seed)
                            actual_saved=L.save()
                            actual_notes=copy.deepcopy(L.league_notes_sent)
                            self.assertEqual(
                                {k:v for k,v in actual_notes.items() if k!='_rejected_trade_packages'},
                                {k:v for k,v in notes.items() if k!='_rejected_trade_packages'})
                            # Only the genuine rejection ledger may change;
                            # roster, contracts, cap and every other field stay fixed.
                            L.league_notes_sent=copy.deepcopy(notes)
                            self.assertEqual(L.save(),saved)
                            reference_rng=np.random.default_rng(71)
                            with patch.object(TP,'readonly_cache',side_effect=dict):
                                reference=TR._negotiate(*args,reference_rng)
                            self.assertEqual(actual,reference)
                            self.assertEqual(seed.bit_generator.state,reference_rng.bit_generator.state)
                            self.assertEqual(L.save(),actual_saved)
                        self.assertGreater(remember.call_count,0)
                        for call in remember.call_args_list:
                            _,buyer,seller,sends,gets=call.args
                            self.assertTrue(TR.trade_was_rejected(L,buyer,seller,sends,gets))
                    self.assertTrue(all(counts[k]>n+1 for k,n in old_counts.items()))

    def test_readonly_portfolio_cache_matches_validating_reads_and_is_discarded(self):
        L,t=fixture()
        for p in t.roster:p.contract=Contract(1,[1.])
        t.picks=[DraftPick(2026,r,t.abbr,t.abbr) for r in (1,2,3)]
        p=copy.deepcopy(t.by_pos('HB')[0]);p.pid='incoming';p.team='DEN'
        p.contract=Contract(4,[3.]*4);L.players[p.pid]=p
        cases=[([t.picks[0]],[]),([t.picks[1]],[p.pid]),
               ([t.picks[0],t.picks[1]],[p.pid])]
        previous=None
        for changed in ('initial','contract','gm','roster'):
            if changed=='contract':t.by_pos('QB')[0].contract=Contract(5,[2.]*5)
            if changed=='gm':t.gm.patience=1.;t.gm.risk=0.;t.gm.aggression=0.
            if changed=='roster':t.roster=[q for q in t.roster if q.pos!='HB']
            saved=L.save()
            expected=[TP.assess(L,t,sent,received) for sent,received in cases]
            # A new request owns a new snapshot, including changed contracts,
            # GM preferences and roster membership. Pick combinations and
            # hypothetical player exchanges still have distinct results.
            cache=TP.readonly_cache()
            with patch.object(TP,'_public_signature',wraps=TP._public_signature) as signatures, \
                 patch.object(TP.RN,'assess',wraps=TP.RN.assess) as roles:
                actual=[TP.assess(L,t,sent,received,cache=cache) for sent,received in cases]
                self.assertEqual(actual,expected)
                self.assertEqual(signatures.call_count,0)
                self.assertEqual(roles.call_count,2)
            self.assertEqual(L.save(),saved)
            if previous is not None:self.assertNotEqual(actual,previous)
            previous=actual

    def test_local_context_matches_fresh_evaluations_and_refreshes_next_request(self):
        L,a=fixture();L.user_team=a.abbr
        b=Team('DEN','Continental West','Continental');b.league=L
        b.gm=copy.deepcopy(a.gm);L.teams[b.abbr]=b;L.set_phase('free_agency')
        a.picks=[DraftPick(2026,r,a.abbr,a.abbr) for r in range(1,8)]
        b.picks=[DraftPick(2027,1,b.abbr,b.abbr)]
        target='2027-1-DEN'
        evaluate=TE.evaluate
        observed=[]
        def fresh(offer,ca,cb,sa,sb,*args,**kwargs):
            # Reprice every combination from live state as the original
            # search did, keeping real pick values and identical search order.
            live=(a.ctx(),b.ctx(),a.cap_space,b.cap_space)
            self.assertEqual((ca,cb,sa,sb),live)
            return evaluate(offer,*live,*args,**kwargs)
        with patch.object(TR,'cpu_trade_check',return_value=dict(approved=True)), \
             patch.object(TR,'seller_pick_counter',return_value=None):
            for changed in (False,True):
                if changed:
                    p=a.roster.pop(0);p.team=b.abbr;b.roster.append(p)
                    p.contract=Contract(2,[12.,14.]);a.sync_cap();b.sync_cap()
                    a.picks.pop()
                before=L.save()
                with patch.object(a,'ctx',wraps=a.ctx) as read_a, \
                     patch.object(b,'ctx',wraps=b.ctx) as read_b, \
                     patch.object(TE,'evaluate',wraps=evaluate) as prices:
                    actual=VP.act_ask(L,a.abbr,b.abbr,[],[target])
                    self.assertGreater(prices.call_count,10)
                    self.assertEqual(read_a.call_count,1)
                    self.assertEqual(read_b.call_count,1)
                    observed.append(prices.call_args_list[0].args[1:5])
                with patch.object(TE,'evaluate',side_effect=fresh):
                    self.assertEqual(VP.act_ask(L,a.abbr,b.abbr,[],[target]),actual)
                self.assertEqual(L.save(),before)
        self.assertNotEqual(observed[0],observed[1])


if __name__=='__main__':unittest.main()

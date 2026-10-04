"""Context-aware line awards preserve gameplay, legacy evidence and team context."""
import copy
import math
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import awards as A
import blocking_evaluation as B
import game as G
import league as L
import plays as P
import defensive_rush as D
from test_defensive_rush import unit, call
from test_protection_pressure import blocker


class BlockingAwardTests(unittest.TestCase):
    def setUp(self):
        self.off = dict(qb=dict(pid='qb'), ol=[blocker(p) for p in ('LT','LG','C','RG','RT')])
        self.defense = unit('4-3')
        self.rush = D.select_rush(self.defense, call('4-3'))

    def resolve(self, seed=1, **kw):
        return P.resolve_protection(self.off['ol'], self.rush['rushers'], np.random.default_rng(seed),
                                     assignments=self.rush['assignments'], **kw)

    def test_reference_does_not_depend_on_evaluated_players_own_grade(self):
        before=self.resolve()
        # RT has a solo edge assignment. His own skill changes actual wins,
        # but not the reference task used to judge those wins.
        self.off['ol'][-1].update(pass_block_rating=99,pass_block_power_rating=99,
                                 pass_block_finesse_rating=99,strength_rating=99,agility_rating=99)
        after=self.resolve()
        row=lambda p:next(r for r in p['pb_award'] if r[0]=='RT')
        self.assertEqual(row(before),row(after))

    def test_helper_is_compared_with_reference_helper_not_reference_primary(self):
        p=self.resolve()
        helpers=dict(p['pb_helpers'])
        self.assertTrue(helpers)
        helper=next(iter(helpers))
        evaluation=next(r for r in p['pb_model']['evaluations'] if r[0]==helper)
        self.assertFalse(evaluation[-1])
        index=evaluation[1]
        primary=next(r[0] for r in p['pb_model']['evaluations'] if r[1]==index and r[-1])
        person=next(b for b in self.off['ol'] if b['pid']==primary)
        person.update(pass_block_power_rating=99,pass_block_finesse_rating=99,pass_block_rating=99,
                      strength_rating=99,agility_rating=99)
        # Fix already-chosen help to isolate contribution, not coach assignment.
        matched=D.protection_pairs(self.off['ol'],self.rush['assignments'])
        oldhelpers=[[] for _ in matched]
        rusher=helpers[helper]
        i=next(i for i,r in enumerate(self.rush['rushers']) if r['pid']==rusher)
        oldhelpers[i]=[next(b for b in self.off['ol'] if b['pid']==helper)]
        with patch.object(D,'protection_helpers',return_value=oldhelpers):
            stronger=self.resolve()
        expectation=lambda p:next(r[1] for r in p['pb_award'] if r[0]==helper)
        self.assertGreater(expectation(stronger),expectation(p))

    def test_integration_is_deterministic_bounded_and_tracks_call_difficulty(self):
        p=self.resolve()
        before=copy.deepcopy(p['pb_model'])
        short=B.protection_evidence(p['pb_model'],P.PBW_THRESHOLD,hold=-.22,sack_k=P.SACK_K)
        deep=B.protection_evidence(p['pb_model'],P.PBW_THRESHOLD,hold=.4,sack_k=P.SACK_K)
        self.assertGreater(sum(r[3] for r in deep),sum(r[3] for r in short))
        self.assertEqual([r[:2] for r in short],[r[:2] for r in deep])
        self.assertEqual(before,p['pb_model'])
        self.assertEqual(deep,B.protection_evidence(p['pb_model'],P.PBW_THRESHOLD,hold=.4,sack_k=P.SACK_K))
        self.assertLessEqual(B._protection_evidence.cache_info().currsize,512)
        for row in deep:
            self.assertTrue(all(math.isfinite(v) and 0<=v<=1 for v in row[1:]))

    def test_zero_rush_and_nullified_plays_add_no_evaluation(self):
        p=P.resolve_protection(self.off['ol'],[],np.random.default_rng(1),assignments=[])
        self.assertEqual(p['pb_award'],[])
        book=G.StatBook()
        book.record(dict(self.resolve(),type='sack',nullified=True),{}, {},np.random.default_rng(1))
        self.assertEqual(book.p,{})

    def test_distribution_and_free_rusher_atom_match_analytic_probabilities(self):
        times=np.asarray([.5,1.,2.,2.5,4.,6.,10.])
        _,survival=B._distribution(times,3.5)
        exact=np.asarray([.5*math.erfc(math.log(t/3.5)/(.26*math.sqrt(2.))) for t in times])
        self.assertLess(float(np.max(np.abs(survival-exact))),1e-7)
        model=dict(means=[3.5,0.],free=[1],evaluations=[('LT',0,3.5,True)],qb_scale=1.)
        _,win,pressure,sack=B.protection_evidence(model,2.5)[0]
        self.assertAlmostEqual(pressure,1.-win,places=7)
        self.assertLess(sack,1e-8)

    def test_expectations_only_book_existing_contests_once_and_escape_reduces_sacks(self):
        book=G.StatBook()
        out=dict(type='incomplete',pb_reps=[('LT',True)],rb_reps=[('C',False)],
                 pb_award=[('LT',.9,.1,.05),('LT',.9,.1,.05),('idle',1,0,0)],
                 rb_award=[('C',.7),('C',.7),('idle',1)],pb_sack_survival=.6)
        book.record(out,self.off,{},np.random.default_rng(1))
        self.assertEqual(book.p['LT']['pb_eval_snaps'],1)
        self.assertAlmostEqual(book.p['LT']['pb_expected_sacks'],.03)
        self.assertEqual(book.p['C']['rb_eval_snaps'],1)
        self.assertNotIn('idle',book.p)

    def test_sack_to_scramble_keeps_expectations_but_not_actual_sack(self):
        import events
        from test_game_clock_decisions import ClockDecisions
        fixture=ClockDecisions();fixture.setUp()
        with patch.object(events,'scramble_chance',return_value=1.), \
             patch.object(events,'resolve_scramble',return_value=dict(type='scramble',yards=36,touchdown=True)):
            dr,book,_=fixture.drive([dict(type='sack',yards=-4,by='cb',beaten='lt',
                pb_reps=[('lt',False)],pb_award=[('lt',.9,.1,.04)],pressured=True)])
        line=book.p['lt']
        self.assertEqual(line['pb_eval_snaps'],1)
        self.assertEqual(line['pb_expected_sacks'],0.)
        self.assertEqual(line['sacks_allowed'],0)
        self.assertEqual(line['pressures_allowed'],1)
        self.assertEqual(line['pb_expected_pressures'],.1)

    def test_legacy_exact_formula_and_partial_evidence_is_additive(self):
        old=dict(pb_snaps=600,pb_wins=540,rb_snaps=400,rb_wins=280,
                 pressures_allowed=20,sacks_allowed=4)
        raw=100*.9+45*.7-260*(3*4+20)/600
        self.assertAlmostEqual(B.line_score(old),raw)
        part=dict(old,pb_eval_snaps=200,pb_expected_wins=180,
                  pb_expected_pressures=8,pb_expected_sacks=2,
                  rb_eval_snaps=100,rb_expected_wins=70)
        adjustment=(100*(200-180)+260*(3*2+8))/600-45*70/400
        self.assertAlmostEqual(B.line_score(part),raw+adjustment)
        self.assertIsNone(B.line_score(dict(old,pb_snaps=149)))

    def test_reference_execution_is_position_independent_and_shortfall_costs_points(self):
        line=dict(pb_snaps=600,pb_wins=540,rb_snaps=400,rb_wins=280,
                  pressures_allowed=20,sacks_allowed=4,pb_eval_snaps=600,
                  pb_expected_wins=540,pb_expected_pressures=20,pb_expected_sacks=4,
                  rb_eval_snaps=400,rb_expected_wins=280)
        for pos in A.OL_POS:
            self.assertAlmostEqual(A.Ballot.line_score(None,NS(pos=pos),line),100.)
        for key in ('sacks_allowed','pressures_allowed'):
            worse=dict(line);worse[key]+=1
            self.assertLess(B.line_score(worse),100.)
        self.assertLess(B.line_score(dict(line,pb_wins=530)),100.)
        self.assertLess(B.line_score(dict(line,rb_wins=270)),100.)

    def test_team_context_still_decides_otherwise_equal_protectors(self):
        players={pid:NS(pid=pid,pos='LT',team=pid) for pid in ('A','B')}
        l=dict(pb_snaps=600,pb_wins=540,rb_snaps=400,rb_wins=280,pb_eval_snaps=600,
               pb_expected_wins=540,rb_eval_snaps=400,rb_expected_wins=280)
        league=NS(year=2028,stats={2028:{pid:dict(l) for pid in players}},player=players.get,
                  teams={'A':NS(win_pct=.4),'B':NS(win_pct=.8)})
        self.assertEqual(A.Ballot(league).protector().pid,'B')

    def test_run_reference_accounts_for_opponent_not_our_skills(self):
        self.assertGreater(B.run_expectation(.6,P.RBW_THRESHOLD),B.run_expectation(.9,P.RBW_THRESHOLD))
        self.assertAlmostEqual(B.run_expectation(.8,P.RBW_THRESHOLD),.6368306512,places=8)

    def test_run_evidence_reaches_touchdown_and_non_touchdown_returns(self):
        from test_run_support_attributes import offense
        off=offense();seen=set()
        for ytg in (1,60):
            for seed in range(30):
                out=P._run_play(off,self.defense,dict(scheme='inside_zone'),
                    dict(call('4-3'),front='4-3 over',box=7),ytg,np.random.default_rng(seed))
                self.assertEqual({p for p,_ in out['rb_reps']},{p for p,_ in out['rb_award']})
                self.assertEqual(len(out['rb_award']),len(set(p for p,_ in out['rb_award'])))
                seen.add(bool(out.get('touchdown')))
        self.assertEqual(seen,{True,False})

    def test_new_measurements_survive_game_season_career_and_reload(self):
        league=L.League(2027)
        league.players['lt']=L.Player('lt','Test','LT',25,{},team='GB')
        old=dict(pb_snaps=200,pb_wins=180)
        new=dict(pb_snaps=300,pb_wins=285,pb_eval_snaps=300,pb_expected_wins=270.,
                 pb_expected_pressures=4.5,pb_expected_sacks=1.25,rb_snaps=200,
                 rb_wins=150,rb_eval_snaps=200,rb_expected_wins=135.)
        league.record_stats(2027,'lt',old,game='old')
        league.record_stats(2027,'lt',new,game='new')
        expected=copy.deepcopy(league.stats[2027]['lt'])
        restored=L.League.load(league.save())
        for row in (restored.stats[2027]['lt'],restored.players['lt'].career[2027]):
            for k,v in expected.items():self.assertEqual(row[k],v)
            self.assertEqual(B.line_score(row),B.line_score(expected))
        for k,v in new.items():self.assertEqual(restored.game_stats['new']['lt'][k],v)


if __name__=='__main__':unittest.main()

"""Roster repairs add coverage atomically without churning new acquisitions."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

import financial_plan as FP
import game_availability as GA
import practice_squad as PS
import targets as TG
from cap_engine import Contract
from league import Team
from test_draft_planning import set_grade
import test_roster_cap_recovery as recovery_fixture


class DepthRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = recovery_fixture.RecoveryTests().roster()[0]
        cls.templates = {p.pos: copy.deepcopy(p) for p in cls.base.teams['MIN'].roster}

    def fixture(self):
        L = copy.deepcopy(self.base)
        L.set_phase('regular'); L.week = 1
        t = L.teams['MIN']; t.cap.cap = 500; t.sync_cap()
        return L,t

    def move_position(self,p,pos,grade=55):
        p.pos=pos; p.ratings={k:grade for k in TG.DEPTH_WEIGHTS[pos]}

    def arrival(self,L,pos,pid,grade=70,source=None):
        p=copy.deepcopy(self.templates[pos]); p.pid=pid; p.name=pid
        p.team=source; p.contract=None; p.xp_spent={}; p.out_until=None
        p.draft_round=None; p.draft_year=None; p.accrued=1; p._team_ref=None
        set_grade(p,grade); L.players[pid]=p
        if source:
            if source not in L.teams:
                t=Team(source,'United North','United'); t.league=L; L.teams[source]=t
            PS.squad(L.teams[source]).append(p)
        else:L.free_agents.append(pid)
        return p

    def test_all_three_routes_add_backup_without_cutting_only_qb(self):
        for route in ('street','callup','poach'):
            with self.subTest(route=route):
                L,t=self.fixture(); starter=t.by_pos('QB')[0]
                self.move_position(t.by_pos('QB')[-1],'RT')
                p=self.arrival(L,'QB','backup',65,
                    None if route=='street' else t.abbr if route=='callup' else 'DEN')
                before={q.pid for q in t.roster}
                actual=FP.evaluate
                with patch.object(FP,'evaluate',wraps=actual) as budget, \
                     patch.object(PS,'_make_room',side_effect=AssertionError('replanned after approval')):
                    if route=='street':ok=PS.sign_minimum(L,t.abbr,p,essential=True)
                    elif route=='callup':ok=PS.call_up(L,t.abbr,p.pid,emergency=True)
                    else:ok=PS.poach(L,t.abbr,p.pid,1,essential=True)
                self.assertTrue(ok); self.assertIn(starter,t.roster)
                self.assertEqual(len(t.by_pos('QB')),2); self.assertEqual(len(t.active()),54)
                self.assertEqual(before-{q.pid for q in t.roster},set())
                self.assertEqual(budget.call_args.kwargs['removals'],[])
                GA.settle_roster(L,t,1)
                self.assertEqual(len(t.active()),53)
                self.assertIn(starter,t.roster); self.assertIn(p,t.roster)
                self.assertFalse(PS.essential_depth(t,week=1)['shortages'])

    def test_two_tight_ends_added_without_same_pass_or_repeat_churn(self):
        L,t=self.fixture()
        for p in t.by_pos('TE'):self.move_position(p,'DT')
        first=self.arrival(L,'TE','own-te',72,t.abbr)
        second=self.arrival(L,'TE','street-te',68)
        PS.keep_groups_whole(L,np.random.default_rng(1),1)
        self.assertIn(first,t.roster); self.assertIn(second,t.roster)
        self.assertEqual(len(t.by_pos('TE')),2)
        self.assertFalse(PS.essential_depth(t,week=1)['shortages'])
        self.assertFalse(any(e['kind']=='release' and e.get('pid') in (first.pid,second.pid)
                             for e in L.transactions))
        before=list(L.transactions)
        self.assertEqual(PS.keep_groups_whole(L,np.random.default_rng(2),1),[])
        self.assertEqual(before,L.transactions)

    def test_injury_cover_keeps_injured_incumbent_and_healthy_backup(self):
        L,t=self.fixture(); incumbent,backup=t.by_pos('QB')
        incumbent.out_until=6
        p=self.arrival(L,'QB','cover',65)
        self.assertTrue(PS.sign_minimum(L,t.abbr,p,essential=True))
        self.assertIn(incumbent,t.roster); self.assertIn(backup,t.roster)
        self.assertEqual(PS.essential_depth(t,week=1)['counts']['QB'],2)
        self.assertEqual(incumbent.out_until,6)

    def test_short_return_does_not_force_permanent_qb_repair(self):
        L,t=self.fixture(); t.by_pos('QB')[0].out_until=2
        p=self.arrival(L,'QB','cover',65)
        self.assertNotIn('QB',PS.essential_depth(t,week=1)['shortages'])
        PS.keep_groups_whole(L,np.random.default_rng(2),1)
        self.assertIn(p.pid,L.free_agents)

    def test_cap_failure_is_atomic(self):
        L,t=self.fixture(); self.move_position(t.by_pos('QB')[-1],'RT')
        p=self.arrival(L,'QB','backup',65,t.abbr)
        t.cap.cap=-100; before=list(t.roster); logs=list(L.transactions)
        self.assertFalse(PS.call_up(L,t.abbr,p.pid,emergency=True))
        self.assertEqual(before,t.roster);self.assertEqual(logs,L.transactions)
        self.assertIn(p,PS.squad(t));self.assertIsNone(p.contract)

    def test_budget_refusal_tries_another_safe_departure_before_mutation(self):
        L,t=self.fixture(); starter=t.by_pos('QB')[0]
        self.move_position(t.by_pos('QB')[-1],'RT')
        p=self.arrival(L,'QB','backup',65)
        t.cap.cap=t.cap.charges(t.phase)+.3
        before={q.pid for q in t.roster}; calls=[]
        def budget(*args,**kw):
            self.assertEqual(before,{q.pid for q in t.roster})
            calls.append(kw['removals'][0]);return dict(approved=len(calls)>1)
        with patch.object(FP,'evaluate',side_effect=budget):
            self.assertTrue(PS.sign_minimum(L,t.abbr,p,essential=True))
        self.assertEqual(len(calls),2);self.assertNotEqual(*calls)
        self.assertEqual(before-{q.pid for q in t.roster},{calls[-1]})
        self.assertIn(starter,t.roster)

    def test_no_safe_surplus_refuses_without_releasing_starter(self):
        L,t=self.fixture(); self.move_position(t.by_pos('QB')[-1],'RT')
        p=self.arrival(L,'QB','backup',65)
        for q in t.roster:q.contract=Contract(4,[1]*4,signing_bonus=20)
        t.sync_cap();before=list(t.roster)
        # Inflate incumbent dead money to isolate departure protection, without
        # also inflating the replacement's asking price through those comps.
        with patch('valuation.value_player', return_value={'apy': 1.}):
            self.assertTrue(PS.sign_minimum(L,t.abbr,p,essential=True))
        self.assertEqual(t.roster[:-1],before)
        self.assertEqual(len(t.active()),54)
        self.assertIn(p,t.roster)

    def test_recent_acquisition_is_not_optional_upgrade_departure(self):
        L,t=self.fixture(); recent=t.by_pos('WR')[-1];set_grade(recent,60)
        L.log('sign',pid=recent.pid,team=t.abbr)
        p=self.arrival(L,'WR','upgrade',95)
        self.assertTrue(PS.sign_minimum(L,t.abbr,p))
        self.assertIn(recent,t.roster); self.assertIn(p,t.roster)

    def test_healthy_specialist_upgrade_replaces_specialist_not_unrelated_depth(self):
        L,t=self.fixture(); old=t.by_pos('P')[0]
        p=self.arrival(L,'P','new-punter',95)
        self.assertTrue(PS.protected(t,old,L))
        self.assertFalse(PS.protected(t,old,L,incoming=p))
        before={q.pid for q in t.roster}
        self.assertTrue(PS.sign_minimum(L,t.abbr,p))
        self.assertEqual(len(t.by_pos('P')),2)
        self.assertEqual(before-{q.pid for q in t.roster},set())
        GA.settle_roster(L,t,1)
        self.assertEqual(t.by_pos('P'),[p])
        self.assertEqual(before-{q.pid for q in t.roster},{old.pid})

    def test_injured_poach_cannot_count_as_replacement_or_unlock_specialist(self):
        L,t=self.fixture(); p=self.arrival(L,'P','hurt-punter',95,'DEN');p.out_until=5
        self.assertTrue(PS.protected(t,t.by_pos('P')[0],L,incoming=p))
        self.assertFalse(PS.poach(L,t.abbr,p.pid,1,essential=True))
        self.assertIn(p,PS.squad(L.teams['DEN']))

    def test_coach_skill_requirements_and_ol_flexibility(self):
        L,t=self.fixture(); t.gm.off_personnel='13'
        for p in t.by_pos('C'):self.move_position(p,'LG',75)
        r=PS.essential_depth(t,week=1)
        self.assertEqual(r['floors']['TE'],4);self.assertEqual(r['floors']['QB'],2)
        self.assertEqual(r['shortages']['TE'],1);self.assertNotIn('C',r['shortages'])
        self.assertNotIn('OL',r['shortages'])

    def test_preseason_emergency_callup_respects_53_and_native_backup(self):
        L,t=self.fixture();L.set_phase('offseason')
        self.move_position(t.by_pos('QB')[-1],'RT')
        p=self.arrival(L,'QB','backup',65,t.abbr)
        self.assertTrue(PS.minimum_fits(L,t,p,essential=True))
        self.assertTrue(PS.call_up(L,t.abbr,p.pid,emergency=True))
        self.assertEqual(len(t.active()),54)
        GA.settle_roster(L,t,1)
        self.assertEqual(len(t.active()),53);self.assertEqual(len(t.by_pos('QB')),2)


if __name__=='__main__':unittest.main()

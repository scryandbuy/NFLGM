"""Staff contracts, saved decisions, full market and between-game staffing."""
import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch, Mock

import numpy as np
import staff as ST
from session import Session
import views_frontoffice as VF


def coach(name, role='oc', team='A', rating=65, years=0):
    c = ST.Coach(name, role, rating, 50, 'pass protection', 45, years, team)
    c.salary = 1.2; c.staff_traits = []; c.history = [(2026, team, role)]
    return c


def league():
    t = NS(abbr='A', staff={r: coach(r, r) for r in ST.ROLES},
           gm=NS(name='Head Coach', salary=8, patience=.5), owner_spend=.5, roster=[])
    L = NS(year=2028, week=8, phase='regular', teams={'A': t}, staff_pool=[], user_team='A', poaches=[], interviews={})
    L.events=[]; L.log=lambda kind, **kw: L.events.append((kind, kw))
    return L


class StaffContracts(unittest.TestCase):
    def setUp(self):
        self.L=league(); self.patch=patch('inbox.reconcile'); self.patch.start(); self.addCleanup(self.patch.stop)

    def test_renewal_and_expiry_require_explicit_decisions(self):
        L=self.L
        self.assertFalse(ST.finish_renewals(L,'A')['ok'])
        ST.choose_expiry(L,'A','oc'); self.assertEqual(L.teams['A'].staff['oc'].name,'oc')
        ST.choose_expiry(L,'A','oc',False)
        self.assertIn('oc',ST.unresolved_expirations(L,'A'))
        self.assertTrue(ST.extend(L,'A','oc',3)['ok'])
        for role in ('dc','st','scout'): ST.choose_expiry(L,'A',role)
        self.assertTrue(ST.finish_renewals(L,'A')['ok'])
        self.assertEqual(L.teams['A'].staff['oc'].years,3)
        self.assertEqual(len(L.staff_pool),3)
        self.assertTrue(ST.finish_renewals(L,'A')['ok'])
        self.assertEqual(len(L.staff_pool),3)

    def test_choices_persist_and_do_not_release_replacement(self):
        L=self.L; ST.choose_expiry(L,'A','oc')
        saved=json.loads(json.dumps(ST.to_dict(L))); other=league(); ST.from_dict(other,saved)
        self.assertNotIn('oc',ST.unresolved_expirations(other,'A'))
        other.teams['A'].staff['oc']=coach('Replacement')
        self.assertIn('oc',ST.unresolved_expirations(other,'A'))
        other.year+=1
        self.assertEqual(ST.expiry_choices(other,'A'),{})

    def test_renewal_cancels_departure_and_counts_only_salary_delta(self):
        L=self.L; ST.choose_expiry(L,'A','oc'); before=ST.payroll(L.teams['A'])
        self.assertTrue(ST.extend(L,'A','oc',5,3)['ok'])
        self.assertAlmostEqual(ST.payroll(L.teams['A'])-before,1.8)
        self.assertNotIn('oc',ST.expiry_choices(L,'A'))
        self.assertFalse(ST.choose_expiry(L,'A','oc')['ok'])

    def test_firm_refusal_and_budget_guard(self):
        L=self.L; L.teams['A'].staff['oc'].disgruntled=2027
        self.assertFalse(ST.extend(L,'A','oc')['ok'])
        self.assertTrue(ST.choose_expiry(L,'A','oc')['ok'])
        self.assertFalse(ST.extend(L,'A','dc',salary=100)['ok'])

    def test_midseason_hire_and_release_refresh_without_live_changes(self):
        L=self.L; s=Session.__new__(Session); s.L=L;s.user_team='A'
        s.runner=Mock();s.runner.live={'done':False}
        candidate=coach('New',team=None,years=3);L.staff_pool.append(candidate)
        for action, kw in [('staff_release',dict(role='oc')),('staff_extend',dict(role='oc')),('staff_hire',dict(name='New')),('staff_expiry',dict(role='oc'))]:
            self.assertFalse(s.frontoffice_act(action,**kw)['ok'])
        s.runner.live={'done':True}
        self.assertTrue(s.frontoffice_act('staff_release',role='oc')['ok'])
        self.assertTrue(s.frontoffice_act('staff_hire',name='New',years=4)['ok'])
        self.assertEqual(L.teams['A'].staff['oc'].name,'New')
        self.assertTrue(s.save_dirty)
        self.assertIn('A:oc',L.staff_reviews['hired'])
        self.assertEqual(s.runner.refresh.call_count,2)
        self.assertEqual(s.runner._staff_terms.call_count,2)

    def test_full_market_and_no_hiring_employed_coach(self):
        L=self.L
        L.staff_pool=[coach(f'Candidate {i}',team=None,rating=50+i) for i in range(14)]
        employed=coach('Employed',team='B');L.staff_pool.append(employed)
        s=NS(stop=('week',8),runner=None,OFFSEASON=Session.OFFSEASON)
        with patch('views_frontoffice.rail',return_value={}): v=VF.staff(s,L,'A')
        self.assertEqual(len(v['pools']['oc']),14)
        self.assertFalse(ST.hire(L,'A','Employed')['ok'])
        self.assertFalse(v['staff_locked'])

    def test_combined_calendar_and_actual_step_releases_only_choices(self):
        self.assertEqual(Session.OFFSEASON[2][1],'step_coaching')
        self.assertEqual(Session.OFFSEASON[3][1],'step_extensions')
        steps = [step for _label, step in Session.OFFSEASON]
        self.assertEqual(steps.index('step_draft'), steps.index('step_visits') + 1)
        s=Session.__new__(Session);s.L=self.L;s.user_team='A';s.rng=np.random.default_rng(2)
        for r in ST.ROLES: ST.choose_expiry(self.L,'A',r)
        with patch('waivers.process') as wire:
            s.step_staff_contracts();wire.assert_called_once()
        self.assertTrue(all(c is None for c in self.L.teams['A'].staff.values()))


class MidseasonReview(unittest.TestCase):
    def setUp(self):
        self.patch=patch('inbox.reconcile');self.patch.start();self.addCleanup(self.patch.stop)
        self.L=league();L=self.L;L.user_team='T31';L.schedule=[];L.game_stats={};L.teams={}
        for i in range(32):
            a=f'T{i:02}'; t=league().teams['A'];t.abbr=a;t.staff={r:coach(a+r,r,team=a,years=2) for r in ST.ROLES};L.teams[a]=t
        L.staff_pool=[coach('Better OC',team=None,rating=86,years=3),coach('Better DC','dc',team=None,rating=86,years=3)]
        for week in range(1,9):
            for i in range(0,32,2):
                h,a=f'T{i:02}',f'T{i+1:02}'
                L.schedule.append((week,a,h,24,10))
                L.game_stats[f'{L.year}-{week}-{h}-{a}']={h:{'team':h,'pass_plays':40,'rush_plays':20,'pass_epa':-40 if i==0 else 5,'rush_epa':0},a:{'team':a,'pass_plays':40,'rush_plays':20,'pass_epa':6,'rush_epa':0}}
        self.rng=Mock();self.rng.random.return_value=0
        import gameplan_week as GW
        self.grades={k:75 for k in GW.UNITS}
        self.gpatch=patch('gameplan_week.unit_grades',return_value=self.grades);self.gpatch.start();self.addCleanup(self.gpatch.stop)

    def test_only_sustained_bad_unit_replaced_and_saved_review_not_repeated(self):
        before={a:{r:c.name for r,c in t.staff.items()} for a,t in self.L.teams.items()}
        moves=ST.midseason_review(self.L,self.rng,8)
        self.assertEqual([(m['team'],m['role']) for m in moves],[('T00','oc')])
        for a,t in self.L.teams.items():
            for r,c in t.staff.items():
                if (a,r)!=('T00','oc'): self.assertEqual(c.name,before[a][r])
        saved=json.loads(json.dumps(ST.to_dict(self.L)));ST.from_dict(self.L,saved)
        self.assertEqual(ST.midseason_review(self.L,self.rng,8),[])
        self.assertEqual(ST.midseason_review(self.L,self.rng,11),[])

    def test_defense_uses_opponent_epa_and_not_current_roster(self):
        ev=ST.midseason_evidence(self.L,8)
        self.assertGreater(ev['T01']['units']['dc'][0][0],ev['T03']['units']['dc'][0][0])
        self.assertLess(ev['T00']['units']['oc'][0][0],ev['T02']['units']['oc'][0][0])
        # There are intentionally no players on these present-day rosters.
        self.assertNotIn('st',ev['T00']['units'])

    def test_no_early_review_missing_stats_no_upgrade_or_unaffordable(self):
        self.assertEqual(ST.midseason_review(self.L,self.rng,5),[])
        original=copy.deepcopy(self.L)
        for change in ('missing','unaffordable','no_upgrade','user','new_hire','injury','winning','weak_roster'):
            with self.subTest(change=change):
                L=copy.deepcopy(original)
                if change=='missing':L.game_stats={}
                if change=='unaffordable':L.teams['T00'].gm.salary=22
                if change=='no_upgrade':L.staff_pool=[]
                if change=='user':L.user_team='T00'
                if change=='new_hire':ST._reviews(L)['hired']['T00:oc']=7
                if change=='injury':L.teams['T00'].roster=[NS(pos='QB',retired=False,out_until=12,ovr=88)]
                if change=='winning':L.schedule=[(w,a,h,ap,30 if h=='T00' else hp) for w,a,h,ap,hp in L.schedule]
                if change=='weak_roster':self.gpatch.stop();self.gpatch=patch('gameplan_week.unit_grades',side_effect=lambda league,t,healthy_only=True:{k:40 if t.abbr=='T00' else 75 for k in self.grades});self.gpatch.start()
                self.assertEqual(ST.midseason_review(L,self.rng,8),[])

    def test_review_state_bounded_to_current_year(self):
        ST._reviews(self.L)['weeks']=[8,11,14]; self.L.year+=1
        self.assertEqual(ST._reviews(self.L)['weeks'],[])

    def test_improving_unit_is_not_fired_for_old_results(self):
        for key,book in self.L.game_stats.items():
            if int(key.split('-')[1])>=6 and 'T00' in book:
                book['T00']['pass_epa']=40
        self.assertEqual(ST.midseason_review(self.L,self.rng,8),[])

    def test_no_special_teams_firing_for_one_specialist_slump(self):
        for book in self.L.game_stats.values():
            for abbr,line in book.items():
                line.update(fg_att=2,fg_made=0 if abbr=='T00' else 2,punts=5,punt_net_yds=250 if abbr=='T00' else 200)
                if abbr=='T00':line['pass_epa']=5
        self.assertIn('st',ST.midseason_evidence(self.L,8)['T00']['units'])
        self.L.staff_pool.append(coach('Better ST','st',team=None,rating=90))
        self.assertEqual(ST.midseason_review(self.L,self.rng,8),[])


if __name__=='__main__':unittest.main()

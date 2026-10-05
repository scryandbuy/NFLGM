import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
import numpy as np
import roster_needs as RN, cutdown as CD, targets as TG
from league import Player
from cap_engine import Contract
from test_draft_planning import fixture,set_grade

class EssentialRosterTests(unittest.TestCase):
    def roster(self):
        L,t=fixture();L.set_phase('offseason');L.week=0;t.phase='season'
        keep=RN.select_cutdown(t,CD.rows_for(t),53)
        t.roster=[p for p in t.roster if p.pid in keep]
        for p in list(t.roster):
            if p.pos=='C':p.pos='LT'
        t.cap.cap=300;t.sync_cap()
        p=Player('streetC','Street Center','C',28,{k:76. for k in TG.DEPTH_WEIGHTS['C']})
        L.players[p.pid]=p;L.free_agents.append(p.pid)
        return L,t,p
    def test_native_center_is_essential_despite_fieldability(self):
        L,t,p=self.roster();r=RN.assess(t)
        self.assertNotIn('C',r['uncovered'])
        self.assertEqual(RN.essential_coverage(t,report=r)['shortages']['offense:C:0'],1)
        self.assertTrue(CD.violations(L))
    def test_funded_swap_at_53(self):
        L,t,p=self.roster();before=RN.essential_coverage(t)
        self.assertGreater(CD.repair_shape(L),0)
        self.assertEqual(len(t.active()),53);self.assertIn(p,t.roster)
        after=RN.essential_coverage(t)
        self.assertNotIn('offense:C:0',after['shortages'])
        self.assertTrue(RN.coverage_not_worse(before,after));self.assertGreaterEqual(t.cap_space,0)
    def test_user_is_untouched(self):
        L,t,p=self.roster();L.user_team=t.abbr;before=list(t.roster)
        CD.repair_shape(L);self.assertEqual(t.roster,before)
    def test_cap_and_protection(self):
        L,t,p=self.roster();before=list(t.roster)
        # These assertions isolate release/signing guards. An internal OL
        # conversion can legally fill the job without releasing a protected
        # player or spending any cap, and is covered separately below.
        with patch('cutdown._cross_train_line',return_value=False), patch('practice_squad.protected',return_value=True):self.assertEqual(CD.repair_shape(L),0)
        self.assertEqual(t.roster,before)
        with patch('cutdown._cross_train_line',return_value=False), patch('cap_accounting.require_room',side_effect=ValueError('no room')):self.assertEqual(CD.repair_shape(L),0)
        self.assertEqual(t.roster,before)
    def test_atl_linebacker_summary_matches_package(self):
        L,t=fixture();t.gm.def_front='3-4'
        # coach_front uses the actual GM front field below.
        t.gm.front='3-4'
        for p in t.roster:
            if p.pos=='WILL':set_grade(p,50)
            if p.pos=='MIKE':set_grade(p,88)
        r=RN.assess(t)
        for a in r['assignments']:
            if a['role']=='RILB':
                self.assertEqual(a['player'].pos,'MIKE')
                self.assertGreater(a['grade'],75)
                return
        self.fail('No 3-4 RILB assignment')
    def test_real_protected_picks_and_negative_cap(self):
        L,t,p=self.roster();before=list(t.roster)
        for q in t.roster:q.draft_round=1;q.draft_year=L.year
        with patch('cutdown._cross_train_line',return_value=False):self.assertEqual(CD.repair_shape(L),0)
        self.assertEqual(t.roster,before)
        for q in t.roster:q.draft_round=None
        t.cap.cap=.1
        with patch('cutdown._cross_train_line',return_value=False):self.assertEqual(CD.repair_shape(L),0)
        self.assertEqual(t.roster,before)

    def test_protected_roster_can_fill_center_internally_without_spending(self):
        L,t,p=self.roster();before={q.pid for q in t.active()};cap=t.cap_space
        for q in t.roster:q.draft_round=1;q.draft_year=L.year
        self.assertEqual(CD.repair_shape(L),1)
        self.assertEqual({q.pid for q in t.active()},before)
        self.assertEqual(t.cap_space,cap)
        self.assertIsNone(p.team)
        self.assertNotIn('offense:C:0',RN.essential_coverage(t)['shortages'])
        self.assertTrue(all(x['kind']=='position_change' for x in L.transactions))

    def test_te_fullback_is_acceptable_and_reserve_floors_soft(self):
        L,t=fixture();t.gm.off_personnel='21'
        t.roster=[p for p in t.roster if p.pos!='FB']
        for p in t.roster:
            if p.pos=='TE':
                p.ratings.update(run_block_rating=90,lead_block_rating=90,
                                 impact_block_rating=90,strength_rating=90)
        report=RN.assess(t);coverage=RN.essential_coverage(t,report=report)
        fb=next(r for r in report['assignments'] if r['role']=='FB')
        self.assertEqual(fb['player'].pos,'TE')
        self.assertNotIn('offense:FB:0',coverage['shortages'])
        self.assertTrue(all(not key.startswith(('OL:', 'DB:', 'DL:')) for key in coverage['shortages']))

    def test_rare_heavy_vacancy_is_essential_and_repaired(self):
        L,t=fixture();t.gm.def_front='4-3';t.phase='season'
        keep=RN.select_cutdown(t,CD.rows_for(t),53)
        t.roster=[p for p in t.roster if p.pid in keep]
        tackles=[p for p in t.roster if p.pos=='DT']
        for p in tackles[2:]:p.pos='LEDG'
        t.cap.cap=300;t.sync_cap()
        before=RN.essential_coverage(t)
        self.assertEqual(before['shortages']['defense:DT:2'],2)
        p=Player('heavyDT','Heavy Tackle','DT',28,{k:76. for k in TG.DEPTH_WEIGHTS['DT']})
        L.players[p.pid]=p;L.free_agents.append(p.pid)
        self.assertGreater(CD.repair_shape(L),0)
        self.assertEqual(len(t.active()),53);self.assertGreaterEqual(t.cap_space,0)
        self.assertNotIn('defense:DT:2',RN.essential_coverage(t)['shortages'])
        report=RN.assess(t)
        variants={r['variant'] for r in report['package_assignments']}
        for variant in variants:
            rows=[r for r in report['package_assignments'] if r['variant']==variant]
            self.assertEqual(len({r['player'].pid for r in rows if r['player']}),11,variant)
        import defense_roles as DR
        depth=RN._planning_depth(t.active(),report['_grades'])
        for package in ('base','nickel','dime','heavy'):
            rows=DR.assign(depth,'4-3',package)
            self.assertEqual(len({DR.pid(r['player']) for r in rows if r['player']}),11)
            if package=='heavy':
                nose=next(r for r in rows if r['alignment']=='nose')
                self.assertEqual(DR.position(nose['player']),'DT')

    def test_low_share_quality_remains_soft_and_slot_identity_stable(self):
        L,t=fixture();t.gm.def_front='4-3'
        report=RN.assess(t)
        heavy=[r for r in report['package_assignments'] if r['package']=='heavy']
        self.assertTrue(heavy)
        for r in heavy:
            r['weight']=.005;r['grade']=40
        baseline=RN.essential_coverage(t,report=report)
        self.assertNotIn('defense:DT:2',baseline['shortages'])
        for r in heavy:
            if r['role']=='DT' and r['slot']==2:r['player']=None;r['grade']=None
        after=RN.essential_coverage(t,report=report)
        self.assertEqual(after['shortages']['defense:DT:2'],2)
        self.assertFalse(RN.coverage_not_worse(baseline,after))
        for r in heavy:r['weight']=0
        self.assertNotIn('defense:DT:2',RN.essential_coverage(t,report=report)['shortages'])

    def test_coverage_rejects_new_hole(self):
        before={'shortages':{'offense:C:0':1}}
        self.assertFalse(RN.coverage_not_worse(before,{'shortages':{'offense:QB:0':2}}))
        self.assertTrue(RN.coverage_not_worse(before,{'shortages':{}}))

if __name__=='__main__':unittest.main()

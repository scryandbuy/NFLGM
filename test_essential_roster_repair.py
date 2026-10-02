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
        with patch('practice_squad.protected',return_value=True):self.assertEqual(CD.repair_shape(L),0)
        self.assertEqual(t.roster,before)
        with patch('cap_accounting.require_room',side_effect=ValueError('no room')):self.assertEqual(CD.repair_shape(L),0)
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
        self.assertEqual(CD.repair_shape(L),0)
        self.assertEqual(t.roster,before)
        for q in t.roster:q.draft_round=None
        t.cap.cap=.1
        self.assertEqual(CD.repair_shape(L),0)
        self.assertEqual(t.roster,before)

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

    def test_coverage_rejects_new_hole(self):
        before={'shortages':{'offense:C:0':1}}
        self.assertFalse(RN.coverage_not_worse(before,{'shortages':{'offense:QB:0':2}}))
        self.assertTrue(RN.coverage_not_worse(before,{'shortages':{}}))

if __name__=='__main__':unittest.main()

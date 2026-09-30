import copy
import unittest
from types import SimpleNamespace
import defense_roles as D


class DefensivePlanningTests(unittest.TestCase):
    def test_multiple_retains_both_fronts_and_eleven_jobs(self):
        p=D.planning_profile(SimpleNamespace(def_front='multiple',box=.9))
        self.assertEqual({v['front'] for v in p['variants'] if v['package']=='base'},{'4-3','3-4'})
        self.assertAlmostEqual(sum(p['packages'].values()),1)
        self.assertAlmostEqual(sum(r['demand'] for r in p['roles']),11)
        self.assertTrue(all(v['share']>0 and len(v['slots'])==11 for v in p['variants']))
        self.assertTrue(all(x>0 for x in p['packages'].values()))
        self.assertTrue(any(r['specialist']=='tampa_middle' for r in p['roles']))
        self.assertTrue(any(r['specialist']=='big_nickel' for r in p['roles']))

    def test_cache_pure_and_subpackage_preference(self):
        gm=SimpleNamespace(def_front='3-4')
        original=copy.deepcopy(gm.__dict__)
        a=D.planning_profile(gm)
        a['variants'].clear()
        self.assertTrue(D.planning_profile(gm)['variants'])
        self.assertEqual(gm.__dict__,original)
        lighter=D.planning_profile(gm,{'sub_lean':1})
        heavier=D.planning_profile(gm,{'sub_lean':-1})
        self.assertGreater(lighter['packages']['dime'],heavier['packages']['dime'])

    def test_specialist_grades_and_position_gates(self):
        anchor=dict(pos='DT',weight=325,ratings=dict(strength_rating=95,block_shed_rating=95,tackle_rating=85,play_rec_rating=80))
        speed=dict(pos='DT',weight=285,ratings=dict(strength_rating=65,block_shed_rating=65,power_moves_rating=90,finesse_moves_rating=95,acceleration_rating=95))
        self.assertGreater(D.candidate_grade(anchor,'NT'),D.candidate_grade(speed,'NT'))
        self.assertGreater(D.candidate_grade(speed,'DT'),D.candidate_grade(anchor,'DT'))
        self.assertEqual(D.candidate_grade(dict(pos='MIKE',ovr=99,ratings={}),'LOLB'),0)
        self.assertEqual(D.candidate_grade(dict(pos='REDG',ovr=80,ratings={}),'LOLB'),80)
        zone=dict(pos='CB',ratings=dict(zone_cover_rating=95,play_rec_rating=95,awareness_rating=95,speed_rating=80,man_cover_rating=50,press_rating=50,agility_rating=60))
        self.assertGreater(D.candidate_grade(zone,'CB','zone_corner'),D.candidate_grade(zone,'CB','man_corner'))


if __name__=='__main__': unittest.main()

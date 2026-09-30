import copy
import unittest
from types import SimpleNamespace
import defense_roles as D


class DefensivePlanningTests(unittest.TestCase):
    def test_automatic_specialists_and_pins(self):
        counts=dict(LEDG=2,REDG=2,DT=5,MIKE=2,WILL=2,SAM=2,CB=5,FS=2,SS=2)
        depth={pos:[dict(pid=pos+str(i),pos=pos,ovr=65,ratings={}) for i in range(n)] for pos,n in counts.items()}
        nose=dict(pid='nose',pos='DT',weight=325,ovr=90,ratings={})
        depth['DT'].append(nose)
        rows=D.assign(depth,'3-4','base')
        self.assertEqual(next(r['player']['pid'] for r in rows if r['role']=='NT'),'nose')
        pinned=D.assign(depth,'3-4','base',pins={'NT':['DT0']})
        self.assertEqual(next(r['player']['pid'] for r in pinned if r['role']=='NT'),'DT0')
        depth['MIKE'].append(dict(pid='newlb',pos='MIKE',ovr=90,ratings={}))
        rows=D.assign(depth,'4-3','dime')
        self.assertEqual(next(r['player']['pid'] for r in rows if r['role']=='MIKE'),'newlb')
        rows=D.assign(depth,'4-3','dime',pins={'MIKE':['MIKE0']})
        self.assertEqual(next(r['player']['pid'] for r in rows if r['role']=='MIKE'),'MIKE0')
        depth['SS'].append(dict(pid='slot',pos='SS',ovr=95,ratings={}))
        rows=D.assign(depth,'4-3','nickel',big_nickel=True)
        self.assertEqual(next(r['player']['pid'] for r in rows if r['role']=='SLOT'),'slot')
        self.assertEqual(len({r['player']['pid'] for r in rows}),11)

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
        fast=dict(pos='LEDG',ovr=70,ratings={'accel_rating':99})
        slow=dict(pos='LEDG',ovr=70,ratings={'accel_rating':30})
        self.assertGreater(D.candidate_grade(fast,'LE'),D.candidate_grade(slow,'LE'))
        zone=dict(pos='CB',ratings=dict(zone_cover_rating=95,play_rec_rating=95,awareness_rating=95,speed_rating=80,man_cover_rating=50,press_rating=50,agility_rating=60))
        self.assertGreater(D.candidate_grade(zone,'CB','zone_corner'),D.candidate_grade(zone,'CB','man_corner'))

    def test_safety_and_tampa_specialists_are_distinct(self):
        cover=dict(pos='SS',ovr=70,ratings=dict(zone_cover_rating=95,speed_rating=95,play_rec_rating=90,awareness_rating=90,tackle_rating=45,block_shed_rating=40,pursuit_rating=45))
        box=dict(pos='SS',ovr=70,ratings=dict(zone_cover_rating=45,speed_rating=65,play_rec_rating=80,awareness_rating=65,tackle_rating=95,block_shed_rating=95,pursuit_rating=95))
        self.assertGreater(D.candidate_grade(cover,'SS','coverage_safety'),D.candidate_grade(box,'SS','coverage_safety'))
        self.assertGreater(D.candidate_grade(box,'SS','box_safety'),D.candidate_grade(cover,'SS','box_safety'))
        cover['pos']=box['pos']='MIKE'
        self.assertGreater(D.candidate_grade(cover,'MIKE','tampa_middle'),D.candidate_grade(box,'MIKE','tampa_middle'))

    def test_planning_does_not_consume_global_randomness(self):
        import numpy as np
        before=np.random.get_state()
        D.planning_profile({'def_front':'multiple','coverage':.83})
        after=np.random.get_state()
        self.assertEqual(before[0],after[0])
        self.assertTrue(np.array_equal(before[1],after[1]))
        self.assertEqual(before[2:],after[2:])


if __name__=='__main__': unittest.main()

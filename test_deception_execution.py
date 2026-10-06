import unittest
import numpy as np
import schemes as S, plays as P, game as G, rosters
from deception_execution import motion_run_bonus, play_action_effect

class Deception(unittest.TestCase):
    def test_zero_motion_does_not_restore_default(self):
        def count(value):
            return sum(S.call_offense(1,10,0,50,np.random.default_rng(i),lean={'motion':value})['motion'] for i in range(1000))
        self.assertEqual(count(0),count(.00000001))
        self.assertLess(count(0),count(None))

    def test_recognition_can_neutralize_motion_and_fake(self):
        def player(v): return dict(pos='WR',awareness_rating=v,play_rec_rating=v,agility_rating=v,accel_rating=v,play_action_rating=v)
        off={'wr':[player(70)]}
        self.assertEqual(motion_run_bonus(off,{'lb':[player(95)]},P.rate),0)
        self.assertGreater(motion_run_bonus(off,{'lb':[player(40)]},P.rate),0)
        fast,benefit=play_action_effect(player(70),{'lb':[player(95)]},P.rate,True)
        slow,poor_read=play_action_effect(player(70),{'lb':[player(40)]},P.rate,False)
        self.assertEqual(benefit,0)
        self.assertGreater(poor_read,benefit)
        self.assertGreater(slow,fast)
        self.assertGreater(fast,0)

    def test_fake_changes_actual_pressure_release_window(self):
        teams=rosters.load_league()
        off,_=G.field_units(teams['GB'],None,np.random.default_rng(1),True,'11')
        deff,_=G.field_units(teams['MIA'],None,np.random.default_rng(2),False,'nickel','4-3')
        checked=0
        for seed in range(50):
            outputs=[]
            for pa in (False,True):
                rng=np.random.default_rng(seed)
                oc=dict(is_pass=True,personnel='11',depth='medium',concept='dagger',down=2,ydstogo=8,shotgun=True,play_action=pa)
                dc=S.call_defense(oc,2,8,rng)
                outputs.append(P._pass_play(off,deff,oc,dc,50,rng))
            a,b=outputs
            if 'pressure_release' in a and 'pressure_release' in b and a.get('depth')==b.get('depth') and a.get('read')==b.get('read'):
                self.assertGreaterEqual(b['pressure_release'],a['pressure_release'])
                checked+=b['pressure_release']>a['pressure_release']
        self.assertGreater(checked,5)

if __name__=='__main__':unittest.main()

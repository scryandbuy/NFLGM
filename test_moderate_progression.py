import copy
import unittest
from unittest.mock import patch
from league import Player
import xp as X
import targets as T

class ModerateProgressionTests(unittest.TestCase):
    def player(self,dev='xfactor',age=22,ovr=80):
        return Player('p','Test','WR',age,{k:float(ovr) for k in T.DEPTH_WEIGHTS['WR']},dev=dev,potential=99)
    def test_performance_boost_does_not_boost_snaps(self):
        line={'rec_yds':150,'rec':9,'rec_td':2,'snaps':65}
        for dev,age,boost in [('xfactor',22,1.75),('superstar',24,1.6),('normal',22,1.15),('star',22,1.3),('xfactor',25,1.625),('xfactor',30,1)]:
            p=self.player(dev,age); q=copy.deepcopy(p)
            raw=X.event_xp(line)+X.weekly_xp(q,line,2026)
            expected=((raw-195)*boost+195)*X.modifier(p)
            self.assertAlmostEqual(X.game_xp(p,line,2026),expected)
            self.assertAlmostEqual(X.game_xp(p,{'snaps':65},2026),195*X.modifier(p))
    def test_exact_tested_cost_relief_and_taper(self):
        for ovr in (80,88,91,94,97):
            for attr in ('catch_rating','speed_rating'):
                p=self.player(ovr=ovr);p.xp_spent={attr:10}
                old=copy.deepcopy(p);old.dev='normal'
                blend=max(0,min(1,(94-p.ovr)/6))
                with patch.object(X, 'learning_relief', return_value=0): baseline=X.cost_per_point(old,attr)
                expected=baseline*((1.03-.02*blend)/1.03)**X.points_bought(p)
                if attr not in X.PHYSICAL:expected*=((1.06-.03*blend)/1.06)**10
                self.assertAlmostEqual(X.cost_per_point(p,attr),expected)
        for dev,age in [('star',22),('normal',22),('xfactor',25)]:
            p=self.player(dev,age);p.xp_spent={'catch_rating':10}
            q=copy.deepcopy(p);q.dev='normal'
            self.assertEqual(X.cost_per_point(p,'catch_rating'),X.cost_per_point(q,'catch_rating'))
if __name__=='__main__':unittest.main()

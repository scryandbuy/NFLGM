import unittest
from types import SimpleNamespace as N
import game as G
import test_game_clock_decisions as C


class ShortFieldRisk(unittest.TestCase):
    def plan(self,y=83,secs=25,ag=.5,adv=.1,prev='hurry',diff=17):
        dr=N(quarter=2,clock_period=2,score_diff=diff,yardline=y,down=1,togo=10,_plan_mode=prev)
        tos=G.Timeouts()
        off=dict(qb={'off':True},wr=[{'off':True}],k={})
        defense=dict(db=[{}])
        rate=lambda p,w:.7+adv if p.get('off') else .7
        plan=G.end_of_half_plan(dr,off,defense,rate,tos,'home',1800,secs,
            coach=dict(fourth_down=ag,adjust_willingness=ag))
        return dr,tos,plan

    def test_deep_leading_drive_abandons_hurry_and_saves_own_timeout(self):
        for y,secs in ((88,31),(83,25),(83,19)):
            for ag in (0,.5,1):
                for adv in (0,.1,.2):
                    dr,tos,p=self.plan(y,secs,ag,adv)
                    self.assertEqual(p['choice'],'kneel')
                    self.assertFalse(p['hurry'])
                    G._timeout_call(dr,'scramble',dict(type='scramble',yards=0),tos,
                        'home',1800,secs,plan=p)
                    self.assertEqual(tos.left['home'],3)

    def test_scoring_range_preserves_attack(self):
        dr,tos,p=self.plan(y=30,secs=31)
        self.assertEqual(p['choice'],'play')
        self.assertEqual(G._timeout_call(dr,'complete',dict(type='complete',yards=3),tos,
            'home',1800,31,plan=p),(True,'home'))

    def test_short_field_turnover_is_more_costly_than_opponent_deep_field(self):
        deep=self.plan(y=83)[2]
        near=self.plan(y=30)[2]
        self.assertGreater(deep['turnover_costs']['play'],near['turnover_costs']['play'])

    def test_distant_shot_decays_and_arm_strength_matters(self):
        def chance(y,power):
            return G._shot_td_prob(y,dict(qb={}),{},lambda *a:power)
        self.assertLess(chance(88,.7),chance(62,.7)/5)
        self.assertGreater(chance(75,.95),chance(75,.5))

    def test_live_and_batch_protect_with_opposing_timeouts(self):
        for live in (False,True):
            h=C.ClockDecisions();h.setUp();calls=[]
            dr,book,tos=h.drive([dict(type='run',yards=1)]*8,start=88,clock=1831,
                diff=17,own=3,other=3,live=live,calls=calls)
            self.assertEqual(tos.left['home'],3)
            self.assertTrue(all(not c.get('is_pass') for c in calls))
            self.assertEqual(dr.result,'End of half')


if __name__=='__main__': unittest.main()

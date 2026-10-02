import unittest
from types import SimpleNamespace
import numpy as np
import game as G
import plays
import events as E

class Week7(unittest.TestCase):
    def plan(self, seconds=10, timeouts=0, quarter=2, diff=0, aggression=.5):
        dr=SimpleNamespace(quarter=quarter, score_diff=diff, yardline=17, down=3)
        tos=G.Timeouts();tos.left={'home':timeouts,'away':0}
        return G.end_of_half_plan(dr, {'k':{},'ol':[]}, {'dl':[],'lb':[]}, lambda *a:.7,
            tos,'home',1800 if quarter==2 else None,seconds,
            {'fourth_down':aggression,'adjust_willingness':aggression})
    def test_reported_ten_seconds_kicks(self):
        for aggression in (0,.5,1):
            self.assertEqual(self.plan(aggression=aggression)['choice'],'kick')
    def test_touchdown_required_does_not_kick(self):
        self.assertNotEqual(self.plan(quarter=4,diff=-6)['choice'],'kick')
    def test_timeout_increases_shot_value(self):
        self.assertGreater(self.plan(timeouts=1)['evs']['shot'],self.plan()['evs']['shot'])
    def test_sacks_depth_and_tail(self):
        samples={d:np.array([plays.sack_loss(r,d,2.7) for _ in range(20000)])
                 for d,r in [(d,np.random.default_rng(42)) for d in ('screen','short','medium','deep')]}
        self.assertLess(samples['short'].mean(),samples['medium'].mean())
        self.assertLess(samples['medium'].mean(),samples['deep'].mean())
        self.assertLess(np.mean(samples['medium']>=14),.02)
        self.assertTrue(np.all((samples['deep']>=.5)&(samples['deep']<=18)))
    def test_context_keeps_flag_and_side(self):
        rng=np.random.default_rng(73)
        for outcome in ({'type':'sack'},{'type':'incomplete','pressured':False},
                        {'type':'complete','air':12,'pressured':True},{'type':'scramble'}):
            for _ in range(1500):
                pen=E.penalty_check(rng,is_pass=True)
                adjusted=E.contextual_penalty(pen,outcome,{'is_pass':True},rng)
                self.assertEqual(pen is None,adjusted is None)
                if pen:
                    self.assertEqual(pen['on_offense'],adjusted['on_offense'])
                    if adjusted['penalty']=='Roughing the Passer':
                        self.assertEqual(outcome['type'],'complete')
                    if adjusted['penalty']=='Face Mask':
                        self.assertNotEqual(outcome['type'],'incomplete')
    def test_illegal_contact_can_precede_sack(self):
        pen=dict(penalty='Illegal Contact',on_offense=False,nullifies=False)
        self.assertIs(E.contextual_penalty(pen,{'type':'sack'},{'is_pass':True},np.random.default_rng(1)),pen)
    def test_legitimate_consecutive_roughing_retained(self):
        pen=dict(penalty='Roughing the Passer',on_offense=False,nullifies=False)
        for _ in range(2):
            self.assertIs(E.contextual_penalty(pen,{'type':'complete','pressured':True},{'is_pass':True},np.random.default_rng(1)),pen)

if __name__=='__main__': unittest.main()

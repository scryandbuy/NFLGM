import copy
import unittest
from types import SimpleNamespace
import numpy as np
import plays as P
import ticker
import run_blocking as RB
from test_defensive_rush import unit, call
from test_run_support_attributes import offense


class ExecutionDraws:
    def __init__(self, values):self.values=iter(values);self.rng=np.random.default_rng(5)
    def normal(self,loc,scale):
        return next(self.values) if scale==P.BE.RUN_SIGMA else self.rng.normal(loc,scale)
    def __getattr__(self,key):return getattr(self.rng,key)


class RunExecutionContact(unittest.TestCase):
    def resolve(self, values, scheme='inside_zone', off=None, ytg=60):
        return P._run_play(off or offense(),unit('4-3'),dict(scheme=scheme),
            dict(call('4-3'),front='4-3 over',box=6),ytg,ExecutionDraws(values))

    def test_recorded_failures_and_wins_drive_the_actual_contact(self):
        lost=self.resolve([-.2]*9);won=self.resolve([.2]*9)
        self.assertEqual(sum(w for _,w in lost['rb_reps']),0)
        self.assertEqual(sum(w for _,w in won['rb_reps']),9)
        self.assertLess(lost['yards'],0)
        self.assertGreater(won['ybc'],0)

    def test_single_failed_block_can_disrupt_without_every_failure_being_a_stuff(self):
        base=self.resolve([0.]*9)
        # Front order is stable. An interior block loses its rep; the rest
        # of the actual offense still contributes to the path.
        small=[0.]*9;small[1]=-.06
        big=[0.]*9;big[1]=-.6
        marginal=self.resolve(small);penetration=self.resolve(big)
        self.assertFalse(marginal['rb_reps'][1][1])
        self.assertGreater(marginal['yards'],0)
        self.assertLess(marginal['ybc'],base['ybc'])
        self.assertLess(penetration['yards'],0)
        self.assertFalse(penetration['touchdown'])

    def test_scheme_weights_interior_and_edge_execution(self):
        def blocks(edge,interior):
            return [dict(front=True,alignment='left_edge',execution=edge),
                    dict(front=True,alignment='left_interior',execution=interior)]
        for scheme,edge_larger in (('inside_zone',False),('outside_zone',True)):
            e=RB.contact_execution(blocks(-.1,0),scheme,.1,1.33)
            i=RB.contact_execution(blocks(0,-.1),scheme,.1,1.33)
            self.assertEqual(e<i,edge_larger)

    def test_support_failure_changes_contact_and_has_one_stat_record(self):
        base=self.resolve([0.]*9)
        draws=[0.]*9;draws[5]=-.3
        lost=self.resolve(draws)
        self.assertLess(lost['ybc'],base['ybc'])
        self.assertEqual(len(lost['rb_reps']),len({pid for pid,_ in lost['rb_reps']}))

    def test_normalized_execution_preserves_variance_across_personnel(self):
        # Exact Gaussian coefficient norm, not an outcome-rate target.
        for n in (3,5,9):
            coefficients=[]
            for i in range(n):
                blocks=[dict(front=False,weight=.2+j/n,execution=.1 if i==j else 0) for j in range(n)]
                coefficients.append(RB.contact_execution(blocks,'power',.1,1.33))
            self.assertAlmostEqual(sum(x*x for x in coefficients),1.33**2)


class FractionalLossWording(unittest.TestCase):
    def test_short_losses_are_explicit_without_changing_the_play(self):
        league=SimpleNamespace(player=lambda pid:SimpleNamespace(name=pid))
        for kind in ('run','complete','scramble','sack'):
            for loss in (-.01,-.2,-.49,-.5):
                p=dict(type=kind,yards=loss,yardline=50,down=1,ydstogo=10,clock=600,
                    carrier='Back',passer='QB',target='Receiver',by='Defender',scheme='inside_zone')
                before=copy.deepcopy(p)
                line=ticker.play_line(league,p,'GB','LA')
                self.assertIn('a short loss',line['text'])
                self.assertNotIn('no gain',line['text'])
                self.assertEqual(line['kind'],'loss')
                self.assertEqual(p,before)
                self.assertEqual(ticker._display_gain(50,loss,'GB','LA'),0)

    def test_zero_positive_and_whole_losses_keep_their_meaning(self):
        self.assertEqual(ticker._yards(0),('none','no gain'))
        self.assertEqual(ticker._yards(.2),('none','no gain'))
        self.assertEqual(ticker._yards(-.6),('loss','a loss of 1 yard'))
        self.assertEqual(ticker._yards(-2),('loss','a loss of 2 yards'))


if __name__=='__main__':unittest.main()

"""Football action/restraint and outcome contract for avoiding QB contact."""
import copy
import unittest
import numpy as np
import qb_contact as Q


class Rolls:
    def __init__(self, *values):
        self.values = iter(values)
    def random(self):
        return next(self.values)


def player(**kw):
    return dict(pid='QB', speed_rating=80, accel_rating=80, agility_rating=80,
                awareness_rating=80, break_tackle_rating=65, strength_rating=65, **kw)


def rate(p, weights):
    return sum(p.get(k, 70) * v for k, v in weights.items()) / 100.


def outcome(**kw):
    out=dict(type='scramble',yards=10.,yardline=70.,down=1,ydstogo=10.,
             by='QB',passer='QB',tackler='EDGE',rush_pressures=['EDGE'])
    out.update(kw)
    return out


class QBContact(unittest.TestCase):
    def slide(self, out=None, **kw):
        out=out if out is not None else outcome()
        return Q.apply(out,player(),{},Rolls(0.,1.,0.,0.,.99),rate,**kw)

    def test_slide_surrenders_yards_preserves_identity_and_pressure(self):
        out=outcome();self.assertIs(self.slide(out),out)
        self.assertEqual(out['run_end'],'slide')
        self.assertTrue(out['contact_avoided']);self.assertTrue(out['ended_without_contact'])
        self.assertFalse(out['out_of_bounds']);self.assertNotIn('tackler',out)
        self.assertEqual(out['by'],'QB');self.assertEqual(out['rush_pressures'],['EDGE'])
        self.assertEqual(out['yards'],9.2)
        self.assertEqual(out['qb_contact']['yards_given_up'],.8)
        self.assertEqual(out['qb_contact']['pursuer_pid'],'EDGE')
        old=copy.deepcopy(out)
        Q.apply(out,player(),{},Rolls(),rate)
        self.assertEqual(out,old)

    def test_continuing_for_yards_remains_possible_and_keeps_tackler(self):
        out=Q.apply(outcome(),player(),{},Rolls(0.,0.,0.,0.,0.),rate)
        self.assertEqual(out['run_end'],'contact');self.assertEqual(out['yards'],10.)
        self.assertEqual(out['tackler'],'EDGE');self.assertFalse(out['contact_avoided'])

    def test_no_opportunity_does_not_invent_sideline_or_slide(self):
        out=Q.apply(outcome(),player(),{},Rolls(1.,1.,0.,0.),rate)
        self.assertEqual(out['run_end'],'contact')
        self.assertFalse(out['qb_contact']['sideline_available'])
        self.assertFalse(out['qb_contact']['slide_available'])

    def test_safe_designed_run_ends_before_first_contact(self):
        out=self.slide(outcome(type='run',carrier_pid='QB',qb_run=True,
                               ybc=4.,broken_tackles=2,yards=12.))
        self.assertEqual(out['run_end'],'slide');self.assertEqual(out['yards'],3.2)
        self.assertEqual(out['ybc'],3.2);self.assertEqual(out['broken_tackles'],0)
        self.assertEqual(out['qb_contact']['original_yards'],12.)
        self.assertEqual(out['qb_contact']['yards_given_up'],8.8)

    def test_contact_before_open_space_cannot_be_relabelled_safe(self):
        out=Q.apply(outcome(type='run',carrier_pid='QB',ybc=1.,yards=20.),player(),{},Rolls(),rate)
        self.assertEqual(out['run_end'],'contact');self.assertEqual(out['yards'],20.)
        self.assertEqual(out['qb_contact']['reason'],'no_safe_space')

    def test_early_down_can_surrender_conversion_fourth_cannot_buy_it(self):
        early=self.slide(outcome(yards=10.,ydstogo=10.))
        self.assertLess(early['yards'],10.)
        for yards in (8.,10.5):
            out=self.slide(outcome(yards=yards,down=4,ydstogo=10.))
            self.assertEqual(out['run_end'],'contact');self.assertEqual(out['yards'],yards)
        converted=self.slide(outcome(yards=14.,down=4,ydstogo=10.))
        self.assertEqual(converted['run_end'],'slide');self.assertGreater(converted['yards'],10.)

    def test_short_loss_sneak_nonqb_turnover_and_score_unchanged(self):
        fixtures=[outcome(type='run',carrier_pid='HB',qb_run=True),
                  outcome(sneak=True),outcome(type='kneel'),outcome(type='sack'),
                  outcome(touchdown=True),outcome(yards=9.8,yardline=10.),
                  outcome(fumble=True),outcome(fumble_lost=True)]
        for out in fixtures:
            before=copy.deepcopy(out)
            self.assertEqual(Q.apply(out,player(),{},Rolls(),rate),before)
        for yards in (-2.,0.,2.):
            out=Q.apply(outcome(yards=yards),player(),{},Rolls(),rate)
            self.assertEqual(out['yards'],yards);self.assertEqual(out['run_end'],'contact')

    def test_sideline_is_a_separate_opportunity_and_preserves_noncontact_risk_contract(self):
        out=Q.apply(outcome(),player(),dict(quarter=4,seconds=50,score_diff=-3),
                    Rolls(1.,0.,0.,0.,.99),rate)
        self.assertEqual(out['run_end'],'out_of_bounds');self.assertTrue(out['out_of_bounds'])
        self.assertTrue(out['ended_without_contact'])
        self.assertEqual(out['yards'],9.5);self.assertNotIn('fumble',out)
        self.assertNotIn('injury_immune',out)

    def counts(self,call=None,coach=None,condition=100,qb=None,out=None):
        count={'contact':0,'slide':0,'out_of_bounds':0}
        for seed in range(600):
            value=Q.apply(copy.deepcopy(out or outcome(yards=14.)),qb or player(),
                           call or {},np.random.default_rng(seed),rate,coach,condition)
            count[value['run_end']]+=1
        return count

    def test_clock_objective_changes_choice_but_never_guarantees_boundary(self):
        trail=self.counts(dict(quarter=4,seconds=60,score_diff=-3))
        lead=self.counts(dict(quarter=4,seconds=60,score_diff=3))
        self.assertGreater(trail['out_of_bounds'],lead['out_of_bounds'])
        self.assertGreater(lead['slide'],trail['slide'])
        for c in (trail,lead):
            self.assertGreater(c['contact'],0)
            self.assertLess(c['out_of_bounds'],600)

    def test_staff_condition_awareness_and_running_strength_preserve_differences(self):
        cautious=self.counts(coach={'starter_protection':1.})
        aggressive=self.counts(coach={'starter_protection':0.})
        tired=self.counts(condition=35)
        fresh=self.counts(condition=100)
        self.assertLess(cautious['contact'],aggressive['contact'])
        self.assertLess(tired['contact'],fresh['contact'])
        aware=player();aware['awareness_rating']=95
        unaware=player();unaware['awareness_rating']=40
        self.assertLess(self.counts(qb=aware)['contact'],self.counts(qb=unaware)['contact'])
        strong=player();strong.update(strength_rating=95,break_tackle_rating=95)
        self.assertGreater(self.counts(qb=strong)['contact'],fresh['contact'])

    def test_critical_third_down_is_less_willing_to_surrender_the_marker(self):
        normal=self.counts(out=outcome(yards=10.5,down=1,ydstogo=10.))
        third=self.counts(out=outcome(yards=10.5,down=3,ydstogo=10.))
        self.assertGreater(third['contact'],normal['contact'])


class BoundaryClock(unittest.TestCase):
    def test_regulation_boundaries_and_warning(self):
        out={'out_of_bounds':True}
        self.assertFalse(Q.oob_stops_until_snap(out,1,60))
        self.assertFalse(Q.oob_stops_until_snap(out,2,121))
        self.assertFalse(Q.oob_stops_until_snap(out,2,120))
        self.assertTrue(Q.oob_stops_until_snap(out,2,120,True))
        self.assertTrue(Q.oob_stops_until_snap(out,2,119))
        self.assertFalse(Q.oob_stops_until_snap(out,3,60))
        self.assertFalse(Q.oob_stops_until_snap(out,4,300))
        self.assertTrue(Q.oob_stops_until_snap(out,4,299))
        self.assertFalse(Q.oob_stops_until_snap({'run_end':'slide'},4,10))

    def test_regular_and_postseason_overtime_timing_are_distinct(self):
        out={'out_of_bounds':True}
        self.assertFalse(Q.oob_stops_until_snap(out,5,301))
        self.assertTrue(Q.oob_stops_until_snap(out,5,299))
        self.assertFalse(Q.oob_stops_until_snap(out,5,60,playoffs=True))
        self.assertTrue(Q.oob_stops_until_snap(out,6,119,playoffs=True))
        self.assertFalse(Q.oob_stops_until_snap(out,7,60,playoffs=True))
        self.assertTrue(Q.oob_stops_until_snap(out,8,299,playoffs=True))


if __name__=='__main__': unittest.main()

"""Behavioral checks for box-dependent disruption, not only gain compression."""
import unittest
from statistics import NormalDist
from unittest.mock import patch
import plays as P
import schemes as S
from test_defensive_rush import unit, call


class BoxContactTests(unittest.TestCase):
    def contact(self, raw, box):
        return S.box_run_contact(raw, box, P.RUN_BASE, P.RUN_NOISE)

    def test_dense_box_can_turn_marginal_gain_into_loss(self):
        self.assertGreater(self.contact(.2, 6), 0)
        self.assertLess(self.contact(.2, 9), 0)
        self.assertGreater(self.contact(-.2, 4), 0)

    def test_six_man_box_is_neutral_and_heavy_boxes_do_not_soften_losses(self):
        for raw in (-3, -.5, 0, .5, 3, 8):
            self.assertAlmostEqual(self.contact(raw, 6), raw)
            contacts=[self.contact(raw,box) for box in range(4,11)]
            self.assertEqual(contacts,sorted(contacts,reverse=True))
        self.assertLess(self.contact(-1,10),-1)

    def test_reference_loss_gradient_without_extra_random_roll(self):
        # Quantile sampling removes seed noise from this threshold check.
        distribution=NormalDist(-P.RUN_NOISE*NormalDist().inv_cdf(S.BOX_NEG[6]/100),P.RUN_NOISE)
        samples=[distribution.inv_cdf((i+.5)/10000) for i in range(10000)]
        for box,target in S.BOX_NEG.items():
            fraction=sum(self.contact(raw,box)<0 for raw in samples)/len(samples)
            self.assertAlmostEqual(fraction,target/100,delta=.0002)

    def test_blocking_matchup_still_changes_losses_and_gains(self):
        for box in range(4,11):
            for raw in (-1,0,1,3):
                self.assertGreater(self.contact(raw+.6,box),self.contact(raw,box))

    def test_actual_resolver_applies_disruption_before_yac(self):
        defense=unit('4-3')
        offense=dict(ol=[dict(pid=p,pos=p) for p in ('LT','LG','C','RG','RT')],qb=dict(pid='Q'),rb=dict(pid='H'))
        class FixedNoise:
            def normal(self,loc,scale):
                return -1.85 if scale==P.RUN_NOISE else 0
        def no_yac(runner,chasers,ytg,rng,contact_at=0,gain_scale=1):
            return dict(yards=contact_at*gain_scale,touchdown=False)
        with patch.object(P,'resolve_yards_after',side_effect=no_yac), \
             patch('run_blocking.contact_execution',return_value=-1.85):
            neutral=P._run_play(offense,defense,dict(scheme='inside_zone'),dict(call('4-3'),front='4-3 over',box=6),50,FixedNoise())
            dense=P._run_play(offense,defense,dict(scheme='inside_zone'),dict(call('4-3'),front='4-3 over',box=10),50,FixedNoise())
        self.assertGreater(neutral['yards'],0)
        self.assertLess(dense['yards'],0)
        self.assertEqual(len(dense['rb_reps']),5)
        self.assertFalse(dense['touchdown'])

    def test_execution_limits_loss_instead_of_magnifying_it(self):
        defense=unit('4-3')
        offense=dict(ol=[dict(pid=p,pos=p) for p in ('LT','LG','C','RG','RT')],qb=dict(pid='Q'),rb=dict(pid='H'))
        class FixedNoise:
            def normal(self,loc,scale):return -3 if scale==P.RUN_NOISE else 0
        with patch('run_blocking.contact_execution',return_value=-3.):
            results=[P._run_play(offense,defense,dict(scheme='inside_zone',execution_mod=e),
                                dict(call('4-3'),front='4-3 over',box=10),50,FixedNoise()) for e in (.94,1.06)]
        self.assertLess(results[0]['yards'],results[1]['yards'])
        self.assertLess(results[1]['yards'],0)


if __name__=='__main__':unittest.main()

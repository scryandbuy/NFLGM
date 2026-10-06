import unittest
from collections import Counter
from types import SimpleNamespace as NS
import numpy as np
import offense_roles as OR
import schemes as S
import plays as P
from test_offense_personnel import roster


class EmptyPersonnel(unittest.TestCase):
    def depth(self, te=75, wr5=75):
        d=roster()['depth']
        for p in d['TE']: p['ovr']=te
        for p in d['WR']: p['ovr']=wr5
        return d

    def test_default_and_marginal_wr_edge_keep_te(self):
        for te,wr in ((80,70),(75,75),(75,82)):
            d=self.depth(te,wr)
            self.assertEqual(OR.empty_package(d),'01')
            rows=OR.assign(d,OR.empty_package(d))
            self.assertEqual(Counter(r for r,p in rows)['WR'],4)
            self.assertEqual(Counter(r for r,p in rows)['TE'],1)
            self.assertEqual(len({p['pid'] for r,p in rows}),11)

    def test_large_gap_and_coach_difference(self):
        self.assertEqual(OR.empty_package(self.depth(60,85)),'00')
        d=self.depth(70,81)
        self.assertEqual(OR.empty_package(d,NS(aggression=1)),'00')
        self.assertEqual(OR.empty_package(d,NS(aggression=0)),'01')

    def test_receiving_skill_not_blocking_overall_or_hidden_potential(self):
        d=self.depth(50,80)
        d['TE'][0].update({k:90 for k in ('catch_rating','route_run_short_rating',
            'route_run_med_rating','route_run_deep_rating','cit_rating','speed_rating','release_rating')})
        d['TE'][0]['potential']=50
        self.assertEqual(OR.empty_package(d),'01')
        rows=OR.assign(d,'01')
        self.assertEqual(next(p['pid'] for r,p in rows if r=='TE'),d['TE'][0]['pid'])

    def test_unavailable_te_and_wr5(self):
        d=self.depth(60,90)
        self.assertEqual(OR.empty_package(d,excluded=[p['pid'] for p in d['WR'][4:]]),'01')
        self.assertEqual(OR.empty_package(d,excluded=[p['pid'] for p in d['TE']]),'00')
        oc=dict(personnel='11',formation='empty')
        OR.refresh_empty_call(oc,dict(depth=d),NS(out={p['pid'] for p in d['WR'][4:]}))
        self.assertEqual(oc['personnel'],'01')

    def test_live_calls_and_planning_agree_on_empty_composition(self):
        for te,wr,expected in ((80,70,'01'),(60,85,'00')):
            ros=roster();ros['depth']=self.depth(te,wr)
            for seed in range(8):
                call=S.call_offense(2,10,0,50,np.random.default_rng(seed),
                    offense=ros,rate_fn=P.rate,lean={'personnel_mix':{'00':1}})
                self.assertEqual(call['personnel'],expected)
                self.assertEqual(call['formation'],'empty')
                self.assertEqual(S.PERSONNEL_OFF[expected]['protect'],5)
                self.assertEqual(S.choose_protection(expected,7,'deep',np.random.default_rng(seed),
                    preference='full_slide'),'five')
            mix=OR.expected_package_weights(NS(off_personnel='00',aggression=.5),ros['depth'])
            self.assertGreater(mix.get(expected,0),.4)
            self.assertAlmostEqual(sum(mix.values()),1.)


if __name__=='__main__': unittest.main()

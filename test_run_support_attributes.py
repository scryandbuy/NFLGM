import copy
import unittest
from unittest.mock import patch
import numpy as np
import plays as P
import offense_roles as O
import defensive_rush as D
from run_blocking import support_blocks
from test_defensive_rush import unit, call


def offense():
    depth={pos:[dict(pid=pos,pos=pos)] for pos in ('QB','HB','FB','LT','LG','C','RG','RT')}
    depth['TE']=[dict(pid='TE'+str(i),pos='TE') for i in range(3)]
    depth['WR']=[dict(pid='WR'+str(i),pos='WR') for i in range(5)]
    return O.field(dict(depth=depth),'22')


class RunSupportAttributes(unittest.TestCase):
    def resolve(self, off, seed=5, scheme='power', defense=None):
        return P._run_play(off, defense or unit('4-3'),dict(scheme=scheme),
            dict(call('4-3'),front='4-3 over',box=6),60,np.random.default_rng(seed))

    def test_actual_contact_improves_with_previously_ignored_attributes(self):
        for pos,attr in [('FB','lead_block_rating'),('FB','impact_block_rating'),
                         ('TE','run_block_rating'),('TE','impact_block_rating'),
                         ('WR','run_block_rating')]:
            low,high=offense(),offense()
            for off,value in [(low,20),(high,99)]:
                for p in off['extra_blockers']+off['wr']:
                    if p['pos']==pos:p[attr]=value
            for seed in range(30):
                a,b=self.resolve(low,seed),self.resolve(high,seed)
                self.assertGreater(b['ybc'],a['ybc'],(pos,attr,seed))

    def test_free_lineman_uses_impact_and_lead_ratings(self):
        for attr in ('impact_block_rating','lead_block_rating'):
            low,high=offense(),offense()
            for off,value in [(low,20),(high,99)]:
                for p in off['ol']:p[attr]=value
            self.assertGreater(self.resolve(high)['ybc'],self.resolve(low)['ybc'])

    def test_no_duplicate_blocker_or_defender_and_no_runner_block(self):
        off=offense();result=self.resolve(off)
        blocks=result['run_support']
        self.assertEqual(len(blocks),len({b['blocker'] for b in blocks}))
        self.assertEqual(len(blocks),len({b['defender'] for b in blocks}))
        self.assertNotIn(off['rb']['pid'],{b['blocker'] for b in blocks})
        self.assertEqual(len(result['rb_reps']),len({p for p,_ in result['rb_reps']}))
        self.assertEqual(len(result['rb_reps']),9)

    def test_neutral_support_is_zero_and_actual_defender_shedding_matters(self):
        off=offense();defense=unit('4-3')
        for group in ('dl','lb','db'):
            for p in defense[group]:p['power_moves_rating']=70
        roles=D.assignments(defense,call('4-3'))
        delta,blocks=support_blocks(off,roles,set(),set(),'power',P.rate)
        self.assertAlmostEqual(delta,0)
        for p in defense['lb']:p.update(block_shed_rating=99,strength_rating=99)
        changed,_=support_blocks(off,D.assignments(defense,call('4-3')),set(),set(),'power',P.rate)
        self.assertLess(changed,delta)

    def test_wide_run_values_receiver_block_more(self):
        low,high=offense(),offense()
        for off,value in [(low,20),(high,99)]:
            for p in off['wr']:
                if p['pos']=='WR':p['run_block_rating']=value
        gaps={s:self.resolve(high,scheme=s)['ybc']-self.resolve(low,scheme=s)['ybc']
              for s in ('power','outside_zone')}
        self.assertGreater(gaps['outside_zone'],gaps['power'])

    def test_support_order_is_stable_and_unused_bench_players_do_not_enter(self):
        off=offense();expected=self.resolve(off)
        for group in ('wr','extra_blockers','ol'):off[group].reverse()
        off['depth']={'TE':[dict(pid='bench',pos='TE',run_block_rating=99)]}
        self.assertEqual(self.resolve(off),expected)

    def test_fullback_fill_in_is_graded_as_the_assigned_role(self):
        off=offense()
        fb=next(p for p in off['extra_blockers'] if p['pos']=='FB')
        fb['pos']='HB';fb['lead_block_rating']=99
        result=self.resolve(off)
        self.assertEqual(next(b['role'] for b in result['run_support'] if b['blocker']==fb['pid']),'FB')

    def test_package_and_injury_selection_remain_authoritative(self):
        depth={p:[dict(pid=p,pos=p)] for p in ('QB','HB','FB','LT','LG','C','RG','RT')}
        depth['TE']=[dict(pid='TE'+str(i),pos='TE') for i in range(4)]
        depth['WR']=[dict(pid='WR'+str(i),pos='WR') for i in range(6)]
        from types import SimpleNamespace
        state=SimpleNamespace(out={'TE0'})
        for package in O.PACKAGES:
            off=O.field(dict(depth=depth),package,state=state)
            result=self.resolve(off)
            active={p['pid'] for _,p in off['offensive_assignments']}
            self.assertNotIn('TE0',active)
            self.assertTrue({b['blocker'] for b in result['run_support']}<=active)


if __name__=='__main__':unittest.main()

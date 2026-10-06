import copy
import unittest
import numpy as np
import coverage as C
import defensive_rush as R
import pass_pursuit as PP
import plays as P
from test_defensive_rush import unit, call
from test_coverage_recording import offense


class PursuitTests(unittest.TestCase):
    def setup_play(self, name='two_man', side='L'):
        c = dict(call('4-3', 'nickel'), coverage=name,
                 under='man' if name in ('two_man', 'cover_0', 'cover_1') else 'zone')
        d = R.select_rush(unit('4-3', 'nickel'), c)['coverage']
        pairs, _ = C.assign_coverage([dict(player=dict(pid='W', pos='WR'), spot='X', side=side)],
                                    d, c, np.random.default_rng(7), P.rate)
        return d, c, pairs[0], pairs

    def choose(self, data, **kw):
        d,c,p,pairs = data
        args = dict(primary=p['defender'], helper=None, depth='deep', separation=.7, in_man=p['man'])
        args.update(kw)
        return PP.select(d,c,p,pairs,**args)

    def test_separated_two_man_catch_retains_same_side_safety(self):
        a = self.choose(self.setup_play(side='L'))
        b = self.choose(self.setup_play(side='R'))
        self.assertEqual([p['pid'] for p in a], ['SS','CBR'])
        self.assertEqual([p['pid'] for p in b], ['FS','CBL'])

    def test_one_high_and_zero_high_differ(self):
        self.assertEqual([p['pid'] for p in self.choose(self.setup_play('cover_1'))], ['FS','CBR'])
        self.assertEqual([p['pid'] for p in self.choose(self.setup_play('cover_0'))], ['CBR'])

    def test_seam_preserves_both_halves(self):
        d,c,p,pairs = self.setup_play()
        p.update(side='R', spot='slot')
        self.assertEqual({p['pid'] for p in self.choose((d,c,p,pairs))}, {'FS','SS'})

    def test_zone_hole_uses_real_helper_and_no_provisional_owner(self):
        data = self.setup_play('cover_2'); d,c,p,pairs=data
        p.update(side='C',spot='slot')
        helper = next(x for x in d['db'] if x['pid']=='FS')
        out=self.choose(data,helper=copy.deepcopy(helper),hole=True)
        self.assertEqual({x['pid'] for x in out}, {'FS','SS'})

    def test_busy_man_safety_is_not_free_help(self):
        data=self.setup_play(); d,c,p,pairs=data
        safety=next(x for x in d['db'] if x['pid']=='SS')
        pairs.append(dict(defender=safety,man=True,receiver=dict(pid='TE')))
        self.assertEqual([p['pid'] for p in self.choose(data)], ['CBR'])

    def test_short_catch_retains_deep_support(self):
        for name in ('two_man', 'cover_1', 'cover_2', 'cover_3', 'cover_4', 'cover_6', 'tampa_2', 'fire_zone'):
            data=self.setup_play(name)
            out=self.choose(data,depth='short',separation=.2)
            self.assertTrue(any(x['pos'] in ('FS','SS') for x in out), name)
            self.assertEqual(len(out),len({x['pid'] for x in out}))

    def test_no_help_does_not_invent_a_stop_or_tackler(self):
        out=P.resolve_yards_after({},[],60,np.random.default_rng(5),track_tackler=True)
        self.assertTrue(out['touchdown'])
        self.assertIsNone(out['tackler'])

    def test_distinct_live_copies_and_rusher_exclusion(self):
        data=self.setup_play(); d,c,p,pairs=data
        pid=p['defender']['pid']; p['defender']=dict(p['defender'])
        out=self.choose(data,depth='short',separation=.2,helper=dict(p['defender']))
        self.assertEqual(out[0]['pid'],pid)
        self.assertEqual(len(out),len({x['pid'] for x in out}))
        self.assertNotIn('LE',{x['pid'] for x in out})
        out=self.choose(data,depth='short',helper=dict(pid='LE',pos='LEDG'))
        self.assertNotIn('LE',{x['pid'] for x in out})

    def test_reordering_inputs_preserves_assignment_choice(self):
        data=self.setup_play('cover_3'); expected=self.choose(data,depth='short')
        d,c,p,pairs=copy.deepcopy(data)
        for group in (*R.GROUPS,'defensive_assignments'): d[group].reverse()
        self.assertEqual(expected,self.choose((d,c,p,pairs),depth='short'))

    def test_safety_attributes_affect_the_existing_tackle_and_chase(self):
        carrier=dict(pid='WR',pos='WR',speed_rating=85,accel_rating=85)
        totals=[]
        for grade in [35,95]:
            defenders=[dict(pid='S',tackle_rating=grade,pursuit_rating=grade,speed_rating=grade,awareness_rating=grade)]
            totals.append(sum(P.resolve_yards_after(carrier,defenders,70,np.random.default_rng(seed),
                             in_space=True,track_tackler=True)['yards'] for seed in range(500)))
        self.assertLess(totals[1],totals[0])

    def test_short_catch_convergence_reduces_one_miss_long_tail(self):
        # A receiver may still outrun the defense, but the next assigned
        # pursuer should reach a catch in front of him before one missed
        # tackle alone routinely becomes a 20-yard run.
        pursuers=self.choose(self.setup_play('cover_3'),depth='short')
        carrier=dict(pid='WR',pos='WR',speed_rating=85,accel_rating=85,
                     agility_rating=85,juke_move_rating=85,
                     break_tackle_rating=80,bcv_rating=80)
        totals=[]
        for convergence in (False,True):
            gains=[P.resolve_yards_after(carrier,pursuers,70,np.random.default_rng(seed),
                   in_space=True,track_tackler=True,
                   converging_pursuit=convergence)['yards'] for seed in range(5000)]
            totals.append((sum(gains)/len(gains),sum(y>=20 for y in gains)))
        self.assertLess(totals[1][1],totals[0][1]*0.6)
        self.assertGreater(totals[1][1],0)
        self.assertGreater(totals[1][0],totals[0][0]*0.85)

    def test_each_pursuit_attribute_has_an_effect(self):
        for attribute in ('tackle_rating','pursuit_rating','speed_rating'):
            sums=[]
            for grade in (35,95):
                defender=dict(pid='S',**{attribute:grade})
                sums.append(sum(P.resolve_yards_after({},[defender],80,np.random.default_rng(seed),
                                in_space=True,track_tackler=True)['yards'] for seed in range(700)))
            self.assertLess(sums[1],sums[0],attribute)

    def test_real_resolver_records_only_distinct_eligible_pursuers(self):
        off=offense(); defense=unit('4-3','nickel')
        n=0
        for seed in range(200):
            c=dict(call('4-3','nickel'),coverage='two_man',shell='cover_2',under='man',box=6,front='over')
            out=P.resolve_play(off,defense,dict(is_pass=True,depth='deep',concept='four_verts',personnel='11',protection='five'),
                               c,85,np.random.default_rng(seed))
            if 'pursuit' not in out: continue
            n+=1; ids=out['pursuit']
            self.assertEqual(len(ids),len(set(ids)))
            self.assertNotIn('LE',ids)
            if out.get('tackler'): self.assertIn(out['tackler'],ids)
            if out['touchdown']: self.assertIsNone(out.get('tackler'))
        self.assertGreater(n,20)


if __name__=='__main__': unittest.main()

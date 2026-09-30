import copy
import unittest
import numpy as np
import defensive_rush as R
import plays as P
import coverage as C


def unit(front='3-4', package='base'):
    front_rows = [('34LE','dl','left_interior','DT'),('NT','dl','nose','DT'),('34RE','dl','right_interior','DT'),
                  ('LOLB','lb','left_edge','LEDG'),('LILB','lb','offball_left','MIKE'),('RILB','lb','offball_right','WILL'),('ROLB','lb','right_edge','REDG')]
    if front=='4-3' or package!='base':
        front_rows=[('LE','dl','left_edge','LEDG'),('DTL','dl','left_interior','DT'),('DTR','dl','right_interior','DT'),('RE','dl','right_edge','REDG')]
        front_rows += [(f'LB{i}','lb',f'offball_{side}','MIKE') for i,side in enumerate(['left','middle','right'][:3 if package=='base' else 2 if package=='nickel' else 1])]
    db=[('CBL','db','corner_left','CB'),('CBR','db','corner_right','CB'),('FS','db','deep_left','FS'),('SS','db','deep_right','SS')]
    db += [(f'SLOT{i}','db','slot','CB') for i in range(0 if package=='base' else 1 if package=='nickel' else 2)]
    out={k:[] for k in R.GROUPS}; out['defensive_assignments']=[]
    for role,group,alignment,pos in front_rows+db:
        p=dict(pid=role,pos=pos,power_moves_rating=75,finesse_moves_rating=75,zone_cover_rating=60)
        out[group].append(p);out['defensive_assignments'].append(dict(role=role,group=group,alignment=alignment,player=dict(p)))
    return out


def call(front='3-4', package='base', count=4, **kw):
    return dict(front_family=front,personnel=package,rushers=count,coverage='cover_2',**kw)


class RushTests(unittest.TestCase):
    def test_run_front_includes_edges_and_is_order_independent(self):
        from unittest.mock import patch
        d=unit(); c=dict(call(),front='3-4 one',box=7)
        off=dict(ol=[dict(pid=p,pos=p) for p in ('LT','LG','C','RG','RT')],qb=dict(pid='Q'),rb=dict(pid='H'))
        original=R.protection_pairs
        with patch.object(R,'protection_pairs',wraps=original) as pairs:
            a=P._run_play(off,d,dict(scheme='inside_zone'),c,50,np.random.default_rng(4))
            self.assertEqual(len(pairs.call_args.args[1]),5)
        perm=copy.deepcopy(d)
        for group in (*R.GROUPS,'defensive_assignments'):perm[group].reverse()
        b=P._run_play(dict(off,ol=off['ol'][::-1]),perm,dict(scheme='inside_zone'),c,50,np.random.default_rng(4))
        self.assertEqual(a,b)
        self.assertEqual(len({pid for pid,_ in a['rb_reps']}),5)
        weak=copy.deepcopy(d); strong=copy.deepcopy(d)
        for defense,rating in ((weak,30),(strong,99)):
            for p in defense['lb']:
                if p['pid'] in ('LOLB','ROLB'):
                    p.update(block_shed_rating=rating,strength_rating=rating,tackle_rating=rating,pursuit_rating=rating)
        lo=P._run_play(off,weak,dict(scheme='inside_zone'),c,50,np.random.default_rng(4))
        hi=P._run_play(off,strong,dict(scheme='inside_zone'),c,50,np.random.default_rng(4))
        self.assertLess(hi['ybc'],lo['ybc'])

    def test_sneak_uses_inside_not_edge_linebacker(self):
        d=unit(); c=dict(call(),box=7)
        off=dict(ol=[dict(pid=p,pos=p) for p in ('LT','LG','C','RG','RT')],qb=dict(pid='Q'),wr=[])
        changed=copy.deepcopy(d)
        for p in changed['lb']:
            if p['pid'] in ('LOLB','ROLB'):p.update(strength_rating=1,block_shed_rating=1)
        for seed in range(40):
            self.assertEqual(P._sneak(off,d,{},c,1,np.random.default_rng(seed)),P._sneak(off,changed,{},c,1,np.random.default_rng(seed)))

    def test_base34_both_edges_at_five_and_better_edge_at_four(self):
        d=unit(); next(p for p in d['lb'] if p['pid']=='ROLB')['power_moves_rating']=99
        four=R.select_rush(d,call()); five=R.select_rush(d,call(count=5))
        self.assertEqual({p['pid'] for p in four['rushers']},{'34LE','NT','34RE','ROLB'})
        self.assertEqual({p['pid'] for p in five['rushers']},{'34LE','NT','34RE','LOLB','ROLB'})

    def test_packages_counts_complement_and_permutation(self):
        for front in ('3-4','4-3'):
            for package in ('base','nickel','dime'):
                for count in range(3,8):
                    d=unit(front,package); c=call(front,package,count)
                    a=R.select_rush(d,c)
                    perm=copy.deepcopy(d)
                    for group in (*R.GROUPS,'defensive_assignments'):perm[group].reverse()
                    b=R.select_rush(perm,c)
                    ids={p['pid'] for p in a['rushers']}
                    cover={p['pid'] for group in R.GROUPS for p in a['coverage'][group]}
                    self.assertEqual(len(ids),count);self.assertEqual(len(ids|cover),11);self.assertFalse(ids&cover)
                    self.assertEqual([p['pid'] for p in a['rushers']],[p['pid'] for p in b['rushers']])
                    if package!='base' and count==4:
                        self.assertEqual({r['alignment'] for r in a['assignments']},set(R.EDGES+('left_interior','right_interior')))

    def test_sim_exchange_and_db_blitz_never_cover(self):
        d=unit('4-3','nickel')
        a=R.select_rush(d,call('4-3','nickel',4,sim_pressure=True))
        self.assertTrue(any(r['group']=='lb' for r in a['assignments']))
        self.assertTrue(a['coverage']['dl'])
        a=R.select_rush(d,call('4-3','nickel',5,blitzer_ids=['SLOT0']))
        self.assertIn('SLOT0',{p['pid'] for p in a['rushers']})
        self.assertNotIn('SLOT0',{p['pid'] for p in a['coverage']['db']})
        aligned=[dict(player=dict(pid=f'WR{i}',pos='WR'),spot=spot,side=side) for i,(spot,side) in enumerate([('X','L'),('Z','R'),('slot','C')])]
        pairs,_=C.assign_coverage(aligned,a['coverage'],call('4-3','nickel',5),np.random.default_rng(1),P.rate,travel=False)
        self.assertNotIn('SLOT0',{r['defender']['pid'] for r in pairs if r['defender']})

    def test_protection_uses_tackles_on_edges_and_pid_not_order(self):
        a=R.select_rush(unit('4-3','nickel'),call('4-3','nickel'))['assignments']
        blockers=[dict(pid=pos,pos=pos) for pos in ('LT','LG','C','RG','RT')]
        pairs=R.protection_pairs(blockers,a)
        mapping={r['alignment']:b['pos'] for r,b in zip(a,pairs)}
        self.assertEqual(mapping,dict(left_edge='RT',right_edge='LT',left_interior='RG',right_interior='LG'))
        x=P.resolve_protection(blockers,[r['player'] for r in a],np.random.default_rng(8),assignments=a)
        y=P.resolve_protection(blockers[::-1],[r['player'] for r in a[::-1]],np.random.default_rng(8),assignments=a[::-1])
        self.assertEqual(x,y)

    def test_edge_rating_changes_pressure_without_changing_assignments(self):
        d=unit('4-3','nickel');a=R.select_rush(d,call('4-3','nickel'))['assignments']
        blockers=[dict(pid=pos,pos=pos) for pos in ('LT','LG','C','RG','RT')]
        def mean(grade):
            for r in a:
                if r['alignment'] in R.EDGES:r['player'].update(power_moves_rating=grade,finesse_moves_rating=grade)
            return np.mean([P.resolve_protection(blockers,[r['player'] for r in a],np.random.default_rng(i),assignments=a)['time'] for i in range(300)])
        self.assertLess(mean(99),mean(40))


if __name__=='__main__':unittest.main()

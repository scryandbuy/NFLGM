"""Protection accounts for gaps, real overloads, and the coach's chosen family."""
import unittest
from unittest.mock import patch
import numpy as np
import defensive_rush as D
import plays as P
from test_defensive_rush import unit, call
from test_designed_qb_runs import offense


class ProtectionAssignments(unittest.TestCase):
    def blockers(self, extra=()):
        return [dict(pid=p, pos=p) for p in ('LT','LG','C','RG','RT') + extra]

    def front(self):
        return D.select_rush(unit('4-3','base'), call('4-3','base',6))['assignments']

    def test_slide_picks_inside_blitz_bob_retains_front_and_extra_back_solves_both(self):
        rows = self.front()
        free = lambda pro: [a['alignment'] for a,b in zip(rows,
            D.protection_pairs(self.blockers(),rows,pro,'left')) if b is None]
        self.assertEqual(free('half_slide'), ['left_edge'])
        self.assertEqual(free('six_bob'), ['offball_left'])
        for pro in ('half_slide','six_slide','six_bob'):
            pairs = D.protection_pairs(self.blockers(('HB',)),rows,pro,'left')
            self.assertTrue(all(pairs))
            self.assertEqual(len({b['pid'] for b in pairs}),6)

    def test_slide_direction_matters_and_presnap_read_does_not_know_blitzer(self):
        rows = self.front(); men=self.blockers()
        self.assertNotEqual(D.protection_pairs(men,rows,'half_slide','left'),
                            D.protection_pairs(men,rows,'half_slide','right'))
        defense=unit('4-3','base'); front=D.assignments(defense)
        side=D.protection_slide_side(front)
        for blitz in (a['player']['pid'] for a in front if a['alignment'].startswith('offball')):
            selected=D.select_rush(defense,dict(call('4-3','base',5),blitzer_ids=[blitz]))
            self.assertIn(blitz,{p['pid'] for p in selected['rushers']})
            self.assertEqual(D.protection_slide_side(D.assignments(defense)),side)

    def test_same_side_overload_can_leave_a_hot_defender_with_equal_body_counts(self):
        rows=[dict(player=dict(pid=str(i),pos='LEDG'),alignment=alignment)
              for i,alignment in enumerate(('left_edge','left_edge','left_interior','offball_left','corner_left'))]
        pairs=D.protection_pairs(self.blockers(),rows,'six_slide','left')
        self.assertGreater(sum(b is None for b in pairs),0)
        self.assertTrue(all(b is None or b['pos']!='LT' for b in pairs))
        out=P.resolve_protection(self.blockers(),[a['player'] for a in rows],
             np.random.default_rng(7),assignments=rows,protection='six_slide',slide_side='left')
        self.assertEqual(out['free_rushers'],sorted(a['player']['pid'] for a,b in zip(rows,pairs) if b is None))

    def test_actual_free_rush_triggers_quick_answer_when_count_math_says_no(self):
        original=P.resolve_protection
        def overloaded(*args,**kw):
            out=original(*args,**kw)
            out['free_rushers']=['unaccounted']; out['time']=6.
            return out
        trace=[]
        with patch.object(P,'resolve_protection',side_effect=overloaded), patch.object(P,'PASS_TRACE',trace):
            P.resolve_play(offense(),unit('4-3','nickel'),
                dict(is_pass=True,personnel='11',depth='deep',protection_pref='six'),
                dict(call('4-3','nickel'),shell='cover_2',box=6),70,np.random.default_rng(40))
        clocks=[r for r in trace if r.get('path')=='clock']
        self.assertTrue(clocks)
        self.assertTrue(all(r['hot'] for r in clocks))

    def test_reordering_players_and_roles_does_not_change_decision(self):
        rows=self.front();men=self.blockers(('HB',))
        def mapping(bs,rs):
            return {a['player']['pid']:(b or {}).get('pid') for a,b in zip(rs,D.protection_pairs(bs,rs,'six_slide','left'))}
        self.assertEqual(mapping(men,rows),mapping(men[::-1],rows[::-1]))

    def test_unreachable_hot_defender_does_not_prevent_adjacent_help(self):
        rows=[dict(player=dict(pid='dt'),alignment='left_interior'),
              dict(player=dict(pid='wide'),alignment='corner_left')]
        guard=dict(pid='RG',pos='RG'); center=dict(pid='C',pos='C')
        help_=D.protection_helpers([guard,center],rows,[guard,None],[.2,1.],'six_slide')
        self.assertEqual(help_,[[center],[]])

    def test_run_blocking_keeps_existing_role_matcher(self):
        rows=self.front();men=self.blockers(('TE',))
        self.assertEqual(D.protection_pairs(men,rows,protection='run'),D._run_pairs(men,rows))


if __name__=='__main__': unittest.main()

"""General protection help and simulated-pressure opportunity-cost checks."""
import copy
import unittest
from unittest.mock import patch

import numpy as np
import defensive_rush as R
import plays as P
from test_defensive_rush import unit, call


def blocker(pos, rating=70):
    return dict(pid=pos, pos=pos, pass_block_rating=rating,
                pass_block_power_rating=rating, pass_block_finesse_rating=rating,
                strength_rating=rating, awareness_rating=rating, agility_rating=rating)


class ProtectionPressureTests(unittest.TestCase):
    def setUp(self):
        self.defense = unit('4-3', 'nickel')
        self.plan = R.select_rush(self.defense, call('4-3', 'nickel'))
        self.blockers = [blocker(p) for p in ('LT', 'LG', 'C', 'RG', 'RT')]

    def resolve(self, blockers=None, seed=0, plan=None, **kwargs):
        plan = plan or self.plan
        return P.resolve_protection(self.blockers if blockers is None else blockers,
            plan['rushers'], np.random.default_rng(seed), assignments=plan['assignments'], **kwargs)

    def test_retained_helpers_change_actual_clock_pressure_sacks_and_winner(self):
        five = [self.resolve(seed=i) for i in range(800)]
        seven = [self.resolve(self.blockers + [blocker('TE'), blocker('HB')], seed=i,
                              protection='seven') for i in range(800)]
        self.assertGreater(np.mean([r['time'] for r in seven]), np.mean([r['time'] for r in five]) + .07)
        self.assertLess(np.mean([r['pressure'] for r in seven]), np.mean([r['pressure'] for r in five]))
        self.assertLess(sum(r['sack'] for r in seven), sum(r['sack'] for r in five))
        self.assertTrue(any(a['beaten_by'] != b['beaten_by'] for a,b in zip(five,seven)))
        self.assertTrue(all(b['time'] >= a['time'] for a,b in zip(five,seven)))

    def test_helper_quality_changes_assistance(self):
        weak = self.blockers + [blocker('TE', 25), blocker('HB', 25)]
        strong = self.blockers + [blocker('TE', 95), blocker('HB', 95)]
        low = [self.resolve(weak, seed=i) for i in range(200)]
        high = [self.resolve(strong, seed=i) for i in range(200)]
        self.assertGreater(np.mean([r['time'] for r in high]), np.mean([r['time'] for r in low]))
        self.assertEqual(low[0]['pb_helpers'], high[0]['pb_helpers'])

    def test_helper_assignments_do_not_see_the_random_winner(self):
        class Rolls:
            def __init__(self, times): self.times = iter(times)
            def lognormal(self, *args): return next(self.times)
            def random(self): return .999
        results = [P.resolve_protection(self.blockers, self.plan['rushers'], Rolls(times),
                    assignments=self.plan['assignments'])
                   for times in ((.5, 1, 1, 1), (1, 1, 1, .5))]
        self.assertNotEqual(results[0]['beaten_by'], results[1]['beaten_by'])
        self.assertEqual(results[0]['pb_helpers'], results[1]['pb_helpers'])
        helped = dict(results[0]['pb_helpers'])
        alignment = {r['player']['pid']:r['alignment'] for r in self.plan['assignments']}
        self.assertIn(alignment[helped['C']], R.INTERIOR)

    def test_help_uses_known_threat_and_reachable_gap(self):
        plan = copy.deepcopy(self.plan)
        for r in plan['rushers']:
            if r['pid'] == 'DTL': r.update(power_moves_rating=99, finesse_moves_rating=99)
        result = self.resolve(plan=plan)
        self.assertEqual(dict(result['pb_helpers'])['C'], 'DTL')
        result = self.resolve(self.blockers+[blocker('TE')], plan=plan)
        alignment = {r['player']['pid']:r['alignment'] for r in plan['assignments']}
        self.assertIn(alignment[dict(result['pb_helpers'])['TE']], R.EDGES)

    def test_slide_and_man_protection_assign_back_differently(self):
        blockers = self.blockers + [blocker('HB')]
        man = dict(self.resolve(blockers, protection='six_bob')['pb_helpers'])
        slide = dict(self.resolve(blockers, protection='six_slide')['pb_helpers'])
        alignment = {r['player']['pid']:r['alignment'] for r in self.plan['assignments']}
        self.assertIn(alignment[man['HB']], R.EDGES)
        self.assertIn(alignment[slide['HB']], R.INTERIOR)

    def test_helpers_share_actual_rep_and_have_unique_assignments(self):
        blockers = self.blockers+[blocker('TE'),blocker('HB')]
        for seed in range(30):
            result = self.resolve(blockers, seed=seed)
            pb, pr = dict(result['pb_reps']), dict(result['pr_reps'])
            self.assertEqual(len(result['pb_reps']), len(blockers))
            self.assertEqual(len(result['pb_helpers']), len(dict(result['pb_helpers'])))
            for helper, rusher in result['pb_helpers']:
                self.assertEqual(pb[helper], not pr[rusher])

    def test_order_and_duplicate_blocker_input_cannot_create_extra_help(self):
        blockers = self.blockers+[blocker('TE'),blocker('HB')]
        plan = dict(rushers=self.plan['rushers'][::-1], assignments=self.plan['assignments'][::-1])
        self.assertEqual(self.resolve(blockers, seed=4), self.resolve(blockers[::-1],seed=4,plan=plan))
        self.assertEqual(self.resolve(blockers), self.resolve(blockers+[dict(blockers[-1])]))

    def test_free_rusher_and_zero_rushers_remain_valid(self):
        blitz = R.select_rush(self.defense, dict(call('4-3','nickel',7), coverage='cover_0'))
        result = self.resolve(plan=blitz)
        self.assertEqual(result['time'], .6)
        self.assertIsNone(result['beaten'])
        self.assertFalse(result['pb_helpers'])
        empty = self.resolve(plan=dict(rushers=[], assignments=[]))
        self.assertEqual(empty['time'], 6)
        self.assertEqual(empty['pressure'], 0)

    def test_chip_still_buys_time(self):
        plain = [self.resolve(seed=i)['time'] for i in range(100)]
        chipped = [self.resolve(seed=i, chip=(blocker('TE',95),0))['time'] for i in range(100)]
        self.assertGreater(np.mean(chipped), np.mean(plain))

    def test_edge_and_interior_talent_still_matter_with_helpers(self):
        blockers = self.blockers + [blocker('TE'),blocker('HB')]
        for positions in (R.EDGES, R.INTERIOR):
            times = []
            for grade in (35,95):
                plan = copy.deepcopy(self.plan)
                for a in plan['assignments']:
                    if a['alignment'] in positions:
                        a['player'].update(power_moves_rating=grade,finesse_moves_rating=grade)
                times.append(np.mean([self.resolve(blockers,seed=i,plan=plan)['time'] for i in range(200)]))
            self.assertLess(times[1],times[0])

    def exchange_defense(self):
        d = copy.deepcopy(self.defense)
        # Generic edge profiles reproduce the opportunity-cost problem.
        for p in d['dl']:
            if p['pos']=='REDG': p.update(power_moves_rating=95,finesse_moves_rating=95,zone_cover_rating=64)
            if p['pos']=='LEDG': p.update(power_moves_rating=76,finesse_moves_rating=76,zone_cover_rating=44)
        return d

    def test_sim_exchange_usually_preserves_premier_rusher_without_forbidding_drops(self):
        d = self.exchange_defense(); c = call('4-3','nickel',4,sim_pressure=True)
        results = [R.select_rush(d,c,np.random.default_rng(i)) for i in range(500)]
        dropped = sum('RE' not in {p['pid'] for p in row['rushers']} for row in results)
        self.assertGreater(dropped,0)
        self.assertLess(dropped,75)
        self.assertIn('RE',{p['pid'] for p in R.select_rush(d,c)['rushers']})

    def test_replacement_rusher_and_lost_coverage_both_matter(self):
        d = self.exchange_defense(); c = call('4-3','nickel',4,sim_pressure=True)
        for p in d['lb']:
            if p['pid']=='LB0': p.update(power_moves_rating=95,finesse_moves_rating=95,zone_cover_rating=35)
            else: p.update(power_moves_rating=35,finesse_moves_rating=35,zone_cover_rating=95)
        selected = R.select_rush(d,c)
        self.assertIn('LB0',{p['pid'] for p in selected['rushers']})
        self.assertNotIn('LB1',{p['pid'] for p in selected['rushers']})
        dropped = next(a for a in selected['coverage']['defensive_assignments'] if a['player']['pid']=='LE')
        self.assertEqual(dropped['alignment'],'offball_left')

    def test_legitimate_good_covering_edge_can_drop(self):
        d = self.defense
        for p in d['dl']:
            if p['pos']=='REDG':p['zone_cover_rating']=95
            if p['pos']=='LEDG':p['zone_cover_rating']=20
        selected=R.select_rush(d,call('4-3','nickel',4,sim_pressure=True))
        self.assertNotIn('RE',{p['pid'] for p in selected['rushers']})

    def test_explicit_rush_call_and_deep_shell_are_preserved(self):
        d=self.exchange_defense()
        c=call('4-3','nickel',4,sim_pressure=True,rusher_ids=['LE','DTL','DTR','RE'])
        self.assertEqual({p['pid'] for p in R.select_rush(d,c)['rushers']},set(c['rusher_ids']))
        for front in ('3-4','4-3'):
            for package in ('base','nickel','dime'):
                d=unit(front,package);c=call(front,package,4,sim_pressure=True)
                a=R.select_rush(d,c,np.random.default_rng(5))
                ids={p['pid'] for p in a['rushers']}
                cover={p['pid'] for group in R.GROUPS for p in a['coverage'][group]}
                self.assertEqual(len(ids),4);self.assertEqual(len(ids|cover),11)
                self.assertFalse(ids&cover);self.assertTrue({'FS','SS'}<=cover)
                perm=copy.deepcopy(d)
                for group in (*R.GROUPS,'defensive_assignments'):perm[group].reverse()
                b=R.select_rush(perm,c,np.random.default_rng(5))
                self.assertEqual([p['pid'] for p in a['rushers']],[p['pid'] for p in b['rushers']])

    def test_real_rosters_wire_retained_protection_and_exchange_into_live_resolver(self):
        import game
        import rosters
        import schemes
        teams = rosters.load_league()
        for home, away, family, package in (('GB','DEN','3-4','base'),
                                             ('DAL','MIN','4-3','nickel'),
                                             ('BUF','CHI','4-3','dime'),
                                             ('LAC','KC','3-4','nickel')):
            rng = np.random.default_rng(17)
            off, _ = game.field_units(teams[home], None, rng, True, '11')
            defense, _ = game.field_units(teams[away], None, rng, False, package, family)
            oc = dict(is_pass=True,personnel='11',depth='medium',concept='dagger',
                      down=2,ydstogo=8,play_action=False,shotgun=True)
            dc = schemes.call_defense(oc,2,8,rng)
            dc.update(front_family=family,personnel=package,rushers=4,sim_pressure=True)
            with patch.object(schemes,'choose_protection',return_value='seven'), \
                 patch.object(P,'resolve_protection',wraps=P.resolve_protection) as protect, \
                 patch.object(R,'select_rush',wraps=R.select_rush) as select:
                out = P._pass_play(off,defense,oc,dc,50,rng)
            self.assertEqual(len(protect.call_args.args[0]),7)
            self.assertEqual(protect.call_args.kwargs['protection'],'seven')
            self.assertIs(select.call_args.kwargs['rng'],rng)
            opportunities = dict(out['pb_opportunities'])
            self.assertEqual(len(opportunities), 7)
            contested = {pid for pid, kind in opportunities.items() if kind != 'unengaged'}
            self.assertEqual({pid for pid, won in out['pb_reps']}, contested)
            self.assertEqual(len(out['pb_reps']), len(contested))


if __name__ == '__main__':unittest.main()

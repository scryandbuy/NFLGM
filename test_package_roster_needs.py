"""Personnel choices must value deployment, including ordinary subpackages."""
import copy
import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import patch

import defense_roles as DR
import offense_roles as OR
import roster_needs as RN
from test_roster_needs import Team


def player(pos, number, overall=78, block=None):
    ratings = {} if block is None else {key: block for key in
        ('run_block_rating', 'lead_block_rating', 'impact_block_rating', 'strength_rating')}
    return SimpleNamespace(pid=f'{pos}-{number}', pos=pos, ovr=float(overall), ratings=ratings,
                           out_until=None, weight=320 if pos=='DT' else 240)


def team(base='11', front='4-3'):
    players = [player(pos, i) for pos in RN.POSITIONS for i in range(6 if pos in ('WR','CB','DT') else 3)]
    return Team(front, base, players)


class PackageRosterTests(unittest.TestCase):
    def test_base_is_plurality_and_each_mapping_is_independent(self):
        for package in OR.PACKAGES:
            gm = SimpleNamespace(off_personnel=package)
            weights = OR.package_weights(gm)
            self.assertAlmostEqual(sum(weights.values()), 1)
            self.assertEqual(max(weights, key=weights.get), package)
            self.assertLess(weights[package], .7)
            weights['11'] = 99
            self.assertLess(OR.package_weights(gm)['11'], 1)

    def test_air_raid_values_fourth_receiver_more_than_eleven(self):
        t = team()
        for p in t.roster:
            if p.pos=='WR': p.ovr=90 if int(p.pid[-1])<3 else 55
        arrival = player('WR', 'new', 80)
        spread = RN.move_gain(t, arrival)
        t.gm.off_personnel='10'
        air = RN.move_gain(t, arrival)
        self.assertGreater(air, spread * 3)
        self.assertGreater(air, 10)

    def test_heavy_second_te_prefers_blocking_with_equal_overall(self):
        t=team('12')
        for p in t.roster:
            if p.pos=='TE':
                p.ovr=90 if p.pid=='TE-0' else 75
                p.ratings={key:50 for key in ('run_block_rating','lead_block_rating','impact_block_rating','strength_rating')}
        good=player('TE','good',75,95); weak=player('TE','weak',75,40)
        baseline=RN.assess(t)
        self.assertGreater(RN.move_gain(t,good,baseline=baseline),RN.move_gain(t,weak,baseline=baseline)+5)
        updated=RN.assess(t, t.roster+[good])
        roles=[r for r in updated['package_assignments'] if r['variant']=='offense:12' and r['role']=='TE']
        self.assertEqual([r['player'].pid for r in roles], ['TE-0',good.pid])

    def test_twenty_one_preserves_blocking_te_as_second_back(self):
        t=team('21');t.roster=[p for p in t.roster if p.pos!='FB']
        for p in t.roster:
            if p.pos in ('TE','HB'):
                p.ratings={key:40 for key in ('run_block_rating','lead_block_rating','impact_block_rating','strength_rating')}
        blocker=next(p for p in t.roster if p.pid=='TE-2')
        blocker.ratings={key:99 for key in ('run_block_rating','lead_block_rating','impact_block_rating','strength_rating')}
        report=RN.assess(t)
        rows=[r for r in report['package_assignments'] if r['variant']=='offense:21']
        self.assertEqual(next(r['player'].pid for r in rows if r['role']=='FB'),blocker.pid)
        self.assertEqual(len({r['player'].pid for r in rows}),11)

    def test_nickel_and_dime_value_third_and_fourth_corners_by_share(self):
        t=team()
        for p in t.roster:
            if p.pos=='CB':p.ovr=[90,90,60,50,45,40][int(p.pid[-1])]
        variants=[dict(front='4-3',package=package,big_nickel=False,share=share,
                       slots=DR.role_slots('4-3',package)) for package,share in [('nickel',.8),('dime',.2)]]
        with patch.object(DR,'planning_profile',return_value=dict(variants=variants)):
            baseline=RN.assess(t)
            third=RN.move_gain(t,player('CB','new',78),baseline=baseline)
            fourth=RN.move_gain(t,player('CB','new',55),baseline=baseline)
        self.assertGreater(third,10)
        self.assertAlmostEqual(fourth,1.0)

    def test_multiple_front_variants_have_unique_players_and_do_not_mutate(self):
        t=team(front='multiple'); before=copy.deepcopy(t.__dict__)
        report=RN.assess(t)
        rows=report['package_assignments']
        self.assertEqual({r['front'] for r in rows if r['side']=='defense'}, {'3-4','4-3'})
        variants=defaultdict(list)
        for row in rows: variants[row['variant']].append(row)
        for lineup in variants.values():
            self.assertEqual(len(lineup),11)
            self.assertEqual(len({r['player'].pid for r in lineup}),11)
        for side in ('offense','defense'):
            self.assertAlmostEqual(sum(v[0]['weight'] for v in variants.values() if v[0]['side']==side),1)
        self.assertEqual(t.__dict__,before)

    def test_cached_gain_matches_full_reassessment_and_unrelated_player_does_not_help(self):
        t=team(); baseline=RN.assess(t)
        for pos in ('QB','WR','TE','DT','CB','K'):
            arrival=player(pos,'new',86)
            departure=next(p for p in t.roster if p.pos==pos)
            players=[p for p in t.roster if p.pid!=departure.pid]+[arrival]
            expected=RN.assess(t,players)['score']-baseline['score']
            self.assertAlmostEqual(RN.move_gain(t,arrival,departure,baseline),expected)
        self.assertAlmostEqual(RN.move_gain(t,player('QB','weak',40),baseline=baseline),0)
        self.assertEqual(RN.candidate_gains(t,[player('QB','weak',40)],baseline), {'QB-weak':0})

    def test_cutdown_strength_does_not_ignore_subpackage_upgrades(self):
        t=team('11')
        for p in t.roster:
            if p.pos=='WR':p.ovr=90 if int(p.pid[-1])<3 else 55
        before_missing,before=RN.lineup_strength(t,t.roster)
        after_missing,after=RN.lineup_strength(t,t.roster+[player('WR','new',80)])
        self.assertEqual(before_missing,after_missing)
        self.assertGreater(after,before)


if __name__=='__main__': unittest.main()

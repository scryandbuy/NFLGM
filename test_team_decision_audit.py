"""Real-roster regression probes after package-aware personnel integration."""
import copy
import unittest
from collections import defaultdict

import numpy as np
import cutdown
import roster_needs as RN
from session import Session


class TeamDecisionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = Session.new('GB', seed=93030).save()

    def test_all_teams_cutdown_preserves_playable_packages_without_mutation(self):
        s = Session.load(self.initial)
        original = s.L.save()
        random_state = copy.deepcopy(s.rng.bit_generator.state)
        for abbr, team in s.L.teams.items():
            with self.subTest(team=abbr, base=team.gm.off_personnel, front=team.gm.def_front):
                men = team.active()
                before = RN.assess(team)
                keep = RN.select_cutdown(team, cutdown.rows_for(team))
                self.assertEqual(len(keep), min(53, len(men)))
                self.assertLessEqual(keep, {p.pid for p in men})
                retained = [p for p in men if p.pid in keep]
                after = RN.assess(team, retained)
                grouped = defaultdict(list)
                for row in after['package_assignments']: grouped[row['variant']].append(row)
                for variant, rows in grouped.items():
                    players = [r['player'].pid for r in rows if r['player']]
                    self.assertEqual(len(players), len(set(players)), (abbr, variant))
                    old_missing = sum(r['player'] is None for r in before['package_assignments'] if r['variant']==variant)
                    self.assertLessEqual(11-len(players), old_missing, (abbr, variant))
                for pos in ('QB','LT','LG','C','RG','RT','K','P','LS'):
                    if any(p.pos==pos for p in men):
                        self.assertTrue(any(p.pos==pos for p in retained), (abbr,pos))
        self.assertEqual(s.L.save(), original)
        self.assertEqual(s.rng.bit_generator.state, random_state)

    def test_all_teams_cached_move_comparison_matches_proposed_roster(self):
        s = Session.load(self.initial)
        candidates = {}
        for team in s.L.teams.values():
            for p in team.active():
                if p.pos not in candidates or p.ovr>candidates[p.pos].ovr:
                    candidates[p.pos]=p
        for abbr, team in s.L.teams.items():
            before=RN.assess(team)
            for pos in ('WR','TE','DT','CB'):
                arrival=copy.deepcopy(candidates[pos]);arrival.pid='audit-'+abbr+'-'+pos
                departure=min((p for p in team.active() if p.pos==pos),key=lambda p:p.ovr,default=None)
                proposed=[p for p in team.active() if departure is None or p.pid!=departure.pid]+[arrival]
                direct=RN.assess(team,proposed)['score']-before['score']
                self.assertAlmostEqual(RN.move_gain(team,arrival,departure,before),direct,
                                       places=7,msg=(abbr,pos))


if __name__=='__main__': unittest.main()

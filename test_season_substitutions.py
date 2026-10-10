import copy
import unittest
from unittest.mock import patch
import numpy as np
import game as G
import rosters
import game_substitutions as S

class SeasonSubstitutions(unittest.TestCase):
    def setUp(self):
        self.r = copy.deepcopy(rosters.load_league()['GB'])
        self.st = G.TeamState(self.r, coach={'starter_protection': .5})
        self.a, self.b = self.r['depth']['QB'][:2]
        self.a['age'], self.b['age'] = 32, 23
        self.st.season_rest = dict(mode='eliminated', week=18)
        self.st.rest_draws = {self.a['pid']: 0.}
        self.scoring = patch.object(S.targets, 'position_score', return_value=75)
        self.scoring.start()
        self.addCleanup(self.scoring.stop)

    def probability(self, seconds=900, playoffs=False):
        return S.season_probability(self.a, self.b, 'QB', self.st, seconds, playoffs)

    def test_eliminated_veteran_gives_ready_young_qb_real_snaps_after_half(self):
        self.assertEqual(self.probability(2700), 0)
        view = S.for_possession(self.r, self.st, 900, 0, np.random.default_rng(2))
        self.assertEqual(view['qb']['pid'], self.b['pid'])
        unit, positions = G.field_units(view, self.st, np.random.default_rng(4), True, '11')
        self.assertEqual(unit['qb']['pid'], self.b['pid'])
        self.assertEqual(self.st.snaps[self.b['pid']], 1)
        self.assertEqual(len(positions), 11)
        self.assertEqual(self.r['qb']['pid'], self.a['pid'])

    def test_restraint_young_starter_older_backup_bad_backup(self):
        self.a['age'] = 25
        self.assertEqual(self.probability(), 0)
        self.a['age'], self.b['age'] = 32, 29
        self.assertEqual(self.probability(), 0)
        self.b['age'] = 23
        with patch.object(S.targets, 'position_score', side_effect=[90, 60]):
            self.assertEqual(self.probability(), 0)
        self.st.cond.cond[self.b['pid']] = 60
        self.assertEqual(self.probability(), 0)

    def test_locked_seed_coach_age_and_condition_matter(self):
        self.st.season_rest['mode'] = 'locked'
        base = self.probability()
        self.st.coach['starter_protection'] = 1
        self.assertGreater(self.probability(), base)
        self.st.coach['starter_protection'] = .5
        self.st.cond.cond[self.a['pid']] = 70
        self.assertGreater(self.probability(), base)
        self.a['age'] = 23
        self.assertLess(self.probability(), base)
        self.assertLess(self.probability(3600), self.probability(900))

    def test_no_mode_or_playoffs_preserves_starters(self):
        self.assertEqual(self.probability(playoffs=True), 0)
        self.st.season_rest['mode'] = None
        self.assertEqual(self.probability(), 0)
        self.assertIs(S.for_possession(self.r,self.st,900,0,np.random.default_rng(2)), self.r)

    def test_injured_backup_is_not_used_and_choices_are_stable(self):
        self.st.out.update(p['pid'] for p in self.r['depth']['QB'][1:])
        view = S.for_possession(self.r,self.st,900,0,np.random.default_rng(2))
        self.assertEqual(view['qb']['pid'], self.a['pid'])
        self.st.out.clear()
        one = S.for_possession(self.r,self.st,900,0,np.random.default_rng(2))
        two = S.for_possession(self.r,self.st,900,0,np.random.default_rng(99))
        self.assertEqual(one['qb']['pid'],two['qb']['pid'])

if __name__ == '__main__': unittest.main()

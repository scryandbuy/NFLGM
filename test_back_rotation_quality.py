"""HB rotation uses the eligible alternatives' real grades, preserving the chart."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import game
import offense_roles as OR
import rosters
import targets as TG
from test_offense_personnel import roster


def set_grade(p, grade):
    p.update({key: grade for key in TG.DEPTH_WEIGHTS['HB']})


class BackRotationQualityTests(unittest.TestCase):
    def choose(self, grade, condition, seed, pinned=False):
        team = roster()
        for p, value in zip(team['depth']['HB'], (grade, 75, 70)): set_grade(p, value)
        if pinned:
            team['depth']['HB'].reverse()
        state = game.TeamState(team)
        state.cond.cond[team['depth']['HB'][0]['pid']] = condition
        return OR.field(team, '11', np.random.default_rng(seed), state)['rb']['pid']

    def test_live_field_rest_decision_uses_real_quality_gap(self):
        star = sum(self.choose(95, 70, seed) == 'HB0' for seed in range(200))
        peer = sum(self.choose(77, 70, seed) == 'HB0' for seed in range(200))
        self.assertGreater(star, peer + 40)

    def test_remaining_alternatives_and_emergencies_use_same_back_grade(self):
        men = [dict(pid=str(i), pos='HB' if i < 3 else 'WR', ovr=99)
               for i in range(4)]
        for p, value in zip(men, (90, 60, 80, 50)): set_grade(p, value)
        self.assertEqual(OR.back_quality_gaps(men), [.5, -1, 1, 0])
        self.assertEqual(OR.back_quality_gaps(men[1:]), [-1, 1, 0])
        self.assertEqual(OR.back_quality_gaps(men[:1]), [0])

    def test_fresh_pinned_lower_grade_starter_is_not_reordered(self):
        for seed in range(50): self.assertEqual(self.choose(99, 100, seed, pinned=True), 'HB2')

    def test_exhausted_star_can_rest(self):
        self.assertGreater(sum(self.choose(99, 20, seed) != 'HB0' for seed in range(100)), 90)

    def test_legacy_field_path_uses_same_gap_without_reordering_pinned_back(self):
        team = roster()
        for p, value in zip(team['backs'], (90, 80, 70)): set_grade(p, value)
        team['backs'] = list(reversed(team['backs']))
        state = game.TeamState(team)
        with patch.object(state.cond, 'needs_rest', return_value=False) as rest:
            unit, _ = game.field_units(team, state, np.random.default_rng(3), True)
        self.assertEqual(unit['rb']['pid'], 'HB2')
        back_check = next(call.args for call in rest.call_args_list if call.args[0] == 'HB2')
        self.assertEqual(back_check[-1], -1.0)

    def test_healthy_filtered_candidates_drive_gap_and_two_back_uniqueness(self):
        team = roster(); state = game.TeamState(team); state.out = {'HB0'}
        team['depth']['FB'] = []; team['fullbacks'] = []
        for p, value in zip(team['depth']['HB'], (99, 80, 70)): set_grade(p, value)
        with patch.object(OR, 'back_quality_gaps', wraps=OR.back_quality_gaps) as gaps:
            unit, positions = game.field_units(team, state, np.random.default_rng(8), True, '21')
        self.assertNotIn('HB0', [p['pid'] for p in gaps.call_args.args[0]])
        self.assertEqual(len(positions), 11)
        rows = unit['offensive_assignments']
        self.assertEqual(len({p['pid'] for _, p in rows}), 11)
        self.assertNotEqual(next(p['pid'] for role, p in rows if role == 'HB'),
                            next(p['pid'] for role, p in rows if role == 'FB'))

    def test_actual_roster_with_series_recovery_keeps_quality_and_coach_effects(self):
        original = rosters.load_league()['NE']

        def share(grade, policy):
            team = copy.deepcopy(original)
            lead = team['depth']['HB'][0]
            set_grade(lead, grade)
            total = 0
            for seed in range(12):
                state = game.TeamState(team, policy=policy); rng = np.random.default_rng(seed)
                for length in (6, 4, 8, 3, 10, 5, 7, 6, 4, 7):
                    for _ in range(length):
                        game.field_units(team, state, rng, True, '11')
                    state.sideline_recovery(6)
                total += state.snaps.get(lead['pid'], 0)
            return total / (12 * 60)

        self.assertGreater(share(99, .5), share(84, .5))
        self.assertGreater(share(99, .1), share(99, .9))
        self.assertLess(share(99, .1), .95)


if __name__ == '__main__': unittest.main()

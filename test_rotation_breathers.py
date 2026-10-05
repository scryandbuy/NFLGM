"""Physical idle time and proactive breathers preserve football choices."""
import unittest
from types import SimpleNamespace as NS

import numpy as np
import defense_roles as D
import offense_roles as O
import health as H


def player(pid, pos, grade=90, stamina=85):
    p = dict(pid=pid, pos=pos, stamina_rating=stamina)
    for name in ('finesse_moves', 'power_moves', 'accel', 'speed', 'block_shed',
                 'strength', 'tackle', 'pursuit', 'play_rec', 'awareness',
                 'carry', 'bcv', 'agility', 'break_tackle', 'trucking',
                 'spin_move', 'juke_move', 'stiff_arm', 'catch', 'run_block',
                 'pass_block'):
        p[name + '_rating'] = grade
    return p


def offense_with_backs(backs):
    depth = {pos: [player(pos, pos)] for pos in ('QB', *O.OL, 'TE')}
    depth['WR'] = [player('WR' + str(i), 'WR') for i in range(3)]
    depth['HB'] = backs
    return depth


def drive_share(role='LEDG', stamina=85, backup_grade=80, drive_length=6,
                policy=.5, important=False):
    """Eight series separated by equal physical idle opportunities, 80 seeds.

    No play outcomes or arbitrary usage quotas: production selection and
    Condition debit/rest methods choose each snap from the same two players.
    """
    selected = total = 0
    for seed in range(80):
        a = player('starter', role, 90, stamina)
        b = player('reserve', role, backup_grade, 80)
        state = NS(cond=H.Condition(policy), rotation_context=dict(
            down=3 if important else 1, to_go=8, score_diff=0))
        depth = offense_with_backs([a, b]) if role == 'HB' else None
        rng = np.random.default_rng(28500 + seed)
        for series in range(8):
            for snap in range(drive_length):
                if role == 'HB':
                    rows = O.assign(depth, '11', rng=rng, state=state)
                    chosen = next(p for assigned, p in rows if assigned == 'HB')
                else:
                    chosen = D.rotation_choice(dict(player=a,
                        role='DT' if role == 'DT' else 'RE'), [b], state, rng)
                selected += chosen is a
                total += 1
                for p in (a, b):
                    if p is chosen:
                        state.cond.play(p['pid'], role, p['stamina_rating'])
                    else:
                        state.cond.rest(p['pid'])
            for idle in range(drive_length):
                state.cond.rest('starter')
                state.cond.rest('reserve')
    return selected / total


class RotationBreatherTests(unittest.TestCase):
    def test_fully_fresh_players_do_not_need_fatigue_substitution(self):
        for pos in ('LEDG', 'REDG', 'DT', 'HB'):
            for policy in (0., .5, 1.):
                for gap in (-1., 0., 1.25):
                    c = H.Condition(policy)
                    for seed in range(30):
                        self.assertFalse(c.needs_rest('P', pos,
                            np.random.default_rng(seed), 70, gap))

    def test_repeated_explosive_work_produces_breathers(self):
        for role in ('LEDG', 'DT', 'HB'):
            share = drive_share(role)
            self.assertGreater(share, .5, role)
            self.assertLess(share, .99, role)

    def test_long_series_need_more_relief_than_three_and_outs(self):
        for role in ('LEDG', 'HB'):
            short = drive_share(role, drive_length=3)
            long = drive_share(role, drive_length=12)
            self.assertGreater(short, long + .1, role)

    def test_stamina_and_reserve_quality_both_matter(self):
        for role in ('LEDG', 'HB'):
            self.assertGreater(drive_share(role, stamina=95),
                               drive_share(role, stamina=55) + .05)
            self.assertGreater(drive_share(role, backup_grade=65),
                               drive_share(role, backup_grade=90) + .03)

    def test_coach_breather_preference_changes_usage(self):
        self.assertGreater(drive_share(policy=0.), drive_share(policy=1.) + .05)

    def test_actual_team_coach_preference_reaches_selection(self):
        import game
        a, b = player('starter', 'LEDG'), player('reserve', 'LEDG', 80)
        counts = []
        for preference in (0., 1.):
            state = game.TeamState({}, policy=.5,
                                   coach={'starter_protection': preference})
            state.cond.cond = {'starter': 91., 'reserve': 100.}
            counts.append(sum(D.rotation_choice(dict(player=a, role='RE'),
                [b], state, np.random.default_rng(seed)) is a for seed in range(500)))
        self.assertGreater(counts[0], counts[1] + 100)

    def test_key_third_down_retains_star_but_not_exhausted_star(self):
        a, b = player('star', 'LEDG', 95), player('reserve', 'LEDG', 75)
        def retained(condition, down, distance, margin=0):
            count = 0
            for seed in range(1000):
                cond = H.Condition()
                cond.cond = {'star': condition, 'reserve': 100.}
                state = NS(cond=cond, rotation_context=dict(
                    down=down, to_go=distance, score_diff=margin))
                chosen = D.rotation_choice(dict(player=a, role='RE'), [b],
                                            state, np.random.default_rng(seed))
                count += chosen is a
            return count
        neutral = retained(87., 1, 8)
        self.assertGreater(retained(87., 3, 8), neutral + 40)
        self.assertEqual(retained(87., 3, 1), neutral)
        self.assertEqual(retained(87., 3, 8, 24), neutral)
        self.assertLess(retained(25., 3, 8), 100)

    def test_short_series_preserve_healthy_qb_and_line_continuity(self):
        for seed in range(30):
            depth = offense_with_backs([player('HB1', 'HB'), player('HB2', 'HB', 80)])
            state = NS(cond=H.Condition())
            rng = np.random.default_rng(seed)
            for series in range(8):
                for snap in range(6):
                    rows = O.assign(depth, '11', rng=rng, state=state)
                    for role, p in rows:
                        if role in ('QB', *O.OL):
                            self.assertEqual(p['pid'], role)
                            state.cond.play(p['pid'], role, p['stamina_rating'])
                for idle in range(6):
                    for role in ('QB', *O.OL): state.cond.rest(role)


if __name__ == '__main__':
    unittest.main()

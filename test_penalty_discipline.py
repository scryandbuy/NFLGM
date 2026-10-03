"""Discipline changes eligible foul risk, without changing unrelated systems."""
import copy
import json
import unittest
from unittest.mock import patch
import numpy as np
import events as E
import game as G
import penalty_players as PP
import personality as P
import plays
import rosters
import schemes


class Probe:
    def __init__(self, roll=0): self.roll = roll; self.weights = {}
    def random(self): return self.roll
    def choice(self, options, p):
        if isinstance(options, int): return 0
        self.weights = {E._names[i]: float(w) for i, w in zip(options, p)}
        return next(i for i, w in zip(options, p) if w > 0)


def rates(**kw):
    probe = Probe()
    E.penalty_check(probe, **kw)
    lo, hi = 0., 1.
    for _ in range(30):
        mid = (lo + hi) / 2
        if E.penalty_check(Probe(mid), **kw) is None: hi = mid
        else: lo = mid
    return {n: w * (lo + hi) / 2 for n, w in probe.weights.items()}


def row(pid, role, discipline):
    return role, dict(pid=pid, pos=role, traits=dict(discipline=discipline, work_ethic=50))


class DisciplineTests(unittest.TestCase):
    def test_bounded_rates_and_team_foul_independence(self):
        results = []
        for discipline in (0, 50, 100):
            results.append(rates(offense_players=[row('o', 'LT', discipline)],
                                 defense_players=[row('d', 'DL', discipline), row('c', 'DB', discipline)]))
        low, mid, high = results
        for name, bound in [('False Start', .10), ('Roughing the Passer', .20), ('Offensive Holding', .05)]:
            self.assertAlmostEqual(low[name] / mid[name], 1+bound, places=6)
            self.assertAlmostEqual(high[name] / mid[name], 1-bound, places=6)
        for name in PP.TEAM_FOULS:
            self.assertAlmostEqual(low[name], high[name], places=8)

    def test_split_checks_preserve_neutral_marginal_probability(self):
        all_rates = rates()
        pre = rates(timing='pre')
        live = rates(timing='live')
        survival = 1 - sum(pre.values())
        for name, chance in all_rates.items():
            self.assertAlmostEqual(pre.get(name, 0) + survival*live.get(name, 0), chance, places=8)

    def test_actual_blockers_and_rushers_only(self):
        rows = [row('rush', 'DL', 50), row('drop', 'LB', 0), row('corner', 'DB', 0)]
        evidence = {'pr_reps': [('rush', True)], 'pb_reps': [('tackle', True)]}
        self.assertEqual([p['pid'] for _, p in PP.eligible('Roughing the Passer', rows, evidence)], ['rush'])
        off = [row('tackle', 'LT', 50), row('receiving-back', 'HB', 0)]
        self.assertEqual([p['pid'] for _, p in PP.eligible('Offensive Holding', off, evidence)], ['tackle'])
        a = rates(offense_players=off, defense_players=rows, outcome=evidence)
        rows[1][1]['traits']['discipline'] = 100
        b = rates(offense_players=off, defense_players=rows, outcome=evidence)
        self.assertAlmostEqual(a['Roughing the Passer'], b['Roughing the Passer'], places=8)

    def test_unused_depth_and_work_ethic_cannot_change_risk(self):
        starter = row('starter', 'LT', 50)
        roster = {'offensive_assignments': [starter], 'depth': {'LT': [starter[1], row('bench', 'LT', 0)[1]]}}
        a = rates(offense_players=PP.unit(roster, True))
        roster['depth']['LT'][1]['traits']['discipline'] = 100
        starter[1]['traits']['work_ethic'] = 100
        self.assertEqual(a, rates(offense_players=PP.unit(roster, True)))

    def test_interference_uses_actual_target_coverage(self):
        rows = [row('owner', 'DB', 50), row('unrelated', 'DB', 0), row('drop', 'DL', 50)]
        out = dict(coverage_evidence=dict(primary='owner', helper='drop', drops=[('owner', 'outside', 'man'), ('drop', 'other', 'zone')]))
        self.assertEqual({p['pid'] for _, p in PP.eligible('Defensive Pass Interference', rows, out)}, {'owner', 'drop'})
        out['coverage_evidence'].update(primary=None, helper=None)
        self.assertEqual(PP.eligible('Defensive Pass Interference', rows, out), [])

    def test_contact_fouls_exclude_remote_players(self):
        off = [row('runner', 'HB', 50), row('blocker', 'LT', 50), row('remote-wr', 'WR', 0)]
        deff = [row('tackler', 'LB', 50), row('front', 'DL', 50), row('remote-safety', 'DB', 0)]
        out = dict(type='run', carrier='runner', tackler='tackler', rb_reps=[('blocker', True)], run_support=[])
        self.assertEqual([p['pid'] for _, p in PP.eligible('Offensive Holding', off, out)], ['blocker'])
        for name in ('Face Mask', 'Unnecessary Roughness'):
            self.assertEqual({p['pid'] for _, p in PP.eligible(name, off, out)}, {'runner', 'blocker'})
            self.assertEqual({p['pid'] for _, p in PP.eligible(name, deff, out)}, {'tackler', 'front'})

    def test_attribution_is_weighted_and_survives_json(self):
        profile = PP.profile('Unnecessary Roughness', [row('low', 'DL', 0), row('high', 'DL', 100)])
        rng = np.random.default_rng(311)
        count = dict(low=0, high=0)
        for _ in range(6000):
            flag = PP.attribute({'penalty': 'Unnecessary Roughness', 'yards': 7.5}, profile, rng)
            count[flag['offender_pid']] += 1
        self.assertGreater(count['low'] / count['high'], 1.35)
        book = G.StatBook()
        PP.decision(flag, True); PP.book_flag(book, flag)
        saved = json.loads(json.dumps(flag))
        self.assertEqual(flag, saved)
        self.assertEqual(book.p[flag['offender_pid']]['penalty_yards'], 7.5)
        PP.decision(saved, False); PP.book_flag(book, saved)
        self.assertEqual(book.p[flag['offender_pid']]['penalties_committed'], 2)
        self.assertEqual(book.p[flag['offender_pid']]['penalties_accepted'], 1)

    def test_special_teams_uses_only_selected_unit(self):
        low = [row('blocker', 'ST', 0)]
        high = [row('blocker', 'ST', 100)]
        self.assertIsNotNone(E.special_teams_penalty_check(Probe(.018), 'kickoff', returned=True, offense_players=low))
        self.assertIsNone(E.special_teams_penalty_check(Probe(.018), 'kickoff', returned=True, offense_players=high))

    def test_selection_deferred_until_snap_and_not_repeated(self):
        ros = rosters.load_league()['GB']
        state = G.TeamState(ros)
        before = copy.deepcopy((state.snaps, state.cond.cond, state.cond.snaps))
        pending = G._PendingSnap(state)
        rng = np.random.default_rng(43)
        selected, positions = G.field_units(ros, pending, rng, True, '11')
        after_selection_rng = copy.deepcopy(rng.bit_generator.state)
        self.assertEqual(before, (state.snaps, state.cond.cond, state.cond.snaps))
        self.assertFalse(getattr(state, 'snap_counts', {}))
        pending.commit(selected)
        self.assertEqual(rng.bit_generator.state, after_selection_rng)
        self.assertEqual(sum(state.snaps.values()), 11)
        self.assertEqual(set(state.snaps), set(positions))
        self.assertEqual(state.snap_counts['offense']['total'], 1)

    def test_real_drive_false_start_has_no_snap_or_workload(self):
        rosters_ = rosters.load_league()
        off, deff = rosters_['GB'], rosters_['DEN']
        os, ds = G.TeamState(off), G.TeamState(deff)
        initial = copy.deepcopy((os.cond.cond, ds.cond.cond))
        flag = dict(penalty='False Start', nullifies=True, on_offense=True, yards=5., rule_yards=5., auto_first=False)
        def cd(oc, down, togo, rng, yards, **kw):
            return schemes.call_defense(oc, down, togo, rng, yards_to_endzone=yards, **kw)
        with patch.object(E, 'penalty_check', return_value=flag), patch.object(G, 'end_of_half_plan', return_value=None):
            gen = G.drive_steps(off, deff, 50, 3000, 1, 0, np.random.default_rng(19),
                plays.resolve_play, schemes.call_offense, cd, plays.rate, off_state=os, def_state=ds)
            event, dr = next(gen)
            gen.close()
        self.assertEqual(dr.log[-1]['penalty'], 'False Start')
        self.assertEqual((os.snaps, ds.snaps), ({}, {}))
        self.assertEqual((os.cond.cond, ds.cond.cond), initial)

    def test_player_penalty_stats_save_and_reload(self):
        from test_cap_accounting import fixture, player
        from league import League
        league = fixture(); p = player(league)
        line = dict(penalty_opportunities=45, penalties_committed=2, penalties_accepted=1, penalty_yards=7.5)
        league.record_stats(2026, p.pid, line, game='penalty-audit')
        loaded = League.load(league.save())
        self.assertEqual(loaded.stats[2026][p.pid], line)
        for key, value in line.items(): self.assertEqual(loaded.game_stats['penalty-audit'][p.pid][key], value)

    def test_seeded_game_replays_the_same_attribution(self):
        rosters_ = rosters.load_league()
        def cd(oc, down, togo, rng, yards, **kw):
            return schemes.call_defense(oc, down, togo, rng, yards_to_endzone=yards, **kw)
        def run():
            home, away = copy.deepcopy(rosters_['GB']), copy.deepcopy(rosters_['DEN'])
            for roster in (home, away):
                for men in roster['depth'].values():
                    for p in men: p['traits'] = dict(discipline=15)
            book = G.StatBook()
            result = G.play_game(home, away, np.random.default_rng(471), plays.resolve_play,
                schemes.call_offense, cd, plays.rate, book=book, home_state=G.TeamState(home), away_state=G.TeamState(away))
            flags = [p for _, dr in result['drives'] for p in dr.log if p.get('type') == 'penalty']
            return result['home'], result['away'], flags, book.p
        first, second = run(), run()
        self.assertEqual(first, second)
        self.assertTrue(any(p.get('offender_pid') for p in first[2]))
        self.assertTrue(all('accepted' in p and 'enforced_yards' in p for p in first[2]))


if __name__ == '__main__': unittest.main()

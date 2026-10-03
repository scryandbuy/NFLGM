"""All-team, production-prepared discipline audit with paired game seeds.

Fresh league per round, each team plays once per mode. No season-long
development claim. Both modes use identical current roster/practice/coach
preparation, isolating the penalty/game-loop change from other features.
"""
import argparse
from collections import Counter
from contextlib import ExitStack
import copy
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
from unittest.mock import patch
import numpy as np
import league as LG
import season as SN
import game as G
import events as E
import kick_returns as KR
import penalty_players as PP
from calibrate import Collector, TARGETS
from audit_penalty_discipline import committed_module


def logs(result):
    return [p for _, dr in result['drives'] for p in dr.log]


def flags(result):
    for p in logs(result):
        if p.get('type') == 'penalty': yield p
        if p.get('declined_penalty'): yield p['declined_penalty']
        yield from p.get('other_declined_penalties') or []


def validate(result, book, league, violations, label):
    counts = {}
    for p in flags(result):
        pid = p.get('offender_pid')
        if pid:
            row = counts.setdefault(pid, [0, 0, 0.])
            row[0] += 1; row[1] += int(p.get('accepted', False)); row[2] += p.get('enforced_yards', 0.)
            if league.player(pid) is None: violations.append([label, 'unknown_offender', pid])
        if p.get('accepted') == p.get('declined'):
            violations.append([label, 'invalid_status', p])
    for pid, row in book.p.items():
        actual = [row.get('penalties_committed', 0), row.get('penalties_accepted', 0), row.get('penalty_yards', 0.)]
        expected = counts.get(pid, [0, 0, 0.])
        if actual != expected: violations.append([label, 'log_book_mismatch', pid, actual, expected])


def replay_check(blob):
    """Actual SeasonRunner batch/live plus a midgame save/replay continuation."""
    def runner(): return SN.SeasonRunner(LG.League.load(copy.deepcopy(blob)), np.random.default_rng(19741))
    batch = runner(); batch_result = batch.play('GB', 'MIN', 1)
    live = runner(); live.open_live('GB', 'MIN', 1)
    for _ in range(12): live.live_step('play')
    saved_league = json.loads(json.dumps(live.L.save()))
    saved_state = copy.deepcopy(live.save_state())
    start, actions = copy.deepcopy(live.live['start']), copy.deepcopy(live.live['actions'])
    rng = copy.deepcopy(live.rng.bit_generator.state)
    saved_state, start, actions, rng = json.loads(json.dumps([saved_state, start, actions, rng]))
    def finish(r):
        for _ in range(20):
            if r.live['done']: break
            r.live_step('resume' if r.live['halftime_open'] else 'finish')
        if not r.live['done']: raise AssertionError('Live game did not finish')
    # Finish one session before opening the restored one. The game engine's
    # environment/kickoff globals intentionally hold one current live game.
    finish(live)
    restored = SN.SeasonRunner(LG.League.load(saved_league), np.random.default_rng(1))
    restored.load_state(saved_state)
    restored.open_live('GB', 'MIN', 1, replay_start=start)
    restored.replay_live(actions, rng)
    finish(restored)
    def signature(result, book):
        return dict(score=[result['home'], result['away']], logs=logs(result), stats=book.p)
    batch_sig = signature(batch_result, batch._book)
    live_sig = signature(live.live['res'], live._book)
    restored_sig = signature(restored.live['res'], restored._book)
    return dict(batch_live_equal=batch_sig == live_sig, live_reload_equal=live_sig == restored_sig,
                scores=[batch_sig['score'], live_sig['score'], restored_sig['score']],
                reloaded_penalty_stats={pid:{k:v for k,v in row.items() if k.startswith('penalt')}
                                       for pid,row in restored._book.p.items() if row.get('penalties_committed')})


def migration_check(blob):
    if isinstance(blob, str): blob = json.loads(blob)
    legacy = copy.deepcopy(blob)
    for p in legacy['players'].values():
        if p.get('traits'): p['traits'].pop('discipline', None)
    unchanged = copy.deepcopy(legacy)
    loaded = LG.League.load(legacy)
    reloaded = LG.League.load(loaded.save())
    return dict(players=len(loaded.players), input_unchanged=legacy == unchanged,
        generated_migrated_match=all(p.traits['discipline'] == blob['players'][pid]['traits']['discipline']
                                    for pid,p in loaded.players.items()),
        reload_stable=all(p.traits == reloaded.player(pid).traits for pid,p in loaded.players.items()),
        prior_traits_preserved=all(all(p.traits[k] == value for k,value in (unchanged['players'][pid].get('traits') or {}).items())
                                   for pid,p in loaded.players.items()),
        progression_preserved=all(all(getattr(p,k) == unchanged['players'][pid][k] for k in ('xp','dev','potential'))
                                  for pid,p in loaded.players.items()))


def run(rounds=4, baseline='c14c945'):
    old_game, old_events, old_returns = [committed_module(baseline, n) for n in ('game', 'events', 'kick_returns')]
    collectors = {k:Collector() for k in ('baseline', 'realistic')}
    games = {k:[] for k in collectors}; seconds = Counter(); violations = []; role_counts = Counter()
    disciplines = []; first_blob = None
    current_penalty, current_field = E.penalty_check, G.field_units
    def checked_field(*args, **kw):
        selected, positions = current_field(*args, **kw)
        state = args[1]; offense = args[3]
        rows = PP.unit(selected, offense)
        pids = [p['pid'] for _,p in rows]
        if len(pids) != 11 or len(set(pids)) != 11: violations.append(['selection', 'eleven', pids])
        if state is not None and set(pids) & state.out: violations.append(['selection', 'inactive', list(set(pids) & state.out)])
        return selected, positions
    def checked_penalty(*args, **kw):
        flag = current_penalty(*args, **kw)
        if not flag or not flag.get('offender_pid'): return flag
        pid = flag['offender_pid']; name = flag['penalty']; outcome = kw.get('outcome') or {}
        rows = kw.get('offense_players' if flag['on_offense'] else 'defense_players', ())
        if pid not in {p['pid'] for _,p in rows}: violations.append(['draw', 'off_field', flag])
        if name == 'Roughing the Passer' and 'pr_reps' in outcome and pid not in {r[0] for r in outcome['pr_reps']}:
            violations.append(['draw', 'not_rusher', flag])
        if name == 'Offensive Holding':
            key = 'rb_reps' if 'rb_reps' in outcome else 'pb_reps'
            if key in outcome and pid not in {r[0] for r in outcome[key]}: violations.append(['draw', 'not_blocker', flag])
        role_counts[name + ':' + str(flag.get('offender_role'))] += 1
        return flag
    for round_ in range(rounds):
        seed = 29100 + round_
        league = LG.build_league(rng=np.random.default_rng(seed))
        blob = league.save()
        if first_blob is None: first_blob = copy.deepcopy(blob)
        disciplines.extend(p.traits['discipline'] for p in league.players.values() if p.traits)
        teams = sorted(league.teams); np.random.default_rng(seed).shuffle(teams)
        for mode in collectors:
            with ExitStack() as stack:
                if mode == 'baseline':
                    stack.enter_context(patch.object(SN, 'G', old_game))
                    for name in ('penalty_check', 'contextual_penalty', 'special_teams_penalty_check'):
                        stack.enter_context(patch.object(E, name, getattr(old_events, name)))
                    stack.enter_context(patch.object(KR, 'enforce_return_flag', old_returns.enforce_return_flag))
                else:
                    stack.enter_context(patch.object(G, 'field_units', checked_field))
                    stack.enter_context(patch.object(E, 'penalty_check', checked_penalty))
                runner = SN.SeasonRunner(LG.League.load(copy.deepcopy(blob)), np.random.default_rng(seed+900))
                for index, (home, away) in enumerate(zip(teams[::2], teams[1::2])):
                    runner.rng = np.random.default_rng(seed*100+index)
                    started = time.perf_counter()
                    result = runner.play(home, away, 1)
                    seconds[mode] += time.perf_counter()-started
                    collectors[mode].add(result)
                    one = Collector(); one.add(result)
                    row = dict(round=round_, home=home, away=away, seed=seed*100+index,
                               metrics=one.got(), accepted_flags=sum(p.get('type')=='penalty' for p in logs(result)))
                    games[mode].append(row)
                    if mode == 'realistic': validate(result, runner._book, runner.L, violations, [round_, home, away])
            print(f'round {round_+1}/{rounds} {mode}: {len(games[mode])} games, {seconds[mode]:.2f}s, violations={len(violations)}', flush=True)
    reports = {mode:col.got() for mode,col in collectors.items()}
    deltas = {}
    for key in reports['baseline']:
        differences = [b['metrics'][key]-a['metrics'][key] for a,b in zip(games['baseline'],games['realistic'])]
        if not all(np.isfinite(d) for d in differences): continue
        deltas[key] = dict(mean=statistics.mean(differences), paired_95_margin=1.96*statistics.stdev(differences)/math.sqrt(len(differences)))
    differences = [b['accepted_flags']-a['accepted_flags'] for a,b in zip(games['baseline'],games['realistic'])]
    deltas['accepted_flags'] = dict(mean=statistics.mean(differences),
        paired_95_margin=1.96*statistics.stdev(differences)/math.sqrt(len(differences)))
    return dict(baseline=baseline, combined_source=subprocess.check_output(['git','rev-parse','HEAD']).decode().strip(), rounds=rounds, games=games,
        scope='Fresh production-prepared week-1 games; all 32 teams once per round; not season-long calibration. Runtime includes game preparation and recording, plus attribution checks in realistic mode.',
        runtime_seconds=dict(seconds), register=reports, paired_deltas=deltas,
        register_misses={mode:[dict(metric=n, value=reports[mode][n], target=t, tolerance=tol)
                              for n,t,tol,_ in TARGETS if abs(reports[mode][n]-t)>tol] for mode in reports},
        discipline=dict(n=len(disciplines), mean=statistics.mean(disciplines), sd=statistics.stdev(disciplines), min=min(disciplines), max=max(disciplines)),
        offender_roles=dict(role_counts), violations=violations, replay=replay_check(first_blob), migration=migration_check(first_blob))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--rounds',type=int,default=4); parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if args.rounds < 1: parser.error('--rounds must be positive')
    Path(args.output).write_text(json.dumps(run(args.rounds),indent=2))

"""Paired-seed penalty/scoring smoke audit; not a season balance calibration.

Run: python audit_penalty_discipline.py --games 32 --output results.json
Baseline uses committed game/events/kick_returns at --baseline; roster, play
resolution and coaching callers stay fixed for a targeted comparison.
"""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import time
import types
from unittest.mock import patch
import numpy as np
import game as G
import plays as P
import schemes as S
import rosters as R
import events as E
import kick_returns as KR


def committed_module(ref, name):
    module = types.ModuleType('baseline_' + name)
    source = subprocess.check_output(['git', 'show', ref + ':' + name + '.py']).decode()
    exec(compile(source, ref + ':' + name + '.py', 'exec'), module.__dict__)
    return module


def run(games=32, baseline='c14c945'):
    old = committed_module(baseline, 'game')
    old_events = committed_module(baseline, 'events')
    old_returns = committed_module(baseline, 'kick_returns')
    rosters = R.load_league()
    def call_def(oc, down, togo, rng, yards, **kw):
        return S.call_defense(oc, down, togo, rng, yards_to_endzone=yards, **kw)
    results = dict(baseline=baseline, games_per_case=games, seed_start=8200, cases=[])
    for mode, engine, discipline in [('baseline', old, 50), ('neutral', G, 50), ('low', G, 0), ('high', G, 100)]:
        started = time.perf_counter()
        rows = []
        for seed in range(games):
            home = copy.deepcopy(rosters[('GB', 'BUF', 'ARI', 'NYG')[seed % 4]])
            away = copy.deepcopy(rosters[('CIN', 'KC', 'DEN', 'SEA')[seed % 4]])
            for roster in (home, away):
                for men in roster['depth'].values():
                    for player in men: player['traits'] = dict(discipline=discipline, work_ethic=50)
            book = engine.StatBook()
            hs, ds = engine.TeamState(home), engine.TeamState(away)
            # Use the original event/enforcement functions for the original
            # game loop, without changing this process's play resolver.
            with patch.object(E, 'penalty_check', old_events.penalty_check if mode == 'baseline' else E.penalty_check), \
                 patch.object(E, 'contextual_penalty', old_events.contextual_penalty if mode == 'baseline' else E.contextual_penalty), \
                 patch.object(E, 'special_teams_penalty_check', old_events.special_teams_penalty_check if mode == 'baseline' else E.special_teams_penalty_check), \
                 patch.object(KR, 'enforce_return_flag', old_returns.enforce_return_flag if mode == 'baseline' else KR.enforce_return_flag):
                result = engine.play_game(home, away, np.random.default_rng(8200 + seed), P.resolve_play,
                                          S.call_offense, call_def, P.rate, book=book, home_state=hs, away_state=ds)
            logs = [p for _, drive in result['drives'] for p in drive.log]
            rows.append(dict(seed=8200+seed, points=result['home']+result['away'],
                accepted_flags=sum(p.get('type') == 'penalty' for p in logs),
                player_flags=sum(p.get('penalties_committed', 0) for p in book.p.values()),
                declined_flags=sum(bool(p.get('declined_penalty')) for p in logs),
                enforced_yards=sum(float(p.get('yards', 0)) for p in logs if p.get('type') == 'penalty')))
        means = {key: round(sum(row[key] for row in rows)/len(rows), 3) for key in rows[0] if key != 'seed'}
        case = dict(mode=mode, means=means, seconds=round(time.perf_counter()-started, 3), games=rows)
        results['cases'].append(case)
        print(mode, means, case['seconds'], flush=True)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--games', type=int, default=32)
    parser.add_argument('--baseline', default='c14c945')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.games < 1: parser.error('--games must be positive')
    Path(args.output).write_text(json.dumps(run(args.games, args.baseline), indent=2))

"""Targeted game-engine injury measurements; no franchise transactions or years."""
import argparse
from collections import Counter
import json
from pathlib import Path
import time

import numpy as np
import game as G
import health as H
import league as LG
import plays as P
import season as SN


def run(rounds=4, seed=941, multiplier=1.0):
    rng = np.random.default_rng(seed)
    league = LG.build_league(rng=np.random.default_rng(seed))
    runner = SN.SeasonRunner(league, rng)
    teams = sorted(league.teams)
    original_scale = H._RULED_OUT_SHARE
    H._RULED_OUT_SHARE *= multiplier
    games = []; durations = Counter(); kinds = Counter(); positions = Counter()
    started = time.monotonic()
    try:
        for week in range(1, rounds + 1):
            order = np.random.default_rng(seed + week).permutation(teams).tolist()
            for h, a in zip(order[::2], order[1::2]):
                result = G.play_game(runner.states[h].roster, runner.states[a].roster,
                                     rng, P.resolve_play, runner.co, runner.cd, P.rate,
                                     home_state=runner.states[h], away_state=runner.states[a], week=week)
                injuries = result.get('injuries', [])
                ids = [x['player'] for x in injuries]
                assert len(ids) == len(set(ids)), 'duplicate injury to a player in one game'
                durations.update(x['weeks_out'] for x in injuries)
                kinds.update(x['kind'] for x in injuries)
                positions.update(x['position'] for x in injuries)
                games.append(dict(home=h, away=a, week=week, injuries=len(injuries)))
            print(f'Round {week}: {len(games)} games, {sum(durations.values()) / (2 * len(games)):.3f} injuries/team/game', flush=True)
    finally:
        H._RULED_OUT_SHARE = original_scale
    n = sum(durations.values())
    return dict(seed=seed, rounds=rounds, games=len(games), team_games=2 * len(games),
                rate_scale=original_scale * multiplier, injuries=n,
                injuries_per_team_game=n / (2 * len(games)),
                mean_weeks=sum(w * count for w, count in durations.items()) / max(n, 1),
                ir_eligible_share=sum(count for w, count in durations.items() if w >= 4) / max(n, 1),
                durations=dict(durations), kinds=dict(kinds), positions=dict(positions),
                rows=games, seconds=time.monotonic() - started,
                scope='Controlled game-engine sample with condition/jadedness carried between games; availability reset per game, no franchise seasons advanced.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--rounds', type=int, default=4)
    parser.add_argument('--seed', type=int, default=941)
    parser.add_argument('--multiplier', type=float, default=1.0)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.rounds, args.seed, args.multiplier)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'kinds', 'positions', 'durations')}, indent=2))

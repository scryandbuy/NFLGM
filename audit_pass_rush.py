"""Small production-path comparison; identical seeds/config on each checkout.

Uses every team, catalog coaches and SeasonRunner/TeamState. Fresh week-one
games isolate the mechanics; this is not a season-long fatigue calibration.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
import numpy as np
import league as LG
import season as SN


def run(seeds):
    games, players = [], []
    for seed in seeds:
        league = LG.build_league(rng=np.random.default_rng(seed))
        runner = SN.SeasonRunner(league, np.random.default_rng(seed + 1000))
        teams = sorted(league.teams)
        np.random.default_rng(seed).shuffle(teams)
        for home, away in zip(teams[::2], teams[1::2]):
            result = runner.play(home, away, 1)
            book = runner._book.p
            logged_reps, logged_wins = Counter(), Counter()
            for side, drive in result['drives']:
                for play in drive.log:
                    if play.get('nullified'): continue
                    for pid, won in play.get('pr_reps') or []:
                        logged_reps[pid] += 1
                        logged_wins[pid] += bool(won)
            mismatches = sum((line.get('pr_reps', 0), line.get('pr_wins', 0)) !=
                (logged_reps[pid], logged_wins[pid]) for pid, line in book.items())
            games.append(dict(seed=seed, home=home, away=away,
                              hs=result['home'], away_score=result['away'],
                              rush_log_book_mismatches=mismatches,
                              injuries=len(result.get('injuries') or [])))
            for team, opponent_side in ((home, 'away'), (away, 'home')):
                state = runner.states[team]
                defensive_counts = state.last_snap_counts.get('defense', {})
                defensive_snaps = defensive_counts.get('total', 0)
                for player in league.teams[team].active():
                    if player.pos not in ('LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM'): continue
                    line = book.get(player.pid, {})
                    snaps = defensive_counts.get('players', {}).get(player.pid, 0)
                    depth = state.roster.get('depth', {}).get(player.pos, [])
                    depth_rank = next((i + 1 for i, p in enumerate(depth) if p.get('pid') == player.pid), None)
                    players.append(dict(seed=seed, team=team, front=league.teams[team].gm.def_front,
                        pid=player.pid, name=player.name, pos=player.pos, ovr=round(player.ovr, 2),
                        depth_rank=depth_rank,
                        quality='elite' if player.ovr >= 88 else 'average' if player.ovr >= 75 else 'reserve',
                        snaps=snaps, defensive_snaps=defensive_snaps,
                        snap_share=round(snaps / max(1, defensive_snaps), 4),
                        condition=round(state.cond.get(player.pid), 2),
                        reps=line.get('pr_reps', 0), wins=line.get('pr_wins', 0),
                        pressures=line.get('pressures', 0), sacks=line.get('sacks', 0)))
            print(f'seed {seed}: {home} {result["home"]}-{result["away"]} {away}', flush=True)
    groups = {}
    for row in players:
        role = 'edge' if row['pos'] in ('LEDG', 'REDG') else 'interior' if row['pos'] == 'DT' else 'offball'
        for key in (role, role + '/' + row['front'], role + '/' + row['quality']):
            group = groups.setdefault(key, dict(player_games=0, reps=0, wins=0, pressures=0, sacks=0, snaps=0, condition_sum=0))
            group['player_games'] += 1
            for stat in ('reps', 'wins', 'pressures', 'sacks', 'snaps'): group[stat] += row[stat]
            group['condition_sum'] += row['condition']
    return dict(seeds=seeds, games=games, players=players, groups=groups,
        points_per_team_game=sum(g['hs']+g['away_score'] for g in games)/max(1, 2*len(games)),
        injuries=sum(g['injuries'] for g in games),
        limitations='Fresh week-one games; no full-season health/development inference. Quality bands use overall, not depth rank; snaps are defensive-unit counts.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', nargs='+', type=int, default=[93031, 93032])
    parser.add_argument('--out', required=True)
    parser.add_argument('--baseline-ref', help='Load game.py/advanced_stats.py from this Git ref for accounting comparison only')
    args = parser.parse_args()
    if args.baseline_ref:
        import subprocess, game, advanced_stats
        for module in (advanced_stats, game):
            source = subprocess.check_output(['git', 'show', args.baseline_ref + ':' + module.__name__ + '.py'])
            exec(compile(source, module.__file__, 'exec'), module.__dict__)
    Path(args.out).write_text(json.dumps(run(args.seeds), indent=2), encoding='utf-8')

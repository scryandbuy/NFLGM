"""Compare a three-season defensive-return run with the prior run and NFL scores."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


def margins(games):
    return np.array([float(g['home']) - float(g['away']) for g in games])


def summarize_scores(values):
    absolute = np.abs(values)
    return dict(games=len(values), mean_margin=float(absolute.mean()),
                margin_10plus_pct=float((absolute >= 10).mean() * 100),
                margin_17plus_pct=float((absolute >= 17).mean() * 100),
                margin_24plus_pct=float((absolute >= 24).mean() * 100),
                signed_margin_sd=float(values.std()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('current', type=Path)
    parser.add_argument('previous', type=Path)
    parser.add_argument('nfl_games', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    current = json.loads(args.current.read_text(encoding='utf-8'))
    previous = json.loads(args.previous.read_text(encoding='utf-8'))
    if len(current['games']) != 816:
        raise ValueError('Three complete 272-game regular seasons are required')
    sim = margins(current['games'])
    strengths = np.array([g['strength']['home']['overall'] - g['strength']['away']['overall']
                          for g in current['games']])
    design = np.column_stack([np.ones(len(strengths)), strengths])
    intercept, slope = np.linalg.lstsq(design, sim, rcond=None)[0]
    expectation = design @ [intercept, slope]
    with args.nfl_games.open(encoding='utf-8', newline='') as source:
        real_games = [r for r in csv.DictReader(source)
                      if r['game_type'] == 'REG' and 2021 <= int(r['season']) <= 2025
                      and r['home_score'] and r['away_score'] and r['spread_line']]
    real = np.array([float(r['home_score']) - float(r['away_score']) for r in real_games])
    spread = np.array([float(r['spread_line']) for r in real_games])
    defensive_tds = sum(bucket.get('Defensive touchdown', 0)
                        for bucket in current['drives'].values())
    turnovers = sum(bucket.get('Turnover', 0) + bucket.get('Defensive touchdown', 0)
                    for bucket in current['drives'].values())
    all_drives = sum(sum(bucket.values()) for bucket in current['drives'].values())
    result = {
        'source_commits': {'current': 'defensive returns plus later integrated work',
                           'previous': previous.get('commit')},
        'current': summarize_scores(sim),
        'current_by_season': {str(2026+i): summarize_scores(sim[272*i:272*(i+1)]) for i in range(3)},
        'previous': {'games': 816, **previous['combined']['got']},
        'nfl_2021_2025': summarize_scores(real),
        'nfl_abs_spread_mean': float(np.abs(spread).mean()),
        'nfl_spread_sd': float(spread.std()),
        'nfl_margin_minus_spread_sd': float((real-spread).std()),
        'sim_mean_abs_strength_gap': float(np.abs(strengths).mean()),
        'sim_strength_gap_sd': float(strengths.std()),
        'sim_strength_by_season': {
            str(2026+i): {
                'mean_abs_gap': float(np.abs(strengths[272*i:272*(i+1)]).mean()),
                'gap_sd': float(strengths[272*i:272*(i+1)].std()),
            } for i in range(3)
        },
        'sim_margin_per_strength_point': float(slope),
        'sim_predicted_margin_abs_mean': float(np.abs(expectation).mean()),
        'sim_predicted_margin_sd': float(expectation.std()),
        'sim_unexplained_margin_sd': float((sim-expectation).std()),
        'sim_strength_margin_correlation': float(np.corrcoef(strengths, sim)[0, 1]),
        # The historical drive result also covers blocked-punt scores. The
        # play-level return kind was not exported by this calendar harness.
        'defensive_scores_including_blocked_punts': defensive_tds,
        'defensive_scores_per_game': defensive_tds / len(sim),
        'defensive_scores_by_kind': current.get('defensive_scores'),
        'turnover_or_defensive_score_drives_per_game': turnovers / len(sim),
        'turnover_or_defensive_score_drive_pct': 100 * turnovers / all_drives,
    }
    args.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

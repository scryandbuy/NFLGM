"""Paired rating-aging checks; this is not a full franchise/gameplay register.

Run with --save PATH --output PATH to add read-only saved-player evidence.
"""
import argparse
import collections
import json
import numpy as np
import regression as R


def prior_loss(pos, age, longevity, roll, rating):
    years = max(0, int(age) - R.plateau_end(pos))
    if not years:
        return 0.
    physical = rating * max(0., 1 - R.curve_factor(pos, age)) * R.DAMPING / max(.35, longevity) * roll * R.PHYS_DAMP
    bound = min(1.8, .35 + .22 * (years - 1)) * np.clip(1 / max(.35, longevity), .8, 1.2) * np.clip(roll, .65, 1.35)
    return min(physical, bound, 2.)


def trajectories(n=2000):
    result = {}
    for pos in ('WR', 'CB'):
        samples = {mode: collections.defaultdict(list) for mode in ('prior_curve', 'revised_curve')}
        zero = collections.Counter()
        for seed in range(n):
            rng = np.random.default_rng(seed)
            longevity = float(np.clip(rng.normal(1., .22), .45, 1.7))
            speed = dict(prior_curve=90., revised_curve=90.)
            for age in range(27, 37):
                roll = float(np.clip(rng.normal(1., .35), .15, 2.2))
                for mode in speed:
                    before = speed[mode]
                    if mode == 'prior_curve':
                        loss = prior_loss(pos, age, longevity, roll, before)
                    else:
                        physical = before * max(0., 1 - R.curve_factor(pos, age)) * R.DAMPING / max(.35, longevity) * roll * R.PHYS_DAMP
                        loss = R.athletic_loss(pos, age, longevity, roll, 'speed_rating', physical)
                    speed[mode] -= loss
                    zero[mode] += loss < .05
                    if age in (28, 31, 34, 36):
                        samples[mode][age].append(90 - speed[mode])
        result[pos] = {mode: dict(
            cumulative_loss={age: dict(mean=round(float(np.mean(values)), 2),
                                      p10_p50_p90=np.round(np.percentile(values, [10, 50, 90]), 2).tolist())
                             for age, values in ages.items()},
            near_flat_year_percent=round(zero[mode] / (n * 10) * 100, 1))
            for mode, ages in samples.items()}
    return dict(careers_per_position=n, starting_speed=90, start_age=26,
                note='Same age, longevity and annual draws isolate the curve change. No XP, retirement, injury or roster selection.',
                positions=result)


def saved_evidence(path):
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    players = data['players']
    if isinstance(players, dict): players = list(players.values())
    events = [x for x in data.get('transactions', []) if x.get('kind') == 'regress']
    grouped = collections.defaultdict(list)
    for event in events:
        grouped[event.get('pid'), event.get('year')].append(event)
    duplicates = [rows for rows in grouped.values() if len(rows) > 1]
    example = []
    for p in players:
        if p['pos'] not in ('WR', 'CB') or p.get('retired') or not 30 <= p['age'] < 33:
            continue
        history = [dict(year=x['year'], speed=x.get('attrs', {}).get('speed_rating'))
                   for x in events if x.get('pid') == p['pid']]
        example.append(dict(name=p['name'], pos=p['pos'], age=p['age'], speed=p['ratings']['speed_rating'], history=history))
    return dict(duplicate_player_years=len(duplicates),
                duplicate_groups_with_complete_speed_pairs=sum(all('speed_rating' in x.get('attrs', {}) for x in rows) for rows in duplicates),
                players=example, repair='No rating restoration: missing historical attribute pairs cannot establish the extra loss.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--save')
    parser.add_argument('--output')
    args = parser.parse_args()
    report = trajectories()
    if args.save: report['save'] = saved_evidence(args.save)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'save'}, indent=2))
    if 'save' in report: print(json.dumps({k: v for k, v in report['save'].items() if k != 'players'}))

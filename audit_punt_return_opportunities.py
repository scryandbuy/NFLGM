"""Read-only punt opportunity audit using the actual players in a copied save.

Origins are controlled uniform draws from 48..95 yards to goal, not a sampled
NFL field-position distribution. Return flags and injuries are omitted here;
game-loop credit/penalties are covered separately by test_kick_return_outcomes.
No changes to the save or game settings, and no target touchdown quota.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from league import League
from season import SeasonRunner
import game as G
import plays as P
import kick_returns as KR


def run(path, seeds, punts):
    league = League.load(Path(path).read_text(encoding='utf-8'))
    history = {year: {stat: sum(float(row.get(stat, 0) or 0) for row in rows.values())
                      for stat in ('pr', 'pr_yds', 'pr_td')}
               for year, rows in league.stats.items()}
    runner = SeasonRunner(league, np.random.default_rng(1)); runner.week = int(league.week or 1)
    units = {abbr: runner._units(abbr) for abbr in sorted(league.teams)}
    teams = list(units)
    samples = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        counts = Counter(); gains = []; scores = []; stops = []
        original = P.resolve_yards_after
        def observe(*args, **kwargs):
            out = original(*args, **kwargs)
            counts['breakaway_contests'] += 1
            counts['broken_' + str(out['broken_tackles'])] += 1
            counts['contest_touchdowns'] += int(out['touchdown'])
            return out
        with patch.object(P, 'resolve_yards_after', side_effect=observe):
            for index in range(punts):
                kicking = teams[index % len(teams)]
                receiving = teams[(index % len(teams) + 1 + index // len(teams) % (len(teams)-1)) % len(teams)]
                offense, defense = units[kicking], units[receiving]
                returner = G.returner_for(defense, None, P.rate, kind='pr')
                coverage = KR.unit(offense, None, P.rate)
                blockers = KR.unit(defense, None, P.rate, True, returner.get('pid'))
                out = G.punt(float(rng.uniform(48, 95)), offense['p'], returner, rng, P.rate,
                             snapper=G.snapper_for(offense), return_coverage=coverage, return_blockers=blockers)
                counts['punts'] += 1
                counts[out.get('how', 'blocked')] += 1
                if out.get('how') != 'return': continue
                gains.append(out['ret'])
                if out.get('breakaway_opportunity'):
                    counts['lanes'] += 1
                    contacts = out.get('punt_pursuit', [])
                    stopped = next((c for c in contacts if not c['missed']), None)
                    if stopped:
                        counts[stopped['role'] + '_stops'] += 1
                        if len(stops) < 12:
                            stops.append(dict(kicking=kicking, receiving=receiving,
                                              name=league.player(returner['pid']).name, **out))
                    counts['all_contacts_missed'] += int(bool(contacts) and stopped is None)
                for key, condition in [('touchdowns', out.get('touchdown')), ('fumbles', out.get('fumble')),
                                       ('20_plus', out['ret'] >= 20), ('40_plus', out['ret'] >= 40)]:
                    counts[key] += int(bool(condition))
                if out.get('touchdown'):
                    book = G.StatBook(); KR.book_return(book, 'pr', out)
                    assert book.p[returner['pid']]['pr_td'] == 1
                    scores.append(dict(kicking=kicking, receiving=receiving,
                                       name=league.player(returner['pid']).name, **out))
        samples.append(dict(seed=seed, counts=dict(counts), average=float(np.mean(gains)),
                            p90=float(np.percentile(gains, 90)), longest=max(gains), touchdowns=scores, stops=stops))
    return dict(history=history, samples=samples,
                limitations='Controlled punt origins 48..95; actual saved personnel; before return penalties; no full season simulation.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('save'); parser.add_argument('--seeds', type=int, nargs='+', default=[60107, 60207])
    parser.add_argument('--punts', type=int, default=20000)
    parser.add_argument('--out', default='outputs/punt-return-opportunities.json')
    args = parser.parse_args()
    result = run(args.save, args.seeds, args.punts)
    target = Path(args.out); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps([dict(seed=s['seed'], counts=s['counts'], average=s['average'], p90=s['p90'])
                      for s in result['samples']], indent=2))

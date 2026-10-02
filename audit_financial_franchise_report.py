"""Summarize the saved observations; never advances or changes a franchise."""
import argparse
import collections
import json
import statistics
from pathlib import Path


def report(folder):
    folder = Path(folder)
    snaps = json.loads((folder / 'snapshots.json').read_text())
    events = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines()]
    kickoffs = [json.loads(line) for line in (folder / 'kickoffs.jsonl').read_text().splitlines()]
    selected = []
    failures = []
    if (folder / 'failure.json').exists():
        failures.append(json.loads((folder / 'failure.json').read_text()))
    for s in snaps:
        if s['invalid_owners'] or s['multiple_owners']:
            failures.append(dict(year=s['year'], label=s['label'], issue='ownership'))
        opening = s['label'] in ('initial_cutdown', 'end_offseason')
        sampled_week = s['label'] in ('week_1', 'week_9', 'week_18')
        if opening or sampled_week:
            for t in s['teams']:
                # Weekly snapshots are taken after the games and transactions.
                # A newly acquired player may temporarily put a team over 53;
                # the next advance clears it before any kickoff.
                checks = [('illegal_cap', t['cap_space'] < -.01)]
                if opening:
                    checks += [('over_53', t['active'] > 53),
                               ('missing_roles', bool(t['uncovered'])),
                               ('duplicate_or_missing_package_players', bool(t['package_bad']))]
                for issue, bad in checks:
                    if bad:
                        failures.append(dict(year=s['year'], label=s['label'], team=t['team'], issue=issue))
        if opening or sampled_week or s['label'] == 'season_closed':
            ts = s['teams']
            future = [[t['financial_plan']['years'][i] for t in ts] for i in range(4)]
            selected.append(dict(year=s['year'], label=s['label'], regular_games=s['regular_games'],
                playoff_games=s['playoff_games'], active_range=[min(t['active'] for t in ts), max(t['active'] for t in ts)],
                under_53=[t['team'] for t in ts if t['active'] < 53],
                depth_shortfalls=[dict(team=t['team'], positions=t['position_short'], groups=t['group_short'])
                                  for t in ts if t['position_short'] or t['group_short']],
                cap_room=dict(min=min(t['cap_space'] for t in ts), median=statistics.median(t['cap_space'] for t in ts),
                              max=max(t['cap_space'] for t in ts), below_1m=sum(t['cap_space'] < 1 for t in ts)),
                mean_ovr=statistics.mean(t['mean_ovr'] for t in ts), mean_age=statistics.mean(t['mean_age'] for t in ts),
                mean_package_score=statistics.mean(t['score'] for t in ts), free_agents=s['free_agents'],
                dead_total=sum(t['dead'] for t in ts), dead_next_total=sum(t['dead_next'] for t in ts),
                future=[dict(year=ys[0]['year'], raw_negative=sum(y['raw_room'] < -.01 for y in ys),
                             funded_negative=sum(y['funded_room'] < -.01 for y in ys),
                             median_funded=statistics.median(y['funded_room'] for y in ys)) for ys in future]))
    closed = [s for s in snaps if s['label'] == 'season_closed']
    for s in closed:
        if (s['regular_games'], s['playoff_games']) != (272, 13):
            failures.append(dict(year=s['year'], issue='incomplete_season', regular=s['regular_games'], playoffs=s['playoff_games']))
    for k in kickoffs:
        for abbr, count in k['active'].items():
            if count > 53:
                failures.append(dict(year=k['year'], week=k['week'], team=abbr,
                                     issue='over_53_at_kickoff', active=count))
    by_year = collections.defaultdict(collections.Counter)
    for e in events:
        by_year[str(e['year'])][e['kind']] += 1
    result = dict(methodology=json.loads((folder / 'methodology.json').read_text()),
                  completed_seasons=len(closed), completed_offseasons=sum(s['label']=='end_offseason' for s in snaps),
                  regular_games=sum(s['regular_games'] for s in closed), playoff_games=sum(s['playoff_games'] for s in closed),
                  failures=failures, snapshots=selected, event_counts=by_year,
                  kickoff_active_range=[min(n for k in kickoffs for n in k['active'].values()),
                                        max(n for k in kickoffs for n in k['active'].values())],
                  kickoff_note='Recorded before pregame repairs/elevations, not a count of dressed or on-field players',
                  elapsed_seconds=snaps[-1]['elapsed'])
    (folder / 'verification.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('folders', nargs='+')
    for folder in ap.parse_args().folders:
        r = report(folder)
        print(json.dumps(dict(folder=folder, seasons=r['completed_seasons'], offseasons=r['completed_offseasons'],
                              regular_games=r['regular_games'], playoff_games=r['playoff_games'], failures=r['failures'])))

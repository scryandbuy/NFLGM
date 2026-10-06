"""Read-only player-level audit of one saved league's secondary alternatives."""
import argparse
import json
from pathlib import Path
from time import perf_counter

from league import League
import market as MK
import position_change as PC
import roster_needs as RN


def run(path, user='GB'):
    league = League.load(Path(path).read_text(encoding='utf-8'))
    league.user_team = user
    candidates = []
    for abbr, team in sorted(league.teams.items()):
        if abbr == user: continue
        options = PC.aging_corner_options(league, team)
        if not options: continue
        option = options[0]; player = option['player']
        def read(p):
            return dict(pid=p.pid, name=p.name, age=round(p.age, 1), ovr=round(p.ovr, 1),
                        years=p.contract.years if p.contract else 0)
        candidates.append(dict(team=abbr, player=read(player), to=option['to'],
            immediate_gain=round(option['immediate_gain'], 2), settled_gain=round(option['settled_gain'], 2),
            remaining_corners=[read(p) for p in team.active() if p.pos == 'CB' and p is not player],
            displaced=[read(league.player(pid)) for pid in option['displaced']]))
    markets = []
    for candidate in candidates:
        team = league.teams[candidate['team']]
        pool = [league.player(pid) for pid in league.free_agents]
        pool = [p for p in pool if p and MK.available_for_signing(p)]
        secondary = sorted([p for p in pool if p.pos in ('CB', 'FS', 'SS')], key=lambda p: -p.ovr)[:30]
        other = sorted([p for p in pool if p.pos not in ('CB', 'FS', 'SS')], key=lambda p: -p.ovr)[:30]
        start = perf_counter()
        current = RN.candidate_gains(team, secondary + other, RN.assess(team))
        current_seconds = perf_counter() - start
        start = perf_counter()
        plan = RN.planning_assess(league, team)
        proposed = RN.candidate_gains(team, secondary + other, plan)
        planned_seconds = perf_counter() - start
        alternatives = []
        for p in secondary:
            after = RN.planning_assess(league, team, list(team.active()) + [p])
            alternatives.append(dict(name=p.name, pos=p.pos, ovr=round(p.ovr, 1),
                gain=round(proposed[p.pid], 2), current_gain=round(current[p.pid], 2),
                moves=after.get('corner_moves', [])))
        markets.append(dict(team=team.abbr, candidates=len(secondary)+len(other),
            current_seconds=current_seconds, planned_seconds=planned_seconds,
            alternatives=sorted(alternatives, key=lambda x: -x['gain'])))
    return dict(year=league.year, phase=league.phase, candidates=candidates, markets=markets,
                scope='Copied save; potential acquisitions only. No signed deals or season outcomes simulated.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('save'); parser.add_argument('--user', default='GB')
    parser.add_argument('--out', default='outputs/aging-corner-planning-audit.json')
    args = parser.parse_args()
    result = run(args.save, args.user)
    target = Path(args.out); target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(dict(candidates=result['candidates'], timing=[
        {k: m[k] for k in ('team', 'candidates', 'current_seconds', 'planned_seconds')} for m in result['markets']]), indent=2))

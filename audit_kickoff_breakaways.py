"""Controlled kickoff-return contact audit using an existing franchise roster."""
import collections
import json
import sys
from pathlib import Path

import numpy as np

import game as G
import kick_returns as KR
import plays as PL

KR.KICKOFF_CONTAIN_LEVERAGE = float(sys.argv[1]) if len(sys.argv) > 1 else KR.KICKOFF_CONTAIN_LEVERAGE
KR.KICKOFF_BREAKAWAY_BASE = float(sys.argv[2]) if len(sys.argv) > 2 else KR.KICKOFF_BREAKAWAY_BASE
KR.KICKOFF_BREAKAWAY_UPPER = float(sys.argv[3]) if len(sys.argv) > 3 else KR.KICKOFF_BREAKAWAY_UPPER

SAVE = Path(r'C:/Users/HP/Downloads/nflgm-2034-offseason-2.json')
saved = json.loads(SAVE.read_text(encoding='utf-8'))
players = saved['players']
teams = list(saved['teams'])
flat = lambda p: dict(p['ratings'], pid=p['pid'], pos=p['pos'])
rosters = {team: {'depth': {'all': [flat(players[pid]) for pid in row['roster']]}}
           for team, row in saved['teams'].items()}
lines = saved['stats']['2033']
rng = np.random.default_rng(int(sys.argv[4]) if len(sys.argv) > 4 else 2034)
counts = collections.Counter()
by_team = {}
for i, team in enumerate(teams):
    candidates = [pid for pid in saved['teams'][team]['roster'] if lines.get(pid, {}).get('kr', 0)]
    if not candidates:
        continue
    pid = max(candidates, key=lambda p: lines[p]['kr'])
    returner = flat(players[pid])
    own = rosters[team]
    opponent = rosters[teams[(i + 13) % 32]]
    kicker = max((p for p in opponent['depth']['all'] if p['pos'] == 'K'),
                 key=lambda p: p.get('kick_power_rating', 70), default={})
    coverage = KR.unit(opponent, None, PL.rate)
    blockers = KR.unit(own, None, PL.rate, True, pid)
    local = collections.Counter()
    for _ in range(500):
        out = G.kickoff(returner, rng, PL.rate, kicking=coverage, receiving=blockers,
                        kicker=kicker, short_kick_bias=0)
        local['kicks'] += 1
        if out.get('touchback'):
            continue
        local['returns'] += 1
        local['yards'] += out.get('ret', 0)
        local['forty_plus'] += out.get('ret', 0) >= 40
        if out.get('touchdown'):
            local['td'] += 1
        if not out.get('breakaway_opportunity'):
            continue
        local['breakaways'] += 1
        pursuit = out.get('kickoff_pursuit') or []
        reachable = [p for p in pursuit if p.get('reachable')]
        local['reachable_sum'] += len(reachable)
        local['none_reachable'] += not bool(reachable)
        local['missed_all'] += bool(reachable) and all(p.get('missed') for p in reachable)
        local['contain_reachable'] += any(p['leverage'] == 'contain' and p.get('reachable') for p in pursuit)
        local['contain_missed'] += any(p['leverage'] == 'contain' and p.get('missed') for p in pursuit)
        local['kicker_reachable'] += any(p['role'] == 'kicker' and p.get('reachable') for p in pursuit)
        local['td_no_reachable'] += out.get('touchdown') and not reachable
        local['td_missed_all'] += out.get('touchdown') and bool(reachable)
    counts.update(local)
    by_team[team] = dict(local)
print('model', KR.KICKOFF_CONTAIN_LEVERAGE, KR.KICKOFF_BREAKAWAY_BASE,
      KR.KICKOFF_BREAKAWAY_UPPER, 'overall', dict(counts))
print('td_by_team', {team: row.get('td', 0) for team, row in by_team.items()})

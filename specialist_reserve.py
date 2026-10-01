"""Keep a street supply of young long snappers without changing team rosters.

The 50 marked seed rows establish the initial reserve. Old saves receive it once;
annual pool cleanup replaces departures with distinct fictional players. Loading
a current save does not replenish signed players or consume simulation randomness.
"""
import csv
import hashlib
from pathlib import Path

import numpy as np

VERSION = 1
TARGET = 50
SEED_MARKER = 'LS Reserve 2026 v1'
POOL_PATH = Path(__file__).with_name('free_agent_pool.csv')


def eligible(p):
    return (p is not None and p.pos == 'LS' and not p.retired
            and p.team is None and p.contract is None
            and 21 <= p.age <= 25 and 55 <= p.ovr <= 65)


def ensure(league, pool_path=None):
    """Top up to 50 eligible unsigned LS; return only the newly created players."""
    if not getattr(league, 'teams', None):
        return []
    existing = {pid for pid in league.free_agents if eligible(league.player(pid))}
    needed = max(0, TARGET - len(existing))
    if not needed:
        league.ls_reserve_version = VERSION
        return []
    with open(pool_path or POOL_PATH, encoding='utf-8-sig', newline='') as handle:
        rows = [r for r in csv.DictReader(handle)
                if r.get('iteration') == SEED_MARKER and r.get('madden_position') == 'LS']
    if len(rows) != TARGET:
        raise ValueError('Long-snapper reserve requires its 50 source profiles')

    import league as LG
    import newgens as NG
    import personality as PT

    # Local deterministic stream, isolated from games, drafts and contract rolls.
    token = f'ls-reserve-v{VERSION}|{league.year}|{len(league.players)}'
    rng = np.random.default_rng(int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], 'big'))
    history = NG.name_history(league)
    used_names = set(history)
    allocator = None
    added = []
    cursor = 0
    for index in range(needed):
        row = rows[index % len(rows)]
        pid = 'FA' + row['player_id']
        name = row['full_name']
        if pid in league.players or NG.normalize_name(name) in used_names:
            while True:
                pid = f'LSR{league.year}-{cursor:04d}'
                cursor += 1
                if pid not in league.players:
                    break
            if allocator is None:
                allocator = NG.NameAllocator(league, league.year)
            name = allocator.draw(rng, pid)
        ratings = {key: float(value) for key, value in row.items()
                   if key.endswith('_rating') and value not in ('', None)}
        age = float(row['age'])
        p = LG.Player(pid, name, 'LS', age, ratings, dev='normal',
                      potential=min(75.0, float(row['overall']) + float(rng.uniform(3, 8))),
                      longevity=float(rng.uniform(.8, 1.2)),
                      # Street prospects, not current draft UDFAs awaiting cutdown.
                      accrued=0, entry_year=league.year - 1)
        p.height, p.weight = int(row['height_inches']), int(row['weight_lbs'])
        p.number = int(row['jersey_num'])
        p.college = p.home_state
        PT.ensure(p, rng)
        league.players[pid] = p
        league.free_agents.append(pid)
        used_names.add(NG.normalize_name(name))
        added.append(p)
    league.player_name_history = NG.name_history(league)
    league.ls_reserve_version = VERSION
    return added


def migrate(league, saved_version):
    """One-time legacy-save repair; never resurrect or overwrite an existing ID."""
    if int(saved_version or 0) < VERSION:
        ensure(league)
    league.ls_reserve_version = VERSION

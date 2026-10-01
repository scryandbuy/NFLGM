"""Conservative, once-only repair of the former two-writer rush counters.

No global halving: require a whole game's duplicate signature, an impossible
opportunity count, and agreement with its season/career aggregates. Lost
scramble opportunities cannot be recovered from saved display logs.
"""
from collections import defaultdict

VERSION = 1
FIELDS = ('pr_reps', 'pr_wins')


def pair(line):
    return tuple(line.get(k, 0) for k in FIELDS)


def migrate(data):
    if data.get('rush_accounting_version', 0) >= VERSION:
        return data.get('rush_accounting_repair', {})
    games = data.get('game_stats') or {}
    totals = defaultdict(lambda: [0, 0])
    parsed = {}
    candidates = set()
    for key, book in games.items():
        try:
            year, week, home, away = key.split('-')
            week = int(week); int(year)
        except (ValueError, TypeError):
            continue
        bucket = ('post_stats' if week > 18 else 'stats', year)
        parsed[key] = (bucket, week)
        for pid, line in book.items():
            for i, value in enumerate(pair(line)): totals[bucket + (pid,)][i] += value
        rows = [line for line in book.values() if line.get('pr_reps', 0)]
        if (rows and any(line.get('pressures', 0) > 0 for line in rows)
                and any(line.get('pr_reps', 0) > line.get('def_plays', float('inf')) for line in rows)
                and all(isinstance(line.get('pr_reps'), int) and line['pr_reps'] % 2 == 0
                    and line.get('pr_wins', 0) == 2 * line.get('pressures', 0)
                    and 0 <= line.get('pr_wins', 0) <= line['pr_reps'] for line in rows)):
            candidates.add(key)
    eligible = {}
    for (store, year, pid), total in totals.items():
        line = (data.get(store, {}).get(year) or {}).get(pid)
        career = ((data.get('players', {}).get(pid) or {}).get('career') or {}).get(year) if store == 'stats' else None
        if line is not None and pair(line) == tuple(total) and (career is None or pair(career) == tuple(total)):
            eligible[(store, year, pid)] = (line, career)
    changed = 0
    current_week = (data.get('_runner_state') or {}).get('week')
    for key in candidates:
        (store, year), week = parsed[key]
        for pid, line in games[key].items():
            targets = eligible.get((store, year, pid))
            if targets is None or not line.get('pr_reps'): continue
            old = pair(line)
            delta = tuple(v // 2 for v in old)
            for i, field in enumerate(FIELDS):
                line[field] -= delta[i]
                for target in targets:
                    if target is not None: target[field] -= delta[i]
            # The current-week copy is not part of the season aggregation.
            weekly = (data.get('_week_book') or {}).get(pid)
            if (str(data.get('year')) == year and week == current_week and weekly is not None
                    and pair(weekly) == old and weekly.get('pressures', 0) == line.get('pressures', 0)):
                for field in FIELDS: weekly[field] = line[field]
            changed += 1
    report = dict(version=VERSION, candidate_games=len(candidates), repaired_player_games=changed,
                  unclassified_games=len(games)-len(candidates),
                  historical_scramble_reps_reconstructed=False)
    data['rush_accounting_version'] = VERSION
    data['rush_accounting_repair'] = report
    return report

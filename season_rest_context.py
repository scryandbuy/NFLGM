"""Conservative pregame season stakes; no projected wins or hidden player data."""
from collections import defaultdict


def contexts(league, week, playoffs=False):
    result = {a: dict(mode=None, week=int(week)) for a in league.teams}
    if playoffs or not 15 <= week <= 18:
        return result
    low = dict.fromkeys(league.teams, 0.)
    remaining = dict.fromkeys(league.teams, 0)
    for wk, away, home, ap, hp in league.schedule:
        if not 1 <= wk <= 18 or away not in low or home not in low:
            continue
        if ap is None or hp is None:
            remaining[away] += 1
            remaining[home] += 1
        elif ap == hp:
            low[away] += .5
            low[home] += .5
        else:
            low[away if ap > hp else home] += 1
    high = {a: low[a] + remaining[a] for a in low}
    conferences = defaultdict(list)
    for a, team in league.teams.items():
        conferences[getattr(team, 'conf', None) or team.division.split(' ')[0]].append(a)
    for members in conferences.values():
        divisions = defaultdict(list)
        for a in members:
            divisions[league.teams[a].division].append(a)
        if len(divisions) != 4:
            continue
        winners = {}
        for division, clubs in divisions.items():
            for a in clubs:
                if all(low[a] > high[b] for b in clubs if b != a):
                    winners[division] = a
        for a in members:
            rivals = divisions[league.teams[a].division]
            division_out = any(low[b] > high[a] for b in rivals if b != a)
            wildcard_ahead = sum(max(0, sum(low[b] > high[a] for b in clubs if b != a) - 1)
                                 for clubs in divisions.values())
            if division_out and wildcard_ahead >= 3:
                result[a]['mode'] = 'eliminated'
            if a in winners.values():
                # A rival division winner's record lies between its strongest
                # current record and strongest possible final record.
                bands = [(max(low[b] for b in clubs), max(high[b] for b in clubs))
                         for d, clubs in divisions.items() if d != league.teams[a].division]
                if all(lo > high[a] or hi < low[a] for lo, hi in bands):
                    result[a].update(mode='locked', seed=1 + sum(lo > high[a] for lo, hi in bands))
            elif division_out and len(winners) == len(divisions):
                others = [b for b in members if b != a and b not in winners.values()]
                if all(low[b] > high[a] or high[b] < low[a] for b in others):
                    rank = 1 + sum(low[b] > high[a] for b in others)
                    if rank <= 3:
                        result[a].update(mode='locked', seed=len(divisions) + rank)
    return result

"""
THE DEVELOPMENT TRAIT MOVES, once a year.

progression_engine.trait_move_chances had the odds and nothing ever called
it: the year loop ran regression, which ages men and takes points, and the
trait the league was seeded with never changed. No MVP got his guaranteed
tier, no All-Pro rolled, no fading superstar was demoted.

The odds need two things the engine did not define. PRODUCTION is his
percentile within his position on the season score the awards ballot already
computes (passer, skill, defence, line). EXPECTATION is his percentile within
the same position by overall. Beat your rating rank and the up-odds rise;
fall short of it and, for anyone above normal, the down-odds rise. Awards
stack on top: the five majors are a guaranteed tier, the rest add to the odds
and protect against demotion. Runs after the vote and before regression, on
men who actually played.
"""
import numpy as np, collections
import awards as AW
import progression_engine as PE

MIN_SNAPS = 300


def _score(b, p, line):
    if p.pos in AW.OL_POS:
        return b.line_score(p, line)
    if p.pos in AW.PASS_RUSH_POS + AW.COVERAGE_POS:
        return b.def_score(p, line)
    if p.pos == 'QB':
        return b.passer_score(line)
    if p.pos in ('K', 'P', 'LS'):
        return None
    return b.skill_score(line)


def _pct(vals):
    """Percentile within a group, 0-1, ties at the mean rank."""
    order = np.argsort(np.argsort(vals, kind='stable'))
    n = max(len(vals) - 1, 1)
    return order / n


def run(league, votes, rng, season=None, verbose=False):
    year = season or league.year
    b = AW.Ballot(league, year)
    # awards by pid
    won = collections.defaultdict(set)
    for award, who in (votes or {}).items():
        if award == 'coty': continue
        for w in (who if isinstance(who, list) else [who]):
            pid = getattr(w, 'pid', None)
            if pid: won[pid].add(award)
    # the men who played, grouped by position
    groups = collections.defaultdict(list)
    for p, line in b.players():
        if p.retired or float(line.get('snaps', 0) or 0) < MIN_SNAPS: continue
        sc = _score(b, p, line)
        if sc is None: continue
        # A RATE, not a total. Season totals rank a man who missed half the
        # year at the bottom of his position: Crosby at 92 overall came out at
        # the 18th percentile of edges after an injury and was demoted for it.
        # Per snap, with the 300-snap floor above, he is ranked on how he
        # played when he played.
        snaps = float(line.get('snaps', 0) or 0)
        groups[p.pos].append((p, sc / snaps))
    moved = []
    for pos, rows in groups.items():
        if len(rows) < 4: continue
        prod = _pct(np.array([sc for _, sc in rows]))
        # Expectation is his rating rank SHRUNK toward the middle. Taken
        # straight, the best-rated man at a position expects the 100th
        # percentile and can never beat it: Chase produced at the 93rd among
        # receivers and was demoted for falling short. The top-rated man is
        # expected to land around the 85th and the lowest around the 15th.
        exp = 0.5 + 0.7 * (_pct(np.array([p.ovr for p, _ in rows])) - 0.5)
        for (p, _), pr, ex in zip(rows, prod, exp):
            aw = won.get(p.pid, set())
            c_up, c_down = PE.trait_move_chances(p.dev, p.age, float(pr), float(ex), aw)
            r = rng.random()
            change = None
            if r < c_up and p.dev != PE.DEV_ORDER[-1]:
                p.dev = PE.DEV_ORDER[PE.DEV_ORDER.index(p.dev) + 1]; change = 'up'
            elif r > 1 - c_down and p.dev != PE.DEV_ORDER[0]:
                p.dev = PE.DEV_ORDER[PE.DEV_ORDER.index(p.dev) - 1]; change = 'down'
            if change:
                moved.append((p, change, float(pr), float(ex), sorted(aw)))
                league.log('dev_trait', pid=p.pid, pos=p.pos, age=round(p.age, 1),
                           change=change, dev=p.dev, production=round(float(pr), 2),
                           expected=round(float(ex), 2), awards=sorted(aw))
    if verbose:
        ups = [m for m in moved if m[1] == 'up']; downs = [m for m in moved if m[1] == 'down']
        print(f'  dev traits: {len(ups)} up, {len(downs)} down, of {sum(len(v) for v in groups.values())} who played')
    return moved

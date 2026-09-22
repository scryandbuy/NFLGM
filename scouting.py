"""
SCOUTING, the simple version.

Every GM has a scouting rating. For each prospect each club draws ONE error,
fixed for the year, and sees the prospect's overall through it: the best rooms
sit about 1.5 points from the truth on average, the worst about 6. The ceiling
is scouted twice as badly as the present, which is where busts and steals
come from. A club that is wrong about a man stays wrong about him all spring,
so it reaches for him or passes on him for a reason.

The consensus board is the average of the 32 reads, more accurate than any
one room, the way the real one is. A reach is a club's private read
disagreeing with it.

The true ratings are never shown until the man is drafted.

Later patches: exact combine measurables, scouting visits that shrink the
error on a chosen prospect, regional coverage.
"""
import numpy as np

SD_BEST, SD_WORST = 1.5, 6.0
CEILING_MULT = 2.0


def error_sd(gm):
    s = float(getattr(gm, 'scouting', 0.5)) if gm is not None else 0.5
    return SD_WORST - (SD_WORST - SD_BEST) * s


def scout(league, rng):
    """
    league.scouting = {team: {pid: dict(ovr, pot_lo, pot_hi)}} for the class on
    league.draft_pool, plus league.consensus = {pid: dict(ovr, pot, rank)}.
    """
    pool = league.draft_pool
    views = {}
    for abbr, team in league.teams.items():
        sd = error_sd(team.gm)
        v = {}
        for p in pool:
            e = float(rng.normal(0.0, sd))
            lo, hi = p.potential_range if p.potential_range else (p.ovr, p.ovr + 3)
            e_pot = float(rng.normal(0.0, sd * CEILING_MULT))
            v[p.pid] = dict(ovr=round(float(np.clip(p.ovr + e, 30, 99)), 1),
                            pot_lo=round(float(np.clip(lo + e_pot, 30, 99)), 1),
                            pot_hi=round(float(np.clip(hi + e_pot, 30, 99)), 1))
        views[abbr] = v
    cons = {}
    for p in pool:
        o = np.mean([views[a][p.pid]['ovr'] for a in views])
        pt = np.mean([(views[a][p.pid]['pot_lo'] + views[a][p.pid]['pot_hi']) / 2 for a in views])
        cons[p.pid] = dict(ovr=round(float(o), 1), pot=round(float(pt), 1))
    # the board is ranked by VALUE, not raw overall: the engine rates kickers
    # in the high 80s, and on raw overall ten kickers and punters topped it
    # ranked the way the boards are: rank within position by the room's
    # grade, then the position's slot curve
    import draft as DRAFT
    groups = {}
    for p in pool:
        groups.setdefault(DRAFT.SLOT_GROUP.get(p.pos, p.pos), []).append(p)
    slot = {}
    for g, ps in groups.items():
        ps.sort(key=lambda p: -(0.6 * cons[p.pid]['ovr'] + 0.4 * cons[p.pid]['pot']))
        for i, p in enumerate(ps):
            slot[p.pid] = DRAFT.expected_slot(p.pos, i)
    for r, pid in enumerate(sorted(cons, key=lambda k: slot[k]), 1):
        cons[pid]['rank'] = r; cons[pid]['slot'] = slot[pid]
    league.scouting = views
    league.consensus = cons
    return views, cons


def view(league, abbr, pid):
    """What one club believes about one prospect."""
    return league.scouting[abbr][pid]

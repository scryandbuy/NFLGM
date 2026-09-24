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
PHYS_SHARE = 0.35        # the share of a read's error that is about the body
POWER = {'SEC', 'Big Ten', 'Big 12', 'ACC', 'Pac-12', 'Big East', 'Independent'}


def _power(p):
    conf = getattr(p, 'conference', None)
    return conf is None or conf in POWER


def _refresh(view, p):
    """The numbers a room sees, from the truth and its own errors."""
    lo, hi = p.potential_range if p.potential_range else (p.ovr, p.ovr + 3)
    adj = view.get('adj', 0.0)          # medical and character, by this room
    view['ovr'] = round(float(np.clip(p.ovr + view['e_phys'] + view['e_skill'] + adj, 30, 99)), 1)
    view['pot_lo'] = round(float(np.clip(lo + view['e_pot'] + adj, 30, 99)), 1)
    view['pot_hi'] = round(float(np.clip(hi + view['e_pot'] + adj, 30, 99)), 1)


def second_look(view, p, sd, rng, weight=1.0):
    """Another read on the man, averaged into the room's skill and ceiling errors."""
    n = view.get('reads', 1)
    draw_s = float(rng.normal(0.0, sd * (1 - PHYS_SHARE) ** 0.5)); draw_p = float(rng.normal(0.0, sd * CEILING_MULT))
    view['e_skill'] = (view['e_skill'] * n + draw_s * weight) / (n + weight)
    view['e_pot'] = (view['e_pot'] * n + draw_p * weight) / (n + weight)
    view['reads'] = n + weight
    _refresh(view, p)


def consensus(league):
    """Recompute the room's average and the board after the reads moved."""
    pool = league.draft_pool or getattr(league, 'next_class', [])
    views = league.scouting
    cons = {}
    for p in pool:
        if not all(p.pid in views[a] for a in views): continue
        o = np.mean([views[a][p.pid]['ovr'] for a in views])
        pt = np.mean([(views[a][p.pid]['pot_lo'] + views[a][p.pid]['pot_hi']) / 2 for a in views])
        prev = (league.consensus or {}).get(p.pid, {})
        cons[p.pid] = dict(ovr=round(float(o), 1), pot=round(float(pt), 1), prev_rank=prev.get('rank'))
    _rank(league, pool, cons)
    league.consensus = cons
    return cons


def error_sd(gm, team=None):
    """The room's error. The head scout sets it when the club has one; the GM's
    own dial is the fallback for a league built before staff existed."""
    if team is not None and getattr(team, 'staff', None) and team.staff.get('scout') is not None:
        import staff as ST
        s = ST.scout_quality(team)
    else:
        s = float(getattr(gm, 'scouting', 0.5)) if gm is not None else 0.5
    return SD_WORST - (SD_WORST - SD_BEST) * s


def scout(league, rng):
    """
    league.scouting = {team: {pid: dict(ovr, pot_lo, pot_hi)}} for the class on
    league.draft_pool, plus league.consensus = {pid: dict(ovr, pot, rank)}.
    """
    pool = league.draft_pool or getattr(league, 'next_class', [])
    # men few rooms watched carry a wider first read: the back half of the
    # class by true value, and small-school men more so. The spring's second
    # looks move them most, which is where the helium comes from.
    by_val = sorted(pool, key=lambda p: -p.ovr)
    deep = {p.pid for p in by_val[len(by_val) // 2:]}
    views = {}
    for abbr, team in league.teams.items():
        sd = error_sd(team.gm, team)
        v = {}
        for p in pool:
            wide = 1.0 + (0.5 if p.pid in deep else 0.0) + (0.4 if not _power(p) else 0.0)
            # the error has a physical part (the forty, the size) and a skill
            # part; the combine collapses the first, second looks shrink the second
            e_phys = float(rng.normal(0.0, sd * wide * PHYS_SHARE ** 0.5))
            e_skill = float(rng.normal(0.0, sd * wide * (1 - PHYS_SHARE) ** 0.5))
            lo, hi = p.potential_range if p.potential_range else (p.ovr, p.ovr + 3)
            e_pot = float(rng.normal(0.0, sd * wide * CEILING_MULT))
            v[p.pid] = dict(e_phys=e_phys, e_skill=e_skill, e_pot=e_pot, reads=1, flags=[])
            _refresh(v[p.pid], p)
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
    _rank(league, pool, cons)
    league.scouting = views
    league.consensus = cons
    return views, cons


def _rank(league, pool, cons):
    import draft as DRAFT
    groups = {}
    for p in pool:
        if p.pid in cons: groups.setdefault(DRAFT.SLOT_GROUP.get(p.pos, p.pos), []).append(p)
    slot = {}
    for g, ps in groups.items():
        ps.sort(key=lambda p: -(0.6 * cons[p.pid]['ovr'] + 0.4 * cons[p.pid]['pot']))
        for i, p in enumerate(ps):
            slot[p.pid] = DRAFT.expected_slot(p.pos, i)
    for r, pid in enumerate(sorted(cons, key=lambda k: slot[k]), 1):
        cons[pid]['rank'] = r; cons[pid]['slot'] = slot[pid]


def view(league, abbr, pid):
    """What one club believes about one prospect."""
    return league.scouting[abbr][pid]

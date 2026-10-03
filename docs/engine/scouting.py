from stable import stable_seed
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


POT_ERR_CAP = 7.0        # the most a room's read of a ceiling can be off

# CERTAINTY. How much of a player a room has seen, 0 to 1, kept on the view and never shown. It starts where the
# first read's information starts (more on the top half of the class, less deep and at small schools), and every
# look raises it by an amount the head scout sets: a great head scout learns more from the same Senior Bowl than
# a poor one. The room's remaining error and the width of its ceiling read both follow it.
CERT_START_TOP, CERT_START_DEEP, CERT_SMALL_SCHOOL = 0.35, 0.22, -0.06
CERT_LOOK_BASE, CERT_LOOK_SCOUT = 0.10, 0.12          # a look adds base + scout share × head-scout quality
CERT_VISIT_MULT, CERT_COMBINE, CERT_MAX = 1.6, 0.08, 0.92


def scout_q(team):
    """The head scout's quality, 0 to 1; the GM's dial when the club has no scout."""
    try:
        if team is not None and getattr(team, 'staff', None) and team.staff.get('scout') is not None:
            import staff as ST
            return float(np.clip(ST.scout_quality(team), 0.0, 1.0))
    except Exception: pass
    return float(np.clip(float(getattr(getattr(team, 'gm', None), 'scouting', 0.5) or 0.5), 0.0, 1.0))


def cert_gain(team, weight=1.0):
    return (CERT_LOOK_BASE + CERT_LOOK_SCOUT * scout_q(team)) * float(weight)


def certainty(view):
    return float(np.clip(float(view.get('cert', CERT_START_TOP) or 0.0), 0.0, CERT_MAX))
TAPE_SD = 4.0            # the whole league's shared error on a player: what his tape says against what he is
TAPE_FLOOR = 0.4         # how much of it survives every look; a visit and a workout uncover the rest, not all of it


def tape(p):
    """THE TAPE. One error per prospect that every room sees on top of its own, drawn once and kept with him.
    Thirty-two independent reads average to the truth, which had the league grading every player within a point of
    what he was; real drafts have busts and steals because the league is wrong about a player together. The tape
    fades with a room's looks (a visit uncovers part of it) but never entirely."""
    t = p.xp_spent.get('_tape')
    if t is None:
        r = np.random.default_rng(stable_seed(('tape', p.pid)))
        t = float(np.clip(r.normal(0.0, TAPE_SD), -10.0, 10.0)); p.xp_spent['_tape'] = t
    return float(np.clip(t, -15.0, 15.0))       # the class builder's gems and busts carry up to fifteen


def _refresh(view, p):
    """The numbers a room sees, from the truth, the tape, and its own errors."""
    lo, hi = p.potential_range if p.potential_range else (p.ovr, p.ovr + 3)
    adj = view.get('adj', 0.0)          # medical and character, by this room
    n = float(view.get('reads', 1) or 1)
    # the room's own error left: the first draw scaled by what remains unknown, against what was unknown at the start
    c, c0 = certainty(view), float(view.get('cert0', CERT_START_TOP) or CERT_START_TOP)
    left = (1.0 - c) / max(0.05, 1.0 - c0)
    if 'e_skill0' in view: view['e_skill'] = float(view['e_skill0']) * left
    if 'e_pot0' in view: view['e_pot'] = float(np.clip(float(view['e_pot0']) * left, -POT_ERR_CAP, POT_ERR_CAP))
    fade = max(TAPE_FLOOR, 1.0 - 0.25 * (n - 1.0))
    if 'visited' in (view.get('flags') or []):
        # A VISIT IS THE LOOK THAT SEES THROUGH TAPE. In the building, on the board, in the interview, a room learns
        # most of what the film hid: three-quarters of a gem's or a bust's tape, half of an ordinary player's
        fade = min(fade, 0.25 if p.xp_spent.get('_tape_role') else 0.5)
    tp = tape(p) * fade
    view['ovr'] = round(float(np.clip(p.ovr + view['e_phys'] + view['e_skill'] + tp + adj, 30, 99)), 1)
    # a room's ceiling read is bounded: nobody sees a 59 as a 97. The ceiling error is capped and the ceiling
    # itself cannot sit more than eighteen points above what the room sees today
    e_pot = float(np.clip(view.get('e_pot', 0.0) or 0.0, -POT_ERR_CAP, POT_ERR_CAP)); view['e_pot'] = e_pot
    # the tape colours the ceiling too: a hidden player's upside is hidden with him, an inflated one's inflated.
    # The width of the ceiling read is the room's uncertainty: wide on a first look, narrowing with every one after
    mid = (lo + hi) / 2.0 + e_pot + tp + adj
    half = (hi - lo) / 2.0 * (0.5 + 0.5 * (1.0 - c)) + 5.0 * (1.0 - c)
    view['pot_lo'] = round(float(np.clip(min(mid - half, view['ovr'] + 12.0), 30, 99)), 1)
    view['pot_hi'] = round(float(np.clip(min(mid + half, view['ovr'] + 18.0), max(view['pot_lo'], 30), 99)), 1)


def second_look(view, p, sd, rng, weight=1.0, R=None, team=None):
    """Another read on the player, averaged into the room's skill and ceiling errors. The room's
    traits scale and lean the new draw the same way they did the first. Certainty rises by what the head
    scout gets from a look; the residual error and the ceiling's width follow it in the refresh."""
    R = R or dict(skill_mult=1.0, skill_bias=0.0, pot_mult=1.0, pot_bias=0.0)
    n = view.get('reads', 1)
    view['cert'] = float(np.clip(float(view.get('cert', CERT_START_TOP) or 0.0) + cert_gain(team, weight), 0.0, CERT_MAX))
    draw_s = float(rng.normal(0.0, sd * (1 - PHYS_SHARE) ** 0.5)) * R['skill_mult'] + R['skill_bias']; draw_p = float(rng.normal(0.0, sd * CEILING_MULT)) * R['pot_mult'] + R['pot_bias']
    # _refresh derives the displayed errors from these baselines. Update the
    # baselines with the new evidence; changing e_skill/e_pot directly would
    # be discarded by _refresh on this very call.
    view['e_skill0'] = (float(view.get('e_skill0', view['e_skill'])) * n + draw_s * weight) / (n + weight)
    view['e_pot0'] = float(np.clip((float(view.get('e_pot0', view['e_pot'])) * n + draw_p * weight) / (n + weight), -POT_ERR_CAP, POT_ERR_CAP))
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


def room(team):
    """The head scout's traits as the room's terms: multipliers on each error and a bias on each,
    whether the small-school widening applies, how far the second looks reach, and how the
    character read behaves. A room with no scout is a plain room."""
    import staff_traits as STR
    s = (getattr(team, 'staff', None) or {}).get('scout') if team is not None else None
    t = dict(skill_mult=1.0, skill_bias=0.0, phys_mult=1.0, phys_bias_athlete=0.0, pot_mult=1.0, pot_bias=0.0,
             small_school_wide=0.4, power_bias=0.0, character='normal', looks_mult=1.0, day3_reads=True)
    if s is None: return t
    if STR.has(s, 'eye'): t['skill_mult'] = 0.75
    if STR.has(s, 'wants'): t['skill_mult'] = 1.25; t['skill_bias'] = 1.0
    if STR.has(s, 'stopwatch'): t['phys_mult'] = 0.70
    if STR.has(s, 'measurables'): t['phys_mult'] = 1.25; t['phys_bias_athlete'] = 1.5
    if STR.has(s, 'projector'): t['pot_mult'] = 0.70
    if STR.has(s, 'floor'): t['pot_mult'] = 1.25; t['pot_bias'] = -2.0
    if STR.has(s, 'small_school'): t['small_school_wide'] = 0.0
    if STR.has(s, 'big_program'): t['small_school_wide'] = 0.8; t['power_bias'] = 1.5
    if STR.has(s, 'character'): t['character'] = 'sharp'
    if STR.has(s, 'tape'): t['character'] = 'none'
    if STR.has(s, 'grinder'): t['looks_mult'] = 1.33
    if STR.has(s, 'narrow'): t['day3_reads'] = False
    return t


def _athlete(p):
    """Does his body outrun his skill: the physical grades against the rest."""
    r = p.ratings; phys = np.mean([r.get(k, 60) for k in ('speed_rating', 'accel_rating', 'agility_rating', 'jump_rating', 'strength_rating')])
    skill = np.mean([v for k, v in r.items() if k.endswith('_rating') and k not in ('speed_rating', 'accel_rating', 'agility_rating', 'jump_rating', 'strength_rating', 'stamina_rating', 'injury_rating', 'toughness_rating')] or [phys])
    return float(phys - skill)


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
        sd = error_sd(team.gm, team); R = room(team)
        v = {}
        for p in pool:
            wide = 1.0 + (0.5 if p.pid in deep else 0.0) + (R['small_school_wide'] if not _power(p) else 0.0)
            # the error has a physical part (the forty, the size) and a skill
            # part; the combine collapses the first, second looks shrink the second.
            # The room's traits scale each part and lean it: an Eye for Talent tightens skill,
            # a Stopwatch tightens the body, a Projector the ceiling; the blind spots widen and bias
            e_phys = float(rng.normal(0.0, sd * wide * PHYS_SHARE ** 0.5)) * R['phys_mult'] + (R['phys_bias_athlete'] if _athlete(p) > 4.0 else 0.0)
            e_skill = float(rng.normal(0.0, sd * wide * (1 - PHYS_SHARE) ** 0.5)) * R['skill_mult'] + R['skill_bias'] + (R['power_bias'] if _power(p) else 0.0)
            lo, hi = p.potential_range if p.potential_range else (p.ovr, p.ovr + 3)
            e_pot = float(np.clip(float(rng.normal(0.0, sd * wide * CEILING_MULT)) * R['pot_mult'] + R['pot_bias'], -POT_ERR_CAP, POT_ERR_CAP))
            c0 = (CERT_START_DEEP if p.pid in deep else CERT_START_TOP) + (CERT_SMALL_SCHOOL if not _power(p) else 0.0)
            v[p.pid] = dict(e_phys=e_phys, e_skill=e_skill, e_pot=e_pot, reads=1, flags=[], cert=float(c0), cert0=float(c0),
                            e_skill0=e_skill, e_pot0=e_pot)
            _refresh(v[p.pid], p)
            import character_assessment as CA
            CA.film(p, abbr, v[p.pid], small_school=not _power(p))
            if R['character'] == 'none': v[p.pid]['character_skipped'] = 'tape'
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
    # A STRONG POSITION CLASS DOES NOT BURY ITS EIGHTH PLAYER. The slot is the position's rank table (the mix by
    # construction) blended with where his grade sits in the whole class, so a 79 back in a year with ten of them
    # still reads as a third-round player rather than a seventh
    grade_of = {p.pid: 0.6 * cons[p.pid]['ovr'] + 0.4 * cons[p.pid]['pot'] for p in pool if p.pid in cons}
    grades_desc = sorted(grade_of.values())
    for g, ps in groups.items():
        ps.sort(key=lambda p: -grade_of[p.pid])
        for i, p in enumerate(ps):
            by_rank = DRAFT.expected_slot(p.pos, i)
            if p.pos in ('K', 'P', 'LS', 'FB'):
                slot[p.pid] = by_rank
            else:
                slot[p.pid] = 0.5 * by_rank + 0.5 * DRAFT.grade_slot(grade_of[p.pid], grades_desc)
    for r, pid in enumerate(sorted(cons, key=lambda k: slot[k]), 1):
        cons[pid]['rank'] = r; cons[pid]['slot'] = slot[pid]


def view(league, abbr, pid):
    """What one club believes about one prospect."""
    return league.scouting[abbr][pid]


def scheme_fit_view(league, abbr, p, view):
    """How the prospect grades in this club's scheme, ON THE ROOM'S READ: the scouted attribute vector (the true
    ratings shifted by the room's physical and skill errors) run through the same fit function the roster uses.
    As uncertain as the estimate it is built from; a visit tightens both."""
    import gm_engine as GE, xp as XP
    team = league.teams.get(abbr)
    if team is None or view is None: return 0.0
    e_p, e_s = float(view.get('e_phys', 0.0) or 0.0), float(view.get('e_skill', 0.0) or 0.0)
    fade = max(TAPE_FLOOR, 1.0 - 0.25 * (float(view.get('reads', 1) or 1) - 1.0))
    if 'visited' in (view.get('flags') or []): fade = min(fade, 0.25 if p.xp_spent.get('_tape_role') else 0.5)
    e_s += tape(p) * fade
    seen = {k: float(np.clip(v + (e_p if (k in XP.PHYSICAL or k in XP.TOOLS) else e_s), 30.0, 99.0)) for k, v in p.ratings.items()}
    try: return round(float(GE.scheme_fit(seen, p.pos, team)), 1)
    except Exception: return 0.0


def senior_bowl(league, rng, *, event_year=None):
    """The week before the Championship Game, in Mobile: the seniors who accept the invitation play in front of every
    scouting department. Every room gets a second look at them (their estimates tighten and move), the players
    carry the mark on the board, and the user's assistants say who helped himself and who did not."""
    pool = list(getattr(league, 'draft_pool', None) or getattr(league, 'next_class', None) or [])   # in season the class waits in next_class
    if not pool: return []
    event_year = league.year + 1 if event_year is None else event_year
    if any(x.get('year') == event_year and x.get('event') == 'Senior Bowl'
           and x.get('kind') == 'event' for x in (getattr(league, 'spring_news', None) or [])):
        return []
    if any(p.xp_spent.get('_senior_bowl') in (event_year - 1, event_year) for p in pool):
        return []
    cons = getattr(league, 'consensus', None) or {}
    seniors = [p for p in pool if p.age >= 22.5 and p.pos not in ('K', 'P', 'LS')]
    # about 110 invitations: the consensus top of the senior class, with some depth mixed in
    ranked = sorted(seniors, key=lambda p: (cons.get(p.pid, {}).get('rank') or 999))
    invited = ranked[:80] + [p for p in ranked[80:] if rng.random() < 0.15][:35]
    user = getattr(league, 'user_team', None)
    before = {p.pid: (getattr(league, 'scouting', {}).get(user, {}).get(p.pid, {}) or {}).get('ovr') for p in invited} if user else {}
    for abbr, team in league.teams.items():
        views = (getattr(league, 'scouting', None) or {}).get(abbr) or {}
        sd = error_sd(team.gm, team); R = room(team)
        for p in invited:
            v = views.get(p.pid)
            if v is None: continue
            second_look(v, p, sd * 0.85, rng, weight=0.7, R=R, team=team)
    for p in invited:
        p.xp_spent['_senior_bowl'] = league.year
    # the consensus moves with the rooms
    try: consensus(league)
    except Exception: pass
    # Played before the year roll; results belong to the following spring.
    import spring as SP
    SP._stock_moves(league, 'Senior Bowl', year=event_year)
    SP._log(league, 'event', year=event_year, event='Senior Bowl', participants=len(invited))
    moves = []
    if user:
        after = getattr(league, 'scouting', {}).get(user, {}) or {}
        for p in invited:
            b = before.get(p.pid); a = (after.get(p.pid) or {}).get('ovr')
            if b is None or a is None: continue
            moves.append((round(float(a) - float(b), 1), p))
    return moves

"""
ZONE AS SPACE.

The coverage call defines areas and who owns them; a route lands in an
area; the man who contests the throw is the owner of that area, with a
second defender converging on longer throws from the next area over. An
area with no owner (a blitz took him, or the call leaves it, like the deep
middle in Cover 2) is a hole. Quarters pattern-matches: a vertical route by
an outside receiver is played man by the quarter's owner.

Before this, a zone snap was still a pairing: the receiver's matched
defender contested every throw to him, so a corner contested the dig that
runs into a linebacker's area, deep balls never found a seam, and passes
defended piled up on corners.

Areas: deep_L, deep_M, deep_R; hook_L, hook_M, hook_R; flat_L, flat_R.
"""
import numpy as np

HOLE_WINDOW = 1.30          # the window when nobody owns the area
CONVERGE_WEIGHT = 0.45      # the second defender's squeeze, relative to the owner's


def landing(spot, side, depth, receiver_pos=None):
    """Where the route puts the ball."""
    s = 'L' if side in ('L', 'left') else 'R' if side in ('R', 'right') else 'C'
    if depth == 'deep':
        if spot in ('X', 'Z') and s != 'C': return f'deep_{s}'
        return 'deep_M'                       # seams: slot and tight end verticals, the post
    if depth == 'medium':
        if spot in ('X', 'Z') and s != 'C': return f'hook_{s}'
        return 'hook_M'                       # digs and crossers over the ball
    # short
    if spot == 'back': return 'flat_L' if s == 'L' else 'flat_R' if s == 'R' else 'hook_M'
    if spot in ('X', 'Z') and s != 'C': return f'flat_{s}'
    if spot == 'te': return f'hook_{s}' if s != 'C' else 'hook_M'
    return f'hook_{s}' if s != 'C' else 'hook_M'


def _pick(pool, used, key=None):
    for d in (sorted(pool, key=key) if key else pool):
        if d is not None and id(d) not in used:
            used.add(id(d)); return d
    return None


def owners(call, unit, rushers, rate):
    """
    {area: defender or None} for this call from the men who dropped. Corners
    hold their sides; safeties take the deep middle or halves; the fifth
    and sixth backs and the linebackers fill underneath, best in space
    first. Rushers never own an area.
    """
    rid = {id(r) for r in rushers or []}
    cbs = [d for d in unit.get('cbs', []) if id(d) not in rid]
    safs = [d for d in unit.get('safs', []) if id(d) not in rid]
    lbs = [d for d in unit.get('lbs', []) if id(d) not in rid]
    sides = unit.get('sides') or {}
    cbL = sides.get('L'); cbR = sides.get('R')
    if cbL is None and cbs: cbL = cbs[0]
    if cbR is None and len(cbs) > 1: cbR = cbs[1]
    nick = [c for c in cbs if c is not cbL and c is not cbR]
    used = set(); Z = {}
    space = lambda d: -rate(d, {'zone_cover_rating': .5, 'speed_rating': .3, 'play_rec_rating': .2})
    def deep_thirds():
        Z['deep_L'] = _pick([cbL], used); Z['deep_R'] = _pick([cbR], used)
        Z['deep_M'] = _pick(safs, used, space)
    def under(areas):
        pool = nick + [s for s in safs if id(s) not in used] + lbs
        for a in areas:
            Z[a] = _pick(pool, used, space)
    if call in ('cover_3', 'cover_3_mable', 'fire_zone'):
        deep_thirds()
        under(['flat_L', 'flat_R', 'hook_L', 'hook_R'] if call != 'fire_zone' else ['hook_L', 'hook_R', 'flat_L'])
        Z.setdefault('hook_M', Z.get('hook_L') or Z.get('hook_R')); Z.setdefault('flat_R', None)
    elif call in ('cover_2', 'tampa_2'):
        Z['deep_L'] = _pick(safs, used, space); Z['deep_R'] = _pick(safs, used, space)
        Z['deep_M'] = _pick(lbs, used, space) if call == 'tampa_2' else None      # the hole in Cover 2
        Z['flat_L'] = _pick([cbL], used); Z['flat_R'] = _pick([cbR], used)
        under(['hook_L', 'hook_R', 'hook_M'])
    elif call in ('cover_4',):
        Z['deep_L'] = _pick([cbL], used); Z['deep_R'] = _pick([cbR], used)
        Z['deep_M'] = _pick(safs, used, space)      # the two safeties split the seams; one is named
        under(['hook_M', 'flat_L', 'flat_R', 'hook_L', 'hook_R'])
    elif call == 'cover_6':
        Z['deep_L'] = _pick([cbL], used); Z['deep_M'] = _pick(safs, used, space); Z['deep_R'] = _pick(safs, used, space)
        Z['flat_R'] = _pick([cbR], used)
        under(['flat_L', 'hook_L', 'hook_R', 'hook_M'])
    else:
        return None                                    # a man call: pairings stand
    for a in ('deep_L', 'deep_M', 'deep_R', 'hook_L', 'hook_M', 'hook_R', 'flat_L', 'flat_R'):
        Z.setdefault(a, None)
    return Z


NEIGHBOUR = {'deep_L': ['deep_M'], 'deep_R': ['deep_M'], 'deep_M': ['deep_L', 'deep_R'],
             'hook_L': ['hook_M', 'flat_L'], 'hook_R': ['hook_M', 'flat_R'], 'hook_M': ['hook_L', 'hook_R'],
             'flat_L': ['hook_L'], 'flat_R': ['hook_R']}


def contest(call, pair, rushers, depth, rng, rate):
    """
    (owner, converger, hole, match_man) for a throw to this receiver in this
    call. match_man is a quarters vertical played man by the quarter owner.
    """
    unit = pair.get('_unit') or {}
    Z = owners(call, unit, rushers, rate)
    if Z is None:
        return pair.get('defender'), None, False, False
    area = landing(pair.get('spot'), pair.get('side', 'C'), depth)
    owner = Z.get(area)
    hole = owner is None
    second = None
    if depth in ('deep', 'medium'):
        for nb in NEIGHBOUR.get(area, []):
            d = Z.get(nb)
            if d is not None and d is not owner:
                rng_ = rate(d, {'speed_rating': .5, 'zone_cover_rating': .3, 'play_rec_rating': .2})
                if rng.random() < 0.35 + 0.6 * (rng_ - 0.70):
                    second = d; break
    match_man = (call == 'cover_4' and depth == 'deep' and pair.get('spot') in ('X', 'Z') and owner is not None)
    return owner, second, hole, match_man

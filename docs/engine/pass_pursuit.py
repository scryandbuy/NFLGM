"""Post-catch pursuers drawn from the coverage actually played on this snap."""
from defensive_rush import assignments, player_key
import zones


def select(coverage, call, pair, pairs, primary, helper, depth, separation,
           in_man, hole=False, screen=False):
    """Keep nearby coverage players distinct; a blitzing player cannot reappear.

    This is a coarse assignment/side model, not tracked field coordinates.
    Deep catches use the remaining deep coverage, not random underneath men.
    """
    rows = assignments(coverage, call)
    live = {player_key(a['player']): a['player'] for a in rows}
    pair = pair or {}
    name = call.get('coverage') or call.get('shell', 'cover_3')
    side = pair.get('side', 'C')
    side = {'left': 'L', 'right': 'R'}.get(side, side)
    deep_catch = depth == 'deep' and not screen
    if deep_catch:
        # Match the zone resolver's catch area: a slot/TE vertical is a seam
        # even when the receiver lined up on the right or left of the formation.
        area = zones.landing(pair.get('spot'), side, depth)
        side = 'C' if area == 'deep_M' else area[-1]
    trailing = bool(primary and deep_catch and in_man and separation >= .5)
    out, used = [], set()

    def add(p):
        if not p:
            return
        key = player_key(p)
        if key in live and key not in used:
            out.append(live[key]); used.add(key)

    # The actual throw contest identifies the first contact opportunity.
    if not hole and not trailing:
        add(primary)
    add(helper)

    unit = pair.get('_unit') or {}
    zone = zones.owners(name, unit, [], _rate) if unit else None
    deep = []
    if zone is not None:
        # Same-side deep owner, then the adjacent middle; seam catches can
        # draw both halves. Never invent an underneath pursuer for a deep ball.
        areas = (['deep_'+side, 'deep_M'] if side in ('L', 'R')
                 else ['deep_M', 'deep_L', 'deep_R'])
        deep = [zone.get(area) for area in areas]
    elif name != 'cover_0':
        safeties = [a for a in rows if a['alignment'].startswith('deep_')]
        single = name in ('cover_1', 'cover_1_robber')
        # Man defenders occupied by other receivers are not free safety help.
        occupied = {player_key(p['defender']) for p in pairs
                    if p.get('man') and p.get('defender') and p is not pair}
        for a in safeties[:1] if single else safeties:
            p = a['player']
            same_side = a['alignment'] == ('deep_right' if side == 'L' else 'deep_left')
            if player_key(p) not in occupied and (single or side == 'C' or same_side):
                deep.append(p)

    if deep_catch:
        for p in deep:
            add(p)
        # Separation delays the primary defender; it does not delete his
        # recovery pursuit. Deep support gets the first chance, then the
        # trailing defender can recover if the receiver escapes that help.
        if trailing and not hole:
            add(primary)
        return out[:2]

    # Underneath catches: actual owner/helper first, nearby underneath players
    # next, and deep support last. Side ties use IDs, never roster list order.
    target_side = 'right' if side == 'L' else 'left' if side == 'R' else ''
    def proximity(a):
        alignment = a['alignment']
        is_deep = alignment.startswith('deep_')
        opposite = bool(target_side and ('left' in alignment or 'right' in alignment)
                        and target_side not in alignment)
        return is_deep, opposite, player_key(a['player'])
    count = 4 if screen or depth == 'medium' or pair.get('spot') == 'back' else 3
    # A short completion can become a long run too. Reserve the last pursuit
    # opportunity for the relevant deep support instead of filling every slot
    # with underneath defenders and declaring the field empty behind them.
    last = next((p for p in deep if p and player_key(p) in live
                 and player_key(p) not in used), None)
    near_count = count - bool(last)
    for a in sorted(rows, key=proximity):
        if len(out) >= near_count:
            break
        if last and player_key(a['player']) == player_key(last):
            continue
        add(a['player'])
    add(last)
    return out[:count]


def _rate(p, weights):
    return sum(p.get(k, 70) * v for k, v in weights.items()) / 100

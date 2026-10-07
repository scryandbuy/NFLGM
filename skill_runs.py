"""Occasional handoffs to skill players already in the selected eleven."""
import math

WR_RUN = dict(speed_rating=.30, accel_rating=.20, agility_rating=.15,
              bcv_rating=.15, carry_rating=.20)
FB_RUN = dict(carry_rating=.35, bcv_rating=.25, truck_rating=.20,
              break_tackle_rating=.20)


def choose(off, call, ytg, rate, rng):
    """Return a carrier and action, or retain the ordinary run.

    This is a situational changeup, never a touch quota. Use current running
    attributes, not overall rating or hidden development potential. Motion
    reflects the coach's existing call tendencies, not a universal WR rate.
    """
    if (call.get('is_pass') or call.get('sneak') or call.get('qb_run')
            or call.get('protect_ball') or 'down' not in call or not off.get('rb')):
        return None, None
    down, distance = call['down'], call.get('ydstogo', 10)
    seconds = call.get('seconds')
    if seconds is not None and seconds <= 120:
        return None, None
    scheme = call.get('scheme', 'inside_zone')
    candidates = []
    if down <= 2 and 3 <= distance <= 12 and ytg > 10 and scheme in ('outside_zone', 'stretch'):
        for player in off.get('wr') or ():
            if player.get('pos') != 'WR':
                continue
            quality = rate(player, WR_RUN)
            weight = .012 * math.exp(max(-2., min(1., (quality - .75) / .12)))
            if call.get('motion'):
                weight *= 2.
            candidates.append((player, 'jet_sweep' if call.get('motion') else 'end_around', weight))
    if distance <= 2 and scheme in ('inside_zone', 'power', 'duo', 'trap'):
        for role, player in off.get('offensive_assignments') or ():
            # A TE filling the FB blocking role has not demonstrated FB carries.
            if role == 'FB' and player.get('pos') == 'FB':
                quality = rate(player, FB_RUN)
                weight = .06 * math.exp(max(-2., min(.7, (quality - .70) / .12)))
                candidates.append((player, 'fb_handoff', weight))
    if not candidates:
        return None, None
    # The best available runner determines whether the changeup is attractive.
    # Extra receivers offer alternatives, not extra independent call chances.
    chance = max(weight for _, _, weight in candidates)
    draw = rng.random()
    if draw >= chance:
        return None, None
    draw = draw / chance * sum(weight for _, _, weight in candidates)
    for player, action, weight in candidates:
        draw -= weight
        if draw < 0:
            return player, action
    return candidates[-1][0], candidates[-1][1]

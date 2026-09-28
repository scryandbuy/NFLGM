"""
FIT ON THE FIELD. The front office grades a player through his club's scheme
(gm_engine.scheme_fit, the Fit number on the card). Until this module that
number reached nothing on a Sunday: every snap read the raw card. Here it
becomes game-day ratings.

The shift is by attribute, in the direction the club's tags already define
(targets.SCHEME_SHIFT): a zone club gets more out of a lineman's finesse
blocking and less out of his power, a two-high defense more out of a safety's
zone cover. Each touched attribute moves in proportion to how far the player
sits above or below his own position grade on it, so a finesse blocker gains
finesse and a mauler loses power, and the position-weighted total of the
shifts equals his fit. So the number on the card is the number on the field,
at the position-grade level.

Centered: fits do not average to zero at a position across the league (a
scheme that values zone cover lifts every safety who has it), so the shift
applied is his fit minus the league mean at his position that week. The
effect is who gains and who loses against each other; league scoring holds.
"""
import numpy as np
import targets as TG

GAIN = 3.2         # from the register rosters: a player's touched attributes move, in the tag's direction, by his card fit on average (slope 1.0); typical move ~1 point, 90th pct ~3.6
FIELD = 1.0        # a knob on top of GAIN; 1.0 is the calibrated size
CAP = 4.0          # the position-grade composite of a player's shifts, either way
ATTR_CAP = 8.0     # any one attribute, either way
SPECIALISTS = ('K', 'P', 'LS')


def touched(pos, tags):
    """The weight shift the club's tags put on each attribute the spot weighs (the card's up/down markers)."""
    w = TG.DEPTH_WEIGHTS.get(pos, {})
    out = {}
    for s in (tags or []):
        if pos not in TG.SCHEME_DOMAIN.get(s, ()):
            continue
        for k, v in TG.SCHEME_SHIFT.get(s, {}).items():
            if k in w:
                out[k] = out.get(k, 0.0) + float(v) * TG.SCHEME_BITE
    return out


def raw_fit(ratings, pos, tags, rigidity=0.5):
    """The card's number: what the scheme adds to or takes from his grade, scaled by the coach's rigidity."""
    if not tags or pos in SPECIALISTS:
        return 0.0
    raw = TG.position_score(ratings, pos)
    sch = TG.position_score(ratings, pos, tags)
    return float((sch - raw) * (0.6 + 0.8 * float(rigidity)))


def deltas(ratings, pos, tags, rigidity=0.5):
    """The uncentered game-day move on each touched attribute: the tag's direction times how far he sits
    from his own grade on it, times the coach's rigidity. A finesse blocker's finesse counts for more in
    a zone scheme (up); a mauler's power counts for less (down); a weakness the scheme does not value
    hurts less (up)."""
    if pos in SPECIALISTS or not tags:
        return {}
    sh = touched(pos, tags)
    if not sh:
        return {}
    base = TG.position_score(ratings, pos)
    scale = GAIN * FIELD * (0.6 + 0.8 * float(rigidity))
    return {k: scale * sh[k] * (float(ratings.get(k, 70.0)) - base) for k in sh}


def centers(deltas_by_pos):
    """League mean move on each attribute at each position, from {pos: [deltas, ...]}. Subtracting it
    leaves every attribute's league mean where it was, so league scoring holds and only the spread moves."""
    out = {}
    for pos, ds in deltas_by_pos.items():
        keys = set(k for d in ds for k in d)
        out[pos] = {k: float(np.mean([d.get(k, 0.0) for d in ds])) for k in keys}
    return out


def shifted(ratings, pos, d, center=None):
    """His game-day ratings from his centered moves, each attribute capped and the composite capped."""
    if not d:
        return dict(ratings)
    c = (center or {}).get(pos, {}) if center is not None else {}
    mv = {k: float(np.clip(v - c.get(k, 0.0), -ATTR_CAP, ATTR_CAP)) for k, v in d.items()}
    w = TG.DEPTH_WEIGHTS.get(pos, {}); tot = sum(w.values()) or 1.0
    comp = sum(w.get(k, 0.0) * v for k, v in mv.items()) / tot
    if abs(comp) > CAP:
        f = CAP / abs(comp); mv = {k: v * f for k, v in mv.items()}
    out = dict(ratings)
    for k, v in mv.items():
        out[k] = float(np.clip(float(ratings.get(k, 70.0)) + v, 1.0, 99.0))
    return out


def composite(ratings, shifted_ratings, pos):
    """What the shifts add to his position grade, for tests."""
    return float(TG.position_score(shifted_ratings, pos) - TG.position_score(ratings, pos))

"""Individual rush contests; public attributes and on-field assignments only."""
import math

BASE = 3.591
SENSITIVITY = .90
REFERENCE_GAP = .05
HELP = .13

# Approximate pre-snap approach coordinates in yards (lateral, off LOS),
# measured to a five-yard drop. These are model assumptions, not tracking
# data. Equal athletes retain the shorter gap's advantage; any free runner
# still has to close that distance rather than appearing at the quarterback.
FREE_APPROACH = {
    'nose': (0., 0.), 'left_interior': (1.5, 0.), 'right_interior': (1.5, 0.),
    'left_edge': (4., 0.), 'right_edge': (4., 0.),
    'offball_middle': (0., 3.), 'offball_left': (3., 3.), 'offball_right': (3., 3.),
    'slot': (7., 1.), 'corner_left': (10., 1.), 'corner_right': (10., 1.),
    'deep_left': (5., 10.), 'deep_right': (5., 10.),
}


def free_arrival_mean(player, alignment):
    """Median free path time; live field ratings already include fatigue.

    A .20s reaction plus travel at 4.5–7 yards/second is an intentionally
    simple acceleration/closing proxy. The resolver applies the same rush
    execution distribution as blocked contests; no position or star bonus.
    """
    lateral, depth = FREE_APPROACH.get(alignment, (3., 3.))
    movement = sum(float(player.get(k, 70)) * w for k, w in
                   (('accel_rating', .55), ('speed_rating', .45))) / 100.
    closing = 4.5 + 2.5 * max(0., min(1., movement))
    return .20 + math.hypot(lateral, 5. + depth) / closing


JOINT_FINISH_WINDOW = .12  # Model assumption: roughly one step at closing speed.


def sack_credits(primary, arrivals):
    """At most two nearby finishers share one sack; a late pressure does not.

    Times are the final adjusted arrivals, after QB/protection effects.
    This only attributes an already-resolved sack; it cannot cause one.
    """
    if not primary:
        return []
    times = {}
    for pid, time in arrivals:
        if pid: times[pid] = min(float(time), times.get(pid, float('inf')))
    if primary not in times:
        return [(primary, 1.)]
    near = [(time, pid) for pid, time in times.items() if pid != primary
            and -.000000001 <= time - times[primary] <= JOINT_FINISH_WINDOW]
    if not near:
        return [(primary, 1.)]
    second = min(near)[1]
    return [(primary, .5), (second, .5)]


def credited_sackers(out, fallback=None):
    """Read new/legacy credit safely, conserving one sack and unique IDs."""
    ids = []
    if out.get('by'): ids.append(out['by'])
    for pid, credit in out.get('sack_credits') or ():
        if pid and credit > 0 and pid not in ids: ids.append(pid)
    if not ids and fallback: ids.append(fallback)
    ids = ids[:2]
    return [(pid, 1. / len(ids)) for pid in ids]


def arrival_mean(attack, block, base=BASE):
    return base * math.exp(-SENSITIVITY * (attack - block - REFERENCE_GAP))


def help_effect(helper, block_grade, attack, alignment, roll, layer=0, strength=HELP):
    # A back crossing the pocket has a harder job than an adjacent lineman.
    reach = .08 if helper.get('pos') in ('HB', 'FB') and 'edge' in alignment else 0.
    awareness = float(helper.get('awareness_rating', 70)) / 100.
    chance = max(.20, min(.90, .82 + .90 * (block_grade - attack)
                           + .25 * (awareness - .75) - reach))
    return strength * max(0., min(1., block_grade)) / (layer + 1) if roll < chance else 0.


def finish_scale(player):
    # Getting through the block and finishing against a moving QB are distinct.
    ability = sum(float(player.get(k, 70)) * w for k, w in (
        ('pursuit_rating', .40), ('tackle_rating', .35), ('speed_rating', .25))) / 100.
    return max(.65, min(1.35, 1. + 1.5 * (ability - .80)))

"""
Play resolution.

Every link is an individual matchup pulling only the attributes that matter for
that contest. No unit-strength number exists anywhere.

Nothing here samples an outcome from a distribution. A play is resolved, and
the yardage is whatever the resolution produces - which is why the FIELD limits
a long run, not a curve. From your own 7 a broken tackle and a clean track is
93 yards; the identical play from the opponent's 30 is a 30-yard touchdown.

Contests resolve RELATIVE TO AVERAGE (0.70 on the 0-1 rating scale). An average
player against an average player produces an average outcome; the rating gap is
what moves the result.
"""
import numpy as np
from matchups import (PASS_RUSH, ROUTE, THROW, CATCH, YAC, RUN_BLOCK,
                      BALL_SECURITY, ZONE_DEFENDERS_NEAR, zone_window)

AVG = 0.70

def rate(p, weights):
    """Weighted attribute score on 0-1. Missing attributes default to average."""
    return sum(p.get(k, 70) * v for k, v in weights.items()) / 100.0

def edge(a, b, scale=1.0):
    """How far one side beats the other, centred on zero. Feeds logistic rolls."""
    return (a - b) * scale

def logistic(x, k=6.0):
    return 1.0 / (1.0 + np.exp(-k * x))

# ============================================================ PROTECTION
# Five individual matchups per dropback. The rusher picks the move his own
# profile favours; the blocker defends the move he actually GETS, which is how
# a powerful tackle loses to speed and a light one loses to a bull rush.
# The clock is the MINIMUM across four rushers, and the minimum of several
# draws sits well below any one of them. Per-rusher base is solved so that
# min-of-4 lands on the real 2.72s league mean: at 3.50 it gives 2.724.
# The first build used 2.72 per rusher and produced a 2.12s league average.
RUSHER_BASE = 3.50
BASE_TTT = 2.72          # the league mean the clock must land on

def resolve_protection(blockers, rushers, rng, qb=None):
    """
    Returns time available, whether a sack happened, and pressure 0-1.
    Each rusher races his blocker; the FASTEST win sets the clock.
    """
    wins = []
    for i, r in enumerate(rushers):
        b = blockers[i] if i < len(blockers) else None
        pw = rate(r, PASS_RUSH['rusher']['power'])
        fn = rate(r, PASS_RUSH['rusher']['finesse'])
        move = 'power' if pw >= fn else 'finesse'
        atk = max(pw, fn)
        if b is None:                      # unblocked - a free runner
            wins.append((0.6, move, r, None)); continue
        dfn = rate(b, PASS_RUSH['blocker'][move])
        e = edge(atk, dfn)
        # time for THIS rusher to arrive: average matchup ~ BASE_TTT
        # Sensitivity is 0.35, solved. At 1.15 the rating gap swung the clock
        # so hard that an average line against an elite front sacked on 42% of
        # dropbacks; the real spread is roughly 4% to 11%.
        t = RUSHER_BASE * (1.0 - 0.35 * e) * rng.lognormal(0.0, 0.26)
        wins.append((max(0.35, t), move, r, b))

    t_arrive, move, winner, loser = min(wins, key=lambda x: x[0])

    # the QB's own escapability buys time once someone arrives
    if qb is not None:
        t_arrive *= 1.0 + 0.55 * (rate(qb, {'break_sack_rating': .6,
                                            'agility_rating': .25,
                                            'speed_rating': .15}) - AVG)

    pressure = float(np.clip((BASE_TTT - t_arrive) / BASE_TTT, 0.0, 1.0))
    # Sack chance falls off SMOOTHLY with the time available rather than
    # tripping a threshold. A hard cliff meant any matchup whose mean clock sat
    # under the threshold sacked on most dropbacks. Constants solved against the
    # real league: 6.6% average, ~4% behind an elite line, ~11% against an
    # elite front.
    p_sack = 25.0 * np.exp(-2.40 * t_arrive)
    if qb is not None:
        p_sack *= 1.0 - 0.45 * (rate(qb, {'break_sack_rating': 1.0}) - AVG)
    sack = rng.random() < float(np.clip(p_sack, 0.0, 0.85))
    return dict(time=round(float(t_arrive), 2), pressure=round(pressure, 3),
                sack=bool(sack), beaten_by=winner.get('pid'),
                beaten=loser.get('pid') if loser else None, move=move)

# ============================================================ MAN COVERAGE
# The defender watches the RECEIVER, head often turned from the ball. The
# contest is separation, and separation is what the throw is aimed into.
def resolve_man(receiver, defender, depth, time_available, rng):
    """Returns separation 0-1. Higher = more open."""
    rel = edge(rate(receiver, ROUTE['receiver']['release']),
               rate(defender, ROUTE['defender_man']['press']))
    rt = edge(rate(receiver, ROUTE['receiver'][depth]),
              rate(defender, ROUTE['defender_man'][depth]))
    # a release win compounds the longer the route runs
    w = {'short': 0.55, 'medium': 0.40, 'deep': 0.28}[depth]
    sep = 0.42 + 1.30 * (w * rel + (1 - w) * rt)
    # more time on the route means more chance to work open
    sep *= 1.0 + 0.10 * (time_available - BASE_TTT) / BASE_TTT
    return float(np.clip(sep + rng.normal(0, 0.11), 0.02, 0.98))

# ============================================================ THE THROW
def resolve_throw(qb, depth, separation, pressure, rng, on_run=False,
                  play_action=False):
    """
    Accuracy at this depth against the separation actually available.
    Returns completion, interception, or incompletion.
    """
    acc = rate(qb, THROW[depth])
    if pressure > 0:
        up = rate(qb, THROW['under_pressure'])
        acc *= 1.0 - pressure * (0.42 - 0.34 * (up - AVG))
    if on_run:
        acc *= 0.88 + 0.24 * (rate(qb, THROW['on_run']) - AVG)
    if play_action:
        acc *= 1.0 + 0.12 * (rate(qb, THROW['play_action']) - AVG)

    # A deep throw is harder for EVERYONE, not just for a QB with a poor deep
    # accuracy rating. The first build used one depth-independent multiplier, so
    # short, medium and deep all completed at the same rate from the same
    # separation. These are solved so an average QB at league-average separation
    # (0.42) hits the real per-depth rates: 74.4 / 56.0 / 39.4.
    DEPTH_MULT = {'short': 1.77, 'medium': 1.33, 'deep': 0.94}
    p = separation * DEPTH_MULT[depth] * (1.0 + 1.15 * (acc - AVG))
    p = float(np.clip(p, 0.02, 0.97))

    roll = rng.random()
    if roll < p:
        return dict(result='complete', contested=separation < 0.35)
    # a bad throw into tight coverage is where picks come from
    # calibrated to the real 2.1% league interception rate
    p_int = (1.0 - separation) * 0.074 * (1.0 + 2.2 * (AVG - acc))
    if rng.random() < max(0.0, p_int):
        return dict(result='interception', contested=True)
    return dict(result='incomplete', contested=separation < 0.45)

# ============================================================ THE CATCH
def resolve_catch(receiver, defender, contested, rng):
    if not contested:
        # Real drop rates run roughly 2% for the best hands to 8% for the worst.
        # The first build spread them only 95.0 to 96.9 - hands did not matter.
        p = 0.952 + 0.55 * (rate(receiver, CATCH['clean']) - AVG)
    else:
        e = edge(rate(receiver, CATCH['contested']), rate(defender, CATCH['defender']))
        p = 0.50 + 1.10 * e
    return rng.random() < float(np.clip(p, 0.05, 0.995))

# ============================================================ YARDS AFTER
# Shared by yards after catch and by a run that clears the line. Nothing caps
# the yardage: he runs until someone catches him, and the FIELD is the limit.
def resolve_yards_after(carrier, tacklers, yards_to_endzone, rng,
                        already=0.0, contact_at=0.0):
    """
    Walks the carrier through pursuers one at a time. Each is a contest he can
    win; clearing them all is a touchdown from wherever he is.
    """
    gained = contact_at
    elus = rate(carrier, YAC['carrier']['elusive'])
    powr = rate(carrier, YAC['carrier']['power'])
    brk = rate(carrier, YAC['carrier']['breakaway'])
    vis = rate(carrier, YAC['carrier']['vision'])
    broken = 0

    # Each successive defender is HARDER to beat, because the further he runs
    # the better the angles behind him get. Without this ramp a good back beats
    # the two or three men in front of him and is gone, which produced a 30-yard
    # average and a 50% explosive rate against a real 4.52 and 2.46%.
    for i, t in enumerate(tacklers):
        if gained >= yards_to_endzone:
            break
        wrap = rate(t, YAC['tackler']['wrap'])
        atk = max(elus, powr) + 0.30 * (vis - AVG)
        # 0.52 base difficulty puts an average back's break rate near the real
        # ~18%; the ramp adds difficulty for every man already beaten
        p_break = logistic(edge(atk, wrap) - 0.13 - 0.10 * i, k=7.0)
        if rng.random() > p_break:
            gained += max(0.0, rng.normal(0.9, 0.8))          # brought down
            break
        broken += 1
        chase = logistic(edge(brk, rate(t, YAC['tackler']['angle'])), k=5.5)
        gained += max(0.3, rng.gamma(1.7, 1.4 + 4.4 * chase))
    else:
        # Every pursuer beaten. Rare by construction now, and even then the
        # secondary still has to be outrun.
        ang = np.mean([rate(t, YAC['tackler']['angle']) for t in tacklers]) if tacklers else AVG
        chase_all = logistic(edge(brk, ang), k=5.0)
        # Most runs die early; the whole tail lives here. Mean and tail have to
        # be tuned SEPARATELY - raising the break rate lifts both together and
        # cannot hit 4.52 mean with a 2.46% explosive rate at the same time.
        if rng.random() < 0.35 + 0.45 * chase_all:
            gained = yards_to_endzone                          # house call
        else:
            gained += max(1.0, rng.gamma(2.2, 5.0 + 9.0 * chase_all))

    gained = min(gained, yards_to_endzone)
    return dict(yards=round(float(gained), 1), broken_tackles=broken,
                touchdown=gained >= yards_to_endzone)

# ============================================================ RUN PLAY
def resolve_run(carrier, blockers, defenders, yards_to_endzone, rng):
    """
    Blocking produces yards before contact, then the carrier runs the same
    gauntlet as a receiver after the catch.
    """
    n = min(len(blockers), len(defenders))
    wins = []
    for i in range(n):
        b, d = blockers[i], defenders[i]
        pw = rate(b, RUN_BLOCK['blocker']['power'])
        fn = rate(b, RUN_BLOCK['blocker']['finesse'])
        shed = rate(d, RUN_BLOCK['defender']['shed'])
        wins.append(edge(max(pw, fn), shed))
    push = float(np.mean(wins)) if wins else 0.0

    fill = np.mean([rate(d, RUN_BLOCK['defender']['fill']) for d in defenders]) if defenders else AVG
    # yards before contact: average line vs average front ~ 2.1 yards
    ybc = 2.1 + 9.0 * push - 3.2 * (fill - AVG) + rng.normal(0, 1.5)
    ybc = max(-4.0, ybc)

    if ybc < 0:                                  # stuffed behind the line
        return dict(yards=round(float(ybc), 1), broken_tackles=0,
                    touchdown=False, ybc=round(float(ybc), 1))

    # unblocked defenders are the pursuit he still has to beat
    # He faces everyone still on his feet, not just the unblocked leftovers.
    # Passing two or three chasers made breaking into the open trivial.
    chasers = list(defenders[n:]) + list(defenders[:n])
    out = resolve_yards_after(carrier, list(chasers), yards_to_endzone, rng,
                              contact_at=ybc)
    out['ybc'] = round(float(ybc), 1)
    return out

def fumble_chance(carrier, hit_power, rng):
    sec = rate(carrier, BALL_SECURITY)
    p = 0.011 * (1.0 + 2.4 * (AVG - sec)) * (1.0 + 1.3 * (hit_power - AVG))
    return rng.random() < max(0.0, p)

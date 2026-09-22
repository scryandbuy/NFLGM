"""
The matchup map.

Every link in a play's resolution chain is a contest between one player's
attributes and another's. No unit-strength number exists anywhere: each link
pulls only the attributes that matter for THAT contest, weighted for the role,
which is how FM's engine works and why a 16-finishing striker is not
automatically better than a 14 with better movement.

The Madden attribute set turns out to be built for exactly this. The pairs are
almost all explicit: pass_block_power against power_moves, man_cover against
route_run, throw_acc_deep against depth. Where a pairing is not obvious it is
flagged below rather than invented.

WEIGHTS: within a side of a contest, weights sum to 1.0. They are my judgment,
not measured, and they are the first thing to revisit when calibration is off.
"""

# ============================================================ PASS PLAY
# link 1: protection. Five individual matchups, one per lineman, every dropback.
PASS_RUSH = {
    'rusher': {           # what the man rushing brings
        'power':   {'power_moves_rating': .45, 'strength_rating': .30,
                    'block_shed_rating': .25},
        'finesse': {'finesse_moves_rating': .45, 'accel_rating': .25,
                    'agility_rating': .15, 'block_shed_rating': .15},
        'pursuit': {'pursuit_rating': .55, 'speed_rating': .45},
    },
    'blocker': {          # what the man blocking him brings
        'power':   {'pass_block_power_rating': .50, 'strength_rating': .30,
                    'pass_block_rating': .20},
        'finesse': {'pass_block_finesse_rating': .50, 'agility_rating': .25,
                    'pass_block_rating': .25},
    },
    # a rusher picks his move from his own profile; the blocker defends the
    # move he actually gets, which is why a powerful tackle can be beaten
    # by speed and vice versa
    'move_choice': ('power_moves_rating', 'finesse_moves_rating'),
}

# link 2: the route. One matchup per receiver in the pattern.
ROUTE = {
    'receiver': {
        'release': {'release_rating': .55, 'accel_rating': .25, 'agility_rating': .20},
        'short':   {'route_run_short_rating': .55, 'change_of_direction_rating': .25,
                    'agility_rating': .20},
        'medium':  {'route_run_med_rating': .55, 'change_of_direction_rating': .20,
                    'speed_rating': .25},
        'deep':    {'route_run_deep_rating': .45, 'speed_rating': .40,
                    'accel_rating': .15},
    },
    'defender_man': {
        'press':   {'press_rating': .55, 'strength_rating': .25, 'man_cover_rating': .20},
        'short':   {'man_cover_rating': .50, 'change_of_direction_rating': .25,
                    'agility_rating': .25},
        'medium':  {'man_cover_rating': .50, 'speed_rating': .25, 'agility_rating': .25},
        'deep':    {'man_cover_rating': .40, 'speed_rating': .45, 'accel_rating': .15},
    },
    # ZONE: a structurally different contest, not man with a different stat.
    #
    # In man the defender watches the RECEIVER, head often turned away from the
    # ball. In zone he watches the QUARTERBACK - reading the QB is what
    # separates great zone defenders from average ones, and teams play zone
    # specifically to force the QB to make perfect throws through the window.
    # In a true window the receiver is unguarded; if the ball is thrown well
    # enough he simply catches it.
    #
    # So zone resolves in two steps:
    #   1. the coverage structure and the route produce a WINDOW
    #   2. the NEAREST defender to that window contests the THROW, not the man
    # Separation barely matters. Throw quality and the defender's break do.
    'defender_zone': {
        # how fast he reads it and breaks on the ball
        'break':   {'play_rec_rating': .40, 'zone_cover_rating': .35,
                    'awareness_rating': .25},
        # how much ground he covers once he has broken
        'close':   {'speed_rating': .45, 'accel_rating': .35, 'agility_rating': .20},
        # contesting at the catch point
        'contest': {'zone_cover_rating': .45, 'jump_rating': .30, 'tackle_rating': .25},
    },
    # the receiver's only job in zone is finding the soft spot, which is route
    # IQ rather than separation athleticism
    'receiver_zone': {
        'find_window': {'route_run_short_rating': .25, 'route_run_med_rating': .25,
                        'route_run_deep_rating': .20, 'awareness_rating': .30},
    },
}

# link 3: the throw. QB against the separation he actually sees.
THROW = {
    'short':  {'throw_acc_short_rating': .60, 'awareness_rating': .25, 'throw_power_rating': .15},
    'medium': {'throw_acc_mid_rating': .55, 'throw_power_rating': .25, 'awareness_rating': .20},
    'deep':   {'throw_acc_deep_rating': .50, 'throw_power_rating': .35, 'awareness_rating': .15},
    # these MODIFY the above rather than replacing it
    'under_pressure': {'throw_under_pressure_rating': .60, 'break_sack_rating': .40},
    'on_run':         {'throw_on_run_rating': 1.00},
    'play_action':    {'play_action_rating': 1.00},
}

# link 4: the catch, contested or not
CATCH = {
    'clean':     {'catch_rating': .80, 'awareness_rating': .20},
    'contested': {'cit_rating': .50, 'spec_catch_rating': .30, 'jump_rating': .20},
    'defender':  {'man_cover_rating': .40, 'jump_rating': .35, 'press_rating': .25},
}

# link 5: yards after catch. Runs until someone catches him - the FIELD is the
# limit, not a distribution. That is why a 93-yard play is possible from the 7
# and a 30-yard play is the ceiling from the opponent's 30.
YAC = {
    'carrier': {'elusive': {'juke_move_rating': .30, 'agility_rating': .20,
                            'change_of_direction_rating': .15, 'spin_move_rating': .15,
                            'break_tackle_rating': .20},
                'power':   {'truck_rating': .30, 'stiff_arm_rating': .25,
                            'strength_rating': .20, 'break_tackle_rating': .25},
                'breakaway': {'speed_rating': .60, 'accel_rating': .40},
                'vision':  {'bcv_rating': .70, 'awareness_rating': .30}},
    'tackler': {'wrap':    {'tackle_rating': .70, 'pursuit_rating': .30},
                'angle':   {'pursuit_rating': .55, 'speed_rating': .45},
                'impact':  {'hit_power_rating': .60, 'tackle_rating': .40}},
}

# ============================================================ RUN PLAY
RUN_BLOCK = {
    'blocker': {'power':   {'run_block_power_rating': .50, 'strength_rating': .30,
                            'run_block_rating': .20},
                'finesse': {'run_block_finesse_rating': .50, 'agility_rating': .25,
                            'run_block_rating': .25},
                'second':  {'impact_block_rating': .50, 'lead_block_rating': .30,
                            'speed_rating': .20}},
    'defender': {'shed':   {'block_shed_rating': .50, 'strength_rating': .30,
                            'power_moves_rating': .20},
                 'fill':   {'play_rec_rating': .45, 'pursuit_rating': .35,
                            'awareness_rating': .20}},
}
# the ball carrier's contact and breakaway chain is the same as YAC above

# ============================================================ MODIFIERS
# these do not decide a contest, they shift one that is already happening
BALL_SECURITY = {'carry_rating': .70, 'awareness_rating': .30}
DURABILITY    = {'injury_rating': .60, 'tough_rating': .40}
ENDURANCE     = {'stamina_rating': 1.00}
KICKING       = {'accuracy': {'kick_acc_rating': .75, 'awareness_rating': .25},
                 'power':    {'kick_power_rating': 1.00}}
RETURN        = {'kick_ret_rating': .45, 'speed_rating': .30, 'juke_move_rating': .25}

# ============================================================ not used
# src_rating is a provenance flag from the seed build (madden vs generated),
# not a football attribute. Deliberately excluded.
NOT_ATTRIBUTES = {'src_rating'}

def attrs_used():
    """Every attribute this map actually touches, so nothing is silently unused."""
    seen = set()
    def walk(d):
        for k, v in d.items():
            if isinstance(v, dict): walk(v)
            elif isinstance(v, (int, float)) and k.endswith('_rating'): seen.add(k)
            elif isinstance(v, tuple): seen.update(x for x in v if str(x).endswith('_rating'))
    for blk in (PASS_RUSH, ROUTE, THROW, CATCH, YAC, RUN_BLOCK,
                BALL_SECURITY, DURABILITY, ENDURANCE, KICKING, RETURN):
        walk(blk if isinstance(blk, dict) else {})
    return seen


# ============================================================ ZONE RESOLUTION
# Window size by coverage shell and route depth, in "throw difficulty" terms.
# Larger = easier throw. Derived from where each shell is structurally soft:
# Cover 2 has a seam between the two deep safeties and is beaten by corner
# routes and four verticals; Cover 3 has one fewer deep defender's worth of
# width underneath; Cover 0 has no zone at all.
# Windows are anchored to the REAL completion rate at each throw depth
# (74.4% short / 56.0% medium / 39.4% deep, over six seasons), then modulated
# by where each shell is structurally soft. The first build let shell dominate
# and produced deep completions ABOVE short, which is backwards.
ZONE_WINDOW = {
    #            short  medium  deep
    'cover_2':  (0.56,  0.49,   0.39),   # soft in the deep seam
    'cover_3':  (0.61,  0.44,   0.29),   # three deep, soft underneath
    'cover_4':  (0.65,  0.46,   0.23),   # takes away deep, gives up short
    'cover_6':  (0.60,  0.45,   0.31),   # quarter-quarter-half
    'tampa_2':  (0.54,  0.40,   0.33),   # MIKE carries the seam
}
# How many defenders are close enough to contest. A route landing between two
# zones - the seam - is where zone gets beaten, so fewer contesting defenders.
ZONE_DEFENDERS_NEAR = {'cover_2': 1.3, 'cover_3': 1.5, 'cover_4': 1.7,
                       'cover_6': 1.5, 'tampa_2': 1.6}

# The scalar that turns a window into a completion probability. 1.26 was
# solved for an average QB against an average defender on the bench; it is
# now solved inside games, per depth, against the defence as it actually
# calls coverage (see plays.PASS_TRACE and refit_passing.py).
# Per depth because real defenders sit well above the 0.70 centre and the
# squeeze compounds with depth: the mean window after squeeze runs 0.56 short,
# 0.42 medium, 0.28 deep inside games, so one scalar left deep zone at 35%
# against a real ~42 and zone overall 8 points BELOW man.
ZONE_SCALE = {'short': 1.279, 'medium': 1.371, 'deep': 1.397}

# HOW STEEPLY RATINGS MOVE THE WINDOW. Measured inside games by club: the
# defending club's mean window ran sd 0.028 on a mean of 0.42 and completion
# allowed spread 3.5x the real club-to-club figure; the offence's QB accuracy
# slope put completion thrown at 2.2x. Blowouts between a strong roster and a
# weak one are right; a 25-point spread in completion allowed across the
# league is not. Slopes cut to leave the spread a little wider than real,
# not on it: the defence's by ~0.45, the offence's by ~0.6.
ZONE_SLOPE = dict(find=0.30, **{'break': 0.38, 'close': 0.34}, acc=0.70)

def zone_window(shell, depth):
    """Base window for this shell at this route depth. Bigger = easier throw."""
    i = {'short': 0, 'medium': 1, 'deep': 2}[depth]
    return ZONE_WINDOW.get(shell, (0.58, 0.39, 0.27))[i]

def resolve_zone(receiver, defenders, qb, shell, depth, pressure, rng, rate):
    """
    Zone pass resolution. Two steps, as the football describes it:

      1. the shell and the route produce a WINDOW. The receiver's job is only
         to FIND it - route IQ, not separation athleticism.
      2. the NEAREST defender contests the THROW. He must read it (break),
         cover ground (close), then contest at the catch point.

    The QB is the load-bearing party, which is the whole point of zone: it
    forces him to be perfect, and a great one shreds it.

    Returns dict with completion, contested flag, and the window actually left.
    """
    w = zone_window(shell, depth)

    # Contests are resolved RELATIVE TO AVERAGE (0.70 on the 0-1 rating scale),
    # not on the absolute rating. An average defender should leave an average
    # window, not eat 40% of it - the first build squeezed every window by the
    # defender's raw rating and collapsed league completion to the 30s.
    AVG = 0.70

    # 1. does the receiver find the soft spot at all
    find = rate(receiver, ROUTE['receiver_zone']['find_window'])
    w *= 1.0 + ZONE_SLOPE['find'] * (find - AVG)

    # 2. the nearest defender squeezes it. Others are too far to matter, which
    #    is why the seam beats zone.
    near = min(defenders, key=lambda d: d.get('dist_to_window', 99)) if defenders else None
    if near is not None:
        brk = rate(near, ROUTE['defender_zone']['break'])
        cls = rate(near, ROUTE['defender_zone']['close'])
        n = ZONE_DEFENDERS_NEAR.get(shell, 1.5)
        squeeze = (ZONE_SLOPE['break'] * (brk - AVG)
                   + ZONE_SLOPE['close'] * (cls - AVG)) * (n / 1.5)
        w *= 1.0 - squeeze

    w = max(0.04, min(0.97, w))

    # 3. the throw. Accuracy at this depth, degraded by pressure.
    acc = rate(qb, THROW[depth])
    if pressure > 0:
        # a QB with elite under-pressure ability barely degrades; a poor one
        # falls apart. The first build scaled by (1 - ability), which made even
        # heavy pressure worth ~3 points of completion.
        up = rate(qb, THROW['under_pressure'])
        acc *= 1.0 - pressure * (0.42 - 0.34 * (up - AVG))

    # a good enough throw beats the window; a poor one gets contested.
    # 1.26 is solved, not chosen: with the depth-anchored windows above it puts
    # an average QB against an average defender on the real per-depth
    # completion rates (74.4 / 56.0 / 39.4).
    raw = w * (1.0 + ZONE_SLOPE['acc'] * (acc - AVG))
    p_complete = min(0.97, raw * ZONE_SCALE[depth])
    roll = rng.random()
    complete = roll < p_complete
    contested = (not complete) and (roll < p_complete + (1.0 - w) * 0.45)
    return dict(complete=complete, contested=contested, window=round(w, 3),
                p_complete=round(p_complete, 3), raw=raw,
                defender=near.get('pid') if near else None)

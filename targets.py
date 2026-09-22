"""
Targets and depth charts.

TARGETS: a quarterback does not throw to whoever is open. He throws to his
designed read, and openness only sometimes decides it.

  FTN charting, all dropbacks (2023-24):
    first read 53.0%, checkdown 15.2%, designed 11.2%, scramble drill 10.3%,
    second read 10.3%.
    Across 45 QBs the first-read rate runs 43.7% to 66.6%, sd 5.0.

  Outcomes differ sharply BY READ:
    first read    60.7% comp, 10.9 air yards, +0.31 EPA
    second read   53.6% comp, 11.0 air yards, +0.16 EPA
    checkdown     78.1% comp,  0.7 air yards, -0.04 EPA
    designed      83.2% comp, -3.0 air yards, -0.06 EPA
    scramble      29.8% comp, 11.6 air yards,  2.0% INT
  So working deeper into a progression is WORSE, and the checkdown is a
  high-completion negative-value play.

  THE FINDING THAT DRIVES THE DESIGN: research measuring how often a QB throws
  to the most open receiver (by expected completion probability) found the best
  in the league at 26.8% and the worst at 13.2%, while that worst QB threw to
  the LEAST open man 27.5% of the time. With four or five options, random is
  roughly 20-25%. Even elite quarterbacks are barely better than chance at
  finding the most open man, and bad ones are worse than chance.

SEPARATION is anchored to real yards from Next Gen tracking:
  league mean 3.04, sd 0.57, range 1.11 to 5.66. TE 3.35, WR 2.93.
  And it trades against depth: under 2.4 yards of separation catches 57.8% at
  12.8 air yards; over 3.8 catches 73.0% at 6.5 air yards - but yards per
  target is nearly FLAT across the whole range (8.10 down to 7.67). Getting
  open buys completion percentage, not production. Which is why the best
  receivers post LOW separation: they draw better corners and win contested.
"""
import numpy as np

# ============================================================ SEPARATION
SEP_MEAN, SEP_SD = 3.04, 0.57
SEP_MIN, SEP_MAX = 1.11, 5.66
SEP_BY_POS = {'WR': 2.93, 'TE': 3.35, 'HB': 3.6, 'FB': 3.6}

def to_yards(sep01, pos='WR'):
    """Convert the 0-1 matchup output to real yards of separation."""
    base = SEP_BY_POS.get(pos, SEP_MEAN)
    return float(np.clip(base + (sep01 - 0.42) * 3.1, SEP_MIN, SEP_MAX))

def from_yards(yards, pos='WR'):
    base = SEP_BY_POS.get(pos, SEP_MEAN)
    return float(np.clip(0.42 + (yards - base) / 3.1, 0.02, 0.98))


# ============================================================ READ ORDER
# Derived from the concept, not authored play by play. Coaching sources
# describe these as read RULES: flood is high-to-low, smash reads the corner
# then the hitch, mesh is a full-field read.
CONCEPT_READS = {
    'flood':      ['deep', 'medium', 'flat'],      # high to low
    'smash':      ['corner', 'hitch'],
    'levels':     ['deep_in', 'shallow'],
    'dagger':     ['seam', 'dig', 'check'],
    'mesh':       ['cross1', 'cross2', 'sit', 'check'],
    'four_verts': ['seam1', 'seam2', 'outside', 'check'],
    'scissors':   ['post', 'corner'],
    'slant_flat': ['slant', 'flat'],
    'stick':      ['stick', 'flat', 'back'],
    'curl_flat':  ['curl', 'flat', 'check'],
    'screen':     ['screen'],
    'go':         ['go', 'check'],
}

# Real read distribution on dropbacks.
READ_MIX = dict(first=.530, second=.103, checkdown=.152,
                designed=.112, scramble=.103)


def read_profile(qb, rate_fn, AVG=0.70):
    """
    This quarterback's personal read distribution. Anchored to the league
    figures, shifted by awareness and pocket ability within the real observed
    spread (first read 43.7% to 66.6%).
    """
    iq = rate_fn(qb, {'awareness_rating': .55, 'play_rec_rating': .20,
                      'throw_under_pressure_rating': .25})
    mob = rate_fn(qb, {'speed_rating': .5, 'agility_rating': .5})
    m = dict(READ_MIX)
    # a sharper processor gets deeper into the progression and checks down less
    # Real spread across 45 QBs: first read 43.7% to 66.6%, sd 5.0. The first
    # build scaled hard enough to push an elite QB to 40% - below the league
    # MINIMUM - and his designed rate above the league maximum.
    m['first']     = float(np.clip(.530 - 0.28 * (iq - AVG), .437, .666))
    m['second']    = float(np.clip(.103 + 0.20 * (iq - AVG), .058, .163))
    m['checkdown'] = float(np.clip(.152 - 0.18 * (iq - AVG), .087, .208))
    m['scramble']  = float(np.clip(.103 + 0.38 * (mob - AVG), .030, .159))
    m['designed'] = max(0.02, 1.0 - sum(v for k, v in m.items() if k != 'designed'))
    t = sum(m.values())
    return {k: v / t for k, v in m.items()}


def select_target(pairs, qb, concept, rng, rate_fn, plan=None, AVG=0.70):
    """
    Who gets the ball.

    The READ ORDER decides, and openness modifies it. A quarterback locked onto
    his first read throws there whether the man is open or not; a better one
    gets off it. Nothing consults a target-share table at any point - the share
    curve is an OUTCOME of this plus the defence's response to it.

    Returns (receiver, defender, read_kind, separation).
    """
    if not pairs:
        return None, None, 'none', 0.0

    prof = read_profile(qb, rate_fn, AVG)
    kinds = list(prof)
    kind = str(rng.choice(kinds, p=np.array([prof[k] for k in kinds])))

    # THE FIRST READ IS NOT THE SAME MAN EVERY PLAY. Concepts put different
    # receivers first, so the read order is drawn per play with a bias toward
    # the better options. Fixing WR1 as the permanent first read gave him 53%
    # of targets against a real 23.6%.
    n = len(pairs)
    w = np.array([1.0 + 0.55 * (plan.target_priority.get(
        p['receiver'].get('pid'), 0.0) if plan is not None and
        plan.target_priority else 0.0) for p in pairs], float)
    # depth-chart position carries a mild designed bias: a coordinator does
    # build for his best player, but it breaks ties rather than setting a share
    # Real target share by rank: 23.6 / 17.5 / 13.3 / 10.5 / 8.5 - a ratio of
    # about 0.76 between neighbours. A flatter curve produced a near-uniform
    # distribution where the fifth option saw as many balls as the second.
    w *= np.array([0.76 ** i for i in range(n)], float)
    w = w / w.sum()
    order = list(rng.choice(n, size=n, replace=False, p=w))

    if kind == 'checkdown':
        # the back is the usual outlet but not the only one - a tight end or
        # an underneath receiver sits down too. Always taking the last man gave
        # the back 27% of all targets against a real ~10%.
        late = order[-2:] if len(order) > 2 else order
        i = late[int(rng.integers(0, len(late)))]
    elif kind == 'designed':
        i = order[0]
    elif kind == 'second':
        i = order[1] if len(order) > 1 else order[0]
    elif kind == 'scramble':
        i = order[int(rng.integers(0, len(order)))]
    else:                                        # first read
        i = order[0]

    # Openness pulls him off the read - but only a little. Even the best QBs
    # find the most open man barely more often than chance.
    # Even the best QBs find the most open man barely more often than chance:
    # 26.8% for the best in the league, 13.2% for the worst, against a random
    # baseline near 20-25%. So this override must be SMALL and steeply
    # skill-scaled; the first build fired it often enough to hand the most-open
    # receiver 30% of all targets regardless of who was throwing.
    skill = rate_fn(qb, {'awareness_rating': .6, 'play_rec_rating': .4})
    if kind in ('first', 'second') and len(pairs) > 1:
        if rng.random() < float(np.clip(0.04 + 0.85 * (skill - AVG), 0.0, 0.26)):
            seps = [p.get('separation', 0.42) for p in pairs]
            i = int(np.argmax(seps))

    p = pairs[int(i)]
    return p['receiver'], p['defender'], kind, p.get('separation', 0.42)


# Real outcome shift by read kind, used to modify the throw.
READ_MODIFIER = {
    'first':     dict(comp=1.00, air=10.9, epa=+0.31),
    'second':    dict(comp=0.88, air=11.0, epa=+0.16),
    'checkdown': dict(comp=1.29, air=0.7,  epa=-0.04),
    'designed':  dict(comp=1.37, air=-3.0, epa=-0.06),
    'scramble':  dict(comp=0.49, air=11.6, epa= 0.00),
}


# ============================================================ DEPTH CHARTS
# Ordering by POSITION-SPECIFIC rating, not overall. Overall is a blend that
# means little for a slot corner versus a boundary corner.
DEPTH_WEIGHTS = {
    'QB':   {'throw_acc_short_rating': .18, 'throw_acc_mid_rating': .18,
             'throw_acc_deep_rating': .12, 'awareness_rating': .22,
             'throw_power_rating': .10, 'throw_under_pressure_rating': .12,
             'break_sack_rating': .08},
    'HB':   {'break_tackle_rating': .16, 'speed_rating': .18, 'bcv_rating': .16,
             'juke_move_rating': .12, 'carry_rating': .12, 'accel_rating': .14,
             'catch_rating': .06, 'pass_block_rating': .06},
    'WR':   {'route_run_short_rating': .16, 'route_run_med_rating': .16,
             'route_run_deep_rating': .14, 'catch_rating': .16,
             'speed_rating': .16, 'release_rating': .12, 'cit_rating': .10},
    'TE':   {'route_run_short_rating': .16, 'route_run_med_rating': .16,
             'catch_rating': .20, 'run_block_rating': .16,
             'pass_block_rating': .10, 'speed_rating': .12, 'cit_rating': .10},
    'LT':   {'pass_block_finesse_rating': .30, 'pass_block_power_rating': .22,
             'pass_block_rating': .18, 'run_block_rating': .16,
             'agility_rating': .08, 'strength_rating': .06},
    'RT':   {'pass_block_power_rating': .26, 'pass_block_finesse_rating': .22,
             'pass_block_rating': .18, 'run_block_rating': .20,
             'strength_rating': .08, 'agility_rating': .06},
    'LG':   {'run_block_power_rating': .26, 'pass_block_power_rating': .22,
             'run_block_rating': .18, 'pass_block_rating': .16,
             'strength_rating': .12, 'agility_rating': .06},
    'C':    {'awareness_rating': .18, 'run_block_rating': .20,
             'pass_block_rating': .20, 'run_block_power_rating': .16,
             'strength_rating': .14, 'agility_rating': .12},
    'LEDG': {'power_moves_rating': .24, 'finesse_moves_rating': .24,
             'block_shed_rating': .16, 'accel_rating': .14,
             'pursuit_rating': .12, 'strength_rating': .10},
    'DT':   {'power_moves_rating': .24, 'block_shed_rating': .24,
             'strength_rating': .20, 'finesse_moves_rating': .14,
             'tackle_rating': .10, 'pursuit_rating': .08},
    'MIKE': {'play_rec_rating': .22, 'tackle_rating': .20, 'pursuit_rating': .16,
             'zone_cover_rating': .14, 'awareness_rating': .14,
             'block_shed_rating': .14},
    'WILL': {'pursuit_rating': .20, 'speed_rating': .16, 'tackle_rating': .16,
             'man_cover_rating': .16, 'zone_cover_rating': .16,
             'play_rec_rating': .16},
    'CB':   {'man_cover_rating': .26, 'speed_rating': .20, 'zone_cover_rating': .16,
             'press_rating': .14, 'accel_rating': .12,
             'change_of_direction_rating': .12},
    'FS':   {'zone_cover_rating': .24, 'play_rec_rating': .20, 'speed_rating': .18,
             'man_cover_rating': .14, 'awareness_rating': .14,
             'tackle_rating': .10},
    'SS':   {'tackle_rating': .20, 'zone_cover_rating': .20, 'hit_power_rating': .16,
             'play_rec_rating': .16, 'man_cover_rating': .14, 'pursuit_rating': .14},
    'K':    {'kick_acc_rating': .65, 'kick_power_rating': .35},
    'P':    {'kick_power_rating': .60, 'kick_acc_rating': .40},
}
DEPTH_WEIGHTS['RG'] = DEPTH_WEIGHTS['LG']
DEPTH_WEIGHTS['REDG'] = DEPTH_WEIGHTS['LEDG']
DEPTH_WEIGHTS['SAM'] = DEPTH_WEIGHTS['WILL']
DEPTH_WEIGHTS['FB'] = {'run_block_rating': .40, 'lead_block_rating': .30,
                       'impact_block_rating': .20, 'carry_rating': .10}
DEPTH_WEIGHTS['LS'] = {'awareness_rating': 1.0}

# A GM's scheme preference shifts the ordering, which is where gap-versus-zone
# blocking and one-gap-versus-two-gap fronts connect back to roster building.
# Scheme has to be strong enough to actually FLIP an ordering, or it is
# decoration. A zone-blocking team really does prefer the smaller, more agile
# lineman over the mauler; the first build's weights left the mauler on top
# under both schemes, which defeated the point.
SCHEME_SHIFT = {
    'gap':      {'run_block_power_rating': +.26, 'strength_rating': +.16,
                 'run_block_finesse_rating': -.14, 'agility_rating': -.10},
    'zone':     {'run_block_finesse_rating': +.28, 'agility_rating': +.20,
                 'run_block_power_rating': -.16, 'strength_rating': -.12},
    'two_gap':  {'strength_rating': +.24, 'block_shed_rating': +.18,
                 'finesse_moves_rating': -.14, 'accel_rating': -.10},
    'one_gap':  {'accel_rating': +.18, 'finesse_moves_rating': +.24,
                 'strength_rating': -.14},
    'man':      {'man_cover_rating': +.24, 'press_rating': +.18,
                 'zone_cover_rating': -.14},
    'zone_cov': {'zone_cover_rating': +.26, 'play_rec_rating': +.20,
                 'man_cover_rating': -.16},
}

# WHO A SCHEME SHIFT APPLIES TO. A run-blocking scheme grades linemen and
# the men who block for the run, a front grades the men in it, a coverage
# grades the men who cover. Applied to everyone, a zone-blocking shift put
# run-block weights on quarterbacks and receivers (defaulting to 70) and
# graded every starter in the league fifteen points below his rating.
SCHEME_DOMAIN = {
    'gap':      {'LT', 'LG', 'C', 'RG', 'RT', 'TE', 'FB', 'HB'},
    'zone':     {'LT', 'LG', 'C', 'RG', 'RT', 'TE', 'FB', 'HB'},
    'one_gap':  {'LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM'},
    'two_gap':  {'LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM'},
    'man':      {'CB', 'FS', 'SS', 'MIKE', 'WILL', 'SAM'},
    'zone_cov': {'CB', 'FS', 'SS', 'MIKE', 'WILL', 'SAM'},
}


# How hard fit bites on the field. At full strength a 380-pound mauler graded
# ten points under his rating in a zone scheme; real but bounded is a few
# points either way, so a misfit starter still starts and simply plays a
# little under his card.
SCHEME_BITE = 0.5


def position_score(player, position, scheme=None):
    """How good is he AT THIS SPOT, not overall."""
    w = dict(DEPTH_WEIGHTS.get(position, {'awareness_rating': 1.0}))
    if scheme:
        for s in ([scheme] if isinstance(scheme, str) else scheme):
            if position not in SCHEME_DOMAIN.get(s, ()):
                continue
            for k, v in SCHEME_SHIFT.get(s, {}).items():
                # only shift what the spot already weighs; a shift is a
                # lean within his job, not a new job
                if k in w:
                    w[k] = max(0.0, w[k] + v * SCHEME_BITE)
    tot = sum(w.values()) or 1.0
    return sum(player.get(k, 70.0) * v for k, v in w.items()) / tot

def order_depth(players, position, scheme=None, unavailable=None):
    """Rank a position group, dropping anyone unavailable."""
    out = [p for p in players if not unavailable or p.get('pid') not in unavailable]
    return sorted(out, key=lambda p: -position_score(p, position, scheme))

def build_depth_chart(roster, scheme=None, unavailable=None):
    """roster: {position -> [players]}. Returns the same, ordered."""
    return {pos: order_depth(grp, pos, scheme, unavailable)
            for pos, grp in roster.items()}


# ============================================================ PERSONNEL
# Who is ON THE FIELD by package. This is the piece fatigue alone cannot
# produce: five DBs play every snap in nickel, so the top five are all
# starters and the sixth never appears. Real teams sub by package.
OFF_PACKAGES = {
    '11': dict(WR=3, TE=1, HB=1), '12': dict(WR=2, TE=2, HB=1),
    '21': dict(WR=2, TE=1, HB=2), '13': dict(WR=1, TE=3, HB=1),
    '10': dict(WR=4, TE=0, HB=1), '22': dict(WR=1, TE=2, HB=2),
    '00': dict(WR=5, TE=0, HB=0),
}
DEF_PACKAGES = {
    'base':   dict(CB=2, FS=1, SS=1, LB=3, DL=4),
    'nickel': dict(CB=3, FS=1, SS=1, LB=2, DL=4),
    'dime':   dict(CB=4, FS=1, SS=1, LB=1, DL=4),
    'heavy':  dict(CB=2, FS=1, SS=0, LB=4, DL=5),
}

def field_package(chart, package, side='off'):
    """The eleven men this package puts on the field, in depth order."""
    spec = (OFF_PACKAGES if side == 'off' else DEF_PACKAGES).get(package, {})
    out = {}
    for pos, n in spec.items():
        grp = chart.get(pos, [])
        out[pos] = grp[:n]
    return out

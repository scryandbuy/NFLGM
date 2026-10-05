"""
Scrambles, fumbles and penalties.

The baseline outcome distributions below were measured from six seasons of
play-by-play (2020-2025, 281,339 plays, 1,615 games). Quarterback decision
weights are separate football judgments, not measured per-dropback rates.

SCRAMBLES  5.12% of dropbacks (3.87/gm). Mean 7.00 yds, sd 6.07, median 6,
           p10 1, p90 14, max 61. ZERO negative - a scramble is by definition
           a QB who got out. 24.8% go 10+, 4.3% go 20+. EPA +0.402 against
           -1.791 for a sack, so escaping is worth over two EPA.
           48.3% convert a first down.

FUMBLES    1.348% of plays overall (2.28/gm), 0.604% lost (1.02/gm).
           The offence recovers 55.2%. 67.6% of fumbles are forced.
           By play: rush 1.499%, completed pass 1.141%, SACK 12.528%.
           Lost-if-fumbled: run 42.0%, pass 48.3%, punt 35.8%.

PENALTIES  7.03% of plays, 11.88 per game across both teams. Mean 8.30 yards.
           29.9% carry an automatic first down. 56% offence, 44% defence.
"""
import numpy as np

# ============================================================ SCRAMBLES
# Conditional on an imminent sack. Leaving the pocket before the throw is
# a separate decision; do not treat this as a per-dropback scramble rate.
SACK_ESCAPE_BASE = 0.0512
SCRAMBLE = dict(mean=7.00, sd=6.07, median=6, p10=1, p90=14, max=61,
                pct_10plus=0.248, pct_20plus=0.043, first_down_rate=0.483)

def escape_lane_evidence(defense, rush_plan, arrivals, decision_time, rate_fn):
    """Outside escape control from the selected men and their actual jobs.

    Arrival is a proxy for disengagement, not a tracked path or a claim that
    every fast rush maintains contain. Dropped edges use their coverage side.
    No extra random draw and no off-field players enter the decision.
    """
    import defensive_rush as DR
    rushing = {DR.player_key(a['player']): a for a in rush_plan['assignments']}
    covering = {DR.player_key(a['player']): a
                for a in rush_plan['coverage'].get('defensive_assignments', [])}
    arrival_by = dict(arrivals)
    lanes = {'left': [], 'right': []}
    for a in DR.assignments(defense):
        if a['alignment'] not in DR.EDGES:
            continue
        p = a['player']; key = DR.player_key(p)
        job = rushing.get(key) or covering.get(key)
        if job is None:
            continue
        side = 'right' if 'right' in job['alignment'] else 'left' if 'left' in job['alignment'] else None
        if side is None:
            continue  # A middle drop does not own both outside lanes.
        arrival = arrival_by.get(p.get('pid'))
        available = (float(np.clip(decision_time + .5 - arrival, 0., 1.))
                     if key in rushing and arrival is not None else 0. if key in rushing else 1.)
        grade = rate_fn(p, {'pursuit_rating': .4, 'play_rec_rating': .3,
                            'speed_rating': .2, 'accel_rating': .1})
        lanes[side].append(dict(pid=p.get('pid'), grade=float(grade), available=available))
    return lanes


def escape_lane_factor(mobility, lanes):
    if lanes is None:
        return 1.  # Legacy/direct callers without assignment evidence.
    factors = []
    for side in ('left', 'right'):
        threats = lanes.get(side, [])
        # The QB may choose the less controlled side; one good edge cannot
        # seal the entire pocket. Keep pursuit effects bounded and probabilistic.
        # An open lane is already allowed by the underlying scramble choice;
        # do not add a second bonus simply because an edge remains blocked.
        factors.append(min((float(np.clip(1. - 1.8 * (d['grade'] - mobility) * d['available'], .65, 1.2))
                            for d in threats), default=1.))
    return max(factors)


def scramble_chance(qb, pressure, time_available, rate_fn, AVG=0.70, *, escape_lanes=None):
    """
    A scramble is what a mobile QB does INSTEAD of taking the sack. Without it
    every collapsed pocket becomes a sack regardless of who is playing.
    Conditional escape chance; mobility and pressure both move it.
    """
    mob = rate_fn(qb, {'speed_rating': .40, 'agility_rating': .30,
                       'accel_rating': .15, 'break_sack_rating': .15})
    p = SACK_ESCAPE_BASE * (1.0 + 3.2 * (mob - AVG))
    p *= 0.55 + 1.30 * pressure          # he scrambles because he has to
    p *= escape_lane_factor(mob, escape_lanes)
    return float(np.clip(p, 0.0, 0.42))

def pocket_run_chance(qb, defenders, rate_fn, *, separation, pressure,
                      read='first', screen=False, hot=False, swing=False,
                      time_available=2.5, down=1, distance=10, seconds=None,
                      margin=0, aggression=.5, man=False, escape_lanes=None):
    """Choose a run after reading coverage, before resolving any throw.

    Public movement ratings describe whether running is a useful alternative.
    The read and actual pursuit make that alternative more or less attractive.
    These are conditional decision weights, not a target league scramble rate.
    """
    if screen or hot or swing or time_available < 1.6:
        return 0.
    if separation >= .8 and pressure < .35 and read == 'first':
        return 0.  # Take the clearly open scheduled throw.
    mobility = rate_fn(qb, {'speed_rating': .40, 'agility_rating': .30,
                            'accel_rating': .15, 'break_sack_rating': .15})
    athlete = float(np.clip((mobility - .55) / .4, 0., 1.))
    willingness = .012 + .16 * athlete * athlete
    window = float(np.clip(1. - .85 * separation, .12, 1.))
    if read != 'first': window = min(1., window + .15)
    pressure_pull = 1. + min(.7, max(0., pressure))
    # Zone defenders looking into the backfield can close a lane. Man
    # defenders following receivers are less ready, but still have pursuit.
    support = [d for d in defenders if d.get('pos') in ('MIKE', 'WILL', 'SAM', 'CB', 'SS', 'FS')]
    pursuit = float(np.mean([rate_fn(d, {'pursuit_rating': .4, 'speed_rating': .3,
                                       'awareness_rating': .3}) for d in support])) if support else .70
    lane = float(np.clip(1. - 1.8 * (pursuit - mobility) - .035 * max(0, len(support) - 4), .35, 1.35))
    if man: lane = min(1.4, lane * 1.15)
    choice = willingness * window * pressure_pull * lane * (.8 + .4 * float(np.clip(aggression, 0., 1.)))
    choice *= escape_lane_factor(mobility, escape_lanes)
    if down == 4 and distance > 5:
        choice *= max(.12, 5. / distance)  # Running short also loses the ball.
    if seconds is not None and seconds <= 20 and margin <= 0:
        choice *= .12  # Preserve time for a scoring throw or a kick.
    return float(np.clip(choice, 0., .32))


def resolve_scramble(qb, tacklers, yards_to_endzone, rng, rate_fn, AVG=0.70):
    """
    Gamma-shaped to match the real distribution: mean 7.00, sd 6.07, median 6,
    right tail to 61. A scramble is never negative in the data.
    """
    mob = rate_fn(qb, {'speed_rating': .45, 'accel_rating': .30,
                       'agility_rating': .25})
    # shape/scale solved against mean 7.00 / sd 6.07
    shape, scale = 1.33, 5.26
    y = rng.gamma(shape, scale) * (1.0 + 0.85 * (mob - AVG))
    # Escaping the pocket does not also beat the pursuit. Use the selected
    # on-field defenders, with no extra roll and neutral legacy context.
    unique = {p.get('pid', id(p)): p for p in tacklers if p}
    if unique:
        chase = float(np.mean([rate_fn(p, {'pursuit_rating': .40,
                               'speed_rating': .30, 'tackle_rating': .30})
                               for p in unique.values()]))
        y *= float(np.clip(1.0 - .40 * (chase - AVG), .85, 1.20))
    y = float(np.clip(y, 0.0, min(yards_to_endzone, SCRAMBLE['max'])))
    return dict(type='scramble', yards=round(y, 1),
                touchdown=y >= yards_to_endzone, by=qb.get('pid'))

# ============================================================ FUMBLES
# Rates per play by event type, straight from the data.
FUMBLE_RATE = {'run': 0.01499, 'complete_pass': 0.01141, 'sack': 0.12528,
               'scramble': 0.01499, 'punt_return': 0.03059, 'kick_return': 0.00684}
# Share LOST once fumbled, by event type.
FUMBLE_LOST = {'run': 0.420, 'complete_pass': 0.483, 'sack': 0.483,
               'scramble': 0.420, 'punt_return': 0.358, 'kick_return': 0.487}
FORCED_SHARE = 0.676             # 67.6% of fumbles are forced, not muffed

def fumble_check(carrier, event, rng, rate_fn, hit_power=0.70, AVG=0.70, env_mult=1.0, rate_mult=1.0):
    """
    Ball security against the hit. A sack fumbles at 12.5% - eight times the
    rate of a run - which is what makes a strip sack its own event.
    rate_mult scales the chance of the ball coming out at all (a Disciplinarian's unit: 0.9).
    env_mult describes wet-ball handling risk, not a recovery advantage for
    either team. Apply it once, when the ball comes loose.
    """
    base = FUMBLE_RATE.get(event, 0.0140)
    sec = rate_fn(carrier, {'carry_rating': .70, 'awareness_rating': .30})
    p = base * (1.0 + 2.4 * (AVG - sec)) * (1.0 + 1.3 * (hit_power - AVG)) * rate_mult * env_mult
    if rng.random() >= max(0.0, p):
        return None
    lost = rng.random() < FUMBLE_LOST.get(event, 0.45)
    return dict(fumble=True, lost=bool(lost),
                forced=rng.random() < FORCED_SHARE, by=carrier.get('pid'))

# ============================================================ PENALTIES
# Per game across BOTH teams, with mean yardage and automatic-first-down share.
# Sorted by frequency; these 20 cover the overwhelming majority.
PENALTIES = [
    # name,                            per_game, yards, auto_1st, on_offense, phase
    ('Offensive Holding',                 2.243,   9.6, 0.00, True,  'any'),
    ('False Start',                       2.228,   4.9, 0.00, True,  'pre'),
    ('Defensive Pass Interference',       1.045,  15.8, 0.99, False, 'pass'),
    ('Defensive Holding',                 0.658,   4.7, 0.99, False, 'any'),
    ('Unnecessary Roughness',             0.610,  13.1, 0.65, None,  'post'),
    ('Delay of Game',                     0.581,   4.9, 0.00, True,  'pre'),
    ('Defensive Offside',                 0.544,   4.8, 0.18, False, 'pre'),
    ('Roughing the Passer',               0.399,  13.2, 0.96, False, 'pass'),
    ('Neutral Zone Infraction',           0.376,   4.8, 0.25, False, 'pre'),
    ('Face Mask',                         0.294,  13.5, 0.69, None,  'any'),
    ('Illegal Formation',                 0.283,   4.9, 0.00, True,  'any'),
    ('Offensive Pass Interference',       0.256,   9.7, 0.00, True,  'pass'),
    ('Illegal Contact',                   0.241,   4.9, 1.00, False, 'pass'),
    ('Illegal Block Above the Waist',     0.226,   9.3, 0.00, True,  'any'),
    ('Illegal Use of Hands',              0.223,   6.0, 0.74, None,  'any'),
    ('Ineligible Downfield Pass',         0.193,   4.9, 0.00, True,  'pass'),
    ('Intentional Grounding',             0.161,  11.5, 0.00, True,  'pass'),
    ('Defensive Too Many Men on Field',   0.137,   4.4, 0.24, False, 'pre'),
    # Rule 7-4-7: ordinary shifts are live-ball fouls, on runs or passes.
    # The separate not-all-set/running-clock exception after the two-minute
    # warning is a False Start (7-4-2 Item 6), not every late illegal shift.
    ('Illegal Shift',                     0.136,   4.9, 0.00, True,  'any'),
    ('Encroachment',                      0.128,   4.7, 0.28, False, 'pre'),
]
PENALTIES_PER_GAME = 11.88
PLAYS_PER_GAME = 169.0           # all plays including ST, from the same data
PENALTY_RATE = 0.0703            # of plays, kept for reference; see penalty_check
SCRIMMAGE_PLAYS_PER_GAME = 123.95   # what this engine counts (the register's own figure)
PASS_PLAYS_PER_GAME = 123.95 * 0.578

_names = [p[0] for p in PENALTIES]
_rates = np.array([p[1] for p in PENALTIES], float)
_p = _rates / _rates.sum()
PEN_INFO = {p[0]: dict(yards=p[2], auto_first=p[3], offense=p[4], phase=p[5])
            for p in PENALTIES}

# the rulebook: enforcement yardage by foul (Rule 12 and 7; DPI is a spot foul and drawn separately)
RULE_YARDS = {'Offensive Holding': 10, 'False Start': 5, 'Defensive Holding': 5, 'Unnecessary Roughness': 15, 'Delay of Game': 5, 'Defensive Offside': 5,
              'Roughing the Passer': 15, 'Neutral Zone Infraction': 5, 'Face Mask': 15, 'Illegal Formation': 5, 'Offensive Pass Interference': 10, 'Illegal Contact': 5,
              'Illegal Block Above the Waist': 10, 'Illegal Use of Hands': 10, 'Ineligible Downfield Pass': 5, 'Intentional Grounding': 10,
              'Defensive Too Many Men on Field': 5, 'Illegal Shift': 5, 'Encroachment': 5}

# Defensive pass interference is a SPOT foul and the biggest single swing in
# the game: mean 15.3, median 13, p90 30, p99 46, max 52. 28% go 20+ yards.
DPI = dict(mean=15.3, median=13, p75=21, p90=30, p99=46, max=52,
           pct_20plus=0.280, pct_40plus=0.034)

def dpi_yards(rng, air_yards=None):
    """Spot foul: the yardage IS roughly where the ball was going."""
    if air_yards is not None:
        return float(np.clip(abs(air_yards) + rng.normal(0, 2.5), 1, DPI['max']))
    # lognormal solved against median 13 / p90 30 / max 52
    return float(np.clip(rng.lognormal(np.log(13.0), 0.62), 1, DPI['max']))

def penalty_check(rng, phase='any', is_pass=True, discipline=0.70, AVG=0.70,
                  air_yards=None, noise=1.0, hurry=False, *,
                  offense_discipline=None, defense_discipline=None,
                  offense_multiplier=1.0, defense_multiplier=1.0,
                  offense_players=(), defense_players=(), outcome=None, timing=None):
    """
    Returns a penalty or None. discipline is the offending unit's rating on
    0-1; the league rate of 7.03% of plays sits at average discipline.
    Explicit unit ratings and staff multipliers apply by offending side.
    The legacy discipline argument supplies both when they are omitted.
    """
    # EACH FOUL AT ITS OWN PER-PLAY RATE. The old draw rolled one flat 7.03%
    # (a rate quoted per play INCLUDING special teams, applied to scrimmage
    # snaps only) and then picked a type by its share of all penalties. A
    # pass-only foul was spread over every snap and then filtered off the
    # runs, so interference came out at 0.48 a game against a real 1.05 and
    # the whole book ran 9 a game against 11.9. Now a foul that can only
    # happen on a pass is rated per pass play, the rest per scrimmage play,
    # and the chance of ANY flag is the sum of what is eligible on this snap.
    if phase == 'any':
        ok = [i for i, n in enumerate(_names)
              if n != 'Intentional Grounding' and (PEN_INFO[n]['phase'] != 'pass' or is_pass)]
    else:
        ok = [i for i, n in enumerate(_names)
              if PEN_INFO[n]['phase'] in ('any', 'post', phase)
              or (PEN_INFO[n]['phase'] == 'pass' and is_pass)]
    if not ok: return None
    per_play = np.array([_rates[i] / (PASS_PLAYS_PER_GAME
                                      if PEN_INFO[_names[i]]['phase'] == 'pass'
                                      else SCRIMMAGE_PLAYS_PER_GAME) for i in ok])
    # the crowd: the road offence's false starts and delays run at the
    # building's noise multiplier (Kansas City, Seattle and New Orleans ~1.35)
    if noise != 1.0:
        for k, i in enumerate(ok):
            if _names[i] in ('False Start', 'Delay of Game'):
                per_play[k] *= noise
    if hurry:
        # A DRILL DOES NOT TAKE A DELAY. An offense racing the clock snaps the ball the moment it is set; the
        # delay of game is the huddle offense's foul. It had been drawn at the league rate on every snap, so a
        # club down eleven with 48 seconds lost 23 of them to one on its first snap.
        for k, i in enumerate(ok):
            if _names[i] == 'Delay of Game':
                per_play[k] = 0.0
    off_rating = discipline if offense_discipline is None else offense_discipline
    def_rating = discipline if defense_discipline is None else defense_discipline
    off_factor = max(0.0, (1 + 1.6 * (AVG - off_rating)) * offense_multiplier)
    def_factor = max(0.0, (1 + 1.6 * (AVG - def_rating)) * defense_multiplier)
    import penalty_players as PP
    profiles, factors = {}, {}
    for k, i in enumerate(ok):
        name = _names[i]
        side = PEN_INFO[name]['offense']
        if timing == 'pre' and PEN_INFO[name]['phase'] != 'pre':
            per_play[k] = 0.
            continue
        pair = []
        for on_off, rows, base in ((True, offense_players, off_factor), (False, defense_players, def_factor)):
            if side is not None and side != on_off:
                pair.append(0.)
                continue
            prof = profiles[name, on_off] = PP.profile(name, rows, outcome)
            eligible = bool(prof) or not rows or name in PP.TEAM_FOULS
            pair.append(base * PP.factor(prof) if eligible else 0.)
        factors[name] = pair
        per_play[k] *= pair[0] if side is True else pair[1] if side is False else .18 * pair[0] + .82 * pair[1]
    # Split pre-snap/live checks without increasing the marginal flag rate.
    # The live check only runs after surviving the pre-snap check.
    pre = np.array([PEN_INFO[_names[i]]['phase'] == 'pre' for i in ok])
    if timing == 'live':
        survived = max(.01, 1. - float(per_play[pre].sum()))
        per_play[pre] = 0.
        per_play /= survived
    elif timing == 'pre':
        per_play[~pre] = 0.
    p = per_play.sum()
    if rng.random() >= max(0.0, p):
        return None
    name = _names[int(rng.choice(ok, p=per_play / per_play.sum()))]
    info = PEN_INFO[name]

    if name == 'Defensive Pass Interference':
        yds = float(round(dpi_yards(rng, air_yards)))       # a spot foul lands on a yard line
    else:
        # THE RULEBOOK'S YARDAGE, not a draw around the average: five, ten or fifteen by foul.
        # Half the distance to the goal is applied where the ball is, in the game.
        yds = float(RULE_YARDS.get(name, round(info['yards'] / 5.0) * 5.0 or 5.0))

    on_off = info['offense']
    if on_off is None:                     # can be either side
        # The 56/44 league split is across ALL penalties. The 20 types modelled
        # here already resolve to 6.31/gm offence and 3.53/gm defence, which is
        # 57.5% offence before the either-side fouls are assigned at all - so no
        # value here reaches exactly 56%. The gap is the untracked long tail
        # (the 20 types cover 10.96 of the real 11.88 per game), which skews
        # defensive. These specific fouls go against the defence more often.
        off_factor, def_factor = factors[name]
        either_factor = .18 * off_factor + .82 * def_factor
        on_off = rng.random() < (.18 * off_factor / either_factor if either_factor else .18)
    if name == 'Illegal Use of Hands' and not on_off:
        yds = 5.0                         # defensive use of hands is five, offensive is ten
    # the rulebook's automatic first down: every defensive foul except the pre-snap fives
    # (offside, neutral zone, encroachment, too many men) and delay-type fouls; never an offensive foul
    AUTO = {'Defensive Pass Interference', 'Defensive Holding', 'Roughing the Passer', 'Illegal Contact', 'Unnecessary Roughness', 'Face Mask', 'Illegal Use of Hands'}
    flag = dict(penalty=name, yards=float(int(round(float(yds)))), rule_yards=float(yds),
                on_offense=bool(on_off),
                auto_first=(not on_off) and (name in AUTO),
                # only a dead-ball, pre-snap foul is decided before the snap; holding, OPI, an ineligible man downfield
                # and a block above the waist happen DURING the play, which runs and is then wiped in the book
                nullifies=info['phase'] in ('pre',))
    return PP.attribute(flag, profiles[name, bool(on_off)], rng) if offense_players or defense_players else flag


def contextual_penalty(pen, out, call, rng, offense_players=(), defense_players=()):
    """Keep the rolled flag and offending side, but require a possible live foul.

    Missing evidence in legacy/custom resolvers retains the prior eligibility.
    No extra flag chance and no cooldown suppressing consecutive penalties.
    """
    if pen is None or pen.get('nullifies') or pen['penalty'] == 'Intentional Grounding':
        return pen
    kind = out.get('type')
    released = kind in ('complete', 'incomplete', 'drop', 'interception')
    contact = kind in ('run', 'complete', 'sack', 'scramble')
    def allowed(name):
        if name == 'Roughing the Passer':
            return released and not out.get('throwaway') and out.get('pressured', True)
        if name in ('Defensive Pass Interference', 'Offensive Pass Interference', 'Ineligible Downfield Pass'):
            return released and not out.get('throwaway') and (name != 'Defensive Pass Interference' or float(out.get('air', 1) or 0) > 0)
        if name == 'Face Mask':
            return contact
        return True
    if allowed(pen['penalty']):
        return pen
    side = pen['on_offense']
    candidates = [(name, rate * (.18 if side else .82) if owner is None else rate)
                  for name, rate, _, _, owner, phase in PENALTIES
                  if phase != 'pre' and name != 'Intentional Grounding'
                  and (owner is None or owner == side)
                  and (phase != 'pass' or call.get('is_pass')) and allowed(name)]
    import penalty_players as PP
    rows = offense_players if side else defense_players
    profiles = {name: PP.profile(name, rows, out) for name, _ in candidates}
    candidates = [(name, w * PP.factor(profiles[name])) for name, w in candidates
                  if not rows or profiles[name] or name in PP.TEAM_FOULS]
    if not candidates: return None
    weights = np.array([w for _, w in candidates], float)
    name = candidates[int(rng.choice(len(candidates), p=weights/weights.sum()))][0]
    yards = (dpi_yards(rng, out.get('air')) if name == 'Defensive Pass Interference'
             else 5 if name == 'Illegal Use of Hands' and not side else RULE_YARDS[name])
    flag = dict(pen, penalty=name, yards=float(round(yards)), rule_yards=float(round(yards)),
                auto_first=not side, context_adjusted=True)
    return PP.attribute(flag, profiles[name], rng) if rows else flag


def special_teams_penalty_check(rng, kind, returned=False, phase=None,
                                offense_players=(), defense_players=()):
    """Flags on kick snaps and returns, where the scrimmage foul draw does not run."""
    table = {
        'punt': [('False Start', .012, True, 'pre', 5, False),
                 ('Defensive Offside', .006, False, 'kick_offside', 5, False),
                 ('Roughing the Kicker', .004, False, 'kick', 15, True)],
        'field_goal': [('False Start', .010, True, 'pre', 5, False),
                       ('Defensive Offside', .006, False, 'kick_offside', 5, False),
                       ('Roughing the Kicker', .004, False, 'kick', 15, True)],
        'extra_point': [('False Start', .008, True, 'pre', 5, False),
                        ('Defensive Offside', .004, False, 'kick_offside', 5, False)],
        'kickoff': [('Illegal Block in Back', .018, True, 'return', 10, False)] if returned else [],
        'two_point': [('False Start', .012, True, 'pre', 5, False),
                      ('Defensive Offside', .008, False, 'kick_offside', 5, False)],
    }.get(kind, [])
    if kind == 'punt' and returned:
        table.append(('Return Holding', .025, False, 'return', 10, False))
    if phase is not None:
        table = [entry for entry in table if entry[3] == phase]
    roll = rng.random()
    import penalty_players as PP
    for name, chance, on_offense, phase, yards, auto_first in table:
        rows = offense_players if on_offense else defense_players
        profile = PP.profile(name, rows)
        chance *= PP.factor(profile)
        if rows and not profile and name not in PP.TEAM_FOULS: chance = 0.
        if roll < chance:
            flag = dict(penalty=name, yards=float(yards), rule_yards=float(yards),
                        on_offense=on_offense, phase=phase, auto_first=auto_first,
                        nullifies=phase == 'pre')
            return PP.attribute(flag, profile, rng) if rows else flag
        roll -= chance
    return None

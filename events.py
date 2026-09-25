"""
Scrambles, fumbles and penalties.

Every rate, distribution and yardage figure here is computed from six seasons of
real play-by-play (2020-2025, 281,339 plays, 1,615 games). Nothing is assumed.

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
SCRAMBLE_RATE_BASE = 0.0512      # of dropbacks, league-wide
SCRAMBLE = dict(mean=7.00, sd=6.07, median=6, p10=1, p90=14, max=61,
                pct_10plus=0.248, pct_20plus=0.043, first_down_rate=0.483)

def scramble_chance(qb, pressure, time_available, rate_fn, AVG=0.70):
    """
    A scramble is what a mobile QB does INSTEAD of taking the sack. Without it
    every collapsed pocket becomes a sack regardless of who is playing.
    League base is 5.12% of dropbacks; mobility and pressure both move it.
    """
    mob = rate_fn(qb, {'speed_rating': .40, 'agility_rating': .30,
                       'accel_rating': .15, 'break_sack_rating': .15})
    p = SCRAMBLE_RATE_BASE * (1.0 + 3.2 * (mob - AVG))
    p *= 0.55 + 1.30 * pressure          # he scrambles because he has to
    return float(np.clip(p, 0.0, 0.42))

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
    """
    base = FUMBLE_RATE.get(event, 0.0140)
    sec = rate_fn(carrier, {'carry_rating': .70, 'awareness_rating': .30})
    p = base * (1.0 + 2.4 * (AVG - sec)) * (1.0 + 1.3 * (hit_power - AVG)) * rate_mult
    if rng.random() >= max(0.0, p):
        return None
    lost = rng.random() * (1.0 / env_mult) < FUMBLE_LOST.get(event, 0.45)
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
    ('Illegal Formation',                 0.283,   4.9, 0.00, True,  'pre'),
    ('Offensive Pass Interference',       0.256,   9.7, 0.00, True,  'pass'),
    ('Illegal Contact',                   0.241,   4.9, 1.00, False, 'pass'),
    ('Illegal Block Above the Waist',     0.226,   9.3, 0.00, True,  'any'),
    ('Illegal Use of Hands',              0.223,   6.0, 0.74, None,  'any'),
    ('Ineligible Downfield Pass',         0.193,   4.9, 0.00, True,  'pass'),
    ('Intentional Grounding',             0.161,  11.5, 0.00, True,  'pass'),
    ('Defensive Too Many Men on Field',   0.137,   4.4, 0.24, False, 'pre'),
    ('Illegal Shift',                     0.136,   4.9, 0.00, True,  'pre'),
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
                  air_yards=None, noise=1.0):
    """
    Returns a penalty or None. discipline is the offending unit's rating on
    0-1; the league rate of 7.03% of plays sits at average discipline.
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
              if PEN_INFO[n]['phase'] != 'pass' or is_pass]
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
    p = per_play.sum() * (1.0 + 1.6 * (AVG - discipline))
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
        on_off = rng.random() < 0.18
    # the rulebook's automatic first down: every defensive foul except the pre-snap fives
    # (offside, neutral zone, encroachment, too many men) and delay-type fouls; never an offensive foul
    AUTO = {'Defensive Pass Interference', 'Defensive Holding', 'Roughing the Passer', 'Illegal Contact', 'Unnecessary Roughness', 'Face Mask', 'Illegal Use of Hands'}
    return dict(penalty=name, yards=round(float(yds), 1),
                on_offense=bool(on_off),
                auto_first=(not on_off) and (name in AUTO),
                nullifies=info['phase'] in ('pre',) or name in
                          ('Offensive Holding', 'Offensive Pass Interference',
                           'Illegal Formation', 'Ineligible Downfield Pass',
                           'Illegal Block Above the Waist'))

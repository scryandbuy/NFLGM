"""
The game loop.

Wraps play resolution into drives, downs, field position and a clock. This is
the gate on fatigue, injuries and stat attribution - none of them mean anything
without games.

Every constant is computed from real play-by-play (2020-2025 for most, 2025
alone for kickoffs because the rules changed).

  DRIVES        21.73 per game, 5.96 plays each, 1.84 first downs each
  OUTCOMES      punt 35.18%, TD 22.60%, FG 15.35%, turnover 10.23%,
                end of half 7.03%, downs 5.60%, missed FG 2.66%,
                opp TD 1.11%, safety 0.25%
  PLAYS         123.0 offensive per game, 172.9 including special teams
  CLOCK         pass 23.2s (complete 31.4, incomplete 10.2), run 34.7s,
                punt 9.4s, FG 4.0s, kickoff 5.8s
  FOURTH DOWN   14.12 per game; go-for-it and conversion tables below
  FIELD GOALS   overall 85.0%, 3.91 attempts per game
  PUNTS         7.65 per game, 47.2 gross (sd 9.8), 7.5% touchback,
                returned on 35%, mean return 4.23
  KICKOFFS      2025 rules: 20.7% touchback, returned on 73.9%, 26.1 avg
"""
import numpy as np
import weather as W
ENV = W.CLEAR

# ============================================================ CLOCK
SEC = {'complete': 32.6, 'incomplete': 10.2, 'run': 36.0, 'sack': 31.2,      # re-centered once a touchdown stopped the clock at the whistle (it had been charged a full play's runoff)
       'scramble': 36.0, 'punt': 9.4, 'field_goal': 4.0, 'kickoff': 5.8,
       'penalty': 14.4, 'interception': 12.0, 'drop': 10.2, 'fumble': 12.0}
QUARTER = 900
HALF = 1800
GAME = 3600

def play_seconds(result, clock_stopped=False, hurry=False, timeout=False, tempo=0.5):
    s = SEC.get(result, 25.0)
    if clock_stopped: s = min(s, 8.0)
    if not clock_stopped and not hurry and not timeout and result in ('complete', 'run', 'scramble', 'sack'):
        s = 6.0 + max(0.0, s - 6.0) * (1.0 - 0.6 * (float(np.clip(tempo, 0, 1)) - 0.5))
    if hurry: s *= 0.65     # a two-minute drill runs about 17 seconds a snap against 25 to 27 at the normal pace
    if timeout: s = min(s, 6.0)     # the clock stops the moment it is called
    return float(s)


# ============================================================ TIMEOUTS
# Three a half, each. Every published win-probability model uses them and this
# engine tracked none, so both sides were assumed to hold all three forever -
# which makes a two-minute drill far too easy and a defensive stop far too
# cheap.
#
# Who spends them, and why: the DEFENCE burns them when it is behind and needs
# the ball back, which is the only reason a defence ever calls one late. The
# OFFENCE spends them driving at the end of a half, to stop a clock that the
# play itself did not stop. Nobody spends one in the first quarter.
TIMEOUTS_PER_HALF = 3


class Timeouts:
    """Three a half each. Who has them left is real state, not an assumption."""

    def __init__(self):
        self.left = {'home': TIMEOUTS_PER_HALF, 'away': TIMEOUTS_PER_HALF}

    def halftime(self):
        self.left = {'home': TIMEOUTS_PER_HALF, 'away': TIMEOUTS_PER_HALF}

    def use(self, side):
        if self.left.get(side, 0) <= 0:
            return False
        self.left[side] -= 1
        return True

    def edge(self, side):
        """Timeout advantage for this side - the feature the model wants."""
        other = 'away' if side == 'home' else 'home'
        return self.left.get(side, 0) - self.left.get(other, 0)

    def __repr__(self):
        return f"<TO home {self.left['home']} away {self.left['away']}>"

# ============================================================ FOURTH DOWN
# Real go-for-it rate by distance and field zone.
GO_RATE = {
    #            FG range  midfield  own 30-50  backed up
    '1':   dict(fg_range=.825, midfield=.920, own=.534, backed=.211),
    '2':   dict(fg_range=.506, midfield=.705, own=.199, backed=.101),
    '3-4': dict(fg_range=.268, midfield=.496, own=.107, backed=.067),
    '5-7': dict(fg_range=.120, midfield=.236, own=.083, backed=.048),
    '8+':  dict(fg_range=.085, midfield=.116, own=.073, backed=.040),
}
FOURTH_CONV = {'1': .675, '2': .588, '3-4': .510, '5-7': .442, '8+': .247}

def fourth_band(ydstogo):
    if ydstogo <= 1: return '1'
    if ydstogo <= 2: return '2'
    if ydstogo <= 4: return '3-4'
    if ydstogo <= 7: return '5-7'
    return '8+'

def fourth_zone(yardline_100):
    """yardline_100 = yards to the opponent's end zone."""
    if yardline_100 <= 35: return 'fg_range'
    if yardline_100 <= 50: return 'midfield'
    if yardline_100 <= 70: return 'own'
    return 'backed'

def fourth_down_decision(yardline_100, ydstogo, score_diff, secs_left, rng,
                         aggression=0.5, timeout_edge=0, use_wp=True,
                         kicker=None, rate_fn=None):
    """
    go, field_goal or punt.

    THE AI HAS A SAY, NOT A RULE. The win-probability model produces an edge (going against the best
    alternative); that edge becomes a PROBABILITY of going, shifted by the coach's aggression, and is blended
    half and half with what clubs actually do in that spot (GO_RATE by distance and zone). So fourth and one
    from the own 30 is a lean, fourth and three from the own 45 in the first quarter is a long shot, fourth
    and one at midfield is nearly always, and fourth and goal from the 2 down seventeen is always. No zone is
    a rule. The field goal is taken only when three points change the number of scores the club still needs.
    """
    import decisions as DEC
    distance = yardline_100 + 17
    kick_chance = fg_probability(distance, kicker, rate_fn)
    kick_chance *= ENV.kick_mult if distance >= 35 else 1.0 - 0.3 * (1.0 - ENV.kick_mult)
    minimum = 0.42 if secs_left > 300 or score_diff >= 0 else 0.25
    if secs_left < 20: minimum = min(minimum, 0.20)
    in_range = kick_chance >= minimum
    # With time for one play, a reachable kick ties or wins. The general
    # desperation rule must not force a conversion that leaves no clock.
    if secs_left <= 6 and -3 <= score_diff <= 0 and in_range:
        return 'field_goal'
    if secs_left <= 6 and score_diff < -3:
        return 'go'
    need_now = int(np.ceil(-score_diff / 8.0)) if score_diff < 0 else 0
    chasing = score_diff < 0 and secs_left < 150 * need_now + 90
    # does a field goal matter? Down 14 it leaves two scores either way; down 10 it makes it one
    need_after_fg = int(np.ceil(-(score_diff + 3) / 8.0)) if score_diff + 3 < 0 else 0
    fg_matters = not (score_diff < -3 and secs_left < 480 and need_after_fg >= need_now and -score_diff not in (7, 8) and -(score_diff + 3) not in (7, 8))
    band, zone = fourth_band(ydstogo), fourth_zone(yardline_100)
    p_table = float(np.clip(GO_RATE[band][zone] * (0.55 + 0.60 * aggression), 0.0, 1.0))     # the observed rates already carry an average coach; the personality term sits around them
    r = DEC.fourth_down(score_diff, max(1.0, secs_left), yardline_100, ydstogo,
                       fg_prob=kick_chance, aggression=aggression, is_home=1) if use_wp else None
    if r is not None:
        # the model's edge as a probability: a small edge is a lean, a big one nearly certain, a negative one nearly never
        edge = float(r.get('go_boost', 0.0)); thresh = 0.020 - 0.024 * (aggression - 0.5)
        p_model = 1.0 / (1.0 + np.exp(-(edge - thresh) / 0.015))
        # the model's possession bias is worst deep in its own end; there the league's behavior carries more weight
        w_model = 0.30 if yardline_100 <= 60 else 0.18 if yardline_100 <= 75 else 0.0     # inside your own 25 the model's possession bias has no vote
        p_go = w_model * p_model + (1.0 - w_model) * p_table
    else:
        p_go = p_table
    # THE SCORE AND THE CLOCK. The table averages every score state, so it carries the desperate club's fourth
    # downs and the comfortable club's alike. A lead shrinks the appetite as it grows and as the clock runs (up
    # 22 in the fourth quarter, nobody goes on fourth and six from his own 25); a deficit raises it. Continuous,
    # so a one-point lead and a twenty-point lead are not the same rule.
    played = float(np.clip(1.0 - secs_left / 3600.0, 0.0, 1.0))
    lead_scores = score_diff / 8.0
    if yardline_100 >= 60 and not chasing:
        # DEEP IN YOUR OWN END the table's rate is made of clubs that had to: it is the league's average over
        # every state, and the going from the 12 is nearly all late and behind. Early, or ahead, or tied, it is
        # a punt. The share of the table's rate that applies rises with the clock and only when behind.
        urgency = float(np.clip((played - 0.5) / 0.5, 0.0, 1.0)) * (1.0 if score_diff < 0 else 0.25)
        base_share = 0.65 if ydstogo <= 1 else 0.25 if ydstogo <= 3 else 0.08     # fourth and one is a tactical go anywhere; the long ones are the desperate ones
        p_go *= base_share + (1.0 - base_share) * urgency
    if lead_scores > 0:
        p_go *= float(np.exp(-LEAD_FOURTH * lead_scores * (1.0 + played)))
    elif lead_scores < 0:
        p_go = float(min(0.85, p_go * min(1.4, np.exp(0.2 * (-lead_scores) * (1.0 + played)))))   # a deficit pushes a little; the table already carries the trailing club's fourth downs, and the chase rule takes over late
    if chasing:
        p_go = max(p_go, 0.55 if score_diff < -8 else 0.35)
    if score_diff <= -9 and yardline_100 <= 5 and ydstogo <= 5:
        p_go = max(p_go, 0.85)                           # down two scores at the goal line, the touchdown is the point
    if secs_left < 120 and score_diff < 0 and yardline_100 > 40 and not (in_range and fg_matters):
        p_go = 1.0                                       # a punt down late is the game
    if rng.random() < p_go:
        return 'go'
    # not going: the kick when it is in range and worth something, else the punt
    # A team's range follows its kicker and the weather. The old fixed yardline
    # limits made a weak leg try the same long kick as a strong one.
    if in_range and fg_matters:
        return 'field_goal' if r is None or r['wp_fg'] >= r['wp_punt'] else 'punt'
    if in_range and not fg_matters:
        return 'go'                                      # three points change nothing here; the down is the drive
    return 'punt'


def returner_for(ros, state, rate_fn, kind='kr'):
    """The club's return man for this kick: the charted one unless he is hurt or out, then the best healthy
    man among the return positions. A hurt returner kept returning kicks because the slot was fixed at kickoff."""
    out = state.out if state is not None else set()
    kr = ros.get(kind) or {}
    if kr and kr.get('pid') not in out: return kr
    import rosters as R
    cands = [p for grp in ('wr', 'db', 'backs') for p in (ros.get(grp) or []) if p and p.get('pid') not in out and p.get('pos') in R.RETURN_POS]
    if ros.get('rb') and ros['rb'].get('pid') not in out: cands.append(ros['rb'])
    return max(cands, key=R.return_score) if cands else (kr or {})


def kickoff_booked(returner, rng, rate_fn, book, from_50=False):
    """kickoff(), and the return goes in the book against the returner. Kickoff returns were resolved
    for years and never booked, so no kick returner had a line. The result is kept so the drive it
    opens can log the kick as its first play."""
    r = kickoff(returner, rng, rate_fn, from_50=from_50)
    if book is not None and not r.get('touchback') and returner:
        book.special('kr', returner.get('pid'), ret=r.get('ret', 0.0))
    r['returner'] = (returner or {}).get('pid')
    LAST_KICKOFF['r'] = r
    return r


def kickoff_clock(clock, kick):
    """Run the game clock during a live kickoff return, stopping at period end.

    Touchbacks never start the clock. The kick that crosses halftime ends the
    half before the receiving offense can begin a possession.
    """
    if kick.get('touchback') or clock <= 0:
        return clock
    after = clock - play_seconds('kickoff')
    for edge in (2700.0, 1800.0, 900.0, 0.0):
        if clock > edge >= after:
            return edge
    return float(max(0.0, np.floor(after + 0.5)))



# Distance anchors, not stepwise bands. Interpolate beyond 34 yards so a
# fraction of a yard cannot trigger an entire five-yard accuracy penalty.
FG_PCT = [(29, .975), (34, .955), (39, .905), (44, .840), (49, .785),
          (54, .720), (59, .590)]

def fg_probability(distance, kicker=None, rate_fn=None, AVG=0.70):
    """Smooth distance accuracy, gradual leg-strength influence, then range tail.

    Keep the short-kick/33-yard PAT baseline unchanged. The 59-yard anchor
    holds beyond the curve; the kicker-specific range tail handles longer
    attempts without granting an artificial accuracy jump at 50 yards.
    """
    if distance <= 34:
        base = next(p for d, p in FG_PCT if distance <= d)
    else:
        base = float(np.interp(distance, [d for d, _ in FG_PCT], [p for _, p in FG_PCT]))
    pwr = AVG
    if kicker is not None and rate_fn is not None:
        acc = rate_fn(kicker, {'kick_acc_rating': .75, 'awareness_rating': .25})
        pwr = rate_fn(kicker, {'kick_power_rating': 1.0})
        base *= 1.0 + 0.16 * (acc - AVG)
        # Blend in power over 40-52 yards rather than switching it on at 50.
        base *= 1.0 + 0.55 * (pwr - AVG) * float(np.clip((distance - 40.0) / 12.0, 0.0, 1.0))
    reach = 57.0 + 26.0 * (pwr - AVG)
    if distance > 48:
        base *= 1.0 / (1.0 + np.exp((distance - reach) / 2.0))
    return float(np.clip(base, 0.005, 0.995))

def snapper_for(roster, state=None):
    """First available snapper in depth order, else an emergency center."""
    depth = roster.get('depth') or {}
    out = getattr(state, 'out', set())
    for pos in ('LS', 'C'):
        for player in depth.get(pos, []):
            if player.get('pid') not in out: return player
    return None


def snap_quality(snapper, rate_fn):
    """Small reliability edge from the existing LS grade; 70 is neutral.

    Missing context stays neutral for standalone callers. Real rosters use
    their ordered LS depth, with a center as the emergency fallback.
    """
    if snapper is None: return 0.0
    import targets as TG
    return float(np.clip(rate_fn(snapper, TG.DEPTH_WEIGHTS['LS']) - 0.70, -0.5, 0.3))


def attempt_field_goal(yardline_100, kicker, rng, rate_fn, snapper=None):
    dist = yardline_100 + 17               # 10 end zone + 7 snap
    p_make = fg_probability(dist, kicker, rate_fn) * (ENV.kick_mult if dist >= 35 else 1.0 - 0.3 * (1.0 - ENV.kick_mult))
    # the special teams coordinator: a good one keeps the kicker near his number, a poor one adds variance either way
    kn = float(kicker.get('st_noise', 1.0)) if isinstance(kicker, dict) else 1.0
    if kn != 1.0:
        p_make = float(np.clip(0.5 + (p_make - 0.5) / kn, 0.02, 0.99))
    p_make = float(np.clip(p_make + 0.02 * snap_quality(snapper, rate_fn), 0.005, 0.995))
    made = rng.random() < p_make
    return dict(type='field_goal', distance=dist, made=made,
                points=3 if made else 0)

# ============================================================ THE TRY
# A touchdown is six. What follows is a separate decision and a separate
# play, so the extra point can be missed and the two-point try can fail.
#
# The kick is a 33-yard field goal - ball on the 15, seven yards back to the
# hold, ten yards of end zone - so it runs through the same distance curve and
# the same kicker ratings as every other kick rather than a flat league rate.
#
# The two-point try is ONE REAL SNAP from the two, resolved by the same play
# engine as any other goal-line play. The conversion rate is therefore an
# output of the rosters and the red zone physics, not a constant. It is not
# calibrated to the real 47.9% and should not be until the red zone
# touchdown rate is fixed, since both come from the same per-play numbers.

# Leads (from the scoring team's view, counting the six just scored) where the
# accepted chart says go for two. Late game only: before the fourth quarter
# the chart has no opinion and teams kick.
TWO_POINT_GO = (-18, -16, -10, -5, -2, 1, 4, 5)

def two_point_decision(lead_after_td, quarter, secs_left=None,
                       conv_prob=None, aggression=0.5):
    """
    Kick or go, on win probability rather than a chart.

    The chart below gated on the fourth quarter and produced tries on 2.5% of
    touchdowns against a real 6.4%, because a chart cannot price the thing
    that actually decides it: the two options are worth 0.957 points and 0.950
    points, so it is an active choice every time and what tips it is score AND
    clock together.

    TWO_POINT_GO is kept as the fallback when no clock is available.
    """
    if secs_left is None:
        if quarter < 4: return False
        return int(round(lead_after_td)) in TWO_POINT_GO
    import decisions as DEC
    r = DEC.two_point(lead_after_td, max(1.0, secs_left),
                      conv_prob=conv_prob if conv_prob else DEC.TWO_RATE,
                      aggression=aggression)
    return r['call'] == 'two'

def attempt_extra_point(kicker, rng, rate_fn, snapper=None, distance=33):
    import events as E
    flag = E.special_teams_penalty_check(rng, 'extra_point')
    if flag and flag['on_offense']:
        distance += flag['yards']
    chance = np.clip(fg_probability(distance, kicker, rate_fn) + 0.02 * snap_quality(snapper, rate_fn), 0.005, 0.995)
    made = rng.random() < chance
    if flag and not flag['on_offense']:
        if made:
            flag = None                        # keep the point, decline the offside flag
        else:
            spot = max(0.5, distance - 18.0)
            walk = min(flag['yards'], spot / 2.0)
            flag['yards'] = walk
            distance -= walk
            chance = np.clip(fg_probability(distance, kicker, rate_fn) + 0.02 * snap_quality(snapper, rate_fn), 0.005, 0.995)
            made = rng.random() < chance       # replay the untimed try
    return dict(type='extra_point', distance=distance, penalty=flag, made=bool(made),
                points=1 if made else 0)

def offensive_leans(state):
    """The same caller inputs for normal downs and conversion attempts."""
    pl = getattr(state, 'plan', None)
    if pl is None: return None
    seq = getattr(state, 'seq', None) or {'run_hot': 0.0}
    pa_boost = float(np.clip(1.0 + 0.55 * min(seq['run_hot'], 3.0) / 3.0, 0.85, 1.55))
    return dict(pass_bias=pl.pass_bias, play_action=min(0.95, pl.play_action_rate * pa_boost),
                motion=pl.motion_rate, protection=(pl.protection if pl.protection_locked else None),
                screen_boost=pl.screen_boost, heavy_lean=pl.heavy_lean,
                personnel_mix=dict(pl.personnel_mix), off_personnel=pl.off_personnel,
                run_scheme_mix=dict(pl.run_scheme_mix), tempo=pl.tempo)


def apply_offensive_plan(call, state, rng, yards, down, togo):
    pl = getattr(state, 'plan', None)
    if pl is None: return
    import gameplan as GP
    call['plan'] = pl
    call['travel_willingness'] = float(state.coach.get('travel_willingness', 0.5))
    if call.get('is_pass') and not call.get('plan_depth'):
        call['depth'] = GP.depth(pl, rng, yards_to_endzone=yards, down=down, ydstogo=togo)


def apply_defensive_plan(call, state, rng):
    pl = getattr(state, 'plan', None)
    if pl is None: return
    import gameplan as GP
    call['box'] = int(np.clip(call.get('box', 6) + GP.box_shift(pl.box_bias, rng), 4, 10))
    call['bracket'] = pl.bracket
    call['travel'] = pl.travel
    call['travel_target'] = pl.travel_target
    call['zone_aggression'] = pl.zone_aggression


def attempt_two_point(offense, defense, rng, resolve_fn, call_off, call_def,
                      rate_fn, off_state=None, def_state=None, start_yardline=2, _retry=False):
    """
    One snap from the two. Deliberately NOT fed to state.observe: the
    adjustment engine reads a rolling four-series window of normal downs, and
    a goal-line try is not one of those.
    """
    import gameplan as GP
    import events as E
    flag = None if _retry else E.special_teams_penalty_check(rng, 'two_point')
    if flag and flag['on_offense']:
        start_yardline += flag['yards']
    try_yards = max(1, int(np.ceil(start_yardline)))
    oc = call_off(1, try_yards, 0, try_yards, rng, offense=offense, rate_fn=rate_fn,
                  lean=offensive_leans(off_state))
    dp = getattr(def_state, 'plan', None)
    dc = call_def(oc, 1, try_yards, rng, try_yards, defense=defense, rate_fn=rate_fn,
                  lean=GP.defensive_leans(dp) if dp is not None else None,
                  recent=getattr(def_state, 'cov_memory', None))
    apply_offensive_plan(oc, off_state, rng, try_yards, 1, try_yards)
    apply_defensive_plan(dc, def_state, rng)
    off_f, _ = field_units(offense, off_state, rng, True, oc.get('personnel'))
    def_f, _ = field_units(defense, def_state, rng, False, dc.get('personnel'),
                           front_family=dc.get('front_family'))
    # The package has already selected and recorded the carrier's snap.
    out = resolve_fn(off_f, def_f, oc, dc, try_yards, rng)
    good = out.get('type') in ('run', 'complete', 'scramble') and \
           float(np.round(out.get('yards', 0.0))) >= start_yardline
    if flag and not flag['on_offense']:
        if good:
            flag = None                         # the offense keeps the successful free play
        else:
            walk = min(flag['yards'], start_yardline / 2.0)
            flag['yards'] = walk
            retry = attempt_two_point(offense, defense, rng, resolve_fn, call_off, call_def,
                                      rate_fn, off_state, def_state, start_yardline - walk, _retry=True)
            retry['penalty'] = flag
            return retry
    return dict(type='two_point', play=out.get('type'), from_yardline=start_yardline, penalty=flag, made=bool(good),
                points=2 if good else 0)

# ============================================================ PUNTS
# Real: returned on 35% of punts, mean 11.5 yards WHEN returned (the 4.23
# figure counted all punts including fair catches), p90 19, max 97, and 0.36%
# go for a touchdown.
PUNT = dict(gross=50.2, sd=7.4, blocked=.0043,        # gross up from 48.6 once the 70-yard cap and the 7.4 spread trimmed the long tail          # sd from 8.5: 60-yard punts are about 4% of the real league's and 65-yarders about 1%; at 8.5 they ran 9% and 3%          # the full swing; pooches from better field position pull the league gross to the real 47.2
            # real: 45% returned, mean return 10.4; the rest fair caught,
            # downed, out of bounds or a touchback
            return_rate=.45, return_mean=10.4, return_p90=19, td_rate=.0036,
            # A FULL swing from a league-average leg. The 47.2 league gross
            # includes every kick shortened from midfield, so the leg is
            # longer than the mean. Real punters rate well above 0.70 on power,
            # which the multiplier below turns into their extra distance.
            full=49.0,
            # where he tries to drop it when a full swing would carry through
            # the end zone, and how far an average leg misses that spot
            aim=12.0, aim_sd=7.0,
            # a ball that comes down inside the 10 and is not caught bounces
            # toward the goal; gunners down it unless it gets there first
            roll_mean=6.0, roll_sd=4.0)

def punt(yardline_100, punter, returner, rng, rate_fn, AVG=0.70, snapper=None):
    """
    The punter READS THE FIELD, and so does the returner.

    This used to kick a full gross from wherever the punter stood and touched
    back only if the ball crossed the goal, so a punt from midfield landed at
    the 3 every time: 9.8% of drives started inside the own 10 (real is a few
    percent) and safeties ran three times the real rate off the sacks and
    losses that followed. From midfield a real punter shortens the kick and
    drops it around the 10; the distance is a decision made from field
    position and his own leg, not a constant. At the other end the returner
    decides what to do with a ball coming down near his goal line: fair catch
    it, return it, or let it bounce and hope for the touchback. Every real
    touchback is one of those decisions going the kicking team's way.
    """
    quality = snap_quality(snapper, rate_fn)
    spread = 1.0 - 0.5 * quality
    if rng.random() < PUNT['blocked'] * (1.0 - 1.5 * quality):
        return dict(type='punt', blocked=True, net=0, origin=yardline_100,
                    new_yardline=100 - yardline_100)
    pwr = rate_fn(punter, {'kick_power_rating': .70, 'kick_acc_rating': .30})
    acc = rate_fn(punter, {'kick_acc_rating': 1.0})
    full = min(68.0, rng.normal(PUNT['full'] * (1.0 + 0.30 * (pwr - AVG)) * ENV.punt_mult, PUNT['sd'] * spread))     # 68 is a season-long league high
    pooch = False
    if yardline_100 - full < PUNT['aim']:
        # a full swing goes into or through the end zone: drop it short.
        # Accuracy decides how close to the spot he actually lands it.
        pooch = True
        miss = rng.normal(0.0, PUNT['aim_sd'] * (1.0 - 0.6 * (acc - AVG)) * spread)
        gross = max(15.0, yardline_100 - PUNT['aim'] + miss)
    else:
        gross = full
    land = yardline_100 - gross
    touchback = land <= 0
    ret = 0.0
    how = 'touchback'
    if not touchback:
        if land < 10:
            # THE RETURNER'S CALL. Deep in his own end he rarely runs it
            # back; the closer to the goal the more he lets it go, because a
            # bounce into the end zone is worth twenty yards to him.
            let_go = rng.random() < (0.85 if land < 5 else 0.35)
            if let_go:
                roll = max(0.0, rng.normal(PUNT['roll_mean'], PUNT['roll_sd']))
                if land - roll <= 0:
                    touchback = True
                else:
                    land -= roll; how = 'downed'; gross = min(70.0, gross + roll)      # the roll is part of the gross; 70 is the modern high
            else:
                how = 'fair_catch'
        elif rng.random() < PUNT['return_rate']:
            how = 'return'
            skill = rate_fn(returner, {'kick_ret_rating': .45, 'speed_rating': .30,
                                       'juke_move_rating': .25})
            # shape/scale solved against mean 10.4 and p90 19, with a long
            # right tail so 0.36% reach the end zone
            ret = max(0.0, rng.gamma(1.9, 5.5) * (1.0 + 0.9 * (skill - RET_AVG)))
        else:
            how = 'fair_catch'
    if touchback:
        return dict(type='punt', blocked=False, touchback=True, how='touchback',
                    gross=round(float(gross), 1), pooch=pooch,
                    origin=yardline_100, net=round(float(yardline_100 - 20), 1),
                    new_yardline=80)       # opponent's own 20
    # A return brings the ball OUT, toward the kicking team's goal, so it
    # SHORTENS the receiving team's field. This was + ret: every punt return
    # in the engine's history pushed the returner backwards by the length of
    # his own return, and the punt net came out longer than the gross.
    new = float(np.clip(100 - land - ret, 1, 99))
    return dict(type='punt', blocked=False, touchback=False, pooch=pooch, how=how,
                gross=round(float(gross), 1), ret=round(float(ret), 1),
                land=round(float(land), 1), origin=yardline_100,
                net=round(float(yardline_100 - (100 - new)), 1),
                new_yardline=round(new, 0))

# ============================================================ KICKOFFS
# 2026 DYNAMIC KICKOFF. The rule has changed every year since 2024, so older
# seasons describe a game that no longer exists: touchbacks ran 73.0% in 2023,
# 64.2% in 2024, 20.7% in 2025 and 15.5% through the start of 2026.
#
# Under the current rule the kicker kicks from his own 35, coverage waits at the
# opponent's 40, and a kick reaching the end zone in the air is a touchback out
# to the RECEIVING TEAM'S OWN 35 - not the 30, which is what the first build
# used. The live 2026 data confirms it: the mean drive start after a touchback
# is the own 35.0.
#
# 2026-specific tweaks also in effect: an onside kick may be declared at any
# point in the game, only five receiving players must have a foot on the
# restraining line (was six), and a touchback on a kickoff from the 50 after
# penalty enforcement is spotted at the 20 rather than the 35.
RET_AVG = 0.80                    # the return skill of the man clubs actually send back there
KICKOFF = dict(touchback=.155, return_rate=.799, return_mean=25.0,      # 26.9 drew a 30.8 mean once the return-man skill term was applied; 25.0 lands the league at about 27.6
               touchback_to=65,            # receiving team's own 35
               touchback_from_50=80,       # own 20, the 2026 anti-loophole rule
               onside_recovery=.0645)      # under the dynamic kickoff

LAST_KICKOFF = {}



# ============================================================ THE END OF A HALF, PRICED
# What the offense does with the last seconds of a half used to be three fixed yardlines: kick from inside the
# 37, take a shot from inside the 37, kneel from outside the 45. A club at the 38 with 11 seconds and three
# timeouts let the half expire. Now the coach prices his options in expected points from where he stands and
# takes the best one; his kicker's leg sets the kick's range, his passing game against their secondary sets the
# shot's odds, and his own aggression sets how much he likes the shot when the numbers are close.
SCORE_STOPS_CLOCK = True    # a scoring play stops the clock at the score (test toggle)
LEAD_FOURTH = 0.45          # how fast a lead shrinks the fourth-down appetite (0.9 had leaders going on nothing, and the league lost its blowouts)
STALL_ON = True
PLAN_WINDOW = 75.0          # seconds left in the half within which the clock, not the downs, is the constraint
PLAY_SECS = 7.0             # a snap with the clock stopped after it (an incompletion, a timeout, out of bounds)
PLAY_SECS_RUN = 38.0        # a snap with the clock running: huddle, snap late in the play clock
PLAY_BAD = 0.08             # one more snap ends in a sack or a turnover this often
PLAY_INC = 0.32             # ...or an incompletion, which stops the clock and leaves the kick where it was
PLAY_GAIN = 9.0             # a completion's expected gain in yards
SHOT_INT = 0.08             # a throw to the end zone is picked off this often
SHOT_SHORT = 0.15           # ...or caught short of the goal, in bounds
HAIL_MARY_LINE = 0.21       # expected points below which the offense kneels instead (before the half)
PLAY_OOB = 0.30             # the share of completions that get out of bounds when the sideline is the point


def _possession_odds(secs, tos):
    """What the other side can do with the ball from a kickoff with this much clock and these timeouts: the odds of
    reaching a kick (a possession that has to travel about forty yards in a handful of snaps) and of a touchdown.
    Nothing with a few seconds; a real possession with half a minute and timeouts."""
    if secs <= 6: return 0.0, 0.0
    # time is the currency and a timeout is worth about a dozen seconds of it; the odds of reaching a kick rise
    # with the time and level off (a minute and a half with timeouts is about as good as it gets)
    # timeouts make the time usable: without them a club works the sidelines and spikes; with three it uses all of it
    secs_eff = float(secs) * (0.75 + 0.25 * min(3, max(0, int(tos))) / 3.0) + 8.0 * max(0, int(tos))
    p_reach = 0.50 * (1.0 - float(np.exp(-secs_eff / 75.0)))              # a possession from a kickoff with a minute and timeouts reaches a kick about half the time
    p_td = 0.05 * (1.0 - float(np.exp(-secs_eff / 45.0)))
    return p_reach, p_td


def _possession_value(secs, tos, game_end=False, lead_after=0):
    """The other side's possession priced in the plan's own units: expected points before the half; at the end
    of the game, the share of the win it takes back, which depends on what our score left them needing (a kick
    ties them if we lead by three or less after it; only a touchdown helps them if we lead by more)."""
    p_reach, p_td = _possession_odds(secs, tos)
    if not game_end:
        return float(3.0 * p_reach * 0.72 + 6.95 * p_td)
    if lead_after <= 0: return float(p_reach * 0.5 + p_td)            # we did not get ahead: their kick wins it
    if lead_after <= 3: return float(p_reach * 0.72 * 0.5 + p_td)     # their kick ties, their touchdown wins
    return float(p_td * 0.5)                                           # they need a touchdown, and a tie at best


def _shot_td_prob(yardline, offense, defense, rate_fn):
    """A throw to the end zone from this spot: the odds fall with distance and move with the passing matchup."""
    base = float(np.clip(0.40 - 0.0080 * float(yardline), 0.03, 0.40))
    try:
        qb = offense.get('qb') or {}; wrs = (offense.get('wr') or [])[:3]; dbs = (defense.get('db') or [])[:5]
        o = 0.5 * rate_fn(qb, {'throw_acc_deep_rating': .6, 'throw_power_rating': .4}) + 0.5 * float(np.mean([rate_fn(w, {'speed_rating': .35, 'spec_catch_rating': .35, 'jump_rating': .3}) for w in wrs])) if wrs else 0.7
        d = float(np.mean([rate_fn(x, {'zone_cover_rating': .4, 'man_cover_rating': .3, 'speed_rating': .3}) for x in dbs])) if dbs else 0.7
        base *= float(np.clip(1.0 + 1.5 * (o - d), 0.7, 1.3))
    except Exception: pass
    return float(np.clip(base, 0.02, 0.5))


def end_of_half_plan(dr, offense, defense, rate_fn, timeouts, pos, half_end, secs_in_half, coach=None, yardline=None):
    """The coach's best option with the seconds left, priced from where he stands: 'kick', 'shot', 'play' (one or
    more snaps, then decide again), or 'kneel'. Before halftime the price is expected points. At the end of the
    game it is the game: a field goal is worth nothing down four, a touchdown is the win down six and a coin flip
    down eight, and with no timeouts a completion in bounds ends it. Returns dict(choice, evs, p_fg, p_td) or None
    outside the window, or when the side with the ball is ahead at the end of the game (it wants the clock)."""
    if half_end is None and (dr.quarter < 4 or dr.score_diff > 0): return None
    if half_end is not None and dr.quarter > 2: return None
    if secs_in_half > PLAN_WINDOW or secs_in_half <= 0: return None
    y = float(yardline if yardline is not None else dr.yardline)
    if y <= 0.5: return None
    c = coach or {}
    aggr = float(np.clip(0.5 * float(c.get('fourth_down', 0.5)) + 0.5 * float(c.get('adjust_willingness', 0.5)), 0.0, 1.0))
    own_tos = timeouts.left.get(pos, 0) if timeouts is not None else 0
    kicker = offense.get('k') or {}
    game_end = half_end is None
    need = max(0, -int(round(dr.score_diff))) if game_end else 0
    two_scores = game_end and need > 8                          # a touchdown alone does not tie it; it is still the only thing to play for
    # WHAT A SCORE IS WORTH. Points before the half; at the end of the game, the share of a win: a kick wins a tie
    # and only ties a deficit of three or less, a touchdown wins outright down six or less, needs the kick down
    # seven and the two-point try down eight
    if game_end:
        v_kick = 1.0 if need == 0 else (0.5 if need <= 3 else 0.0)
        v_td = 1.0 if need <= 6 else (0.94 if need == 7 else 0.48 if need == 8 else 0.02)
        v_kneel = 0.5 if need == 0 else 0.0                        # the clock runs out: overtime tied, a loss behind
        floor_line = 0.0                                           # behind, any chance beats none; tied, the kneel's coin flip is the bar
    else:
        v_kick, v_td, v_kneel, floor_line = 3.0, 6.95, 0.0, HAIL_MARY_LINE
    def kick_ev(yy): return v_kick * fg_probability(yy + 17.0, kicker, rate_fn)
    p_fg = fg_probability(y + 17.0, kicker, rate_fn)
    p_td = _shot_td_prob(y, offense, defense, rate_fn)
    evs = {'kneel': v_kneel}
    if secs_in_half >= 1: evs['kick'] = kick_ev(y)
    def shot_ev(yy, secs, tos):
        """A throw to the end zone: the touchdown, or, with time to kick after it, the kick that follows an
        incompletion (the clock stops) or a catch short of the goal (a timeout stops it); tied at the end of the
        game, an incompletion still leaves the coin flip."""
        p = _shot_td_prob(yy, offense, defense, rate_fn)
        ev = v_td * p * (0.85 + 0.30 * aggr)
        live = 1.0 - p - SHOT_INT
        if secs >= 6:                                                # the throw takes four seconds; an incompletion leaves the kick
            ev += live * ((1.0 - SHOT_SHORT) * kick_ev(yy) + SHOT_SHORT * (kick_ev(max(1.0, yy - 15.0)) if tos > 0 else 0.0))
        elif game_end and need == 0:
            ev += live * v_kneel
        return ev
    if secs_in_half >= 4: evs['shot'] = shot_ev(y, secs_in_half, own_tos)
    # one snap or several before deciding: a completion gains PLAY_GAIN, an incompletion stops the clock for
    # nothing, a sack or a turnover ends the attempt. Each snap takes PLAY_SECS with the clock stopped after it; a
    # completion in bounds keeps the clock running and, with no timeout left and no time to spare, ends the half
    best_play = None; k_best = 0
    n_max = int((secs_in_half - 4.0) // PLAY_SECS)
    surv = 1.0; yk = y; sk = secs_in_half; tos_k = own_tos
    for k in range(1, max(0, min(n_max, own_tos + 3)) + 1):
        sk -= PLAY_SECS
        if sk < 3: break
        p_comp = 1.0 - PLAY_BAD - PLAY_INC
        if tos_k > 0: tos_k -= 1; surv *= (1.0 - PLAY_BAD)                                  # the timeout stops it after a catch
        elif sk >= 25: surv *= (1.0 - PLAY_BAD)                                             # enough clock to absorb a catch in bounds
        else: surv *= (1.0 - PLAY_BAD - p_comp * (1.0 - PLAY_OOB))                          # a catch in bounds ends it; only the sideline saves it
        yk = max(1.0, yk - PLAY_GAIN * p_comp)
        terminal = max(kick_ev(yk), shot_ev(yk, sk, tos_k))
        evk = surv * terminal
        if best_play is None or evk > best_play: best_play = evk; k_best = k
    if best_play is not None: evs['play'] = best_play
    # THE CLOCK IS AN ASSET TOO. Hurrying (timeouts, stoppages, more snaps) leaves the other side time after the
    # score; bleeding it (snap late, kick at the last moment) leaves them nothing. The hurry is charged with what
    # the other side can do with the seconds left; the bleed gets the snaps the clock allows without stoppages
    # (about PLAY_SECS_RUN each). A coach's aggression sets how much he fears the other side's possession.
    fear = 1.25 - 0.5 * aggr                                     # the conservative coach counts their chance at 1.25x, the gambler at 0.75x
    other_tos = timeouts.left.get('away' if pos == 'home' else 'home', 0) if timeouts is not None else 3
    # each option leaves the other side a different amount of clock: a kick now leaves nearly all of it, a shot
    # then a kick a little less, k quick snaps then a kick less again; the bleed leaves next to nothing
    residual = {'kick': secs_in_half - 4.0, 'shot': secs_in_half - PLAY_SECS - 4.0, 'play': 4.0, 'kneel': 0.0}   # the drill that gets there runs to the gun; only a kick or a shot taken now hands time back
    lead_after = {'kick': int(round(dr.score_diff)) + 3, 'shot': int(round(dr.score_diff)) + 7, 'play': int(round(dr.score_diff)) + 3, 'kneel': int(round(dr.score_diff))}
    # THE STALL. A drive that hurries from its own end mostly does not get to a kick: it punts with time left, and
    # that time is the other side's. The odds of the stall rise with the distance to range; a stalled drive hands
    # back what its three snaps and a punt leave. A club behind pays none of this: it needs the points.
    p_stall = float(np.clip((y - 30.0) / 70.0, 0.05, 0.85))
    stall_left = max(0.0, secs_in_half - PLAY_SECS * 3 - 6.0)
    def cost(opt):
        if dr.score_diff < 0: return 0.0                           # behind, the clock is ours to spend
        if game_end and need > 0 and opt != 'kick': return 0.0
        c = fear * _possession_value(max(0.0, residual.get(opt, 0.0)), other_tos, game_end, lead_after.get(opt, 0))
        if opt == 'play' and STALL_ON: c += fear * p_stall * _possession_value(stall_left, other_tos, game_end, int(round(dr.score_diff)))
        return c
    net = {k: v - cost(k) for k, v in evs.items()}
    hurry_choice = max(net, key=lambda k: net[k]); hurry_ev = net[hurry_choice]; cost_hurry = cost(hurry_choice)
    # THE BLEED: k slow snaps with the clock running, then the play clock run down and one shot at the end zone
    # with a few seconds left, then the kick if it misses; the other side gets nothing back. The best k is taken.
    bleed_ev = None; k_bleed = 0; bleed_final = 'kick'
    for k in range(0, 4):
        rest = secs_in_half - PLAY_SECS_RUN * k
        if rest < 6: break
        yk = max(1.0, y - PLAY_GAIN * (1.0 - PLAY_BAD - PLAY_INC) * k)
        kv, sv = (kick_ev(yk), shot_ev(yk, min(rest, 12.0), own_tos)) if 'kick' in evs else (0.0, 0.0)
        evk = ((1.0 - PLAY_BAD) ** k) * max(kv, sv)
        if bleed_ev is None or evk > bleed_ev: bleed_ev, k_bleed, bleed_final = evk, k, ('shot' if sv > kv else 'kick')
    hurry = True; choice = hurry_choice
    behind = dr.score_diff < 0
    # THE MODE STICKS. The plan is priced again at every snap and a spot near the boundary flipped between hurrying
    # and bleeding within one possession (a timeout spent at 0:49, then the play clock run down at 0:43). Once a
    # possession has chosen, the other way has to beat it by a clear margin: a quarter of its value and a fifth
    # of a point. A big gain or a turnover moves the prices far more than that, so real changes still register.
    prev = getattr(dr, '_plan_mode', None)
    bleed_wins = bleed_ev is not None and bleed_ev >= floor_line and (
        (bleed_ev >= hurry_ev * 1.25 + 0.2) if prev == 'hurry' else
        (hurry_ev < bleed_ev * 1.25 + 0.2) if prev == 'bleed' else
        (bleed_ev >= hurry_ev))
    if not behind and bleed_wins:
        # ahead or tied, the clock is worth protecting; behind, every second is the offense's own and it never
        # waits (a team down two scores once ran the play clock down because every option priced near nothing)
        hurry = False; choice = 'play' if k_bleed > 0 else bleed_final; evs = dict(evs, bleed=bleed_ev)
    dr._plan_mode = 'hurry' if hurry else 'bleed'
    if evs.get(choice, 0.0) < floor_line: choice = 'kneel'
    return dict(choice=choice, hurry=hurry, evs={k: round(v, 3) for k, v in evs.items()}, cost_hurry=round(cost_hurry, 3), p_fg=round(p_fg, 3), p_td=round(p_td, 3), aggr=round(aggr, 2), need=need)



def _onside_call(clock, need, my_tos, coach, rng):
    """Onside or kick deep, priced. The onside comes back about 6% of the time and gives the kicker's side the ball
    near its own 45 with the clock intact; a miss gives the other side the ball there, in range, and most of the
    clock. Kicking deep hands them the ball at their 30 and asks the defense for a stop: the ball comes back
    with whatever the stop leaves, and the timeouts in hand decide how much that is. The coach's aggression
    weighs the gamble; a club needing two scores counts every possession double. Where the two are close the
    coach's appetite decides, so the same spot is not the same call for every staff."""
    if need <= 0: return False
    c = coach or {}
    aggr = float(np.clip(0.5 * float(c.get('fourth_down', 0.5)) + 0.5 * float(c.get('adjust_willingness', 0.5)), 0.0, 1.0))
    p_rec = KICKOFF['onside_recovery']
    def usable(secs, tos):
        pr, _ = _possession_odds(secs, tos); return pr / 0.5             # the odds of a usable possession, 0 to 1
    # DEEP: they have it at their 30; the ball comes back if they stall (about 60% of drives after a kickoff do),
    # with whatever their three snaps leave on the clock; each timeout in hand keeps about 24 seconds of it
    burn = 3 * PLAY_SECS_RUN - 24.0 * min(3, my_tos)
    v_deep = 0.60 * usable(max(0.0, clock - burn - 6.0), my_tos)
    # ONSIDE: recovered, the ball is near midfield with the clock intact (worth more than a kickoff drive); missed,
    # they have it in range and the clock, and it comes back only if they stall (about 35% from there)
    v_rec = 1.25 * usable(clock, my_tos)
    v_miss = 0.35 * usable(max(0.0, clock - 2 * PLAY_SECS_RUN - 6.0), my_tos)
    v_onside = (p_rec * v_rec + (1.0 - p_rec) * v_miss) * (0.85 + 0.30 * aggr)   # the gambler likes the gamble
    return v_onside > v_deep


def _timeout_call(dr, t, out, timeouts, pos, half_end, secs_in_half, coach=None, plan=None, dcoach=None):
    """Who spends a timeout after this play, if anyone. The trailing side spends them to get the ball back; the
    driving side to keep the clock alive. Neither wastes one early. Returns (used, used_by).

    THE TRAILING OFFENSE'S WINDOW IS THE COACH'S. Down one score at the end of a half, an offense holding two or
    three timeouts starts spending them earlier than one down to its last: from 60 seconds out for the most
    conservative coach to 100 for the most aggressive (his fourth-down and adjustment dials), and 60 with one left
    whoever he is. Tied stays at 40: a tie is not worth the last timeout until the very end."""
    used = False; used_by = None
    c = coach or {}
    clock_aggr = float(np.clip(0.5 * float(c.get('fourth_down', 0.5)) + 0.5 * float(c.get('adjust_willingness', 0.5)), 0.0, 1.0))
    own_left = timeouts.left.get(pos, 0) if timeouts is not None else 0
    trail_window = (60.0 + 40.0 * clock_aggr) if own_left >= 2 else 60.0
    _scored_now = t in ('run', 'complete', 'scramble') and float(np.round(float(out.get('yards', 0.0) or 0.0))) >= dr.yardline - 0.01
    _at_warning = secs_in_half > 120 and secs_in_half - play_seconds(t) <= 120 and not getattr(dr, '_two_min', False)
    if timeouts is not None and secs_in_half < 300 and not _scored_now and not _at_warning:
        other = 'away' if pos == 'home' else 'home'
        # nothing to stop after a score (the clock is dead at the whistle) or on the play that reaches the
        # two-minute warning (the warning stops it for free)
        in_bounds = t in ('run', 'scramble', 'complete', 'sack')          # the clock runs after these; nothing to stop after an incompletion
        # the defense stops the clock in the last three minutes of the GAME when it trails; in the first
        # half only a two-score deficit is worth a timeout to get the ball back before the break
        if dr.score_diff > 0 and in_bounds and timeouts.left.get(other, 0) > 0 and half_end is None and secs_in_half < 180:
            used = timeouts.use(other); used_by = other                    # the end of the game: the trailing defense stops the clock
        elif dr.score_diff > 0 and in_bounds and timeouts.left.get(other, 0) > 0 and half_end is not None and (plan is None or not plan.get('hurry', True)):
            # BEFORE THE HALF the trailing defense buys time back only when it is worth a possession: the offense
            # ahead is letting the clock run toward a late kick (or is out of the plan's window and moving slowly),
            # and each timeout now is seconds the defense gets after the score. Its coach's appetite sets the bar.
            d_aggr = float(np.clip(0.5 * float((dcoach or {}).get('fourth_down', 0.5)) + 0.5 * float((dcoach or {}).get('adjust_willingness', 0.5)), 0.0, 1.0))
            tos_d = timeouts.left.get(other, 0)
            # THE STOP IS THE POINT. After this play the offense has (4 - down) snaps before it must punt; the
            # defense gets the ball only if the series fails, and the time it gets is what is left after those
            # snaps. A timeout now saves one clock-run snap's worth of time; the value is that saving times the
            # odds of the stop. After a first down the odds are low and the offense has three chances left, so the
            # timeout waits; on third and long it is worth spending.
            nd = int(getattr(dr, 'down', 1)); togo = float(getattr(dr, 'togo', 10.0))
            remaining = max(1, 4 - nd)                          # snaps before the punt, counting the one just run as done
            p_stop = 0.28 if nd <= 1 else (0.40 if togo >= 4 else 0.25) if nd == 2 else (0.62 if togo >= 7 else 0.48 if togo >= 3 else 0.32)
            later = 0.65 * PLAY_SECS_RUN + 0.35 * PLAY_SECS                  # a later snap stops the clock itself a third of the time
            after_with = max(0.0, secs_in_half - PLAY_SECS * min(remaining, tos_d) - later * max(0, remaining - tos_d) - 6.0)
            after_without = max(0.0, secs_in_half - PLAY_SECS_RUN - later * (remaining - 1) - 6.0)
            # what the defense gets if the series fails: a possession, worth less when it needs touchdowns (down
            # two scores a field-goal drive is nearly nothing to it)
            need_td = 0.35 if dr.score_diff >= 9 else 1.0
            d_gain = need_td * (_possession_value(after_with, max(0, tos_d - min(remaining, tos_d))) - _possession_value(after_without, tos_d))
            # ...and what the offense gets if the series lives: the stopped clock is its time too, and it is the one
            # driving. Past midfield with the clock short, that is most of the value of the stop handed to them.
            o_gain = 0.6 * (_possession_value(after_with + 12.0, timeouts.left.get(pos, 0)) - _possession_value(after_without + 12.0, timeouts.left.get(pos, 0))) * (1.4 if dr.yardline <= 50 else 0.7)
            gain = p_stop * d_gain - (1.0 - p_stop) * o_gain
            # ...AGAINST WAITING FOR THIRD DOWN. With snaps still to come, the timeout can be held for the series'
            # last one, where the stop is likelier and every timeout is still in hand; a conversion in between
            # costs nothing. The timeout is spent now only when now beats that.
            if remaining > 1:
                secs_3rd = secs_in_half - PLAY_SECS_RUN - later * (remaining - 2)
                if secs_3rd > 6:
                    w3 = max(0.0, secs_3rd - PLAY_SECS - 6.0); wo3 = max(0.0, secs_3rd - PLAY_SECS_RUN - 6.0)
                    gain_later = 0.50 * need_td * (_possession_value(w3, tos_d - 1) - _possession_value(wo3, tos_d))
                    if gain_later >= gain: gain = 0.0
            if gain * (0.75 + 0.5 * d_aggr) > 0.06:                  # first-half timeouts do not carry past the break; a modest gain is worth one
                used = timeouts.use(other); used_by = other
        elif (plan is None or plan.get('hurry', True)) and ((-8 <= dr.score_diff < 0 and secs_in_half < trail_window) or (dr.score_diff == 0 and secs_in_half < 40)) and in_bounds and secs_in_half > 6 and timeouts.left.get(pos, 0) > 0:
            used = timeouts.use(pos); used_by = pos                        # one score down inside a minute, or tied at the very end; down two the offense runs the hurry-up and keeps them for the defense
        elif plan is not None and plan['choice'] != 'kneel' and plan.get('hurry', True) and in_bounds and secs_in_half > 4 and timeouts.left.get(pos, 0) > 0:
            used = timeouts.use(pos); used_by = pos                        # the clock is running on a spot worth a kick or a shot, and the plan needs the time
        elif plan is not None and not plan.get('hurry', True) and in_bounds and timeouts.left.get(other, 0) > 0 and dr.score_diff >= 0 and (half_end is None or dr.score_diff == 0):
            # THE DEFENSE BUYS ITSELF A POSSESSION. The offense is bleeding the clock toward a late kick; each
            # timeout the defense spends now is time it gets back after the score. It spends one when that time
            # is worth a real possession to it, by its own coach's appetite for the chance.
            d_aggr = float(np.clip(0.5 * float((dcoach or {}).get('fourth_down', 0.5)) + 0.5 * float((dcoach or {}).get('adjust_willingness', 0.5)), 0.0, 1.0))
            need_d = max(0, int(round(dr.score_diff)))
            after_now = max(0.0, secs_in_half - 4.0)
            after_bleed = max(0.0, secs_in_half - PLAY_SECS_RUN * (1 + int((secs_in_half - 5.0) // PLAY_SECS_RUN)) - 4.0)
            gain = _possession_value(after_now, timeouts.left.get(other, 0) - 1, half_end is None, need_d + 3) - _possession_value(after_bleed, timeouts.left.get(other, 0), half_end is None, need_d + 3)
            if gain * (0.75 + 0.5 * d_aggr) > (0.25 if half_end is not None else 0.08):
                used = timeouts.use(other); used_by = other
    return used, used_by


def _tick(dr, secs):
    """Take seconds off the clock; a deduction that crosses a quarter's edge stops there (the quarter ends, the next snap is at 15:00)."""
    before = dr.clock
    dr.clock -= secs
    for edge in (2700.0, 1800.0, 900.0):
        if before > edge >= dr.clock: dr.clock = float(edge); break
    dr.clock = float(np.ceil(dr.clock - 1e-9))                          # whole seconds


def returner_for(ros, state, rate_fn, kind='kr'):
    """The club's return man for this kick: the charted one unless he is hurt or out, then the best healthy
    man among the return positions. A hurt returner kept returning kicks because the slot was fixed at kickoff."""
    out = state.out if state is not None else set()
    kr = ros.get(kind) or {}
    if kr and kr.get('pid') not in out: return kr
    import rosters as R
    cands = [p for grp in ('wr', 'db', 'backs') for p in (ros.get(grp) or []) if p and p.get('pid') not in out and p.get('pos') in R.RETURN_POS]
    if ros.get('rb') and ros['rb'].get('pid') not in out: cands.append(ros['rb'])
    return max(cands, key=R.return_score) if cands else (kr or {})


def kickoff_booked(returner, rng, rate_fn, book, from_50=False):
    """kickoff(), and the return goes in the book against the returner. Kickoff returns were resolved
    for years and never booked, so no kick returner had a line. The result is kept so the drive it
    opens can log the kick as its first play."""
    r = kickoff(returner, rng, rate_fn, from_50=from_50)
    if not r.get('touchback'):
        import events as E
        flag = E.special_teams_penalty_check(rng, 'kickoff', returned=True)
        if flag:
            walk = min(flag['yards'], (100.0 - r['new_yardline']) / 2.0)
            flag['yards'] = walk
            r['new_yardline'] += walk
            r['penalty'] = flag
    if book is not None and not r.get('touchback') and returner:
        book.special('kr', returner.get('pid'), ret=r.get('ret', 0.0))
    r['returner'] = (returner or {}).get('pid')
    LAST_KICKOFF['r'] = r
    return r


def kickoff(returner, rng, rate_fn, AVG=0.70, from_50=False):
    if rng.random() < KICKOFF['touchback']:
        spot = KICKOFF['touchback_from_50'] if from_50 else KICKOFF['touchback_to']
        return dict(type='kickoff', touchback=True, new_yardline=spot)
    skill = rate_fn(returner, {'kick_ret_rating': .45, 'speed_rating': .30,
                               'juke_move_rating': .25})
    # the returner is the club's best now, not its last receiver: the skill term is centered on
    # the typical chosen returner, so the league mean stays at the real 26.9
    ret = min(98.0, rng.gamma(7.0, KICKOFF['return_mean'] / 7.0) * (1.0 + 0.8 * (skill - RET_AVG)))     # 2024-25: mean 27.6 with most returns 20 to 35; a 50-yarder is a few a season, not two a game
    # the landing zone runs from the goal line to the 20, so a returned kick
    # starts from roughly the 5 and the return is measured from there
    start = 5.0 + ret
    return dict(type='kickoff', touchback=False, ret=round(float(ret), 1),
                new_yardline=float(np.clip(100 - start, 1, 99)))

# ============================================================ TEAM STATE
class TeamState:
    """
    Live health for one team. Condition and injuries were built but nothing
    called them, so nobody tired, nobody rotated and nobody got hurt during an
    actual game. This is what connects them.
    """
    def __init__(self, roster, policy=0.5, plan=None, coach=None, scheme=None):
        import health as H, gameplan as GP, adjust as AD, targets as TG
        self.roster = roster
        self.plan = plan if plan is not None else GP.base_plan(coach)
        # the plan he walks in with, kept so every game starts from it
        self.base_plan = self.plan.copy()
        self.coach = coach or {}
        self.scheme = scheme
        self.mem = AD.GameMemory()
        # Walsh's opener, run before the defence can counter. Off-script
        # performance is measurably worse for some callers: Shanahan's 2022
        # San Francisco had +0.32 passing EPA on script and -0.10 off it.
        self.script = AD.Script(length=int((coach or {}).get('script_length', 15)),
                                off_script_skill=float((coach or {}).get(
                                    'off_script_skill', 0.5)))
        self.last_adjustment = None      # what the OTHER side just did to us
        self.chart = None
        self.cond = H.Condition(policy)
        self.jaded = {}          # pid -> 0-1, carries across a season
        self.injuries = []       # this game's injuries
        self.cov_memory = {}     # what his coverage calls have produced
        self.out = set()         # unavailable right now
        self.snaps = {}

    def available(self, group, position):
        """Men at this position who are not hurt, deepest-first order kept."""
        return [p for p in group if p.get('pid') not in self.out] or list(group)

    def pick(self, group, position, rng, stamina_key='stamina_rating'):
        """
        Who takes this snap. Walks the depth chart until someone is fresh
        enough to go - which is what actually produces rotation.
        """
        import health as H
        men = self.available(group, position)
        for rank, p in enumerate(men):
            pid = p.get('pid', f'{position}{rank}')
            gap = 0.6 if rank == 0 and len(men) > 1 else 0.0
            if not self.cond.needs_rest(pid, position, rng,
                                        p.get(stamina_key, 70.0), gap):
                return p, rank
        return men[-1], len(men) - 1

    def snap(self, player, position, on_field=True):
        import health as H
        pid = player.get('pid', position)
        if on_field:
            self.cond.play(pid, position, player.get('stamina_rating', 70.0), effort=getattr(self, 'road_stamina', 1.0))
            self.snaps[pid] = self.snaps.get(pid, 0) + 1
        else:
            self.cond.rest(pid, position)

    def state(self, player, position):
        """The player as he actually is, condition applied."""
        import health as H
        pid = player.get('pid', position)
        return H.apply_state(player, self.cond.get(pid))

    def hurt(self, player, position, contact, rng, rate_fn, week=1):
        import health as H
        pid = player.get('pid', position)
        # A man already ruled out cannot be hurt again. Without this the same
        # back was injured three times in one game.
        if pid in self.out:
            return None
        inj = H.roll_injury(player, position, contact, rng, rate_fn,
                            condition=self.cond.get(pid),
                            jaded=self.jaded.get(pid, 0.0))
        if inj:
            inj['week'] = week
            self.injuries.append(inj)
            self.out.add(pid)
        return inj

    def rebuild_chart(self):
        """Order every position group by POSITION-SPECIFIC rating."""
        import targets as TG
        groups = {}
        for key, pos in (('wr', 'WR'), ('ol', 'LT'), ('dl', 'DT'),
                         ('lb', 'MIKE'), ('db', 'CB')):
            if key in self.roster:
                groups[key] = TG.order_depth(self.roster[key], pos,
                                             self.scheme, self.out)
        self.chart = groups
        return groups

    def sideline_recovery(self, snaps=30):
        """
        This unit is OFF THE FIELD while the other side plays. Real players
        recover on the bench between series; without this, condition collapsed
        to a mean of 53 by the end of a game - with some men at zero - which
        drove the injury multiplier to 16.7x and produced 4-5 men ruled out per
        team per game against a real 2.51.
        """
        for pid in list(self.cond.cond):
            self.cond.rest(pid)
            for _ in range(max(0, int(snaps * 0.55)) // 6):
                self.cond.rest(pid)

    def new_series(self):
        self.mem.new_series()

    def observe(self, off_call, def_call, outcome):
        self.mem.record(off_call, def_call, outcome)

    def remember_coverage(self, call, yards, sack=False, turnover=False):
        """
        What has been WORKING. A coordinator leans on a call that is getting
        stops and drops one that is not, and he does it inside the game rather
        than waiting for the film.

        Kept as a running score per call, decayed so an early stop does not
        justify the same call all afternoon.
        """
        if not call:
            return
        good = -0.55 if turnover or sack else (0.28 if yards >= 7 else
                                               (-0.30 if yards <= 2 else 0.0))
        for k in list(self.cov_memory):
            self.cov_memory[k] *= 0.93
        # a NEGATIVE outcome for the offence is a positive for this call, so
        # the sign flips: the memory is the defence's, not the offence's
        self.cov_memory[call] = float(np.clip(
            self.cov_memory.get(call, 0.0) - good, -1.2, 1.2))

    def adjust(self, quarter=1, rng=None):
        """Read the trends and modify THE PLAN. Returns what changed."""
        if rng is None:
            import numpy as _np
            rng = _np.random.default_rng()
        import adjust as AD, gameplan as GP
        skill = float(self.coach.get('adjust_skill', 0.5))
        aggr = float(self.coach.get('adjust_willingness', 0.5))
        trends = AD.detect(self.mem, skill=skill)
        ctr = AD.respond(trends, skill=skill, aggressiveness=aggr,
                         rng=rng)
        if not ctr:
            return []
        self.plan, applied = GP.adjust_plan(self.plan, ctr, skill, 0.55, quarter)
        if applied:
            self.last_adjustment = ctr
        return applied

    def end_game(self, rng, expected_snaps=45.0, bye=False):
        """Recovery and jadedness roll forward between games."""
        import health as H
        self.last_snaps = dict(self.snaps)     # keep the game log readable
        fitness = {}
        try:
            for grp in (self.roster or {}).values():
                if isinstance(grp, list):
                    for p in grp:
                        if isinstance(p, dict) and p.get('pid'):
                            # natural fitness: durability and toughness, the body's rate of recovery
                            fitness[p['pid']] = 0.6 * float(p.get('injury_rating', 80) or 80) + 0.4 * float(p.get('tough_rating', 80) or 80)
        except Exception: pass
        for pid, n in self.snaps.items():
            self.jaded[pid] = H.update_jadedness(self.jaded.get(pid, 0.0), n,
                                                 fitness.get(pid, 70.0), expected_snaps, bye)
        # CONDITION CARRIES BETWEEN GAMES. A player leaves the field at whatever the game took from him and recovers
        # over the week at his body's rate, slowed by how worn the season has left him; a bye week restores him. The
        # old rule reset everyone to 100 after every game, so the roster's Condition never moved and December was
        # no harder than September. Recovery at full fitness is nearly complete in seven days; a jaded starter in
        # December comes back at 90 to 95, and plays the next game a little slower and a little more breakable
        ended = dict(self.cond.cond)
        self.cond.reset_game()
        if not bye:
            for pid, c in ended.items():
                self.cond.cond[pid] = H.recover_between_games(float(c), natural_fitness=fitness.get(pid, 70.0), days_rest=7,
                                                              jadedness=self.jaded.get(pid, 0.0))
        self.snaps = {}
        self.injuries = []
        self.cov_memory = {}
        # A GAME PLAN IS FOR A GAME. Adjustments made in one game (a max
        # protect with an 80/16/4 depth mix after a pressure read, a man
        # lean, a shell shift) were carried into the next and the next, so a
        # club that got pressured in September was throwing screens in
        # December: the shallow drift across a season. Each game now starts
        # from the plan the coach walks in with; what carries between games
        # is what he learned, not what he did about it.
        import gameplan as GP, adjust as AD
        if getattr(self, 'base_plan', None) is not None:
            travel, target, bracket = self.plan.travel, self.plan.travel_target, self.plan.bracket
            self.plan = self.base_plan.copy()
            self.plan.travel, self.plan.travel_target, self.plan.bracket = travel, target, bracket
        self.mem = AD.GameMemory()
        self.last_adjustment = None
        self.seq = {'run_hot': 0.0}
        # The opener belongs to one game. Keep the coach's script and skill,
        # but start its sequence again next week (and after a bye).
        self.script.used = 0
        self.script.active = True
        # THE OUT LIST WAS NEVER CLEARED. hurt() refuses to roll for a man
        # already on it, so once a player was hurt he stopped being able to be
        # hurt again FOR THE REST OF THE SEASON - and so did everyone else, one
        # by one, until almost nobody on the roster could get injured at all.
        # Week one produced about six injuries a team and the season averaged
        # 0.96 against a real 2.51; the rate was never the problem.
        #
        # Who is ACTUALLY unavailable is the League's business - it holds
        # out_until on the player and the season rebuilds the units from men
        # who are fit. This list only exists to stop the same man being hurt
        # twice inside one game, so it belongs to the game and dies with it.
        self.out = set()

# ============================================================ DRIVE
def _ep_state(down, togo, spot):
    """Expected points for the offense with the ball at spot (yards to the goal), from the offense's view."""
    import advanced_stats as AS
    return float(AS.ep(int(down), float(togo), float(spot)))


def _ep_play_stands(dr, out):
    """The offense's expected points if the play is allowed to stand: the next down and spot, a first down, a
    touchdown, a turnover, or a failed fourth down handing the ball over."""
    import advanced_stats as AS
    gained = float(np.round(float(out.get('yards') or 0.0)))
    if out.get('touchdown') or float(out.get('yards') or 0.0) >= dr.yardline - 0.01 or gained >= dr.yardline - 0.01: return float(AS.TD_VALUE)
    spot = float(np.clip(dr.yardline - gained, 1.0, 99.0))
    if out.get('type') == 'interception':
        spot = _interception_spot(dr.yardline, out)
        return -_ep_state(1, 10, 100.0 - spot)
    if out.get('fumble_lost'):
        return -_ep_state(1, 10, 100.0 - spot)
    if gained >= dr.togo - 0.01:
        return _ep_state(1, min(10.0, spot), spot)
    if dr.down >= 4:
        return -_ep_state(1, 10, 100.0 - spot)                     # a failed fourth down is the other side's ball
    return _ep_state(dr.down + 1, dr.togo - gained, spot)


def _resolve_live_penalty(dr, pen, out, oc):
    """
    A foul during or after the play. Returns 'replaced' if the penalty is taken instead of the play, 'added' if
    it is tacked on after it, None if declined.

    THE RULE: the side that did not foul looks at both outcomes, the play standing and the penalty enforced, and
    takes whichever is better for it. Both are whole game states (down, distance, spot, possession) valued in
    expected points, so a failed fourth down that stands is a change of possession and the comparison sees it,
    and a defense would rather face second and goal from the 9 than first and goal from the 12. A dead-ball foul
    after the whistle is not a choice; it is added to whatever the play produced.
    """
    import events as E
    # INTERFERENCE NEEDS A BALL THROWN TO THE RECEIVER DOWNFIELD. The flag is drawn before the play resolves. If
    # the quarterback was sacked or scrambled, the call became a run, or the throw was a screen or behind the
    # line, the contact that drew the flag was holding, not interference: the foul is renamed and enforced as
    # holding (five and an automatic first on the defense, ten on the offense), not thrown away
    thrown = out.get('type') in ('complete', 'incomplete', 'interception', 'drop')
    downfield = thrown and not out.get('screen') and (out.get('air') is None or float(out.get('air') or 0.0) >= 1.0)
    # FOULS THAT DEPEND ON HOW THE PLAY ENDED. Grounding is a throw away to nobody: it needs an incompletion, and
    # on a completion, a pick or a sack there was no grounding. Ineligible downfield needs a ball thrown at all.
    if pen['penalty'] == 'Intentional Grounding' and not (out.get('type') == 'incomplete' and out.get('throwaway') and out.get('pressured')):
        return None
    if pen['penalty'] == 'Ineligible Downfield Pass' and not thrown:
        return None
    if pen['penalty'] in ('Roughing the Passer', 'Illegal Contact') and not thrown:
        return None
    if pen['penalty'] == 'Defensive Pass Interference' and not downfield:
        pen['penalty'] = 'Defensive Holding'; pen['yards'] = pen['rule_yards'] = 5.0; pen['auto_first'] = True
    elif pen['penalty'] == 'Offensive Pass Interference' and not downfield:
        pen['penalty'] = 'Offensive Holding'; pen['yards'] = pen['rule_yards'] = 10.0; pen['auto_first'] = False
    yards = float(pen['yards'])
    gained = float(out.get('yards') or 0.0)
    spot_gain = dr.yardline if gained >= dr.yardline - 0.01 else float(np.round(gained))
    if pen['on_offense']:
        if pen['penalty'] == 'Intentional Grounding':
            yards = max(yards, float(out.get('throwback', 0.0) or 0.0))
            pen['yards'] = yards
            if dr.yardline + float(out.get('throwback', 0.0) or 0.0) >= 100.0:
                pen['safety'] = True
                dr.yardline = 100.0
                dr.result, dr.points = 'Safety', -2
                return 'replaced'
        if E.PEN_INFO[pen['penalty']]['phase'] == 'post':
            spot = max(0.0, dr.yardline - spot_gain)
            if spot <= 0:
                dr.try_penalty = -yards
                pen['on_try'] = True
                return 'added'
            yards = min(yards, (100.0 - spot) / 2.0); pen['yards'] = yards
            dr.log_pen_after = -yards                 # the offense fouled after the whistle: it walks back
            return 'added'
        # THE DEFENSE DECIDES: the play standing against the down replayed from further back
        yards = min(yards, (100.0 - dr.yardline) / 2.0); pen['yards'] = yards
        ep_stand = _ep_play_stands(dr, out)
        down_e = dr.down + (1 if pen['penalty'] == 'Intentional Grounding' else 0)
        spot_e = dr.yardline + yards
        ep_enf = -_ep_state(1, 10, 100.0 - spot_e) if down_e > 4 else _ep_state(down_e, dr.togo + yards, spot_e)
        if ep_enf >= ep_stand:
            return None                               # the play as it stands is worse for the offense: the defense declines
        dr.yardline = spot_e
        dr.togo += yards
        if pen['penalty'] == 'Intentional Grounding':
            dr.down += 1                          # loss of down
        return 'replaced'
    if out.get('touchdown') or gained >= dr.yardline - 0.01 or float(np.round(gained)) >= dr.yardline:
        if E.PEN_INFO[pen['penalty']]['phase'] == 'post':
            dr.try_penalty = yards
            pen['on_try'] = True
            return 'added'
        return None                               # the play stands; the offense declines the live foul
    if pen['penalty'] == 'Defensive Pass Interference':
        # A SPOT FOUL FOLLOWS THE THROW: the yardage is where the ball was going (the flag was drawn before the
        # play resolved, at a generic 13-yard median, so a screen once came back with a 20-yard DPI)
        if out.get('air') is not None:
            yards = float(max(1, int(round(float(out['air'])))))
            pen['yards'] = yards
    if E.PEN_INFO[pen['penalty']]['phase'] == 'post':
        spot = max(0.0, dr.yardline - spot_gain)
        yards = min(yards, spot / 2.0); pen['yards'] = yards
        dr.log_pen_after = yards                      # the defense fouled: the offense walks forward
        dr.log_pen_first = bool(pen['auto_first'])
        return 'added'
    # THE OFFENSE DECIDES: the play standing against the penalty enforced
    if pen['penalty'] == 'Defensive Pass Interference':
        end_zone = yards >= dr.yardline
        gained_p = (dr.yardline / 2.0 if dr.yardline < 2 else dr.yardline - 1.0) if end_zone else yards
    else:
        gained_p = min(yards, dr.yardline / 2.0)   # every other foul: half the distance to the goal
        end_zone = False
    pen_first = bool(pen['auto_first']) or gained_p >= dr.togo - 0.01
    spot_e = max(0.5, dr.yardline - gained_p)
    ep_enf = _ep_state(1, min(10.0, spot_e), spot_e) if pen_first else _ep_state(dr.down, dr.togo - gained_p, spot_e)
    ep_stand = _ep_play_stands(dr, out)
    if ep_stand >= ep_enf:
        return None                               # the play did better: the offense declines
    if end_zone: pen['end_zone'] = True; pen['spot'] = dr.yardline - gained_p
    pen['yards'] = float(gained_p)
    dr.yardline -= gained_p
    if pen_first:
        dr.down, dr.togo = 1, min(10.0, dr.yardline); dr.first_downs += 1
    else:
        dr.togo -= gained_p
    return 'replaced'

class Drive:
    """One possession: downs, field position and the plays that move them."""
    def __init__(self, offense, defense, start_yardline, clock, quarter,
                 score_diff, rng):
        self.off, self.deff = offense, defense
        self.yardline = float(start_yardline)     # yards to opponent end zone
        self.down, self.togo = 1, 10
        self.clock, self.quarter = clock, quarter
        self.score_diff = score_diff
        self.rng = rng
        self.plays, self.first_downs = 0, 0
        self.start = float(start_yardline)        # where it began, for analysis
        self.best = float(start_yardline)         # closest it ever got
        self.result, self.points = None, 0
        self.try_result = None
        self.log = []

def _interception_spot(yardline, out):
    """The former offense's distance to goal after the catch and return."""
    caught = float(yardline) - float(out.get('air', 0.0) or 0.0)
    if caught <= 0:
        return 20.0                         # defensive touchback in the end zone
    return float(np.clip(caught + float(out.get('ret', 0.0) or 0.0), 1.0, 99.0))

def _enforce_turnover_penalty(dr, pen):
    """Walk a dead-ball foul from the turnover's return spot, in the old offense's coordinates."""
    nominal = float(pen.get('rule_yards', pen['yards']))
    if pen['on_offense']:
        walk = min(nominal, (100.0 - dr.yardline) / 2.0)
        dr.yardline += walk                 # new offense advances toward the old offense's goal
    else:
        walk = min(nominal, dr.yardline / 2.0)
        dr.yardline -= walk                 # new offense is walked back
    pen['yards'] = walk
    dr.log_pen_after = 0.0
    dr.log_pen_first = False

def _kick_presnap_flag(dr, pen):
    """A pre-snap kick foul keeps the same down and lets the coach decide again."""
    if not pen or pen.get('phase') != 'pre': return False
    if pen['on_offense']:
        walk = min(pen['yards'], (100.0 - dr.yardline) / 2.0)
        dr.yardline += walk; dr.togo += walk
    else:
        walk = min(pen['yards'], dr.yardline / 2.0)
        dr.yardline -= walk; dr.togo -= walk
        if dr.togo <= 0:
            dr.down, dr.togo = 1, min(10.0, dr.yardline)
            dr.first_downs += 1
        dr.untimed = True; dr.untimed_at = len(dr.log) + 1
    pen['yards'] = walk
    dr.log.append(dict(type='penalty', **pen))
    return True

def _kick_roughing(dr, pen, kick):
    """Accept roughing when the failed kick or punt is worse than a first down."""
    if not pen or pen.get('phase') != 'kick' or kick.get('made') or kick.get('blocked'): return False
    kick['nullified'] = True
    dr.log.append(kick)
    walk = min(pen['yards'], dr.yardline / 2.0)
    pen['yards'] = walk
    dr.yardline -= walk
    dr.down, dr.togo = 1, min(10.0, dr.yardline)
    dr.first_downs += 1
    dr.log.append(dict(type='penalty', **pen))
    return True

def _kick_offside(dr, pen, kick):
    """The kicking side may keep a made FG or a good punt; otherwise it can replay the down."""
    if not pen or pen.get('phase') != 'kick_offside' or kick.get('made'):
        return False
    walk = min(pen['yards'], dr.yardline / 2.0)
    if kick.get('type') == 'punt' and not kick.get('blocked') and walk < dr.togo:
        return False
    kick['nullified'] = True
    dr.log.append(kick)
    dr.yardline -= walk
    dr.togo -= walk
    pen['yards'] = walk
    if dr.togo <= 0:
        dr.down, dr.togo = 1, min(10.0, dr.yardline)
        dr.first_downs += 1
    dr.log.append(dict(type='penalty', **pen))
    return True

def _advance(dr, gained):
    """Apply yardage, update downs and field position. Whole yards only."""
    raw_gained = float(gained)
    gained = dr.yardline if raw_gained >= dr.yardline else float(np.round(raw_gained))
    # Decide the play's down and score before walking off a dead-ball foul.
    after = getattr(dr, 'log_pen_after', 0.0)
    pen_first = getattr(dr, 'log_pen_first', False)
    dr.log_pen_after = 0.0
    dr.log_pen_first = False
    dr.yardline -= gained
    dr.togo -= gained
    dr.best = min(dr.best, max(0.0, dr.yardline))
    if dr.yardline <= 0:
        # Six. The try is resolved at the end of run_drive, where the kicker
        # and the play engine are both in scope.
        dr.yardline = 0.0                                           # the drive ends at the goal line
        dr.result, dr.points = 'Touchdown', 6
        return True
    if dr.yardline >= 100:
        dr.result, dr.points = 'Safety', -2
        return True
    if dr.togo <= 0:
        dr.down, dr.togo = 1, min(10, dr.yardline)
        dr.first_downs += 1
    else:
        dr.down += 1
    if after:
        dr.yardline -= after
        if pen_first and dr.down != 1:
            dr.down = 1
            dr.first_downs += 1
        if dr.down == 1:
            dr.togo = min(10, dr.yardline)
        else:
            dr.togo -= after
        dr.best = min(dr.best, max(0.0, dr.yardline))
    return False

def _prepare_scoring_play(dr, out):
    """Give the play log and stat book the distance actually gained before booking the snap."""
    if out.get('type') not in ('run', 'complete', 'scramble') or out.get('nullified'):
        return
    yards = float(out.get('yards', 0.0) or 0.0)
    scored = yards >= dr.yardline - 0.01 or float(np.round(yards)) >= dr.yardline - 0.01
    out['touchdown'] = scored
    if scored:
        out['yards'] = dr.yardline

# Eleven men a side. QB + RB + 5 OL + 3 WR/TE on offence; 4 DL + 2 LB + 5 DB
# in nickel, which is the league's base defence. The first build fielded five
# receivers, five linemen and four linebackers every snap - sixteen defenders -
# which made every backup a starter and flattened the snap distribution.
# Real carry share by rank within a team-season: 48.9 / 22.9 / 11.4 / 6.9 / 3.7
# (the third-ranked ball carrier on a typical team is the QUARTERBACK, at 52
# carries, which scrambles already supply).
CARRY_SHARE = [0.56, 0.24, 0.13, 0.07]

def pick_runner(backs, state, rng, gameplan=None):
    """
    Who carries it. Nothing decided this before, so one back took every carry
    and finished with 462 attempts and 3,788 yards against a real 334 and 1,763.
    Condition and injury are honoured, so a tiring starter cedes carries.
    """
    if not backs: return None, 0
    avail = [b for b in backs
             if state is None or b.get('pid') not in state.out] or backs
    n = min(len(avail), len(CARRY_SHARE))
    w = np.array(CARRY_SHARE[:n], float)
    # a worn-down back gets fewer. The lead back is on the field every snap
    # (the 'rb' slot never rotates) so his condition always sits under the
    # bench's; at 0.35 + 0.65 x condition that handed the backups most of
    # the carries and the league's leading rusher was a third-stringer with
    # 298 carries and 188 snaps. Real lead backs take 55-60% of carries.
    if state is not None:
        w = w * np.array([0.80 + 0.20 * (state.cond.get(b.get('pid')) / 100.0)
                          for b in avail[:n]])
    w = w / w.sum()
    i = int(rng.choice(n, p=w))
    return avail[i], i


# five skill slots: the package chooses up to five men (receivers, tight ends, a second back)
# and every one of them gets on the field. With three slots the tight end in 11 personnel
# was the fourth man in the list and sat unless a receiver was resting.
OFF_SLOTS = [('ol', ['LT', 'LG', 'C', 'RG', 'RT']), ('wr', ['WR', 'WR', 'WR', 'WR', 'WR'])]
# the slot lists are as long as the biggest package needs: heavy fields five linemen and
# four linebackers, dime six defensive backs. Shorter lists cut the package's last man.
DEF_SLOTS = [('dl', ['LEDG', 'DT', 'DT', 'REDG', 'DT']),
             ('lb', ['MIKE', 'WILL', 'SAM', 'MIKE']),
             ('db', ['CB', 'CB', 'CB', 'FS', 'SS', 'CB'])]
# without a package (a call that names no personnel) the defence is the nickel shape
NO_PACKAGE_SLOTS = {'dl': 4, 'lb': 2, 'db': 5, 'wr': 4, 'ol': 5}

POS_KEY = {'WR': 'wr', 'TE': 'wr', 'HB': 'wr', 'CB': 'db', 'FS': 'db',
           'SS': 'db', 'LB': 'lb', 'DL': 'dl'}

def package_units(roster, state, rng, is_offense, package, front_family=None):
    """
    Which men the PACKAGE puts on the field. This is the piece fatigue alone
    cannot produce: five DBs play every snap in nickel, so without packages the
    top five are permanently starters and the sixth never appears.
    """
    import targets as TG
    spec = (TG.OFF_PACKAGES if is_offense else TG.DEF_PACKAGES).get(package)
    if not spec:
        return None
    out = {}
    family = front_family or roster.get('front_family', '4-3')
    import defense_roles as DR
    family = DR.front_family(family)
    if not is_offense and roster.get('depth'):
        # Select from canonical, available depth for THIS call. Cached dl/lb
        # groups may describe a different front, or still contain a man hurt
        # earlier in the game. Keep reserves until package selection is done.
        unavailable = state.out if state is not None else ()
        depth = DR.available_depth(roster['depth'], unavailable)
        roster = dict(roster, depth=depth)
        assignments = DR.assign(depth, family, package, roster.get('depth_pins'))
        dl = [row['player'] for row in assignments
              if row['group'] == 'dl' and row['player'] is not None]
        chosen = {p['pid'] for p in dl}
        roster['dl'] = dl + [p for pos in ('LEDG', 'DT', 'REDG')
                            for p in depth.get(pos, ()) if p['pid'] not in chosen]
        roster['lb'] = ([p for pos in ('MIKE', 'WILL', 'SAM') for p in depth.get(pos, ())[:1]] +
                        [p for pos in ('MIKE', 'WILL', 'SAM') for p in depth.get(pos, ())[1:]])
        roster['db'] = [p for pos in ('CB', 'FS', 'SS') for p in depth.get(pos, ())]
    if not is_offense and roster.get('depth') and (
            family == '3-4' or DR.needs_fallback(roster['depth'], family, package)):
        used_reserves = set()
        for row in assignments:
            chosen = row['player']
            if chosen is None:
                continue
            reserves = [p for p in row['reserves'] if p['pid'] not in used_reserves]
            role = row['role']
            rotation = (0.32 if row['group'] == 'dl' else
                        0.20 if row['group'] == 'lb' else
                        0.06 if role == 'CB' else 0.02)
            if reserves and rng.random() < rotation:
                chosen = reserves[0]
                used_reserves.add(chosen['pid'])
            out.setdefault(row['group'], []).append(chosen)
        return out
    if is_offense:
        import offense_roles as OR
        return OR.field(roster, package, rng=rng, state=state)
    else:
        db = list(roster.get('db', []))
        cbs = [d for d in db if d.get('pos') == 'CB']
        saf = [d for d in db if d.get('pos') in ('FS', 'SS')]
        n_cb = spec.get('CB', 3)
        # BIG NICKEL. The fifth defensive back is a third safety about a
        # third of the time in the real league, which is most of why the
        # third corner plays 57% of snaps and not 80%. The dime stays corners.
        if n_cb == 3 and len(saf) >= 3 and rng.random() < 0.34:
            n_cb = 2
            fss = [d for d in saf if d.get('pos') == 'FS']
            sss = [d for d in saf if d.get('pos') == 'SS']
            core = fss[:1] + sss[:1]
            out['db'] = cbs[:2] + (core + [d for d in saf if d not in core])[:3]
        else:
            # a free safety and a strong safety, not the first two in the list (a club with two free safeties was
            # fielding both and its strong safety never played)
            fss = [d for d in saf if d.get('pos') == 'FS']; sss = [d for d in saf if d.get('pos') == 'SS']
            pick = fss[:spec.get('FS', 1)] + sss[:spec.get('SS', 1)]
            for d in saf:
                if len(pick) >= spec.get('FS', 1) + spec.get('SS', 1): break
                if d not in pick: pick.append(d)
            out['db'] = cbs[:n_cb] + pick
        # the linebackers are the coordinator's call by the package's job, not the first N in the list
        lbs = [m for m in roster.get('lb', []) if m.get('pid') not in (state.out if state is not None else set())]
        chosen = TG.package_linebackers(lbs, package, scheme=None, key=lambda m: m)
        out['lb'] = [m for m, why in chosen][:spec.get('LB', 2)] or list(roster.get('lb', []))[:spec.get('LB', 2)]
        # THE FRONT ROTATES. Fatigue alone left the starting four at 92-94% of snaps;
        # real edges play 65-80% and interior linemen 55-70%, with the third edge at
        # 30-45% and the third and fourth tackles at 30-45 and 15-30. Each slot rotates
        # to the next man at its spot on a draw, with the interior turning over more.
        dl = list(roster.get('dl', [])); n_dl = spec.get('DL', 4)
        starters = dl[:n_dl]; depth = dl[n_dl:]
        def same_spot(a, b):
            ea = a.get('pos') in ('LEDG', 'REDG'); eb = b.get('pos') in ('LEDG', 'REDG'); return ea == eb
        fielded, used = [], set()
        # the starters are asked in a random order, so with one backup at the spot both
        # starters share the rest rather than the first-listed (the best) man taking it all
        order = list(range(len(starters))); rng.shuffle(order); fielded = [None] * len(starters)
        for idx in order:
            st_ = starters[idx]
            edge = st_.get('pos') in ('LEDG', 'REDG')
            p_rot = 0.30 if edge else 0.32
            subs = [d for d in depth if same_spot(d, st_) and d.get('pid') not in used]
            if subs and rng.random() < p_rot:
                # the first backup takes most of the rotation, the second a share
                pick = subs[0] if (len(subs) == 1 or rng.random() < (0.78 if edge else 0.68)) else subs[1]
                fielded[idx] = pick; used.add(pick.get('pid'))
            else:
                fielded[idx] = st_; used.add(st_.get('pid'))
        out['dl'] = fielded
    return out


def field_units(roster, state, rng, is_offense, package=None, front_family=None):
    """
    Put eleven men on the field for this snap, honouring condition and
    injuries. Anyone not selected recovers. This is where rotation actually
    happens - the depth chart is walked until someone is fresh enough.
    """
    if is_offense and package:
        import offense_roles as OR
        depth = OR.roster_depth(roster)
        selected = OR.field(roster, package, rng=rng, state=state, depth=depth)
        out = dict(roster); out.update(selected)
        rows = selected['offensive_assignments']
        positions = {OR.pid(p): OR.position(p) for role, p in rows}
        if state is not None:
            all_men = {OR.pid(p): p for men in depth.values() for p in men}
            for pid, p in all_men.items():
                state.snap(p, OR.position(p), pid in positions)
            transformed = {OR.pid(p): state.state(p, OR.position(p)) for role, p in rows}
            for key in ('qb', 'rb'):
                out[key] = transformed[OR.pid(selected[key])] if selected[key] is not None else None
            for key in ('ol', 'wr', 'backs', 'extra_blockers'):
                out[key] = [transformed[OR.pid(p)] for p in selected[key]]
        return out, positions
    if state is None:
        return roster, {}
    # the package decides WHO is eligible this snap; condition then decides
    # which of them actually goes
    pk = package_units(roster, state, rng, is_offense, package, front_family) if package else None
    if pk:
        roster = dict(roster); roster.update(pk)
    packaged = set(pk.keys()) if pk else set()
    out, positions = dict(roster), {}
    slots = OFF_SLOTS if is_offense else DEF_SLOTS
    if not is_offense:
        import defense_roles as DR
        default_slots = DR.counts(front_family or roster.get('front_family', '4-3'), 'nickel')
    else:
        default_slots = None
    if is_offense:
        for key in ('qb', 'rb'):
            if roster.get(key) is not None:
                pos = 'QB' if key == 'qb' else 'HB'
                p = roster[key]
                # THE BACK ROTATES LIKE EVERYONE ELSE. The rb slot was fixed
                # to the lead back every snap, so his condition hit zero by
                # the second quarter and the carry draw, which reads
                # condition, handed most carries to fresh backups who were
                # never on the field. Walk the backfield by condition the way
                # every other slot is walked; real lead backs play ~65% of
                # snaps and take 55-60% of carries.
                if key == 'rb':
                    backs = [b for b in (roster.get('backs') or [p]) if b and b.get('pid') not in state.out] or [p]
                    pick = None
                    for rank, b in enumerate(backs):
                        gap = 0.75 if rank == 0 and len(backs) > 1 else (0.3 if rank == 1 else 0.0)  # a coach commits to his lead back, short of riding him (353-carry seasons); the third back is an emergency
                        if not state.cond.needs_rest(b.get('pid'), 'HB', rng, b.get('stamina_rating', 70.0), gap):
                            pick = b; break
                    p = pick or backs[0]
                    for b in backs:
                        if b is not p: state.snap(b, 'HB', False)
                # an injured starter yields to the backup - real leagues carry
                # ~2.4 QBs taking meaningful snaps, which is most of why the
                # real QB15-to-QB25 distribution falls off a cliff
                if key == 'qb' and p.get('pid') in state.out:
                    bench = roster.get('qbs') or []
                    alt = next((q for q in bench
                                if q.get('pid') not in state.out), None)
                    if alt is not None: p = alt
                state.snap(p, pos, True)
                out[key] = state.state(p, pos)
                positions[p.get('pid')] = pos
    for key, poslist in slots:
        group = roster.get(key, [])
        if not group: continue
        # Walk the depth chart IN ORDER, skipping men who need rest and men
        # already on the field for another slot. Rotating the list per slot -
        # what the first build did - gave every player a turn as the starter
        # and produced a completely flat snap distribution.
        avail = state.available(group, poslist[0])
        used, chosen = set(), []
        # a package names exactly the men who play; without one, the default shape
        n_slots = len(group) if key in packaged else (default_slots.get(key, len(poslist)) if default_slots else NO_PACKAGE_SLOTS.get(key, len(poslist)))
        # WHO THE COACH COMMITS TO. The commitment (a longer stint before a breather) went to the first players in
        # the group list by rank, and in the receiving group that list runs every receiver before the first tight
        # end, so the starting tight end sat at rank six with no commitment and came off as readily as a fourth
        # receiver: tight ends played 70% of snaps and took 62% of their room's targets against a real 80 and 78.
        # The commitment now goes by role: the first three receivers, the first tight end and the first back.
        starters, seconds, seen = set(), set(), {}
        for p in avail:
            ps = p.get('pos'); k_ = 'WR' if ps == 'WR' else 'TE' if ps == 'TE' else 'HB' if ps in ('HB', 'FB') else ps
            seen[k_] = seen.get(k_, 0) + 1
            if seen[k_] <= (3 if k_ == 'WR' else 1 if k_ in ('TE', 'HB') else len(poslist)): starters.add(p.get('pid'))
            elif seen[k_] <= (4 if k_ == 'WR' else 2 if k_ in ('TE', 'HB') else len(poslist) + 1): seconds.add(p.get('pid'))
        for pos in poslist[:min(len(poslist), len(avail), n_slots)]:
            pick = None
            for rank, p in enumerate(avail):
                pid = p.get('pid')
                if pid in used: continue
                gap = 0.6 if pid in starters else (0.3 if pid in seconds else 0.0)
                if not state.cond.needs_rest(pid, pos, rng,
                                             p.get('stamina_rating', 70.0), gap):
                    pick = p; break
            if pick is None:
                pick = next((p for p in avail if p.get('pid') not in used),
                            avail[-1])
            used.add(pick.get('pid'))
            ppos = pick.get('pos') or pos
            state.snap(pick, ppos, True)
            chosen.append(state.state(pick, ppos))
            positions[pick.get('pid')] = ppos
        for p in group:
            if p.get('pid') not in used:
                state.snap(p, poslist[0], False)
        out[key] = chosen
    return out, positions

def run_drive(*args, **kwargs):
    """One possession, played to its end. Thin wrapper over drive_steps, which is the same code paused
    after every snap so a game can be played live; the AI's games and the register come through here."""
    gen = drive_steps(*args, **kwargs)
    try:
        while True: next(gen)
    except StopIteration as done:
        return done.value


def drive_steps(offense, defense, start_yardline, clock, quarter, score_diff,
              rng, resolve_fn, call_off, call_def, rate_fn, aggression=0.5,
              book=None, off_state=None, def_state=None, week=1,
              timeouts=None, pos='home', half_end=None):
    """
    Play a full possession. resolve_fn is plays.resolve_play; call_off/call_def
    are the scheme-layer callers.
    """
    dr = Drive(offense, defense, start_yardline, clock, quarter, score_diff, rng)
    import events as E
    # the kick that opened this possession, when there was one, is the drive's first entry
    ko = LAST_KICKOFF.pop('r', None)
    if ko is not None and abs(float(ko.get('new_yardline', -1)) - float(start_yardline)) < 0.5:
        dr.log.append(dict(type='kickoff', touchback=bool(ko.get('touchback')), new_yardline=float(ko.get('new_yardline', start_yardline)), ret=float(ko.get('ret', 0.0) or 0.0), carrier=ko.get('returner'), clock=clock, onside=bool(ko.get('onside')), recovered=bool(ko.get('recovered')), free_kick=bool(ko.get('free_kick'))))
        if ko.get('penalty'):
            dr.log.append(dict(type='penalty', **ko['penalty']))
    # Adjustment happens AFTER EACH SERIES, which is what the coaches describe:
    # "If you wait until halftime to make your adjustments, you're too late."
    for st in (off_state, def_state):
        if st is not None:
            st.new_series()
            # Adjustment is considered every series but does not fire every
            # series. Calling it unconditionally on ~11 drives produced 5.56
            # plan changes per team per game against the ~3 the standalone
            # calibration targeted.
            # Use the GAME's generator. A fresh unseeded one here made the
            # whole engine non-reproducible: the same seed produced a
            # different season every time, so no calibration run could be
            # compared to another and a real regression was indistinguishable
            # from noise. The register swung four rows between identical runs.
            if rng.random() < 0.55:
                st.adjust(quarter, rng)

    import advanced_stats as AS
    pending = None                        # the last scrimmage play, waiting for its after-state
    _seen = 0
    while dr.result is None:
        if len(dr.log) > _seen:
            _seen = len(dr.log); yield ('snap', dr)              # the book grew: a live game shows it before the next snap
        if pending is not None:
            _o, _off, _def, _st = pending
            _v = AS.epa(_o, _st[0], _st[1], _st[2], dr.down, dr.togo, dr.yardline)
            _o['epa'] = round(_v, 3); AS.book_play(book, _o, _off, _def, _v); pending = None
        wall = half_end if half_end is not None else 0.0
        if dr.clock <= wall and getattr(dr, 'untimed', False) and getattr(dr, 'untimed_at', -1) == len(dr.log):
            # a half does not end on an accepted defensive foul: one untimed down, only when the foul was the last thing to happen
            dr.untimed = False; dr.clock = wall + 1.0
        elif getattr(dr, 'untimed', False) and getattr(dr, 'untimed_at', -1) != len(dr.log):
            dr.untimed = False                                 # a snap has been run since the foul: the flag is stale
        elif dr.clock <= 0:
            dr.result = 'End of half'; break
        # THE HALF IS A WALL TOO. Without this the game ran as one continuous
        # 3600 seconds and only ONE drive a game was ever killed by a clock -
        # the last one. Real games kill two, one per half, and end-of-half
        # drives are 7.1% of all drives against the 4.0% this produced.
        if half_end is not None and dr.clock <= half_end:
            dr.clock = half_end
            dr.result = 'End of half'; break
        # 10. THE KNEEL. With the ball and no time to use it, out of range, a club takes a knee: the first half at
        # any score, the second half when it is not behind. Real clubs do not throw from their own 35 at 0:04.
        secs_left_half = dr.clock - wall
        opp_tos = timeouts.left.get('away' if pos == 'home' else 'home', 0) if timeouts is not None else 0
        clock_dies = secs_left_half <= 3 or (secs_left_half <= 10 and opp_tos == 0)
        _plan0 = end_of_half_plan(dr, offense, defense, rate_fn, timeouts, pos, half_end, secs_left_half, coach=(off_state.coach if off_state is not None else None))
        if clock_dies and secs_left_half > 0 and ((_plan0 is not None and _plan0['choice'] == 'kneel') or (_plan0 is None and ((half_end is None and dr.score_diff > 0) or (dr.yardline > 45 and dr.score_diff >= 0)))) and not getattr(dr, '_kneeled', False):
            dr._kneeled = True
            dr.log.append(dict(type='kneel', passer=(offense.get('qb') or {}).get('pid'), down=dr.down, ydstogo=dr.togo, yardline=dr.yardline, clock=dr.clock))
            dr.plays += 1; dr.clock = wall; dr.result = 'End of half'; break
        if dr.plays > 25:
            dr.result = 'End of half'; break

        # ---- THE CLOCK KICK. Down three or tied with the clock about to
        # expire and the ball in range, the field goal unit comes on
        # whatever the down: a team down three with eight seconds left at
        # the 30 does not run another play. The drive loop only ever kicked
        # on fourth down, so the tying kick was rarely attempted and
        # overtime ran at 3% against a real 6.2%. ----
        # the seconds left in THIS half: the first-half two-minute drill and the
        # kick before the break were missing, and the second quarter scored 8.4
        # points a game against a real 13; games without those points finish
        # farther apart than they should (12% decided by 1-3 against a real 23)
        secs_in_half = dr.clock - half_end if half_end is not None else dr.clock
        no_tos = timeouts is not None and timeouts.left.get(pos, 0) == 0
        clock_kick_time = secs_in_half <= 8 or (secs_in_half <= 22 and no_tos)
        _plan = end_of_half_plan(dr, offense, defense, rate_fn, timeouts, pos, half_end, secs_in_half, coach=(off_state.coach if off_state is not None else None))
        dr._plan = _plan
        if _plan is not None and not _plan.get('hurry', True) and _plan['choice'] in ('kick', 'shot') and secs_in_half > 14 and dr.down < 4:
            # THE BLEED'S WAIT: the play clock runs down before the last snap, so the shot or the kick comes with a
            # few seconds left and the other side gets nothing back
            burn = float(min(PLAY_SECS_RUN - 5.0, secs_in_half - 10.0))
            _tick(dr, burn); secs_in_half -= burn; clock_kick_time = secs_in_half <= 8 or (secs_in_half <= 22 and timeouts is not None and timeouts.left.get(pos, 0) == 0)
        _kick_by_plan = _plan is not None and _plan['choice'] == 'kick' and dr.down < 4 and (_plan.get('hurry', True) or clock_kick_time or secs_in_half <= 14)
        _kick_old = ((quarter >= 4 and -3 <= dr.score_diff <= 0) or (half_end is not None and quarter <= 2)) and dr.yardline <= 37 and dr.down < 4 and clock_kick_time and _plan is None
        if _kick_by_plan or _kick_old:
            flag = E.special_teams_penalty_check(rng, 'field_goal')
            if _kick_presnap_flag(dr, flag): continue
            fg = attempt_field_goal(dr.yardline, (offense.get('k') or {}), rng, rate_fn,
                                    snapper=snapper_for(offense, off_state))
            if _kick_roughing(dr, flag, fg):
                dr.clock -= play_seconds('field_goal')
                continue
            if _kick_offside(dr, flag, fg):
                dr.clock -= play_seconds('field_goal')
                continue
            if book is not None: book.special('fg', (offense.get('k') or {}).get('pid'), **fg)
            dr.clock -= min(dr.clock, play_seconds('field_goal'))
            dr.result = 'Field goal' if fg['made'] else 'Missed field goal'
            dr.points = fg['points']; dr.log.append(fg); break
        # ---- fourth down is a decision, not a play ----
        if dr.down == 4:
            # the head coach's appetite, off his identity when he has one
            aggr4 = float(off_state.coach.get('fourth_down', aggression)) if off_state is not None and off_state.coach else aggression
            dec = fourth_down_decision(dr.yardline, dr.togo, dr.score_diff,
                                       dr.clock, rng, aggr4,
                                       kicker=(offense.get('k') or {}), rate_fn=rate_fn)
            if dec == 'field_goal':
                flag = E.special_teams_penalty_check(rng, 'field_goal')
                if _kick_presnap_flag(dr, flag): continue
                fg = attempt_field_goal(dr.yardline, (offense.get('k') or {}), rng, rate_fn,
                                        snapper=snapper_for(offense, off_state))
                if _kick_roughing(dr, flag, fg):
                    dr.clock -= play_seconds('field_goal')
                    continue
                if _kick_offside(dr, flag, fg):
                    dr.clock -= play_seconds('field_goal')
                    continue
                if book is not None: book.special('fg', (offense.get('k') or {}).get('pid'), **fg)
                dr.clock -= play_seconds('field_goal')
                dr.result = 'Field goal' if fg['made'] else 'Missed field goal'
                dr.points = fg['points']; dr.log.append(fg); break
            if dec == 'punt':
                flag = E.special_teams_penalty_check(rng, 'punt')
                if _kick_presnap_flag(dr, flag): continue
                p = punt(dr.yardline, (offense.get('p') or {}),
                         (defense.get('pr') or defense.get('kr') or {}), rng, rate_fn,
                         snapper=snapper_for(offense, off_state))
                if _kick_roughing(dr, flag, p):
                    dr.clock -= play_seconds('punt')
                    continue
                if _kick_offside(dr, flag, p):
                    dr.clock -= play_seconds('punt')
                    continue
                if p.get('how') == 'return':
                    return_flag = E.special_teams_penalty_check(rng, 'punt', returned=True, phase='return')
                    if return_flag:
                        walk = min(return_flag['yards'], (100.0 - p['new_yardline']) / 2.0)
                        return_flag['yards'] = walk
                        p['new_yardline'] += walk
                if book is not None:
                    book.special('punt', (offense.get('p') or {}).get('pid'), **p)
                    if p.get('how') == 'return' or (p.get('ret') and not p.get('touchback')):
                        book.special('pr', (defense.get('pr') or defense.get('kr') or {}).get('pid'), ret=p.get('ret', 0.0))
                dr.clock -= play_seconds('punt')
                dr.result = 'Punt'; dr.log.append(p)
                if p.get('how') == 'return' and return_flag:
                    dr.log.append(dict(type='penalty', **return_flag))
                dr.next_yardline = p['new_yardline']; break

        # ---- a real play ----
        # Pass the REAL down. The first build sent down=1 on fourth down, so a
        # team going for it on 4th-and-8 called a first-down run and failed,
        # putting turnovers on downs at 21.6% against a real 5.6%.
        # yards_to_endzone must never round DOWN to zero. The first build passed
        # int(yardline), so a ball at the 0.4 gave the resolver a zero-yard field,
        # every gain capped at 0.0, and the offence physically could not score -
        # touchdowns came out at 2.1% against a real 22.6%.
        ytg_i = max(1, int(np.ceil(dr.yardline)))
        # THE PLAY CALLER'S IDENTITY: pass lean, play-action rate, motion
        # and deep-ball appetite from the plan go into the call
        olean = offensive_leans(off_state)
        secs_for_call = dr.clock
        if half_end is not None and quarter <= 2 and secs_in_half <= 240 and dr.score_diff <= 0:
            secs_for_call = secs_in_half          # the drive before the break is a two-minute drill for the side not ahead
        _pl = getattr(dr, '_plan', None)
        last_shot = (_pl is not None and _pl['choice'] == 'shot') or (_pl is None and (half_end is not None and quarter <= 2 or (quarter >= 4 and -8 <= dr.score_diff <= 0)) and secs_in_half <= 25 and dr.yardline <= 37 and dr.yardline > 1)
        if _pl is not None and _pl['choice'] in ('shot', 'play') and _pl.get('hurry', True) and dr.score_diff > 0 and half_end is not None:
            secs_for_call = secs_in_half          # a leading offense hurrying before the break is in the drill too, not burning clock
        # THE CLOCK DECIDES THE CALL LATE. Ahead in the last four minutes the offense runs to burn it
        # (a pass on third and long, otherwise the ball stays on the ground); behind, or tied, in the
        # last two minutes of a half it throws, a draw once in a while and a run only on a yard to go.
        late_lean = 0.0
        final_period = (quarter >= 4 and half_end is None) or (half_end is not None and quarter <= 2)
        if final_period:
            if dr.score_diff > 0 and dr.yardline >= 80 and secs_in_half <= 60:
                late_lean = -8.0                                   # ahead, inside your own 20, under a minute: the clock is the point and a run cannot stop it
            elif dr.score_diff > 0 and half_end is None and dr.clock <= 240:
                late_lean = -1.0 if (dr.down == 3 and dr.togo >= 6) else -3.5    # run-heavy, not run-only: a lead still needs first downs
            elif dr.score_diff <= 0 and secs_in_half <= 120:
                late_lean = 1.0 if dr.togo <= 1 else (12.0 if secs_in_half <= 30 else 6.5)          # the two-minute drill: throw; under thirty seconds there is no other call
            elif dr.score_diff < 0 and half_end is None and dr.clock < 150 * int(np.ceil(-dr.score_diff / 8.0)) + 90:
                late_lean = 0.5 if dr.togo <= 1 else 2.5          # chasing with little time: lean to the pass, not all of it
        lean_now = dict(olean or {})
        # the plan's 'play' is a quick throw to move the kick closer, whatever the score: the same drill the trailing side runs
        if _pl is not None and _pl['choice'] == 'play' and _pl.get('hurry', True) and not last_shot: late_lean = max(late_lean, 12.0 if secs_in_half <= 30 else 6.5)
        if last_shot: lean_now['pass_bias'] = float(lean_now.get('pass_bias', 0.0)) + 6.0
        elif late_lean: lean_now['pass_bias'] = float(lean_now.get('pass_bias', 0.0)) + late_lean
        oc = call_off(dr.down, max(1, int(np.ceil(dr.togo))),
                      dr.score_diff, ytg_i, rng, secs_left=secs_for_call,
                      offense=offense, rate_fn=rate_fn, lean=(lean_now if (last_shot or late_lean) else olean))
        if last_shot and _pl is not None and _pl['choice'] == 'shot':
            oc['is_pass'] = True; oc['depth'] = 'deep'; oc['concept'] = 'four_verts'; oc['play_action'] = False; oc['plan_depth'] = True   # the plan's shot: everyone to the end zone
        elif _pl is not None and _pl['choice'] == 'play' and half_end is None and dr.score_diff < 0:
            # NEEDING A SCORE WITH THE CLOCK DYING, the throws go down the field or to the sideline: no play action
            # (the fake costs a second the drive does not have), nothing short and in bounds; under fifteen seconds
            # every throw is a shot at the end zone
            oc['is_pass'] = True; oc['play_action'] = False; oc['plan_depth'] = True
            if secs_in_half <= 15: oc['depth'] = 'deep'; oc['concept'] = 'four_verts'
            elif oc.get('depth') in (None, 'short'): oc['depth'] = 'medium'
        if late_lean >= 6.0 and not oc.get('is_pass') and dr.togo > 1.5:
            # THE TWO-MINUTE DRILL THROWS. The lean left a few percent of runs and the weather's run lean ate into it
            # further; trailing under two minutes with more than a yard to go, a designed run is not a call
            oc = call_off(dr.down, max(1, int(np.ceil(dr.togo))), dr.score_diff, ytg_i, rng, secs_left=secs_for_call,
                          offense=offense, rate_fn=rate_fn, lean=dict(lean_now, pass_bias=lean_now.get('pass_bias', 0.0) + 30.0))
            if not oc.get('is_pass'): oc['is_pass'] = True; oc['depth'] = oc.get('depth') or 'medium'; oc['concept'] = oc.get('concept') or 'levels'
        if late_lean >= 6.0: oc['rpo'] = False                    # the RPO's handoff option is off the table too: that was where the last of the two-minute runs came from
        # Backed up against the own goal the offence plays differently. That
        # used to be an OVERRIDE here that rewrote a called pass as a run or
        # forced its depth short. The coach now reads the field position
        # himself: schemes.pass_rate and identity.situational_depth carry the
        # real backed-up rates and nothing is decided for him after the call.
        if dr.yardline >= 91 and oc.get('is_pass'):
            oc = dict(oc, backed_up=True)
        # THE COVERAGE CALL NEVER FIRED IN A GAME. call_defense only consults
        # coverage_call when it is handed both the defence AND rate_fn, and this
        # passed the defence alone - so every real game fell back to the shell
        # draw, man only under cover 0 and cover 1, and the eleven-call system
        # ran nowhere but its own demo. Every register row measured since it
        # was built was measured against a defence that did not use it.
        # THE COORDINATOR'S IDENTITY GOES INTO THE CALL, not over it: the
        # plan's coverage lean, shell lean, blitz lean and front family are
        # read by the coverage call itself, so one truth per snap
        dlean = None
        if def_state is not None and def_state.plan is not None:
            import gameplan as GP
            dlean = GP.defensive_leans(def_state.plan)
        dc = call_def(oc, dr.down, max(1, int(np.ceil(dr.togo))), rng, ytg_i,
                      defense=defense, rate_fn=rate_fn, score_diff=dr.score_diff,
                      secs_left=dr.clock, lean=dlean,
                      recent=(def_state.cov_memory if def_state else None))

        # THE AUDIBLE. He reads the look they are SHOWING and modifies the
        # call - he does not go back to the sheet and pick again, which would
        # let a good quarterback beat every defence every time. And the look
        # can be a lie: a disguised coverage sells him a picture that is not
        # there and he checks into something worse. That is what disguise is
        # for, and the engine already carried a shown shell and an actual one
        # with nothing reading the difference.
        try:
            import playcall as PC
            oc, checked = PC.audible(oc, dc, offense, rate_fn, rng,
                                     family_mix=(off_state.plan.run_scheme_mix
                                                 if off_state is not None and off_state.plan is not None else None))
            if checked and late_lean >= 6.0 and not oc.get('is_pass') and dr.togo > 1.5:
                oc['is_pass'] = True; checked = None          # a light box is no reason to run in the two-minute drill; the check stays a pass
            if checked:
                dr.log.append(dict(type='audible', kind=checked,
                                   off_a_lie=bool(dc.get('shown_shell')
                                                  != dc.get('shell'))))
        except Exception:
            pass

        # The opener. A situation - usually third down - forces him off it.
        script_mod = 1.0
        if off_state is not None:
            off_state.script.next_call(dr.down, int(dr.togo), rng)
            script_mod = off_state.script.performance_modifier()

        # Overlay the gameplans. Everything downstream reads THE PLAN, so an
        # adjustment made three series ago is still in force now.
        if off_state is not None and off_state.plan is not None:
            import gameplan as GP
            pl = off_state.plan
            # Personnel was selected before the defense answered the call.
            apply_offensive_plan(oc, off_state, rng, ytg_i, dr.down, int(dr.togo))
            # The caller already chose a run from roster fit and the coach's
            # run-family weights. Replacing it here discarded both decisions.

            # THE CHEATER PLAY. An adjustment vacates something, and that
            # something is the answer: "once a cheater play is used to reset
            # the defense, the play-caller can revert back". Anticipating the
            # adjustment rather than merely identifying it is what separates
            # callers, so this is gated on the caller's skill.
            import adjust as AD
            their = def_state.last_adjustment if def_state is not None else None
            ch = AD.cheater_available(their)
            if ch and not (late_lean or last_shot) and rng.random() < 0.20 + 0.55 * float(
                    off_state.coach.get('adjust_skill', 0.5)):
                if ch['call'] == 'run':
                    oc['is_pass'] = False
                    import playcall as PC
                    oc['scheme'] = PC.call_run(offense, 'chains', rate_fn, rng,
                                               family_mix=pl.run_scheme_mix)
                elif ch['call'] == 'deep':
                    oc['is_pass'] = True; oc['depth'] = 'deep'
                    oc['concept'] = 'four_verts'
                elif ch['call'] == 'play_action':
                    oc['is_pass'] = True; oc['play_action'] = True
                    oc['depth'] = 'medium'
                elif ch['call'] == 'other_target':
                    oc['avoid_bracket'] = True
                oc['cheater'] = ch['call']
                dr.cheaters = getattr(dr, 'cheaters', []) + [ch['call']]
                if def_state is not None:
                    def_state.last_adjustment = None      # the reset
        apply_defensive_plan(dc, def_state, rng)

        # Penalties. A pre-snap foul or a nullifying one (holding, OPI) wipes
        # the snap. EVERYTHING ELSE WAS BEING THROWN AWAY: the draw below
        # returned pass interference, defensive holding, roughing the passer,
        # unnecessary roughness, face masks and illegal contact, and the loop
        # dropped them on the floor because they do not nullify. So the engine
        # applied every foul that sets an offence back and none of the ones
        # that extend a drive - 0.17 automatic first downs a game against a
        # real ~3.4 - and drives died four yards and a third of a first down
        # short of real. The non-nullifying fouls are held here and resolved
        # after the play, where the offence decides whether to take them.
        # the Disciplinarian's units foul less: the offense's factor on its plays, the defense's folded in evenly
        fx_o = getattr(off_state, 'staff_fx', None) or {}; fx_d = getattr(def_state, 'staff_fx', None) or {}
        # the defense's discipline carries its awareness: the smart unit jumps offside and grabs less
        import defense_roles as DR
        _dc = DR.counts(dc.get('front_family', '4-3'), dc.get('personnel', 'nickel'))
        _dmen = ((defense.get('db') or [])[:_dc['db']] +
                 (defense.get('lb') or [])[:_dc['lb']] +
                 (defense.get('dl') or [])[:_dc['dl']])
        d_awr = float(np.mean([rate_fn(d, {'awareness_rating': 1.0}) for d in _dmen])) if _dmen else 0.70
        _in_drill = (secs_in_half < 120 and dr.score_diff <= 0) or (getattr(dr, '_plan', None) is not None and dr._plan.get('hurry', False) and dr._plan['choice'] != 'kneel')
        pen = E.penalty_check(rng, phase='any', is_pass=oc['is_pass'], discipline=float(np.clip(0.70 + 0.8 * (d_awr - 0.787), 0.5, 0.9)),
                              noise=(getattr(off_state, 'road_noise', 1.0) if off_state is not None else 1.0) * (0.5 * fx_o.get('pen_off', 1.0) + 0.5 * fx_d.get('pen_def', 1.0)), hurry=_in_drill)
        live_pen = pen if (pen and not pen['nullifies']) else None
        if pen and pen['nullifies']:
            _tick(dr, play_seconds('penalty'))
            if pen['on_offense']:
                # half the distance to the offense's own goal when the full yardage would reach it
                walk = min(float(pen['yards']), (100.0 - dr.yardline) / 2.0)
                pen['yards'] = walk
                dr.yardline += walk
                dr.togo += walk
            else:
                # half the distance to the defense's goal
                gained = min(float(pen['yards']), dr.yardline / 2.0)
                pen['yards'] = gained
                dr.untimed = True; dr.untimed_at = len(dr.log) + 1     # a half cannot end on this; the penalty entry appended below is the last thing in the log
                if pen['auto_first']:
                    dr.yardline -= gained; dr.down, dr.togo = 1, min(10, dr.yardline)
                    dr.first_downs += 1
                else:
                    dr.yardline -= gained; dr.togo -= gained
                    if dr.togo <= 0:
                        dr.down, dr.togo = 1, min(10, dr.yardline); dr.first_downs += 1
            dr.log.append(dict(type='penalty', **pen))
            continue

        # field the units for THIS snap - condition, injuries and rotation
        off_f, off_pos = field_units(offense, off_state, rng, True,
                                     oc.get('personnel'))
        def_f, def_pos = field_units(defense, def_state, rng, False,
                                     dc.get('personnel'), front_family=dc.get('front_family'))

        # the back who actually carries it
        # the back who carries it is the back on the field: the rotation in
        # field_units decides who that is
        out = resolve_fn(off_f, def_f, oc, dc, ytg_i, rng)
        if live_pen is None and out.get('throwaway') and rng.random() < 0.12:
            live_pen = dict(penalty='Intentional Grounding', yards=10.0, rule_yards=10.0,
                            on_offense=True, auto_first=False, nullifies=False)
        # the situation rides with the play, for the ticker and the probes
        if isinstance(out, dict):
            out['down'] = dr.down; out['ydstogo'] = dr.togo; out['yardline'] = dr.yardline; out['clock'] = dr.clock
            out['passer'] = off_f['qb'].get('pid') if out.get('is_pass') or out.get('type') in ('complete', 'incomplete', 'interception', 'drop', 'sack', 'scramble') else None
            _snap_state = (dr.down, dr.togo, dr.yardline)
        if script_mod != 1.0 and out.get('yards'):
            out['yards'] = round(float(out['yards']) * script_mod, 1)
        dr.plays += 1
        if off_state is not None:
            seq = getattr(off_state, 'seq', None)
            if seq is None: seq = off_state.seq = {'run_hot': 0.0}
            if out.get('type') == 'run' and not out.get('sneak'):
                seq['run_hot'] = seq['run_hot'] * 0.85 + (1.0 if float(out.get('yards') or 0) >= 4.0 else -0.4)
                seq['run_hot'] = max(0.0, seq['run_hot'])
            elif out.get('type') in ('complete', 'incomplete', 'interception', 'drop'):
                seq['run_hot'] *= 0.92
            # the hot hand: a receiver who beat his man (a completion of 12+
            # or good separation) climbs the read order for the rest of the
            # game; a drop or a smothered target slips
            tgt = out.get('target')
            if tgt and off_state.plan is not None:
                tp = off_state.plan.target_priority
                if tp is None: tp = off_state.plan.target_priority = {}
                won = out.get('type') == 'complete' and (float(out.get('yards') or 0) >= 12 or float(out.get('separation') or 0) > 1.5)
                lost = out.get('type') in ('drop', 'interception')
                tp[tgt] = float(np.clip(tp.get(tgt, 0.0) * 0.9 + (0.35 if won else -0.25 if lost else 0.0), -0.6, 1.0))
        # WHAT HAS BEEN WORKING. The coordinator's own record of his calls,
        # decayed so an early stop does not justify the same call all
        # afternoon. Nothing fed this before, so `recent` was always empty.
        if def_state is not None and dc.get('coverage'):
            def_state.remember_coverage(
                dc['coverage'], float(out.get('yards') or 0.0),
                sack=(out.get('type') == 'sack'),
                turnover=(out.get('type') in ('interception', 'fumble')))
        # THE CALL, ON THE RECORD. Play action, motion and the blitz were
        # decided on every snap and then discarded, so the register carried
        # their real values as constants and reported ok whatever the engine
        # did. Now the log says what was called and the register measures it.
        out['is_pass'] = bool(oc.get('is_pass'))
        out['play_action'] = bool(oc.get('play_action'))
        out['motion'] = bool(oc.get('motion'))
        out['blitzers'] = int(dc.get('blitzers', 0))
        out['shell'] = dc.get('shell'); out['box'] = dc.get('box'); out['personnel'] = oc.get('personnel')
        out['blitz'] = bool(dc.get('blitz')) or int(dc.get('rushers', 4)) >= 5
        dr.log.append(out)
        for st in (off_state, def_state):
            if st is not None: st.observe(oc, dc, out)

        # INJURIES: EVERY MAN ON THE FIELD ROLLS ONCE A SNAP, at his position's real share of the
        # league's injuries, with the man who took the hit rolling harder. The old roll touched only
        # the ball carrier and one random defender, so backs and the top wideout took half the league's
        # injuries and no lineman was ever hurt; the position table (health.INJURY_SHARE) now sets the
        # distribution by construction and the total is solved with health._RULED_OUT_SHARE.
        if out['type'] in ('run', 'complete', 'sack', 'scramble', 'incomplete'):
            hit_pid = None
            if out['type'] in ('sack', 'scramble'): hit_pid = off_f['qb'].get('pid')
            elif out['type'] == 'run': hit_pid = (off_f['qb'] if out.get('sneak') else (off_f.get('rb') or off_f['qb'])).get('pid')
            elif out['type'] == 'complete': hit_pid = out.get('target') or off_f['wr'][0].get('pid')
            if off_state is not None:
                men = [(off_f['qb'], 'QB'), (off_f['rb'], 'HB')] + [(m, m.get('pos', 'LT')) for m in (off_f.get('ol') or [])] + [(m, m.get('pos', 'WR')) for m in off_f['wr']] + [(m, m.get('pos', 'TE')) for m in (off_f.get('te') or [])]
                for m, mp in men:
                    if m:
                        inj_ = off_state.hurt(m, mp, 1.6 if m.get('pid') == hit_pid else 1.0, rng, rate_fn, week)
                        if inj_: dr.log.append(dict(type='injury', pid=m.get('pid'), pos=mp, kind=inj_.get('kind'), weeks=inj_.get('weeks_out'), side='off', clock=dr.clock))
            if def_state is not None:
                for d in def_f['db'] + def_f['lb'] + def_f['dl']:
                    inj_ = def_state.hurt(d, def_pos.get(d.get('pid'), 'CB'), 1.3 if out['type'] in ('run', 'complete') else 1.0, rng, rate_fn, week)
                    if inj_: dr.log.append(dict(type='injury', pid=d.get('pid'), pos=def_pos.get(d.get('pid'), 'CB'), kind=inj_.get('kind'), weeks=inj_.get('weeks_out'), side='def', clock=dr.clock))

        t = out['type']
        if live_pen is not None:
            taken = _resolve_live_penalty(dr, live_pen, out, oc)
            if taken in ('replaced', 'added') and not live_pen.get('on_offense'):
                dr.untimed = True; dr.untimed_at = len(dr.log) + 1     # the penalty entry appended next is the last thing in the log
            if taken == 'replaced':
                # accepted in place of the play: the down is replayed and the snap does not count, but the
                # play-by-play keeps the play it wiped (marked), so a reader sees the pass the flag came on
                if live_pen['penalty'] == 'Intentional Grounding':
                    if book is not None: book.record(out, off_f, def_f, rng)
                else:
                    dr.plays -= 1
                    out['nullified'] = True
                dr.log.append(dict(type='penalty', **live_pen))
                # THE CLOCK ON A WIPED PLAY IS THE CLOCK ON ANY PLAY. It had charged a full normal-pace play plus the
                # flag and skipped the timeout check, so a holding call at 0:48 in a two-minute drill ran 47 seconds
                # off and the trailing offense never got to stop it. The play runs at the drill's pace; the flag stops
                # the clock; if a side calls a timeout the clock stays stopped, otherwise it restarts on the ready
                secs_in_half_p = (dr.clock - half_end) if half_end is not None else dr.clock
                _plan_p = end_of_half_plan(dr, offense, defense, rate_fn, timeouts, pos, half_end, secs_in_half_p - PLAY_SECS, coach=(off_state.coach if off_state is not None else None)) if secs_in_half_p - PLAY_SECS > 4 else None
                used_p, used_by_p = _timeout_call(dr, t, out, timeouts, pos, half_end, secs_in_half_p, coach=(off_state.coach if off_state is not None else None), plan=_plan_p, dcoach=(def_state.coach if def_state is not None else None))
                hurry_p = (secs_in_half_p < 120 and dr.score_diff <= 0) or bool(oc.get('no_huddle'))
                _tick(dr, play_seconds(t, hurry=hurry_p, timeout=used_p, tempo=(off_state.plan.tempo if off_state is not None and off_state.plan is not None else 0.5)) + (0.0 if used_p else play_seconds('penalty')))
                dr.clock = float(np.ceil(dr.clock - 1e-9))
                if used_p and used_by_p:
                    dr.log.append(dict(type='timeout', side=used_by_p, side_abbr=(getattr(off_state if used_by_p == pos else def_state, 'abbr', None) or used_by_p.upper()), left=timeouts.left.get(used_by_p, 0), clock=dr.clock))
                after_p = (dr.clock - half_end) if half_end is not None else dr.clock
                if secs_in_half_p > 120 >= after_p and not getattr(dr, '_two_min', False):
                    dr.clock += min(20.0, 120.0 - after_p); dr._two_min = True
                    dr.log.append(dict(type='two_minute', clock=dr.clock))
                continue
            if taken == 'added':
                dr.log.append(dict(type='penalty', **live_pen))

        # a collapsed pocket is not automatically a sack - a mobile QB runs
        if t == 'sack':
            if rng.random() < E.scramble_chance(offense['qb'], 1.0, 1.4, rate_fn):
                _old = out
                _head = {k: _old.get(k) for k in ('down', 'ydstogo', 'yardline', 'clock', 'passer', 'personnel', 'is_pass') if k in _old}
                out = E.resolve_scramble(offense['qb'], [], ytg_i, rng, rate_fn); out.update({k: v for k, v in _head.items() if k not in out})
                t = 'scramble'
                for _i in range(len(dr.log) - 1, -1, -1):
                    if dr.log[_i] is _old: dr.log[_i] = out; break          # replace the play itself, not whatever was logged after it
        # THE BOOK IS WRITTEN HERE, after the flags and the scramble are settled: a play wiped by a penalty or
        # turned into a scramble was being credited as it first resolved
        _prepare_scoring_play(dr, out)
        if book is not None: book.record(out, off_f, def_f, rng)
        pending = (out, off_f, def_f, _snap_state)

        if t == 'interception':
            # The ball changes hands at the catch, then travels on the return.
            dr.yardline = _interception_spot(dr.yardline, out)
            if live_pen is not None and taken == 'added' and E.PEN_INFO[live_pen['penalty']]['phase'] == 'post':
                _enforce_turnover_penalty(dr, live_pen)
            dr.clock -= play_seconds('interception'); dr.result = 'Turnover'; break

        # fumbles attach to the event that produced them
        ev = {'complete': 'complete_pass', 'run': 'run', 'sack': 'sack',
              'scramble': 'scramble'}.get(t)
        if ev and not out.get('touchdown'):
            carrier = offense['qb'] if ev in ('sack', 'scramble') else \
                      ((offense.get('rb') or offense['qb']) if ev == 'run' else offense['wr'][0])
            fum = E.fumble_check(carrier, ev, rng, rate_fn, env_mult=ENV.fumble_mult, rate_mult=(getattr(off_state, 'staff_fx', None) or {}).get('fum_off', 1.0))
            if fum:
                out['fumble'] = True; out['fumble_lost'] = bool(fum['lost']); out['fumble_by'] = (carrier or {}).get('pid')
                if book is not None: book.record_fumble(out)          # the book was written before the ball came out
            if fum and fum['lost']:
                # the ball comes out where the play ended, not where it started: the gain (or loss) is applied first
                dr.yardline = float(np.clip(dr.yardline - float(np.round(out.get('yards', 0.0) or 0.0)), 1.0, 99.0))
                if live_pen is not None and taken == 'added' and E.PEN_INFO[live_pen['penalty']]['phase'] == 'post':
                    _enforce_turnover_penalty(dr, live_pen)
                dr.clock -= play_seconds('fumble'); dr.result = 'Turnover'; break

        # ---- timeouts ----
        _y_after = float(np.clip(dr.yardline - float(out.get('yards', 0.0) or 0.0), 1.0, 99.0))
        _secs_after = secs_in_half - PLAY_SECS
        _plan_to = end_of_half_plan(dr, offense, defense, rate_fn, timeouts, pos, half_end, _secs_after, coach=(off_state.coach if off_state is not None else None), yardline=_y_after) if _secs_after > 4 else None
        used, used_by = _timeout_call(dr, t, out, timeouts, pos, half_end, secs_in_half, coach=(off_state.coach if off_state is not None else None), plan=_plan_to, dcoach=(def_state.coach if def_state is not None else None))
        hurry = (secs_in_half < 120 and dr.score_diff <= 0) or bool(oc.get('no_huddle'))
        before_clock = secs_in_half
        clock_before = dr.clock
        _fourth_fail = dr.down >= 4 and t in ('run', 'complete', 'scramble', 'sack') and float(np.round(float(out.get('yards', 0.0) or 0.0))) < dr.togo - 0.01 and not (float(np.round(float(out.get('yards', 0.0) or 0.0))) >= dr.yardline - 0.01)
        if (t in ('run', 'complete', 'scramble') and ((out.get('touchdown') and SCORE_STOPS_CLOCK) or float(np.round(float(out.get('yards', 0.0) or 0.0)) if SCORE_STOPS_CLOCK else float(out.get('yards', 0.0) or 0.0)) >= dr.yardline - 0.01)) or _fourth_fail:
            dr.clock -= 6.0                                    # a touchdown or a change of possession stops the clock at the whistle; no huddle follows it
        else:
            dr.clock -= play_seconds(t, hurry=hurry, timeout=used, tempo=(off_state.plan.tempo if off_state is not None and off_state.plan is not None else 0.5))
        for edge in (2700.0, 900.0):
            if clock_before > edge >= dr.clock: dr.clock = float(edge)   # the quarter ends with this play; no huddle runs into the next one
        dr.clock = float(np.ceil(dr.clock - 1e-9))                          # the clock is whole seconds; a fraction left is a second
        after_clock = dr.clock - half_end if half_end is not None else dr.clock
        if used and used_by:
            dr.log.append(dict(type='timeout', side=used_by, side_abbr=(getattr(off_state if used_by == pos else def_state, 'abbr', None) or used_by.upper()), left=timeouts.left.get(used_by, 0), clock=dr.clock))
        if before_clock > 120 >= after_clock and not getattr(dr, '_two_min', False):
            # the two-minute warning: the clock stops at 2:00, so the runoff this play would have taken past it is given back
            dr.clock += min(20.0, 120.0 - after_clock); dr._two_min = True
            dr.log.append(dict(type='two_minute', clock=dr.clock))
        before = dr.yardline
        if t == 'sack' and dr.yardline - float(out.get('yards', 0.0) or 0.0) >= 100.0:
            out['yards'] = float(-(100.0 - dr.yardline)); out['safety'] = True
            dr.clock -= 0; dr.result, dr.points = 'Safety', -2
            break
        scored = _advance(dr, out.get('yards', 0.0))
        if not scored and out.get('touchdown'):
            out['touchdown'] = False                # the play engine's own read used a fraction; the drive's whole yards say he was short
        if scored:
            # the play that scored says so: the touchdown flag on the entry, the yards capped at the
            # distance to the goal, the tackler cleared (a 54-yard pass from the 48 is a 52-yard touchdown)
            if dr.result == 'Touchdown':
                out['touchdown'] = True; out['yards'] = float(min(float(out.get('yards', 0.0) or 0.0), before)); out.pop('tackler', None)
            elif dr.result == 'Safety':
                out['safety'] = True
            break
        if dr.down > 4:
            dr.result = 'Turnover on downs'; break

    if dr.result is None: dr.result = 'End of half'

    # ---- the try, once the touchdown is on the board ----
    if dr.result == 'Touchdown':
        try_penalty = float(getattr(dr, 'try_penalty', 0.0))
        def try_spot(base):
            return base + abs(try_penalty) if try_penalty < 0 else base - min(try_penalty, base / 2.0)
        if two_point_decision(dr.score_diff + 6, dr.quarter, dr.clock):
            t = attempt_two_point(offense, defense, rng, resolve_fn, call_off,
                                  call_def, rate_fn, off_state, def_state, start_yardline=try_spot(2))
        else:
            t = attempt_extra_point(offense.get('k') or {}, rng, rate_fn,
                                    snapper=snapper_for(offense, off_state), distance=try_spot(15) + 18)
            if book is not None: book.special('xp', (offense.get('k') or {}).get('pid'), **t)
        dr.points += t['points']
        dr.try_result = t
        if t.get('penalty'):
            dr.log.append(dict(type='penalty', **t['penalty']))
        dr.log.append(t)
    if pending is not None:
        _o, _off, _def, _st = pending
        _v = AS.epa(_o, _st[0], _st[1], _st[2], dr.down, dr.togo, dr.yardline, result=dr.result)
        _o['epa'] = round(_v, 3); AS.book_play(book, _o, _off, _def, _v)
    # the kick or the punt that ended it has an EPA of its own, so the ledger
    # balances: what the offence had on fourth down against what it left
    if dr.result in ('Punt', 'Field goal', 'Missed field goal') and dr.log and isinstance(dr.log[-1], dict):
        last = dr.log[-1]
        AS.book_special(book, dr, last, offense)
    if len(dr.log) > _seen: yield ('snap', dr)
    return dr

OT_LENGTH = 600          # one 10-minute period in the regular season
OT_PLAYOFF_LENGTH = 900  # 15-minute periods, repeated until someone wins

def play_overtime(home, away, score, rng, resolve_fn, call_off, call_def,
                  rate_fn, home_state=None, away_state=None, week=1,
                  playoffs=False, first='away', book=None):
    """
    2026 NFL overtime (Rule 16).

      - one 10-minute period in the regular season; 15-minute periods in the
        postseason, repeated until someone wins
      - BOTH teams get an opening opportunity to possess, even if the first
        team scores a touchdown. This changed in 2025; before that an opening
        TD ended it.
      - after both opportunities, a lead wins; still tied and time remaining
        means sudden death
      - the regular-season period does NOT extend to let the second team
        finish, so the clock can expire before it even possesses
      - a safety by the KICKING team on the receiving team's initial
        possession ends the game immediately
      - the regular season can end in a tie. Real rate: 0.29% of games.
        Overtime itself is reached in 6.2% of games.
    """
    # Real: 6.2% of games reach overtime and only 0.29% of all games end
    # tied - so roughly 1 in 20 overtimes. Teams play overtime with real
    # urgency, which a neutral game script does not reproduce on its own.
    clock = OT_PLAYOFF_LENGTH if playoffs else OT_LENGTH
    pos = first
    had = {'home': False, 'away': False}
    drives = []
    kick = kickoff_booked(returner_for(home if pos == 'home' else away, home_state if pos == 'home' else away_state, rate_fn),
                          rng, rate_fn, book)
    start = kick['new_yardline']
    clock = kickoff_clock(clock, kick)

    while clock > 0:
        off = home if pos == 'home' else away
        deff = away if pos == 'home' else home
        o_st = home_state if pos == 'home' else away_state
        d_st = away_state if pos == 'home' else home_state
        sd = score[pos] - score['away' if pos == 'home' else 'home']

        # overtime is played aggressively: nobody is protecting a lead
        # Overtime is played with maximum aggression - nobody protects a
        # lead, everyone goes for it on fourth down. Ties are real but rare:
        # 0.29% of all games, roughly 1 in 20 overtimes.
        dr = run_drive(off, deff, start, clock, 5, sd, rng, resolve_fn,
                       call_off, call_def, rate_fn, 0.98, None, o_st, d_st, week)
        drives.append((pos, dr))
        clock = max(0.0, dr.clock)
        had[pos] = True
        other = 'away' if pos == 'home' else 'home'

        if dr.points > 0:
            score[pos] += dr.points
        elif dr.points < 0:
            # a safety by the kicking team on the receiving team's FIRST
            # possession ends it immediately - the one exception to both
            # teams getting the ball
            score[other] += 2
            if not had[other]:
                return score, drives, 'safety_walkoff'

        # both have possessed: a lead wins, otherwise sudden death
        if had['home'] and had['away']:
            if score['home'] != score['away']:
                return score, drives, 'decided'

        if dr.result in ('Touchdown', 'Field goal'):
            kick = kickoff_booked(returner_for(deff, d_st, rate_fn), rng, rate_fn, book)
            start = kick['new_yardline']
            clock = kickoff_clock(clock, kick)
        elif dr.result == 'Punt':
            start = getattr(dr, 'next_yardline', 75)
        elif dr.result in ('Turnover', 'Turnover on downs'):
            start = float(np.clip(100 - dr.yardline, 1, 99))
        else:
            start = 75
        pos = other

    if playoffs:                       # the postseason never ties
        return play_overtime(home, away, score, rng, resolve_fn, call_off,
                             call_def, rate_fn, home_state, away_state, week,
                             True, first)
    return score, drives, ('tie' if score['home'] == score['away'] else 'decided')


def play_game(*args, **kwargs):
    """A full 60-minute game, played to the end. Thin wrapper over game_steps, the same game paused after
    every snap, at every drive's end and at halftime so it can be played live."""
    gen = game_steps(*args, **kwargs)
    try:
        while True: next(gen)
    except StopIteration as done:
        return done.value


def game_steps(home, away, rng, resolve_fn, call_off, call_def, rate_fn,
              home_aggr=0.5, away_aggr=0.5, book=None,
              home_state=None, away_state=None, week=1, playoffs=False, venue=None):
    """A full 60-minute game as a generator. Yields ('snap', dr) after every logged entry, ('drive', pos, dr, score)
    when a possession ends, ('halftime', score) at the break before the second-half kick, ('overtime', score)
    before overtime; returns the result dict."""
    score = {'home': 0, 'away': 0}
    drives, clock, quarter = [], GAME, 1
    pos = 'away'                                   # away receives first
    kick = kickoff_booked(returner_for(away, away_state, rate_fn), rng, rate_fn, book)    # the RECEIVING side's man returns it
    start = kick['new_yardline']
    clock = kickoff_clock(clock, kick)

    tos = Timeouts()
    half_done = False
    # THE BUILDING AND THE SKY. Conditions are drawn for this home city in
    # this week and set on the two modules that read them; they can turn at
    # the half. The road team pays the crowd and the altitude.
    global ENV
    import plays as _P
    home_abbr = (home_state.abbr if home_state is not None and getattr(home_state, 'abbr', None) else home.get('abbr', ''))
    ENV = W.draw(venue or home_abbr, week, rng, neutral=playoffs and week >= 22)     # a neutral site draws its own sky
    _P.ENV = ENV
    if away_state is not None:
        away_state.road_noise = ENV.road_false_start; away_state.road_stamina = ENV.road_stamina
    if home_state is not None:
        home_state.road_noise = 1.0; home_state.road_stamina = 1.0
    # SHADOWING IS A GAME-WEEK DECISION. A coordinator decides on Tuesday
    # whether his best corner follows their best receiver, and then he does
    # it all game. Decided per snap it ran at 4% of pass plays; the real rate
    # for clubs that shadow is 15-25% of all snaps, near 50% of games for a
    # premier corner against a premier receiver.
    import coverage as CV
    for st, ros, opp in ((home_state, home, away), (away_state, away, home)):
        if st is None or st.plan is None: continue
        cbs = sorted([d for d in ros.get('db', []) if d.get('pos') == 'CB'],
                     key=lambda d: -rate_fn(d, {'man_cover_rating': .55, 'speed_rating': .25, 'press_rating': .20}))
        wrs = [w for w in opp.get('wr', []) if w.get('pos') == 'WR']
        if len(cbs) >= 2 and wrs:
            wr1 = max(wrs, key=lambda w: rate_fn(w, {'route_run_short_rating': .20, 'route_run_med_rating': .25,
                                                     'route_run_deep_rating': .25, 'speed_rating': .30}))
            if not getattr(st.plan, 'travel_locked', False):     # the GM's own call, when he made one, stands
                st.plan.travel = CV.should_travel(cbs[0], cbs[1], wr1, rate_fn, True, rng,
                                                  coach_willingness=float(st.coach.get('travel_willingness', 0.5)),
                                                  scale=1.6)          # a game-week call has a lower bar than a snap
                st.plan.travel_target = wr1.get('pid') if st.plan.travel else None
            elif st.plan.travel and not getattr(st.plan, 'travel_target', None):
                st.plan.travel_target = wr1.get('pid')
            # BRACKETING IS A GAME-WEEK DECISION TOO. A coordinator doubles
            # their star when the second receiver is not one and the plan can
            # afford the safety: real clubs bracket the top man on about a
            # third of his snaps, more against the true elite.
            if not getattr(st.plan, 'bracket_locked', False): st.plan.bracket = None
            if len(wrs) >= 2 and not getattr(st.plan, 'bracket_locked', False):
                srt = sorted(wrs, key=lambda w: -rate_fn(w, {'route_run_short_rating': .20, 'route_run_med_rating': .25,
                                                              'route_run_deep_rating': .25, 'speed_rating': .30}))
                gap = rate_fn(srt[0], {'route_run_med_rating': .5, 'speed_rating': .5}) - rate_fn(srt[1], {'route_run_med_rating': .5, 'speed_rating': .5})
                star = rate_fn(srt[0], {'route_run_med_rating': .5, 'speed_rating': .5}) >= 0.86
                p_br = (0.55 if star else 0.25) * float(np.clip(gap / 0.08, 0.3, 1.5)) * float(st.coach.get('bracket_willingness', 0.5)) / 0.5
                if rng.random() < min(0.8, p_br):
                    st.plan.bracket = srt[0].get('pid')
    while clock > 0:
        if not half_done and clock <= HALF:
            # A kickoff return can itself use the final seconds of the half.
            # There is no empty offensive drive after that return.
            tos.halftime()
            half_done = True
            yield ('halftime', dict(score))
            ENV.turn(rng, home_abbr); _P.ENV = ENV
            pos = 'home'
            kick = kickoff_booked(returner_for(home, home_state, rate_fn), rng, rate_fn, book)
            start = kick['new_yardline']
            clock = kickoff_clock(HALF, kick)
            quarter = 3
            continue
        quarter = min(4, int((GAME - clock) // QUARTER) + 1)
        off = home if pos == 'home' else away
        deff = away if pos == 'home' else home
        sd = score[pos] - score['away' if pos == 'home' else 'home']
        aggr = home_aggr if pos == 'home' else away_aggr

        o_st = home_state if pos == 'home' else away_state
        d_st = away_state if pos == 'home' else home_state
        # the unit that just came off recovers while the other side plays
        if d_st is not None: d_st.sideline_recovery(dr_snaps if 'dr_snaps' in dir() else 30)
        dr = yield from drive_steps(off, deff, start, clock, quarter, sd, rng,
                       resolve_fn, call_off, call_def, rate_fn, aggr, book,
                       o_st, d_st, week, timeouts=tos, pos=pos,
                       half_end=(GAME / 2 if not half_done else None))
        dr_snaps = dr.plays
        if o_st is not None: o_st.sideline_recovery(dr.plays)
        drives.append((pos, dr))
        clock = max(0.0, dr.clock)
        quarter = min(4, int((GAME - clock) // QUARTER) + 1)

        if dr.points > 0:
            score[pos] += dr.points
        elif dr.points < 0:
            score['away' if pos == 'home' else 'home'] += 2
        yield ('drive', pos, dr, dict(score))

        if not half_done and clock <= HALF:
            continue                      # the next loop opens the second half

        # where the next possession starts
        onside_kept = False
        if dr.result in ('Touchdown', 'Field goal'):
            # THE ONSIDE KICK. The scoring side still trails and the clock says it needs the ball back: under
            # two and a half minutes down by one score, or under five down by two. Recovered about 6% of the
            # time under the dynamic kickoff (2024-25); a failed one gives the receiving side the ball near
            # the kicking team's 45.
            my_diff = score[pos] - score['away' if pos == 'home' else 'home']
            need_after = int(np.ceil(-my_diff / 8.0)) if my_diff < 0 else 0
            try_onside = my_diff < 0 and half_done and clock > 0 and _onside_call(clock, need_after, tos.left.get(pos, 0), (o_st.coach if o_st is not None else None), rng)
            if try_onside:
                got = rng.random() < KICKOFF['onside_recovery']
                LAST_KICKOFF['r'] = dict(onside=True, recovered=got, new_yardline=(55.0 if got else 45.0), ret=0.0, returner=None, touchback=False)
                clock = kickoff_clock(clock, LAST_KICKOFF['r'])
                if got: onside_kept = True; start = 55.0                 # the kicking side has it around its own 45
                else: start = 45.0                                       # the receiving side takes over at the kicking team's 45
            else:
                kick = kickoff_booked(returner_for(deff, d_st, rate_fn), rng, rate_fn, book)
                start = kick['new_yardline']
                clock = kickoff_clock(clock, kick)
        elif dr.result == 'Punt':
            start = getattr(dr, 'next_yardline', 75)
        elif dr.result in ('Turnover', 'Turnover on downs'):
            start = float(np.clip(100 - dr.yardline, 1, 99))
        elif dr.result == 'Missed field goal':
            start = float(np.clip(100 - dr.yardline - 8, 1, 99))
        elif dr.result == 'Safety':
            # the free kick: the side that gave it up punts from its 20 and the scoring side takes over around its own 40
            start = float(np.clip(rng.normal(60.0, 6.0), 45.0, 75.0))
            LAST_KICKOFF['r'] = dict(free_kick=True, new_yardline=start, ret=0.0, returner=None, touchback=False)
            clock = kickoff_clock(clock, LAST_KICKOFF['r'])
        else:
            start = 75
        if not onside_kept:
            pos = 'away' if pos == 'home' else 'home'      # a recovered onside kick keeps the ball with the kicking side

    # overtime
    ot = None
    if score['home'] == score['away']:
        yield ('overtime', dict(score))
        first = 'away' if rng.random() < 0.5 else 'home'
        score, ot_drives, ot = play_overtime(
            home, away, score, rng, resolve_fn, call_off, call_def, rate_fn,
            home_state, away_state, week, playoffs, first, book=book)
        drives += ot_drives

    inj = []
    for st in (home_state, away_state):
        if st is not None:
            inj += st.injuries
            st.end_game(rng)
    return dict(home=score['home'], away=score['away'], drives=drives,
                injuries=inj, overtime=ot, env=ENV.to_dict())

# ============================================================ STAT ATTRIBUTION
# Every play already names its contributors, so accumulation is nearly free.
class StatBook:
    """Accumulates individual lines across plays, games and a season."""
    def __init__(self):
        self.p = {}

    def special(self, kind, pid, **kw):
        """A kick, a punt or a return: the kicking game's box score."""
        if not pid: return
        d = self._get(pid)
        if kind == 'fg':
            d['fg_att'] += 1
            if kw.get('made'):
                d['fg_made'] += 1; d['fg_long'] = max(d['fg_long'], int(kw.get('distance', 0)))
        elif kind == 'xp':
            d['xp_att'] += 1; d['xp_made'] += 1 if kw.get('made') else 0
        elif kind == 'punt':
            d['punts'] += 1; d['punt_yds'] += float(kw.get('gross', 0.0)); d['punt_net_yds'] += float(kw.get('net', 0.0))
            if kw.get('touchback'): d['punt_tb'] += 1
            elif kw.get('new_yardline', 50) >= 80: d['punt_in20'] += 1
        elif kind == 'kr':
            d['kr'] += 1; d['kr_yds'] += float(kw.get('ret', 0.0))
        elif kind == 'pr':
            d['pr'] += 1; d['pr_yds'] += float(kw.get('ret', 0.0))

    def _get(self, pid):
        if pid not in self.p:
            self.p[pid] = dict(
                pass_att=0, pass_cmp=0, pass_yds=0.0, pass_td=0, ints=0, sacked=0,
                rush_att=0, rush_yds=0.0, rush_td=0,
                tgt=0, rec=0, rec_yds=0.0, rec_td=0, drops=0,
                tackles=0, sacks=0.0, int_def=0, pressures=0, ff=0, fumbles=0, fumbles_lost=0,
                pass_def=0,
                fum=0, fum_lost=0,
                # ---- specialists ----
                fg_att=0, fg_made=0, fg_long=0, xp_att=0, xp_made=0,
                punts=0, punt_yds=0.0, punt_net_yds=0.0, punt_in20=0, punt_tb=0,
                kr=0, kr_yds=0.0, pr=0, pr_yds=0.0,
                # ---- offensive line ----
                # There are no traditional stats for a lineman, which is why
                # his page on any real site is blank. The industry settled on
                # win rates: ESPN counts a pass block win as sustaining the
                # block 2.5 seconds or longer, and a run block win as beating
                # the man across from you. Football GM, which hit exactly this
                # problem, landed on the same three - PBWR, RBWR and sacks
                # allowed. Pancakes are deliberately NOT here: no credible
                # source tracks them and there is no standard definition, and
                # run block win rate is the real version of that idea.
                pb_snaps=0, pb_wins=0, sacks_allowed=0, pressures_allowed=0,
                # ---- advanced ----
                pass_epa=0.0, pass_plays=0, rush_epa=0.0, rush_plays=0, rec_epa=0.0, def_epa=0.0, def_plays=0,
                xcomp=0.0, cpoe_att=0, pr_reps=0, pr_wins=0, sep_total=0.0, sep_n=0, st_epa=0.0,
                rb_snaps=0, rb_wins=0)
        return self.p[pid]

    def record(self, out, off, deff, rng):
        t = out.get('type')
        qb = off['qb'].get('pid', 'QB')

        # ---- the line. Every rep, on every snap, both phases ----
        for pid, won in out.get('pb_reps') or ():
            l = self._get(pid)
            l['pb_snaps'] += 1
            l['pb_wins'] += 1 if won else 0
            if not won and out.get('pressured'):
                l['pressures_allowed'] += 1
        for pid, won in out.get('rb_reps') or ():
            l = self._get(pid)
            l['rb_snaps'] += 1
            l['rb_wins'] += 1 if won else 0
        # THE RUSH. Every rusher's rep is booked; a rusher who won his rep on a play the quarterback was pressured on
        # is credited the pressure (the blocker who lost it already carries the pressure allowed)
        for pid, won in out.get('pr_reps') or ():
            if not pid: continue
            l = self._get(pid)
            l['pr_reps'] += 1
            if won:
                l['pr_wins'] += 1; l['pressures'] += 1          # a won rep is a pressure, the way the charting services count it (about 12 a team a game)
        # A sack is charged to the man who was actually beaten, which the
        # protection resolver already names.
        if out.get('pass_def'):
            self._get(out['pass_def'])['pass_def'] += 1
        if t == 'sack' and out.get('beaten'):
            self._get(out['beaten'])['sacks_allowed'] += 1
        if t in ('complete', 'incomplete', 'drop', 'interception'):
            s = self._get(qb); s['pass_att'] += 1
            wr = out.get('target')
            w = self._get(wr) if wr else None
            if w is not None: w['tgt'] += 1
            if t == 'complete':
                s['pass_cmp'] += 1; s['pass_yds'] += out['yards']
                w['rec'] += 1; w['rec_yds'] += out['yards']
                if out.get('touchdown'): s['pass_td'] += 1; w['rec_td'] += 1
            elif t == 'drop':
                w['drops'] += 1
            elif t == 'interception':
                s['ints'] += 1
                d = self._get(out.get('by', deff['db'][0].get('pid', 'DB1')))
                d['int_def'] += 1
        elif t == 'sack':
            s = self._get(qb); s['sacked'] += 1
            d = self._get(out.get('by', (deff.get('dl') or [{}])[0].get('pid', 'DL1')))
            d['sacks'] += 1.0; d['tackles'] += 1
        elif t == 'scramble':
            s = self._get(qb); s['rush_att'] += 1; s['rush_yds'] += out['yards']
            if out.get('touchdown'): s['rush_td'] += 1
        elif t == 'run':
            rb = out.get('carrier_pid') or (off.get('rb') or off['qb']).get('pid', 'RB1')
            s = self._get(rb); s['rush_att'] += 1; s['rush_yds'] += out['yards']
            if out.get('touchdown'): s['rush_td'] += 1
        # a tackle is credited on any play that ends in the field of play, to the player the play-by-play names
        if t in ('run', 'complete', 'scramble') and not out.get('touchdown'):
            tk_pid = out.get('tackler')
            if not tk_pid:
                pool = deff['db'] + deff['lb'] + deff['dl']
                tk_pid = pool[rng.integers(0, len(pool))].get('pid', 'D?')
            self._get(tk_pid)['tackles'] += 1

    def record_fumble(self, out):
        """The carrier's fumble, lost or not, and the forced fumble to the tackler who hit him. Called from the drive
        once the ball has come out, which is after the play itself was booked."""
        fb = out.get('fumble_by') or out.get('carrier') or out.get('target')
        if fb:
            s = self._get(fb); s['fumbles'] = s.get('fumbles', 0) + 1
            if out.get('fumble_lost'): s['fumbles_lost'] = s.get('fumbles_lost', 0) + 1
        if out.get('tackler'):
            d = self._get(out['tackler']); d['ff'] += 1

    def table(self):
        import pandas as pd
        return pd.DataFrame(self.p).T

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
import copy
import numpy as np
import penalty_players as PP
import punt_strategy as PST
import weather as W
from decisions import field_goal_distance, missed_field_goal_start
ENV = W.CLEAR

# ============================================================ CLOCK
SEC = {'complete': 32.6, 'incomplete': 10.2, 'run': 36.0, 'sack': 31.2,      # re-centered once a touchdown stopped the clock at the whistle (it had been charged a full play's runoff)
       'scramble': 36.0, 'punt': 9.4, 'field_goal': 4.0, 'kickoff': 5.8,
       'penalty': 14.4, 'interception': 12.0, 'drop': 10.2, 'fumble': 12.0}
QUARTER = 900
HALF = 1800
GAME = 3600

def play_seconds(result, clock_stopped=False, hurry=False, timeout=False, tempo=0.5, urgent=False, catchup=0.0):
    # Dead-ball preparation consumes no game-clock time. The caller replaces
    # this six-second baseline with the resolved live action duration.
    if result in ('incomplete', 'drop', 'spike'):
        return 6.0
    s = SEC.get(result, 25.0)
    if clock_stopped: s = min(s, 8.0)
    if not clock_stopped and not hurry and not timeout and result in ('complete', 'run', 'scramble', 'sack'):
        # The old pace depended on charging time for penalty administration.
        # Put ordinary huddle time on running plays instead. This is the interval
        # AFTER this snap, bounded by the 40-second play clock plus live action.
        s = 6.0 + min(40.0, max(0.0, s - 6.0 + 2.0) * (1.0 - 0.6 * (float(np.clip(tempo, 0, 1)) - 0.5)))
    if hurry: s *= 0.65     # a two-minute drill runs about 17 seconds a snap against 25 to 27 at the normal pace
    if catchup and result in ('complete', 'run', 'scramble', 'sack'):
        target = 6.0 + 8.0 * (1.0 - .5 * (float(np.clip(tempo, 0, 1)) - .5))
        s -= float(np.clip(catchup, 0, 1)) * max(0.0, s - target)
    if urgent and result in ('complete', 'run', 'scramble', 'sack'):
        # Preserve live action, but spend only a short reset between snaps
        # when another possession (or several) is still needed to catch up.
        s = min(s, 6.0 + 8.0 * (1.0 - .5 * (float(np.clip(tempo, 0, 1)) - .5)))
    if timeout: s = min(s, 6.0)     # the clock stops the moment it is called
    return float(s)


def receiver_won_read(out):
    """Reward explosive gains or useful catches with clearly open separation."""
    gain = float(out.get('yards') or 0)
    needed = max(1., float(out.get('ydstogo') or 10))
    useful = gain >= (needed if int(out.get('down') or 1) >= 3 else min(4., needed))
    return out.get('type') == 'complete' and (
        gain >= 12 or (useful and float(out.get('separation') or 0) >= .65))


def live_play_seconds(out):
    """Live action only, without a huddle, using the resolved play's distance.

    Retain the six-second baseline for ordinary short plays. Longer plays
    need travel time: passes include the throw/route and running after the
    catch. These deterministic estimates consume no simulation RNG.
    """
    yards = max(0.0, float(out.get('yards', 0.0) or 0.0))
    kind = out.get('type')
    throw = max(0.0, float(out.get('ttt', 2.7) or 2.7))
    if kind == 'complete' and not any(k in out for k in ('air', 'intended_air', 'depth')):
        duration = 1.0 + yards / 8.0  # older/minimal records lack passing detail
    elif kind in ('complete', 'incomplete', 'drop', 'interception'):
        air = out.get('air', out.get('intended_air'))
        if air is None:
            air = {'short': 5., 'medium': 13., 'deep': 27.}.get(out.get('depth'), 0.)
        air = max(0.0, float(air))
        if out.get('throwaway'):
            duration = throw + 1.0
        else:
            if kind == 'complete':
                air = min(yards, air)
            duration = max(throw + air / 20.0, air / 8.0)
            if kind == 'complete':
                duration += max(0.0, yards - air) / 8.0
    elif kind == 'scramble':
        # Pocket time precedes the escape and downfield running.
        duration = throw + 1.0 + yards / 8.0
    elif kind == 'sack':
        duration = throw + 1.0
    else:
        duration = 1.0 + yards / 8.0
    return float(np.ceil(max(6.0, duration)))


def return_seconds(kick, baseline, setup=1.0):
    """Extend the existing kick/return timing only for long returns."""
    distance = max(0.0, float(kick.get('ret', 0.0) or 0.0))
    return max(baseline, float(np.ceil(setup + distance / 8.0)))


def comeback_viable(seconds, deficit):
    """Generous clock budget for chasing, not a win-probability estimate.

    Preserve one- and two-score attempts, including last-ditch onside paths.
    Each score beyond those needs another 90 seconds of usable game time.
    This prevents a four/five-score blowout from using close-game strategy.
    """
    scores = int(np.ceil(max(0.0, deficit) / 8.0))
    return seconds > 0 and seconds >= 90.0 * max(0, scores - 2)


def comeback_clock_budget(deficit):
    """Seconds left at which each required scoring possession needs clock help."""
    scores_needed = int(np.ceil(max(0.0, deficit) / 8.0))
    return 150.0 * scores_needed + 90.0


def multi_score_urgency(seconds, score_diff, quarter, chasing=False):
    if quarter not in (3, 4) or score_diff >= -8 or seconds <= 0:
        return False
    return ((chasing or comeback_viable(seconds, -score_diff))
            and seconds <= comeback_clock_budget(-score_diff))


def comeback_pace(seconds, score_diff, quarter, *, yardline=75, timeouts=3, tempo=.5):
    """Gradual second-half acceleration; seconds is remaining game time."""
    if quarter == 4 and -8 <= score_diff < -3 and seconds > 0:
        # A touchdown is needed, and a stalled drive may leave another
        # possession necessary. Budget for the remaining field AND a reply,
        # rather than spending normal huddle time until the two-minute drill.
        # This only adjusts pace; the coach still chooses runs, passes and kicks.
        reserve = 90.0 + max(0.0, 120.0 - 30.0 * np.clip(timeouts, 0, 3))
        snap_budget = (max(0.0, yardline) / 6.0 + 2.0) * 30.0
        start = min(600.0, (snap_budget + reserve) * (1.0 + .15 * (tempo - .5)))
        return float(np.clip((start - seconds) / max(1.0, start - 120.0), 0, 1))
    if quarter not in (3, 4) or score_diff >= -8 or not comeback_viable(seconds, -score_diff):
        return 0.0
    scores = int(np.ceil(-score_diff / 8.0))
    start = min(HALF, 450.0 * scores)
    full = comeback_clock_budget(-score_diff)
    return float(np.clip((start - seconds) / max(1.0, start - full), 0.0, 1.0))


def hurry_for_snap(seconds, score_diff, plan=None, call=None, quarter=None, chasing=False):
    """Use the coach's clock plan for normal plays and penalty restarts alike."""
    if quarter == 4 and score_diff < 0 and chasing:
        return seconds > 0
    if quarter == 4 and score_diff < 0 and not comeback_viable(seconds, -score_diff):
        return False
    if multi_score_urgency(seconds, score_diff, quarter):
        return True
    if plan is not None:
        return plan.get('choice') != 'kneel' and bool(plan.get('hurry', True))
    return (seconds <= 120 and score_diff <= 0) or bool((call or {}).get('no_huddle'))


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
                         kicker=None, rate_fn=None, must_score=False, half_seconds_left=None, is_home=1,
                         half_intent=None, punter=None, returner=None, snapper=None,
                         defensive_confidence=0.):
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
    distance = field_goal_distance(yardline_100)
    kick_chance = fg_probability(distance, kicker, rate_fn)
    kick_chance *= ENV.kick_mult if distance >= 35 else 1.0 - 0.3 * (1.0 - ENV.kick_mult)
    minimum = 0.42 if secs_left > 300 or score_diff >= 0 else 0.25
    if secs_left < 20: minimum = min(minimum, 0.20)
    in_range = kick_chance >= minimum
    # A reply possession in overtime ends the game if it ends short of the
    # opponent's score. Regulation clock heuristics cannot describe that state.
    if must_score:
        if -3 <= score_diff < 0 and in_range:
            return 'field_goal'
        return 'go'
    if half_seconds_left is not None and half_intent == 'protect' and score_diff >= 0:
        return 'field_goal' if in_range else 'punt'
    if score_diff < 0 and not comeback_viable(secs_left, -score_diff):
        # Play out a decided game with ordinary field-position choices.
        # A consolation kick is not a comeback benefit: attempt it only
        # with a routine chance of success, not the desperation range bar.
        band, zone = fourth_band(ydstogo), fourth_zone(yardline_100)
        ordinary_go = float(np.clip(GO_RATE[band][zone] * (0.55 + 0.60 * aggression), 0, 1))
        if rng.random() < ordinary_go:
            return 'go'
        return 'field_goal' if kick_chance >= .60 else 'punt'
    # A conversion deep in our own end with one or two snaps before halftime
    # offers little scoring opportunity; failing hands over field-goal range.
    # Keep this separate from the full-game clock and fourth-quarter urgency.
    if half_seconds_left is not None and half_seconds_left <= 20 and yardline_100 >= 60:
        return 'punt'
    # A late-half conversion on fourth and long usually leaves no time for a
    # follow-up score. The full-game win model cannot price the halftime break.
    if (half_seconds_left is not None and 0 < half_seconds_left <= 12
            and in_range and yardline_100 <= 35 and ydstogo >= 5):
        return 'field_goal'
    # With time for one play, a reachable kick ties or wins. The general
    # desperation rule must not force a conversion that leaves no clock.
    if secs_left <= 6 and -3 <= score_diff <= 0 and in_range:
        return 'field_goal'
    if secs_left <= 6 and score_diff < -3:
        return 'go'
    need_now = int(np.ceil(-score_diff / 8.0)) if score_diff < 0 else 0
    chasing = score_diff < 0 and secs_left < comeback_clock_budget(-score_diff)
    # does a field goal matter? Down 14 it leaves two scores either way; down 10 it makes it one
    need_after_fg = int(np.ceil(-(score_diff + 3) / 8.0)) if score_diff + 3 < 0 else 0
    fg_matters = not (score_diff < -3 and secs_left < 480 and need_after_fg >= need_now and -score_diff not in (7, 8) and -(score_diff + 3) not in (7, 8))
    # Keep possession for a still-viable late comeback. Useful tying/winning
    # or score-reducing kicks remain available; decided games returned above.
    if (chasing and secs_left <= 90.0 * need_now + 60.0
            and not (in_range and fg_matters)):
        return 'go'
    band, zone = fourth_band(ydstogo), fourth_zone(yardline_100)
    p_table = float(np.clip(GO_RATE[band][zone] * (0.55 + 0.60 * aggression), 0.0, 1.0))     # the observed rates already carry an average coach; the personality term sits around them
    punt_value = (PST.estimate(yardline_100, punter, returner, rate_fn, PUNT,
                              ENV.punt_mult, snap_quality(snapper, rate_fn))
                  if punter is not None and rate_fn is not None else None)
    r = DEC.fourth_down(score_diff, max(1.0, secs_left), yardline_100, ydstogo,
                       fg_prob=kick_chance, aggression=aggression, is_home=is_home, timeout_edge=timeout_edge,
                       kickoff_yardline=KICKOFF['touchback_to'],
                       punt_start=punt_value['receiving_start'] if punt_value else None) if use_wp else None
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
    # Near midfield, a defense earning repeated stops can support either
    # calculated aggression or a field-position game. Keep score/clock rules
    # dominant late, and require an actual pin chance for conservative trust.
    if 40 <= yardline_100 <= 60 and ydstogo <= 4 and secs_left > 300 and not chasing:
        p_go = float(np.clip(p_go + PST.flow_adjustment(aggression, defensive_confidence,
                             punt_value['inside20'] if punt_value else 0.), 0, 1))
    if ydstogo > 8 and not chasing:
        p_go *= DEC.fourth_conversion(ydstogo) / DEC.FOURTH_CONV[8]
        if ydstogo >= 15 and (r is None or r.get('go_boost', 0.0) <= 0):
            p_go = 0.0
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


def kickoff_clock(clock, kick):
    """Run the game clock during a live kickoff return, stopping at period end.

    Touchbacks never start the clock. The kick that crosses halftime ends the
    half before the receiving offense can begin a possession.
    """
    if kick.get('touchback') or clock <= 0:
        return clock
    kick['clock'] = clock
    after = clock - return_seconds(kick, play_seconds('kickoff'))
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


def kick_probability(dist, kicker, rate_fn, snapper=None):
    """Shared field-goal/try accuracy after weather, coaching and snapping."""
    p_make = fg_probability(dist, kicker, rate_fn) * (ENV.kick_mult if dist >= 35 else 1.0 - 0.3 * (1.0 - ENV.kick_mult))
    # the special teams coordinator: a good one keeps the kicker near his number, a poor one adds variance either way
    kn = float(kicker.get('st_noise', 1.0)) if isinstance(kicker, dict) else 1.0
    if kn != 1.0:
        p_make = float(np.clip(0.5 + (p_make - 0.5) / kn, 0.02, 0.99))
    p_make = float(np.clip(p_make + 0.02 * snap_quality(snapper, rate_fn), 0.005, 0.995))
    return float(p_make)


def attempt_field_goal(yardline_100, kicker, rng, rate_fn, snapper=None):
    dist = field_goal_distance(yardline_100)
    made = rng.random() < kick_probability(dist, kicker, rate_fn, snapper)
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

def attempt_extra_point(kicker, rng, rate_fn, snapper=None, distance=33,
                        offense_players=(), defense_players=(), book=None):
    import events as E
    PP.book_opportunities(book, list(offense_players) + list(defense_players))
    flag = E.special_teams_penalty_check(rng, 'extra_point', offense_players=offense_players, defense_players=defense_players)
    declined = None
    if flag and flag['on_offense']:
        distance += flag['yards']
    chance = kick_probability(distance, kicker, rate_fn, snapper)
    made = rng.random() < chance
    if flag and not flag['on_offense']:
        if made:
            declined = PP.decision(flag, False); PP.book_flag(book, declined)
            flag = None                        # keep the point, decline the offside flag
        else:
            spot = max(0.5, distance - 18.0)
            walk = min(flag['yards'], spot / 2.0)
            flag['yards'] = walk
            distance -= walk
            chance = kick_probability(distance, kicker, rate_fn, snapper)
            made = rng.random() < chance       # replay the untimed try
    if flag: PP.decision(flag, True); PP.book_flag(book, flag)
    return dict(type='extra_point', distance=distance, penalty=flag, declined_penalty=declined, made=bool(made),
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
                      rate_fn, off_state=None, def_state=None, start_yardline=2, _retry=False, book=None):
    """
    One snap from the two. Deliberately NOT fed to state.observe: the
    adjustment engine reads a rolling four-series window of normal downs, and
    a goal-line try is not one of those.
    """
    import gameplan as GP
    import events as E
    try_yards = max(1, int(np.ceil(start_yardline)))
    oc = call_off(1, try_yards, 0, try_yards, rng, offense=offense, rate_fn=rate_fn,
                  lean=offensive_leans(off_state))
    dp = getattr(def_state, 'plan', None)
    dc = call_def(oc, 1, try_yards, rng, try_yards, defense=defense, rate_fn=rate_fn,
                  lean=GP.defensive_leans(dp) if dp is not None else None,
                  recent=getattr(def_state, 'cov_memory', None))
    apply_offensive_plan(oc, off_state, rng, try_yards, 1, try_yards)
    apply_defensive_plan(dc, def_state, rng)
    if def_state is not None:
        def_state.rotation_context = dict(down=4, to_go=try_yards, score_diff=0)
    pending_off = _PendingSnap(off_state) if off_state is not None else None
    pending_def = _PendingSnap(def_state) if def_state is not None else None
    off_f, _ = field_units(offense, pending_off, rng, True, oc.get('personnel'))
    def_f, _ = field_units(defense, pending_def, rng, False, dc.get('personnel'),
                           front_family=dc.get('front_family'))
    off_rows, def_rows = PP.unit(off_f, True), PP.unit(def_f, False)
    PP.book_opportunities(book, off_rows + def_rows)
    flag = None if _retry else E.special_teams_penalty_check(rng, 'two_point', offense_players=off_rows, defense_players=def_rows)
    if flag and flag['on_offense']:
        # An untimed false start moves the try before its actual play.
        flag['yards'] = min(flag['yards'], (100. - start_yardline) / 2.)
        PP.decision(flag, True); PP.book_flag(book, flag)
        retry = attempt_two_point(offense, defense, rng, resolve_fn, call_off, call_def,
                                  rate_fn, off_state, def_state, start_yardline + flag['yards'], _retry=True, book=book)
        retry['penalty'] = flag
        return retry
    if pending_off is not None: off_f = pending_off.commit(off_f)
    if pending_def is not None: def_f = pending_def.commit(def_f)
    # The package has already selected and recorded the carrier's snap.
    out = resolve_fn(off_f, def_f, oc, dc, try_yards, rng)
    good = out.get('type') in ('run', 'complete', 'scramble') and \
           float(np.round(out.get('yards', 0.0))) >= start_yardline
    declined = None
    if flag and not flag['on_offense']:
        if good:
            declined = PP.decision(flag, False); PP.book_flag(book, declined)
            flag = None                         # the offense keeps the successful free play
        else:
            walk = min(flag['yards'], start_yardline / 2.0)
            flag['yards'] = walk
            retry = attempt_two_point(offense, defense, rng, resolve_fn, call_off, call_def,
                                      rate_fn, off_state, def_state, start_yardline - walk, _retry=True, book=book)
            PP.decision(flag, True); PP.book_flag(book, flag)
            retry['penalty'] = flag
            return retry
    if flag: PP.decision(flag, True); PP.book_flag(book, flag)
    return dict(type='two_point', play=out.get('type'), from_yardline=start_yardline, penalty=flag, declined_penalty=declined, made=bool(good),
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

def _blocked_punt(yardline, rng, kicking=(), receiving=()):
    """Resolve a ball deflected behind the line, in the kicking team's coordinates."""
    loose = min(110.0, float(yardline) + float(rng.uniform(1.0, 15.0)))
    recovery = 'receiving' if rng.random() < .7 else 'kicking'
    pool = receiving if recovery == 'receiving' else kicking
    man = pool[int(rng.integers(len(pool)))] if pool else {}
    advance = float(rng.gamma(1.5, 4.0))
    end = loose + advance if recovery == 'receiving' else loose - advance
    # A ball through the kicking team's end line is dead before recovery.
    dead = loose >= 110
    safety = dead or (recovery == 'kicking' and end >= 100)
    td = not safety and (end >= 100 if recovery == 'receiving' else end <= 0)
    return dict(type='punt', blocked=True, origin=float(yardline),
                recovery=None if dead else recovery, recoverer=man.get('pid') if not dead else None,
                recovery_spot=loose, end_spot=float(np.clip(end, 0, 100)),
                advance=0.0 if dead else advance, safety=safety, touchdown=td,
                dead_end_line=dead, gross=0.0,
                net=float(yardline) - float(np.clip(end, 0, 100)),
                new_yardline=float(np.clip(100 - end, 1, 99)))


def _apply_blocked_punt(dr, kick):
    """Keep a recovered fourth-down kick only if the kicking team gains the line."""
    origin = dr.yardline
    dr.yardline = kick['end_spot']
    if kick['safety']:
        dr.result, dr.points = 'Safety', -2
    elif kick['touchdown']:
        defending = kick['recovery'] == 'receiving'
        dr.result = 'Defensive touchdown' if defending else 'Touchdown'
        dr.points = -6 if defending else 6
    elif kick['recovery'] == 'kicking' and origin - dr.yardline >= dr.togo:
        dr.down, dr.togo = 1, min(10.0, dr.yardline)
        dr.first_downs += 1
        dr.clock_running = True
        dr.runoff_charged = 0.0
        kick['retained'] = True
        dr.result = None
    else:
        kick['retained'] = False
        dr.result = 'Punt'
        dr.next_yardline = kick['new_yardline']


def punt(yardline_100, punter, returner, rng, rate_fn, AVG=0.70, snapper=None,
         kicking=(), receiving=(), return_coverage=None, return_blockers=None):
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
        return _blocked_punt(yardline_100, rng, kicking or (punter,), receiving)
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
                    gross=round(float(yardline_100), 1), pooch=pooch,
                    origin=yardline_100, net=round(float(yardline_100 - 20), 1),
                    new_yardline=80)       # opponent's own 20
    # A return brings the ball OUT, toward the kicking team's goal, so it
    # SHORTENS the receiving team's field. This was + ret: every punt return
    # in the engine's history pushed the returner backwards by the length of
    # his own return, and the punt net came out longer than the gross.
    import kick_returns as KR
    outcome = KR.resolve(100 - land, ret, returner or {}, rng, rate_fn,
                         kicking if return_coverage is None else return_coverage,
                         receiving if return_blockers is None else return_blockers,
                         event='punt_return', weather=ENV.fumble_mult) if how == 'return' else {}
    ret = outcome.get('ret', ret)
    new = outcome.get('new_yardline', float(np.clip(100 - land, 1, 99)))
    result = dict(type='punt', blocked=False, touchback=False, pooch=pooch, how=how,
                gross=round(float(gross), 1), ret=round(float(ret), 1),
                display_gross=int(round(yardline_100)) - int(round(land)),
                display_ret=100 - int(round(new)) - int(round(land)),
                land=round(float(land), 1), origin=yardline_100,
                net=round(float(yardline_100 - (100 - new)), 1),
                new_yardline=round(new, 0))
    result.update(outcome)
    # The return resolver can replace both the spot and its own rounded gain.
    # Derive the displayed distances from the final, displayed field spots.
    field_round = lambda y: int(np.floor(float(y) + .5))
    finish = 100 - field_round(result['new_yardline'])
    landing = min(field_round(result['land']), finish) if how == 'return' else finish
    result['display_gross'] = field_round(yardline_100) - landing
    result['display_ret'] = finish - landing
    return result

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


def _shot_sack_prob(offense, defense, rate_fn):
    """Bounded planning estimate of a sack on the end-zone concept."""
    blockers = offense.get('ol') or []
    rushers = (defense.get('dl') or []) + (defense.get('lb') or [])
    block = float(np.mean([rate_fn(p, {'pass_block_rating': 1.0}) for p in blockers])) if blockers else .7
    rush = float(np.mean([rate_fn(p, {'finesse_moves_rating': .5, 'power_moves_rating': .5}) for p in rushers])) if rushers else .7
    return float(np.clip(.09 + .35 * (rush - block), .03, .22))


def end_of_half_plan(dr, offense, defense, rate_fn, timeouts, pos, half_end, secs_in_half, coach=None, yardline=None):
    """The coach's best option with the seconds left, priced from where he stands: 'kick', 'shot', 'play' (one or
    more snaps, then decide again), or 'kneel'. Before halftime the price is expected points. At the end of the
    game it is the game: a field goal is worth nothing down four, a touchdown is the win down six and a coin flip
    down eight, and with no timeouts a completion in bounds ends it. Returns dict(choice, evs, p_fg, p_td) or None
    outside the window, or when the side with the ball is ahead at the end of the game (it wants the clock)."""
    if half_end is None and (dr.quarter < 4 or dr.score_diff > 0): return None
    if half_end is None and dr.quarter == 4 and dr.score_diff < 0 and not comeback_viable(secs_in_half, -dr.score_diff):
        return None
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
    def kick_ev(yy): return v_kick * fg_probability(field_goal_distance(yy), kicker, rate_fn)
    p_fg = fg_probability(field_goal_distance(y), kicker, rate_fn)
    p_td = _shot_td_prob(y, offense, defense, rate_fn)
    evs = {'kneel': v_kneel}
    if secs_in_half >= 1: evs['kick'] = kick_ev(y)
    def shot_ev(yy, secs, tos):
        """A throw to the end zone: the touchdown, or, with time to kick after it, the kick that follows an
        incompletion (the clock stops) or a catch short of the goal (a timeout stops it); tied at the end of the
        game, an incompletion still leaves the coin flip."""
        # Beyond a plausible end-zone throw, keep the safe tied-game option.
        if secs < 6 and yy > 60 and game_end and need == 0:
            return v_kneel
        sack = _shot_sack_prob(offense, defense, rate_fn)
        p = (1.0 - sack) * _shot_td_prob(yy, offense, defense, rate_fn)
        ev = v_td * p * (0.85 + 0.30 * aggr)
        live = max(0.0, 1.0 - p - SHOT_INT - sack)
        # A stopped-clock miss costs 6-8 seconds; reserve 3 seconds to line up.
        # A sack/catch in bounds needs a timeout or time for a field-goal change.
        kick_after_miss = float(np.clip((secs - 9.0) / 2.0, 0.0, 1.0))
        kick_after_sack = tos > 0 and secs >= 9 or secs >= 24
        if kick_after_sack:
            ev += sack * kick_ev(min(99.0, yy + 8.0))
        if secs >= 6:
            ev += live * ((1.0 - SHOT_SHORT) * kick_ev(yy) * kick_after_miss + SHOT_SHORT * (kick_ev(max(1.0, yy - 15.0)) if kick_after_sack else 0.0))
        elif game_end and need == 0:
            # A final-play interception usually ends regulation tied too;
            # it is not an automatic loss. Return touchdowns are possible,
            # but this coarse look-ahead does not resolve the return itself.
            ev += (1.0 - p) * v_kneel
        return ev
    if secs_in_half > 0: evs['shot'] = shot_ev(y, secs_in_half, own_tos)
    # one snap or several before deciding: a completion gains PLAY_GAIN, an incompletion stops the clock for
    # nothing, a sack or a turnover ends the attempt. Each snap takes PLAY_SECS with the clock stopped after it; a
    # completion in bounds keeps the clock running and, with no timeout left and no time to spare, ends the half
    best_play = None; k_best = 0
    # A final quick throw uses the same live duration as execution. Three
    # stopped-clock seconds suffice to snap the kick; it may finish after zero.
    quick_seconds = live_play_seconds(dict(type='complete', yards=PLAY_GAIN))
    quick_window = secs_in_half < PLAY_SECS + 4.0
    play_seconds = quick_seconds if quick_window else PLAY_SECS
    n_max = min(max(0, 4 - int(dr.down)), int((secs_in_half - 3.0) // play_seconds))
    surv = 1.0; yk = y; sk = secs_in_half; tos_k = own_tos
    for k in range(1, max(0, min(n_max, own_tos + 3)) + 1):
        sk -= play_seconds
        if sk < 3: break
        p_comp = 1.0 - PLAY_BAD - PLAY_INC
        if tos_k > 0: tos_k -= 1; surv *= (1.0 - PLAY_BAD)                                  # the timeout stops it after a catch
        elif sk >= 18:
            sk -= 12.0
            surv *= (1.0 - PLAY_BAD)                                             # enough clock to absorb a catch in bounds
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
    for k in range(0, max(0, 4 - int(dr.down)) + 1):
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
    return dict(choice=choice, hurry=hurry, quick_play=bool(quick_window and choice == 'play'), evs={k: round(v, 3) for k, v in evs.items()}, cost_hurry=round(cost_hurry, 3), p_fg=round(p_fg, 3), p_td=round(p_td, 3), aggr=round(aggr, 2), need=need)



def _onside_call(clock, need, my_tos, coach, rng):
    """Onside or kick deep, priced. The onside comes back about 6% of the time and gives the kicker's side the ball
    near its own 45 with the clock intact; a miss gives the other side the ball there, in range, and most of the
    clock. Kicking deep hands them the ball at their 30 and asks the defense for a stop: the ball comes back
    with whatever the stop leaves, and the timeouts in hand decide how much that is. The coach's aggression
    weighs the gamble; a club needing two scores counts every possession double. Where the two are close the
    coach's appetite decides, so the same spot is not the same call for every staff."""
    if need <= 0 or not comeback_viable(clock, need): return False
    c = coach or {}
    aggr = float(np.clip(0.5 * float(c.get('fourth_down', 0.5)) + 0.5 * float(c.get('adjust_willingness', 0.5)), 0.0, 1.0))
    p_rec = KICKOFF['onside_recovery']
    scores_needed = int(np.ceil(need / 8.0))
    # The first possession is useful only if time remains for the other
    # scores. Reserve an optimistic 45-second scoring drive plus a six-second
    # recovery attempt for each additional possession; do not spend the
    # entire remaining clock valuing a single consolation score.
    reserve = 51.0 * max(0, scores_needed - 1)
    def usable(secs, tos):
        pr, _ = _possession_odds(max(0.0, secs - reserve), tos); return pr / 0.5
    # DEEP: they have it at their 30; the ball comes back if they stall (about 60% of drives after a kickoff do),
    # with whatever their three snaps leave on the clock; each timeout in hand keeps about 24 seconds of it
    burn = 3 * PLAY_SECS_RUN - 24.0 * min(3, my_tos)
    v_deep = 0.60 * usable(max(0.0, clock - burn - 6.0), max(0, my_tos - 3))
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
    dr._half_stall_intent = None
    if secs_in_half <= live_play_seconds(out):
        return False, None  # the play itself ends the period; nothing left to stop
    if (half_end is None and getattr(dr, 'quarter', 4) == 4 and dr.score_diff != 0
            and not comeback_viable(secs_in_half, abs(dr.score_diff))):
        return False, None
    used = False; used_by = None
    c = coach or {}
    clock_aggr = float(np.clip(0.5 * float(c.get('fourth_down', 0.5)) + 0.5 * float(c.get('adjust_willingness', 0.5)), 0.0, 1.0))
    own_left = timeouts.left.get(pos, 0) if timeouts is not None else 0
    trail_window = (60.0 + 40.0 * clock_aggr) if own_left >= 2 else 60.0
    _scored_now = bool(out.get('touchdown') or out.get('defensive_td')) or (t in ('run', 'complete', 'scramble') and float(out.get('yards', 0.0) or 0.0) >= dr.yardline - 0.01)
    if out.get('fumble_lost') or t == 'interception': return False, None
    # Only live action can make the warning stop this play for free. A huddle
    # that would reach 2:00 is time a trailing team can still save now.
    _at_warning = secs_in_half > 120 and secs_in_half - live_play_seconds(out) <= 120 and not getattr(dr, '_two_min', False)
    if timeouts is not None and secs_in_half < 300 and not _scored_now and not _at_warning:
        other = 'away' if pos == 'home' else 'home'
        # nothing to stop after a score (the clock is dead at the whistle) or on the play that reaches the
        # two-minute warning (the warning stops it for free)
        in_bounds = t in ('run', 'scramble', 'complete', 'sack')          # the clock runs after these; nothing to stop after an incompletion
        failed_third = getattr(dr, 'down', 1) >= 3 and float(out.get('yards', 0) or 0) < getattr(dr, 'togo', 10)
        # A last-half possession outside scoring range is over after a failed
        # third down. Do not buy the opponent another snap by stopping the clock
        # just to punt, including when trailing before halftime.
        if (half_end is not None and failed_third and secs_in_half <= 20
                and dr.yardline - float(out.get('yards', 0) or 0) >= 50):
            dr._half_stall_intent = 'protect'
            return False, None
        if (half_end is not None and dr.score_diff >= 0 and failed_third
                and dr.yardline - float(out.get('yards', 0) or 0) > 40):
            attacking = plan is not None and plan.get('hurry', True) and plan.get('choice') != 'kneel'
            dr._half_stall_intent = 'attack' if attacking else 'protect'
            if not attacking:
                return False, None  # retain this intent for the subsequent fourth down
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
            # The live drive still describes the snap. Price the defense's
            # timeout from the resulting spot and new series instead.
            gained = float(np.round(float(out.get('yards', 0) or 0)))
            old_down = int(getattr(dr, 'down', 1))
            old_togo = float(getattr(dr, 'togo', 10.0))
            next_spot = max(.5, dr.yardline - gained)
            converted_now = gained >= old_togo - .01
            nd = 1 if converted_now else old_down + 1
            togo = min(10., next_spot) if converted_now else old_togo - gained
            remaining_seconds = max(0., secs_in_half - live_play_seconds(out))
            remaining = max(1, 4 - nd)                          # snaps before the punt, counting the one just run as done
            p_stop = 0.28 if nd <= 1 else (0.40 if togo >= 4 else 0.25) if nd == 2 else (0.62 if togo >= 7 else 0.48 if togo >= 3 else 0.32)
            later = 0.65 * PLAY_SECS_RUN + 0.35 * PLAY_SECS                  # a later snap stops the clock itself a third of the time
            after_with = max(0.0, remaining_seconds - PLAY_SECS * min(remaining, tos_d) - later * max(0, remaining - tos_d) - 6.0)
            after_without = max(0.0, remaining_seconds - PLAY_SECS_RUN - later * (remaining - 1) - 6.0)
            # what the defense gets if the series fails: a possession, worth less when it needs touchdowns (down
            # two scores a field-goal drive is nearly nothing to it)
            need_td = 0.35 if dr.score_diff >= 9 else 1.0
            d_gain = need_td * (_possession_value(after_with, max(0, tos_d - min(remaining, tos_d))) - _possession_value(after_without, tos_d))
            # ...and what the offense gets if the series lives: the stopped clock is its time too, and it is the one
            # driving. Past midfield with the clock short, that is most of the value of the stop handed to them.
            o_gain = 0.6 * (_possession_value(after_with + 12.0, timeouts.left.get(pos, 0)) - _possession_value(after_without + 12.0, timeouts.left.get(pos, 0))) * (1.4 if next_spot <= 50 else 0.7)
            gain = p_stop * d_gain - (1.0 - p_stop) * o_gain
            # ...AGAINST WAITING FOR THIRD DOWN. With snaps still to come, the timeout can be held for the series'
            # last one, where the stop is likelier and every timeout is still in hand; a conversion in between
            # costs nothing. The timeout is spent now only when now beats that.
            if remaining > 1:
                secs_3rd = remaining_seconds - PLAY_SECS_RUN - later * (remaining - 2)
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
        elif plan is not None and not plan.get('hurry', True) and in_bounds and timeouts.left.get(other, 0) > 0 and dr.score_diff >= 0 and (half_end is None or (dr.score_diff == 0 and dr.down >= 3 and float(out.get('yards', 0) or 0) < dr.togo)):
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


def _kneel_interval(seconds, down, opponent_timeouts):
    """Live knee takes two seconds; only a retained possession can run clock.

    Return remaining seconds, whether the defense uses a timeout, and whether
    the two-minute warning stops this interval. Shared by planning/execution.
    """
    live_end = max(0.0, seconds - 2.0)
    warning = seconds > 120 >= live_end
    if live_end == 0 or down >= 4 or warning:
        return live_end, False, warning
    if opponent_timeouts > 0:
        return live_end, True, False
    end = max(0.0, live_end - 40.0)
    if live_end > 120 >= end:
        return 120.0, False, True
    return end, False, False


def _can_kneel_out(dr, seconds, opponent_timeouts):
    """Prove that knees end this period before downs or a safety give it away."""
    if seconds <= 0:
        return False
    yardline = dr.yardline
    for down in range(dr.down, 5):
        yardline += 1
        if yardline >= 100:
            return False
        seconds, used, _ = _kneel_interval(seconds, down, opponent_timeouts)
        opponent_timeouts -= int(used)
        if seconds <= 0:
            return True
    return False


def _injury_timeout(dr, injuries, out, timeouts, pos, half_end, live_end,
                    off_state=None, def_state=None, foul=False):
    """Administer post-warning injury timeouts after down/spot enforcement."""
    wall = half_end if half_end is not None else 0.
    if (not injuries or timeouts is None or dr.quarter not in (2, 4)
            or not getattr(dr, '_two_min', False) or live_end <= wall
            or dr.result in ('Touchdown', 'Safety', 'Turnover on downs')
            or out.get('fumble_lost') or out.get('type') == 'interception'):
        return False
    sides = sorted({pos if i['side'] == 'off' else
                    ('away' if pos == 'home' else 'home') for i in injuries})
    dr.clock = live_end
    dr.clock_running = False
    dr.runoff_charged = 0.
    dr.play_clock = 25.
    excess = []
    for side in sides:
        charged = timeouts.use(side)
        state = off_state if side == pos else def_state
        dr.log.append(dict(type='timeout', reason='injury', side=side,
            side_abbr=getattr(state, 'abbr', None) or side.upper(),
            left=timeouts.left.get(side, 0), excess=not charged, clock=live_end))
        if not charged:
            key = (dr.quarter, side)
            counts = getattr(timeouts, 'injury_excess', {})
            counts[key] = counts.get(key, 0) + 1
            timeouts.injury_excess = counts
            excess.append((side, counts[key]))
    if len(sides) == 1 and excess:
        side, count = excess[0]
        if count > 1:
            offense = side == pos
            yards = min(5., (100 - dr.yardline if offense else dr.yardline) / 2.)
            dr.yardline += yards if offense else -yards
            dr.togo += yards if offense else -yards
            if dr.togo <= 0:
                dr.down, dr.togo = 1, min(10., dr.yardline)
                dr.first_downs += 1
            dr.log.append(dict(type='penalty', penalty='Delay of Game',
                side='off' if offense else 'def', yards=yards, clock=live_end,
                accepted=True, before_snap=True))
        running = out.get('type') in ('run', 'complete', 'sack', 'scramble') and not out.get('out_of_bounds') and not foul
        # The opponent chooses a restart that serves its clock objective.
        restart = running and ((side == pos and dr.score_diff <= 0)
                               or (side != pos and dr.score_diff > 0))
        if restart:
            runoff = 10. if side == pos else 0.
            if runoff:
                dr.log.append(dict(type='injury_runoff', seconds=10, clock=live_end))
            dr.play_clock = 30. if runoff else 40.
            ready = min(dr.play_clock, max(0., play_seconds(out['type']) - 6.))
            dr.clock = max(wall, live_end - runoff - ready)
            dr.clock_running = dr.clock > wall
            dr.runoff_charged = ready if dr.clock_running else 0.
    return True


def _delay_clock_expired(dr, half_end=None):
    """Wait for the remaining play clock before a delay flag; boundaries win."""
    if not dr.clock_running:
        return True
    remaining = max(0., dr.play_clock - dr.runoff_charged)
    start = dr.clock
    wall = half_end if half_end is not None else 0.
    boundaries = [edge for edge in (2700., 1800., 900., 0.) if wall <= edge < start]
    warning = wall + 120.
    if dr.quarter in (2, 4) and not getattr(dr, '_two_min', False) and warning < start:
        boundaries.append(warning)
    boundary = max(boundaries, default=wall)
    if start - remaining <= boundary:
        dr.clock = boundary
        dr.clock_running = False
        dr.runoff_charged = 0.
        dr.play_clock = 25. if boundary == warning else 40.
        if boundary == warning:
            dr._two_min = True
            dr.log.append(dict(type='two_minute', clock=dr.clock))
        return False
    dr.clock -= remaining
    dr.runoff_charged += remaining
    return True


def _penalty_ready_clock(dr, pen, half_end=None, *, before_snap=False,
                         was_running=False, result=None, hurry=False, tempo=0.5,
                         timeout=False, live_start=None):
    """Charge only the legal ready-to-snap interval, never flag administration.

    Rule 4-3-2(e) retains the preceding clock status outside late-half exceptions;
    Rule 4-6-2 resets the play clock to 25. A pre-snap flag resets that interval,
    so a running clock may consume another interval after enforcement.
    """
    dr.clock_running = False
    dr.runoff_charged = 0.0
    dr.play_clock = 25.0
    wall = half_end if half_end is not None else 0.0
    secs = dr.clock - wall
    period_ended = live_start is not None and any(
        live_start > edge >= dr.clock for edge in (2700.0, 1800.0, 900.0, 0.0))
    runs = was_running if before_snap else result in ('run', 'complete', 'scramble', 'sack')
    # Fourth-period offensive pre-snap fouls start on the snap even before 5:00.
    late = secs <= (120.0 if dr.quarter <= 2 else 300.0)
    if (not runs or timeout or late or period_ended or dr.result is not None
            or (before_snap and pen['on_offense'] and dr.quarter >= 4)):
        return
    start = dr.clock
    ready = min(dr.play_clock, max(0.0, play_seconds(
        result or 'run', hurry=hurry, tempo=tempo,
        catchup=comeback_pace(secs, dr.score_diff, dr.quarter,
            yardline=dr.yardline, timeouts=getattr(dr, '_own_timeouts', 3), tempo=tempo)) - 6.0))
    # A warning interrupts ready-for-play runoff, but never erases live action.
    if not getattr(dr, '_two_min', False) and secs > 120:
        ready = min(ready, secs - 120.0)
    _tick(dr, ready)
    dr.clock = max(wall, dr.clock)
    pen['ready_seconds'] = start - dr.clock
    dr.runoff_charged = start - dr.clock
    boundary = any(start > edge >= dr.clock for edge in (2700.0, 1800.0, 900.0, 0.0))
    warning = secs > 120 and dr.clock - wall <= 120
    dr.clock_running = not boundary and not warning


def returner_for(ros, state, rate_fn, kind='kr'):
    """Re-evaluate healthy returners, including newly promoted primary starters."""
    import rosters as R
    out = state.out if state is not None else set()
    depth = ros.get('depth') or {}
    current = ros.get(kind) or (ros.get('kr') if kind == 'pr' else None) or {}
    # Legacy/minimal game rosters may specify a return man without a chart.
    if not depth and current and current.get('pid') not in out:
        return current
    groups = depth.values() if depth else [ros.get(g) or [] for g in ('wr', 'db', 'backs')]
    candidates = [p for men in groups for p in men if p and p.get('pid') not in out]
    if not depth and ros.get('rb') and ros['rb'].get('pid') not in out:
        candidates.append(ros['rb'])
    ordered = R.return_order(candidates, ros.get('depth_pins'), kind.upper(), depth)
    return ordered[0] if ordered else {}


def kickoff_booked(returner, rng, rate_fn, book, from_50=False, kicking=(), receiving=(), kicker=None,
                   short_kick_bias=None):
    """Resolve, enforce and book the return once, before the next possession."""
    import events as E
    import kick_returns as KR
    r = kickoff(returner, rng, rate_fn, from_50=from_50, kicking=kicking, receiving=receiving,
                kicker=kicker, short_kick_bias=short_kick_bias)
    if not r.get('touchback'):
        rows = [('ST', p) for p in receiving]
        PP.book_opportunities(book, rows)
        KR.enforce_return_flag(r, E.special_teams_penalty_check(rng, 'kickoff', returned=True, offense_players=rows))
        PP.book_flag(book, r.get('penalty') or r.get('declined_penalty'))
        KR.book_return(book, 'kr', r)
    r['returner'] = (returner or {}).get('pid')
    LAST_KICKOFF['r'] = r
    return r


def kickoff(returner, rng, rate_fn, AVG=0.70, from_50=False, kicking=(), receiving=(), kicker=None,
            short_kick_bias=None):
    power = rate_fn(kicker, {'kick_power_rating': 1.0}) - AVG if kicker is not None else 0.0
    accuracy = rate_fn(kicker, {'kick_acc_rating': 1.0}) - AVG if kicker is not None else 0.0
    touchback = float(np.clip(KICKOFF['touchback'] + .16 * power + .08 * accuracy, .02, .98))
    skill = rate_fn(returner, {'kick_ret_rating': .45, 'speed_rating': .30, 'juke_move_rating': .25})
    # Aim high and short only when the coordinator likes the coverage matchup.
    # The return still resolves normally, so a good returner can punish the call.
    short = False
    if short_kick_bias is not None and not from_50:
        cov = np.mean([rate_fn(p, {'tackle_rating': .55, 'speed_rating': .45}) for p in kicking]) if kicking else AVG
        block = np.mean([rate_fn(p, {'run_block_rating': .55, 'speed_rating': .45}) for p in receiving]) if receiving else AVG
        # Coverage players are selected for tackling and return-unit players
        # for blocking; the average matchup has a built-in ~0.13 rating gap.
        chance = float(np.clip(.265 + short_kick_bias + 1.2 * (cov - block - .13)
                               - .25 * (skill - RET_AVG), .04, .55))
        short = rng.random() < chance
    if not short and rng.random() < touchback:
        spot = KICKOFF['touchback_from_50'] if from_50 else KICKOFF['touchback_to']
        return dict(type='kickoff', touchback=True, new_yardline=spot)
    import kick_returns as KR
    ret = rng.gamma(7.0, KICKOFF['return_mean'] / 7.0) * (1.0 + 0.8 * (skill - RET_AVG))
    # Better placement leaves a smaller return; neutral skill preserves the
    # existing landing point and return distribution without another roll.
    ret *= float(np.clip(1.0 - .15 * accuracy, .90, 1.10))
    if short:
        # Hang time lets coverage close, while the catch around the own 10
        # gives the returner enough field to beat a poor coverage unit.
        ret *= .78
        landing = float(np.clip(89. + 5. * accuracy, 86., 93.))
    else:
        landing = float(np.clip(95. + 6. * power, 90., 98.))
    outcome = KR.resolve(landing, ret, returner or {}, rng, rate_fn, kicking, receiving,
                         event='kick_return', weather=ENV.fumble_mult)
    return dict(type='kickoff', touchback=False, short_kick=short, **outcome)


def kickoff_for(kicking, receiving, kick_state, receive_state, rng, rate, book):
    import kick_returns as KR
    returner = returner_for(receiving, receive_state, rate)
    coverage = KR.unit(kicking, kick_state, rate)
    blockers = KR.unit(receiving, receive_state, rate, True, returner.get('pid'))
    kicker = specialist_for(kicking, kick_state, 'K', rate)
    result = kickoff_booked(returner, rng, rate, book,
        kicking=coverage, receiving=blockers, kicker=kicker,
        short_kick_bias=(getattr(kick_state, 'staff_fx', None) or {}).get('short_kick_bias', 0.0))
    if not result.get('touchback'):
        special_injuries(kick_state, coverage + [kicker], rng, rate, ENV.week, contact=.8)
        special_injuries(receive_state, blockers + [returner], rng, rate, ENV.week, contact=.8)
    return result


def pending_kick_outcome():
    kick = LAST_KICKOFF.get('r') or {}
    return bool(kick.get('touchdown') or kick.get('fumble_lost'))


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
        self.memories = {unit: AD.GameMemory() for unit in ('offense', 'defense')}
        # Walsh's opener, run before the defence can counter. Off-script
        # performance is measurably worse for some callers: Shanahan's 2022
        # San Francisco had +0.32 passing EPA on script and -0.10 off it.
        self.script = AD.Script(length=int((coach or {}).get('script_length', 15)),
                                off_script_skill=float((coach or {}).get(
                                    'off_script_skill', 0.5)))
        self.last_adjustment = None      # our latest defensive counter, for their counter-punch
        self.chart = None
        self.cond = H.Condition(policy)
        self.jaded = {}          # pid -> 0-1, carries across a season
        self.injuries = []       # this game's injuries
        self.cov_memory = {}     # what his coverage calls have produced
        self.out = set()         # unavailable right now
        self.snaps = {}
        self.snap_counts = {}

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

    def hurt(self, player, position, contact, rng, rate_fn, week=1, risk_scale=.96):
        import health as H
        pid = player.get('pid', position)
        # A man already ruled out cannot be hurt again. Without this the same
        # back was injured three times in one game.
        if pid in self.out:
            return None
        inj = H.roll_injury(player, position, contact, rng, rate_fn,
                            condition=self.cond.get(pid),
                            jaded=self.jaded.get(pid, 0.0), risk_scale=risk_scale)
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

    def new_series(self, *, unit):
        self.memories[unit].new_series()

    def observe(self, off_call, def_call, outcome, *, unit):
        # Own offense supplies protection/self-scouting; opponent offense
        # supplies the defensive coordinator's targets and tendencies.
        self.memories[unit].record(off_call, def_call, outcome)

    def adjustment_skill(self, unit):
        suffix = {'offense': 'off', 'defense': 'def'}[unit]
        return float(self.coach.get('adjust_skill_' + suffix,
                                    self.coach.get('adjust_skill', 0.5)))

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

    def adjust(self, quarter=1, rng=None, *, unit):
        """Read the trends and modify THE PLAN. Returns what changed."""
        if rng is None:
            import numpy as _np
            rng = _np.random.default_rng()
        import adjust as AD, gameplan as GP
        skill = self.adjustment_skill(unit)
        # Communication can postpone a series response without changing the
        # coach's skill or erasing observations. Explicit user plans bypass it.
        delay = max(1.0, float(getattr(self, 'road_adjust_delay', 1.0)))
        if delay > 1.0 and rng.random() >= 1.0 / delay:
            return []
        aggr = float(self.coach.get('adjust_willingness', 0.5))
        trends = AD.detect(self.memories[unit], skill=skill, unit=unit)
        ctr = AD.respond(trends, skill=skill, aggressiveness=aggr,
                         rng=rng)
        if not ctr:
            return []
        self.plan, applied = GP.adjust_plan(self.plan, ctr, skill, 0.55, quarter)
        if applied and unit == 'defense':
            self.last_adjustment = ctr
        return applied

    def end_game(self, rng, expected_snaps=45.0, bye=False):
        """Recovery and jadedness roll forward between games."""
        import health as H
        self.last_snaps = dict(self.snaps)     # keep the game log readable
        self.last_snap_counts = {unit: dict(total=row['total'], players=dict(row['players']))
                                 for unit, row in self.snap_counts.items()}
        self.snap_counts = {}
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
        if getattr(self, "defer_recovery", False):
            self.cond.cond = ended
        elif not bye:
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
        self.memories = {unit: AD.GameMemory() for unit in ('offense', 'defense')}
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
    if out.get('defensive_td'):
        return -float(AS.TD_VALUE)
    if out.get('touchdown') or float(out.get('yards') or 0.0) >= dr.yardline - 0.01 or gained >= dr.yardline - 0.01: return float(AS.TD_VALUE)
    spot = float(np.clip(dr.yardline - gained, 1.0, 99.0))
    if out.get('type') == 'interception':
        spot = _interception_spot(dr.yardline, out)
        return -_ep_state(1, 10, 100.0 - spot)
    if out.get('fumble_lost'):
        spot = float(out.get('end_spot', spot))
        return -_ep_state(1, 10, 100.0 - spot)
    if gained >= dr.togo - 0.01:
        return _ep_state(1, min(10.0, spot), spot)
    if dr.down >= 4:
        return -_ep_state(1, 10, 100.0 - spot)                     # a failed fourth down is the other side's ball
    return _ep_state(dr.down + 1, dr.togo - gained, spot)


def _resolve_live_penalty(dr, pen, out, oc):
    """
    A foul during or after the play. Returns 'replaced' if the penalty is taken instead of the play, 'added' if
    it is tacked on after it, 'enforced' for a retained gain with live-foul
    down enforcement already applied, None if declined.

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
    if out.get('defensive_td') and E.PEN_INFO[pen['penalty']]['phase'] == 'post':
        dr.try_penalty = yards if pen['on_offense'] else -yards
        pen['on_try'] = True
        return 'added'
    if pen['on_offense']:
        if (pen['penalty'] == 'Face Mask'
                and out.get('type') in ('complete', 'run', 'scramble')
                and 0 < spot_gain < dr.yardline
                and not out.get('fumble_lost')):
            # A contact foul at the end of the advance is enforced there.
            # Retain the gain for statistics (GSIS Penalty Plays 2A), then
            # repeat the down unless the NET gain still earns a first down.
            # Do not treat this live foul as a dead-ball foul after a first down.
            spot = dr.yardline - spot_gain
            walk = min(yards, (100.0 - spot) / 2.0)
            net = spot_gain - walk
            first = net >= dr.togo
            ep_enf = _ep_state(1 if first else dr.down,
                min(10.0, spot + walk) if first else dr.togo - net, spot + walk)
            if ep_enf >= _ep_play_stands(dr, out):
                return None
            pen['yards'] = walk
            dr.yardline = spot + walk
            dr.best = min(dr.best, dr.yardline)
            out['converted'] = first
            if first:
                dr.down, dr.togo = 1, min(10.0, dr.yardline)
                dr.first_downs += 1
            else:
                dr.togo -= net
            return 'enforced'
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
    # A completed forward pass beyond the line retains its gain when the
    # passer is roughed, provided possession did not change during the down.
    if (pen['penalty'] == 'Roughing the Passer' and out.get('type') == 'complete'
            and gained > 0 and not out.get('fumble_lost')
            and not out.get('change_of_possession') and not out.get('defensive_td')):
        spot = max(0.0, dr.yardline - spot_gain)
        if spot <= 0 or out.get('touchdown'):
            dr.try_penalty = yards
            pen['on_try'] = True
        else:
            pen['yards'] = min(yards, spot / 2.0)
            dr.log_pen_after = pen['yards']
            dr.log_pen_first = True
        return 'added'
    if not out.get('defensive_td') and (out.get('touchdown') or gained >= dr.yardline - 0.01 or float(np.round(gained)) >= dr.yardline):
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
    running_facemask = (pen['penalty'] == 'Face Mask'
                        and out.get('type') in ('run', 'scramble', 'complete')
                        and gained >= 0 and not out.get('fumble_lost'))
    if E.PEN_INFO[pen['penalty']]['phase'] == 'post' or running_facemask:
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
        self.start_quarter = quarter
        self.clock_running = False
        self.runoff_charged = 0.0
        self.play_clock = 40.0
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
    if out.get('end_spot') is not None:
        return float(out['end_spot'])
    caught = float(yardline) - float(out.get('air', 0.0) or 0.0)
    returned_to = caught + float(out.get('ret', 0.0) or 0.0)
    if caught <= 0 and returned_to <= 0:
        return 20.0                         # defensive touchback in the end zone
    return float(np.clip(returned_to, 0.0, 100.0))


def _prepare_interception(yardline, out):
    """Record a touchback without crediting return yards inside the end zone."""
    if out.get('type') != 'interception':
        return
    if out.get('end_spot') is not None:
        return
    caught = float(yardline) - float(out.get('air', 0.0) or 0.0)
    out['touchback'] = caught <= 0 and caught + float(out.get('ret', 0.0) or 0.0) <= 0
    if out['touchback']:
        out['ret'] = 0.0
    out['return_start'] = caught
    out['returner'] = out.get('by')
    out['return_kind'] = 'int'
    out['end_spot'] = _interception_spot(yardline, out)
    out['defensive_td'] = out['end_spot'] >= 100
    if out['defensive_td']:
        out['ret'] = 100.0 - max(0.0, caught)
        out.update(touchdown=True, scoring_side='defense')


def _healthy_quarterback(roster, state):
    """Use healthy QB depth, then the same emergency pool as offensive roles."""
    import offense_roles as OR
    depth = OR.roster_depth(roster)
    candidates = list(depth.get('QB', ())) + [roster.get('qb')] + list(roster.get('qbs') or ())
    candidates += [p for men in depth.values() for p in men]
    excluded = state.out if state is not None else ()
    return next((p for p in candidates if p is not None and p.get('pid') not in excluded), None)


def _prepare_fumble(dr, out, off, deff, rng, rate_fn, off_state=None):
    """Resolve the loose ball before penalties choose between play outcomes."""
    import events as E
    from plays import defensive_return, YAC
    ev = {'complete': 'complete_pass', 'run': 'run', 'sack': 'sack', 'scramble': 'scramble'}.get(out['type'])
    if ev is None or out.get('touchdown'):
        return
    men = [off['qb'], off.get('rb')] + list(off.get('wr') or []) + list(off.get('te') or [])
    carrier_id = out.get('target') if ev == 'complete_pass' else out.get('carrier_pid') or out.get('carrier')
    carrier = next((m for m in men if m and m.get('pid') == carrier_id), None) if carrier_id else None
    if carrier is None:
        carrier = off['qb'] if ev in ('sack', 'scramble') or out.get('sneak') else (off.get('rb') or off['qb'])
    defenders = list(deff.get('dl') or []) + list(deff.get('lb') or []) + list(deff.get('db') or [])
    contact_id = out.get('by') if ev == 'sack' else out.get('tackler')
    contact = next((p for p in defenders if p.get('pid') == contact_id), None) if contact_id else None
    impact = rate_fn(contact, YAC['tackler']['impact']) if contact is not None else 0.70
    fum = E.fumble_check(carrier, ev, rng, rate_fn, hit_power=impact, env_mult=ENV.fumble_mult,
                        rate_mult=(getattr(off_state, 'staff_fx', None) or {}).get('fum_off', 1.0))
    if not fum:
        return
    out.update(fumble=True, fumble_lost=bool(fum['lost']), fumble_by=carrier.get('pid'),
               fumble_forced=bool(fum.get('forced', True)))
    if not fum['lost']:
        return
    if not defenders:
        raise ValueError('A defensive fumble recovery requires a defender on the field')
    weights = np.array([3.0 if (ev == 'sack' and p in (deff.get('dl') or [])) else
                        1.5 if p.get('pid') == out.get('tackler') else 1.0 for p in defenders])
    recoverer = defenders[int(rng.choice(len(defenders), p=weights/weights.sum()))]
    start = float(np.clip(dr.yardline - float(np.round(out.get('yards', 0) or 0)), 0, 100))
    out.update(recoverer=recoverer.get('pid'), fumble_recovered_by=recoverer.get('pid'))
    out.update(defensive_return(start, 'fumble', recoverer,
               [m for m in men + list(off.get('ol') or []) if m], rng, rate_fn))


def _finish_turnover(dr, out, penalty=None):
    dr.yardline = float(out['end_spot'])
    if out.get('defensive_td'):
        dr.result, dr.points = 'Defensive touchdown', -6
    else:
        dr.result = 'Turnover'
        if penalty is not None:
            _enforce_turnover_penalty(dr, penalty)
    dr.log_pen_after = 0.0
    dr.log_pen_first = False
    _tick(dr, return_seconds(out,
        play_seconds('interception' if out['type'] == 'interception' else 'fumble'),
        setup=live_play_seconds(out)))

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

def specialist_for(roster, state, position, rate_fn):
    """Use healthy specialist depth, then the best available emergency leg."""
    out = getattr(state, 'out', set())
    preferred = [roster.get(position.lower())] + list((roster.get('depth') or {}).get(position, []))
    for p in preferred:
        if p and p.get('pid') not in out:
            return p
    candidates = [p for group in (roster.get('depth') or {}).values() for p in group
                  if p and p.get('pid') not in out]
    if not candidates:
        candidates = [p for key in ('ol', 'wr', 'lb', 'db') for p in roster.get(key, [])
                      if p and p.get('pid') not in out]
    return max(candidates, key=lambda p: rate_fn(p, {'kick_power_rating': .5, 'kick_acc_rating': .5}), default={})


def special_injuries(state, players, rng, rate_fn, week, contact=.35):
    """Small contact exposure, funded by reduced scrimmage injury risk.

    A special-teams rep carries one tenth of the existing per-snap hazard;
    scrimmage hazard is reduced four percent. Deduplicate multi-role players.
    Injury severity/recovery and existing durability/fatigue still apply.
    """
    if state is None:
        return []
    injuries = []
    for p in {p['pid']: p for p in players if p and p.get('pid')}.values():
        injury = state.hurt(p, p.get('pos', 'ST'), contact, rng, rate_fn, week, risk_scale=.1)
        if injury:
            injury['source'] = 'special_teams'
            injuries.append(injury)
    return injuries


def kick_injuries(offense, defense, off_state, def_state, kind, rng, rate_fn, week, returned=False):
    off, deff = kick_penalty_units(offense, defense, off_state, def_state, kind, rate_fn)
    if returned:
        import kick_returns as KR
        returner = returner_for(defense, def_state, rate_fn, kind='pr')
        off = [('ST', p) for p in KR.unit(offense, off_state, rate_fn)] + [
            ('P', specialist_for(offense, off_state, 'P', rate_fn))]
        deff = [('ST', p) for p in KR.unit(defense, def_state, rate_fn, True, returner.get('pid'))] + [('RET', returner)]
    return (special_injuries(off_state, [p for _, p in off], rng, rate_fn, week, .8 if returned else .35)
            + special_injuries(def_state, [p for _, p in deff], rng, rate_fn, week, .8 if returned else .35))


def kick_penalty_units(offense, defense, off_state, def_state, kind, rate_fn):
    """A fixed, healthy kick unit; no reserve can influence its foul risk."""
    import kick_returns as KR
    unavailable = getattr(off_state, 'out', set())
    snapper = snapper_for(offense, off_state)
    candidates = [snapper, specialist_for(offense, off_state, 'P' if kind == 'punt' else 'K', rate_fn)]
    if kind != 'punt': candidates.append(_healthy_quarterback(offense, off_state))
    candidates += [p for p in offense.get('ol', []) if not snapper or p.get('pos') != 'C']
    candidates += KR.unit(offense, off_state, rate_fn, True)
    chosen = list({p['pid']: p for p in candidates if p and p.get('pid') and p['pid'] not in unavailable}.values())[:11]
    off_rows = [(p.get('pos', 'ST'), p) for p in chosen]
    unavailable = getattr(def_state, 'out', set())
    candidates = [(k.upper(), p) for k in ('dl', 'lb', 'db') for p in defense.get(k, [])
                  if p and p.get('pid') and p['pid'] not in unavailable]
    def_rows = list({p['pid']: (role, p) for role, p in candidates}.values())[:11]
    return off_rows, def_rows


def kick_flag(rng, kind, offense, defense, off_state, def_state, rate_fn, book):
    import events as E
    off_rows, def_rows = kick_penalty_units(offense, defense, off_state, def_state, kind, rate_fn)
    PP.book_opportunities(book, off_rows + def_rows)
    return E.special_teams_penalty_check(rng, kind, offense_players=off_rows, defense_players=def_rows)


def _kick_presnap_flag(dr, pen, half_end=None, book=None):
    """A pre-snap kick foul keeps the same down and lets the coach decide again."""
    if not pen or pen.get('phase') != 'pre': return False
    if pen.get('penalty') == 'Delay of Game' and not _delay_clock_expired(dr, half_end):
        return True
    clock_before = dr.clock
    _penalty_ready_clock(dr, pen, half_end, before_snap=True, was_running=dr.clock_running)
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
    PP.decision(pen, True); PP.book_flag(book, pen)
    dr.log.append(dict(type='penalty', timing='before_snap', clock=clock_before, **pen))
    wall = half_end if half_end is not None else 0.0
    if clock_before - wall > 120 >= dr.clock - wall and not getattr(dr, '_two_min', False):
        dr._two_min = True
        dr.log.append(dict(type='two_minute', clock=dr.clock))
    return True

def _kick_roughing(dr, pen, kick, book=None):
    """Accept roughing when the failed kick or punt is worse than a first down."""
    if not pen or pen.get('phase') != 'kick': return False
    if kick.get('made') or kick.get('blocked'):
        kick['declined_penalty'] = PP.decision(pen, False); PP.book_flag(book, pen)
        return False
    kick['nullified'] = True
    dr.log.append(kick)
    walk = min(pen['yards'], dr.yardline / 2.0)
    pen['yards'] = walk
    PP.decision(pen, True); PP.book_flag(book, pen)
    dr.yardline -= walk
    dr.down, dr.togo = 1, min(10.0, dr.yardline)
    dr.first_downs += 1
    dr.log.append(dict(type='penalty', **pen))
    return True

def _kick_offside(dr, pen, kick, book=None):
    """The kicking side may keep a made FG or a good punt; otherwise it can replay the down."""
    if not pen or pen.get('phase') != 'kick_offside':
        return False
    if kick.get('made'):
        kick['declined_penalty'] = PP.decision(pen, False); PP.book_flag(book, pen)
        return False
    walk = min(pen['yards'], dr.yardline / 2.0)
    if kick.get('type') == 'punt' and not kick.get('blocked') and walk < dr.togo:
        kick['declined_penalty'] = PP.decision(pen, False); PP.book_flag(book, pen)
        return False
    kick['nullified'] = True
    dr.log.append(kick)
    dr.yardline -= walk
    dr.togo -= walk
    pen['yards'] = walk
    PP.decision(pen, True); PP.book_flag(book, pen)
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
        dr.yardline = 100.0
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
    if out.get('type') not in ('run', 'complete', 'scramble') or out.get('nullified') or out.get('defensive_td'):
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
    """Select the called personnel and preserve each defender's on-field job."""
    if is_offense:
        import offense_roles as OR
        return OR.field(roster, package, rng=rng, state=state) if str(package) in OR.PACKAGES else None
    import defense_roles as DR
    return DR.field(roster, package, front_family, rng=rng, state=state)


def field_units(roster, state, rng, is_offense, package=None, front_family=None):
    """Record the actual selected unit without changing selection or random draws."""
    result, positions = _field_units(roster, state, rng, is_offense, package, front_family)
    if state is not None:
        if not hasattr(state, 'snap_counts'): state.snap_counts = {}
        row = state.snap_counts.setdefault('offense' if is_offense else 'defense', dict(total=0, players={}))
        row['total'] += 1
        for pid in positions:
            row['players'][pid] = row['players'].get(pid, 0) + 1
    return result, positions


class _PendingSnap:
    """Select once; commit workload only when a snap actually happens."""
    def __init__(self, state):
        self.original = state
        self.calls = []
        self.snap_counts = {}

    def __getattr__(self, key):
        return getattr(self.original, key)

    def snap(self, player, position, on_field=True):
        self.calls.append((player, position, on_field))

    def state(self, player, position):
        return player

    def commit(self, unit):
        for player, position, on_field in self.calls:
            self.original.snap(player, position, on_field)
        if not hasattr(self.original, 'snap_counts'): self.original.snap_counts = {}
        for side, counts in self.snap_counts.items():
            row = self.original.snap_counts.setdefault(side, dict(total=0, players={}))
            row['total'] += counts['total']
            for pid, n in counts['players'].items():
                row['players'][pid] = row['players'].get(pid, 0) + n
        changed = {p.get('pid'): self.original.state(p, role)
                   for p, role, active in self.calls if active}
        def transformed(value):
            if isinstance(value, dict):
                # Reserve dictionaries contain many ratings but need no work:
                # only selected participants receive a state transformation.
                if 'pid' in value: return changed.get(value['pid'], value)
                return {k: transformed(v) for k, v in value.items()}
            if isinstance(value, list): return [transformed(v) for v in value]
            if isinstance(value, tuple): return tuple(transformed(v) for v in value)
            return value
        return {k: transformed(v) if k != 'depth' else v for k, v in unit.items()}


def _field_units(roster, state, rng, is_offense, package=None, front_family=None):
    """
    Put eleven men on the field for this snap, honouring condition and
    injuries. Anyone not selected recovers. This is where rotation actually
    happens - the depth chart is walked until someone is fresh enough.
    """
    if not is_offense:
        import defense_roles as DR
        selected = DR.field(roster, package or 'nickel', front_family, rng=rng, state=state)
        out = dict(roster); out.update(selected)
        positions = {DR.pid(row['player']): DR.position(row['player'])
                     for row in selected['defensive_assignments']}
        return out, positions
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
                    import offense_roles as OR
                    gaps = OR.back_quality_gaps(backs)
                    pick = None
                    for rank, b in enumerate(backs):
                        gap = gaps[rank]
                        if not state.cond.needs_rest(b.get('pid'), 'HB', rng, b.get('stamina_rating', 70.0), gap):
                            pick = b; break
                    p = pick or backs[0]
                    for b in backs:
                        if b is not p: state.snap(b, 'HB', False)
                # an injured starter yields to the backup - real leagues carry
                # ~2.4 QBs taking meaningful snaps, which is most of why the
                # real QB15-to-QB25 distribution falls off a cliff
                if key == 'qb' and p.get('pid') in state.out:
                    p = _healthy_quarterback(roster, state)
                    if p is None:
                        raise ValueError('No healthy player available at quarterback')
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
              timeouts=None, pos='home', half_end=None, must_score=False, try_allowed=True,
              start_state=None):
    """
    Play a full possession. resolve_fn is plays.resolve_play; call_off/call_def
    are the scheme-layer callers.
    """
    dr = Drive(offense, defense, start_yardline, clock, quarter, score_diff, rng)
    if quarter in (2, 4) and clock - (1800 if quarter == 2 else 0) <= 120:
        dr._two_min = True
    if start_state is not None:
        dr.down, dr.togo = start_state
    import events as E
    # the kick that opened this possession, when there was one, is the drive's first entry
    ko = LAST_KICKOFF.pop('r', None)
    if ko is not None and abs(float(ko.get('new_yardline', -1)) - float(start_yardline)) < 0.5:
        dr.log.append(dict(ko, type='kickoff', carrier=ko.get('returner'), clock=ko.get('clock', clock)))
        wall = HALF if quarter == 2 else 0 if quarter == 4 else None
        if wall is not None and float(ko.get('clock', clock)) > wall + 120 >= clock:
            dr._two_min = True
            dr.log.append(dict(type='two_minute', clock=clock))
        if ko.get('touchdown'):
            dr.result, dr.points, dr.yardline = 'Touchdown', 6, 0.
        elif ko.get('fumble_lost'):
            dr.result = 'Turnover'
        if dr.result is not None:
            dr.start = float(ko.get('return_start', 95))
            dr.return_only = True
        if ko.get('penalty'):
            dr.log.append(dict(type='penalty', **ko['penalty']))
    # Adjustment happens AFTER EACH SERIES, which is what the coaches describe:
    # "If you wait until halftime to make your adjustments, you're too late."
    for st, unit in ((off_state, 'offense'), (def_state, 'defense')):
        if st is not None:
            st.new_series(unit=unit)
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
                st.adjust(quarter, rng, unit=unit)

    import advanced_stats as AS
    pending = None                        # the last scrimmage play, waiting for its after-state
    _seen = 0
    chasing = False  # keep this possession's established hurry-up intent
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
        if dr.start_quarter <= 4:
            current_quarter = min(4, int((GAME - dr.clock) // QUARTER) + 1)
            if current_quarter != dr.quarter:
                dr.log.append(dict(type='period', quarter=current_quarter, clock=dr.clock))
                dr.clock_running = False
                dr.runoff_charged = 0.0
            quarter = dr.quarter = current_quarter
        # 10. THE KNEEL. With the ball and no time to use it, out of range, a club takes a knee: the first half at
        # any score, the second half when it is not behind. Real clubs do not throw from their own 35 at 0:04.
        secs_left_half = dr.clock - wall
        dr._own_timeouts = timeouts.left.get(pos, 0) if timeouts is not None else 0
        chasing = chasing or multi_score_urgency(secs_left_half, dr.score_diff, dr.quarter)
        opp_tos = timeouts.left.get('away' if pos == 'home' else 'home', 0) if timeouts is not None else 0
        if (half_end is None and dr.quarter == 4 and dr.score_diff > 0
                and not comeback_viable(secs_left_half, dr.score_diff)):
            opp_tos = 0  # inventory remains; this defense will not stop knees
        clock_dies = secs_left_half <= 3 or (secs_left_half <= 10 and opp_tos == 0)
        can_kneel = _can_kneel_out(dr, secs_left_half, opp_tos)
        victory_kneel = (half_end is None and dr.quarter == 4
                         and dr.score_diff > 0 and can_kneel)
        _plan0 = end_of_half_plan(dr, offense, defense, rate_fn, timeouts, pos, half_end, secs_left_half, coach=(off_state.coach if off_state is not None else None))
        closing_kneel = (clock_dies and can_kneel and (
            (_plan0 is not None and _plan0['choice'] == 'kneel') or
            (_plan0 is None and ((half_end is None and dr.score_diff > 0) or
                                (dr.yardline > 45 and dr.score_diff >= 0)))))
        if victory_kneel or closing_kneel:
            qb = _healthy_quarterback(offense, off_state)
            if qb is None:
                raise ValueError('No healthy player available to kneel')
            # Use ordinary healthy units and snap accounting, without invoking
            # tackle, fumble, or ordinary play-resolution randomness for a knee.
            knee_off = dict(offense, qb=qb, qbs=[qb])
            os = off_state if hasattr(off_state, 'available') else None
            ds = def_state if hasattr(def_state, 'available') else None
            off_f, _ = field_units(knee_off, os, rng, True, package='11')
            def_f, _ = field_units(defense, ds, rng, False)
            out = dict(type='kneel', passer=off_f['qb'].get('pid'), yards=-1.0,
                       down=dr.down, ydstogo=dr.togo, yardline=dr.yardline, clock=dr.clock)
            dr.log.append(out)
            if book is not None:
                book.record(out, off_f, def_f, rng)
            remaining, stopped, warning = _kneel_interval(secs_left_half, dr.down, opp_tos)
            dr.plays += 1
            _advance(dr, -1)
            dr.clock = wall + remaining
            dr.clock_running = not stopped and not warning and remaining > 0
            dr.play_clock = 40.0
            dr.runoff_charged = max(0.0, secs_left_half - remaining - 2.0) if dr.clock_running else 0.0
            if stopped:
                other = 'away' if pos == 'home' else 'home'
                timeouts.use(other)
                dr.log.append(dict(type='timeout', side=other,
                    side_abbr=getattr(def_state, 'abbr', None) or other.upper(),
                    left=timeouts.left[other], clock=dr.clock))
            if warning:
                dr._two_min = True
                dr.log.append(dict(type='two_minute', clock=dr.clock))
            if remaining <= 0:
                dr.result = 'End of half'
            elif dr.down > 4:
                dr.result = 'Turnover on downs'
            continue
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
        if dr.clock_running and _plan is not None and not _plan.get('hurry', True) and _plan['choice'] in ('kick', 'shot') and secs_in_half > 14 and dr.down < 4:
            # THE BLEED'S WAIT: the play clock runs down before the last snap, so the shot or the kick comes with a
            # few seconds left and the other side gets nothing back
            burn = float(min(max(0.0, min(PLAY_SECS_RUN - 5.0, dr.play_clock) - dr.runoff_charged), secs_in_half - 10.0))
            _tick(dr, burn); secs_in_half -= burn; clock_kick_time = secs_in_half <= 8 or (secs_in_half <= 22 and timeouts is not None and timeouts.left.get(pos, 0) == 0)
            dr.runoff_charged += burn
        _kick_by_plan = _plan is not None and _plan['choice'] == 'kick' and dr.down < 4 and (_plan.get('hurry', True) or clock_kick_time or secs_in_half <= 14)
        _kick_old = ((quarter >= 4 and -3 <= dr.score_diff <= 0) or (half_end is not None and quarter <= 2)) and dr.yardline <= 37 and dr.down < 4 and clock_kick_time and _plan is None
        if _kick_by_plan or _kick_old:
            flag = kick_flag(rng, 'field_goal', offense, defense, off_state, def_state, rate_fn, book)
            if _kick_presnap_flag(dr, flag, half_end, book): continue
            fg = attempt_field_goal(dr.yardline, specialist_for(offense, off_state, 'K', rate_fn), rng, rate_fn,
                                    snapper=snapper_for(offense, off_state))
            fg['kicker_pid'] = specialist_for(offense, off_state, 'K', rate_fn).get('pid')
            fg['injuries'] = kick_injuries(offense, defense, off_state, def_state, 'field_goal', rng, rate_fn, week)
            fg.update(clock=dr.clock, down=dr.down, ydstogo=dr.togo, yardline=dr.yardline)
            if _kick_roughing(dr, flag, fg, book):
                dr.clock -= play_seconds('field_goal')
                continue
            if _kick_offside(dr, flag, fg, book):
                dr.clock -= play_seconds('field_goal')
                continue
            if book is not None: book.special('fg', fg['kicker_pid'], **fg)
            dr.clock -= min(dr.clock, play_seconds('field_goal'))
            dr.result = 'Field goal' if fg['made'] else 'Missed field goal'
            dr.points = fg['points']; dr.log.append(fg); break
        # ---- fourth down is a decision, not a play ----
        if dr.down == 4:
            # the head coach's appetite, off his identity when he has one
            aggr4 = float(off_state.coach.get('fourth_down', aggression)) if off_state is not None and off_state.coach else aggression
            dec = fourth_down_decision(dr.yardline, dr.togo, dr.score_diff,
                                       dr.clock, rng, aggr4,
                                       kicker=specialist_for(offense, off_state, 'K', rate_fn), rate_fn=rate_fn,
                                       must_score=must_score, is_home=int(pos == 'home'),
                                       timeout_edge=(timeouts.left.get(pos, 0) - timeouts.left.get('away' if pos == 'home' else 'home', 0)) if timeouts is not None else 0,
                                       half_seconds_left=(dr.clock - half_end if half_end is not None else None),
                                       half_intent=getattr(dr, '_half_stall_intent', None),
                                       punter=offense.get('p'),
                                       returner=returner_for(defense, def_state, rate_fn, kind='pr'),
                                       snapper=snapper_for(offense, off_state),
                                       defensive_confidence=PST.confidence(off_state))
            if dec == 'field_goal':
                flag = kick_flag(rng, 'field_goal', offense, defense, off_state, def_state, rate_fn, book)
                if _kick_presnap_flag(dr, flag, half_end, book): continue
                fg = attempt_field_goal(dr.yardline, specialist_for(offense, off_state, 'K', rate_fn), rng, rate_fn,
                                        snapper=snapper_for(offense, off_state))
                fg['kicker_pid'] = specialist_for(offense, off_state, 'K', rate_fn).get('pid')
                fg['injuries'] = kick_injuries(offense, defense, off_state, def_state, 'field_goal', rng, rate_fn, week)
                fg.update(clock=dr.clock, down=dr.down, ydstogo=dr.togo, yardline=dr.yardline)
                if _kick_roughing(dr, flag, fg, book):
                    dr.clock -= play_seconds('field_goal')
                    continue
                if _kick_offside(dr, flag, fg, book):
                    dr.clock -= play_seconds('field_goal')
                    continue
                if book is not None: book.special('fg', fg['kicker_pid'], **fg)
                dr.clock -= play_seconds('field_goal')
                dr.result = 'Field goal' if fg['made'] else 'Missed field goal'
                dr.points = fg['points']; dr.log.append(fg); break
            if dec == 'punt':
                flag = kick_flag(rng, 'punt', offense, defense, off_state, def_state, rate_fn, book)
                if _kick_presnap_flag(dr, flag, half_end, book): continue
                returner = returner_for(defense, def_state, rate_fn, kind='pr')
                import kick_returns as KR
                p = punt(dr.yardline, specialist_for(offense, off_state, 'P', rate_fn),
                         returner, rng, rate_fn,
                         snapper=snapper_for(offense, off_state),
                         kicking=[m for m in (offense.get('ol', []) + [specialist_for(offense, off_state, 'P', rate_fn)])
                                  if m and (off_state is None or m.get('pid') not in off_state.out)],
                         receiving=[m for m in (defense.get('dl', []) + defense.get('lb', []))
                                    if m and (def_state is None or m.get('pid') not in def_state.out)],
                         return_coverage=KR.unit(offense, off_state, rate_fn),
                         return_blockers=KR.unit(defense, def_state, rate_fn, True, returner.get('pid')))
                p['punter_pid'] = specialist_for(offense, off_state, 'P', rate_fn).get('pid')
                p['injuries'] = kick_injuries(offense, defense, off_state, def_state, 'punt', rng, rate_fn, week, returned=p.get('how') == 'return')
                p.update(clock=dr.clock, down=dr.down, ydstogo=dr.togo, yardline=dr.yardline)
                if _kick_roughing(dr, flag, p, book):
                    dr.clock -= play_seconds('punt')
                    continue
                if _kick_offside(dr, flag, p, book):
                    dr.clock -= play_seconds('punt')
                    continue
                if p.get('how') == 'return':
                    return_rows = [('ST', m) for m in KR.unit(defense, def_state, rate_fn, True, returner.get('pid'))]
                    PP.book_opportunities(book, return_rows)
                    return_flag = E.special_teams_penalty_check(rng, 'punt', returned=True, phase='return', defense_players=return_rows)
                    KR.enforce_return_flag(p, return_flag)
                    if return_flag: PP.book_flag(book, p.get('penalty') or p.get('declined_penalty'))
                    # Return penalties change the next spot, not punt yardage.
                    p['net'] = round(p['gross'] - p.get('ret', 0), 1)
                if book is not None:
                    book.special('punt', p['punter_pid'], **p)
                    if p.get('how') == 'return' or (p.get('ret') and not p.get('touchback')):
                        KR.book_return(book, 'pr', p)
                _tick(dr, return_seconds(p, play_seconds('punt'), setup=5.0))
                dr.clock = max(wall, dr.clock)
                dr.result = 'Punt'; dr.log.append(p)
                if p.get('blocked') and 'end_spot' in p:
                    _apply_blocked_punt(dr, p)
                    AS.book_special(book, dr, p, offense)
                    p['epa_booked'] = True
                    if dr.result is None:
                        continue
                    break
                if p.get('penalty'):
                    dr.log.append(dict(type='penalty', **p['penalty']))
                if p.get('touchdown'):
                    dr.result, dr.points, dr.yardline = 'Defensive touchdown', -6, 100.
                    p['scoring_side'] = 'defense'
                elif p.get('fumble_lost'):
                    dr.result = 'Recovered punt'
                dr.next_yardline = (100 - p['new_yardline']) if p.get('fumble_lost') else p['new_yardline']
                AS.book_special(book, dr, p, offense)
                p['epa_booked'] = True
                break

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
        # Preserve the clock-burning early-down bias. On third and long use
        # the scheme caller's score/clock/down table: another negative bias
        # overwhelms it and makes a leading team almost never throw for a first.
        late_lean = 0.0
        final_period = (quarter >= 4 and half_end is None) or (half_end is not None and quarter <= 2)
        if final_period:
            if dr.score_diff > 0 and dr.yardline >= 80 and secs_in_half <= 60:
                late_lean = -8.0                                   # ahead, inside your own 20, under a minute: the clock is the point and a run cannot stop it
            elif dr.score_diff > 0 and half_end is None and dr.clock <= 240:
                late_lean = 0.0 if (dr.down == 3 and dr.togo >= 6) else -3.5
            elif dr.score_diff <= 0 and secs_in_half <= 120:
                late_lean = 1.0 if dr.togo <= 1 else (12.0 if secs_in_half <= 30 else 6.5)          # the two-minute drill: throw; under thirty seconds there is no other call
            elif dr.score_diff < 0 and half_end is None and dr.clock <= comeback_clock_budget(-dr.score_diff):
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
        elif _pl is not None and _pl.get('quick_play'):
            oc.update(is_pass=True, depth='short', concept='slant_flat', play_action=False, rpo=False, plan_depth=True)
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
        # If timeouts or field position prevent safely kneeling out the half,
        # preserve the planner's protect-the-ball intent with a live run.
        protect_half = (half_end is not None and dr.down < 4
                        and _pl is not None and _pl['choice'] == 'kneel')
        if protect_half:
            oc = dict(oc, is_pass=False, scheme='inside_zone',
                      play_action=False, rpo=False)

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

        # The audible must see the box the defense will actually show.
        # Resolve this once; applying it again after the check would reroll it.
        apply_defensive_plan(dc, def_state, rng)

        # THE AUDIBLE. He reads the look they are SHOWING and modifies the
        # call - he does not go back to the sheet and pick again, which would
        # let a good quarterback beat every defence every time. And the look
        # can be a lie: a disguised coverage sells him a picture that is not
        # there and he checks into something worse. That is what disguise is
        # for, and the engine already carried a shown shell and an actual one
        # with nothing reading the difference.
        try:
            import playcall as PC
            saved_clock_run = dict(oc) if (half_end is not None and secs_in_half <= PLAY_SECS
                and dr.yardline >= 99 and dr.down < 4 and _pl is not None
                and _pl['choice'] == 'kneel') else None
            oc, checked = PC.audible(oc, dc, offense, rate_fn, rng,
                                     score_diff=dr.score_diff, secs_left=dr.clock,
                                     family_mix=(off_state.plan.run_scheme_mix
                                                 if off_state is not None and off_state.plan is not None else None))
            if saved_clock_run is not None:
                oc, checked = saved_clock_run, None
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
                    off_state.adjustment_skill('offense')):
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
        # Select actual participants once, before a flag, without charging a snap.
        if def_state is not None:
            def_state.rotation_context = dict(down=dr.down, to_go=dr.togo, score_diff=dr.score_diff)
        pending_off = _PendingSnap(off_state) if off_state is not None else None
        pending_def = _PendingSnap(def_state) if def_state is not None else None
        off_f, off_pos = field_units(offense, pending_off, rng, True, oc.get('personnel'))
        def_f, def_pos = field_units(defense, pending_def, rng, False,
                                    dc.get('personnel'), front_family=dc.get('front_family'))
        off_rows, def_rows = PP.unit(off_f, True), PP.unit(def_f, False)
        PP.book_opportunities(book, off_rows + def_rows)
        # Awareness and staff retain their existing effects; hidden discipline
        # modifies eligible individual foul hazards separately in events.py.
        fx_o = getattr(off_state, 'staff_fx', None) or {}; fx_d = getattr(def_state, 'staff_fx', None) or {}
        _dmen = [p for _, p in def_rows]
        d_awr = float(np.mean([rate_fn(d, {'awareness_rating': 1.0}) for d in _dmen])) if _dmen else 0.70
        _omen = [p for _, p in off_rows]
        o_awr = float(np.mean([rate_fn(p, {'awareness_rating': 1.0}) for p in _omen])) if _omen else 0.70
        if protect_half:
            oc.update(is_pass=False, scheme='inside_zone', play_action=False, rpo=False)
        if _pl is not None and _pl.get('quick_play'):
            oc.update(is_pass=True, depth='short', concept='slant_flat', play_action=False, rpo=False, no_huddle=True)
        _in_drill = hurry_for_snap(secs_in_half, dr.score_diff, getattr(dr, '_plan', None), oc, dr.quarter)
        penalty_context = dict(is_pass=oc['is_pass'],
                              offense_discipline=float(np.clip(0.70 + 0.8 * (o_awr - 0.787), 0.5, 0.9)),
                              defense_discipline=float(np.clip(0.70 + 0.8 * (d_awr - 0.787), 0.5, 0.9)),
                              offense_multiplier=fx_o.get('pen_off', 1.0), defense_multiplier=fx_d.get('pen_def', 1.0),
                              noise=(getattr(off_state, 'road_noise', 1.0) if off_state is not None else 1.0), hurry=_in_drill,
                              offense_players=off_rows, defense_players=def_rows)
        pen = E.penalty_check(rng, timing='pre', **penalty_context)
        live_pen = pen if (pen and not pen['nullifies']) else None
        if pen and pen['nullifies']:
            if pen.get('penalty') == 'Delay of Game' and not _delay_clock_expired(dr, half_end):
                continue
            penalty_clock = dr.clock
            _penalty_ready_clock(dr, pen, half_end, before_snap=True,
                was_running=dr.clock_running, hurry=_in_drill,
                tempo=(off_state.plan.tempo if off_state is not None and off_state.plan is not None else 0.5))
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
            PP.decision(pen, True); PP.book_flag(book, pen)
            dr.log.append(dict(type='penalty', timing='before_snap', clock=penalty_clock, **pen))
            if penalty_clock - wall > 120 >= dr.clock - wall and not getattr(dr, '_two_min', False):
                dr._two_min = True
                dr.log.append(dict(type='two_minute', clock=dr.clock))
            continue

        if pending_off is not None: off_f = pending_off.commit(off_f)
        if pending_def is not None: def_f = pending_def.commit(def_f)

        # the back who actually carries it
        # the back who carries it is the back on the field: the rotation in
        # field_units decides who that is
        oc['execution_mod'] = script_mod
        out = resolve_fn(off_f, def_f, oc, dc, ytg_i, rng)
        # the situation rides with the play, for the ticker and the probes
        if isinstance(out, dict):
            out['down'] = dr.down; out['ydstogo'] = dr.togo; out['yardline'] = dr.yardline; out['clock'] = dr.clock
            out['passer'] = off_f['qb'].get('pid') if out.get('is_pass') or out.get('type') in ('complete', 'incomplete', 'interception', 'drop', 'sack', 'scramble') else None
            _snap_state = (dr.down, dr.togo, dr.yardline)
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
                won = receiver_won_read(out)
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
        out['def_personnel'] = dc.get('personnel')
        out['blitz'] = bool(dc.get('blitz')) or int(dc.get('rushers', 4)) >= 5
        dr.log.append(out)
        for st, unit in ((off_state, 'offense'), (def_state, 'defense')):
            if st is not None: st.observe(oc, dc, out, unit=unit)

        injury_log_start = len(dr.log)
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

        snap_injuries = [i for i in dr.log[injury_log_start:] if i.get('type') == 'injury']
        late_injury = bool(snap_injuries and dr.quarter in (2, 4) and getattr(dr, '_two_min', False))
        t = out['type']
        # a collapsed pocket is not automatically a sack - a mobile QB runs
        if out.get('pb_award'):
            # Expected sack charges follow the same escape opportunity as
            # actual charges; pressure evidence survives a QB escape.
            out['pb_sack_survival'] = 1. - E.scramble_chance(off_f['qb'], 1.0, 1.4, rate_fn)
        if t == 'sack':
            if rng.random() < E.scramble_chance(off_f['qb'], 1.0, 1.4, rate_fn):
                _old = out
                _head = {k: _old.get(k) for k in ('down', 'ydstogo', 'yardline', 'clock', 'passer', 'personnel', 'is_pass', 'pr_reps', 'rush_pressures', 'pb_reps', 'pb_opportunities', 'pb_award', 'pb_sack_survival', 'pressured', 'coverage_evidence', 'ttt') if k in _old}
                out = E.resolve_scramble(off_f['qb'], def_f['dl'] + def_f['lb'] + def_f['db'], ytg_i, rng, rate_fn); out.update({k: v for k, v in _head.items() if k not in out})
                t = 'scramble'
                for _i in range(len(dr.log) - 1, -1, -1):
                    if dr.log[_i] is _old: dr.log[_i] = out; break          # replace the play itself, not whatever was logged after it
        if live_pen is None:
            live_pen = E.penalty_check(rng, timing='live', outcome=out, **penalty_context)
        if live_pen is None and out.get('throwaway') and rng.random() < 0.12:
            live_pen = dict(penalty='Intentional Grounding', yards=10.0, rule_yards=10.0,
                            on_offense=True, auto_first=False, nullifies=False)
            live_pen = PP.attribute(live_pen, PP.profile('Intentional Grounding', off_rows), rng)
        live_pen = E.contextual_penalty(live_pen, out, oc, rng, off_rows, def_rows)
        _prepare_scoring_play(dr, out)
        _prepare_interception(dr.yardline, out)
        _prepare_fumble(dr, out, off_f, def_f, rng, rate_fn, off_state)
        live_seconds = live_play_seconds(out)
        out['live_seconds'] = live_seconds
        if live_pen is not None:
            original_foul = live_pen['penalty']
            taken = _resolve_live_penalty(dr, live_pen, out, oc)
            if live_pen['penalty'] != original_foul:
                rows = off_rows if live_pen['on_offense'] else def_rows
                live_pen = PP.attribute(live_pen, PP.profile(live_pen['penalty'], rows, out), rng)
            PP.decision(live_pen, taken in ('replaced', 'enforced', 'added'))
            PP.book_flag(book, live_pen)
            if live_pen['declined']:
                # Keep declined evidence on the play, without creating an
                # enforced-penalty row in legacy team aggregate consumers.
                out['declined_penalty'] = dict(live_pen)
            if taken in ('replaced', 'added') and not live_pen.get('on_offense'):
                dr.untimed = True; dr.untimed_at = len(dr.log) + 1     # the penalty entry appended next is the last thing in the log
            if taken in ('replaced', 'enforced'):
                # Both paths already applied field/down enforcement. Only a
                # previous-spot replacement erases the snap's statistics.
                if taken == 'enforced':
                    if book is not None:
                        book.record(out, off_f, def_f, rng)
                        if out.get('fumble'): book.record_fumble(out)
                    pending = (out, off_f, def_f, _snap_state)
                elif live_pen['penalty'] == 'Intentional Grounding':
                    if book is not None: book.record(out, off_f, def_f, rng)
                else:
                    dr.plays -= 1
                    out['nullified'] = True
                penalty_entry = dict(type='penalty', **live_pen)
                dr.log.append(penalty_entry)
                # A wiped snap consumes live time, followed by ready-for-play
                # runoff only when the clock is legally allowed to restart.
                secs_in_half_p = (dr.clock - half_end) if half_end is not None else dr.clock
                _plan_p = end_of_half_plan(dr, offense, defense, rate_fn, timeouts, pos, half_end, secs_in_half_p - PLAY_SECS, coach=(off_state.coach if off_state is not None else None)) if secs_in_half_p - PLAY_SECS > 4 else None
                # No timeout is needed when the enforced foul already starts on
                # the snap. Keep timeout inventory for subsequent live downs.
                late_penalty = secs_in_half_p - live_seconds <= (120.0 if dr.quarter <= 2 else 300.0)
                used_p, used_by_p = (False, None) if late_penalty or late_injury else _timeout_call(dr, t, out, timeouts, pos, half_end, secs_in_half_p, coach=(off_state.coach if off_state is not None else None), plan=_plan_p, dcoach=(def_state.coach if def_state is not None else None))
                hurry_p = hurry_for_snap(secs_in_half_p, dr.score_diff, getattr(dr, '_plan', None), oc, dr.quarter, chasing)
                live_start = dr.clock
                _tick(dr, live_seconds)
                _penalty_ready_clock(dr, penalty_entry, half_end, result=t,
                    hurry=hurry_p, timeout=used_p, live_start=live_start,
                    tempo=(off_state.plan.tempo if off_state is not None and off_state.plan is not None else 0.5))
                dr.clock = float(np.ceil(dr.clock - 1e-9))
                if used_p and used_by_p:
                    dr.log.append(dict(type='timeout', side=used_by_p, side_abbr=(getattr(off_state if used_by_p == pos else def_state, 'abbr', None) or used_by_p.upper()), left=timeouts.left.get(used_by_p, 0), clock=dr.clock))
                if late_injury:
                    _injury_timeout(dr, snap_injuries, out, timeouts, pos, half_end,
                        max(wall, live_start - live_seconds), off_state, def_state, foul=True)
                after_p = (dr.clock - half_end) if half_end is not None else dr.clock
                if secs_in_half_p > 120 >= after_p and not getattr(dr, '_two_min', False):
                    dr._two_min = True
                    dr.log.append(dict(type='two_minute', clock=dr.clock))
                continue
            if taken == 'added':
                penalty_entry = dict(type='penalty', **live_pen)
                dr.log.append(penalty_entry)

        # THE BOOK IS WRITTEN HERE, after the flags and the scramble are settled: a play wiped by a penalty or
        # turned into a scramble was being credited as it first resolved
        _prepare_scoring_play(dr, out)
        _prepare_interception(dr.yardline, out)
        if book is not None: book.record(out, off_f, def_f, rng)
        pending = (out, off_f, def_f, _snap_state)
        # Persist the field's conversion decision for recaps and saved logs.
        # Turnovers/safeties that exit before normal advancement remain false.
        out['converted'] = False

        if book is not None and out.get('fumble'):
            book.record_fumble(out)
        if t == 'interception' or out.get('fumble_lost'):
            if book is not None:
                book.record_defensive_return(out)
            post = penalty_entry if (live_pen is not None and taken == 'added'
                    and E.PEN_INFO[live_pen['penalty']]['phase'] == 'post') else None
            _finish_turnover(dr, out, post)
            dr.clock = max(wall, dr.clock)
            break

        # ---- timeouts ----
        # Look ahead from the completed play before charging its huddle. Keep
        # the live drive unchanged until scoring/down enforcement below.
        after_play = copy.copy(dr)
        _advance(after_play, out.get('yards', 0.0))
        scoring_safety = after_play.result == 'Safety'
        _secs_after = secs_in_half - live_seconds
        after_play.clock = dr.clock - live_seconds
        _plan_to = end_of_half_plan(after_play, offense, defense, rate_fn, timeouts, pos, half_end, _secs_after, coach=(off_state.coach if off_state is not None else None)) if _secs_after > 4 and after_play.result is None and after_play.down <= 4 else None
        added_penalty = live_pen is not None and taken == 'added'
        late_penalty = added_penalty and secs_in_half - live_seconds <= (120.0 if dr.quarter <= 2 else 300.0)
        _fourth_fail = dr.down >= 4 and t in ('run', 'complete', 'scramble', 'sack') and float(np.round(float(out.get('yards', 0.0) or 0.0))) < dr.togo - 0.01 and not (float(np.round(float(out.get('yards', 0.0) or 0.0))) >= dr.yardline - 0.01)
        # The change of possession stops the clock at the whistle. Spending a
        # timeout for the former offense here buys no time.
        used, used_by = (False, None) if late_penalty or late_injury or _fourth_fail or scoring_safety else _timeout_call(dr, t, out, timeouts, pos, half_end, secs_in_half, coach=(off_state.coach if off_state is not None else None), plan=_plan_to, dcoach=(def_state.coach if def_state is not None else None))
        hurry = hurry_for_snap(secs_in_half, dr.score_diff, getattr(dr, '_plan', None), oc, dr.quarter, chasing)
        if half_end is not None and getattr(dr, '_half_stall_intent', None) is not None:
            hurry = dr._half_stall_intent == 'attack'
        before_clock = secs_in_half
        clock_before = dr.clock
        tempo = off_state.plan.tempo if off_state is not None and off_state.plan is not None else 0.5
        elapsed = play_seconds(t, hurry=hurry, timeout=used, tempo=tempo,
                               urgent=multi_score_urgency(secs_in_half, dr.score_diff, dr.quarter, chasing),
                               catchup=comeback_pace(secs_in_half, dr.score_diff, dr.quarter,
                                   yardline=after_play.yardline, timeouts=dr._own_timeouts,
                                   tempo=tempo)) + live_seconds - 6.0
        # A deliberate bleed may wait for a later kick, but it cannot silently
        # consume that kick while holding a timeout. Live action still costs
        # its own live time; no time is restored when the play ends the half.
        if (not used and not late_injury and not added_penalty and not _fourth_fail
                and t in ('run', 'complete', 'scramble', 'sack')
                and after_play.result is None and _plan_to is not None
                and _plan_to['choice'] != 'kneel'
                and secs_in_half - elapsed < 4.0 and _secs_after > 4.0
                and timeouts is not None and timeouts.left.get(pos, 0) > 0):
            used = timeouts.use(pos); used_by = pos
            elapsed = live_seconds
        if late_injury or scoring_safety or (t in ('run', 'complete', 'scramble') and ((out.get('touchdown') and SCORE_STOPS_CLOCK) or float(np.round(float(out.get('yards', 0.0) or 0.0)) if SCORE_STOPS_CLOCK else float(out.get('yards', 0.0) or 0.0)) >= dr.yardline - 0.01)) or _fourth_fail:
            dr.clock -= live_seconds  # scoring/change of possession stops at the whistle
        elif added_penalty:
            _tick(dr, live_seconds)
            _penalty_ready_clock(dr, penalty_entry, half_end, result=t, hurry=hurry,
                timeout=used, live_start=clock_before,
                tempo=(off_state.plan.tempo if off_state is not None and off_state.plan is not None else 0.5))
        else:
            dr.clock -= elapsed
        for edge in (2700.0, 900.0):
            if clock_before > edge >= dr.clock: dr.clock = float(edge)   # the quarter ends with this play; no huddle runs into the next one
        dr.clock = float(np.ceil(dr.clock - 1e-9))                          # the clock is whole seconds; a fraction left is a second
        dr.clock = max(wall, dr.clock)
        if not added_penalty:
            dr.clock_running = t in ('run', 'complete', 'scramble', 'sack') and not used and not out.get('touchdown') and not scoring_safety
            dr.play_clock = 40.0
            dr.runoff_charged = max(0.0, clock_before - dr.clock - live_seconds) if dr.clock_running else 0.0
        after_clock = dr.clock - half_end if half_end is not None else dr.clock
        if used and used_by:
            dr.log.append(dict(type='timeout', side=used_by, side_abbr=(getattr(off_state if used_by == pos else def_state, 'abbr', None) or used_by.upper()), left=timeouts.left.get(used_by, 0), clock=dr.clock))
        if before_clock > 120 >= after_clock and not getattr(dr, '_two_min', False):
            # Stop between plays at 2:00, or after the live play if it crosses
            # 2:00 itself. Never charge the subsequent huddle past the warning.
            if not added_penalty:
                live_end = clock_before - min(live_seconds, clock_before - dr.clock)
                dr.clock = max(dr.clock, min(wall + 120.0, live_end))
            dr._two_min = True
            dr.log.append(dict(type='two_minute', clock=dr.clock))
            dr.clock_running = False
            dr.runoff_charged = 0.0
        before = dr.yardline
        if t == 'sack' and dr.yardline - float(out.get('yards', 0.0) or 0.0) >= 100.0:
            out['yards'] = float(-(100.0 - dr.yardline)); out['safety'] = True
            dr.yardline = 100.0
            dr.result, dr.points = 'Safety', -2
            break
        scored = _advance(dr, out.get('yards', 0.0))
        out['converted'] = dr.result == 'Touchdown' or (dr.result is None and dr.down == 1)
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
        if late_injury:
            _injury_timeout(dr, snap_injuries, out, timeouts, pos, half_end,
                max(wall, clock_before - live_seconds), off_state, def_state, foul=live_pen is not None)

    if dr.result is None: dr.result = 'End of half'

    # ---- the try, once the touchdown is on the board ----
    if try_allowed and dr.result in ('Touchdown', 'Defensive touchdown') and not (dr.result == 'Defensive touchdown' and dr.quarter >= 5):
        defending = dr.result == 'Defensive touchdown'
        try_off, try_def = (defense, offense) if defending else (offense, defense)
        try_os, try_ds = (def_state, off_state) if defending else (off_state, def_state)
        margin = -dr.score_diff if defending else dr.score_diff
        try_penalty = float(getattr(dr, 'try_penalty', 0.0))
        def try_spot(base):
            return base + abs(try_penalty) if try_penalty < 0 else base - min(try_penalty, base / 2.0)
        if two_point_decision(margin + 6, dr.quarter, dr.clock):
            t = attempt_two_point(try_off, try_def, rng, resolve_fn, call_off,
                                  call_def, rate_fn, try_os, try_ds, start_yardline=try_spot(2), book=book)
        else:
            try_orows, try_drows = kick_penalty_units(try_off, try_def, try_os, try_ds, 'extra_point', rate_fn)
            try_kicker = specialist_for(try_off, try_os, 'K', rate_fn)
            t = attempt_extra_point(try_kicker, rng, rate_fn,
                                    snapper=snapper_for(try_off, try_os), distance=try_spot(15) + 18,
                                    offense_players=try_orows, defense_players=try_drows, book=book)
            t['injuries'] = kick_injuries(try_off, try_def, try_os, try_ds, 'extra_point', rng, rate_fn, week)
            if book is not None: book.special('xp', try_kicker.get('pid'), **t)
        dr.points += (-1 if defending else 1) * t['points']
        if defending: t['scoring_side'] = 'defense'
        dr.try_result = t
        if t.get('penalty'):
            dr.log.append(dict(type='penalty', try_type=t['type'], **t['penalty']))
        dr.log.append(t)
    if pending is not None:
        _o, _off, _def, _st = pending
        _v = AS.epa(_o, _st[0], _st[1], _st[2], dr.down, dr.togo, dr.yardline, result=dr.result)
        _o['epa'] = round(_v, 3); AS.book_play(book, _o, _off, _def, _v)
    # the kick or the punt that ended it has an EPA of its own, so the ledger
    # balances: what the offence had on fourth down against what it left
    if dr.result in ('Punt', 'Field goal', 'Missed field goal') and dr.log and isinstance(dr.log[-1], dict):
        last = next((p for p in reversed(dr.log) if p.get('type') in ('punt', 'field_goal')), None)
        if last is not None and not last.get('epa_booked'): AS.book_special(book, dr, last, offense)
    if len(dr.log) > _seen: yield ('snap', dr)
    return dr

OT_LENGTH = 600          # one 10-minute period in the regular season
OT_PLAYOFF_LENGTH = 900  # 15-minute periods, repeated until someone wins

def _terminal_kickoff(dr, kick, before, after, possession, quarter):
    """Keep a return that ends a half even when no offensive drive follows it."""
    boundary = 1800 if quarter == 2 else 0
    if kick.get('touchdown') or kick.get('fumble_lost') or before <= boundary or after > boundary:
        return
    dr.log.append(dict(type='kickoff', touchback=bool(kick.get('touchback')),
                       short_kick=bool(kick.get('short_kick')),
                       new_yardline=kick['new_yardline'], ret=float(kick.get('ret', 0) or 0),
                       carrier=kick.get('returner'), clock=before, end_clock=after,
                       possession=possession, quarter=quarter, ends_period=True,
                       onside=bool(kick.get('onside')), recovered=bool(kick.get('recovered')),
                       free_kick=bool(kick.get('free_kick'))))
    if kick.get('penalty'):
        dr.log.append(dict(type='penalty', possession=possession, clock=after,
                           quarter=quarter, **kick['penalty']))
    LAST_KICKOFF.pop('r', None)


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
    timeouts = Timeouts()
    timeouts.left = dict(home=3 if playoffs else 2, away=3 if playoffs else 2)
    drives = []
    kick = kickoff_for(away if pos == 'home' else home, home if pos == 'home' else away,
                       away_state if pos == 'home' else home_state, home_state if pos == 'home' else away_state, rng, rate_fn, book)
    start = kick['new_yardline']
    clock = kickoff_clock(clock, kick)

    resume_state = None
    while clock > 0 or pending_kick_outcome() or playoffs:
        if clock <= 0 and not pending_kick_outcome():
            clock = OT_PLAYOFF_LENGTH
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
                       call_off, call_def, rate_fn, 0.98, book, o_st, d_st, week,
                       timeouts=timeouts, pos=pos,
                       must_score=had['away' if pos == 'home' else 'home'] and sd < 0,
                       try_allowed=not (had['away' if pos == 'home' else 'home'] and sd + 6 > 0),
                       start_state=resume_state)
        resume_state = None
        drives.append((pos, dr))
        PST.record_defense(d_st, dr)
        clock = max(0.0, dr.clock)
        if dr.result != 'End of half': had[pos] = True
        if dr.result == 'Recovered punt': had['away' if pos == 'home' else 'home'] = True
        other = 'away' if pos == 'home' else 'home'

        if dr.points > 0:
            score[pos] += dr.points
        elif dr.points < 0:
            # a safety by the kicking team on the receiving team's FIRST
            # possession ends it immediately - the one exception to both
            # teams getting the ball
            score[other] += abs(dr.points)
            if dr.result == 'Defensive touchdown':
                return score, drives, 'defensive_touchdown_walkoff'
            if not had[other]:
                return score, drives, 'safety_walkoff'

        # both have possessed: a lead wins, otherwise sudden death
        if had['home'] and had['away']:
            if score['home'] != score['away']:
                return score, drives, 'decided'

        if clock <= 0 and not playoffs:
            break
        if clock <= 0:
            # Continue the same overtime. Preserve the book, possession
            # opportunities and downs instead of recursively starting a new game.
            clock = OT_PLAYOFF_LENGTH
        if dr.result == 'End of half':
            start = dr.yardline
            resume_state = (dr.down, dr.togo)
            continue

        if dr.result in ('Touchdown', 'Field goal'):
            kick = kickoff_for(off, deff, o_st, d_st, rng, rate_fn, book)
            start = kick['new_yardline']
            before = clock
            clock = kickoff_clock(clock, kick)
            _terminal_kickoff(dr, kick, before, clock, other, 5)
        elif dr.result == 'Punt':
            start = getattr(dr, 'next_yardline', 75)
        elif dr.result == 'Missed field goal':
            start = missed_field_goal_start(dr.yardline)
        elif dr.result in ('Turnover', 'Turnover on downs'):
            start = float(np.clip(100 - dr.yardline, 1, 99))
        else:
            start = 75
        if dr.result == 'Recovered punt':
            start = dr.next_yardline
        else:
            pos = other

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
    for state in (home_state, away_state):
        if state is not None: state._fourth_defense = []
    pos = 'away'                                   # away receives first

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
        away_state.road_adjust_delay = ENV.road_adjust_delay
    if home_state is not None:
        home_state.road_noise = 1.0; home_state.road_stamina = 1.0
        home_state.road_adjust_delay = 1.0
    LAST_KICKOFF.clear()
    kick = kickoff_for(home, away, home_state, away_state, rng, rate_fn, book)
    start = kick['new_yardline']
    clock = kickoff_clock(clock, kick)

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
    while clock > 0 or pending_kick_outcome():
        if not half_done and clock <= HALF and not pending_kick_outcome():
            # A kickoff return can itself use the final seconds of the half.
            # There is no empty offensive drive after that return.
            tos.halftime()
            half_done = True
            yield ('halftime', dict(score))
            ENV.turn(rng, home_abbr); _P.ENV = ENV
            pos = 'home'
            kick = kickoff_for(away, home, away_state, home_state, rng, rate_fn, book)
            start = kick['new_yardline']
            clock = kickoff_clock(HALF, kick)
            quarter = 3
            continue
        kick_clock = (LAST_KICKOFF.get('r') or {}).get('clock', clock) if pending_kick_outcome() else clock
        quarter = min(4, int((GAME - kick_clock) // QUARTER) + 1)
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
        PST.record_defense(d_st, dr)
        clock = max(0.0, dr.clock)
        quarter = min(4, int((GAME - clock) // QUARTER) + 1)

        if dr.points > 0:
            score[pos] += dr.points
        elif dr.points < 0:
            score['away' if pos == 'home' else 'home'] += abs(dr.points)
        yield ('drive', pos, dr, dict(score))

        if not half_done and clock <= HALF and not pending_kick_outcome():
            continue                      # the next loop opens the second half

        if clock <= 0:
            continue                      # no kickoff after regulation has expired

        # where the next possession starts
        onside_kept = False
        kick = None
        kick_start = clock
        receiving_pos = 'away' if pos == 'home' else 'home'
        if dr.result in ('Touchdown', 'Field goal'):
            # THE ONSIDE KICK. The scoring side still trails and the clock says it needs the ball back: under
            # two and a half minutes down by one score, or under five down by two. Recovered about 6% of the
            # time under the dynamic kickoff (2024-25); a failed one gives the receiving side the ball near
            # the kicking team's 45.
            my_diff = score[pos] - score['away' if pos == 'home' else 'home']
            need_after = max(0, -my_diff)  # _onside_call expects points, not number of scores
            try_onside = my_diff < 0 and half_done and clock > 0 and _onside_call(clock, need_after, tos.left.get(pos, 0), (o_st.coach if o_st is not None else None), rng)
            if try_onside:
                got = rng.random() < KICKOFF['onside_recovery']
                LAST_KICKOFF['r'] = dict(onside=True, recovered=got, new_yardline=(55.0 if got else 45.0), ret=0.0, returner=None, touchback=False)
                kick = LAST_KICKOFF['r']
                clock = kickoff_clock(clock, LAST_KICKOFF['r'])
                if got: onside_kept = True; start = 55.0                 # the kicking side has it around its own 45
                else: start = 45.0                                       # the receiving side takes over at the kicking team's 45
                if got: receiving_pos = pos
            else:
                kick = kickoff_for(off, deff, o_st, d_st, rng, rate_fn, book)
                start = kick['new_yardline']
                clock = kickoff_clock(clock, kick)
        elif dr.result == 'Defensive touchdown':
            kick = kickoff_for(deff, off, d_st, o_st, rng, rate_fn, book)
            start = kick['new_yardline']
            clock = kickoff_clock(clock, kick)
            receiving_pos = pos
            onside_kept = True          # the team that conceded the return TD receives
        elif dr.result == 'Recovered punt':
            start = dr.next_yardline
            onside_kept = True
        elif dr.result == 'Punt':
            start = getattr(dr, 'next_yardline', 75)
        elif dr.result in ('Turnover', 'Turnover on downs'):
            start = float(np.clip(100 - dr.yardline, 1, 99))
        elif dr.result == 'Missed field goal':
            start = missed_field_goal_start(dr.yardline)
        elif dr.result == 'Safety':
            # the free kick: the side that gave it up punts from its 20 and the scoring side takes over around its own 40
            start = float(np.clip(rng.normal(60.0, 6.0), 45.0, 75.0))
            LAST_KICKOFF['r'] = dict(free_kick=True, new_yardline=start, ret=0.0, returner=None, touchback=False)
            kick = LAST_KICKOFF['r']
            clock = kickoff_clock(clock, LAST_KICKOFF['r'])
        else:
            start = 75
        if kick is not None:
            _terminal_kickoff(dr, kick, kick_start, clock, receiving_pos, 4 if half_done else 2)
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
            if kw.get('touchdown'): d['kr_td'] += 1
        elif kind == 'pr':
            d['pr'] += 1; d['pr_yds'] += float(kw.get('ret', 0.0))
            if kw.get('touchdown'): d['pr_td'] += 1

    def _get(self, pid):
        if pid not in self.p:
            self.p[pid] = dict(
                pass_att=0, pass_cmp=0, pass_yds=0.0, pass_td=0, ints=0, sacked=0,
                rush_att=0, rush_yds=0.0, rush_td=0,
                tgt=0, rec=0, rec_yds=0.0, rec_td=0, drops=0,
                tackles=0, sacks=0.0, int_def=0, pressures=0, ff=0, fumbles=0, fumbles_lost=0,
                int_ret_yds=0.0, int_ret_td=0, fum_rec=0, fum_ret_yds=0.0, fum_ret_td=0, def_td=0,
                pass_def=0,
                fum=0, fum_lost=0,
                # ---- specialists ----
                fg_att=0, fg_made=0, fg_long=0, xp_att=0, xp_made=0,
                punts=0, punt_yds=0.0, punt_net_yds=0.0, punt_in20=0, punt_tb=0,
                kr=0, kr_yds=0.0, kr_td=0, pr=0, pr_yds=0.0, pr_td=0,
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
                pb_solo_snaps=0, pb_solo_wins=0, pb_assisted_snaps=0, pb_assisted_wins=0,
                pb_unengaged_snaps=0,
                pb_eval_snaps=0, pb_expected_wins=0., pb_expected_pressures=0., pb_expected_sacks=0.,
                rb_eval_snaps=0, rb_expected_wins=0.,
                # ---- advanced ----
                pass_epa=0.0, pass_plays=0, rush_epa=0.0, rush_plays=0, rec_epa=0.0, def_epa=0.0, def_plays=0,
                xcomp=0.0, cpoe_att=0, pr_reps=0, pr_wins=0, sep_total=0.0, sep_n=0, st_epa=0.0,
                rb_snaps=0, rb_wins=0)
        return self.p[pid]

    def record_coverage(self, out):
        """Book existing coverage decisions, without changing outcomes or RNG.

        Air yards/TDs/explosives describe the catch point; YAC and total-play
        touchdowns are separate descriptive counters, never coverage blame.
        Uncovered targets remain in play metadata with no individual charge.
        """
        evidence = out.get('coverage_evidence')
        if (not evidence or evidence.get('version') != 1 or out.get('nullified')
                or out.get('throwaway') or out.get('spike')
                or out.get('type') not in ('complete', 'incomplete', 'drop', 'interception', 'sack', 'scramble')):
            return
        seen = set()
        def add(line, key, value=1):
            line[key] = line.get(key, 0) + value
        for pid, role, mode in evidence.get('drops', ()):
            if not pid or pid in seen: continue
            seen.add(pid)
            line = self._get(pid)
            add(line, 'cov_snaps')
            add(line, 'cov_' + (role if role in ('outside', 'slot', 'safety') else 'other') + '_snaps')
            add(line, 'cov_' + (mode if mode in ('man', 'zone') else 'unknown') + '_snaps')
        if not out.get('target') or out.get('type') not in ('complete', 'incomplete', 'drop', 'interception'):
            return
        primary = evidence.get('primary') if not evidence.get('hole') else None
        helper = evidence.get('helper')
        mode, depth = evidence.get('mode'), out.get('depth')
        if mode not in ('man', 'zone') or depth not in ('short', 'medium', 'deep'): return
        if helper in seen and helper != primary:
            line = self._get(helper)
            add(line, 'cov_help_targets')
            add(line, 'cov_help_pd', int(out.get('pass_def') == helper))
            add(line, 'cov_help_ints', int(out.get('type') == 'interception' and out.get('by') == helper))
        if primary not in seen: return
        line = self._get(primary)
        complete = out.get('type') == 'complete'
        air = float(out.get('air') or 0) if complete else 0.0
        receiving_td = complete and bool(out.get('touchdown')) and not out.get('defensive_td')
        values = dict(targets=1, completions=int(complete), air_yards=air,
                      td=int(receiving_td and bool(out.get('coverage_air_td'))),
                      explosive=int(complete and air >= 20),
                      pd=int(out.get('pass_def') == primary),
                      ints=int(out.get('type') == 'interception' and out.get('by') == primary))
        # Emit every field, including zeroes, so missing legacy data cannot
        # masquerade as a complete observed bucket in season evaluation.
        for metric, value in values.items():
            add(line, f'cov_{mode}_{depth}_{metric}', value)
            add(line, 'cov_' + metric, value)
        add(line, 'cov_yac_yards', float(out.get('yac') or 0) if complete else 0.0)
        add(line, 'cov_receiving_td', int(receiving_td))
        add(line, 'cov_receiving_explosive', int(complete and float(out.get('yards') or 0) >= 20))

    def record(self, out, off, deff, rng):
        if out.get('nullified'): return
        self.record_coverage(out)
        t = out.get('type')
        qb = off['qb'].get('pid', 'QB')

        # ---- the line. Every rep, on every snap, both phases ----
        for pid, won in out.get('pb_reps') or ():
            l = self._get(pid)
            l['pb_snaps'] += 1
            l['pb_wins'] += 1 if won else 0
            if not won and out.get('pressured'):
                l['pressures_allowed'] += 1
        # Only new explicit opportunity evidence has a solo/assisted split.
        # Legacy lines retain their existing totals without an inferred split.
        outcomes = dict(out.get('pb_reps') or ())
        seen_opportunities = set()
        for pid, kind in out.get('pb_opportunities') or ():
            if not pid or pid in seen_opportunities:
                continue
            seen_opportunities.add(pid)
            if kind == 'unengaged':
                self._get(pid)['pb_unengaged_snaps'] += 1
            elif kind in ('solo', 'assisted') and pid in outcomes:
                line = self._get(pid)
                line['pb_' + kind + '_snaps'] += 1
                line['pb_' + kind + '_wins'] += int(bool(outcomes[pid]))
        for pid, won in out.get('rb_reps') or ():
            l = self._get(pid)
            l['rb_snaps'] += 1
            l['rb_wins'] += 1 if won else 0
        # Only actual, non-nullified contests carry assignment expectations.
        # Legacy aggregates do not receive fabricated matchup history.
        seen_award = set()
        for pid, wins, pressures, sacks in out.get('pb_award') or ():
            if pid not in outcomes or pid in seen_award:
                continue
            seen_award.add(pid)
            line = self._get(pid)
            line['pb_eval_snaps'] += 1
            line['pb_expected_wins'] += wins
            line['pb_expected_pressures'] += pressures
            line['pb_expected_sacks'] += sacks * out.get('pb_sack_survival', 1.)
        run_outcomes = dict(out.get('rb_reps') or ())
        seen_award = set()
        for pid, wins in out.get('rb_award') or ():
            if pid not in run_outcomes or pid in seen_award:
                continue
            seen_award.add(pid)
            line = self._get(pid)
            line['rb_eval_snaps'] += 1
            line['rb_expected_wins'] += wins
        # Rush wins and pressure are separate evidence. Old recorded plays
        # without arrival evidence retain their original pressure convention.
        for pid, won in out.get('pr_reps') or ():
            if not pid: continue
            l = self._get(pid)
            l['pr_reps'] += 1
            if won:
                l['pr_wins'] += 1
                if 'rush_pressures' not in out: l['pressures'] += 1  # legacy recorded plays
        for pid in set(out.get('rush_pressures', ())):
            if pid: self._get(pid)['pressures'] += 1
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
                if out.get('touchdown') and not out.get('defensive_td'): s['pass_td'] += 1; w['rec_td'] += 1
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
        elif t in ('scramble', 'kneel'):
            s = self._get(qb); s['rush_att'] += 1; s['rush_yds'] += out['yards']
            if out.get('touchdown') and not out.get('defensive_td'): s['rush_td'] += 1
        elif t == 'run':
            rb = out.get('carrier_pid') or (off.get('rb') or off['qb']).get('pid', 'RB1')
            s = self._get(rb); s['rush_att'] += 1; s['rush_yds'] += out['yards']
            if out.get('touchdown') and not out.get('defensive_td'): s['rush_td'] += 1
        # a tackle is credited on any play that ends in the field of play, to the player the play-by-play names
        if t in ('run', 'complete', 'scramble') and (not out.get('touchdown') or out.get('defensive_td')):
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
        forcing = out.get('tackler') or (out.get('by') if out.get('type') == 'sack' else None)
        if forcing and out.get('fumble_forced', True):
            d = self._get(forcing); d['ff'] += 1

    def record_defensive_return(self, out):
        pid = out.get('returner') or out.get('recoverer') or out.get('by')
        if not pid or out.get('nullified'):
            return
        s = self._get(pid)
        kind = 'int' if out.get('type') == 'interception' else 'fum'
        if kind == 'fum': s['fum_rec'] = s.get('fum_rec', 0) + 1
        yards_key, td_key = kind + '_ret_yds', kind + '_ret_td'
        s[yards_key] = s.get(yards_key, 0.0) + float(out.get('ret', 0.0))
        if out.get('defensive_td'):
            s[td_key] = s.get(td_key, 0) + 1
            s['def_td'] = s.get('def_td', 0) + 1

    def table(self):
        import pandas as pd
        return pd.DataFrame(self.p).T

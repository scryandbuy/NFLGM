"""
WIN PROBABILITY, AND THE THREE DECISIONS THAT HANG OFF IT.

Fourth down, the two-point try, and how hard a team throws late are all the
same question asked three ways, and the literature is unanimous that the
question is WIN PROBABILITY rather than points. Romer's 2006 paper used
expected points and had to restrict itself to the first quarter to avoid
end-of-game distortion. Everything since - Yam and Lopez, Baldwin's nfl4th,
ESPN's model - moved to win probability, because score and clock change what
a point is worth. A field goal down fourteen with two minutes left is worth
almost nothing, and expected points cannot see that.

THE MODEL. Logistic, fitted on 83,408 plays from 570 real games, validated by
holding out WHOLE GAMES rather than plays - otherwise it trains on the fourth
quarter of a game it already saw the first quarter of. 75.1% accuracy, Brier
0.160, and calibrated within two points at every decile from 0-10% up to
90-100%.

The one transform that matters: a lead is worth more as the clock runs out,
and the relationship is score over the SQUARE ROOT of time, not score alone.
A touchdown lead in the first quarter and the same lead with a minute left are
different facts.

WHAT THE RESEARCH SAYS, AND WHAT IT MEANS HERE:

  COACHES ARE SYSTEMATICALLY TOO CONSERVATIVE, and it is measured rather than
  asserted. Yam and Lopez matched thirteen seasons of fourth downs and found
  teams would have gained about 0.4 wins a year by going more often. Baldwin
  found coaches go for it in the fourth quarter HALF as often as they should,
  and less than that earlier.

  THAT GAP IS THE COACH DIAL. The engine computes the optimal call and then
  applies a coach-specific fraction of the edge. League average sits well
  below 1.0. A conservative coach still goes on a strong recommendation
  because a big enough edge overwhelms any discount - which is exactly the
  behaviour asked for: a tendency that the situation can override.

  NOT EVERY DECISION IS CLOSE. Wharton put a 90% confidence interval of -5% to
  +8% on one fourth-and-4: genuinely inconclusive. So a recommendation carries
  a STRENGTH, and a coach deviating on a coin flip is not making an error.

  TRAILING TEAMS AND UNDERDOGS SHOULD BE MORE AGGRESSIVE. nfl4th generates
  different charts by point spread. This is not desperation, it is correct: a
  worse team needs variance. It falls out of the win probability arithmetic
  without a special rule.

  A COACH WHO JUST GOT STUFFED GETS GUN-SHY. Roach and Owens, 2024: prior
  fourth-down outcomes within the same game change later behaviour. One state
  variable, and it makes coaches feel like people.

  THE TWO-POINT TRY IS NOT A GAMBLE. One point at a 95.7% kick rate is 0.957;
  two at a 47.5% conversion rate is 0.950. They are nearly identical, so it is
  an active choice every time rather than a default with an exception.

  TAKE THE TRY YOU WILL NEED ANYWAY AS EARLY AS POSSIBLE. The best idea in the
  whole literature and it appears on no chart: the value is INFORMATION.
  Knowing the result lets a coach set the rest of his strategy with certainty
  instead of guessing about onside kicks and field goals later.

NOT MODELLED: timeouts. Every published model uses them and the engine does
not track them, so both sides are assumed to hold all three. The feature is in
the model and fed a constant; wiring real timeouts in later needs no refit.
"""
import json
import os

import numpy as np

_D = os.path.dirname(os.path.abspath(__file__))
_M = json.load(open(os.path.join(_D, 'wp_model.json')))
COEF = np.array(_M['coef'])
INTERCEPT = float(_M['intercept'])

# Real conversion rates when clubs actually went for it, 2023-24.
FOURTH_CONV = {1: 0.71, 2: 0.58, 3: 0.53, 4: 0.53, 5: 0.42, 6: 0.42,
               7: 0.42, 8: 0.22}
PUNT_NET = 40.0          # average net; the engine's own punt model is finer
XP_RATE = 0.957          # measured, 2023-24
TWO_RATE = 0.475         # measured; the engine resolves the real play

# How much of the computed edge a coach actually acts on. The league is not at
# 1.0 and has never been - that is the whole finding. 0.55 reproduces the
# observed go rate; an analytics-forward staff runs near 0.9.
DEFAULT_AGGRESSION = 0.52

# A recommendation worth acting on regardless of temperament. Below this the
# decision is genuinely close and a coach's preference is not an error.
STRONG_EDGE = 0.030      # 3 percentage points of win probability

# The kick is the default. Expected points put the two options within 0.007 of
# each other, so without a bar the model goes for two on noise - and real
# clubs kick about nine times in ten.
TWO_POINT_BAR = 0.006


def win_prob(score_diff, seconds_left, yardline_100, down=1, ydstogo=10,
             timeout_edge=0, is_home=1):
    """
    Probability the team WITH THE BALL wins, from this state.

    yardline_100 is distance to the opponent's goal, matching the engine.
    """
    s = float(np.clip(seconds_left, 1, 3600))
    sd = float(score_diff)
    spm = sd / np.sqrt(s / 60.0 + 1.0)
    x = np.array([
        sd, spm, sd / (s + 1) * 100, np.log(s),
        (float(yardline_100) - 50) / 50, float(down),
        float(np.clip(ydstogo, 1, 30)) / 10.0,
        float(down == 4 and ydstogo <= 2),
        float(timeout_edge), float(timeout_edge) / np.sqrt(s / 60.0 + 1.0),
        float(is_home),
    ])
    return float(1.0 / (1.0 + np.exp(-(x @ COEF + INTERCEPT))))


def _flip(score_diff, seconds_left, yardline_100, is_home=1, **kw):
    """
    Win probability for THIS team when the OTHER side has the ball at that
    spot. The opponent's yardline is the mirror of ours - and so is home
    field. Passing is_home straight through made BOTH teams the home side,
    which quietly deflated every punt and every turnover on downs, and the
    model recommended going for it on fourth and seven from its own fifteen.
    """
    return 1.0 - win_prob(-score_diff, seconds_left, 100 - yardline_100,
                          is_home=1 - is_home, **kw)


# ============================================================ FOURTH DOWN
def fourth_down(score_diff, seconds_left, yardline_100, ydstogo,
                fg_prob=None, conv_prob=None, aggression=DEFAULT_AGGRESSION,
                recent_failure=0.0, is_home=1):
    """
    Returns the call, the win probability edge of going, and how strong the
    recommendation is.

    `go_boost` is Baldwin's number: win probability gained by going for it
    relative to the NEXT BEST alternative, not relative to both. Positive
    means go.
    """
    ytg = int(np.clip(ydstogo, 1, 30))
    p_conv = conv_prob if conv_prob is not None else FOURTH_CONV.get(
        min(ytg, 8), 0.22)

    # ---- go for it ----
    wp_conv = win_prob(score_diff, seconds_left - 6, max(1, yardline_100 - ytg),
                       1, min(10, max(1, yardline_100 - ytg)), is_home=is_home)
    wp_fail = _flip(score_diff, seconds_left - 6, yardline_100, is_home=is_home)
    wp_go = p_conv * wp_conv + (1 - p_conv) * wp_fail

    # ---- field goal ----
    dist = yardline_100 + 17
    if fg_prob is None:
        fg_prob = float(np.clip(1.02 - 0.0095 * max(0, dist - 20), 0.02, 0.985))
    wp_made = _flip(score_diff + 3, seconds_left - 6, 25, is_home=is_home)
    wp_miss = _flip(score_diff, seconds_left - 6, max(1, yardline_100 - 8),
                    is_home=is_home)
    wp_fg = fg_prob * wp_made + (1 - fg_prob) * wp_miss
    if dist > 65:
        wp_fg = -1.0                      # not a real option

    # ---- punt ----
    landed = max(1, min(99, 100 - (yardline_100 - PUNT_NET)))
    wp_punt = _flip(score_diff, seconds_left - 6, 100 - landed, is_home=is_home)
    if yardline_100 <= 35:
        wp_punt -= 0.004                  # punting from field goal range costs

    alt = max(wp_fg, wp_punt)
    go_boost = wp_go - alt
    strength = abs(go_boost)

    # AGGRESSION IS A THRESHOLD, NOT A MULTIPLIER. Scaling the edge by a
    # positive number can never change its sign, so the dial did nothing at
    # all - conservative and analytics-forward staffs produced identical
    # calls. A cautious coach instead demands a BIGGER edge before he will
    # go, which is what being conservative actually means, and a big enough
    # recommendation still overrides any temperament.
    # Calibrated so the DEFAULT setting reproduces the real league go rate of
    # 20.1%. The scale is anchored to behaviour, not to taste.
    bar = (1.0 - np.clip(aggression, 0.05, 1.0)) * 0.042
    bar += 0.02 * recent_failure          # just got stuffed: wants more proof
    # WIN PROBABILITY COMPRESSES AT THE EXTREMES, and a fixed bar reads that
    # as indifference. Down sixteen in the fourth, punting is a near-certain
    # loss and going is only slightly less certain - the ABSOLUTE edge is a
    # single point even though the choice is obvious. Left uncorrected the
    # model went for it 15% of the time trailing by nine or more late, where
    # real clubs go 87%. So the bar shrinks with the room available: a point
    # of win probability is worth far more when you only have three.
    room = max(wp_go, alt)
    bar *= max(0.10, 4.0 * room * (1.0 - room))
    call = 'go' if go_boost > bar else ('field_goal' if wp_fg >= wp_punt else 'punt')

    return dict(call=call, go_boost=round(go_boost, 4),
                optimal='go' if go_boost > 0 else
                        ('field_goal' if wp_fg >= wp_punt else 'punt'),
                strong=strength >= STRONG_EDGE,
                wp_go=round(wp_go, 4), wp_fg=round(wp_fg, 4),
                wp_punt=round(wp_punt, 4))


# ============================================================ THE TRY
def two_point(score_diff_after_td, seconds_left, conv_prob=TWO_RATE,
              xp_prob=XP_RATE, aggression=DEFAULT_AGGRESSION, is_home=1):
    """
    Kick or go, decided on win probability rather than points.

    score_diff_after_td counts the six just scored. The try is resolved from
    the KICKOFF that follows, because that is the state each option leads to.

    conv_prob is the CLUB'S OWN rate, not the league's. A team with a power
    running game or an elite goal-line quarterback clears the break-even bar
    where a poor offence does not, and the engine resolves the try with real
    players so this number can be real.
    """
    def after(points):
        return _flip(score_diff_after_td + points, max(1, seconds_left), 25,
                     is_home=is_home)

    wp_kick = xp_prob * after(1) + (1 - xp_prob) * after(0)
    wp_go = conv_prob * after(2) + (1 - conv_prob) * after(0)
    edge = wp_go - wp_kick

    # INFORMATION VALUE, and it only exists LATE. The argument is that when a
    # try will be needed anyway, taking it now sets the rest of the plan with
    # certainty. That is only knowable once the number of remaining
    # possessions is small - down five in the second quarter you do not yet
    # know you will need it, and applying the bonus there had the model going
    # for two in every trailing situation in the game.
    if seconds_left < 1500 and score_diff_after_td in (
            -8, -14, -15, -2, -5, -10, -16, -18):
        edge += 0.012 * (1.0 + (seconds_left < 600))
    # variance is an underdog's friend: it raises the tail without lowering
    # expected points, which is the whole argument for going when behind
    if score_diff_after_td < 0 and seconds_left < 900:
        edge += 0.004 * min(4, abs(score_diff_after_td) / 4.0)

    # The two options are worth 0.957 and 0.950 points, so the raw edge is
    # near zero almost everywhere and ANY nudge would tip it. Real clubs kick
    # roughly nine times in ten, so a kick is the default and going needs a
    # real reason rather than a rounding error.
    acted = edge * np.clip(aggression + 0.25, 0.1, 1.3)
    return dict(call='two' if acted > TWO_POINT_BAR else 'kick',
                edge=round(edge, 4),
                optimal='two' if edge > 0 else 'kick',
                strong=abs(edge) >= STRONG_EDGE,
                break_even=round(xp_prob / 2.0, 4))


# ============================================================ LATE-GAME TEMPO
# Real pass rate by score and clock, 2023-24. It is almost entirely a SECOND
# HALF effect: the first two quarters sit in a 55-69% band whatever the score,
# and it goes nearly binary in the last four minutes - 90% throwing down 9-16,
# 13% running out the clock up 9-16.
PASS_RATE = {
    #  (score band)      Q1-Q2   Q3    Q4early  last4
    (-99, -17): (0.69, 0.63, 0.77, 0.67),
    (-16, -9):  (0.61, 0.57, 0.75, 0.90),
    (-8, -4):   (0.59, 0.53, 0.59, 0.81),
    (-3, -1):   (0.58, 0.54, 0.56, 0.74),
    (0, 0):     (0.55, 0.55, 0.56, 0.64),
    (1, 3):     (0.58, 0.52, 0.50, 0.29),
    (4, 8):     (0.59, 0.56, 0.50, 0.26),
    (9, 16):    (0.60, 0.51, 0.40, 0.13),
    (17, 99):   (0.59, 0.49, 0.31, 0.14),
}


def pass_rate(score_diff, seconds_left, quarter=None):
    """What share of snaps a real team throws in this state."""
    s = float(seconds_left)
    col = 3 if s <= 240 else (2 if s <= 900 else (1 if s <= 1800 else 0))
    sd = int(round(score_diff))
    for (lo, hi), row in PASS_RATE.items():
        if lo <= sd <= hi:
            return row[col]
    return 0.575


if __name__ == '__main__':
    print('=== FOURTH DOWN: does it reproduce the real go rates? ===')
    print('%-28s %7s %8s %s' % ('situation', 'boost', 'optimal', 'coach'))
    cases = [
        ('4th & 1, opp 35, Q2, tied', 0, 1800, 35, 1),
        ('4th & 1, own 30, Q2, tied', 0, 1800, 70, 1),
        ('4th & 2, opp 40, Q3, -3', -3, 1200, 40, 2),
        ('4th & 4, opp 33, Q2, tied', 0, 1700, 33, 4),
        ('4th & 8, opp 30, Q2, tied', 0, 1700, 30, 8),
        ('4th & 3, own 25, Q1, tied', 0, 3300, 75, 3),
        ('4th & 2, opp 45, Q4 -7', -7, 400, 45, 2),
        ('4th & 5, opp 20, Q4 -2', -2, 200, 20, 5),
        ('4th & 1, opp 5, Q4 -4', -4, 300, 5, 1),
    ]
    for lab, sd, s, y, tg in cases:
        r = fourth_down(sd, s, y, tg)
        print('%-28s %+7.3f %8s %s%s' % (lab, r['go_boost'], r['optimal'],
                                         r['call'],
                                         '  STRONG' if r['strong'] else ''))
    print('\n=== THE TRY ===')
    print('%-24s %7s %8s  %s' % ('score after the TD', 'edge', 'optimal', 'coach'))
    for sd, lab in [(-8, 'down 8'), (-2, 'down 2'), (-5, 'down 5'),
                    (-14, 'down 14'), (1, 'up 1'), (4, 'up 4'),
                    (0, 'tied'), (7, 'up 7'), (-1, 'down 1')]:
        for s, when in ((2400, 'Q2'), (500, 'Q4')):
            r = two_point(sd, s)
            print('%-16s %-7s %+7.3f %8s  %s%s'
                  % (lab, when, r['edge'], r['optimal'], r['call'],
                     '  STRONG' if r['strong'] else ''))
    print('\n=== LATE-GAME PASS RATE ===')
    for sd in (-14, -6, 0, 6, 14):
        print('  %+3d:  Q1 %.0f%%  Q3 %.0f%%  Q4 %.0f%%  last4 %.0f%%'
              % (sd, 100 * pass_rate(sd, 3000), 100 * pass_rate(sd, 1200),
                 100 * pass_rate(sd, 600), 100 * pass_rate(sd, 120)))

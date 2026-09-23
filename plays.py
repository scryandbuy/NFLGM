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

# Diagnostic trace. When a list is bound here, every pass attempt appends the
# quantities the completion roll was built from, so the depth scalars can be
# SOLVED against what the engine actually produces inside games rather than
# tuned by hand. None in normal play; costs nothing.
PASS_TRACE = None

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
# Re-solved on REAL rosters. Actual NFL linemen hold up far better than the
# flat-70 clones this was first fitted against: at 3.50 they produced a 2.99s
# league mean instead of 2.72, and the exponential sack curve collapses at 3s,
# pinning sacks at 3.5% against a real 6.6%.
# Re-solved INSIDE GAMES (refit_clock.py). 3.16 was the bare four-man answer;
# with the blitz multiplier, simulated-pressure protection error and hot routes
# all taking time off the clock, attempts were leaving the hand at 2.55s.
RUSHER_BASE = 3.36
BASE_TTT = 2.72          # the league mean the clock must land on
# how much longer than the average dropback the ball is held, by the route's depth
HOLD_BY_DEPTH = {'screen': -0.55, 'short': -0.22, 'medium': 0.08, 'deep': 0.40}   # deep sacks ran 24% against a real ~10 at 0.50
SACK_K = 22.6            # solved with the hold so the blend lands on the real 6.6%
# ESPN's pass block win rate is whether a lineman sustains his block for 2.5
# seconds or longer. Arbitrary on its face, but it is the industry definition
# and the one every published number is measured against, so it is used here
# rather than a threshold of our own.
PBW_THRESHOLD = 2.5
RBW_THRESHOLD = -0.035   # solved to the real 71% run-block win rate

# Share of incompletions a defender gets credit for breaking up. Solved to the
# real 37.5% overall: a contested throw is usually somebody's doing, a clean
# miss usually nobody's.
LAST_TRAVEL = False
import weather as _W
ENV = _W.CLEAR        # the game's conditions, set at kickoff by game.play_game
PD_CONTESTED = 0.44   # 4.9 a team-game against a real 2.9 at 0.72/0.22
PD_LOOSE = 0.13

# Share of SHORT throws that are really behind the line of scrimmage. The real
# split says 18.4/(18.4+49.5) of the short bucket, but this engine's depth mix
# is not the real one - solved instead against the OUTCOME, the 22.3% of
# completions that travel backwards.
SCREEN_SHARE = 0.285
# Behind-the-line throws complete 78.4% against 71.0% for a short throw, and
# the difference is that nobody is covering the flat the way they cover a
# route downfield. It has to stay small: at 0.14 with a 36% share, league
# completion went to 69.0% against a real 65.0% and mean air yards fell to
# 4.22 against 5.72 - the screen game was swallowing the passing game.
SCREEN_RESCUE = 0.07
# A second blocker buys the pocket roughly this much more time. Used only to
# decide who is CHARGED with a rep, never to change the play.
DOUBLE_TEAM_HELP = 1.45

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

    # EVERY rep, not just the one that ended the play. The resolver already
    # races each rusher against his own blocker and then discards all but the
    # fastest, so the per-man result was being computed and thrown away.
    # A pass block win is ESPN's definition: the blocker sustains for 2.5
    # seconds or longer.
    # EVERY BLOCKER ON THE FIELD HAS A REP, not just the ones a rusher was
    # assigned to. The loop above pairs rusher i with blocker i, so against a
    # four-man rush only linemen 0-3 were ever recorded - and the line is
    # ordered LT, LG, C, RG, RT, which meant the RIGHT TACKLE never got a
    # pass-block rep in his life. Lane Johnson finished a 17-game season with
    # 1,076 snaps and 67 recorded reps; 205 of 365 linemen had none at all.
    #
    # A lineman nobody rushed still blocked: he wins by default, because
    # nobody beat him. That is what five blockers against four rushers means.
    #
    # A surplus blocker DOUBLES rather than standing free. Crediting him with
    # an automatic win put the right tackle at a 98.4% win rate against a real
    # best-in-league 95.6%, because he was handed a free rep on every four-man
    # rush. He now shares the rep of the man being doubled: they both win it or
    # they both lose it, which is what a double team actually is.
    engaged = {id(b) for _t, _m, _r, b in wins if b}
    reps = [(b.get('pid'), t >= PBW_THRESHOLD) for t, _m, _r, b in wins if b]
    spare = [b for b in blockers if id(b) not in engaged]
    if spare and wins:
        # He helps on the man getting there quickest, and a DOUBLED rusher is
        # beaten less often - so the pair are credited against a longer clock,
        # not against the raw loss. Tying him to the unaided result was as
        # wrong in the other direction: it put the right tackle at 53.9%.
        #
        # CREDIT ONLY. The double does not feed back into t_arrive, because
        # that would move a sack rate calibrated to a real 6.6%. It changes
        # who gets charged for the rep, not what happened on the play.
        worst = min(wins, key=lambda x: x[0])
        held = worst[0] * DOUBLE_TEAM_HELP >= PBW_THRESHOLD
        reps += [(b.get('pid'), held) for b in spare]

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
    # Re-solved on REAL rosters. Every earlier value was fitted against
    # synthetic clones whose linemen were worse than the league's, so the same
    # constant produced 3.85% sacks against a real 6.6% once real protection
    # was in front of the quarterback.
    p_sack = 25.0 * np.exp(-2.40 * t_arrive)
    if qb is not None:
        p_sack *= 1.0 - 0.45 * (rate(qb, {'break_sack_rating': 1.0}) - AVG)
    sack = rng.random() < float(np.clip(p_sack, 0.0, 0.85))
    return dict(time=round(float(t_arrive), 2), pressure=round(pressure, 3),
                sack=bool(sack), beaten_by=winner.get('pid'),
                beaten=loser.get('pid') if loser else None, move=move,
                pb_reps=reps)

# ============================================================ MAN COVERAGE
# The defender watches the RECEIVER, head often turned from the ball. The
# contest is separation, and separation is what the throw is aimed into.
MAN_SLOPE = 0.80

def resolve_man(receiver, defender, depth, time_available, rng):
    """Returns separation 0-1. Higher = more open."""
    rel = edge(rate(receiver, ROUTE['receiver']['release']),
               rate(defender, ROUTE['defender_man']['press']))
    rt = edge(rate(receiver, ROUTE['receiver'][depth]),
              rate(defender, ROUTE['defender_man'][depth]))
    # a release win compounds the longer the route runs
    w = {'short': 0.55, 'medium': 0.40, 'deep': 0.28}[depth]
    # slope cut from 1.30 (see matchups.ZONE_SLOPE): the man edge between a
    # club's corners and the opponent's receivers was worth sd 0.038 of
    # separation across defences, three times what the real completion
    # spread allows
    sep = 0.42 + MAN_SLOPE * (w * rel + (1 - w) * rt)
    # more time on the route means more chance to work open
    sep *= 1.0 + 0.10 * (time_available - BASE_TTT) / BASE_TTT
    return float(np.clip(sep + rng.normal(0, 0.11), 0.02, 0.98))

# ============================================================ THE THROW
def resolve_throw(qb, depth, separation, pressure, rng, on_run=False,
                  play_action=False, outcome_mult=1.0):
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
    # These were solved so an average QB at league-average separation hits the
    # real per-depth completion rates - but they sit BEFORE drops, the concept
    # modifier and pressure, all of which come off the top. Calibrating them to
    # the FINAL number meant the chain ended ~11 points low and man coverage
    # ran 62.8% at short depth against a real 74.4%.
    # Completion ran 67.6% against a real 65.0%, and that surplus does more
    # than move one row: an extra completion is an extra 5-6 yards, so drives
    # covered the field faster and needed fewer plays. Yards per play sat at
    # 5.93/5.63/5.94 by down against a real 5.60/5.38/5.37, plays per drive at
    # 5.32 against 5.96, and first downs at 1.56 against 1.84. Pulling the
    # multiplier down lengthens drives as well as fixing completion.
    # RE-SOLVED INSIDE GAMES against the defence as it now calls coverage
    # (refit_passing.py, 96 games, seed 2026). The old values were fitted when
    # man meant cover 0 or cover 1 on a fifth of snaps; with the full call
    # book man is a third of targets and was completing 66% against a real
    # ~60, ABOVE zone, which is backwards.
    DEPTH_MULT = {'short': 1.50, 'medium': 1.13, 'deep': 0.82}   # re-solved with the starters staying in to block
    import matchups as M
    base = separation * (1.0 + M.ZONE_SLOPE['acc'] * (acc - AVG)) * outcome_mult
    p = float(np.clip(base * DEPTH_MULT[depth] * (ENV.deep_mult if depth == 'deep' else (1.0 - 0.3 * (1.0 - ENV.deep_mult)) if depth == 'medium' else 1.0), 0.02, 0.97))

    roll = rng.random()
    if roll < p:
        return dict(result='complete', contested=separation < 0.35, p=p, base=base)
    # a bad throw into tight coverage is where picks come from
    # calibrated to the real 2.1% league interception rate
    # Picks are modelled on the ball that did NOT complete, so the rate per
    # attempt moves with completion. Re-anchored after the completion refit
    # (66% completion left the league at 1.82% against a real 2.10).
    p_int = (1.0 - separation) * 0.129 * (1.0 + 2.2 * (AVG - acc))
    if rng.random() < max(0.0, p_int):
        return dict(result='interception', contested=True, p=p, base=base)
    return dict(result='incomplete', contested=separation < 0.45, p=p, base=base)

# ============================================================ THE CATCH
def resolve_catch(receiver, defender, contested, rng):
    if not contested:
        # Real drop rates run roughly 2% for the best hands to 8% for the worst.
        # The first build spread them only 95.0 to 96.9 - hands did not matter.
        p = 0.952 + 0.55 * (rate(receiver, CATCH['clean']) - AVG)
    else:
        e = edge(rate(receiver, CATCH['contested']), rate(defender, CATCH['defender']))
        p = 0.50 + 1.10 * e
    # rain and snow: the drop rate runs 1.4x and 1.7x
    p = 1.0 - (1.0 - p) * ENV.drop_mult
    return rng.random() < float(np.clip(p, 0.05, 0.995))

# ============================================================ YARDS AFTER
# Shared by yards after catch and by a run that clears the line. Nothing caps
# the yardage: he runs until someone catches him, and the FIELD is the limit.
def _compression(room):
    """
    How much of the open field is actually there.

    A binary switch was too sharp - cutting yards after the catch off at
    eighteen yards took scoring from the 16-20 down to 3.5% of plays against a
    real 7.1%. The real squeeze is gradual and it is steep only close in: real
    yards after catch run 5.64 beyond the opponent 41, 5.05 from 21-40, 4.41
    from 11-20, 2.68 from 6-10 and 0.94 inside the 5. The end zone is a wall
    and there is simply less grass to find.
    """
    # It must stay GENTLE, because the total is already capped at the distance
    # to the goal - the wall is modelled twice otherwise. A hard squeeze took
    # scoring from the two down to 16.1% of plays against a real 51.6%: the
    # cap said "you cannot gain more than two yards" and this said "and only
    # 18% of that", which is nobody scoring from anywhere.
    # Trimmed from 0.45 + room/36 to 0.34 + room/40. Yards after catch ran
    # 6.12 against a real 5.19, and that surplus is what keeps drives short:
    # a drive that gains the same yards in fewer plays ends sooner, which is
    # why plays per drive sat at 5.20 against 5.96 and drives per game at
    # 23.85 against 21.73. Those three rows are one number.
    return float(min(1.0, max(0.42, 0.34 + room / 40.0)))


def resolve_yards_after(carrier, tacklers, yards_to_endzone, rng,
                        already=0.0, contact_at=0.0, in_space=False):
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
        # A receiver catching the ball in space is not a back hitting a pile:
        # he has room to make the first man miss. Using the run chain's
        # difficulty for both left YAC at 2.96 against a real 5.19.
        # Raised from 0.145/0.105 in space to put yards after catch on its
        # real 5.19.
        #
        # I expected this to fix drives per game too, on the theory that a
        # drive gaining the same ground in fewer plays ends sooner. It does
        # not: cutting yards after catch by a FULL 1.4 yards moved plays per
        # drive by 0.08. Drive length is not set by how far a play goes, and
        # that is worth knowing before anyone tunes yardage to chase it again.
        # Re-set for runs once defences stopped carrying box adjustments
        # from game to game: with the ratchet gone, explosive runs ran 3.6%
        # against 2.46 and ypc 4.9 against 4.52, all of it after contact
        base = 0.165 if not in_space else 0.166
        ramp = 0.115 if not in_space else 0.113
        p_break = logistic(edge(atk, wrap) - base - ramp * i, k=7.0)
        if rng.random() > p_break:
            gained += max(0.0, rng.normal(0.9, 0.8))          # brought down
            break
        broken += 1
        chase = logistic(edge(brk, rate(t, YAC['tackler']['angle'])), k=5.5)
        gained += max(0.3, rng.gamma(1.7, (1.4 if not in_space else 1.6)
                                      + (4.4 if not in_space else 4.6) * chase))
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

RUN_BASE = 1.90
# sd of yards before contact around the blocking result; with RUN_BASE
# re-anchored lower, 1.42 put 11.7% of carries in the backfield against 8.5
RUN_NOISE = 1.33

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
    # Slopes cut from 9.0 and 3.2: yards per carry ALLOWED varied across
    # clubs with sd 0.66 against a real 0.35, most of which is sampling noise
    # on 430 carries, so the true real spread is small. RUN_BASE is re-anchored
    # so the league lands on 4.52.
    ybc = RUN_BASE + 5.5 * push - 2.0 * (fill - AVG) + rng.normal(0, RUN_NOISE)
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

# ============================================================ FULL PLAY
# Wires the scheme layer into the matchup resolution. A play is now a personnel
# group and a concept against a front, a box and a coverage.
import schemes as S
from matchups import resolve_zone

def resolve_play(off, deff, off_call, def_call, yards_to_endzone, rng):
    """
    off/deff: dicts of position -> player dict (or list for OL/DL/WR)
    Returns the play outcome with every contributor named.
    """
    if off_call['is_pass']:
        out = _pass_play(off, deff, off_call, def_call, yards_to_endzone, rng)
        if isinstance(out, dict): out['travelled'] = LAST_TRAVEL
        return out
    return _run_play(off, deff, off_call, def_call, yards_to_endzone, rng)

# Red-zone compression is an OUTCOME, not an input. An earlier build multiplied
# yardage by 0.52 inside the 5 to pull touchdowns down from 28.5% of drives to
# the real 22.6% - a fudge factor, and exactly the thing the whole
# resolve-don't-sample approach exists to avoid. It also suppressed the scoring
# play itself, which is why QB touchdowns came out at 12 against a real 43.
#
# What REALLY happens near the goal line, from the data:
#   - air yards collapse because the field runs out: mean 8.09 between the 21
#     and 50, 4.47 from the 6-10, 2.18 inside the 5. Inside the 10 the maximum
#     air yards ever recorded is 10 and ZERO throws travel more than 20.
#   - the box gets heavier: 6.55 defenders inside the 5 against 4.40 at 21-50
#   - rushers increase: 4.68 inside the 5 against 4.30
#   - completion falls out of all that: 42% inside the 5 against 61% at 21-50
# So the compression is produced, not imposed.

def available_depths(ytg):
    """
    You cannot throw a 22-yard route from the 8. The field decides.
    But from the 15-20 a shot to the back of the end zone IS available, and
    barring it made scoring from there nearly impossible: 1.6% per play from
    the 20 against a real 6.96%.
    """
    if ytg <= 6:  return ['short']
    if ytg <= 12: return ['short', 'medium']
    if ytg <= 25: return ['short', 'medium', 'deep']
    return ['short', 'medium', 'deep']

def _run_play(off, deff, off_call, def_call, ytg, rng):
    scheme = off_call.get('scheme', 'inside_zone')
    fam = S.RUN_SCHEMES[scheme]['family']
    # Zone rewards agility and finesse blocking; gap rewards power and leverage.
    # Taking the max of both erased the whole distinction between them.
    key = 'finesse' if fam == 'zone' else 'power'
    blockers = off['ol'][:5]
    front = deff['dl'][:S.FRONTS[def_call['front']]['dl']]
    defenders = front + deff['lb'] + deff['db']

    wins = [edge(rate(b, RUN_BLOCK['blocker'][key]),
                 rate(d, RUN_BLOCK['defender']['shed']))
            for b, d in zip(blockers, front)]
    push = float(np.mean(wins)) if wins else 0.0
    # Same as protection: the per-blocker result already exists and was only
    # ever averaged away. A run block win is beating the man across from you,
    # which is a positive edge.
    # Same fault in the run game: zip() stops at the shorter list, so against a
    # four-man front the fifth lineman was never recorded either. An unblocked
    # man is still blocking somebody - he wins his rep.
    # A win is beating your man, and the line wins about 71% of them (ESPN
    # RBWR): the deterministic edge is the mean, and the rep itself is a
    # draw around it, so a slightly out-rated blocker still wins his share
    rb_reps = [(b.get('pid'), (w + rng.normal(0.0, 0.10)) > RBW_THRESHOLD) for b, w in zip(blockers, wins)]
    # Same in the run game: a surplus blocker is doubling or pulling, not
    # standing free, so he shares the result of the block that mattered most
    # rather than banking an automatic win.
    if len(blockers) > len(wins) and wins:
        # An extra man at the point of attack usually means that block holds.
        shared = max(wins) > -0.04
        rb_reps += [(b.get('pid'), shared) for b in blockers[len(wins):]]
    fill = np.mean([rate(d, RUN_BLOCK['defender']['fill']) for d in defenders[:7]])

    # Slopes cut from 9.0 and 3.2: yards per carry ALLOWED varied across
    # clubs with sd 0.66 against a real 0.35, most of which is sampling noise
    # on 430 carries, so the true real spread is small. RUN_BASE is re-anchored
    # so the league lands on 4.52.
    ybc = RUN_BASE + 5.5 * push - 2.0 * (fill - AVG) + rng.normal(0, RUN_NOISE)
    ybc *= S.box_run_multiplier(def_call['box'])
    ybc *= S.run_scheme_multiplier(scheme, def_call['front'], ytg, def_call['box'])
    ybc *= S.FRONTS[def_call['front']]['run_fit'] ** -1
    if off_call.get('motion'): ybc *= 1.04
    ybc = max(-4.0, ybc)

    if ybc < 0:
        return dict(type='run', yards=round(float(ybc), 1), scheme=scheme,
                    broken_tackles=0, touchdown=False, ybc=round(float(ybc), 1),
                    rb_reps=rb_reps)

    chasers = defenders[len(front):] + defenders[:len(front)]
    # The same wall applies to a run: yards after contact collapse near the
    # goal because there is nowhere to break to.
    out = resolve_yards_after(off['rb'], chasers, ytg, rng, contact_at=ybc)
    if not out['touchdown']:
        # never turn a score into a non-score: the resolver already decided he
        # reached the end zone, and compression is about the grass in between
        after = max(0.0, out['yards'] - ybc)
        out['yards'] = round(ybc + after * _compression(ytg), 1)
    out.update(type='run', scheme=scheme, ybc=round(float(ybc), 1),
               rb_reps=rb_reps)
    return out

def _pass_play(off, deff, off_call, def_call, ytg, rng):
    depth = off_call.get('depth', 'short')
    ok = available_depths(ytg)
    if depth not in ok: depth = ok[-1]
    # THE SCREEN GAME, which did not exist at all. Real clubs throw 18.4% of
    # their attempts BEHIND the line of scrimmage - screens, swings, flares,
    # checkdowns to the flat - and those throws complete 78.4% of the time and
    # gain 9.13 yards after the catch because the receiver has blockers in
    # front of him rather than defenders. Our engine clamped air yards at zero,
    # so none of it existed and every short throw piled into the 0-9 band at
    # 80.6% of completions against a real 54.1%.
    #
    # Behind the line is 18.4% of all attempts and short is 49.5%, so a little
    # over a quarter of what this engine calls a short throw is really a screen.
    screen = (depth == 'short' and not off_call.get('play_action')
              and rng.random() < SCREEN_SHARE)
    concept = off_call.get('concept', 'curl_flat')
    # The offence does NOT know the rush count before the snap. Choosing max
    # protect because six are coming let the defence's blitz cancel itself, so
    # the sack rate barely moved from four to six rushers.
    prot_name = S.choose_protection(off_call['personnel'], 4, depth, rng)
    prot = S.protection_math(prot_name, def_call['rushers'])

    # WHO STAYS IN. The extra blockers used to be the second tight end and
    # the second back, while the starters ran a route on every dropback.
    # Real (PFF): the back stays in on about 26% of pass plays and the
    # tight end on about 16%, and the man who blocks is not in the pattern.
    # So the men the protection keeps are drawn from the starters: on a
    # six-man protection the back most often, the tight end otherwise; on
    # seven both; on max the second tight end too.
    back = (off.get('backs') or [off.get('rb')])[0] if (off.get('backs') or off.get('rb')) else None
    te1 = next((x for x in off['wr'] if x.get('pos') == 'TE'), None)
    extras = []
    n_extra = max(0, prot['blockers'] - 5)
    if n_extra >= 1:
        # a two-tight-end grouping keeps the tight end more often than the
        # back; a spread grouping keeps the back (PFF: tight ends block on
        # ~16% of pass plays league-wide, from near nothing to 30%-plus)
        te_keeps = {'12': 0.75, '13': 0.82, '21': 0.58, '22': 0.68}.get(str(off_call.get('personnel', '11')), 0.42)
        first = te1 if (te1 is not None and (back is None or rng.random() < te_keeps)) else back
        if first is not None: extras.append(first)
    if n_extra >= 2:
        second = te1 if (te1 is not None and te1 not in extras) else back
        if second is not None and second not in extras: extras.append(second)
    if n_extra >= 3:
        extras += [x for x in off.get('extra_blockers', []) if x not in extras][:n_extra - len(extras)]
    blockers = off['ol'][:5] + extras
    kept_in = {id(x) for x in extras}
    rushers = (deff['dl'] + deff['lb'])[:def_call['rushers']]

    p = resolve_protection(blockers, rushers, rng, qb=off['qb'])
    # A protection scheme is worth real time against a blitz, and a simulated
    # pressure makes the line set for a front that never comes.
    if def_call['rushers'] >= 5:
        # Real: 4-man 6.61% sack / 61.9% comp, blitz 8.35% / 56.1%. The blitz
        # penalty has to be SMALL - 8.5% per extra rusher put a six-man rush at
        # an 18% sack rate against a real ~10%.
        p['time'] *= prot['vs_blitz'] * (1.0 - 0.030 * (def_call['rushers'] - 4))
    if def_call.get('protection_error'):
        p['time'] *= 1.0 - def_call['protection_error']
    p['pressure'] = float(np.clip((2.72 - p['time']) / 2.72, 0.0, 1.0))
    # 25.0/2.40 was solved for a bare four-man rush in isolation. Once blitzes,
    # deep drops and protection schemes are in the mix the BLEND has to land on
    # 6.6%, so the constant comes down.
    # Solved together with RUSHER_BASE: a longer clock alone would have taken
    # sacks to ~4.7%. Sacks are measured after a mobile QB has turned some of
    # them into scrambles (game.py), which is what the register counts.
    # THE DROP DEPTH SETS HOW LONG HE HOLDS IT. A three-step throw is out
    # before the rush matters; a seven-step shot waits for the route. The
    # sack roll used to read only the rush's arrival, so a quick game and a
    # deep game were sacked at the same rate against a real ~3% and ~10%.
    hold = HOLD_BY_DEPTH.get('screen' if screen else depth, 0.0)
    p['sack'] = rng.random() < float(np.clip(SACK_K * np.exp(-2.40 * (p['time'] - hold)), 0, .85))

    # Free rushers force the ball out. That is what a hot route IS, and it is
    # the real answer to a blitz - not simply eating the sack.
    hot = prot['hot']
    if hot:
        depth = 'short'
        p['pressure'] = min(1.0, p['pressure'] + 0.20)

    if hot:
        p['sack'] = p['sack'] and rng.random() < 0.35
    if PASS_TRACE is not None:
        PASS_TRACE.append(dict(path='clock', time=p['time'], hot=bool(hot),
                               sack=bool(p['sack']), rushers=def_call['rushers']))
    if p['sack'] and not hot:
        return dict(type='sack', yards=round(-rng.gamma(2.0, 3.4), 1), depth=depth, screen=bool(screen),
                    touchdown=False, by=p['beaten_by'], concept=concept,
                    protection=prot_name, pb_reps=p['pb_reps'], ttt=round(float(p['time']), 3),
                    beaten=p.get('beaten'), pressured=True)

    # the concept, against the coverage it actually faces
    cmult = S.concept_multiplier(
        concept, def_call.get('coverage') or def_call['shell'])
    if off_call.get('play_action') and not off_call.get('shotgun'):
        cmult *= 1.18                      # real: 6.91 ypp vs 3.63 without
    elif off_call.get('play_action'):
        cmult *= 1.10
    dis = S.disguise_penalty(off['qb'], def_call.get('fooled', False), rate)

    # The pattern is the concept's receivers, but the BACK is always an outlet
    # and a tight end is usually in it. Slicing purely by the concept's route
    # count cut the TE and the RB out of the pattern entirely, so they never
    # saw a target - against a real 22.5% for tight ends and 18.1% for backs.
    # THE PATTERN is everyone who is not blocking: the receivers, the tight
    # end unless he stayed in, and the back unless he stayed in. The man kept
    # in by the protection is out of the pattern, which is the whole point of
    # keeping him in.
    pool = [x for x in off['wr'] if id(x) not in kept_in]
    receivers = pool[:5]
    if back is not None and id(back) not in kept_in and not any(r is back for r in receivers) and len(receivers) < 6:
        receivers.append(back)
    if not receivers: receivers = list(off['wr'])[:1]

    # Coverage assignment and target selection. Before this the target was a
    # uniform draw from the receivers and the defender a uniform draw from the
    # secondary, so a TE could be covered by a corner and a WR1 by a safety.
    import coverage as CV, targets as TG
    # FORMATION, not list order. receiver_alignment assigned spot and side by
    # index, so the first receiver was X and always on the left - six hundred
    # snaps out of six hundred. The same two corners split him forever and
    # whichever drew him took nearly every pass break-up in the league.
    import formations as FM
    aligned = FM.align(receivers, off_call.get('personnel', '11'), rng, rate,
                       formation=off_call.get('formation'),
                       down=off_call.get('down', 1),
                       ydstogo=off_call.get('ydstogo', 10))
    # ONLY THE MEN WHO ACTUALLY DROPPED CAN COVER. Coverage was assigned from
    # the whole depth chart regardless of the rush, so a linebacker could be
    # blitzing in the protection math and covering the back in the same snap -
    # and because the pools never changed, the same corner drew the same
    # receiver on every play of every game.
    #
    # The rush decision already exists and is already calibrated: call_defense
    # picks blitzers at the real rates and separates a five-man rush from a
    # blitz. It was simply never read here. Now the rushers come off the top
    # and whoever is left is the coverage - so rushing three leaves eight to
    # drop and blitzing a slot corner forces somebody else onto that receiver.
    rusher_ids = {id(x) for x in rushers}
    in_coverage = dict(deff)
    in_coverage['lb'] = [x for x in deff['lb'] if id(x) not in rusher_ids]
    in_coverage['dl'] = [x for x in deff['dl'] if id(x) not in rusher_ids]
    in_coverage['db'] = list(deff['db'])
    global LAST_TRAVEL
    pairs, travelled = CV.assign_coverage(
        aligned, in_coverage, def_call, rng, rate,
        coach_willingness=off_call.get('travel_willingness', 0.5),
        travel=def_call.get('travel'))

    LAST_TRAVEL = bool(travelled)
    # every man in the pattern gets his own separation from his own matchup
    for pr in pairs:
        pr_depth = 'short' if pr['receiver'].get('pos') in ('HB', 'FB') and depth != 'short' else depth
        pr['separation'] = resolve_man(pr['receiver'], pr['defender'], pr_depth,
                                       p['time'], rng)
        # a bracketed man is squeezed, not erased - an elite receiver doubled
        # still beats an average one singled
        if def_call.get('bracket') == pr['receiver'].get('pid'):
            pr['separation'] *= 0.72

    tgt, cov, read_kind, sep_raw = TG.select_target(
        pairs, off['qb'], concept, rng, rate, plan=off_call.get('plan'))
    if tgt is None:
        tgt, cov, read_kind, sep_raw = receivers[0], deff['db'][0], 'first', 0.42

    if tgt.get('pos') in ('HB', 'FB') and depth != 'short' and not screen:
        depth = 'short'                          # the back's route is a check, a flat, a swing
    rmod = TG.READ_MODIFIER.get(read_kind, TG.READ_MODIFIER['first'])

    # PER-PAIRING, not per-defence. The man who ends up targeted may be in man
    # while the receiver on the other side is in zone - that is a split-field
    # call, and it could not be expressed at all before.
    tgt_pair = next((x for x in pairs if x['receiver'] is tgt), None)
    in_man = tgt_pair.get('man') if tgt_pair else def_call.get('man', False)
    # ZONE AS SPACE (zones.py): in a zone call the man who contests is the
    # owner of the area the route lands in, a second man may converge, the
    # area may be a hole, and quarters plays a vertical by an outside man
    # as man. The pairing's defender only stands in a man call.
    zone_owner, zone_second, zone_hole = None, None, False
    if not in_man and tgt_pair is not None:
        import zones as ZN
        zone_owner, zone_second, zone_hole, match_man = ZN.contest(
            def_call.get('coverage') or def_call['shell'], tgt_pair, rushers, depth, rng, rate)
        if match_man:
            in_man = True; cov = zone_owner
        elif zone_owner is not None:
            cov = zone_owner
    if in_man:
        cb = cov
        # Apply the concept and read modifiers to the COMPLETION PROBABILITY,
        # not to separation. Separation runs through a steep depth multiplier,
        # so folding a 0.94 concept factor into it cost far more than the same
        # factor applied at the end - which is what the zone path does. The
        # mismatch left man coverage 12 points below zone at short depth
        # (61.6% against 75.7%) and dragged league completion to 58.5%.
        sep = float(np.clip(sep_raw, .02, .98))
        thr = resolve_throw(off['qb'], depth, sep, p['pressure'], rng,
                            play_action=off_call.get('play_action', False),
                            outcome_mult=cmult * (1.0 - dis) * rmod['comp'])
        complete = thr['result'] == 'complete'
        if PASS_TRACE is not None:
            PASS_TRACE.append(dict(path='man', depth=depth, screen=screen,
                                   base=thr['base'], p=thr['p'],
                                   acc=rate(off['qb'], THROW[depth]),
                                   sep=sep, cmult=cmult, rmod=rmod['comp'],
                                   dis=dis, pressure=p['pressure']))
        if screen and not complete and rng.random() < SCREEN_RESCUE:
            complete = True        # a ball thrown at his numbers three yards
                                   # behind the line is rarely missed
        picked = thr['result'] == 'interception'
        contested = thr['contested']
    else:
        # Only the NEAREST defender contests - handing the resolver the whole
        # secondary made every window contested by the best of six and dropped
        # league completion to 51.6% against a real 65.0%.
        dbs = ([dict(cov, dist_to_window=0)] if not zone_hole else []) + \
              ([dict(zone_second, dist_to_window=1)] if zone_second is not None else [])
        z = resolve_zone(tgt, dbs, off['qb'], def_call['shell'], depth,
                         p['pressure'], rng, rate, hole=zone_hole)
        # Apply the concept to the WINDOW, not as a second independent gate.
        # Gating twice dropped four-man-rush completion to 51.8% against a
        # real 61.9%.
        # Coverage bodies matter: a blitz leaves fewer men to cover, which is
        # exactly why blitzing costs completion percentage and gains sacks.
        cover_relief = 1.0 + 0.085 * max(0, def_call['rushers'] - 4)
        adj = float(np.clip(z['p_complete'] * cmult * cover_relief * (1.0 - dis)
                            * rmod['comp'], 0.02, 0.97))
        if screen:
            adj = min(0.97, adj + SCREEN_RESCUE)
        if PASS_TRACE is not None:
            PASS_TRACE.append(dict(path='zone', depth=depth, screen=screen,
                                   base=z['raw'] * cmult * cover_relief
                                        * (1.0 - dis) * rmod['comp'],
                                   p=adj, acc=rate(off['qb'], THROW[depth]),
                                   window=z['window'], cmult=cmult,
                                   rmod=rmod['comp'], dis=dis,
                                   pressure=p['pressure'],
                                   relief=cover_relief))
        complete = rng.random() < adj
        # 2.1% is the rate per ATTEMPT, not per incompletion. Applying it to
        # incompletions only produced ~1.1% league-wide.
        picked = (not complete) and rng.random() < 0.092   # re-anchored with the man path
        contested = z['contested']
        cb = cov
        # the man who arrives second breaks up his share of the throws he
        # converges on: that is where a safety's box score comes from
        if zone_second is not None and rng.random() < 0.45:
            cb = zone_second

    if picked:
        return dict(type='interception', yards=0.0, touchdown=False,
                    depth=depth, in_man=bool(in_man), screen=bool(screen), coverage=def_call.get('coverage') or def_call['shell'],
                    concept=concept, protection=prot_name, target=tgt.get('pid'),
                    by=cb.get('pid'), read=read_kind, pb_reps=p['pb_reps'], ttt=round(float(p['time']), 3), pressured=bool(p['pressure'] >= 0.35))
    if not complete:
        # A PASS DEFENDED is a defender breaking the ball up, not simply an
        # incompletion - a throw into the dirt is nobody's credit. Real rate:
        # 37.5% of incompletions, 11.4% of attempts, with a league leader
        # around 24 in a season. It is the main counting stat a corner has and
        # this engine resolved the event without recording it, so a defensive
        # back had almost no box score at all.
        broken = (not contested) and rng.random() < PD_LOOSE
        if contested:
            broken = rng.random() < PD_CONTESTED
        return dict(type='incomplete', yards=0.0, touchdown=False,
                    depth=depth, in_man=bool(in_man), screen=bool(screen), coverage=def_call.get('coverage') or def_call['shell'],
                    concept=concept, protection=prot_name, target=tgt.get('pid'),
                    read=read_kind, pb_reps=p['pb_reps'], ttt=round(float(p['time']), 3),
                    pass_def=(cb.get('pid') if broken and cb else None),
                    pressured=bool(p['pressure'] >= 0.35))
    # A contested ball that already survived the throw should not face the full
    # contested-catch gate again; drops were running at 8.7% against a real ~5%.
    if not resolve_catch(tgt, cb, contested and rng.random() < 0.45, rng):
        return dict(type='drop', yards=0.0, touchdown=False,
                    depth=depth, in_man=bool(in_man), screen=bool(screen), coverage=def_call.get('coverage') or def_call['shell'],
                    concept=concept, protection=prot_name, target=tgt.get('pid'),
                    read=read_kind, pb_reps=p['pb_reps'], ttt=round(float(p['time']), 3), pressured=bool(p['pressure'] >= 0.35))

    # Real air yards average 7.8 with 5.2 after the catch. Short throws were
    # landing at 4.0 and dragging yards per dropback to 4.2 against a real 6.18.
    # Air yards follow the READ. Real: first read 10.9, second 11.0,
    # checkdown 0.7, designed -3.0, scramble 11.6.
    # Real air yards ON COMPLETIONS: 5.72 overall, with the bands running
    # -2.76 behind the line, 4.03 short, 11.93 medium, 25.29 deep. The short
    # band includes throws behind the line, which pulled the real mean down.
    if screen:
        # Real behind-the-line throws average -3.55 air yards on attempts and
        # -2.76 on completions.
        air = float(np.clip(rng.normal(-3.4, 2.2), -9.0, -0.5))
    else:
        # THE DEEP BALL BARELY EXISTED. Blending the depth base half-and-half
        # with the read modifier pulled a deep throw down to 13-16 air yards,
        # so it landed in the 10-19 band and only 0.5% of completions
        # travelled 20+ against a real 6.3%. Real deep completions average
        # 27.6 air yards. The read modifier should colour a throw, not decide
        # how far it goes - the play call already did that.
        base_air = {'short': 2.6, 'medium': 9.8, 'deep': 26.5}[depth]
        w = 0.80 if depth == 'deep' else 0.55
        air = w * base_air + (1.0 - w) * max(0.0, rmod['air'])
        air = max(0.0, air + rng.normal(0, 3.0 if depth != 'deep' else 4.5))
    # A throw to the back of the end zone travels the full remaining distance -
    # it is not clipped short. Clipping it left the YAC chain no room and made
    # scoring from the 15-20 nearly impossible: 1.9% per play against a real 7.0%.
    if screen:
        pass                                   # it already travelled backwards
    elif air >= ytg * 0.68 and ytg <= 25:
        air = float(ytg)
    else:
        air = min(air, float(ytg))
    # A receiver catching the ball faces the two or three defenders near him,
    # not the entire back seven. Handing the resolver ten pursuers crushed
    # yards after catch to 2.8 against a real 5.2.
    if air >= ytg:
        return dict(type='complete', yards=round(float(ytg), 1),
                    air=round(float(air), 1), yac=0.0, touchdown=True,
                    in_man=bool(in_man), screen=bool(screen),
                    coverage=def_call.get('coverage') or def_call['shell'],
                    concept=concept, protection=prot_name, depth=depth,
                    target=tgt.get('pid'), read=read_kind,
                    separation=round(float(sep_raw), 3), pb_reps=p['pb_reps'], ttt=round(float(p['time']), 3), pressured=bool(p['pressure'] >= 0.35))
    # Real YAC by throw depth: behind the line 8.63, short 3.97, medium 3.48,
    # deep 5.31 - a U-shape, because a screen has blockers in front and a deep
    # ball is caught past everyone, while an intermediate throw is caught in
    # traffic. Flat pursuit produced 3.06 overall against a real 5.19.
    pool = deff['db'] + deff['lb']
    n_near = {'short': 3, 'medium': 4, 'deep': 2}[depth]
    if air <= 0: n_near = 2                       # screen: blockers ahead
    tacklers = [pool[rng.integers(0, len(pool))] for _ in range(n_near)]
    if tgt.get('pos') in ('HB', 'FB') and not screen:
        # A BACK'S CATCH is at the line with the underneath defence in front
        # of him: the man who had him is the first tackler and the box
        # linebackers arrive next. Drawing his tacklers from the whole
        # secondary put corners forty yards away on the list and left backs
        # at 8-9 yards a target against a real 6.
        first = [cov] if cov is not None else []
        lbs = list(deff['lb']) or pool
        tacklers = first + [lbs[rng.integers(0, len(lbs))] for _ in range(2)] + [pool[rng.integers(0, len(pool))]]
    # IN SPACE ONLY WHERE THERE IS SPACE. Every catch used to be resolved as
    # if the receiver had open field, and near the goal line he does not: the
    # end zone is a wall and eleven defenders are standing in twenty yards.
    # Real yards after catch collapse from 5.64 beyond the opponent 41 to 2.68
    # from the 6-10 and 0.94 inside the 5.
    #
    # This was the whole red zone problem. Scoring from 6-10 out ran at 28.7%
    # of plays against a real 19.5%, and drives reaching the twenty scored
    # 76.4% of the time against a real 61.0%.
    room = max(0.0, ytg - air)
    # a back's catch in the flat or behind the line is a run against a set
    # defence, not a receiver in space: at in_space the backs averaged
    # 9-10 yards a target against a real 6
    in_space = tgt.get('pos') not in ('HB', 'FB')
    yac = resolve_yards_after(tgt, tacklers, room, rng, in_space=in_space)
    yac['yards'] = round(yac['yards'] * _compression(room), 1)
    total = min(air + yac['yards'], ytg)
    return dict(type='complete', yards=round(float(total), 1), air=round(float(air), 1),
                yac=yac['yards'], touchdown=total >= ytg, concept=concept,
                in_man=bool(in_man), screen=bool(screen),
                coverage=def_call.get('coverage') or def_call['shell'],
                protection=prot_name, depth=depth, target=tgt.get('pid'),
                read=read_kind, separation=round(float(sep_raw), 3), pb_reps=p['pb_reps'], ttt=round(float(p['time']), 3), pressured=bool(p['pressure'] >= 0.35))

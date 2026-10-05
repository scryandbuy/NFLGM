"""
The scheme layer.

Everything here sits BETWEEN the play call and the matchup resolution. A play
is no longer "a dropback" or "a run" - it is a personnel group, a formation, a
concept, against a front, a box count and a coverage, with a protection scheme
that may or may not have enough bodies.

Every rate is from real data: FTN charting of 96,256 plays (2023-24) for scheme
usage, and six seasons of play-by-play for the effects.
"""
import numpy as np
from statistics import NormalDist
import defense_roles as DR

# ============================================================ PERSONNEL
# offence: first digit RB, second TE, remainder WR
PERSONNEL_OFF = {
    '11': dict(rb=1, te=1, wr=3, rate=.595, run_bias=-0.10, protect=5),
    '12': dict(rb=1, te=2, wr=2, rate=.195, run_bias=+0.18, protect=6),
    '21': dict(rb=2, te=1, wr=2, rate=.070, run_bias=+0.26, protect=6),
    '13': dict(rb=1, te=3, wr=1, rate=.030, run_bias=+0.40, protect=7),
    '10': dict(rb=1, te=0, wr=4, rate=.075, run_bias=-0.28, protect=5),
    '22': dict(rb=2, te=2, wr=1, rate=.025, run_bias=+0.48, protect=7),
    '00': dict(rb=0, te=0, wr=5, rate=.010, run_bias=-0.45, protect=5),
}
# Defence answers personnel. The bodies in each package come from
# defense_roles.shape(front, package), since odd and even fronts differ.
PERSONNEL_DEF = {
    'base':   dict(box_bonus=+1.0, cover_penalty=0.10),
    'nickel': dict(box_bonus= 0.0, cover_penalty=0.00),
    'dime':   dict(box_bonus=-1.0, cover_penalty=-0.06),
    'heavy':  dict(box_bonus=+2.0, cover_penalty=0.22),
}

def defensive_personnel(off_pers, down, ydstogo, rng, gm_aggr=0.5, sub_lean=0.0):
    """What the defence puts on the field to answer the offence's grouping. sub_lean is the coordinator's
    halftime call: +1 leans a step lighter (base to nickel, nickel to dime), -1 a step heavier."""
    wr = PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])['wr']
    if wr >= 4:  base = 'dime' if (down == 3 and ydstogo >= 7) else 'nickel'
    elif wr == 3: base = 'nickel'
    elif wr == 2: base = 'base' if rng.random() < 0.70 else 'nickel'
    else:         base = 'heavy' if rng.random() < 0.50 else 'base'
    if down == 3 and ydstogo >= 8 and base in ('base', 'nickel'):
        base = 'nickel' if base == 'base' else 'dime'
    if down in (3, 4) and ydstogo <= 2 and base == 'nickel':
        base = 'base' if rng.random() < 0.6 else 'nickel'
    if sub_lean and rng.random() < min(0.85, abs(sub_lean) * 0.6):
        order = ['heavy', 'base', 'nickel', 'dime']; i = order.index(base) if base in order else 1
        base = order[max(0, min(3, i + (1 if sub_lean > 0 else -1)))]
    return base

# ============================================================ FRONTS
# One-gap penetrates; two-gap occupies to free linebackers. These are different
# JOBS for the same body, and a single "defensive line" number cannot express it.
FRONTS = {
    '4-3 over':  dict(dl=4, gap='one', edge_set='strong', run_fit=1.00, rush=1.00),
    '4-3 under': dict(dl=4, gap='one', edge_set='weak',   run_fit=1.02, rush=0.98),
    '3-4 one':   dict(dl=3, gap='one', edge_set='both',   run_fit=0.96, rush=1.04),
    '3-4 two':   dict(dl=3, gap='two', edge_set='both',   run_fit=1.06, rush=0.90),
    # Standard odd-coach nickel/dime: two interior defenders and both edges
    # on the rush line. The three-interior tite/mint look is a base call.
    '3-4 sub':   dict(dl=4, gap='one', edge_set='both',   run_fit=1.00, rush=1.02),
    'tite':      dict(dl=3, gap='two', edge_set='both',   run_fit=1.10, rush=0.86),
    'bear':      dict(dl=5, gap='one', edge_set='both',   run_fit=1.14, rush=1.06),
    'wide 9':    dict(dl=4, gap='one', edge_set='both',   run_fit=0.90, rush=1.10),
    'mint':      dict(dl=3, gap='two', edge_set='both',   run_fit=1.08, rush=0.88),
}
# Tite closes the interior against zone specifically; gap runs are its answer,
# which is why gap concepts rose as a counter to Tite.
FRONT_VS_SCHEME = {
    'tite':      {'zone': 0.84, 'gap': 1.06},
    'mint':      {'zone': 0.86, 'gap': 1.05},
    'bear':      {'zone': 0.92, 'gap': 0.90},
    '3-4 two':   {'zone': 0.94, 'gap': 1.00},
    'wide 9':    {'zone': 1.08, 'gap': 0.96},
    '4-3 over':  {'zone': 1.00, 'gap': 1.00},
    '4-3 under': {'zone': 0.98, 'gap': 1.02},
    '3-4 one':   {'zone': 1.02, 'gap': 1.00},
    '3-4 sub':   {'zone': 1.00, 'gap': 1.00},
}

def goal_line_box_bonus(yards_to_endzone):
    """
    Real box counts: 6.55 inside the 5, 5.49 from the 6-10, 4.40 at 21-50.
    The defence walks up because there is nothing to defend behind them.
    """
    # Real box counts: 6.55 inside the 5, 5.49 from the 6-10, 4.40 at 21-50.
    # Goal-line defence is heavier still than the 6.55 average suggests, because
    # that figure blends pass and run downs; on the 1 and 2 everyone is in the
    # box. Without extra resistance the sim scored on 65% of plays from the 2
    # against a real 42.9%.
    if yards_to_endzone <= 2:  return 4.30
    if yards_to_endzone <= 5:  return 3.05
    if yards_to_endzone <= 10: return 1.95
    return 0.0

def box_count(def_pers, front, off_pers, blitzers, rng, yards_to_endzone=50):
    """
    Bodies in the box. Real distribution: 6 on 37.6%, 7 on 18.3%, 5 on 10.5%,
    8 on 4.7%.
    """
    # Not every linebacker is IN the box, and the front-four ends are often
    # widened out of it. The first build counted every front-seven body and
    # produced 7-man boxes on 34% of snaps against a real 18%.
    # Real box counts average 4.40 between the 21 and 50. Counting nearly the
    # whole front seven put the sim at 6.15 there and suppressed the run
    # league-wide; ends are widened out of the box and linebackers are often
    # walked out against spread personnel.
    personnel = DR.counts(DR.front_family(front), def_pers)
    b = personnel['dl'] * 0.74 + personnel['lb'] * 0.62
    b += PERSONNEL_DEF[def_pers]['box_bonus'] * 0.34
    b += 0.45 * PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])['te']
    b += 0.34 * PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])['rb']
    b += blitzers * 0.80
    b += goal_line_box_bonus(yards_to_endzone)
    return int(np.clip(round(b + rng.normal(0, 0.34)), 4, 10))

# Real yards per carry by box count, six seasons.
BOX_YPC = {4: 6.6, 5: 5.92, 6: 4.76, 7: 4.16, 8: 3.77, 9: 2.41, 10: 2.0}
BOX_NEG = {4: 4.5, 5: 5.53, 6: 8.20, 7: 9.57, 8: 11.14, 9: 13.76, 10: 16.0}

def box_run_multiplier(box):
    """
    How much this box count helps or hurts a run, relative to a 6-man box.
    The raw ratio is applied to POSITIVE yards before contact only; loss
    generation is separate. The break-tackle chain compresses the ratio,
    so it is exponentiated to survive that.
    Without it the sim spread only 5.51 to 3.72 against a real 5.92 to 2.41.
    """
    return (BOX_YPC.get(int(np.clip(box, 4, 10)), 4.5) / BOX_YPC[6]) ** 2.1

# Translate the existing box-specific loss rates into a contact-depth shift.
# This changes penetration risk on the same matchup/noise draw, not via an
# independent stuff lottery that could erase a won blocking matchup.
_BOX_CONTACT_SHIFT = {box: NormalDist().inv_cdf(BOX_NEG[6] / 100)
                      - NormalDist().inv_cdf(pct / 100) for box, pct in BOX_NEG.items()}


def box_run_contact(yards, box, neutral_mean, noise):
    """Box pressure changes the loss threshold; gain scaling never shrinks losses."""
    box = max(4, min(10, int(box)))
    shift = noise * _BOX_CONTACT_SHIFT[box]
    contact = yards + shift
    if contact <= 0:
        return contact
    # Recenter the positive branch around its previous neutral mean before
    # applying the existing gain multiplier. Otherwise the shift would also
    # amplify light-box gains / suppress heavy-box gains a second time.
    return contact * neutral_mean / (neutral_mean + shift) * box_run_multiplier(box)


# ============================================================ PROTECTION
# The scheme decides how many bodies stay in - and every body that stays in is
# a receiver who does not run a route. That is the trade.
PROTECTIONS = {
    'five':       dict(blockers=5, routes_lost=0, vs_stunt=0.92, vs_blitz=0.85),
    'six_bob':    dict(blockers=6, routes_lost=1, vs_stunt=0.96, vs_blitz=1.00),
    'six_slide':  dict(blockers=6, routes_lost=1, vs_stunt=1.08, vs_blitz=1.04),
    'half_slide': dict(blockers=6, routes_lost=1, vs_stunt=1.05, vs_blitz=1.06),
    'seven':      dict(blockers=7, routes_lost=2, vs_stunt=1.02, vs_blitz=1.16),
    'max':        dict(blockers=8, routes_lost=3, vs_stunt=1.00, vs_blitz=1.25),
}

def choose_protection(off_pers, expected_rush, depth, rng, gm_aggr=0.5, preference=None):
    """Longer-developing concepts need more bodies; quick game needs fewer."""
    avail = PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])['protect']
    chosen = {'half_slide': 'half_slide', 'full_slide': 'six_slide', 'six': 'six_bob', 'empty': 'five'}.get(preference)
    if chosen:
        personnel = PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])
        return chosen if PROTECTIONS[chosen]['blockers'] <= 5 + personnel['rb'] + personnel['te'] else 'five'
    # five men out is the base of the modern game: with the starters the
    # ones who stay in, six-man protection on 65% of dropbacks kept the back
    # in on 48% against a real 26 (PFF) and the tight end near 16
    five_rate = {'short': 0.75, 'medium': 0.55, 'deep': 0.35}.get(depth, 0.6)
    if rng.random() < five_rate:
        return 'five'
    if depth == 'deep' and avail >= 7 and rng.random() < 0.30:
        return 'seven'
    if expected_rush >= 6 and avail >= 7:
        return 'seven'
    return 'half_slide' if rng.random() < 0.62 else 'six_bob'

def protection_math(protection, rushers, hot_available=True):
    """
    Who is unblocked, and is there an answer. When the offence cannot block
    everyone there is a built-in hot route and the QB must beat the free rusher
    with a quick throw. That is the real answer to a blitz.
    """
    p = PROTECTIONS[protection]
    free = max(0, rushers - p['blockers'])
    return dict(blockers=p['blockers'], free_rushers=free,
                routes_lost=p['routes_lost'],
                hot=free > 0 and hot_available,
                vs_blitz=p['vs_blitz'], vs_stunt=p['vs_stunt'])

# ============================================================ RUN SCHEME
# Zone blocks an AREA and makes the defence wrong whatever it does, and works
# with smaller, more agile linemen. Gap blocks DOWN and pulls a man to kick out,
# using leverage to beat physically superior linemen - and is inert if the point
# men cannot create movement. Taking the max of both erases the distinction.
RUN_SCHEMES = {
    'inside_zone':  dict(family='zone', aim='inside',  cutback=0.42, attr='finesse'),
    'outside_zone': dict(family='zone', aim='outside', cutback=0.55, attr='finesse'),
    'stretch':      dict(family='zone', aim='wide',    cutback=0.60, attr='finesse'),
    'power':        dict(family='gap',  aim='inside',  cutback=0.12, attr='power'),
    'counter':      dict(family='gap',  aim='inside',  cutback=0.18, attr='power'),
    'duo':          dict(family='gap',  aim='inside',  cutback=0.25, attr='power'),
    'trap':         dict(family='gap',  aim='inside',  cutback=0.15, attr='power'),
    'draw':         dict(family='zone', aim='inside',  cutback=0.30, attr='finesse'),
}
# Gap is specifically better near the goal line: extra defenders on the line
# create easy down blocks, which is why it shows up around the end zone.
def run_scheme_multiplier(scheme, front, yards_to_endzone, box):
    s = RUN_SCHEMES[scheme]
    m = FRONT_VS_SCHEME.get(front, {}).get(s['family'], 1.0)
    if s['family'] == 'gap' and yards_to_endzone <= 5: m *= 1.12
    if s['family'] == 'zone' and box >= 8: m *= 0.93
    return m

# ============================================================ ROUTE CONCEPTS
# A concept beats a COVERAGE, which is the mechanism by which a play call beats
# a defensive call. Multipliers are on the window/separation the concept yields.
CONCEPTS = {
    #              depth     vs man  vs c2  vs c3  vs c4  routes
    'mesh':        dict(depth='short',  man=1.28, cover_2=1.10, cover_3=1.08, cover_4=1.12, n=4),
    'flood':       dict(depth='medium', man=0.96, cover_2=1.06, cover_3=1.18, cover_4=1.10, n=3),
    'smash':       dict(depth='short',  man=1.02, cover_2=1.20, cover_3=1.02, cover_4=1.14, n=2),
    'levels':      dict(depth='short',  man=0.98, cover_2=1.12, cover_3=1.16, cover_4=1.08, n=3),
    'dagger':      dict(depth='medium', man=1.04, cover_2=1.14, cover_3=1.12, cover_4=0.96, n=3),
    'four_verts':  dict(depth='deep',   man=1.10, cover_2=1.18, cover_3=1.14, cover_4=0.90, n=4),
    'scissors':    dict(depth='deep',   man=1.02, cover_2=0.98, cover_3=1.00, cover_4=1.22, n=2),
    'slant_flat':  dict(depth='short',  man=1.14, cover_2=1.02, cover_3=1.06, cover_4=1.00, n=2),
    'stick':       dict(depth='short',  man=0.98, cover_2=1.08, cover_3=1.12, cover_4=1.06, n=3),
    'curl_flat':   dict(depth='short',  man=0.94, cover_2=1.06, cover_3=1.14, cover_4=1.04, n=3),
    'screen':      dict(depth='short',  man=1.20, cover_2=0.94, cover_3=0.92, cover_4=0.90, n=1),
    'go':          dict(depth='deep',   man=1.16, cover_2=1.04, cover_3=0.92, cover_4=0.84, n=2),
}
# THE CONCEPT IS SCORED AGAINST WHAT IS ACTUALLY PLAYED. This used to be keyed
# off the SHELL, and once the defence started making real coverage calls the
# two came apart: a concept built to beat man was being scored against a zone
# shell while the defence played two-man underneath it. The whole mechanism by
# which a play call beats a defensive call was pointing at the wrong thing.
SHELL_KEY = {'cover_0': 'man', 'cover_1': 'man', 'man': 'man',
             'cover_1_robber': 'man', 'two_man': 'man',
             'cover_2': 'cover_2', 'tampa_2': 'cover_2',
             'cover_3': 'cover_3', 'cover_6': 'cover_3',
             'cover_3_mable': 'man', 'fire_zone': 'cover_3',
             'cover_4': 'cover_4'}

def concept_multiplier(concept, shell):
    return CONCEPTS[concept].get(SHELL_KEY.get(shell, 'cover_3'), 1.0)

# ============================================================ DISGUISE
# A static two-high shell that rotates AFTER the snap forces the QB to process
# once the play has started. A mug front that drops into coverage makes him set
# protection for a seven-man front and face four from odd angles.
def disguise(shell, gm_deception, rng):
    """Returns (shown, actual, whether the QB is fooled at all)."""
    # Roughly a quarter of snaps carry a real disguise; the first build ran 47%.
    if rng.random() > 0.10 + 0.32 * gm_deception:
        return shell, shell, False
    pairs = {'cover_3': 'cover_2', 'cover_1': 'cover_2', 'cover_4': 'cover_2',
             'cover_2': 'cover_3', 'cover_0': 'cover_2', 'tampa_2': 'cover_2',
             'cover_6': 'cover_2'}
    return pairs.get(shell, 'cover_2'), shell, True

def disguise_penalty(qb, fooled, rate_fn, AVG=0.70):
    """A good processor is barely fooled; a poor one throws into the rotation."""
    if not fooled: return 0.0
    iq = rate_fn(qb, {'awareness_rating': .65, 'play_action_rating': .15,
                      'throw_under_pressure_rating': .20})
    return float(np.clip(0.26 * (1.0 - 1.6 * (iq - AVG)), 0.0, 0.40))

def simulated_pressure(rng, gm_deception):
    """
    Show six or seven, drop most, send four from unusual angles. The rush is
    numerically standard but functionally a blitz - it sits outside any model
    that only counts rushers.
    """
    # The league LEADER runs off-ball simulated pressure on 37% of snaps, so
    # the league average is far lower. The first build ran 25% everywhere.
    if rng.random() < 0.04 + 0.16 * gm_deception:
        return dict(sim=True, shown_rushers=6, actual_rushers=4,
                    protection_error=0.28, coverage_bodies=7)
    return dict(sim=False, shown_rushers=None, actual_rushers=None,
                protection_error=0.0, coverage_bodies=7)

# ============================================================ PLAY CALLING
# Real pass rates by down and distance, six seasons.
PASS_RATE = {
    1: {'1-2': .256, '3-4': .308, '5-7': .352, '8-10': .478, '11+': .668},
    2: {'1-2': .323, '3-4': .421, '5-7': .552, '8-10': .671, '11+': .773},
    3: {'1-2': .370, '3-4': .776, '5-7': .871, '8-10': .889, '11+': .834},
    4: {'1-2': .387, '3-4': .888, '5-7': .906, '8-10': .937, '11+': .906},
}
# Game script, by score differential.
SCRIPT = [(-99, -15, .700), (-14, -8, .659), (-7, -1, .595), (0, 0, .552),
          (1, 8, .535), (9, 15, .492), (16, 99, .399)]
NEUTRAL_SCRIPT = .552

def dist_band(ydstogo):
    if ydstogo <= 2: return '1-2'
    if ydstogo <= 4: return '3-4'
    if ydstogo <= 7: return '5-7'
    if ydstogo <= 10: return '8-10'
    return '11+'

def _logit(p):
    p = float(np.clip(p, 1e-4, 1 - 1e-4)); return float(np.log(p / (1 - p)))

def _sigmoid(x):
    return float(1.0 / (1.0 + np.exp(-x)))

def pass_rate(down, ydstogo, score_diff, yards_to_endzone, off_pers,
              gm_pass_bias=0.0, secs_left=None):
    """
    Share of snaps thrown. THE COACH READS EVERYTHING AT ONCE.

    Down and distance set the base; score, clock, field position and
    personnel each move it. They used to move it by MULTIPLYING the rate, and
    every one of those multipliers was measured on the whole-game pass rate
    (about 55%) with no down in it. Multiplying a third-and-long rate of 87%
    by a "up 16, run it" factor of 0.72 gives 63%, when real clubs up 16 on
    third and six still throw ~75%; stacking the personnel lean and the
    late-game blend on top had offences running third and long a quarter of
    the time and converting 14 to 32% of those.

    So the leans now add in LOG-ODDS. A shift that takes a 55% down to 45%
    takes an 87% down to 82%, which is how the real tables behave: the ends
    of the distribution stay at the ends. Near 50% (first down) the two forms
    agree, so first-down calling is unchanged.

    The clock is the biggest of the leans and it is nearly binary at the end
    of a game: 90% throwing down 9-16 in the last four minutes, 13% running it
    out up 9-16. decisions.pass_rate carries that table.
    """
    base = PASS_RATE.get(int(down), PASS_RATE[1])[dist_band(ydstogo)]
    conversion_pass = int(down) == 4 and ydstogo >= 5
    if conversion_pass:
        base = .975 if ydstogo < 6 else .985 if ydstogo < 7 else .99
    L = _logit(base)
    neutral = _logit(NEUTRAL_SCRIPT)
    # score
    sd = int(round(score_diff))
    script = next((v for lo, hi, v in SCRIPT if lo <= sd <= hi), NEUTRAL_SCRIPT)
    L += _logit(script) - neutral
    # field position: the red zone compresses (44.5% pass inside the 5), and
    # backed up against the own goal it compresses the other way (52.2%
    # inside the own 10, 46.6% inside the own 4, against 57.6% open field)
    mult = 1.0
    if yards_to_endzone <= 5:    mult = 0.75
    elif yards_to_endzone <= 10: mult = 0.88
    elif yards_to_endzone <= 20: mult = 0.90
    elif yards_to_endzone >= 96: mult = 46.6 / 57.6
    elif yards_to_endzone >= 91: mult = 52.2 / 57.6
    if mult != 1.0:
        L += _logit(NEUTRAL_SCRIPT * mult) - neutral
    # personnel: heavy groups lean to the run (the old form was -0.30 x bias
    # on the rate; the slope of the logistic at 55% is about 4)
    L += -1.2 * PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])['run_bias']
    # the plan's own lean
    L += 4.0 * gm_pass_bias
    # clock
    if secs_left is not None:
        import decisions as DEC
        target = DEC.pass_rate(score_diff, secs_left)
        w = 0.0 if secs_left > 1800 else (0.25 if secs_left > 900 else
                                          (0.55 if secs_left > 240 else 0.85))
        L += w * (_logit(target) - neutral)
    if conversion_pass:
        # Once committed to fourth-and-long, conversion distance dominates
        # normal clock/identity preferences. Keep a rare surprise run.
        L = _logit(base) + .4 * float(np.clip(L - _logit(base), -1.5, 1.5))
    return float(np.clip(_sigmoid(L), 0.03, .995 if conversion_pass else .98))

MOTION_NEUTRAL = 0.581        # the identity catalog's mean motion lean
BLITZ_NEUTRAL = 0.384         # the catalog's mean blitz lean
BLITZ_BASE = 0.048            # was 0.085 centred at 0.35; the coverage call's fire zones and cover 0 add about six points on their own


def designed_qb_run_chance(offense, defense, call, def_call, rate_fn, *,
                           condition=100., healthy_backups=1):
    """Share of already-called runs entrusted to the selected quarterback.

    A keep uses the same installed run scheme and gives the back a lead-block
    job. These are coaching judgments, not a measured league carry target.
    The handoff remains the alternative, including for an athletic passer.
    """
    qb = offense.get('qb')
    if (not qb or qb.get('pos') != 'QB' or call.get('is_pass')
            or call.get('sneak') or call.get('protect_ball') or condition <= 60):
        return 0.
    mobility = rate_fn(qb, {'speed_rating': .5, 'agility_rating': .3, 'accel_rating': .2})
    athlete = float(np.clip((mobility - .75) / .20, 0., 1.))
    if not athlete:
        return 0.  # A pocket passer's sneak is a different short-yardage job.
    down, distance = call.get('down', 1), call.get('ydstogo', 10)
    seconds, margin = call.get('seconds'), call.get('score_diff', 0)
    if seconds is not None and seconds <= 30:
        return 0.  # Preserve a scoring throw/kick, or let the back burn clock.
    if down >= 3 and distance > 6:
        return 0.  # Do not turn a long-yardage handoff into extra QB exposure.
    risk = float(np.clip(call.get('qb_run_aggression', .5), 0., 1.))
    choice = .24 * athlete * athlete * (.6 + .8 * risk)
    # Coach identity already determines the run's frequency and scheme. The
    # ballcarrier choice also values the handoff and its opportunity cost.
    rb = offense.get('rb')
    if rb:
        back_run = rate_fn(rb, {'speed_rating': .3, 'agility_rating': .3,
                               'bcv_rating': .2, 'break_tackle_rating': .2})
        choice *= float(np.clip(1. + 1.5 * (mobility - back_run), .7, 1.15))
    security = rate_fn(qb, {'carry_rating': .7, 'awareness_rating': .3})
    choice *= float(np.clip(1. + 1.5 * (security - .70), .55, 1.15))
    import defensive_rush as DR
    roles = DR.assignments(defense, def_call)
    contain = [a['player'] for a in roles if a['alignment'] in DR.EDGES
               or a['alignment'].startswith('offball_')]
    if contain:
        pursuit = float(np.mean([rate_fn(p, {'pursuit_rating': .4,
                    'play_rec_rating': .3, 'speed_rating': .3}) for p in contain]))
        choice *= float(np.clip(1. + 2. * (mobility - pursuit), .55, 1.2))
    choice *= float(np.clip(1. - .12 * (def_call.get('box', 7) - 6), .5, 1.15))
    if distance <= 3:
        choice *= 1.2
    if seconds is not None and seconds <= 120:
        choice *= .3 if margin <= 0 else .4
    elif seconds is not None and seconds <= 240 and margin > 0:
        choice *= .55
    if abs(margin) >= 17:
        choice *= .4
    choice *= float(np.clip((condition - 60.) / 35., 0., 1.))
    if healthy_backups < 1:
        choice *= .35
    return float(np.clip(choice, 0., .32))


def answer_empty_run(offense, call, yards_to_endzone, rng, rate_fn):
    """An empty package cannot hand off after the coach declines a QB keep."""
    if (call.get('is_pass') or call.get('sneak') or call.get('qb_run')
            or offense.get('rb') is not None):
        return False
    import playcall as PC
    import identity as ID
    down, distance = call.get('down', 1), call.get('ydstogo', 10)
    job = PC.pick_job(down, distance, yards_to_endzone,
                      call.get('score_diff', 0), call.get('seconds'), rng)
    # Keep the selected eleven and the defense's answer. This is a pass
    # audible, not a late substitution or a back invented by the resolver.
    concept = PC.call_pass(offense, job, rate_fn, rng,
                           allow_screen=down != 4 or distance <= 2)
    base = CONCEPTS[concept]['depth']
    mix = {'deep': (.26, .28, .46), 'medium': (.51, .42, .07),
           'short': (.86, .12, .02)}[base]
    mix = ID.situational_depth(mix, yards_to_endzone, down, distance)
    call.update(is_pass=True, qb_run=False, play_action=False, rpo=False,
                screen=concept == 'screen', concept=concept, job=job,
                depth=str(rng.choice(['short', 'medium', 'deep'], p=mix)),
                empty_run_audible=True)
    call.pop('scheme', None)
    call.pop('qb_run_chance', None)
    return True


def call_offense(down, ydstogo, score_diff, yards_to_endzone, rng, gm=None,
                 secs_left=None, offense=None, rate_fn=None, lean=None):
    """Full offensive call: personnel, formation, pass or run, and the concept.
    `lean` is the caller's identity from the plan: pass_bias (log-odds shift),
    play_action (share of dropbacks), motion (share of snaps)."""
    lean = lean or {}
    bias = (gm.aggression - 0.5) * 0.10 if gm is not None else 0.0
    bias += float(lean.get('pass_bias', 0.0))
    # WHO YOU HAVE DECIDES WHAT YOU CALL. Personnel used to be a flat random
    # draw, so a club with two excellent tight ends went 12 personnel exactly
    # as often as one with none, and a line that could maul people had no
    # effect on anything outside the play it was already in. Run and pass
    # blocking were rated and nothing read them.
    ident = None
    ident_run = ident_pass = None
    base = {k: v['rate'] for k, v in PERSONNEL_OFF.items()}
    preferred = lean.get('personnel_mix')
    if isinstance(preferred, dict):
        mix = {k: max(0.0, float(preferred.get(k, 0.0))) for k in base}
        if sum(mix.values()) > 0:
            base = mix
    if offense is not None and rate_fn is not None:
        import identity as ID
        ident = ID.read_identity(offense, rate_fn)
        import playcall as PC
        if not PC.SCHEME_BASE:
            PC.calibrate_baselines({'_': offense}, rate_fn)
        ident_run, ident_pass = PC.identity_plays(offense, rate_fn)
        base = ID.personnel_weights(ident, base)
        bias += ID.run_lean(ident)
    # the situation moves what the roster set, it does not replace it
    import identity as ID2
    base = ID2.situational_weights(base, down, ydstogo, yards_to_endzone,
                                   score_diff, secs_left)
    hl = float(lean.get('heavy_lean', 0.0) or 0.0)
    if hl:
        # the coordinator's halftime call on personnel: heavier groupings up (or down) by the lean
        for k in list(base):
            heavy = PERSONNEL_OFF.get(k, PERSONNEL_OFF['11'])['wr'] <= 2
            base[k] = max(0.005, base[k] * (np.exp(0.9 * hl) if heavy else np.exp(-0.9 * hl)))
    keys = list(base)
    w = np.array([base[k] for k in keys], float)
    pers = keys[int(rng.choice(len(keys), p=w / w.sum()))]
    import plays as _P
    pass_probability = pass_rate(down, ydstogo, score_diff,
                                 yards_to_endzone, pers, bias, secs_left)
    weather_run = _P.ENV.run_lean
    if down == 4 and ydstogo >= 5:
        # Weather can favor the surprise run without adding a flat run share
        # that overwhelms the conversion requirement.
        weather_run *= 4.0 * (1.0 - pass_probability)
    is_pass = rng.random() < pass_probability - weather_run
    shotgun = rng.random() < (0.82 if is_pass else 0.52)
    # The formation is a separate decision from the package: the same eleven
    # men produce a dozen looks, and that is where the variety comes from.
    import formations as FM
    form = FM.choose_formation(pers, rng, down=down, ydstogo=ydstogo,
                               score_diff=score_diff, secs_left=secs_left)
    call = dict(personnel=pers, shotgun=bool(shotgun), is_pass=bool(is_pass),
                formation=form, down=down, ydstogo=ydstogo,
                seconds=secs_left, score_diff=score_diff,
                qb_run_aggression=(float(gm.aggression) if gm is not None else .5),
                protection_pref=lean.get('protection'))
    # SHORT YARDAGE IS ITS OWN PACKAGE. On third and fourth and one, and on
    # second and one some of the time, the quarterback sneak is the call on
    # about 38% of runs league-wide (converting ~81% against ~68% for a
    # handoff); a club with the interior line and the quarterback for it
    # runs the push, which converts ~87%. The caller's heavy-personnel lean
    # nudges it; a spread club sneaks less.
    if not is_pass and ydstogo <= 1 and yards_to_endzone >= 1 and (down >= 3 or (down == 2 and rng.random() < 0.25)):
        p_sneak = 0.38 * (1.15 if str(lean.get('off_personnel', '11')) in ('12', '13', '21', '22') else 0.9)
        if rng.random() < p_sneak:
            call['sneak'] = True
            call['shotgun'] = False
            pers = pers if pers in ('12', '13', '21', '22') else '13'
            call['personnel'] = pers
            call['formation'] = FM.choose_formation(pers, rng, down=down, ydstogo=ydstogo,
                                                    score_diff=score_diff, secs_left=secs_left)

    if is_pass:
        # real rates: play action 10.2%, screen 4.4%, RPO 3.3%
        # Real rate is 10.2% of ALL plays (~17% of pass plays). The first build
        # gated it behind a shotgun check that eliminated 82% of chances and
        # produced 4%.
        # the caller's play-action lean scales the league rate (0.5 neutral):
        # a Shanahan-tree offence at 0.75 uses it about half again as often
        pa_scale = float(np.exp(1.2 * (float(lean.get('play_action', 0.5)) - 0.5)))
        # PLAY ACTION SELLS A RUN, so it lives where a run is a threat: first and second down at manageable
        # distance. Third or fourth and long draws no defender to the fake, and the last seconds of a half have
        # no fake in them. It had been drawn flat across every down and distance, so fourth and 34 with five
        # seconds left got a fake handoff as often as first and ten.
        if ydstogo >= 15: sit = 0.08
        elif down <= 1: sit = 1.0                                        # first down at any normal distance: the run is live
        elif down == 2: sit = 1.0 if ydstogo <= 7 else 0.6 if ydstogo <= 12 else 0.25
        else: sit = 1.0 if ydstogo <= 2 else 0.5 if ydstogo <= 4 else 0.25 if ydstogo <= 8 else 0.08
        if secs_left is not None and secs_left <= 20: sit = 0.0
        call['play_action'] = rng.random() < min(0.6, (0.37 if not shotgun else 0.175) * pa_scale * sit)
        # the designed screen: about 5.5% of throws league-wide, and a club's plan can add no more than three points
        # (a plan that stacked several screen calls had one club throwing a third of its passes on screens)
        screen_rate = 0.055 + float(np.clip(float(lean.get('screen_boost', 0.0) or 0.0), -0.03, 0.03))
        if down == 4:
            # Most fourth-down calls must reach the sticks through the air.
            # Keep an occasional short-yardage screen without treating a
            # five-yard conversion like an ordinary early-down opportunity.
            screen_rate *= (1.0 if ydstogo <= 2 else .4 if ydstogo <= 3
                            else .15 if ydstogo <= 7 else .05 if ydstogo < 15 else 0.)
        call['screen'] = rng.random() < screen_rate
        # The concept selector and pressure audibles share this decision.
        call['allow_screen'] = down != 4 or ydstogo <= 2 or call['screen']
        call['rpo'] = rng.random() < 0.057
        # THE CONCEPT IS A CALL, NOT A DRAW. It used to come off a flat
        # rng.choice inside a distance bucket, so a quarterback who could not
        # throw deep called four verticals as often as one who could. The job
        # comes from the situation; which concept does that job comes from
        # whether THIS passer can throw it.
        if call['screen']:
            call['concept'] = 'screen'
        elif offense is not None and rate_fn is not None:
            import playcall as PC
            job = PC.pick_job(down, ydstogo, yards_to_endzone, score_diff,
                              secs_left, rng)
            call['job'] = job
            call['concept'] = PC.call_pass(
                offense, job, rate_fn, rng,
                identity=(ident_pass if ident_pass else None),
                pressure_risk=(1.0 - (ident['pass_block'] if ident else 0.8)),
                allow_screen=call['allow_screen'])
        elif ydstogo >= 12 or (down >= 3 and ydstogo >= 8):
            call['concept'] = rng.choice(['four_verts', 'dagger', 'flood', 'levels', 'scissors'])
        elif ydstogo <= 4:
            call['concept'] = rng.choice(['slant_flat', 'stick', 'mesh', 'curl_flat'])
        else:
            call['concept'] = rng.choice(['mesh', 'levels', 'flood', 'smash', 'curl_flat',
                                          'dagger', 'slant_flat', 'stick'])
        # The CONCEPT sets the shape, but the QB still works a progression and
        # most throws come off the underneath option. Real depth mix is 61.9%
        # short, 23.7% medium, 14.4% deep; keying depth straight off the concept
        # gave 35/48/17 and cost ~10 points of league completion.
        base = CONCEPTS[call['concept']]['depth']
        mix = {'deep': (.26, .28, .46), 'medium': (.51, .42, .07),
               'short': (.86, .12, .02)}[base]
        import identity as ID3
        mix = ID3.situational_depth(mix, yards_to_endzone, down, ydstogo)
        call['depth'] = str(rng.choice(['short', 'medium', 'deep'], p=mix))
        # The existing under-center PA flood is a boot action. Mark the
        # intent without another random draw; the resolver rechecks it after
        # audibles and abandons movement for a hot answer.
        if call.get('play_action') and not shotgun and call['concept'] == 'flood':
            call['on_run'] = True
            call['qb_movement'] = 'boot'
    else:
        heavy = PERSONNEL_OFF[pers]['te'] >= 2 or PERSONNEL_OFF[pers]['rb'] >= 2
        if offense is not None and rate_fn is not None:
            # A POWER SCHEME IN FRONT OF A FINESSE LINE IS A BAD CALL however
            # good the scheme is. It used to be a flat draw from a distance
            # bucket, so every club ran the same things.
            import playcall as PC
            job = PC.pick_job(down, ydstogo, yards_to_endzone, score_diff,
                              secs_left, rng)
            call['job'] = job
            call['scheme'] = PC.call_run(offense, job, rate_fn, rng,
                                         identity=ident_run,
                                         family_mix=lean.get('run_scheme_mix'))
        elif yards_to_endzone <= 5 or (ydstogo <= 2 and down >= 3):
            call['scheme'] = rng.choice(['power', 'counter', 'duo', 'trap'])
        elif heavy:
            call['scheme'] = rng.choice(['power', 'counter', 'duo', 'inside_zone'])
        else:
            call['scheme'] = rng.choice(['inside_zone', 'outside_zone', 'stretch',
                                         'inside_zone', 'draw'])
    # the lean is centred on the identity catalog's average (0.58), so a league of real
    # coaches averages the real 36.5%; a club with no lean plays at the average
    mo_scale = float(np.exp(1.0 * (float(lean.get('motion', MOTION_NEUTRAL) or MOTION_NEUTRAL) - MOTION_NEUTRAL)))
    call['motion'] = rng.random() < min(0.75, 0.365 * mo_scale)
    # The neutral coach keeps the calibrated 8.5% rate. Faster and slower
    # coordinators move it, and the drive clock reads this choice.
    tempo = float(np.clip(lean.get('tempo', 0.5), 0.0, 1.0))
    protect_lead = score_diff > 0 and secs_left is not None and secs_left <= 240
    call['no_huddle'] = (not protect_lead and rng.random() <
                         float(np.clip(0.085 * np.exp(2.0 * (tempo - 0.5)), 0.01, 0.25)))
    return call

def call_defense(off_call, down, ydstogo, rng, gm=None, yards_to_endzone=50,
                 defense=None, rate_fn=None, score_diff=0, secs_left=None,
                 recent=None, lean=None):
    """
    Front, personnel, rushers and coverage.

    `lean` is the coordinator's identity from the game plan: coverage
    (zone..man), shell (single..two-high), blitz (0..1) and front_pref. It
    used to be applied AFTER this call by overwriting the shell, the man
    flag and the blitzers the call had chosen, which put the coverage call
    and the plan in disagreement on the same snap. Now it enters here and
    the call is made with it.
    """
    aggr = gm.aggression if gm is not None else 0.5
    decep = (gm.board_trust if gm is not None else 0.5)
    lean = lean or {}
    fp = lean.get('front_pref')
    pers = defensive_personnel(off_call['personnel'], down, ydstogo, rng, aggr, sub_lean=float(lean.get('sub_lean', 0.0) or 0.0))
    if pers == 'heavy':
        cands = [f for f in (fp or ()) if f in FRONTS and FRONTS[f]['dl'] == 5] or ['bear']
    else:
        # Standard nickel/dime use two interior defenders and both edges even
        # for odd-front coaches. Map installed odd base fronts to a truthful
        # four-man subfront; tite/mint retain their three interiors in Base.
        cands = []
        for f in (fp or ()):
            if f not in FRONTS or f == 'bear': continue
            selected = '3-4 sub' if pers in ('nickel', 'dime') and DR.front_family(f) == '3-4' else f
            if selected not in cands: cands.append(selected)
        if not cands:
            cands = ((['3-4 sub'] if pers in ('nickel', 'dime') else ['3-4 one', '3-4 two', 'tite', 'mint']) if DR.coach_front(gm) == '3-4'
                     else ['4-3 over', '4-3 under', 'wide 9'])
    # A multiple-front coordinator chooses from the installed fronts using
    # the offense's grouping and the situation. The defense has not seen the
    # actual run/pass call, so this uses only information it could know.
    off_spec = PERSONNEL_OFF.get(off_call['personnel'], PERSONNEL_OFF['11'])
    run_threat = float(np.clip(.46 + .5 * off_spec['run_bias']
                               + (.16 if ydstogo <= 2 else -.10 if ydstogo >= 8 and down >= 3 else 0.0)
                               + (.12 if yards_to_endzone <= 5 else 0.0), .18, .82))
    front_scores = np.array([run_threat * FRONTS[f]['run_fit']
                             + (1.0 - run_threat) * FRONTS[f]['rush'] for f in cands], float)
    front_weights = np.exp(12.0 * (front_scores - front_scores.max()))
    front = str(rng.choice(cands, p=front_weights / front_weights.sum()))
    if pers == 'heavy':
        # Bear is the five-man goal-line alignment for either coaching family.
        # A caller may supply an installed front list without a GM object.
        installed = next((DR.front_family(f) for f in (fp or ())
                          if f in FRONTS and f != 'bear'), None)
        family = DR.coach_front(gm) if gm is not None else installed or DR.front_family(front)
    else:
        family = DR.front_family(front)

    # real: 0 blitzers 86.7%, 1 on 9.7%, 2 on 3.1%, 3 on 0.47%
    r = rng.random()
    # the coordinator's blitz lean scales the league rate: 0.35 is neutral,
    # Flores at 1.0 blitzes about two and a half times the league
    bl = float(lean.get('blitz', BLITZ_NEUTRAL))
    # centred on the catalog's average lean (0.38) so a league of real coaches lands on
    # the real 13.3% with the fire zones and cover 0 the coverage call brings; before
    # this the franchise blitzed at 19% while the random-coach register sat at 16
    p_blitz = BLITZ_BASE * (0.6 + 0.9 * aggr) * float(np.exp(1.6 * (bl - BLITZ_NEUTRAL)))
    if down == 3 and ydstogo >= 6: p_blitz *= 1.35
    if r < p_blitz * 0.73:   blitzers = 1
    elif r < p_blitz * 0.96: blitzers = 2
    elif r < p_blitz:        blitzers = 3
    else:                    blitzers = 0
    # A five-man rush is NOT always a blitz: an end drops and a linebacker
    # comes, which charts as 4 rushers + 0 blitzers or 5 + 0 depending on the
    # look. Real share of pass plays is 19.9% at five rushers but only 9.7%
    # have a charted blitzer. Tying rushers strictly to blitzers put five-man
    # rushes at 8% against a real 20%.
    rushers = 4 + blitzers
    if blitzers == 0:
        r2 = rng.random()
        if r2 < 0.042: rushers = 3
        elif r2 < 0.165: rushers = 5          # exchange rusher, not a blitz
        elif r2 < 0.195: rushers = 6

    sim = simulated_pressure(rng, decep)
    if sim['sim']: rushers, blitzers = 4, 0
    box = box_count(pers, front, off_call['personnel'], blitzers, rng, yards_to_endzone)
    # rushers tick up near the goal line too: 4.68 inside the 5 vs 4.30 at 21-50
    if yards_to_endzone <= 5 and blitzers == 0 and rng.random() < 0.28:
        rushers += 1; blitzers = 1
    # THE COVERAGE CALL. The shell above is the deep structure; this decides
    # what happens underneath it, which can differ by side of the field. It is
    # chosen by JOB - what the call has to do in this situation - and then by
    # whether the personnel can actually run it.
    cov = None
    if defense is not None and rate_fn is not None:
        import coverage_call as CC
        cov = CC.call_coverage(down, ydstogo, score_diff, secs_left,
                               off_call['personnel'], defense, rate_fn, rng,
                               aggression=aggr, recent=recent, lean=lean)
        rushers += cov['rush_bonus']
        if cov['rush_bonus']:
            blitzers = max(blitzers, cov['rush_bonus'])
        # The coverage call supplies the shell; do not draw and discard a
        # second shell before this roster-aware call.
        shell = CC.SHELL_OF[cov['coverage']]
    elif blitzers >= 2:
        shell = rng.choice(['cover_0', 'cover_1', 'cover_3'], p=[.25, .45, .30])
    elif blitzers == 1:
        shell = rng.choice(['cover_1', 'cover_3', 'cover_2'], p=[.40, .40, .20])
    else:
        shell = rng.choice(['cover_3', 'cover_2', 'cover_4', 'cover_1',
                            'tampa_2', 'cover_6'], p=[.30, .18, .22, .15, .08, .07])
    shown, actual, fooled = disguise(shell, decep, rng)

    under = cov['under'] if cov else ('man' if actual in ('cover_0', 'cover_1')
                                      else 'zone')
    return dict(personnel=pers, front=front, front_family=family,
                rushers=rushers, blitzers=blitzers,
                shell=actual, shown_shell=shown, fooled=fooled, box=box,
                sim_pressure=sim['sim'], protection_error=sim['protection_error'],
                coverage=(cov['coverage'] if cov else actual),
                job=(cov['job'] if cov else None),
                under=under,
                # kept so anything still reading the old flag keeps working
                man=(under == 'man'))

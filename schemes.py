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
# defence answers personnel. Nickel is now the base defence in the NFL.
PERSONNEL_DEF = {
    'base':   dict(db=4, lb=3, dl=4, box_bonus=+1.0, cover_penalty=0.10),
    'nickel': dict(db=5, lb=2, dl=4, box_bonus= 0.0, cover_penalty=0.00),
    'dime':   dict(db=6, lb=1, dl=4, box_bonus=-1.0, cover_penalty=-0.06),
    'heavy':  dict(db=3, lb=4, dl=5, box_bonus=+2.0, cover_penalty=0.22),
}

def defensive_personnel(off_pers, down, ydstogo, rng, gm_aggr=0.5):
    """What the defence puts on the field to answer the offence's grouping."""
    wr = PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])['wr']
    if wr >= 4:  base = 'dime' if (down == 3 and ydstogo >= 7) else 'nickel'
    elif wr == 3: base = 'nickel'
    elif wr == 2: base = 'base' if rng.random() < 0.55 else 'nickel'
    else:         base = 'heavy' if rng.random() < 0.50 else 'base'
    if down == 3 and ydstogo >= 8 and base in ('base', 'nickel'):
        base = 'nickel' if base == 'base' else 'dime'
    if down in (3, 4) and ydstogo <= 2 and base == 'nickel':
        base = 'base' if rng.random() < 0.6 else 'nickel'
    return base

# ============================================================ FRONTS
# One-gap penetrates; two-gap occupies to free linebackers. These are different
# JOBS for the same body, and a single "defensive line" number cannot express it.
FRONTS = {
    '4-3 over':  dict(dl=4, gap='one', edge_set='strong', run_fit=1.00, rush=1.00),
    '4-3 under': dict(dl=4, gap='one', edge_set='weak',   run_fit=1.02, rush=0.98),
    '3-4 one':   dict(dl=3, gap='one', edge_set='both',   run_fit=0.96, rush=1.04),
    '3-4 two':   dict(dl=3, gap='two', edge_set='both',   run_fit=1.06, rush=0.90),
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
    b = FRONTS[front]['dl'] * 0.74 + PERSONNEL_DEF[def_pers]['lb'] * 0.62
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
    The raw ratio is applied to YARDS BEFORE CONTACT only, and the break-tackle
    chain then compresses it, so the ratio is exponentiated to survive that.
    Without it the sim spread only 5.51 to 3.72 against a real 5.92 to 2.41.
    """
    return (BOX_YPC.get(int(np.clip(box, 4, 10)), 4.5) / BOX_YPC[6]) ** 2.1

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

def choose_protection(off_pers, expected_rush, depth, rng, gm_aggr=0.5):
    """Longer-developing concepts need more bodies; quick game needs fewer."""
    avail = PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])['protect']
    if depth == 'short' and rng.random() < 0.55:
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
SHELL_KEY = {'cover_0': 'man', 'cover_1': 'man', 'man': 'man',
             'cover_2': 'cover_2', 'tampa_2': 'cover_2',
             'cover_3': 'cover_3', 'cover_6': 'cover_3',
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

def pass_rate(down, ydstogo, score_diff, yards_to_endzone, off_pers,
              gm_pass_bias=0.0, secs_left=None):
    """
    Share of snaps thrown.

    THE SCORE TABLE BELOW HAS NO CLOCK IN IT, and the clock is most of the
    effect. Real pass rate barely moves before halftime whatever the score -
    everything sits in a 55-69% band - and then goes nearly binary at the end:
    90% throwing down 9-16 in the last four minutes against 13% running it out
    up 9-16. Without that, a trailing team never accelerates and a leading one
    never bleeds clock, so games never close up and never run away in the way
    real ones do. Close games (1-7 points) were 31% of ours against a real
    46.8%.
    """
    base = PASS_RATE.get(int(down), PASS_RATE[1])[dist_band(ydstogo)]
    # Scores are whole numbers again now that the try is resolved as its own
    # play. The round stays as a guard on any caller passing a float.
    sd = int(round(score_diff))
    script = next((v for lo, hi, v in SCRIPT if lo <= sd <= hi), NEUTRAL_SCRIPT)
    base *= script / NEUTRAL_SCRIPT
    # the red zone compresses: inside the 5 it is 44.5% pass against 59.7% backed up
    if yards_to_endzone <= 5:  base *= 0.75
    elif yards_to_endzone <= 10: base *= 0.88
    elif yards_to_endzone <= 20: base *= 0.90
    base += PERSONNEL_OFF.get(off_pers, PERSONNEL_OFF['11'])['run_bias'] * -0.30
    if secs_left is not None:
        # Blend toward the measured late-game rate, hard at the very end.
        import decisions as DEC
        target = DEC.pass_rate(score_diff, secs_left)
        w = 0.0 if secs_left > 1800 else (0.25 if secs_left > 900 else
                                          (0.55 if secs_left > 240 else 0.85))
        base = (1.0 - w) * base + w * target * (base / max(NEUTRAL_SCRIPT, .01)
                                                if False else 1.0)
    return float(np.clip(base + gm_pass_bias, 0.03, 0.98))

def call_offense(down, ydstogo, score_diff, yards_to_endzone, rng, gm=None,
                 secs_left=None):
    """Full offensive call: personnel, formation, pass or run, and the concept."""
    bias = (gm.aggression - 0.5) * 0.10 if gm is not None else 0.0
    pers = rng.choice(list(PERSONNEL_OFF),
                      p=np.array([v['rate'] for v in PERSONNEL_OFF.values()]) /
                        sum(v['rate'] for v in PERSONNEL_OFF.values()))
    is_pass = rng.random() < pass_rate(down, ydstogo, score_diff,
                                       yards_to_endzone, pers, bias, secs_left)
    shotgun = rng.random() < (0.82 if is_pass else 0.52)
    # The formation is a separate decision from the package: the same eleven
    # men produce a dozen looks, and that is where the variety comes from.
    import formations as FM
    form = FM.choose_formation(pers, rng, down=down, ydstogo=ydstogo,
                               score_diff=score_diff, secs_left=secs_left)
    call = dict(personnel=pers, shotgun=bool(shotgun), is_pass=bool(is_pass),
                formation=form, down=down, ydstogo=ydstogo)

    if is_pass:
        # real rates: play action 10.2%, screen 4.4%, RPO 3.3%
        # Real rate is 10.2% of ALL plays (~17% of pass plays). The first build
        # gated it behind a shotgun check that eliminated 82% of chances and
        # produced 4%.
        call['play_action'] = rng.random() < (0.30 if not shotgun else 0.14)
        call['screen'] = rng.random() < 0.075
        call['rpo'] = rng.random() < 0.057
        if call['screen']:
            call['concept'] = 'screen'
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
        r = rng.random()
        if base == 'deep':     call['depth'] = 'deep' if r < .46 else ('medium' if r < .74 else 'short')
        elif base == 'medium': call['depth'] = 'medium' if r < .42 else ('short' if r < .93 else 'deep')
        else:                  call['depth'] = 'short' if r < .86 else ('medium' if r < .98 else 'deep')
    else:
        heavy = PERSONNEL_OFF[pers]['te'] >= 2 or PERSONNEL_OFF[pers]['rb'] >= 2
        if yards_to_endzone <= 5 or (ydstogo <= 2 and down >= 3):
            call['scheme'] = rng.choice(['power', 'counter', 'duo', 'trap'])
        elif heavy:
            call['scheme'] = rng.choice(['power', 'counter', 'duo', 'inside_zone'])
        else:
            call['scheme'] = rng.choice(['inside_zone', 'outside_zone', 'stretch',
                                         'inside_zone', 'draw'])
    call['motion'] = rng.random() < 0.365
    call['no_huddle'] = rng.random() < 0.085
    return call

def call_defense(off_call, down, ydstogo, rng, gm=None, yards_to_endzone=50,
                 defense=None, rate_fn=None, score_diff=0, secs_left=None,
                 recent=None):
    """Front, personnel, rushers and coverage."""
    aggr = gm.aggression if gm is not None else 0.5
    decep = (gm.board_trust if gm is not None else 0.5)
    pers = defensive_personnel(off_call['personnel'], down, ydstogo, rng, aggr)
    dl = PERSONNEL_DEF[pers]['dl']
    front = rng.choice(['4-3 over', '4-3 under', 'nickel_even'] if dl == 4 else
                       ['3-4 one', '3-4 two', 'tite', 'mint'])
    if front == 'nickel_even': front = '4-3 over'

    # real: 0 blitzers 86.7%, 1 on 9.7%, 2 on 3.1%, 3 on 0.47%
    r = rng.random()
    p_blitz = 0.133 * (0.6 + 0.9 * aggr)
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

    if blitzers >= 2:
        shell = rng.choice(['cover_0', 'cover_1', 'cover_3'], p=[.25, .45, .30])
    elif blitzers == 1:
        shell = rng.choice(['cover_1', 'cover_3', 'cover_2'], p=[.40, .40, .20])
    else:
        shell = rng.choice(['cover_3', 'cover_2', 'cover_4', 'cover_1',
                            'tampa_2', 'cover_6'], p=[.30, .18, .22, .15, .08, .07])

    sim = simulated_pressure(rng, decep)
    if sim['sim']: rushers, blitzers = 4, 0
    shown, actual, fooled = disguise(shell, decep, rng)
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
                               aggression=aggr, recent=recent)
        rushers += cov['rush_bonus']
        if cov['rush_bonus']:
            blitzers = max(blitzers, cov['rush_bonus'])

    under = cov['under'] if cov else ('man' if actual in ('cover_0', 'cover_1')
                                      else 'zone')
    return dict(personnel=pers, front=front, rushers=rushers, blitzers=blitzers,
                shell=actual, shown_shell=shown, fooled=fooled, box=box,
                sim_pressure=sim['sim'], protection_error=sim['protection_error'],
                coverage=(cov['coverage'] if cov else actual),
                job=(cov['job'] if cov else None),
                under=under,
                # kept so anything still reading the old flag keeps working
                man=(under == 'man'))

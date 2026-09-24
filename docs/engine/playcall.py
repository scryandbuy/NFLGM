"""
THE OFFENSIVE PLAY CALL.

The playbook already existed and was already good - eight run schemes split
between gap and zone, twelve pass concepts each carrying a multiplier against
every coverage. What did not exist was anybody choosing between them on
purpose. The concept was drawn from a flat list, so a club with a
power-blocking line called stretch as often as duo, and a quarterback who
could not throw deep called four verticals as often as anyone.

This mirrors the defensive call, because the reasoning is the same shape:

    THE SITUATION PICKS THE JOB. What does this snap have to do - move the
    chains, take a shot, bleed clock, get one yard.
    THE PERSONNEL PICKS THE PLAY. Which of the plays that do that job can
    THESE men actually run.

Two ideas from how coaches talk that are not in any chart:

    AN IDENTITY PLAY. "You need an identity play which you can always run
    against anyone and anything. Too many offenses do not have an identity.
    They have a collection of plays." So each club has one run and one pass
    concept it comes back to, drawn from what its roster is best at, and it
    shows up more than the maths alone would justify.

    THINK PLAYERS, NOT PLAYS. "When the game is on the line you need to get
    the ball to your dudes." Late and close, the call tilts toward whatever
    gets the ball to the best man on the field rather than toward the highest
    expected value.

The concept multipliers against coverage are NOT read here on purpose. The
offence does not know the coverage when it calls the play - that is what the
quarterback's read at the line is for, and it comes later.
"""
import numpy as np

import schemes as S

# ---------------------------------------------------------------- jobs
# what a snap has to do, and which plays do it
RUN_FOR = {
    'short_yardage': ['power', 'duo', 'counter', 'trap'],
    'chains':        ['inside_zone', 'outside_zone', 'duo', 'counter'],
    'clock':         ['inside_zone', 'duo', 'power', 'stretch'],
    # draw is a CHANGE-UP, not an explosive call - it belongs where the
    # defence is expecting a throw, which is third and long.
    'explosive':     ['outside_zone', 'stretch', 'counter'],
}
# THE INTERMEDIATE THROW HAS TO LIVE SOMEWHERE. The first build put every
# medium concept in the explosive pool only, so 'chains' - by far the most
# common job - was entirely short routes. The depth mix came out 85% short
# against a real 61.9%, which dragged air yards to 4.55 against 5.72 and took
# the whole passing game down with it. On second and seven a real offence
# throws an intermediate route; it does not check the ball down or take a shot.
PASS_FOR = {
    'short_yardage': ['slant_flat', 'stick', 'mesh', 'smash'],
    'chains':        ['curl_flat', 'stick', 'levels', 'mesh', 'slant_flat',
                      'flood', 'dagger', 'smash'],
    'explosive':     ['four_verts', 'go', 'dagger', 'scissors', 'flood'],
    'protect':       ['screen', 'slant_flat', 'stick'],   # get it out fast
    'clock':         ['curl_flat', 'stick', 'flood'],
}

# what each run scheme asks of the men blocking it
SCHEME_WANTS = {
    'power':  {'run_block_power_rating': .55, 'strength_rating': .45},
    'duo':    {'run_block_power_rating': .55, 'strength_rating': .45},
    'counter': {'run_block_power_rating': .45, 'agility_rating': .30,
                'awareness_rating': .25},
    'trap':   {'run_block_finesse_rating': .40, 'agility_rating': .35,
               'awareness_rating': .25},
    'inside_zone':  {'run_block_finesse_rating': .50, 'agility_rating': .30,
                     'awareness_rating': .20},
    'outside_zone': {'run_block_finesse_rating': .45, 'agility_rating': .40,
                     'speed_rating': .15},
    'stretch': {'run_block_finesse_rating': .40, 'agility_rating': .35,
                'speed_rating': .25},
    'draw':   {'pass_block_rating': .50, 'awareness_rating': .50},
}

# what a pass concept asks of the quarterback throwing it
CONCEPT_WANTS = {
    'deep':   {'throw_acc_deep_rating': .45, 'throw_power_rating': .35,
               'awareness_rating': .20},
    'medium': {'throw_acc_mid_rating': .50, 'awareness_rating': .30,
               'throw_under_pressure_rating': .20},
    'short':  {'throw_acc_short_rating': .50, 'awareness_rating': .35,
               'play_action_rating': .15},
}


# League means, so a scheme is judged against how lines generally block it
# rather than against the other schemes on its own scale.
SCHEME_BASE = {}
DEPTH_BASE = {}


def calibrate_baselines(league, rate_fn):
    """Work out what an average line and an average quarterback look like."""
    import numpy as _np
    for s, w in SCHEME_WANTS.items():
        vals = []
        for t in league.values():
            ol = (t.get('ol') or [])[:5]
            if ol:
                vals.append(_np.mean([rate_fn(m, w) for m in ol]))
        SCHEME_BASE[s] = float(_np.mean(vals)) if vals else 0.7
    for d, w in CONCEPT_WANTS.items():
        vals = [rate_fn(t['qb'], w) for t in league.values() if t.get('qb')]
        DEPTH_BASE[d] = float(_np.mean(vals)) if vals else 0.7


def pick_job(down, ydstogo, yards_to_endzone, score_diff, secs_left, rng):
    """What this snap has to do."""
    late = secs_left is not None and secs_left <= 300
    if ydstogo <= 2 or yards_to_endzone <= 3:
        return 'short_yardage'
    if late and score_diff > 0:
        return 'clock'
    if late and score_diff < -8:
        return 'explosive'
    if down >= 3 and ydstogo >= 8:
        return 'explosive' if rng.random() < 0.42 else 'chains'
    if down >= 3:
        return 'chains'
    # Shots come on early downs, when the defence is not expecting one. At an
    # 18% rate the deep concepts came out at 9% of throws against a real 14%.
    if rng.random() < 0.28:
        return 'explosive'
    return 'chains'


def identity_plays(off, rate_fn):
    """
    The run and the pass this club comes back to, from what it does best.

    Not a preference - an identity. It is picked once from the roster and it
    shows up more often than the maths alone would justify, because that is
    what having an identity means.
    """
    ol = (off.get('ol') or [])[:5]
    if not ol:
        return 'inside_zone', 'curl_flat'
    # RELATIVE, NOT ABSOLUTE. Scoring each scheme on its own scale made every
    # club in the league pick power, because power asks for two attributes and
    # the zone schemes ask for three - so the average came out higher for
    # power on ANY line. The question is not which scheme scores highest, it
    # is which scheme THIS line is better at than lines generally are.
    run = max(SCHEME_WANTS, key=lambda s: (
        float(np.mean([rate_fn(m, SCHEME_WANTS[s]) for m in ol]))
        - SCHEME_BASE[s]))
    qb = off.get('qb')
    if qb is None:
        return run, 'curl_flat'
    depth = max(CONCEPT_WANTS,
                key=lambda d: rate_fn(qb, CONCEPT_WANTS[d]) - DEPTH_BASE[d])
    pool = [c for c, v in S.CONCEPTS.items() if v['depth'] == depth]
    best = max(pool, key=lambda c: S.CONCEPTS[c]['n']) if pool else 'curl_flat'
    return run, best


def call_run(off, job, rate_fn, rng, identity=None, box=6):
    """
    Which run, judged by whether THESE linemen can block it.

    A power scheme in front of a finesse line is a bad call however good the
    scheme is, and that is the whole point of reading the roster.
    """
    pool = list(RUN_FOR.get(job, RUN_FOR['chains']))
    if job == 'explosive' and rng.random() < 0.22:
        pool.append('draw')        # the change-up, occasionally
    ol = (off.get('ol') or [])[:5]
    if not ol:
        return pool[0]
    fit = np.array([float(np.mean([rate_fn(m, SCHEME_WANTS[s]) for m in ol]))
                    - SCHEME_BASE[s] for s in pool])
    w = np.exp((fit - fit.max()) / 0.045)
    if identity and identity in pool:
        w[pool.index(identity)] *= 1.8
    if box >= 8:
        # a loaded box makes a gap scheme harder, not easier
        w = w * np.array([0.82 if S.RUN_SCHEMES[s]['family'] == 'gap' else 1.12
                          for s in pool])
    return pool[int(rng.choice(len(pool), p=w / w.sum()))]


def call_pass(off, job, rate_fn, rng, identity=None, pressure_risk=0.5):
    """
    Which concept, judged by whether THIS quarterback can throw it.

    A club whose protection is poor leans on what gets the ball out, which is
    the same reasoning as a defence with bad corners leaning on the fire zone.
    """
    pool = list(PASS_FOR.get(job, PASS_FOR['chains']))
    if pressure_risk > 0.62:
        pool += PASS_FOR['protect']
    qb = off.get('qb')
    if qb is None:
        return pool[0]
    fit = np.array([rate_fn(qb, CONCEPT_WANTS[S.CONCEPTS[c]['depth']])
                    - DEPTH_BASE[S.CONCEPTS[c]['depth']] for c in pool])
    # A gentler temperature here on purpose: a quarterback's short accuracy is
    # nearly always his best number, so a sharp weighting made every passer in
    # the league throw short whatever the call was for.
    w = np.exp((fit - fit.max()) / 0.10)
    if identity and identity in pool:
        w[pool.index(identity)] *= 1.7
    return pool[int(rng.choice(len(pool), p=w / w.sum()))]


def best_target(off, rate_fn):
    """
    The man you want the ball going to when it matters. Think players, not
    plays.
    """
    men = [m for m in (off.get('wr') or []) if m]
    if not men:
        return None
    return max(men, key=lambda m: rate_fn(
        m, {'catch_rating': .30, 'route_run_med_rating': .30,
            'speed_rating': .20, 'spec_catch_rating': .20}))


if __name__ == '__main__':
    import collections
    import rosters as R, plays as P
    rng = np.random.default_rng(3)
    L = R.load_league()
    calibrate_baselines(L, P.rate)
    print('IDENTITY PLAY, by roster')
    for t in ('MIA', 'CIN', 'PHI', 'BAL', 'SF'):
        r, p = identity_plays(L[t], P.rate)
        print('   %-4s run %-14s pass %s' % (t, r, p))
    print('\nWHICH RUN, BY JOB (PHI)')
    off = L['PHI']
    ident_r, ident_p = identity_plays(off, P.rate)
    for job in ('short_yardage', 'chains', 'explosive', 'clock'):
        c = collections.Counter(call_run(off, job, P.rate, rng, ident_r)
                                for _ in range(400))
        print('   %-14s %s' % (job, ', '.join(
            f'{k} {100*v/400:.0f}%' for k, v in c.most_common(3))))
    print('\nWHICH PASS, BY JOB (PHI)')
    for job in ('short_yardage', 'chains', 'explosive'):
        c = collections.Counter(call_pass(off, job, P.rate, rng, ident_p)
                                for _ in range(400))
        print('   %-14s %s' % (job, ', '.join(
            f'{k} {100*v/400:.0f}%' for k, v in c.most_common(3))))
    print('\nSAME JOB, DIFFERENT LINES - chains')
    for t in ('MIA', 'CIN', 'SF'):
        ir, _ = identity_plays(L[t], P.rate)
        c = collections.Counter(call_run(L[t], 'chains', P.rate, rng, ir)
                                for _ in range(400))
        print('   %-4s %s' % (t, ', '.join(
            f'{k} {100*v/400:.0f}%' for k, v in c.most_common(3))))


# ============================================================ THE AUDIBLE
# He MODIFIES the call, he does not make a new one. That is the whole design:
# an audible swaps the run for a pass, or a deep concept for a quick one, or
# the protection - it does not go back to the call sheet and start again. A
# quarterback who could re-call the play from scratch would beat every defence
# every time, which is not the game.
#
# AND HE CAN BE WRONG. He reads the look the defence is SHOWING, not the one
# it is playing, so a disguised coverage sells him a picture that is not there
# and he checks into something worse. That is what disguise is FOR, and it is
# why the engine already carries a shown shell and an actual one.

# What a quarterback is allowed to change, in order of how common it is.
AUDIBLE_KINDS = ('run_to_pass', 'pass_to_run', 'depth', 'protect')


def read_the_look(def_call):
    """
    What the quarterback SEES. The shown shell and the box, not the truth.

    A defence that disguises well shows him one thing and plays another; his
    audible is only as good as the picture he was sold.
    """
    shown = def_call.get('shown_shell') or def_call.get('shell')
    box = def_call.get('box', 6)
    return dict(shell=shown, box=box,
                looks_light=box <= 5, looks_heavy=box >= 7,
                looks_man=shown in ('cover_0', 'cover_1'),
                lying=bool(def_call.get('fooled')))


def audible(off_call, def_call, off, rate_fn, rng, latitude=None):
    """
    Change the call at the line, or leave it alone.

    Returns (call, what_he_did). `what_he_did` is None when he ran the play as
    given, which is most of the time even for a good passer.
    """
    if latitude is None:
        import identity as ID
        latitude = ID.qb_latitude(off, rate_fn)
    if latitude <= 0.01 or rng.random() > latitude * AUDIBLE_RATE:
        return off_call, None

    look = read_the_look(def_call)
    call = dict(off_call)

    # ---- the reads, in the order a quarterback actually makes them ----
    if not call.get('is_pass') and look['looks_heavy']:
        # they have loaded the box against a run - get out of it
        call['is_pass'] = True
        call['concept'] = call_pass(off, 'chains', rate_fn, rng)
        call.pop('scheme', None)
        return call, 'run_to_pass'
    if call.get('is_pass') and look['looks_light']:
        # light box against a pass - take the run they are giving
        call['is_pass'] = False
        call['scheme'] = call_run(off, 'chains', rate_fn, rng,
                                  box=look['box'])
        call.pop('concept', None)
        return call, 'pass_to_run'
    if call.get('is_pass') and look['looks_man']:
        # man coverage: he wants something that beats it one on one
        call['concept'] = call_pass(off, 'explosive', rate_fn, rng)
        return call, 'depth'
    if call.get('is_pass') and look['looks_heavy']:
        # pressure showing - get the ball out
        call['concept'] = call_pass(off, 'protect', rate_fn, rng)
        return call, 'protect'
    return off_call, None


# How often a quarterback with full latitude changes the call. Real audible
# rates are not published per play, but a quarterback does not check out of
# most snaps - the call sheet is usually right.
AUDIBLE_RATE = 0.38

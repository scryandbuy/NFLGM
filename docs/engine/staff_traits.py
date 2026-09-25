"""
staff_traits.py - what a coach or a head scout is like, in words the GM can act on.

Players carry four hidden dials (personality.py). Staff carry TRAITS: a coach has none,
one or two of nine, a scout one or two drawn from six opposed pairs. Three of the coach
traits (Mercenary, Loyal, Climber) describe what he wants from the club and are read off
the hidden dials the poach and re-sign code already uses, so that behavior is unchanged
and the label is now honest. The other six coach traits and every scout trait are new
draws and hook into the engine in their own modules (progression, the game, free agency,
the opponent report, scouting).

Visibility: a man in the pool shows only how many traits he has; the interview reveals
them one at a time. The moment he is yours, everything shows.
"""
import numpy as np

# ------------------------------------------------------------ the coach's nine
COACH = {
    'mercenary':      dict(name='Mercenary',       fam='want',  tip='Asks above the market. A raise is what keeps him; without it he leaves when another club calls.'),
    'loyal':          dict(name='Loyal',           fam='want',  tip='Re-signs when his deal is up and leans toward staying when a head-coaching job calls.'),
    'climber':        dict(name='Climber',         fam='want',  tip='Wants a head-coaching job and will take the first real one. Persuading him to stay is a long shot.'),
    'teacher':        dict(name='Teacher',         fam='coach', tip='Players on his side of the ball earn more XP each week.'),
    'developer':      dict(name='Developer',       fam='coach', tip='Players 24 and under on his side earn more XP; veterans get nothing extra.'),
    'disciplinarian': dict(name='Disciplinarian',  fam='coach', tip='Fewer penalties and turnovers for his unit. The ambitious men on his side chafe a little.'),
    'recruiter':      dict(name='Recruiter',       fam='coach', tip='Free agents at his unit\'s positions want to sign here and ask a little less.'),
    'sharp':          dict(name='Sharp on Sunday', fam='coach', tip='His game-week read is better and his unit plays a touch above its rating on Sunday.'),
    'riser':          dict(name='Riser',           fam='coach', tip='His rating and prestige grow faster year over year.'),
}
COACH_EXCLUSIVE = [('loyal', 'climber'), ('teacher', 'developer'), ('mercenary', 'loyal')]

# ------------------------------------------------------------ the scout's six pairs (positive, negative)
SCOUT = {
    'eye':          dict(name='Eye for Talent',        fam='pos', pair='skill',     tip='His first read on a prospect\'s skill is tighter than his rating alone would give.'),
    'wants':        dict(name='Sees What He Wants',    fam='neg', pair='skill',     tip='Skill reads are wider and lean high on players he likes.'),
    'stopwatch':    dict(name='Stopwatch',             fam='pos', pair='phys',      tip='Physical reads are tight: speed, size, the combine numbers. He does not miss on a forty.'),
    'measurables':  dict(name='Fooled by Measurables', fam='neg', pair='phys',      tip='Physical reads run high on athletes, so a workout warrior grades better than he is.'),
    'projector':    dict(name='Projector',             fam='pos', pair='ceiling',   tip='The ceiling range is narrower; he knows how far a man can grow.'),
    'floor':        dict(name='Sees the Floor',        fam='neg', pair='ceiling',   tip='The ceiling range is wide and low; he undersells development and steers you to safe picks.'),
    'small_school': dict(name='Small-School Eye',      fam='pos', pair='school',    tip='Prospects outside the power conferences carry no extra error in his room.'),
    'big_program':  dict(name='Big-Program Bias',      fam='neg', pair='school',    tip='Small-school reads are wider still, and power-conference players grade a point or two high.'),
    'character':    dict(name='Character Judge',       fam='pos', pair='character', tip='The visit\'s character read is reliable; his flags are rarely wrong.'),
    'tape':         dict(name='Trusts the Tape',       fam='neg', pair='character', tip='He skips the character read. Visits sharpen the ratings but never produce a flag.'),
    'grinder':      dict(name='Grinder',               fam='pos', pair='looks',     tip='More looks a season; more prospects reach a second read without a visit.'),
    'narrow':       dict(name='Narrow Board',          fam='neg', pair='looks',     tip='His room truly scouts the first three rounds; day-three reads stay as wide as the first look.'),
}

ALL = dict(COACH, **SCOUT)


def name(key): return ALL[key]['name']
def tip(key): return ALL[key]['tip']


# ------------------------------------------------------------ the draw
def _want_traits(dials):
    """Mercenary / Loyal / Climber from the hidden dials the poach and re-sign code reads."""
    money = float(dials.get('financial_priority', 50)); loy = float(dials.get('loyalty', 50)); amb = float(dials.get('ambition', 50))
    out = []
    if amb >= 62 and loy < 55: out.append('climber')
    elif loy >= 65 and amb < 55: out.append('loyal')
    if money >= 64 and 'loyal' not in out: out.append('mercenary')
    return out


def draw_coach(rng, dials, age):
    """One or two traits, sometimes none. The want traits come from the dials; the coaching
    traits are drawn, with the exclusions honored and Riser kept to the young."""
    out = _want_traits(dials)
    pool = ['teacher', 'developer', 'disciplinarian', 'recruiter', 'sharp', 'riser']
    weights = np.array([1.0, 0.8, 0.9, 0.8, 0.9, (1.2 if age <= 45 else 0.5 if age <= 55 else 0.0)])
    n_coach = int(rng.choice([0, 1, 2], p=[0.28, 0.52, 0.20]))
    for _ in range(n_coach):
        w = weights.copy()
        for k in list(out):
            for a, b in COACH_EXCLUSIVE:
                if k == a and b in pool: w[pool.index(b)] = 0.0
                if k == b and a in pool: w[pool.index(a)] = 0.0
        for k in out:
            if k in pool: w[pool.index(k)] = 0.0
        if w.sum() <= 0: break
        out.append(str(rng.choice(pool, p=w / w.sum())))
    return out[:3]


def draw_scout(rng):
    """One or two, from different pairs; the two sides of a pair never land together. When
    two land, they are one positive and one negative about 60% of the time."""
    pairs = ['skill', 'phys', 'ceiling', 'school', 'character', 'looks']
    n = int(rng.choice([1, 2], p=[0.45, 0.55]))
    chosen = list(rng.choice(pairs, size=n, replace=False))
    out = []
    if n == 2 and rng.random() < 0.60:
        signs = ['pos', 'neg']; rng.shuffle(signs)
    else:
        signs = [str(rng.choice(['pos', 'neg'], p=[0.6, 0.4])) for _ in chosen]
    for pair, sign in zip(chosen, signs):
        out.append(next(k for k, v in SCOUT.items() if v['pair'] == pair and v['fam'] == sign))
    return out


def ensure(coach, rng):
    """A coach or scout gets his traits the first time anyone asks; men from older saves included."""
    if getattr(coach, 'staff_traits', None) is None:
        if coach.role == 'scout': coach.staff_traits = draw_scout(rng)
        else: coach.staff_traits = draw_coach(rng, coach.traits or {}, int(coach.age))
        coach.known = []
    return coach.staff_traits


def has(coach, key):
    return key in (getattr(coach, 'staff_traits', None) or [])


def words(coach, revealed_only=False):
    """[(key, name, fam, tip, known)] for the cards. revealed_only hides the unknown ones as '?'."""
    keys = getattr(coach, 'staff_traits', None) or []
    known = set(getattr(coach, 'known', None) or [])
    out = []
    for k in keys:
        if revealed_only and k not in known: out.append(dict(key=None, name='?', fam='unknown', tip='Interview him to learn this', known=False))
        else: out.append(dict(key=k, name=ALL[k]['name'], fam=ALL[k]['fam'], tip=ALL[k]['tip'], known=(k in known)))
    return out

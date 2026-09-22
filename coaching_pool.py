"""
THE COACHING POOL AND THE OWNER'S DECISION.

The coach and the GM are one man. Thirty of them sit in the pool at any
time: former head coaches carrying their record, coordinators on the way up,
front-office men from the assistant-GM pipeline. Each is a blend of the
trees in identity_catalog (what he runs) and a personality (how he builds),
with a resume the owner can read and dials the owner cannot.

WHEN AN OWNER FIRES HIS MAN he asks one question of every candidate: do I
hire someone who runs what we run and keep the roster, or do I change the
scheme and either convert my players or tear the roster down? He weighs
  - how much of the current roster fits the candidate's scheme, and what
    the misfits would cost to move (their contracts, the dead money)
  - how good the candidate looks, through an owner who reads talent
    imperfectly (reputation is public, the dials are not)
  - his own patience and the state of the club: a decent young roster
    argues for continuity, a bad old expensive one argues for a teardown,
    a long drought argues for anything different from what just failed
The fired man goes into the pool with his record on him; men in their
mid-sixties retire.

The pool persists on the league and is saved with it.
"""
import numpy as np, collections
import gm_engine as GE

POOL_SIZE = 30
RETIRE_AGE = 65
BACKGROUNDS = {          # what the resume says, and the pipeline shares
    'offensive coordinator': 0.26, 'defensive coordinator': 0.22,
    'former head coach': 0.20, 'assistant GM': 0.18,
    'college head coach': 0.08, 'position coach': 0.06,
}
FIRST = ['Marcus', 'Brian', 'Kevin', 'Matt', 'Chris', 'Mike', 'Jeff', 'Sean', 'Dan', 'Todd', 'Ryan', 'Nick',
         'Eric', 'Adam', 'Joe', 'Aaron', 'Jason', 'Josh', 'Mark', 'David', 'Ben', 'Robert', 'Shane', 'Anthony',
         'Kellen', 'Zac', 'Brandon', 'Darren', 'Klint', 'Jesse', 'Raheem', 'DeMeco', 'Liam', 'Bobby', 'Thomas',
         'Andre', 'Derrick', 'Marcus', 'Jerod', 'Vance', 'Aden', 'Wink', 'Lou', 'Jim', 'Frank', 'Drew', 'Press']
LAST = ['Hollins', 'Garrity', 'Whitfield', 'Okafor', 'Brandt', 'Salazar', 'Pruitt', 'Vandermeer', 'Coyle',
        'Castellanos', 'Harmon', 'Delgado', 'Oyelaran', 'Whitaker', 'Rusnak', 'Kimbrough', 'Tafoya', 'Pettibone',
        'Lindgren', 'Mabry', 'Sekulic', 'Antwine', 'Faulkner', 'Naquin', 'Broussard', 'Steinbach', 'Gilliam',
        'Radke', 'Toussaint', 'Hedlund', 'Carrasco', 'Ridgeway', 'Ballenger', 'Nkemelu', 'Zimmerle', 'Stroud']


def _name(rng, taken):
    for _ in range(50):
        n = f"{FIRST[int(rng.integers(len(FIRST)))]} {LAST[int(rng.integers(len(LAST)))]}"
        if n not in taken: return n
    return n


def make_candidate(rng, taken=(), background=None):
    """A man for the pool: personality from make_gm, identity blended from
    the trees, a resume the owner reads."""
    g = GE.make_gm(rng)
    g.name = _name(rng, set(taken))
    bg = background or str(rng.choice(list(BACKGROUNDS), p=list(BACKGROUNDS.values())))
    g.background = bg
    g.age = int(np.clip(rng.normal({'former head coach': 52, 'assistant GM': 44, 'offensive coordinator': 46,
                                    'defensive coordinator': 47, 'college head coach': 50,
                                    'position coach': 42}.get(bg, 46), 6), 34, 64))
    g.experience = int(np.clip(g.age - 30 + rng.integers(-4, 5), 2, 35))
    g.hc_record = None
    if bg == 'former head coach':
        seasons = int(rng.integers(2, 8)); pct = float(np.clip(rng.normal(0.44, 0.10), 0.15, 0.72))
        g.hc_record = dict(seasons=seasons, win_pct=round(pct, 3), playoffs=int(rng.binomial(seasons, max(0.0, pct - 0.25))))
    # what the league thinks of him: the real quality with the owner's noise
    # added at hire time, not here
    g.reputation = round(float(np.clip(_quality(g) + rng.normal(0, 0.10), 0.05, 0.95)), 2)
    g.tenure = 0
    return g


def _quality(g):
    """The hidden truth: how good a coach and builder he is, as a composite
    of the dials that make one. The owner never sees this number."""
    return float(np.clip(0.35 * g.scouting + 0.25 * g.board_trust + 0.15 * (1 - abs(g.aggression - 0.55))
                         + 0.15 * g.patience + 0.10 * g.dev_belief, 0, 1))


def build_pool(league, rng, n=POOL_SIZE):
    taken = {t.gm.name for t in league.teams.values() if t.gm}
    pool = []
    for _ in range(n):
        c = make_candidate(rng, taken); taken.add(c.name); pool.append(c)
    league.coach_pool = pool
    return pool


def pool(league):
    if not getattr(league, 'coach_pool', None):
        league.coach_pool = []
    return league.coach_pool


def top_up(league, rng):
    """Retirements out, new coordinators in, back to thirty each offseason."""
    p = pool(league)
    for g in list(p):
        g.age = getattr(g, 'age', 48) + 1
        if g.age >= RETIRE_AGE and rng.random() < 0.6:
            p.remove(g); league.log('coach_retire', name=g.name)
    taken = {t.gm.name for t in league.teams.values() if t.gm} | {g.name for g in p}
    while len(p) < POOL_SIZE:
        c = make_candidate(rng, taken); taken.add(c.name); p.append(c)
    return p


# ------------------------------------------------------------ the owner
def roster_fit(team, gm):
    """
    How the club's two-deep would grade under this man's scheme: mean fit
    (points added or lost) and the misfits, each with what he is owed.
    """
    scheme = GE.scheme_of(gm)
    fits = []; misfits = []
    for pos, ps in team.depth.items():
        for p in ps[:2]:
            f = GE.scheme_fit(p.ratings, p.pos, _proxy(team, gm)) if scheme else 0.0
            fits.append(f)
            if f <= -2.0:
                owed = p.contract.remaining_proration(0) if p.contract else 0.0
                misfits.append((p, f, owed))
    return (float(np.mean(fits)) if fits else 0.0), misfits


class _proxy:
    """A team-shaped object with a candidate's scheme, so scheme_fit reads him."""
    def __init__(self, team, gm):
        self.scheme = GE.scheme_of(gm); self.gm = gm; self.abbr = team.abbr


def owner_state(team):
    ages = [p.age for ps in team.depth.values() for p in ps[:1]]
    return dict(win_pct=team.win_pct, prev_win_pct=team.prev_win_pct,
                avg_age=float(np.mean(ages)) if ages else 27.0,
                cap_health=float(np.clip(team.cap_space / 40.0, 0.0, 1.0)),
                drought=getattr(team, 'playoff_drought', 0),
                patience=float(getattr(team, 'owner_patience', 0.5)),
                acumen=float(getattr(team, 'owner_acumen', 0.5)))


def scheme_similarity(a, b):
    """0..1: how much of what the new man runs is what the club runs. Mixed
    blocking and multiple fronts are compatible with either answer."""
    if a is None or b is None: return 0.5
    s = 0.0
    s += 1.0 if a.off_blocking == b.off_blocking or 'mixed' in (a.off_blocking, b.off_blocking) else 0.0
    s += 1.0 if a.def_front == b.def_front or 'multiple' in (a.def_front, b.def_front) else 0.0
    s += 1.0 - min(1.0, abs(a.coverage - b.coverage) / 0.5)
    return s / 3.0


def owner_hire(league, team, rng, verbose=False):
    """
    The decision. Returns (hired, reasons) and moves the man out of the pool.
    """
    p = pool(league)
    if not p:
        top_up(league, rng)
    st = owner_state(team)
    # how much the owner wants continuity, 0 = tear it down, 1 = keep the roster
    decent = float(np.clip((st['win_pct'] - 0.30) / 0.30, 0, 1))
    young = float(np.clip((29.0 - st['avg_age']) / 3.0, 0, 1))
    continuity = 0.25 + 0.35 * decent + 0.25 * young + 0.15 * st['cap_health']
    if st['drought'] >= 6: continuity -= 0.20                # what we did is not working
    continuity = float(np.clip(continuity, 0.05, 0.95))
    old_fit, _ = roster_fit(team, team.gm) if team.gm else (0.0, [])
    scored = []
    for c in p:
        fit, misfits = roster_fit(team, c)
        cost = sum(owed for _p, _f, owed in misfits)                     # dead money to move the misfits
        seen_q = float(np.clip(c.reputation + rng.normal(0, 0.18 * (1 - st['acumen'])), 0, 1))
        # a former head coach's record is public and the owner weighs it
        if getattr(c, 'hc_record', None):
            seen_q = 0.7 * seen_q + 0.3 * float(c.hc_record['win_pct'] / 0.65)
        sim = scheme_similarity(c, team.gm)
        # CONTINUITY OR CHANGE. An owner who wants to keep his roster pays
        # for a man who runs what it runs and grades it well; an owner
        # tearing it down does not care, and a long drought makes sameness
        # a mark against
        fit_term = continuity * (0.30 * (fit - old_fit) + 0.25 * (sim - 0.5))
        if st['drought'] >= 6:
            fit_term -= 0.15 * (sim - 0.5)
        cost_term = (cost / max(20.0, team.cap_space + 40.0)) * continuity * (1.0 - 0.5 * st['patience'])
        score = seen_q + fit_term - cost_term
        scored.append((score, c, fit, len(misfits), cost, seen_q, sim))
    scored.sort(key=lambda x: -x[0])
    score, hired, fit, n_mis, cost, seen_q, sim = scored[0]
    p.remove(hired)
    reasons = dict(continuity=round(continuity, 2), fit=round(fit, 2), old_fit=round(old_fit, 2), misfits=n_mis,
                   conversion_cost=round(cost, 1), seen_quality=round(seen_q, 2), similarity=round(sim, 2),
                   same_scheme=sim >= 0.75)
    if verbose:
        print(f"  {team.abbr} hires {hired.name} ({hired.background}, {hired.tree[:30]}): continuity {continuity:.2f}, fit {fit:+.2f} vs {old_fit:+.2f}, {n_mis} misfits costing ${cost:.0f}m, seen quality {seen_q:.2f}")
    return hired, reasons


def fire_and_hire(league, team, rng, verbose=False):
    """The whole change: the old man to the pool (or retirement), the owner
    picks, the club's scheme becomes the new man's."""
    old = team.gm
    if old is not None:
        old.tenure = 0
        if getattr(old, 'age', 50) >= RETIRE_AGE - 3 and rng.random() < 0.5:
            league.log('coach_retire', name=old.name)
        else:
            old.background = 'former head coach'
            pool(league).append(old)
    hired, reasons = owner_hire(league, team, rng, verbose)
    hired.tenure = 0
    hired.job_security = float(np.clip(rng.normal(.78, .10), .45, .97))
    team.gm = hired
    team.scheme = GE.scheme_of(hired)
    team.tenure = 0
    league.log('gm_change', team=team.abbr, hired=hired.name, background=hired.background,
               win_pct=round(team.win_pct, 3), **reasons)
    return hired, reasons

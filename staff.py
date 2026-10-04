from stable import stable_seed
"""
STAFF. Four people on every club besides the head coach:

  oc      offensive coordinator: the quality of the offensive suggestions
          each week, XP for offensive players, the position-change tax on
          offensive moves
  dc      defensive coordinator: the same for the defense
  st      special teams coordinator: the kicking game's variance
  scout   head scout: the room's error on every prospect

Each is a person: a name, a rating for the job (0-100), prestige, a
specialty word, a contract in years, and the same hidden traits players
have. They live in one pool alongside the head coaches in coaching_pool;
a coordinator whose prestige rises becomes a head-coaching candidate, and
when a club hires him away you have a hole.

THE CAROUSEL, each offseason after the head-coaching moves:
  - contracts run down; an expiring coordinator re-signs by his mood and
    the club's season, or walks to the pool
  - a new head coach brings a coordinator on his own side of the ball
    (an offensive-minded coach brings his OC); the sitting one goes to
    the pool
  - a coordinator whose unit ranked bottom-eight two years running is let
    go by an AI club
  - AI clubs fill holes from the pool by rating and prestige, the user
    is asked
  - the real rate: about a third of clubs change at least one coordinator
    each offseason

THE EFFECTS, each a hook into a thing that already exists:
  gameplan_week.ai_plan   the coordinator's rating replaces the flat
                          adjust_skill on his side
  xp.credit               offensive/defensive XP times 0.85-1.15 by the
                          coordinator's rating
  position_change         the tax games times 0.8-1.2 by his side's coordinator
  scouting.error_sd       the head scout's rating, not the GM's
  game.field_goal/punt    the ST coordinator narrows or widens the variance
"""
import numpy as np

ROLES = ('oc', 'dc', 'st', 'scout')
ROLE_NAME = {'oc': 'Offensive Coordinator', 'dc': 'Defensive Coordinator', 'st': 'Special Teams Coordinator', 'scout': 'Head Scout'}
SIDE = {'oc': 'offense', 'dc': 'defense'}
SPECIALTY = {'oc': ['play design', 'quarterback development', 'run game', 'pass protection', 'tempo', 'red zone'],
             'dc': ['pressure design', 'coverage disguise', 'run fits', 'corner development', 'third down', 'red zone'],
             'st': ['return game', 'kicker management', 'coverage units', 'punt game'],
             'scout': ['small schools', 'the trenches', 'quarterbacks', 'medical reads', 'character reads', 'athletic testing']}
POOL_SIZE = {'oc': 14, 'dc': 14, 'st': 8, 'scout': 10}
CONTRACT_YEARS = (3, 4, 5)         # assistants sign longer than they used to; fewer come up each year
OFFENSE_POS = {'QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT'}
CHANGE_RATE_TARGET = 0.33          # share of clubs changing a coordinator per offseason
BUDGET_BASE = 22.0                 # $m for the whole staff, the head coach included; the owner's spending weight tilts it 15% either way
HC_PAY_BASE, HC_PAY_PER_PRESTIGE = 4.0, 0.11   # a head coach's pay: $4m for a first-timer nobody knows, about $15m for a big name
ROLE_SCALE = {'oc': 1.0, 'dc': 1.0, 'st': 0.5, 'scout': 0.4}
HC_CANDIDATE_PREMIUM = 1.20
ENTRANT_DISCOUNT = 0.85


def ask(coach):
    """What he asks a year, $m. Flat at the bottom of the market and steep at the
    top: a floor for the job, a rating term quadratic above 50, a smaller linear
    prestige term, a premium for a head-coaching candidate, a discount for a
    first-year entrant, and his money trait either way."""
    r = max(0.0, coach.rating - 50.0)
    base = 0.9 + 0.0019 * r * r + 0.012 * coach.prestige
    if coach.hc_candidate: base *= HC_CANDIDATE_PREMIUM
    if not coach.history and coach.age <= 42: base *= ENTRANT_DISCOUNT
    fp = (coach.traits or {}).get('financial_priority', 50) / 100.0
    base *= 0.90 + 0.20 * fp
    return round(base * ROLE_SCALE[coach.role], 2)


def budget(team):
    return round(BUDGET_BASE * (0.85 + 0.30 * float(getattr(team, 'owner_spend', 0.5))), 2)


def hc_pay(gm):
    """What the head coach is paid, priced once from his name when he was hired and kept on him."""
    if gm is None: return 0.0
    s = float(getattr(gm, 'salary', 0.0) or 0.0)
    if s <= 0:
        s = round(HC_PAY_BASE + HC_PAY_PER_PRESTIGE * float(getattr(gm, 'prestige', 20.0) or 20.0), 2)
        try: gm.salary = s
        except Exception: pass
    return s


def payroll(team, without=None):
    """The staff payroll: the head coach and the four assistants. The head coach's salary is the anchor: a big name
    leaves less for the room around him, a first-timer leaves more."""
    assistants = sum(c.salary for r, c in (getattr(team, 'staff', None) or {}).items() if c is not None and r != without)
    hc = 0.0 if without == 'hc' else hc_pay(getattr(team, 'gm', None))
    return round(assistants + hc, 2)


def room(team, without=None):
    return round(budget(team) - payroll(team, without), 2)
DISGRUNTLED_HIT = 12.0             # rating points lost for the year after being blocked


class Coach:
    __slots__ = ('name', 'role', 'rating', 'prestige', 'specialty', 'age', 'years', 'team', 'traits', 'history', 'unit_ranks', 'hc_candidate', 'disgruntled', 'salary', 'staff_traits', 'known')

    def __init__(self, name, role, rating, prestige, specialty, age, years=3, team=None, traits=None):
        self.name, self.role = name, role
        self.rating, self.prestige, self.specialty, self.age = float(rating), float(prestige), specialty, int(age)
        self.years, self.team = int(years), team
        self.traits = traits or {}
        self.staff_traits = None        # the words (staff_traits.py); drawn on first use
        self.known = []                 # which of them the GM has learned, while he is in the pool
        self.history = []              # (year, team, role)
        self.unit_ranks = []           # last seasons' unit rank on his side
        self.hc_candidate = False
        self.disgruntled = 0            # the year he was kept against his will, 0 if not
        self.salary = 0.0               # $m a year on his current deal

    def effective(self):
        """A coordinator kept from a head-coaching job coaches worse for a year:
        his advice is thinner and his side learns slower."""
        return self.rating - (DISGRUNTLED_HIT if self.disgruntled else 0.0)

    def to_dict(self):
        return dict(name=self.name, role=self.role, rating=self.rating, prestige=self.prestige, specialty=self.specialty, age=self.age,
                    years=self.years, team=self.team, traits=self.traits, history=self.history, unit_ranks=self.unit_ranks, hc_candidate=self.hc_candidate, disgruntled=self.disgruntled, salary=self.salary,
                    staff_traits=self.staff_traits, known=self.known)

    @classmethod
    def from_dict(cls, d):
        c = cls(d['name'], d['role'], d['rating'], d['prestige'], d['specialty'], d['age'], d.get('years', 1), d.get('team'), d.get('traits'))
        c.history = d.get('history', []); c.unit_ranks = d.get('unit_ranks', []); c.hc_candidate = d.get('hc_candidate', False); c.disgruntled = d.get('disgruntled', 0); c.salary = d.get('salary', 0.0)
        c.staff_traits = d.get('staff_traits'); c.known = d.get('known') or []
        return c


# ------------------------------------------------------------ creation
def _name(rng, league=None):
    import coaching_pool as CP
    taken = set()
    if league is not None:
        taken |= {c.name for t in league.teams.values() for c in (getattr(t, 'staff', None) or {}).values() if c}
        taken |= {c.name for c in getattr(league, 'staff_pool', []) or []}
        taken |= {t.gm.name for t in league.teams.values() if t.gm is not None}
        taken |= {g.name for g in (getattr(league, 'coach_pool', None) or [])}
    return CP._name(rng, taken)


def make(rng, role, rating=None, prestige=None, team=None, league=None, young=False):
    """A coach. `young` is a new entrant: a position coach or college coordinator getting his
    first shot, 34-42, rated under the sitting men on average with a wide spread."""
    import personality as PT
    if young:
        age = int(rng.integers(34, 43))
        rating = float(np.clip(rng.normal(55, 11), 35, 84)) if rating is None else rating
        prestige = float(np.clip(rng.normal(22, 8), 5, 50)) if prestige is None else prestige
    else:
        age = int(rng.integers(34, 62))
        rating = float(np.clip(rng.normal(62, 12), 35, 92)) if rating is None else rating
        prestige = float(np.clip(rating * 0.7 + rng.normal(0, 9), 10, 90)) if prestige is None else prestige
    c = Coach(_name(rng, league), role, rating, prestige, rng.choice(SPECIALTY[role]), age,
              years=int(rng.choice(CONTRACT_YEARS)), team=team, traits=PT.draw(rng))
    import staff_traits as STR
    STR.ensure(c, rng)
    return c


def seed(league, rng):
    """Every club gets four; the pool gets its share. The head coach's own rating
    seeds his coordinators a little: good coaches hire well."""
    for abbr, team in league.teams.items():
        if getattr(team, 'staff', None): continue
        team.staff = {}
        hc_q = float(getattr(team.gm, 'prestige', 60)) / 100.0
        for role in ROLES:
            r = float(np.clip(rng.normal(58 + 14 * hc_q, 10), 38, 90))
            c = make(rng, role, rating=r, team=abbr, league=league); c.history.append((league.year, abbr, role))
            team.staff[role] = c
        for c in team.staff.values(): c.salary = ask(c)
        hc_pay(team.gm)
        over = payroll(team) - budget(team)
        if over > 0:                                    # day one must fit: the assistants signed for a shade under the market
            avail = max(1.0, budget(team) - hc_pay(team.gm)); tot = max(0.01, payroll(team, without='hc'))
            for c in team.staff.values(): c.salary = round(c.salary * avail / tot, 2)
    league.staff_pool = getattr(league, 'staff_pool', None) or []
    for role, n in POOL_SIZE.items():
        have = sum(1 for c in league.staff_pool if c.role == role)
        for _ in range(max(0, n - have)):
            league.staff_pool.append(make(rng, role, league=league))
    return sum(len(t.staff) for t in league.teams.values())


# ------------------------------------------------------------ the effects
def rating(team, role, default=60.0):
    st = getattr(team, 'staff', None) or {}
    c = st.get(role)
    return float(c.effective()) if c is not None else default


def plan_skill(team, side):
    """0-1 skill for the game plan on one side, from the coordinator; Sharp on Sunday adds 0.15."""
    import staff_traits as STR
    role = 'oc' if side.startswith('off') else 'dc'
    sk = float(np.clip((rating(team, role) - 35.0) / 55.0, 0.05, 1.0))
    c = (getattr(team, 'staff', None) or {}).get(role)
    if c is not None and STR.has(c, 'sharp'): sk = min(1.0, sk + 0.15)
    return sk


def coordinator_of(team, pos):
    """The coach whose unit a position belongs to."""
    st = getattr(team, 'staff', None) or {}
    role = 'oc' if pos in OFFENSE_POS else 'st' if pos in ('K', 'P', 'LS') else 'dc'
    return st.get(role)


def trait(team, pos, key):
    """Does the coordinator over this position carry the trait?"""
    import staff_traits as STR
    c = coordinator_of(team, pos)
    return c is not None and STR.has(c, key)


def xp_mult(team, player):
    """0.85-1.15 by the coordinator on the player's side; a Teacher adds 15% to his whole unit,
    a Developer 15% to the men 24 and under."""
    if team is None: return 1.0
    role = 'oc' if player.pos in OFFENSE_POS else 'dc' if player.pos not in ('K', 'P') else 'st'
    m = 0.85 + 0.30 * float(np.clip((rating(team, role) - 35.0) / 55.0, 0.0, 1.0))
    if trait(team, player.pos, 'teacher'): m *= 1.15
    elif trait(team, player.pos, 'developer') and float(getattr(player, 'age', 30)) <= 24.0: m *= 1.15
    return m


def game_terms(team):
    """What the game reads off the staff each Sunday: the Disciplinarian's penalty and fumble
    factors by side, and the Sharp on Sunday edge by side."""
    st = getattr(team, 'staff', None) or {}
    import staff_traits as STR
    def has(role, key):
        c = st.get(role); return c is not None and STR.has(c, key)
    return dict(pen_off=(0.90 if has('oc', 'disciplinarian') else 1.0), pen_def=(0.90 if has('dc', 'disciplinarian') else 1.0),
                fum_off=(0.90 if has('oc', 'disciplinarian') else 1.0),
                sharp_off=has('oc', 'sharp'), sharp_def=has('dc', 'sharp'))


def recruit_pull(team, pos):
    """A Recruiter over the position: the club's offer reads 5% richer to a free agent and his ask to the club runs 4% lower."""
    return (1.05, 0.96) if trait(team, pos, 'recruiter') else (1.0, 1.0)


def tax_mult(team, new_pos):
    """A good coordinator teaches the new job faster: 0.8-1.2 on the games."""
    if team is None: return 1.0
    role = 'oc' if new_pos in OFFENSE_POS else 'dc'
    return 1.2 - 0.4 * float(np.clip((rating(team, role) - 35.0) / 55.0, 0.0, 1.0))


def kick_noise_mult(team):
    """The ST coordinator: a good one narrows the kicking game's variance."""
    return 1.15 - 0.30 * float(np.clip((rating(team, 'st') - 35.0) / 55.0, 0.0, 1.0))


def short_kick_bias(team):
    """How readily this coordinator trusts coverage to beat a touchback spot."""
    coordinator = (getattr(team, 'staff', None) or {}).get('st')
    if coordinator is None:
        return 0.0
    specialty = {'coverage units': 0.07, 'kicker management': -0.03}.get(
        coordinator.specialty, 0.0)
    return float(np.clip(0.14 * (coordinator.effective() - 60.0) / 50.0
                         + specialty, -0.13, 0.15))


def scout_quality(team):
    """0-1 for scouting.error_sd."""
    return float(np.clip((rating(team, 'scout') - 35.0) / 55.0, 0.0, 1.0))


# ------------------------------------------------------------ the season
def season_end(league, unit_ranks_by_team):
    """Record each coordinator's unit rank; move prestige; age everyone; contracts run down."""
    for abbr, team in league.teams.items():
        st = getattr(team, 'staff', None) or {}
        ranks = unit_ranks_by_team.get(abbr, {})
        hc_prestige = float(getattr(team.gm, 'prestige', 50)) if team.gm is not None else 50.0
        for role, c in st.items():
            if c is None: continue                  # a hole a head-coaching hire just left; the carousel fills it
            r = ranks.get(role)
            if r is not None:
                c.unit_ranks.append(int(r))
                c.prestige = float(np.clip(c.prestige + (8 if r <= 4 else 4 if r <= 8 else -3 if r >= 25 else 0) + (0.25 * (16.5 - r)), 5, 95))
            # THE RATING MOVES. A career arc: a young coordinator grows when his
            # unit is above average, more under a head coach with a name; a man
            # in his late forties holds; from the mid-fifties he loses a point a
            # year. A bottom-eight unit costs even a young man; a disgruntled
            # year teaches nothing.
            good = (r is not None and r <= 16); bad = (r is not None and r >= 25)
            if c.disgruntled:
                d = 0.0
            elif c.age < 45:
                d = (1.5 if good else 0.5) + 0.6 * max(0.0, (hc_prestige - 70) / 30.0) - (1.5 if bad else 0.0)
            elif c.age < 55:
                d = (0.4 if good else 0.0) - (1.0 if bad else 0.0)
            else:
                d = -0.6 - (0.7 if bad else 0.0)
            import staff_traits as STR
            if STR.has(c, 'riser') and d > 0: d *= 1.5
            c.rating = float(np.clip(c.rating + d, 30, 95))
            if STR.has(c, 'riser') and r is not None and r <= 16: c.prestige = float(np.clip(c.prestige + 2.0, 5, 95))
            c.age += 1; c.years -= 1
            if c.disgruntled and c.disgruntled < league.year: c.disgruntled = 0
            if c.role in ('oc', 'dc') and c.prestige >= 72 and c.rating >= 70:
                c.hc_candidate = True
    # retirement: from 64 the chance grows each year; a retiring coordinator leaves a hole the carousel fills
    rng = np.random.default_rng(league.year * 31 + 7)
    for abbr, team in league.teams.items():
        for role, c in list((getattr(team, 'staff', None) or {}).items()):
            if c is not None and c.age >= 64 and rng.random() < 0.15 + 0.12 * (c.age - 64):
                team.staff[role] = None
                league.log('staff_retire', team=abbr, role=role, name=c.name, age=c.age)
                if abbr == getattr(league, 'user_team', None):
                    import inbox as IB
                    IB.post(league, 'staff', f"{c.name} is retiring", f"Your {ROLE_NAME[role].lower()} is calling it a career at {c.age}. The job is open.", sender=c.name, payload=dict(role=role, event='retirement', link='front_office:staff'))
    league.staff_pool = [c for c in getattr(league, 'staff_pool', []) if c.age < 66]
    for c in league.staff_pool:
        c.age += 1; c.prestige = float(np.clip(c.prestige * 0.96 + 2.0, 5, 95))


def unit_ranks(league, year):
    """Evaluate regular-season work for the team that actually received it.

    Season totals cannot reconstruct a traded player's team splits. Missing
    game books therefore leave a club unranked rather than assigning its
    current roster's past production to the current staff.
    """
    import collections
    totals = {a: collections.Counter() for a in league.teams}
    recorded = {a: set() for a in league.teams}
    for key, book in (getattr(league, 'game_stats', None) or {}).items():
        parts = key.split('-')
        if len(parts) != 4 or parts[0] != str(year): continue
        try: week = int(parts[1])
        except ValueError: continue
        if not 1 <= week <= 18: continue
        for abbr in parts[2:]:
            if abbr not in totals: continue
            if not any(line.get('team') == abbr for line in book.values()): continue
            totals[abbr].update(_unit_book_totals(book, abbr))
            recorded[abbr].add(key)
    missing = set()
    if year == league.year:
        for wk, away, home, ap, hp in getattr(league, 'schedule', ()):
            if not 1 <= wk <= 18 or ap is None or hp is None: continue
            key = f'{year}-{wk}-{home}-{away}'
            for abbr in (away, home):
                if key not in recorded.get(abbr, ()): missing.add(abbr)
    off, deff, st = {}, {}, {}
    for abbr, line in totals.items():
        if abbr in missing: continue
        n = line['pass_plays'] + line['rush_plays']
        if n: off[abbr] = (line['pass_epa'] + line['rush_epa']) / n
        if line['def_plays']: deff[abbr] = line['def_epa'] / line['def_plays']
        fga, punts = line['fg_att'], line['punts']
        if fga or punts:
            st[abbr] = (line['fg_made'] / fga if fga else 0.8) + 0.001 * (line['punt_net_yds'] / punts if punts else 0.0)
    def rank(d):
        order = sorted(d, key=lambda a: -d[a]); return {a: i + 1 for i, a in enumerate(order)}
    ro, rd, rs = rank(off), rank(deff), rank(st)
    return {abbr: {'oc': ro.get(abbr), 'dc': rd.get(abbr), 'st': rs.get(abbr)} for abbr in league.teams}


# ------------------------------------------------------------ the carousel
def carousel(league, rng, new_head_coaches=(), verbose=False, *, season_records=None):
    """
    After the head-coaching moves. Returns the log of changes.
      1. a new head coach brings a coordinator on his side; the sitting one goes to the pool
      2. AI clubs let go a coordinator whose unit was bottom-eight two years running
      3. expiring coordinators re-sign or walk
      4. head-coaching hires from the pool that were coordinators leave holes elsewhere (handled by coaching_pool)
      5. holes filled from the pool by rating and prestige; the user's holes are posted to the inbox
    """
    log = []
    pool = league.staff_pool
    user = getattr(league, 'user_team', None)
    finalize_poaches(league)
    import coaching_pool as CP
    CP.close_pending_hires(league, rng)                    # a club still waiting on the user takes the coordinator

    def to_pool(team, role, why):
        c = team.staff.get(role)
        if c is None: return
        c.team = None; c.years = 0
        pool.append(c); team.staff[role] = None
        log.append(dict(team=team.abbr, role=role, out=c.name, why=why))
        league.log('staff_out', team=team.abbr, role=role, name=c.name, why=why)

    # 1. new head coaches bring their own
    for abbr in new_head_coaches:
        team = league.teams[abbr]; gm = team.gm
        side_role = 'oc' if 'offens' in str(getattr(gm, 'background', 'offensive coordinator')) else 'dc'
        if abbr != user or True:
            to_pool(team, side_role, 'new head coach brought his own')
            c = make(rng, side_role, rating=float(np.clip(rng.normal(60 + 0.2 * getattr(gm, 'prestige', 60) - 10, 8), 40, 90)), team=abbr, league=league)
            c.years = int(rng.choice(CONTRACT_YEARS)); c.history.append((league.year, abbr, side_role)); c.salary = ask(c); team.staff[side_role] = c
            log.append(dict(team=abbr, role=side_role, hired=c.name, why='came with the head coach'))
            league.log('staff_in', team=abbr, role=side_role, name=c.name, why='came with the head coach')

    # 2. AI clubs fire on results
    for abbr, team in league.teams.items():
        if abbr == user or abbr in new_head_coaches: continue
        for role in ('oc', 'dc', 'st'):
            c = team.staff.get(role)
            if c is not None and len(c.unit_ranks) >= 2 and all(r >= 25 for r in c.unit_ranks[-2:]) and rng.random() < 0.7:
                to_pool(team, role, 'unit bottom-eight two years running')

    # 3. contracts
    for abbr, team in league.teams.items():
        for role in ROLES:
            c = team.staff.get(role)
            if c is None or c.years > 0: continue
            if abbr == user:
                # The user resolves these during the carousel, including a coach
                # who will not renew after a blocked head-coaching move.
                _post_user(league, team, role, c, 'expiring'); continue
            # re-sign by mood: winners and loyal men stay; a hot name with HC interest walks
            wins = (season_records or {}).get(abbr, team.record)[0]
            # most assistants re-sign: the walk rate on an expiring deal runs about a quarter,
            # higher for a hot name with head-coaching interest and on a losing club
            stay = 0.74 + 0.02 * (wins - 8) + 0.25 * (c.traits.get('loyalty', 50) / 100.0 - 0.5) - (0.35 if c.hc_candidate else 0.0)
            if c.disgruntled: stay = 0.0                      # a man you blocked walks when he can
            new_ask = ask(c)
            if rng.random() < stay and new_ask <= room(team, without=role) + 1e-9:
                c.years = int(rng.choice(CONTRACT_YEARS)); c.salary = new_ask; league.log('staff_extend', team=abbr, role=role, name=c.name, salary=new_ask)
            elif rng.random() < stay:
                to_pool(team, role, 'contract up, priced out')       # the club could not fit his new ask
            else:
                to_pool(team, role, 'contract up, walked')

    # 5. fill holes
    for abbr, team in league.teams.items():
        for role in ROLES:
            if team.staff.get(role) is not None: continue
            cands = [c for c in pool if c.role == role]
            if not cands:
                pool.append(make(rng, role, league=league, young=True)); cands = [c for c in pool if c.role == role]
            if abbr == user:
                _post_user(league, team, role, None, 'vacant', cands); continue
            hc_q = float(getattr(team.gm, 'prestige', 60)) / 100.0
            rm = room(team)
            fit = [c for c in cands if ask(c) <= rm + 1e-9] or sorted(cands, key=ask)[:1]   # the best he can afford; if nothing fits, the cheapest
            best = max(fit, key=lambda c: c.rating * (0.6 + 0.4 * hc_q) + 0.35 * c.prestige + rng.normal(0, 4))
            pool.remove(best); best.team = abbr; best.years = int(rng.choice(CONTRACT_YEARS)); best.history.append((league.year, abbr, role))
            best.salary = min(ask(best), max(0.4 * ROLE_SCALE[role], rm)) if ask(best) > rm else ask(best)
            team.staff[role] = best
            log.append(dict(team=abbr, role=role, hired=best.name, why='from the pool'))
            league.log('staff_in', team=abbr, role=role, name=best.name, why='from the pool')
    # THE CLASS. Every year a handful of new entrants arrive regardless of need,
    # young and mostly unproven: position coaches and college coordinators
    # getting a first shot. The pool then tops up to size with them and does
    # not balloon; the men it sheds are the weakest, which over time means the
    # old ones nobody hired.
    CLASS = {'oc': 3, 'dc': 3, 'st': 1, 'scout': 2}
    for role, k in CLASS.items():
        for _ in range(k):
            pool.append(make(rng, role, league=league, young=True))
            league.log('staff_entrant', role=role, name=pool[-1].name, age=pool[-1].age)
    for role, n in POOL_SIZE.items():
        have = [c for c in pool if c.role == role]
        for _ in range(max(0, n - len(have))):
            pool.append(make(rng, role, league=league, young=True))
        have = [c for c in pool if c.role == role]
        extra = sorted(have, key=lambda c: c.rating + 0.2 * c.prestige)[:max(0, len(have) - 2 * n)]
        for c in extra:
            pool.remove(c)
    if verbose: print(f"  staff carousel: {len(log)} moves")
    return log


def _post_user(league, team, role, coach, kind, cands=None):
    import inbox as IB
    if coach is not None:
        IB.post(league, 'staff', f"{coach.name}'s contract is up", f"Your {ROLE_NAME[role].lower()} ({coach.rating:.0f}, {coach.specialty}) is out of contract. Extend him or let him go to the pool.",
                sender=coach.name, payload=dict(role=role, coach=coach.name, link='front_office:staff'))
    else:
        IB.post(league, 'staff', f"You need a {ROLE_NAME[role].lower()}", f"The job is open. {len(cands or [])} candidates are in the pool.", sender='Front office', payload=dict(role=role, link='front_office:staff'))


# ------------------------------------------------------------ the poach
# When a club wants your coordinator as its head coach, he tells you how he
# feels before anything happens. You can let him go, try to keep him (a
# conversation, a raise, or both), or block it. A blocked man stays and
# coaches worse for a year, then walks when his contract is up.
def poach_request(league, coach, to_abbr, alternate=None):
    import inbox as IB
    tr = coach.traits or {}
    amb = tr.get('ambition', 50) / 100.0; loy = tr.get('loyalty', 50) / 100.0
    lean = 'go' if amb > 0.6 and loy < 0.55 else 'stay' if loy > 0.65 and amb < 0.5 else 'torn'
    words = {'go': f"{coach.name} wants the job. He says this is what he has worked for and he hopes you will not stand in his way.",
             'torn': f"{coach.name} is torn. He likes it here and he knows what he has with you, but a head-coaching job does not come around often.",
             'stay': f"{coach.name} would rather stay if you can make it worth his while. He wants to know you value him."}[lean]
    t = dict(id=len(getattr(league, 'poaches', []) or []) + 1, coach=coach.name, role=coach.role, team=coach.team, to=to_abbr, lean=lean,
             state='open', year=league.year, alternate=(alternate.name if alternate is not None else None), tries=0)
    league.poaches = (getattr(league, 'poaches', None) or []) + [t]
    IB.post(league, 'staff', f"{league.teams[to_abbr].abbr} wants {coach.name} as head coach", words + " Let him go, try to keep him, or block it.",
            sender=coach.name, payload=dict(poach=t['id'], link='front_office:staff'))
    return t


def answer_poach(league, tid, action, raise_years=0, raise_to=None, rng=None):
    """action: 'let_go' | 'persuade' | 'block'. persuade with raise_years and/or raise_to ($m a year) is a
    conversation and money; the money has to fit the staff budget, and what moves an ambitious man is a
    number near what a head-coaching job would pay him at his level, about 1.6x his ask."""
    rng = rng or np.random.default_rng(tid)
    t = next((x for x in (getattr(league, 'poaches', None) or []) if x['id'] == tid), None)
    if t is None or t['state'] != 'open': return dict(ok=False, why='nothing open')
    team = league.teams[t['team']]; c = team.staff.get(t['role'])
    if c is None or c.name != t['coach']: t['state'] = 'void'; __import__('inbox').reconcile(league); return dict(ok=False, why='he is no longer on your staff')
    tr = c.traits or {}; amb = tr.get('ambition', 50) / 100.0; loy = tr.get('loyalty', 50) / 100.0; money = tr.get('financial_priority', 50) / 100.0
    def _complete(take_first):
        __import__('inbox').reconcile(league)
        club = t.get('pending_club')
        if club and club in (getattr(league, 'pending_hires', None) or {}):
            import coaching_pool as CP
            CP.complete_pending_hire(league, club, rng, take_first=take_first)
    if action == 'let_go':
        t['state'] = 'let_go'; _complete(True); return dict(ok=True, result='he goes', line=f"{c.name} thanks you and takes the job.")
    if action == 'persuade':
        t['tries'] += 1
        base = {'go': 0.12, 'torn': 0.35, 'stay': 0.60}[t['lean']]
        a = ask(c); target = 1.6 * a
        if raise_to is not None and raise_to > room(team, without=t['role']) + 1e-9:
            return dict(ok=False, why=f'over the staff budget: ${room(team, without=t["role"]):.2f}m of room', ask=a)
        money_term = 0.0
        if raise_to is not None and raise_to > c.salary:
            money_term = 0.35 * float(np.clip((raise_to - c.salary) / max(0.1, target - c.salary), 0, 1)) * (0.6 + 0.8 * money)
        p = base + 0.25 * (loy - 0.5) - 0.25 * (amb - 0.5) + money_term + (0.04 * min(raise_years, 3) if raise_years else 0.0) - 0.15 * (t['tries'] - 1)
        if rng.random() < float(np.clip(p, 0.03, 0.9)):
            t['state'] = 'stayed'; c.years = max(c.years, int(raise_years) or c.years, 2); c.prestige = float(np.clip(c.prestige + 2, 0, 95))
            if raise_to is not None and raise_to > c.salary: c.salary = round(float(raise_to), 2)
            league.log('staff_extend', team=team.abbr, role=c.role, name=c.name, why='stayed after a head-coaching offer')
            _complete(False)
            return dict(ok=True, result='he stays', line=f"{c.name} stays." + (f" A new {int(raise_years)}-year deal." if raise_years else " He appreciated the conversation."))
        return dict(ok=True, result='he still wants to go', line=f"{c.name} hears you out and still wants the job. Let him go, or block it.")
    if action == 'block':
        t['state'] = 'blocked'; c.disgruntled = league.year
        league.log('staff_blocked', team=team.abbr, role=c.role, name=c.name)
        _complete(False)
        return dict(ok=True, result='blocked', line=f"{c.name} stays because you said so. He will coach, but not the way he did, and he will leave when his deal is up.")
    return dict(ok=False, why='unknown action')


def finalize_poaches(league):
    """At the carousel: open requests default to letting him go (the user did not answer)."""
    out = []
    for t in (getattr(league, 'poaches', None) or []):
        if t['state'] == 'open':
            t['state'] = 'let_go'
        out.append(t)
    __import__('inbox').reconcile(league)
    return out


def _reviews(league):
    state = getattr(league, 'staff_reviews', None) or {}
    if state.get('year') != league.year:
        state = dict(year=league.year, weeks=[], changes={}, hired={})
        league.staff_reviews = state
    return state


def _unit_book_totals(book, abbr):
    """Shared annual/midseason evidence, attributed at game time."""
    import collections
    totals = collections.Counter()
    for line in book.values():
        if line.get('team') != abbr: continue
        for key in ('pass_epa', 'rush_epa', 'pass_plays', 'rush_plays',
                    'def_epa', 'def_plays', 'fg_att', 'fg_made', 'punts'):
            totals[key] += float(line.get(key, 0) or 0)
        # Canonical zero is authoritative; only genuinely old rows use alias.
        totals['punt_net_yds'] += float(line.get('punt_net_yds', line.get('punt_net', 0)) or 0)
    return totals


def midseason_evidence(league, week):
    """Team-tagged game books; defensive success is *opponent* EPA suppressed.

    Never credit a traded player's old games to his current club. Missing or
    compacted books provide no evidence rather than an artificial bad rank.
    """
    import collections
    games = {a: [] for a in league.teams}
    books = getattr(league, 'game_stats', {}) or {}
    for wk, away, home, ap, hp in league.schedule:
        if not 1 <= wk <= min(week, 18) or ap is None or hp is None: continue
        book = books.get(f'{league.year}-{wk}-{home}-{away}') or {}
        for abbr, opponent, own_score, other_score in ((home, away, hp, ap), (away, home, ap, hp)):
            games[abbr].append(dict(week=wk, own=_unit_book_totals(book, abbr),
                                    opp=_unit_book_totals(book, opponent),
                                    win=own_score > other_score, loss=own_score < other_score))
    result = {}
    for abbr, rows in games.items():
        rows.sort(key=lambda r: r['week'])
        if len(rows) < 7: continue
        summary = dict(games=len(rows), wins=sum(r['win'] for r in rows), recent_losses=sum(r['loss'] for r in rows[-3:]), units={})
        for role in ('oc', 'dc', 'st'):
            samples = []
            for subset, min_plays in ((rows, 240), (rows[-3:], 90)):
                totals = collections.Counter()
                for r in subset: totals.update(r['opp' if role == 'dc' else 'own'])
                if role == 'st':
                    # Require both specialists to struggle, not one bad kick.
                    enough = totals['fg_att'] >= (10 if subset is rows else 3) and totals['punts'] >= (20 if subset is rows else 6)
                    samples.append((totals['fg_made']/totals['fg_att'], totals['punt_net_yds']/totals['punts']) if enough else None)
                else:
                    plays = totals['pass_plays'] + totals['rush_plays']
                    samples.append(((totals['pass_epa'] + totals['rush_epa']) / plays * (-1 if role == 'dc' else 1),) if plays >= min_plays else None)
            if all(s is not None for s in samples): summary['units'][role] = samples
        result[abbr] = summary
    return result


def midseason_review(league, rng, week):
    """Selective coordinator changes between games; never fire the user's staff.

    Three review dates, persistent decisions, one change per club per season.
    Require sustained poor results despite a credible healthy roster, and an
    affordable, clearly better available replacement before releasing anyone.
    """
    if league.phase != 'regular' or week not in (8, 11, 14): return []
    state = _reviews(league)
    if week in state['weeks']: return []
    state['weeks'].append(week)
    evidence = midseason_evidence(league, week)
    if len(evidence) < 20: return []
    import gameplan_week as GW
    unit_names = {'oc': ('QB', 'pass block', 'run block', 'receivers', 'tight end', 'backs'),
                  'dc': ('pass rush', 'run front', 'corners', 'safeties', 'linebackers')}
    talent, injury = {}, {}
    for a, t in league.teams.items():
        healthy, full = GW.unit_grades(league, t), GW.unit_grades(league, t, healthy_only=False)
        talent[a], injury[a] = {}, {}
        for role, names in unit_names.items():
            h, f = [healthy[n] for n in names if healthy.get(n) is not None], [full[n] for n in names if full.get(n) is not None]
            talent[a][role] = float(np.mean(h)) if len(h) == len(names) else 0
            injury[a][role] = len(h) < len(f) or (bool(f) and float(np.mean(f)) - talent[a][role] >= 4)
        specialists = [p for p in t.roster if p.pos in ('K', 'P', 'LS') and not p.retired]
        talent[a]['st'] = float(np.mean([max((p.ovr for p in specialists if p.pos == pos and p.out_until is None), default=0) for pos in ('K', 'P', 'LS')]))
        injury[a]['st'] = any(p.out_until is not None for p in specialists)
        # IR players may be absent from depth charts. Protect units losing a
        # top player and offenses without their best quarterback.
        for role, positions in (('oc', OFFENSE_POS), ('dc', {'LEDG', 'REDG', 'DT', 'MIKE', 'WILL', 'SAM', 'CB', 'FS', 'SS'})):
            men = [p for p in t.roster if p.pos in positions and not p.retired]
            injured = [p for p in men if p.out_until is not None]
            injury[a][role] |= any(p.ovr >= 80 for p in injured) or len(injured) >= 3
        qbs = [p for p in t.roster if p.pos == 'QB' and not p.retired]
        if qbs and max(qbs, key=lambda p: p.ovr).out_until is not None: injury[a]['oc'] = True
    moves = []
    for abbr, team in sorted(league.teams.items()):
        ev = evidence.get(abbr)
        if abbr == getattr(league, 'user_team', None) or abbr in state['changes'] or not ev: continue
        if ev['wins'] / ev['games'] > .4 or ev['recent_losses'] < 2: continue
        options = []
        for role in ('oc', 'dc', 'st'):
            c = team.staff.get(role)
            if c is None or f'{abbr}:{role}' in state['hired'] or injury[abbr][role]: continue
            if sum(t[role] > talent[abbr][role] for t in talent.values()) >= 20: continue
            peers = [e['units'][role] for e in evidence.values() if role in e['units']]
            values = ev['units'].get(role)
            if not values or len(peers) < 20: continue
            # Ties do not create a fictitious bottom-quartile ranking.
            if not all(sum(p[window][metric] > values[window][metric] for p in peers) >= .75 * len(peers)
                       for window in (0, 1) for metric in range(len(values[0]))): continue
            candidates = [x for x in pool_for(league, role)
                          if x.effective() >= c.effective() + 7 and ask(x) <= room(team, without=role) + 1e-9]
            if candidates:
                best = max(candidates, key=lambda x: (x.effective(), -ask(x), x.name))
                options.append((best.effective() - c.effective(), role, best))
        if not options: continue
        patience = float(getattr(team.gm, 'patience', .5))
        if rng.random() >= float(np.clip(.65 - .4 * patience, .2, .65)): continue
        _, role, candidate = max(options, key=lambda x: (x[0], x[1]))
        old = team.staff[role]
        old_years = old.years
        release(league, abbr, role, reason='sustained midseason unit underperformance')
        result = hire(league, abbr, candidate.name, reason='midseason replacement')
        if not result['ok']:
            # Defensive rollback: never leave a CPU vacancy if preflight and
            # execution disagree. Normally unreachable without external edits.
            league.staff_pool.remove(old); old.team = abbr; old.years = old_years; team.staff[role] = old
            raise RuntimeError(result['why'])
        state['changes'][abbr] = dict(role=role, week=week, out=old.name, hired=candidate.name)
        moves.append(state['changes'][abbr] | dict(team=abbr))
    return moves


# ------------------------------------------------------------ the user's actions
def extend(league, abbr, role, years=3, salary=None):
    """Extend at his ask (or the salary you name, which he takes if it is at least his ask). Must fit the budget."""
    team = league.teams[abbr]; c = team.staff.get(role)
    if c is None: return dict(ok=False, why='no one in the job')
    if c.years <= 0 and c.disgruntled:
        return dict(ok=False, why='He will not renew after his head-coaching move was blocked.')
    a = ask(c); pay = float(salary) if salary is not None else a
    if pay + 1e-9 < a: return dict(ok=False, why=f'he asks ${a:.2f}m', ask=a)
    if pay > room(team, without=role) + 1e-9: return dict(ok=False, why=f'over the staff budget: ${room(team, without=role):.2f}m of room', ask=a, room=room(team, without=role))
    c.years = int(years); c.salary = round(pay, 2); league.log('staff_extend', team=abbr, role=role, name=c.name, salary=c.salary)
    clear_expiry_choice(league, abbr, role)
    __import__('inbox').reconcile(league)
    return dict(ok=True, name=c.name, years=years, salary=c.salary)


def release(league, abbr, role, *, reason='released by the user'):
    team = league.teams[abbr]; c = team.staff.get(role)
    if c is None: return dict(ok=False, why='no one in the job')
    c.team = None; c.years = 0; league.staff_pool.append(c); team.staff[role] = None
    clear_expiry_choice(league, abbr, role)
    league.log('staff_out', team=abbr, role=role, name=c.name, why=reason)
    __import__('inbox').reconcile(league)
    return dict(ok=True)


def hire(league, abbr, coach_name, years=3, *, reason='hired by the user'):
    team = league.teams[abbr]
    c = next((x for x in league.staff_pool if x.name == coach_name and x.team is None), None)
    if c is None: return dict(ok=False, why='not in the pool')
    if team.staff.get(c.role) is not None: return dict(ok=False, why=f'{ROLE_NAME[c.role]} job is filled')
    a = ask(c)
    if a > room(team) + 1e-9: return dict(ok=False, why=f'he asks ${a:.2f}m and you have ${room(team):.2f}m of room', ask=a, room=room(team))
    league.staff_pool.remove(c); c.team = abbr; c.years = int(years); c.salary = a; c.history.append((league.year, abbr, c.role)); team.staff[c.role] = c
    c.known = list(c.staff_traits or [])                        # yours now: every trait shows
    iv = getattr(league, 'interviews', None) or {}; iv.pop(c.name, None)
    clear_expiry_choice(league, abbr, c.role)
    if league.phase == 'regular':
        _reviews(league)['hired'][f'{abbr}:{c.role}'] = int(league.week or 0)
    league.log('staff_in', team=abbr, role=c.role, name=c.name, why=reason)
    __import__('inbox').reconcile(league)
    return dict(ok=True, name=c.name, role=c.role)


def expiry_choices(league, abbr):
    state = getattr(league, 'staff_renewals', None) or {}
    return (state.get('choices') or {}).get(abbr, {}) if state.get('year') == league.year else {}


def clear_expiry_choice(league, abbr, role):
    expiry_choices(league, abbr).pop(role, None)


def choose_expiry(league, abbr, role, leave=True):
    c = league.teams[abbr].staff.get(role)
    if c is None or c.years > 0:
        return dict(ok=False, why='This staff contract is not expiring.')
    if not isinstance(leave, bool):
        return dict(ok=False, why='Choose whether to let the contract expire.')
    state = getattr(league, 'staff_renewals', None) or {}
    if state.get('year') != league.year:
        state = dict(year=league.year, choices={})
        league.staff_renewals = state
    choices = state.setdefault('choices', {}).setdefault(abbr, {})
    if leave: choices[role] = c.name
    else: choices.pop(role, None)
    return dict(ok=True)


def unresolved_expirations(league, abbr):
    choices = expiry_choices(league, abbr)
    return [r for r, c in league.teams[abbr].staff.items()
            if c is not None and c.years <= 0 and choices.get(r) != c.name]


def finish_renewals(league, abbr):
    if unresolved_expirations(league, abbr):
        return dict(ok=False, why='Renew or choose Let Expire for each expiring staff contract.')
    choices = dict(expiry_choices(league, abbr))
    for role, name in choices.items():
        c = league.teams[abbr].staff.get(role)
        if c is not None and c.name == name and c.years <= 0:
            release(league, abbr, role, reason='contract expired; user declined renewal')
    return dict(ok=True)


# ------------------------------------------------------------ the interview
# Hiring is a conversation before it is a number. In the interview the GM learns the player's
# traits one question at a time; the moment he is hired, everything shows. Three questions:
#   coaching (or, for a scout, hits): reveals one coaching trait / one strength
#   situation (or misses): reveals what he wants / one blind spot
#   references: one more trait, arriving at the next Advance, wrong about one time in six
# A Mercenary who hears you are shopping asks a little more after the interview.
def interview(league, abbr, name):
    import staff_traits as STR
    c = next((x for x in league.staff_pool if x.name == name), None)
    if c is None: return dict(ok=False, why='not in the pool')
    STR.ensure(c, np.random.default_rng(stable_seed(c.name)))
    iv = getattr(league, 'interviews', None) or {}
    st = iv.get(name) or dict(name=name, asked=[], log=[], refs_due=None, pending_ref=None)
    iv[name] = st; league.interviews = iv
    if not st['log']:
        st['log'].append(dict(who='coach', text=f"{c.name} sits down. {ROLE_NAME[c.role]}, {c.age}, {c.specialty}. He knows you are looking."))
    return dict(ok=True, state=_interview_view(league, c, st))


def _interview_view(league, c, st):
    import staff_traits as STR
    known = set(c.known or [])
    return dict(name=c.name, role=c.role, asked=st['asked'], log=st['log'], refs_due=st.get('refs_due'), ask=ask(c),
                traits=STR.words(c, revealed_only=True), all_known=all(k in known for k in (c.staff_traits or [])), n_hidden=sum(1 for k in (c.staff_traits or []) if k not in known))


def _reveal(league, c, st, pool_keys, question):
    """Reveal one of the man's traits from a family, in his own words."""
    import staff_traits as STR
    known = set(c.known or [])
    cands = [k for k in (c.staff_traits or []) if k in pool_keys and k not in known]
    if not cands:
        # nothing in that family: he says so, and that is information too
        fam_word = {'coaching': 'how he coaches', 'situation': 'what he wants', 'hits': 'his best calls', 'misses': 'where he has been wrong'}[question]
        st['log'].append(dict(who='coach', text=f"You ask about {fam_word}. Nothing he says stands out either way."))
        st['asked'].append(question); return None
    rng = np.random.default_rng(stable_seed(c.name + question))
    k = str(rng.choice(cands))
    c.known = list(known | {k})
    SAY = {'mercenary': 'He is plain about the money: he wants to be paid what the job is worth, and he will listen to anyone who pays more.',
           'loyal': 'He talks about finishing somewhere. Stability matters to him more than the next job.',
           'climber': 'He wants to be a head coach and says so. He would take the first real one.',
           'teacher': 'He talks about the classroom: the whole room gets better under him, he says, and his history backs it.',
           'developer': 'He lights up talking about young players. Veterans, less so.',
           'disciplinarian': 'Penalties and turnovers offend him personally. Some players have chafed under him.',
           'recruiter': 'He knows agents by first name and players want to play for him.',
           'sharp': 'He talks through last Sunday like a chess match. His game-week read is his pride.',
           'riser': 'He is getting better every year and he knows it.',
           'eye': 'His first reads on a player\'s skill have held up; he trusts his eyes over the numbers.',
           'wants': 'He falls for players. Once he likes one, his read on him drifts up.',
           'stopwatch': 'He does not miss on the body: the forty, the size, the combine numbers.',
           'measurables': 'He is a sucker for a workout. Athletes grade high in his room.',
           'projector': 'He is good on how far a player can grow.',
           'floor': 'He grades the floor and undersells the ceiling. His boards are full of safe picks.',
           'small_school': 'He has an eye for the small-school player; conference means nothing to him.',
           'big_program': 'He leans toward the big programs and it shows in his grades.',
           'character': 'His character reads have been reliable; his flags land on the right players.',
           'tape': 'He reads on-field discipline from film but skips preparation interviews and references.',
           'grinder': 'He watches more players than any room in the league.',
           'narrow': 'His board goes three rounds deep and stops.'}
    st['log'].append(dict(who='coach', text=SAY.get(k, STR.tip(k)), trait=k))
    st['asked'].append(question)
    return k


def interview_ask(league, abbr, name, question):
    """question: coaching | situation | references (coach); hits | misses | references (scout)."""
    import staff_traits as STR
    c = next((x for x in league.staff_pool if x.name == name), None)
    if c is None: return dict(ok=False, why='not in the pool')
    r = interview(league, abbr, name); st = league.interviews[name]
    if question in st['asked']: return dict(ok=False, why='you asked that already', state=_interview_view(league, c, st))
    COACHING = {'teacher', 'developer', 'disciplinarian', 'recruiter', 'sharp', 'riser'}; WANT = {'mercenary', 'loyal', 'climber'}
    POS = {k for k, v in STR.SCOUT.items() if v['fam'] == 'pos'}; NEG = {k for k, v in STR.SCOUT.items() if v['fam'] == 'neg'}
    if question == 'coaching': _reveal(league, c, st, COACHING, question)
    elif question == 'situation':
        k = _reveal(league, c, st, WANT, question)
        if k == 'mercenary': c.prestige = float(min(95.0, c.prestige + 1.5)); st['log'].append(dict(who='gm', text='He heard you are shopping. His ask has ticked up.'))
    elif question == 'hits': _reveal(league, c, st, POS, question)
    elif question == 'misses': _reveal(league, c, st, NEG, question)
    elif question == 'references':
        st['asked'].append(question); st['refs_due'] = 'next_advance'
        st['log'].append(dict(who='gm', text='You put in calls to people who have worked with him. The answers come back at the Advance.'))
    else: return dict(ok=False, why='no such question')
    return dict(ok=True, state=_interview_view(league, c, st))


def resolve_references(league, advanced=False):
    """At the roll: every reference call that is due comes back. One time in six the reference is wrong
    about him: it names a trait he does not have, and the interview shows it as hearsay."""
    import staff_traits as STR
    iv = getattr(league, 'interviews', None) or {}
    wk = int(league.week or 0)
    for name, st in iv.items():
        due = st.get('refs_due')
        if due is None: continue
        if not advanced and (due == 'next_advance' or due > wk): continue
        st['refs_due'] = None
        c = next((x for x in league.staff_pool if x.name == name), None)
        if c is None: continue
        rng = np.random.default_rng(stable_seed(name + 'refs'))
        known = set(c.known or []); hidden = [k for k in (c.staff_traits or []) if k not in known]
        if hidden and rng.random() >= 1 / 6:
            k = str(rng.choice(hidden)); c.known = list(known | {k})
            st['log'].append(dict(who='ref', text=f"A reference calls back: {STR.tip(k)}", trait=k))
        else:
            fam = STR.SCOUT if c.role == 'scout' else STR.COACH
            wrong = str(rng.choice([k for k in fam if k not in (c.staff_traits or [])]))
            st['log'].append(dict(who='ref', text=f"A reference calls back with a story that does not check out: he calls him {STR.name(wrong).lower()}. Hearsay.", hearsay=wrong))
        import inbox as IB
        IB.post(league, 'staff', f"References on {name}", st['log'][-1]['text'], sender='assistants', payload=dict(link='front_office:staff'))


def pool_for(league, role):
    return sorted([c for c in league.staff_pool if c.role == role and c.team is None], key=lambda c: -(c.rating + 0.3 * c.prestige))


def card(coach, revealed_only=False):
    """The card. On your own staff every trait shows; in the pool only the ones the interview has revealed,
    the rest as '?'."""
    import staff_traits as STR
    STR.ensure(coach, np.random.default_rng(stable_seed(coach.name)))
    return dict(name=coach.name, role=ROLE_NAME[coach.role], rating=round(coach.rating), prestige=round(coach.prestige), specialty=coach.specialty,
                age=coach.age, years=coach.years, salary=coach.salary, ask=ask(coach), hc_candidate=coach.hc_candidate,
                unit_ranks=coach.unit_ranks[-3:], traits=STR.words(coach, revealed_only=revealed_only), n_traits=len(coach.staff_traits or []))


# ------------------------------------------------------------ save
def to_dict(league):
    return dict(pool=[c.to_dict() for c in getattr(league, 'staff_pool', [])],
                renewals=getattr(league, 'staff_renewals', {}), reviews=getattr(league, 'staff_reviews', {}),
                teams={a: {r: (c.to_dict() if c else None) for r, c in (getattr(t, 'staff', None) or {}).items()} for a, t in league.teams.items()})


def from_dict(league, d):
    if not d: return
    league.staff_renewals = d.get('renewals') or {}
    league.staff_reviews = d.get('reviews') or {}
    league.staff_pool = [Coach.from_dict(x) for x in d.get('pool', [])]
    for a, roles in d.get('teams', {}).items():
        if a in league.teams:
            league.teams[a].staff = {r: (Coach.from_dict(c) if c else None) for r, c in roles.items()}

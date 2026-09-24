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
DISGRUNTLED_HIT = 12.0             # rating points lost for the year after being blocked


class Coach:
    __slots__ = ('name', 'role', 'rating', 'prestige', 'specialty', 'age', 'years', 'team', 'traits', 'history', 'unit_ranks', 'hc_candidate', 'disgruntled')

    def __init__(self, name, role, rating, prestige, specialty, age, years=3, team=None, traits=None):
        self.name, self.role = name, role
        self.rating, self.prestige, self.specialty, self.age = float(rating), float(prestige), specialty, int(age)
        self.years, self.team = int(years), team
        self.traits = traits or {}
        self.history = []              # (year, team, role)
        self.unit_ranks = []           # last seasons' unit rank on his side
        self.hc_candidate = False
        self.disgruntled = 0            # the year he was kept against his will, 0 if not

    def effective(self):
        """A coordinator kept from a head-coaching job coaches worse for a year:
        his advice is thinner and his side learns slower."""
        return self.rating - (DISGRUNTLED_HIT if self.disgruntled else 0.0)

    def to_dict(self):
        return dict(name=self.name, role=self.role, rating=self.rating, prestige=self.prestige, specialty=self.specialty, age=self.age,
                    years=self.years, team=self.team, traits=self.traits, history=self.history, unit_ranks=self.unit_ranks, hc_candidate=self.hc_candidate, disgruntled=self.disgruntled)

    @classmethod
    def from_dict(cls, d):
        c = cls(d['name'], d['role'], d['rating'], d['prestige'], d['specialty'], d['age'], d.get('years', 1), d.get('team'), d.get('traits'))
        c.history = d.get('history', []); c.unit_ranks = d.get('unit_ranks', []); c.hc_candidate = d.get('hc_candidate', False); c.disgruntled = d.get('disgruntled', 0)
        return c


# ------------------------------------------------------------ creation
def _name(rng):
    import coaching_pool as CP
    return CP._name(rng, set())


def make(rng, role, rating=None, prestige=None, team=None):
    import personality as PT
    rating = float(np.clip(rng.normal(62, 12), 35, 92)) if rating is None else rating
    prestige = float(np.clip(rating * 0.7 + rng.normal(0, 9), 10, 90)) if prestige is None else prestige
    c = Coach(_name(rng), role, rating, prestige, rng.choice(SPECIALTY[role]), int(rng.integers(34, 62)),
              years=int(rng.choice(CONTRACT_YEARS)), team=team, traits=PT.draw(rng))
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
            c = make(rng, role, rating=r, team=abbr); c.history.append((league.year, abbr, role))
            team.staff[role] = c
    league.staff_pool = getattr(league, 'staff_pool', None) or []
    for role, n in POOL_SIZE.items():
        have = sum(1 for c in league.staff_pool if c.role == role)
        for _ in range(max(0, n - have)):
            league.staff_pool.append(make(rng, role))
    return sum(len(t.staff) for t in league.teams.values())


# ------------------------------------------------------------ the effects
def rating(team, role, default=60.0):
    st = getattr(team, 'staff', None) or {}
    c = st.get(role)
    return float(c.effective()) if c is not None else default


def plan_skill(team, side):
    """0-1 skill for the game plan on one side, from the coordinator."""
    role = 'oc' if side.startswith('off') else 'dc'
    return float(np.clip((rating(team, role) - 35.0) / 55.0, 0.05, 1.0))


def xp_mult(team, player):
    """0.85-1.15 by the coordinator on the player's side."""
    if team is None: return 1.0
    role = 'oc' if player.pos in OFFENSE_POS else 'dc' if player.pos not in ('K', 'P') else 'st'
    return 0.85 + 0.30 * float(np.clip((rating(team, role) - 35.0) / 55.0, 0.0, 1.0))


def tax_mult(team, new_pos):
    """A good coordinator teaches the new job faster: 0.8-1.2 on the games."""
    if team is None: return 1.0
    role = 'oc' if new_pos in OFFENSE_POS else 'dc'
    return 1.2 - 0.4 * float(np.clip((rating(team, role) - 35.0) / 55.0, 0.0, 1.0))


def kick_noise_mult(team):
    """The ST coordinator: a good one narrows the kicking game's variance."""
    return 1.15 - 0.30 * float(np.clip((rating(team, 'st') - 35.0) / 55.0, 0.0, 1.0))


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
            c.rating = float(np.clip(c.rating + d, 30, 95))
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
                    IB.post(league, 'staff', f"{c.name} is retiring", f"Your {ROLE_NAME[role].lower()} is calling it a career at {c.age}. The job is open.", sender=c.name, payload=dict(role=role, link='front_office:staff'))
    league.staff_pool = [c for c in getattr(league, 'staff_pool', []) if c.age < 66]
    for c in league.staff_pool:
        c.age += 1; c.prestige = float(np.clip(c.prestige * 0.96 + 2.0, 5, 95))


def unit_ranks(league, year):
    """Per club: offense rank (for the OC), defense rank (DC), kicking rank (ST) from the season's team stats."""
    import advanced_stats as AS
    S = league.stats.get(year, {})
    off, deff, st = {}, {}, {}
    for abbr, team in league.teams.items():
        pids = {p.pid for p in team.roster}
        lines = [S[pid] for pid in pids if pid in S]
        o = sum(l.get('pass_epa', 0) + l.get('rush_epa', 0) for l in lines); n = sum(l.get('pass_plays', 0) + l.get('rush_plays', 0) for l in lines)
        off[abbr] = o / n if n else 0.0
        d = sum(l.get('def_epa', 0) for l in lines); dn = sum(l.get('def_plays', 0) for l in lines)
        deff[abbr] = d / dn if dn else 0.0
        fga = sum(l.get('fg_att', 0) for l in lines); fgm = sum(l.get('fg_made', 0) for l in lines)
        st[abbr] = (fgm / fga if fga else 0.8) + 0.001 * sum(l.get('punt_net', 0) for l in lines)
    def rank(d):
        order = sorted(d, key=lambda a: -d[a]); return {a: i + 1 for i, a in enumerate(order)}
    ro, rd, rs = rank(off), rank(deff), rank(st)
    return {abbr: {'oc': ro[abbr], 'dc': rd[abbr], 'st': rs[abbr]} for abbr in league.teams}


# ------------------------------------------------------------ the carousel
def carousel(league, rng, new_head_coaches=(), verbose=False):
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
            c = make(rng, side_role, rating=float(np.clip(rng.normal(60 + 0.2 * getattr(gm, 'prestige', 60) - 10, 8), 40, 90)), team=abbr)
            c.years = int(rng.choice(CONTRACT_YEARS)); c.history.append((league.year, abbr, side_role)); team.staff[side_role] = c
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
                if c.disgruntled:
                    to_pool(team, role, 'contract up, walked after being blocked'); continue
                _post_user(league, team, role, c, 'expiring'); continue
            # re-sign by mood: winners and loyal men stay; a hot name with HC interest walks
            wins = team.record[0]
            # most assistants re-sign: the walk rate on an expiring deal runs about a quarter,
            # higher for a hot name with head-coaching interest and on a losing club
            stay = 0.74 + 0.02 * (wins - 8) + 0.25 * (c.traits.get('loyalty', 50) / 100.0 - 0.5) - (0.35 if c.hc_candidate else 0.0)
            if c.disgruntled: stay = 0.0                      # a man you blocked walks when he can
            if rng.random() < stay:
                c.years = int(rng.choice(CONTRACT_YEARS)); league.log('staff_extend', team=abbr, role=role, name=c.name)
            else:
                to_pool(team, role, 'contract up, walked')

    # 5. fill holes
    for abbr, team in league.teams.items():
        for role in ROLES:
            if team.staff.get(role) is not None: continue
            cands = [c for c in pool if c.role == role]
            if not cands:
                pool.append(make(rng, role)); cands = [c for c in pool if c.role == role]
            if abbr == user:
                _post_user(league, team, role, None, 'vacant', cands); continue
            hc_q = float(getattr(team.gm, 'prestige', 60)) / 100.0
            best = max(cands, key=lambda c: c.rating * (0.6 + 0.4 * hc_q) + 0.35 * c.prestige + rng.normal(0, 4))
            pool.remove(best); best.team = abbr; best.years = int(rng.choice(CONTRACT_YEARS)); best.history.append((league.year, abbr, role))
            team.staff[role] = best
            log.append(dict(team=abbr, role=role, hired=best.name, why='from the pool'))
            league.log('staff_in', team=abbr, role=role, name=best.name, why='from the pool')
    # the pool stays stocked and does not balloon
    for role, n in POOL_SIZE.items():
        have = [c for c in pool if c.role == role]
        for _ in range(max(0, n - len(have))):
            pool.append(make(rng, role))
        extra = sorted(have, key=lambda c: c.rating)[:max(0, len(have) - 2 * n)]
        for c in extra:
            pool.remove(c)
    if verbose: print(f"  staff carousel: {len(log)} moves")
    return log


def _post_user(league, team, role, coach, kind, cands=None):
    import inbox as IB
    if coach is not None:
        IB.post(league, 'staff', f"{coach.name}'s contract is up", f"Your {ROLE_NAME[role].lower()} ({coach.rating:.0f}, {coach.specialty}) is out of contract. Extend him or let him go to the pool.",
                sender=coach.name, payload=dict(role=role, link='front_office:staff'))
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


def answer_poach(league, tid, action, raise_years=0, rng=None):
    """action: 'let_go' | 'persuade' | 'block'. persuade with raise_years > 0 is a conversation and money."""
    rng = rng or np.random.default_rng(tid)
    t = next((x for x in (getattr(league, 'poaches', None) or []) if x['id'] == tid), None)
    if t is None or t['state'] != 'open': return dict(ok=False, why='nothing open')
    team = league.teams[t['team']]; c = team.staff.get(t['role'])
    if c is None or c.name != t['coach']: t['state'] = 'void'; return dict(ok=False, why='he is no longer on your staff')
    tr = c.traits or {}; amb = tr.get('ambition', 50) / 100.0; loy = tr.get('loyalty', 50) / 100.0; money = tr.get('financial_priority', 50) / 100.0
    if action == 'let_go':
        t['state'] = 'let_go'; return dict(ok=True, result='he goes', line=f"{c.name} thanks you and takes the job.")
    if action == 'persuade':
        t['tries'] += 1
        base = {'go': 0.12, 'torn': 0.35, 'stay': 0.60}[t['lean']]
        p = base + 0.25 * (loy - 0.5) - 0.25 * (amb - 0.5) + (0.12 * min(raise_years, 3) * (0.6 + 0.8 * money) if raise_years else 0.0) - 0.15 * (t['tries'] - 1)
        if rng.random() < float(np.clip(p, 0.03, 0.9)):
            t['state'] = 'stayed'; c.years = max(c.years, int(raise_years) or c.years, 2); c.prestige = float(np.clip(c.prestige + 2, 0, 95))
            league.log('staff_extend', team=team.abbr, role=c.role, name=c.name, why='stayed after a head-coaching offer')
            return dict(ok=True, result='he stays', line=f"{c.name} stays." + (f" A new {int(raise_years)}-year deal." if raise_years else " He appreciated the conversation."))
        return dict(ok=True, result='he still wants to go', line=f"{c.name} hears you out and still wants the job. Let him go, or block it.")
    if action == 'block':
        t['state'] = 'blocked'; c.disgruntled = league.year
        league.log('staff_blocked', team=team.abbr, role=c.role, name=c.name)
        return dict(ok=True, result='blocked', line=f"{c.name} stays because you said so. He will coach, but not the way he did, and he will leave when his deal is up.")
    return dict(ok=False, why='unknown action')


def finalize_poaches(league):
    """At the carousel: open requests default to letting him go (the user did not answer)."""
    out = []
    for t in (getattr(league, 'poaches', None) or []):
        if t['state'] == 'open':
            t['state'] = 'let_go'
        out.append(t)
    return out


# ------------------------------------------------------------ the user's actions
def extend(league, abbr, role, years=3):
    team = league.teams[abbr]; c = team.staff.get(role)
    if c is None: return dict(ok=False, why='no one in the job')
    c.years = int(years); league.log('staff_extend', team=abbr, role=role, name=c.name)
    return dict(ok=True, name=c.name, years=years)


def release(league, abbr, role):
    team = league.teams[abbr]; c = team.staff.get(role)
    if c is None: return dict(ok=False, why='no one in the job')
    c.team = None; c.years = 0; league.staff_pool.append(c); team.staff[role] = None
    league.log('staff_out', team=abbr, role=role, name=c.name, why='released by the user')
    return dict(ok=True)


def hire(league, abbr, coach_name, years=3):
    team = league.teams[abbr]
    c = next((x for x in league.staff_pool if x.name == coach_name), None)
    if c is None: return dict(ok=False, why='not in the pool')
    if team.staff.get(c.role) is not None: return dict(ok=False, why=f'{ROLE_NAME[c.role]} job is filled')
    league.staff_pool.remove(c); c.team = abbr; c.years = int(years); c.history.append((league.year, abbr, c.role)); team.staff[c.role] = c
    league.log('staff_in', team=abbr, role=c.role, name=c.name, why='hired by the user')
    return dict(ok=True, name=c.name, role=c.role)


def pool_for(league, role):
    return sorted([c for c in league.staff_pool if c.role == role], key=lambda c: -(c.rating + 0.3 * c.prestige))


def card(coach):
    import personality as PT
    return dict(name=coach.name, role=ROLE_NAME[coach.role], rating=round(coach.rating), prestige=round(coach.prestige), specialty=coach.specialty,
                age=coach.age, years=coach.years, personality=PT.words(coach.traits) if coach.traits else '', hc_candidate=coach.hc_candidate,
                unit_ranks=coach.unit_ranks[-3:])


# ------------------------------------------------------------ save
def to_dict(league):
    return dict(pool=[c.to_dict() for c in getattr(league, 'staff_pool', [])],
                teams={a: {r: (c.to_dict() if c else None) for r, c in (getattr(t, 'staff', None) or {}).items()} for a, t in league.teams.items()})


def from_dict(league, d):
    if not d: return
    league.staff_pool = [Coach.from_dict(x) for x in d.get('pool', [])]
    for a, roles in d.get('teams', {}).items():
        if a in league.teams:
            league.teams[a].staff = {r: (Coach.from_dict(c) if c else None) for r, c in roles.items()}

"""
THE DATA MODEL.

Fifteen engines were built - GM valuation, cap, contract structure,
negotiation, free agency, trades, progression, morale, firing, roster
construction, IR, standings - and not one of them was ever called, because
nothing existed to call them. Each assumed a slightly different shape for
`team`, `player` and `gm`. This file settles those shapes once.

THE ONE RULE THAT MATTERS: the League owns the player. league_seed_2026.csv
is the day-one snapshot and nothing more. After the first kickoff, a player's
age, contract, ratings, morale and stats live here. Newgens are created
straight into the league and never touch the CSV at all.

OVERALL IS DERIVED, NEVER STORED. Madden's OVR and Football Manager's Current
Ability are both position-weighted sums of the underlying attributes, and both
recompute rather than store. If we stored an overall, progression would move
it every offseason while the sim kept reading the 53 ratings underneath - a
player would gain five points a year and perform identically forever, and the
two systems would drift apart silently for twenty seasons before anyone
noticed. So `player.ovr` calls the same position_score the depth chart and the
play engine already use. One number, one truth.

NOT zero-sum. FM treats ability as a budget, so raising one attribute lowers
another. That works in football where a player has one role and attributes
substitute for each other; it does not work here. A receiver improving his
hands should not get slower. Development is XP-spend instead, which is also
what Madden franchise does. The fields are reserved below; the spending rules
are deliberately not built yet.

DURABILITY SITS OUTSIDE ABILITY. FM excludes Determination, Natural Fitness,
Aggression and Flair from its ability calculation entirely. The equivalents
here are injury, stamina and toughness: a durable man should not be paying for
his durability out of the same pool as his skill.
"""
import json
from dataclasses import dataclass, field, asdict

import numpy as np

import targets as TG
from cap_engine import Contract, TeamCap, CAP
from gm_engine import GM, make_gm
import contract_structure as CS
import otc_2026 as OTC

# Attributes that describe how AVAILABLE a man is, not how good he is. Kept out
# of any future ability budget for the reason in the docstring.
DURABILITY_ATTRS = ('injury_rating', 'stamina_rating', 'toughness_rating',
                    'stamina', 'injury')

PHASES = ('preseason', 'regular', 'playoffs', 'offseason', 'free_agency',
          'draft', 'camp')


# ================================================================== PLAYER
class Player:
    """
    One man, for his whole career.

    Ratings stay a flat dict keyed exactly as the sim expects
    ('speed_rating', 'man_cover_rating', ...) so game.py, plays.py and
    targets.py can keep treating him as the dict they already take. Everything
    else - age, contract, dev, morale, stats - hangs off the object.
    """
    __slots__ = ('pid', 'name', 'pos', 'age', 'ratings', 'dev', 'potential',
                 'potential_range', 'longevity', 'team', 'contract',
                 'accrued', 'draft_year', 'draft_round', 'draft_overall',
                 'entry_year', 'xp', 'xp_spent', 'morale', 'out_until',
                 'injury_history', 'career', 'seasons', 'retired')

    def __init__(self, pid, name, pos, age, ratings, *, dev='normal',
                 potential=None, potential_range=None, longevity=1.0,
                 team=None, contract=None, accrued=0, draft_year=None,
                 draft_round=None, draft_overall=None, entry_year=None):
        self.pid = str(pid)
        self.name = name
        self.pos = pos
        self.age = float(age)
        self.ratings = dict(ratings)
        self.dev = dev
        # A HARD, HIDDEN, FIXED ceiling, as FM's potential ability is: set once
        # at creation and never moved for the rest of his career.
        self.potential = potential
        # Young players get a RANGE rather than a point, so the same prospect
        # develops differently in different saves. FM does this for under-21s
        # and it is most of the replay value in a draft class.
        self.potential_range = potential_range
        self.longevity = float(longevity)
        self.team = team
        self.contract = contract
        self.accrued = int(accrued)          # accrued seasons, drives FA class
        self.draft_year = draft_year
        self.draft_round = draft_round
        self.draft_overall = draft_overall
        self.entry_year = entry_year
        # reserved: development is XP-spend, rules deliberately not built yet
        self.xp = 0.0
        self.xp_spent = {}
        self.morale = None                   # a morale_system.Morale
        self.out_until = None                # week he is available again
        self.injury_history = []
        self.career = {}                     # season -> stat line
        self.seasons = []                    # season -> (team, games, ovr)
        self.retired = False

    # ---- derived ability -------------------------------------------------
    @property
    def ovr(self):
        """
        How good he is AT HIS POSITION, from the same weights the depth chart
        and the play engine use. Never stored; see the module docstring.
        """
        return TG.position_score(self.ratings, self.pos)

    def score_at(self, position, scheme=None):
        """What he would be worth at a DIFFERENT spot. Position changes and
        scheme fit fall straight out of this."""
        return TG.position_score(self.ratings, position, scheme)

    @property
    def madden_position(self):
        """gm_engine and roster_construction read this name."""
        return self.pos

    # ---- contract views the engines expect ------------------------------
    @property
    def apy(self):
        c = self.contract
        if not c or not c.years: return 0.0
        return round((sum(c.base) + sum(c.rb) + c.sb) / c.years, 3)

    @property
    def contract_years_left(self):
        return self.contract.years if self.contract else 0

    yrs_left = contract_years_left

    def cap_hit(self, year_index=0):
        return self.contract.cap_hit(year_index) if self.contract else 0.0

    def dead_if_cut(self, year_index=0, june1=False):
        if not self.contract: return 0.0
        return self.contract.release(year_index, june1)[0]

    @property
    def expiring(self):
        return self.contract_years_left <= 1

    @property
    def availability(self):
        """0-1. Feeds gm_engine's risk appetite."""
        return 0.0 if self.out_until is not None else 1.0

    # ---- stats -----------------------------------------------------------
    def record_season(self, season, line):
        """His own copy. The league keeps a second copy for leaderboards."""
        self.career[season] = dict(line)

    def career_totals(self):
        tot = {}
        for line in self.career.values():
            for k, v in line.items():
                if isinstance(v, (int, float)):
                    tot[k] = tot.get(k, 0) + v
        return tot

    # ---- persistence -----------------------------------------------------
    def to_dict(self):
        d = {k: getattr(self, k) for k in self.__slots__
             if k not in ('contract', 'morale')}
        d['contract'] = contract_to_dict(self.contract)
        d['morale'] = morale_to_dict(self.morale)
        return d

    @classmethod
    def from_dict(cls, d):
        p = cls.__new__(cls)
        for k in cls.__slots__:
            setattr(p, k, d.get(k))
        p.contract = contract_from_dict(d.get('contract'))
        p.morale = morale_from_dict(d.get('morale'))
        p.career = {int(k): v for k, v in (d.get('career') or {}).items()}
        return p

    def __repr__(self):
        return f'<{self.pos} {self.name} {self.age:.0f}y {self.ovr:.0f}ovr>'


# ================================================================== PICK
@dataclass
class DraftPick:
    """A tradeable asset. Owned by a team, not by the team that earned it."""
    year: int
    round: int
    original: str                 # the team whose record sets the slot
    owner: str                    # who currently holds it
    selection: int = None         # overall slot, once the order is known
    used_on: str = None           # pid, once spent

    @property
    def kind(self): return 'pick'

    @property
    def years_out(self): return 0     # League fills this in against its year


# ================================================================== TEAM
class Team:
    """
    A franchise. Stores the roster, cap, picks, GM and record; everything else
    the engines read is DERIVED. gm_engine, roster_construction,
    negotiation_engine and firing_model between them read fifteen fields off a
    team, and almost all of them are computed rather than kept - so they are
    properties, and there is one source of truth for each.
    """

    def __init__(self, abbr, division, conf, year=2026, gm=None, scheme=None):
        self.abbr = abbr
        self.division = division
        self.conf = conf
        self.scheme = scheme
        self.gm = gm
        self.roster = []                  # Player
        self.practice_squad = []
        self.ir = []
        self.picks = []                   # DraftPick
        self.cap = TeamCap(year)
        self.record = [0, 0, 0]           # W L T, this season
        self.history = []                 # per season: dict(win_pct, ...)
        self.tenure = 0                   # years the current GM has been here

    # ---- record ----------------------------------------------------------
    @property
    def win_pct(self):
        w, l, t = self.record
        n = w + l + t
        return (w + 0.5 * t) / n if n else 0.0

    @property
    def prev_win_pct(self):
        return self.history[-1]['win_pct'] if self.history else 0.5

    @property
    def playoff_drought(self):
        n = 0
        for h in reversed(self.history):
            if h.get('made_playoffs'): break
            n += 1
        return n

    @property
    def expected_pct(self):
        """What this roster should be worth, independent of results. The
        firing model needs luck separated from quality."""
        return float(np.clip((self.roster_strength() - 68.0) / 18.0, .05, .95))

    def hist(self):
        """firing_model.pressure() takes this shape."""
        return dict(win_pct=self.win_pct, prev_win_pct=self.prev_win_pct,
                    tenure=self.tenure, playoff_drought=self.playoff_drought,
                    expected_pct=self.expected_pct)

    # ---- roster shape ----------------------------------------------------
    def active(self):
        return [p for p in self.roster if not p.retired]

    def by_pos(self, pos):
        return sorted((p for p in self.active() if p.pos == pos),
                      key=lambda p: -p.ovr)

    def depth_at(self, pos):
        return len(self.by_pos(pos))

    @property
    def depth(self):
        d = {}
        for p in self.active():
            d.setdefault(p.pos, []).append(p)
        for pos in d:
            d[pos].sort(key=lambda p: -p.ovr)
        return d

    def starter(self, pos):
        g = self.by_pos(pos)
        return g[0] if g else None

    def contested_at_position(self, pos):
        """Two men close together at one spot: a real competition, and what
        negotiation_engine reads when a player asks about his role."""
        g = self.by_pos(pos)
        if len(g) < 2: return 0.0
        return float(np.clip(1.0 - (g[0].ovr - g[1].ovr) / 12.0, 0.0, 1.0))

    def roster_strength(self):
        """Mean of the starters, not the whole roster - a 90-man camp roster
        would otherwise drag every team toward the same number."""
        tops = [g[0].ovr for g in self.depth.values() if g]
        return float(np.mean(tops)) if tops else 0.0

    @property
    def avg_age(self):
        a = [p.age for p in self.active()]
        return float(np.mean(a)) if a else 0.0

    @property
    def top_apy(self):
        a = [p.apy for p in self.active()]
        return max(a) if a else 0.0

    @property
    def expiring(self):
        return [p for p in self.active() if p.expiring]

    @property
    def contender(self):
        """0-1, continuous. The window is never binary."""
        return float(np.clip(0.45 * self.win_pct + 0.35 * self.prev_win_pct +
                             0.20 * self.expected_pct, 0.0, 1.0))

    @property
    def cap_space(self):
        return self.cap.space(self.phase)

    phase = 'season'          # set by the League each time the calendar moves

    def sync_cap(self, year_index=0):
        """Rebuild the cap ledger from who is actually under contract."""
        self.cap.contracts = [(p.pid, p.contract, year_index)
                              for p in self.roster if p.contract]

    # ---- the dict shape the older engines take ---------------------------
    def ctx(self):
        """
        gm_engine, negotiation_engine and roster_construction were written
        against a plain dict. Rather than rewrite four modules, hand them one.
        """
        return dict(team=self.abbr, win_pct=self.win_pct,
                    prev_win_pct=self.prev_win_pct, contender=self.contender,
                    avg_age=self.avg_age, top_apy=self.top_apy,
                    expiring=self.expiring, depth=self.depth,
                    cap_space=self.cap_space, scheme=self.scheme,
                    tenure=self.tenure, job_security=(self.gm.job_security
                                                      if self.gm else 0.6))

    # ---- persistence -----------------------------------------------------
    def to_dict(self):
        return dict(abbr=self.abbr, division=self.division, conf=self.conf,
                    scheme=self.scheme, record=list(self.record),
                    history=self.history, tenure=self.tenure,
                    gm=(asdict(self.gm) if self.gm else None),
                    roster=[p.pid for p in self.roster],
                    practice_squad=[p.pid for p in self.practice_squad],
                    ir=[p.pid for p in self.ir],
                    picks=[asdict(k) for k in self.picks],
                    cap_year=self.cap.year, cap_rollover=self.cap.rollover,
                    cap_dead=self.cap.dead, cap_base=self.cap.cap)

    def __repr__(self):
        w, l, t = self.record
        return f'<{self.abbr} {w}-{l}{"-"+str(t) if t else ""}>'


# ================================================================== LEAGUE
class League:
    """
    The world. Owns every player, every team, the calendar and the record
    books. Nothing above this level exists.
    """

    def __init__(self, year=2026):
        self.year = year
        self.phase = 'preseason'
        self.week = 0
        self.players = {}                 # pid -> Player, INCLUDING retired
        self.teams = {}                   # abbr -> Team
        self.free_agents = []             # pid
        self.schedule = []                # (week, away, home, away_pts, home_pts)
        self.stats = {}                   # season -> pid -> line (REGULAR only)
        self.post_stats = {}              # season -> pid -> line (playoffs)
        self.game_stats = {}              # game key -> pid -> line
        self.standings_history = {}       # season -> abbr -> record
        self.transactions = []            # every move, ever
        self.awards = {}                  # season -> award -> pid
        self.rng_state = None

    # ---- lookups ---------------------------------------------------------
    def player(self, pid):
        return self.players.get(str(pid))

    def team_of(self, pid):
        p = self.player(pid)
        return self.teams.get(p.team) if p and p.team else None

    def roster_dicts(self, abbr):
        """The shape game.py wants: {qb, rb, wr, ol, dl, lb, db, k, p, kr}.
        Built from the live roster, so injuries and signings show up
        immediately instead of being frozen at load."""
        import rosters as R
        t = self.teams[abbr]
        return R.build_roster_rows([dict(p.ratings, pid=p.pid, pos=p.pos)
                                    for p in t.active()
                                    if p.out_until is None], t.scheme)

    # ---- stats: on the player AND in a league book ----------------------
    def record_stats(self, season, pid, line, postseason=False, game=None):
        """
        Regular and postseason are kept APART. Awards are voted on the regular
        season - the ballots are cast before the playoffs - so folding a
        playoff run into a season line would hand the award to whoever went
        deepest. Per-game lines are kept too, because Super Bowl MVP is a
        one-game award.
        """
        if game is not None:
            g = self.game_stats.setdefault(game, {}).setdefault(pid, {})
            for k, v in line.items():
                if isinstance(v, (int, float)): g[k] = g.get(k, 0) + v
        store = self.post_stats if postseason else self.stats
        store.setdefault(season, {}).setdefault(pid, {})
        book = store[season][pid]
        for k, v in line.items():
            if isinstance(v, (int, float)):
                book[k] = book.get(k, 0) + v
        if not postseason:
            p = self.player(pid)
            if p is not None:
                p.record_season(season, book)

    def leaders(self, season, stat, n=10):
        book = self.stats.get(season, {})
        rows = sorted(book.items(), key=lambda kv: -kv[1].get(stat, 0))[:n]
        return [(self.players[pid].name, v.get(stat, 0)) for pid, v in rows
                if pid in self.players]

    # ---- transactions ----------------------------------------------------
    def log(self, kind, **detail):
        self.transactions.append(dict(year=self.year, week=self.week,
                                      phase=self.phase, kind=kind, **detail))

    def sign(self, pid, abbr, contract):
        p = self.player(pid)
        if p.team and p.team in self.teams:
            self.release(pid, log=False)
        p.team, p.contract = abbr, contract
        self.teams[abbr].roster.append(p)
        if pid in self.free_agents: self.free_agents.remove(pid)
        self.log('sign', pid=pid, team=abbr, apy=p.apy, years=contract.years)

    def release(self, pid, june1=False, log=True):
        p = self.player(pid)
        t = self.teams.get(p.team)
        if t is None: return
        dead_now, dead_next, saved = (p.contract.release(0, june1)
                                      if p.contract else (0.0, 0.0, 0.0))
        t.cap.dead += dead_now
        if p in t.roster: t.roster.remove(p)
        p.team, p.contract = None, None
        if pid not in self.free_agents: self.free_agents.append(pid)
        if log:
            self.log('release', pid=pid, team=t.abbr, dead=dead_now, saved=saved)
        return dead_now, dead_next, saved

    def trade(self, a, b, a_sends, b_sends):
        """a_sends / b_sends: lists of pid or DraftPick."""
        for item, src, dst in [(x, a, b) for x in a_sends] + \
                              [(x, b, a) for x in b_sends]:
            if isinstance(item, DraftPick):
                self.teams[src].picks.remove(item)
                item.owner = dst
                self.teams[dst].picks.append(item)
            else:
                p = self.player(item)
                self.teams[src].roster.remove(p)
                p.team = dst
                self.teams[dst].roster.append(p)
        self.log('trade', a=a, b=b,
                 a_sends=[str(x) for x in a_sends],
                 b_sends=[str(x) for x in b_sends])

    # ---- calendar --------------------------------------------------------
    def set_phase(self, phase):
        """Cap accounting differs by phase - only the top 51 contracts count
        until week 1 - so every team has to know where the calendar is."""
        self.phase = phase
        for t in self.teams.values():
            t.phase = 'season' if phase in ('regular', 'playoffs') else phase

    def advance_phase(self):
        i = PHASES.index(self.phase)
        nxt = PHASES[(i + 1) % len(PHASES)]
        if nxt == 'preseason':
            self.year += 1
        self.set_phase(nxt)
        return self.phase

    # ---- persistence -----------------------------------------------------
    def to_dict(self):
        return dict(
            version=1, year=self.year, phase=self.phase, week=self.week,
            players={pid: p.to_dict() for pid, p in self.players.items()},
            teams={a: t.to_dict() for a, t in self.teams.items()},
            free_agents=self.free_agents, schedule=self.schedule,
            stats=self.stats, post_stats=self.post_stats,
            game_stats=self.game_stats,
            standings_history=self.standings_history,
            transactions=self.transactions, awards=self.awards,
            rng_state=self.rng_state)

    def save(self, path=None):
        """
        The whole franchise as text. Anything not written here is silently
        lost on reload, which is the kind of bug you do not notice until a
        save is twenty seasons deep - so everything goes, including the RNG
        state, or a reload mid-draft produces different picks than it was
        about to make.
        """
        blob = json.dumps(self.to_dict(), default=_json_default)
        if path:
            open(path, 'w').write(blob)
        return blob

    @classmethod
    def load(cls, blob):
        d = json.loads(blob) if isinstance(blob, str) else blob
        L = cls(d['year'])
        L.phase, L.week = d['phase'], d['week']
        L.players = {pid: Player.from_dict(pd)
                     for pid, pd in d['players'].items()}
        for abbr, td in d['teams'].items():
            t = Team(abbr, td['division'], td['conf'], d['year'],
                     scheme=td.get('scheme'))
            t.record = td['record']; t.history = td['history']
            t.tenure = td['tenure']
            t.gm = GM(**td['gm']) if td.get('gm') else None
            t.roster = [L.players[p] for p in td['roster'] if p in L.players]
            t.practice_squad = [L.players[p] for p in td['practice_squad']
                                if p in L.players]
            t.ir = [L.players[p] for p in td['ir'] if p in L.players]
            t.picks = [DraftPick(**k) for k in td['picks']]
            t.cap = TeamCap(td['cap_year'], td['cap_rollover'])
            t.cap.dead = td['cap_dead']
            # the solved base has to survive too: cap_engine's table carries
            # 301.0 for 2026 and the real figure is 301.2, and without this a
            # reloaded save drifts 0.2m per team away from its real position
            if td.get('cap_base') is not None:
                t.cap.cap = td['cap_base']
            t.sync_cap()
            L.teams[abbr] = t
        L.free_agents = d['free_agents']
        L.schedule = [tuple(g) for g in d['schedule']]
        L.stats = {int(k): v for k, v in d['stats'].items()}
        L.post_stats = {int(k): v for k, v in (d.get('post_stats') or {}).items()}
        L.game_stats = d.get('game_stats') or {}
        L.standings_history = {int(k): v for k, v
                               in d['standings_history'].items()}
        L.transactions = d['transactions']
        L.awards = {int(k): v for k, v in d['awards'].items()}
        L.rng_state = d['rng_state']
        return L

    def __repr__(self):
        return (f'<League {self.year} {self.phase} wk{self.week} '
                f'{len(self.teams)} teams {len(self.players)} players>')


# ================================================================== SEEDING
def _json_default(o):
    if isinstance(o, (np.integer,)): return int(o)
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, (np.ndarray,)): return o.tolist()
    if isinstance(o, set): return sorted(o)
    raise TypeError(f'not serialisable: {type(o)}')


def contract_to_dict(c):
    if c is None: return None
    return dict(years=c.years, base=list(c.base), signing_bonus=c.sb,
                roster_bonus=list(c.rb), guaranteed_years=c.gtd_yrs,
                void_years=c.void, signed=c.signed)


def contract_from_dict(d):
    return Contract(**d) if d else None


def morale_to_dict(m):
    if m is None: return None
    return dict(pid=m.pid, base=m.base, fast=m.fast, slow=m.slow,
                shock=m.shock, trust=m.trust, broken=m.broken, events=m.events)


def morale_from_dict(d):
    if not d: return None
    from morale_system import Morale
    m = Morale(d['pid'], d['base'])
    for k in ('fast', 'slow', 'shock', 'trust', 'broken', 'events'):
        setattr(m, k, d[k])
    return m


# Dev traits. "slow" was removed by decision - normal is the floor.
DEV_TIERS = ('normal', 'star', 'superstar', 'xfactor')


def _dev_from_seed(row, rng):
    """Madden ships an x_factor / ability flag; use it where it exists rather
    than inventing a distribution."""
    if str(row.get('x_factor', '')).strip() not in ('', 'nan', 'None', '0'):
        return 'xfactor'
    ovr = float(row.get('overall') or 70)
    if ovr >= 88: return 'superstar'
    if ovr >= 80: return 'star'
    return 'normal'


def build_league(seed_csv='league_seed_2026.csv', year=2026, rng=None,
                 standings_csv='schedule_2026.csv'):
    """
    Day one. Read the snapshot, build the world, then never read it again.

    Potential is set here and never moves for the rest of a career, which is
    how FM's potential ability works. Under-23s get a RANGE instead of a
    point, so the same prospect turns out differently in different saves.
    """
    import pandas as pd
    rng = rng or np.random.default_rng()
    S = pd.read_csv(seed_csv, low_memory=False)
    S = S[S.roster == 'active'].copy()
    rating_cols = [c for c in S.columns
                   if c.endswith('_rating') and c != 'src_rating']

    # divisions come off the schedule file, which carries them per team
    SCH = pd.read_csv(standings_csv, low_memory=False)
    div = {}
    for _, r in SCH.iterrows():
        div[r.home_team] = r.home_div
        div[r.away_team] = r.away_div

    L = League(year)
    for abbr in sorted(S.team.dropna().unique()):
        d = div.get(abbr, 'AFC East')
        L.teams[abbr] = Team(abbr, d, d.split()[0], year,
                             gm=make_gm(rng))

    for _, r in S.iterrows():
        ratings = {c: float(r[c]) for c in rating_cols if pd.notna(r[c])}
        age = float(r.age) if pd.notna(r.age) else 25.0
        ovr = float(r.overall) if pd.notna(r.get('overall')) else 70.0
        # a hard, hidden ceiling, fixed for life
        headroom = max(0.0, (28.0 - age)) * rng.uniform(0.35, 1.15)
        pot = float(np.clip(ovr + headroom, ovr, 99.0))
        prange = None
        if age <= 23:
            spread = rng.uniform(3.0, 11.0)
            prange = (round(max(ovr, pot - spread), 1),
                      round(min(99.0, pot + spread), 1))
            pot = None                       # resolved the first time he plays
        yrs = int(r.contract_years_left) if pd.notna(r.get('contract_years_left')) else 1
        apy = float(r.apy) if pd.notna(r.get('apy')) else 1.0
        gtd = float(r.guaranteed) if pd.notna(r.get('guaranteed')) else 0.0
        contract = None
        if yrs > 0:
            # Run it through the real structure builder. A flat apy-per-year
            # split makes every year-one cap hit equal the APY, which is not
            # how a deal works - real contracts prorate the signing bonus and
            # backload the base, so year one is well under the APY. The flat
            # version put the average team 38m over a 301m cap on day one.
            st = CS.structure(apy, yrs, r.madden_position, CAP.get(year, 301.0),
                              L.teams[r.team].gm if r.team in L.teams
                              else make_gm(rng))
            contract = Contract(years=yrs, base=st['base'],
                                signing_bonus=st['signing_bonus'],
                                guaranteed_years=1 if gtd > 0 else 0,
                                signed=int(r.year_signed) if pd.notna(r.get('year_signed')) else year)
        p = Player(r.pid, r.full_name, r.madden_position, age, ratings,
                   dev=_dev_from_seed(r, rng), potential=pot,
                   potential_range=prange,
                   longevity=float(np.clip(rng.normal(1.0, .22), .45, 1.7)),
                   team=r.team, contract=contract,
                   accrued=int(r.years_exp) if pd.notna(r.get('years_exp')) else 0,
                   draft_year=(int(r.draft_year) if pd.notna(r.get('draft_year')) else None),
                   draft_round=(int(r.draft_round) if pd.notna(r.get('draft_round')) else None),
                   draft_overall=(int(r.draft_overall) if pd.notna(r.get('draft_overall')) else None),
                   entry_year=(int(r.entry_year) if pd.notna(r.get('entry_year')) else None))
        L.players[p.pid] = p
        if r.team in L.teams:
            L.teams[r.team].roster.append(p)

    # ---- solve every team onto its REAL cap position -------------------
    # The seed has no per-year cap hit and no signing bonus, and neither does
    # any public dataset - so the per-player number is reconstructed. But the
    # TEAM total is published, and that is enough to pin the aggregate down.
    #
    # Two corrections come from the real data and could not have been reasoned
    # to. Dead money: the build carried none, and Miami alone is 182.6m, about
    # 60% of its cap, owed to men who are not on the roster. And every real
    # team is cap compliant on day one - the tightest is the Rams at 3.27m -
    # so a seed producing 17 teams over the cap was simply wrong.
    for abbr, t in L.teams.items():
        row = OTC.team_cap(abbr)
        if not row:
            continue
        space, active, dead, _n = row
        t.cap.cap = OTC.BASE_CAP_2026
        # carryover is not published directly, but space + spending + dead
        # pins the team's real limit exactly, and the base cap is known
        t.cap.rollover = round(OTC.team_limit(abbr) - OTC.BASE_CAP_2026, 3)
        t.cap.dead = dead
        t.sync_cap()
        current = sum(c.cap_hit(i) for _, c, i in t.cap.contracts)
        if current > 0:
            # hold each deal's SHAPE - proration, backloading, guarantee share
            # all survive - and move only the level, so the team lands on its
            # real year-one spending
            k = active / current
            for _, c, _i in t.cap.contracts:
                c.base = [b * k for b in c.base]
                c.rb = [r * k for r in c.rb]
                c.sb *= k

    # seven rounds, four years out, every pick owned by the team that earned it
    for abbr, t in L.teams.items():
        for yr in range(year, year + 4):
            for rd in range(1, 8):
                t.picks.append(DraftPick(yr, rd, abbr, abbr))
        t.sync_cap()

    # the real schedule, unplayed
    L.set_phase('preseason')
    L.schedule = [(int(r.week), r.away_team, r.home_team, None, None)
                  for _, r in SCH.iterrows()]
    return L


if __name__ == '__main__':
    L = build_league()
    print(L)
    t = L.teams['KC'] if 'KC' in L.teams else next(iter(L.teams.values()))
    print(t, '| strength %.1f' % t.roster_strength(),
          '| avg age %.1f' % t.avg_age,
          '| cap space %.1f' % t.cap_space,
          '| picks', len(t.picks))
    qb = t.starter('QB')
    print('QB:', qb, '| apy %.1f' % qb.apy, '| yrs', qb.contract_years_left,
          '| pot', qb.potential or qb.potential_range)
    blob = L.save()
    print('save: %.1f MB' % (len(blob) / 1e6))
    L2 = League.load(blob)
    print('reload:', L2, '| same QB:', L2.teams[t.abbr].starter('QB'))

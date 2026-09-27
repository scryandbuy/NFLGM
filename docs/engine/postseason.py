"""
THE POSTSEASON, AND CLOSING THE YEAR.

Three things happen here, and two of them have consequences that outlive the
season:

  THE BRACKET decides a champion. Wild card, divisional with RESEEDING, the
  conference championships, the Super Bowl. Playoff games run with playoffs=True
  so overtime uses 15-minute periods and repeats until somebody wins - the
  postseason never ties. There is no bye week inside the bracket, so health
  carries straight through: a team that comes out of a physical wild-card game
  plays the divisional round short.

  THE DRAFT ORDER is set here, and every pick in the league is already a real
  tradeable object waiting for its slot. Eighteen non-playoff teams in reverse
  order of record, then playoff teams slotted by how far they went - which is
  why this cannot happen until the bracket has run.

  FIRING happens here. firing_model was built and never called once. It takes
  exactly the hist dict a Team already exposes, so this is a call, not a port.
  Turnover is not quota'd: each club rolls its own chance off accumulated
  pressure, and the league lands where it lands.

WHAT IS DELIBERATELY SHALLOW: the GM hiring pool is tabled, so a fired man is
replaced by a freshly generated GM. That works, but every new regime is
anonymous and random rather than a named candidate with visible and hidden
attributes. Marked here so it is not mistaken for finished.

AWARDS ARE NOT COMPUTED. Omar defines them. They matter more than they look:
MVP, OROY, DROY, OPOY and DPOY are each a guaranteed +1 development tier, so
progression cannot be built until the rule exists. The league already stores
every stat line and every standing, so whatever rule lands has its data.
"""
import numpy as np

import standings_and_seeding as SS
import firing_model as FM
import ir_and_hiring as IH
from gm_engine import make_gm

ROUNDS = ('WC', 'DIV', 'CONF', 'SB')


class Postseason:
    """Runs the bracket on a SeasonRunner that has finished its schedule."""

    def __init__(self, runner):
        self.r = runner
        self.L = runner.L
        self.games = []          # (round, conf, home, away, home_pts, away_pts)
        self.champion = None
        self.finalists = {}      # conf -> team
        self.exit_round = {}     # team -> the round it lost in

    # ---- one playoff game ----------------------------------------------
    def _play(self, rnd, conf, home, away, week):
        # playoffs=True is what makes overtime use 15-minute periods and
        # repeat until somebody wins. The postseason never ties, so the
        # bracket can never stall, and playoff results do not touch a team's
        # regular-season record.
        res = self.r.play(home, away, week, playoffs=True)
        if res is None:
            return home
        self.games.append((rnd, conf, home, away, res['home'], res['away']))
        win = home if res['home'] >= res['away'] else away
        lose = away if win == home else home
        self.exit_round[lose] = rnd
        self.L.log('playoff', round=rnd, conf=conf, winner=win, loser=lose,
                   score=f"{res['home']}-{res['away']}")
        return win

    # ---- the bracket, one round at a time -------------------------------
    ROUNDS = ('WC', 'DIV', 'CONF', 'SB')
    ROUND_NAMES = {'WC': 'Wild Card', 'DIV': 'Divisional Round', 'CONF': 'Conference Championship', 'SB': 'Super Bowl'}

    def start(self):
        """Seed the bracket. State is plain data so a save can carry it between rounds."""
        seeds = self.r.seeds()
        self.seeds = {c: list(sd) for c, sd in seeds.items()}
        self.alive = {c: {i + 1: t for i, t in enumerate(sd)} for c, sd in seeds.items()}
        self.conf_champs = {}
        self.round_idx = 0

    def alive_now(self):
        """Every club still in the bracket."""
        if self.champion: return {self.champion}
        alive = {t for al in getattr(self, 'alive', {}).values() for t in al.values()}
        return alive | set(getattr(self, 'conf_champs', {}).values())

    def matchups(self, rnd):
        """(conf, home, away) for a round from the bracket as it stands."""
        out = []
        if rnd == 'SB':
            cs = list(self.conf_champs.values())
            if len(cs) == 2:
                a, b = sorted(cs, key=lambda t: -self.L.teams[t].win_pct)
                out.append(('NFL', a, b))
            return out
        for conf, alive in self.alive.items():
            if rnd == 'WC':
                for hi, lo in SS.wc_matchups(self.seeds[conf]):
                    out.append((conf, alive[hi], alive[lo]))
            elif rnd == 'DIV':
                order = sorted(alive); top, rest = order[0], order[1:]
                if len(rest) >= 3:
                    out.append((conf, alive[top], alive[rest[-1]])); out.append((conf, alive[rest[0]], alive[rest[1]]))
            elif rnd == 'CONF':
                order = sorted(alive)
                if len(order) >= 2: out.append((conf, alive[order[0]], alive[order[1]]))
        return out

    def record(self, rnd, conf, home, away, res):
        """A finished playoff game into the bracket, and its score into the schedule entry."""
        self.games.append((rnd, conf, home, away, res['home'], res['away']))
        wk_ = 19 + self.ROUNDS.index(rnd)
        for i, g in enumerate(self.L.schedule):
            if g[0] == wk_ and g[2] == home and g[1] == away: self.L.schedule[i] = (wk_, away, home, res['away'], res['home']); break
        win = home if res['home'] >= res['away'] else away
        lose = away if win == home else home
        self.exit_round[lose] = rnd
        self.L.log('playoff', round=rnd, conf=conf, winner=win, loser=lose, score=f"{res['home']}-{res['away']}")
        if rnd == 'SB':
            self.champion = win
        elif rnd == 'CONF':
            self.conf_champs[conf] = win; self.finalists[conf] = win
            self.alive[conf] = {s: t for s, t in self.alive[conf].items() if t == win}
        else:
            self.alive[conf] = {s: t for s, t in self.alive[conf].items() if t != lose}
        return win

    def schedule_round(self, rnd):
        """The round's games into the league schedule as weeks 19 to 22, so the report, the game plan, the rail and
        the strip find them the way they find a regular week's game."""
        wk_ = 19 + self.ROUNDS.index(rnd)
        have = {(g[1], g[2]) for g in self.L.schedule if g[0] == wk_}
        ms = self.matchups(rnd)
        for conf, home, away in ms:
            if (away, home) not in have: self.L.schedule.append((wk_, away, home, None, None))
        return ms

    def play_round(self, rnd, skip=None, week=None):
        """Play every game of the round except the one involving `skip` (the user's club, played live).
        Returns the skipped matchup as (conf, home, away) or None."""
        week = week if week is not None else 19 + self.ROUNDS.index(rnd)
        held = None
        for conf, home, away in self.matchups(rnd):
            if skip is not None and skip in (home, away):
                held = (conf, home, away); continue
            res = self.r.play(home, away, week, playoffs=True)
            if res is None: res = dict(home=1, away=0)
            self.record(rnd, conf, home, away, res)
        return held

    def to_dict(self):
        return dict(games=self.games, champion=self.champion, finalists=self.finalists, exit_round=self.exit_round,
                    seeds=getattr(self, 'seeds', {}), alive={c: {str(k): v for k, v in a.items()} for c, a in getattr(self, 'alive', {}).items()},
                    conf_champs=getattr(self, 'conf_champs', {}), round_idx=getattr(self, 'round_idx', 0), held=list(getattr(self, 'held', None) or []) or None)

    @classmethod
    def from_dict(cls, runner, d):
        p = cls(runner)
        p.games = [tuple(g) for g in d.get('games', [])]; p.champion = d.get('champion'); p.finalists = dict(d.get('finalists', {}))
        p.exit_round = dict(d.get('exit_round', {})); p.seeds = {c: list(v) for c, v in d.get('seeds', {}).items()}
        p.alive = {c: {int(k): v for k, v in a.items()} for c, a in d.get('alive', {}).items()}
        p.conf_champs = dict(d.get('conf_champs', {})); p.round_idx = int(d.get('round_idx', 0)); p.held = tuple(d['held']) if d.get('held') else None
        return p

    def run(self, verbose=False):
        seeds = self.r.seeds()
        week = 19
        conf_champs = {}
        for conf, sd in seeds.items():
            alive = {i + 1: t for i, t in enumerate(sd)}

            # wild card: the 1 seed sits out
            winners = {}
            for hi, lo in SS.wc_matchups(sd):
                w = self._play('WC', conf, alive[hi], alive[lo], week)
                winners[w] = min(hi, lo) if w == alive[min(hi, lo)] else max(hi, lo)
            # seed numbers of everyone still alive, 1 seed included
            left = {1: alive[1]}
            for t, s in winners.items():
                left[s] = t

            # divisional: RESEEDED. The top seed always draws the worst
            # survivor, which is the whole point of earning the bye.
            order = sorted(left)
            top, rest = order[0], order[1:]
            pairs = [(top, rest[-1]), (rest[0], rest[1])]
            semis = {}
            for hi, lo in pairs:
                w = self._play('DIV', conf, left[hi], left[lo], week + 1)
                semis[w] = hi if w == left[hi] else lo

            # conference championship
            a, b = sorted(semis, key=lambda t: semis[t])
            champ = self._play('CONF', conf, a, b, week + 2)
            conf_champs[conf] = champ
            self.finalists[conf] = champ
            if verbose:
                print(f'  {conf} champion: {champ}')

        # the Super Bowl. Home field is nominal; the better record hosts.
        cs = list(conf_champs.values())
        if len(cs) == 2:
            a, b = sorted(cs, key=lambda t: -self.L.teams[t].win_pct)
            self.champion = self._play('SB', 'NFL', a, b, week + 3)
            if verbose:
                print(f'  champion: {self.champion}')
        elif cs:
            self.champion = cs[0]
        return self.champion


# ================================================================ DRAFT ORDER
# How far a club went decides where it picks. Non-playoff teams first in
# reverse order of record, then the playoff field by exit round, which is why
# the order cannot be set until the bracket has run.
EXIT_RANK = {'WC': 0, 'DIV': 1, 'CONF': 2, 'SB': 3}


def set_draft_order(league, post, year=None):
    """
    Number every first-round pick, then mirror that order through rounds 2-7.

    Picks already exist as tradeable objects with an owner - a pick traded
    three years ago is already sitting in another team's drawer. This fills in
    the SLOT, and it fills it for the team that ORIGINALLY earned it, not the
    one holding it, which is how a traded pick keeps its real value.
    """
    year = year or league.year
    runner_seeds = post.r.seeds()
    in_playoffs = {t for sd in runner_seeds.values() for t in sd}

    def key(abbr):
        t = league.teams[abbr]
        if abbr not in in_playoffs:
            return (0, t.win_pct, t.record[0])
        if abbr == post.champion:
            rank = 4
        elif abbr in post.finalists.values():
            rank = 3.5
        else:
            rank = EXIT_RANK.get(post.exit_round.get(abbr, 'WC'), 0) + 1
        return (1, rank, t.win_pct)

    order = sorted(league.teams, key=key)
    for slot, abbr in enumerate(order, 1):
        for t in league.teams.values():
            for pk in t.picks:
                if pk.year == year and pk.original == abbr:
                    pk.selection = (pk.round - 1) * 32 + slot
    return order


# ================================================================== FIRING
def run_firings(league, rng, pool=None, verbose=False, clubs=None):
    """
    Every club rolls its own chance off accumulated pressure. No quota, no
    target turnover - the league lands where it lands, which is the point of
    having a pressure model at all.

    BLACK MONDAY. With `clubs` given, only those clubs roll (the ones whose season just ended), and the result is
    remembered so the season's close rolls only the clubs that have not yet. That is how the real market works:
    a club fires the day after it is eliminated, and the two Super Bowl clubs wait.
    """
    pool = pool if pool is not None else []
    fired = []
    done = league.__dict__.setdefault('_firings_rolled', {})
    yr = str(league.year); rolled = done.setdefault(yr, [])
    strengths = {a: t.roster_strength() for a, t in league.teams.items()}
    lo, hi = min(strengths.values()), max(strengths.values())
    # the clubs searching in the same week compete for the same names; the worst record moves first
    order = sorted(league.teams.items(), key=lambda kv: kv[1].win_pct)
    for abbr, t in order:
        if t.gm is None:
            continue
        if clubs is not None and abbr not in clubs: continue
        if abbr in rolled: continue
        rolled.append(abbr)
        # roster quality 0-1: a bad record with a bad roster is survivable
        rp = (strengths[abbr] - lo) / (hi - lo) if hi > lo else 0.5
        qb = t.starter('QB')
        qb_dev = bool(qb and qb.age <= 25 and qb.ovr >= 78)
        chance = FM.fire_chance_offseason(t.hist(), rp, qb_dev)
        if rng.random() < chance:
            if abbr == getattr(league, 'user_team', None):
                continue                      # the user is the man; his seat is his own story
            import coaching_pool as CP
            hired, reasons = CP.fire_and_hire(league, t, rng, verbose)
            bg = hired.background if hired is not None else 'pending a search'
            fired.append((abbr, bg))
            league.__dict__.setdefault('_fired_this_year', {}).setdefault(yr, []).append((abbr, bg))
        else:
            t.tenure += 1
            t.gm.tenure = t.tenure
            t.gm.job_security = float(np.clip(1.0 - chance, .05, .95))
    if verbose:
        print(f'  {len(fired)} of 32 made a change: '
              + ', '.join(f'{a}({s})' for a, s in fired))
    return fired


# ============================================================== CLOSE THE YEAR
def close_season(league, runner, rng, pool=None, verbose=False, post=None):
    """Bracket, champion, draft order, firings. Awards are NOT computed. With `post` given (a bracket already
    played round by round), only the closing runs."""
    league.set_phase('playoffs')
    if post is None:
        post = Postseason(runner)
        post.run(verbose)
    league.standings_history.setdefault(league.year, {})
    for abbr in league.teams:
        row = league.standings_history[league.year].get(abbr)
        if row is not None:
            row['exit'] = ('SB_WIN' if abbr == post.champion
                           else post.exit_round.get(abbr))
    order = set_draft_order(league, post)
    league.set_phase('offseason')
    fired = run_firings(league, rng, pool, verbose)                 # whoever has not rolled yet (the two finalists, or all 32 when the bracket was simmed at once)
    earlier = (league.__dict__.get('_fired_this_year', {}) or {}).get(str(league.year), [])
    seen = {a for a, _ in fired}
    fired = fired + [x for x in earlier if x[0] not in seen]
    league.log('season_end', champion=post.champion,
               top_pick=order[0], gm_changes=len(fired))
    return post, order, fired


if __name__ == '__main__':
    import league as LG, season as SN, time
    rng = np.random.default_rng(2026)
    L = LG.build_league(rng=rng)
    t0 = time.time()
    r = SN.run_season(L, rng)
    print('regular season %.0fs' % (time.time() - t0))
    post, order, fired = close_season(L, r, rng, verbose=True)
    print('\nplayoff games:', len(post.games))
    for g in post.games:
        print('  %-4s %-4s %-4s %2d - %-2d %-4s' % (g[0], g[1], g[2], g[4], g[5], g[3]))
    print('\ntop 5 picks:', order[:5])
    print('champion picks at:',
          [pk.selection for t in L.teams.values() for pk in t.picks
           if pk.year == L.year and pk.round == 1 and pk.original == post.champion])
    print('total %.0fs' % (time.time() - t0))


def provisional_slot(league, post, abbr):
    """Where a club picks in the first round, as far as the season has settled it: the eighteen that missed are
    fixed at week 18 by record; a round's losers are fixed once the round is complete; the finalists wait for the
    Super Bowl. None until the club's own season is over."""
    if post is None or not getattr(post, 'seeds', None): return None
    field = {t for sd in post.seeds.values() for t in sd}
    out = [a for a in league.teams if a not in field]
    key = lambda a: (league.teams[a].win_pct, league.teams[a].record[0])
    if abbr not in field:
        return sorted(out, key=key).index(abbr) + 1
    er = (getattr(post, 'exit_round', {}) or {}).get(abbr)
    if er is None:
        if post.champion == abbr: return 32
        return None
    rounds = ('WC', 'DIV', 'CONF', 'SB')
    need = {'WC': 6, 'DIV': 4, 'CONF': 2, 'SB': 1}[er]
    losers = [a for a, r in post.exit_round.items() if r == er]
    if len(losers) < need: return None                     # the round is not finished
    base = len(out) + sum({'WC': 6, 'DIV': 4, 'CONF': 2}[r] for r in rounds[:rounds.index(er)])
    return base + sorted(losers, key=key).index(abbr) + 1

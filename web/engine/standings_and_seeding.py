import pandas as pd, itertools
from collections import defaultdict, Counter

# Historical validation data. Optional: the live game never needs it, and the
# module used to fail at import without it, which is why nothing could call
# the tiebreaker chain.
try:
    G  = pd.read_csv('sched.csv', low_memory=False)
    ST = pd.read_csv('standings.csv', low_memory=False)
except Exception:
    G = ST = None

# ---------------------------------------------------------------- records
class Season:
    @classmethod
    def live(cls, div, conf, games, season=None):
        """
        A season in progress.

        The original constructor reads a FINISHED season out of a dataframe,
        which is right for validating the tiebreaker chain against real NFL
        history and useless for a franchise. This builds the same state from
        results as they happen, so the identical tiebreakers run on a live
        league.

        div/conf: {team: division}, {team: conference}
        games:    [(home, away, home_pts, away_pts)] - completed games only
        """
        S = cls.__new__(cls)
        S.season = season
        S.DIV, S.CONF = dict(div), dict(conf)
        S.teams = sorted(S.DIV)
        S.games = list(games)
        S.rec = defaultdict(lambda: [0, 0, 0])
        S.h2h = defaultdict(lambda: [0, 0, 0])
        S.opps = defaultdict(list)
        S.pf, S.pa = Counter(), Counter()
        for h, a, hs, as_ in S.games:
            res = 0 if hs == as_ else (1 if hs > as_ else -1)
            S._add(h, a, res); S._add(a, h, -res)
            S.pf[h] += hs; S.pa[h] += as_
            S.pf[a] += as_; S.pa[a] += hs
        return S

    def __init__(self, season):
        self.season = season
        s = ST[ST.season == season].set_index('team')
        self.DIV  = s.division.to_dict()
        self.CONF = s.conf.to_dict()
        self.teams = sorted(self.DIV)
        g = G[(G.season == season) & (G.game_type == 'REG')]
        g = g[g.home_score.notna()]
        self.games = [(r.home_team, r.away_team, r.home_score, r.away_score) for _, r in g.iterrows()]
        self.rec   = defaultdict(lambda: [0,0,0])          # W L T
        self.h2h   = defaultdict(lambda: [0,0,0])          # (a,b) from a's view
        self.opps  = defaultdict(list)
        self.pf, self.pa = Counter(), Counter()
        for h, a, hs, as_ in self.games:
            res = 0 if hs == as_ else (1 if hs > as_ else -1)
            self._add(h, a, res); self._add(a, h, -res)
            self.pf[h] += hs; self.pa[h] += as_; self.pf[a] += as_; self.pa[a] += hs

    def _add(self, t, o, res):
        i = 0 if res == 1 else (1 if res == -1 else 2)
        self.rec[t][i] += 1
        self.h2h[(t, o)][i] += 1
        self.opps[t].append(o)

    @staticmethod
    def pct(r):
        w, l, t = r
        n = w + l + t
        return (w + 0.5*t) / n if n else 0.0

    def wpct(self, t): return self.pct(self.rec[t])

    def _subset(self, t, keep):
        r = [0,0,0]
        for h, a, hs, as_ in self.games:
            if t not in (h, a): continue
            o = a if h == t else h
            if not keep(o): continue
            my, th = (hs, as_) if h == t else (as_, hs)
            r[0 if my > th else (1 if my < th else 2)] += 1
        return r

    def div_pct(self, t):  return self.pct(self._subset(t, lambda o: self.DIV[o] == self.DIV[t]))
    def conf_pct(self, t): return self.pct(self._subset(t, lambda o: self.CONF[o] == self.CONF[t]))

    def h2h_pct(self, t, group):
        r = [0,0,0]
        for o in group:
            if o == t: continue
            x = self.h2h[(t, o)]
            r = [r[i] + x[i] for i in range(3)]
        return self.pct(r) if sum(r) else None

    def h2h_sweep(self, t, group):
        """
        3+ clubs, different divisions: the sweep rule applies only if a club beat
        every other club in the tie, or lost to every other club. A club that did
        not play them all is simply neutral here - it must NOT void the step for
        the club that did sweep.
        """
        others = [o for o in group if o != t]
        played = [o for o in others if sum(self.h2h[(t, o)])]
        if len(played) != len(others): return 0
        p = self.h2h_pct(t, group)
        if p == 1.0: return 1
        if p == 0.0: return -1
        return 0

    def common_pct(self, t, group, minimum=4):
        common = set(self.opps[t])
        for o in group:
            if o != t: common &= set(self.opps[o])
        common -= set(group)
        r = self._subset(t, lambda o: o in common)
        return self.pct(r) if sum(r) >= minimum else None

    def sov(self, t):
        beaten = []
        for h, a, hs, as_ in self.games:
            if t == h and hs > as_: beaten.append(a)
            elif t == a and as_ > hs: beaten.append(h)
        return sum(self.wpct(o) for o in beaten) / len(beaten) if beaten else 0.0

    def sos(self, t):
        return sum(self.wpct(o) for o in self.opps[t]) / len(self.opps[t])

    def _combined_rank(self, t, pool):
        pf_rank = sorted(pool, key=lambda x: -self.pf[x]).index(t) + 1
        pa_rank = sorted(pool, key=lambda x: self.pa[x]).index(t) + 1
        return -(pf_rank + pa_rank)                    # higher is better
    def rank_conf(self, t):
        return self._combined_rank(t, [x for x in self.teams if self.CONF[x] == self.CONF[t]])
    def rank_all(self, t):
        return self._combined_rank(t, self.teams)
    def net_common(self, t, group):
        common = set(self.opps[t])
        for o in group:
            if o != t: common &= set(self.opps[o])
        common -= set(group)
        n = 0
        for h, a, hs, as_ in self.games:
            if t == h and a in common: n += hs - as_
            elif t == a and h in common: n += as_ - hs
        return n
    def net_all(self, t): return self.pf[t] - self.pa[t]

# ---------------------------------------------------------------- tiebreakers
def break_tie(S, group, same_division):
    """Returns the group ordered best-to-worst, applying NFL rules in order."""
    group = list(group)
    if len(group) == 1: return group

    if same_division:
        # 3+ clubs in the SAME division: head-to-head win pct among the tied clubs.
        # (The sweep rule is only for wild-card ties across divisions.)
        steps = [
            ('head-to-head',   lambda t: S.h2h_pct(t, group)),
            ('division',       lambda t: S.div_pct(t)),
            ('common',         lambda t: S.common_pct(t, group)),
            ('conference',     lambda t: S.conf_pct(t)),
            ('strength of victory',  S.sov),
            ('strength of schedule', S.sos),
            ('conf pts rank',  S.rank_conf),
            ('league pts rank', S.rank_all),
            ('net common',     lambda t: S.net_common(t, group)),
            ('net points',     S.net_all),
        ]
    else:
        steps = [
            ('head-to-head',   lambda t: S.h2h_pct(t, group) if len(group)==2 else S.h2h_sweep(t, group)),
            ('conference',     lambda t: S.conf_pct(t)),
            ('common',         lambda t: S.common_pct(t, group)),
            ('strength of victory',  S.sov),
            ('strength of schedule', S.sos),
            ('conf pts rank',  S.rank_conf),
            ('league pts rank', S.rank_all),
            ('net common',     lambda t: S.net_common(t, group)),
            ('net points',     S.net_all),
        ]

    for name, fn in steps:
        vals = {t: fn(t) for t in group}
        if any(v is None for v in vals.values()): continue
        best = max(vals.values())
        winners = [t for t in group if vals[t] == best]
        if len(winners) < len(group):
            rest = [t for t in group if t not in winners]
            return (break_tie(S, winners, same_division) if len(winners) > 1 else winners) + \
                   (break_tie(S, rest, same_division) if len(rest) > 1 else rest)
    return sorted(group)          # coin toss: deterministic fallback

def order(S, teams, same_division):
    out = []
    for _, grp in itertools.groupby(sorted(teams, key=lambda t: -S.wpct(t)), key=lambda t: S.wpct(t)):
        grp = list(grp)
        out += break_tie(S, grp, same_division) if len(grp) > 1 else grp
    return out

def division_ranks(S):
    r = {}
    for d in sorted(set(S.DIV.values())):
        ts = [t for t in S.teams if S.DIV[t] == d]
        for i, t in enumerate(order(S, ts, True), 1): r[t] = i
    return r

def seed_conference(S, conf, n_wc=None):
    """
    Division winners seed first, ordered by conference tiebreakers.
    Wild cards follow the real NFL procedure: eliminate all but the highest-ranked
    club in each division (division tiebreakers), rank the survivors by conference
    tiebreakers, award ONE spot, then repeat with the eliminated clubs back in.
    """
    if n_wc is None: n_wc = 3 if S.season >= 2020 else 2
    dr = division_ranks(S)
    winners = [t for t in S.teams if S.CONF[t] == conf and dr[t] == 1]
    seeds = order(S, winners, False)

    pool = [t for t in S.teams if S.CONF[t] == conf and dr[t] != 1]
    wc = []
    while len(wc) < n_wc and pool:
        bydiv = defaultdict(list)
        for t in pool: bydiv[S.DIV[t]].append(t)
        reps = [order(S, ts, True)[0] for ts in bydiv.values()]
        best = order(S, reps, False)[0]
        wc.append(best); pool.remove(best)
    return seeds + wc

# ---------------------------------------------------------------- validate
# Only ever run by hand. This used to execute AT IMPORT, so the module
# could not be imported at all without the historical CSVs present -
# which is why the full tiebreaker chain sat unused.
if __name__ == '__main__':
    print('=== VALIDATION vs real final standings and real playoff fields ===\n')
    tot_rank = hit_rank = tot_seed = hit_seed = 0
    bad_years = []
    for season in range(2002, 2026):
        real = ST[ST.season == season]
        if len(real) != 32: continue
        S = Season(season)
        if len(S.games) < 200: continue
        dr = division_ranks(S)
        rr = real.set_index('team').div_rank.to_dict()
        ok = sum(1 for t in dr if dr[t] == rr[t])
        tot_rank += 32; hit_rank += ok

        pl = G[(G.season == season) & (G.game_type != 'REG')]
        field = set(pl.home_team) | set(pl.away_team)
        mine = set(seed_conference(S, 'AFC') + seed_conference(S, 'NFC'))
        fok = len(mine & field)
        tot_seed += len(field); hit_seed += fok
        if ok < 32 or fok < len(field): bad_years.append((season, ok, fok, len(field)))
        print(f'  {season}: division ranks {ok}/32   playoff field {fok}/{len(field)}')

    print(f'\n  TOTAL division ranks: {hit_rank}/{tot_rank} ({hit_rank/tot_rank:.1%})')
    print(f'  TOTAL playoff field:  {hit_seed}/{tot_seed} ({hit_seed/tot_seed:.1%})')
    if bad_years: print(f'  seasons with any miss: {[b[0] for b in bad_years]}')

    # ---------------------------------------------------------------- bracket


def bracket(seeds):
    """seeds: list of 7 (or 6) teams, best first. Returns the round-by-round matchups."""
    n = len(seeds)
    alive = list(range(1, n + 1))                     # seed numbers
    rounds = []
    byes = 1 if n == 7 else 2
    # wild card: lowest remaining seeds play, top `byes` sit out
    wc = [(alive[i], alive[-(i - byes + 1)]) for i in range(byes, (n + byes) // 2)]
    rounds.append(('WC', wc))
    return rounds

def wc_matchups(seeds):
    n = len(seeds)
    if n == 7:  return [(2,7),(3,6),(4,5)]     # 2020 onward: one bye
    return [(3,6),(4,5)]                       # before 2020: two byes

# A second validation pass, historical data only. Same reason as above:
# this used to run at import.
if __name__ == '__main__':
    print('\n=== SEED ORDER: do our seeds predict the real wild-card matchups? ===')
    tot = hit = 0
    for season in range(2002, 2026):
        if len(ST[ST.season == season]) != 32: continue
        S = Season(season)
        if len(S.games) < 200: continue
        pl = G[(G.season == season) & (G.game_type == 'WC')]
        if not len(pl): continue
        for conf in ['AFC','NFC']:
            sd = seed_conference(S, conf)
            pairs = {tuple(sorted([a, b])) for a, b in wc_matchups(sd)}
            mine = {tuple(sorted([sd[a-1], sd[b-1]])) for a, b in wc_matchups(sd)}
            realp = {tuple(sorted([r.home_team, r.away_team])) for _, r in pl.iterrows()
                     if S.CONF[r.home_team] == conf}
            tot += len(realp); hit += len(mine & realp)
            # home team must be the better seed
        print(f'  {season}: ', end='')
        ok = 0; n = 0
        for conf in ['AFC','NFC']:
            sd = seed_conference(S, conf)
            mine = {tuple(sorted([sd[a-1], sd[b-1]])) for a, b in wc_matchups(sd)}
            realp = {tuple(sorted([r.home_team, r.away_team])) for _, r in pl.iterrows()
                     if S.CONF[r.home_team] == conf}
            ok += len(mine & realp); n += len(realp)
        print(f'wild-card matchups {ok}/{n}')
    print(f'\n  TOTAL wild-card matchups reproduced: {hit}/{tot} ({hit/tot:.1%})')

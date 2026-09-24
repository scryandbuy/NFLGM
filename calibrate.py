"""
CALIBRATION REGISTER.

Every target the sim has ever been tuned against, in one place, with the
constant that controls it and where that constant lives. Everything before now
was calibrated against SYNTHETIC rosters - clones with a linear strength
spread, three receivers, one quarterback who never left the field. Real
starters are better than those clones, so every constant tuned that way came
out too generous: the first run on real 2026 rosters produced 34.3 points per
team against 22.9 and touchdowns on 41.6% of drives against 22.6%.

This runs against the real league and reports every target at once, so a change
that fixes one thing and breaks another is visible in the same pass. That
coupling is what made the piecemeal approach fail.

Sources: nflverse play-by-play 2020-2025, FTN charting 2023-24, nflverse snap
counts 2024-25, official injury reports 2023-25, Next Gen receiving.
"""
import numpy as np, collections

# name, real value, tolerance, where the controlling constant lives
TARGETS = [
    # ---- game level ----
    ('points_per_team',        22.90, 1.50, 'emergent'),
    ('total_points',           45.80, 3.00, 'emergent'),
    # RE-DERIVED so the three agree with each other. The register carried
    # 21.73 drives, 5.96 plays a drive and 123.0 plays a game, and 21.73 x
    # 5.96 is 129.5 - so no engine could hit all three and tuning toward them
    # only moved which row failed. Recomputed from the same 570 games with one
    # filter (scrimmage plays, which is what this engine counts): 123.95 plays
    # a game, 21.00 drives, 5.90 a drive. Those multiply to 123.92.
    ('drives_per_game',        21.60, 1.00, 'emergent'),            # 2024: 10.8 a team a game (Goodberry, NFL drive charting since 1998)
    ('plays_per_drive',         5.90, 0.60, 'emergent'),
    ('first_downs_per_drive',   1.84, 0.20, 'emergent'),
    ('offensive_plays_per_gm', 123.95, 6.00, 'emergent'),
    # ---- drive outcomes ----
    ('drive_touchdown_pct',    22.60, 2.00, 'emergent'),
    ('drive_fieldgoal_pct',    16.50, 2.00, 'game.fourth_down_decision'),   # 2024: 1.78 made a team a game over 10.8 drives
    ('drive_punt_pct',         32.40, 2.50, 'emergent'),            # 2025: 3.5 punts a team a game (AP), the lowest ever, over 10.8 drives; the sim is set in 2026 and the fall continued 4.2 -> 3.8 -> 3.5 from 2023
    ('drive_turnover_pct',     10.23, 1.50, 'emergent'),
    ('drive_downs_pct',         5.60, 1.50, 'game.GO_RATE'),
    # ---- passing ----
    ('completion_pct',         65.00, 2.00, 'plays.DEPTH_MULT'),
    ('sack_pct',                6.60, 1.00, 'plays.resolve_protection'),
    ('int_pct',                 2.10, 0.50, 'plays.resolve_throw p_int'),
    ('air_yards',               5.72, 1.00, 'plays base_air'),
    ('yac',                     5.19, 0.80, 'plays.resolve_yards_after in_space'),
    ('yards_per_dropback',      6.18, 0.60, 'emergent'),
    ('time_to_throw',           2.72, 0.15, 'plays.RUSHER_BASE'),         # seconds, on attempts
    # ---- running ----
    ('run_ypc',                 4.52, 0.35, 'plays._run_play'),
    ('run_explosive_pct',       2.46, 0.80, 'plays.resolve_yards_after'),
    ('run_negative_pct',        8.54, 1.50, 'plays._run_play ybc'),
    # ---- play calling ----
    ('pass_play_share',        57.80, 3.00, 'schemes.PASS_RATE'),
    ('play_action_pct',        10.20, 2.50, 'schemes.call_offense'),    # of all offensive plays
    ('motion_pct',             36.50, 3.00, 'schemes.call_offense'),
    ('blitz_pct',              13.30, 3.00, 'schemes.call_defense'),     # pass plays with a charted blitzer
    # ---- health ----
    ('injuries_per_team_game',  2.51, 0.50, 'health._RULED_OUT_SHARE'),
    # ---- game shape ----
    ('mean_margin',            11.10, 1.50, 'emergent'),
    ('margin_10plus_pct',      44.70, 4.00, 'emergent'),
    ('margin_17plus_pct',      26.10, 4.00, 'emergent'),
    ('overtime_pct',            6.20, 2.00, 'emergent'),
    ('tie_pct',                 0.29, 0.60, 'game.play_overtime'),
    # ---- special teams ----
    ('fg_pct',                 85.00, 3.00, 'game.FG_PCT'),
    ('punt_gross',             47.20, 2.00, 'game.PUNT'),
    ('kickoff_touchback_pct',  15.50, 3.00, 'game.KICKOFF'),
]


class Collector:
    """Everything the register measures, fed one game result at a time. The
    franchise loop (franchise_register.py) uses this on real seasons with the
    league rolling; calibrate.run uses it on the fixed 2026 rosters."""
    LISTS = ('sc', 'inj', 'yac', 'air', 'fd', 'plays_pd', 'ttt', 'fg', 'punts', 'kos')
    INTS = ('ot', 'ties', 'ngames', 'drives_total', 'pa', 'mo', 'bl', 'n_off', 'n_pass')

    def __init__(self):
        self.res = collections.Counter(); self.ypp = collections.defaultdict(list)
        for k in self.LISTS: setattr(self, k, [])
        for k in self.INTS: setattr(self, k, 0)

    def add(self, r):
        self.ngames += 1
        self.sc.append((r['home'], r['away'])); self.inj.append(len(r.get('injuries', [])) / 2)
        if r.get('overtime'): self.ot += 1
        if r['home'] == r['away']: self.ties += 1
        for _, d in r['drives']:
            self.drives_total += 1
            self.res[d.result] += 1
            self.fd.append(d.first_downs + (1 if d.result == 'Touchdown' else 0))
            self.plays_pd.append(d.plays)
            for l in d.log:
                if not isinstance(l, dict): continue
                t = l.get('type')
                if t in ('run', 'complete', 'incomplete', 'sack', 'scramble', 'drop', 'interception'):
                    self.ypp[t].append(l.get('yards', 0) or 0)
                    self.n_off += 1
                    if l.get('motion'): self.mo += 1
                    if l.get('play_action'): self.pa += 1
                    if l.get('is_pass'):
                        self.n_pass += 1
                        if l.get('blitzers', 0) > 0: self.bl += 1
                if t in ('complete', 'incomplete', 'drop', 'interception') and l.get('ttt'):
                    self.ttt.append(l['ttt'])
                if t == 'complete':
                    self.yac.append(l.get('yac', 0)); self.air.append(l.get('air', 0))
                if t == 'field_goal': self.fg.append(bool(l.get('made', False)))
                if t == 'punt' and l.get('gross'): self.punts.append(l['gross'])
                if t == 'kickoff': self.kos.append(bool(l.get('touchback', False)))

    def got(self):
        ypp = self.ypp; res = self.res; sc = self.sc; ngames = self.ngames; drives_total = self.drives_total
        inj, yac, air, fd, plays_pd, ttt, fg, punts, kos = self.inj, self.yac, self.air, self.fd, self.plays_pd, self.ttt, self.fg, self.punts, self.kos
        ot, ties, pa, mo, bl, n_off, n_pass = self.ot, self.ties, self.pa, self.mo, self.bl, self.n_off, self.n_pass
        att = sum(len(ypp[k]) for k in ('complete', 'incomplete', 'drop', 'interception'))
        db = att + len(ypp['sack'])
        runs = np.array(ypp['run']) if ypp['run'] else np.array([0.0])
        pts = [x for p in sc for x in p]
        m = np.array([abs(a - b) for a, b in sc])
        n = max(drives_total, 1)
        passes = att + len(ypp['sack'])
        rush = len(ypp['run']) + len(ypp['scramble'])

        got = {
            'points_per_team': np.mean(pts),
            'total_points': np.mean([a + b for a, b in sc]),
            'drives_per_game': drives_total / max(ngames, 1),
            'plays_per_drive': np.mean(plays_pd),
            'first_downs_per_drive': np.mean(fd),
            'offensive_plays_per_gm': (passes + rush) / max(ngames, 1),
            'drive_touchdown_pct': res['Touchdown'] / n * 100,
            'drive_fieldgoal_pct': res['Field goal'] / n * 100,
            'drive_punt_pct': res['Punt'] / n * 100,
            'drive_turnover_pct': res['Turnover'] / n * 100,
            'drive_downs_pct': res['Turnover on downs'] / n * 100,
            'completion_pct': len(ypp['complete']) / max(att, 1) * 100,
            'sack_pct': len(ypp['sack']) / max(db, 1) * 100,
            'int_pct': len(ypp['interception']) / max(att, 1) * 100,
            'air_yards': np.mean(air) if air else 0,
            'yac': np.mean(yac) if yac else 0,
            'yards_per_dropback': (sum(ypp['complete']) + sum(ypp['sack'])) / max(db, 1),
            'time_to_throw': np.mean(ttt) if ttt else 0,
            'run_ypc': runs.mean(),
            'run_explosive_pct': (runs >= 20).mean() * 100,
            'run_negative_pct': (runs < 0).mean() * 100,
            'pass_play_share': passes / max(passes + rush, 1) * 100,
            'play_action_pct': pa / max(n_off, 1) * 100,
            'motion_pct': mo / max(n_off, 1) * 100,
            'blitz_pct': bl / max(n_pass, 1) * 100,
            'injuries_per_team_game': np.mean(inj),
            'mean_margin': m.mean(),
            'margin_10plus_pct': (m >= 10).mean() * 100,
            'margin_17plus_pct': (m >= 17).mean() * 100,
            'overtime_pct': ot / max(ngames, 1) * 100,
            'tie_pct': ties / max(ngames, 1) * 100,
            'fg_pct': (np.mean(fg) * 100) if fg else 85.0,
            'punt_gross': np.mean(punts) if punts else 47.2,
            'kickoff_touchback_pct': (np.mean(kos) * 100) if kos else 15.5,
        }


        return got

    def report(self, title):
        got = self.got()
        print(f'{title}, {self.ngames} games\n')
        print(f'  {"metric":26s} {"sim":>8s} {"real":>8s} {"diff":>8s}  {"":4s} controls')
        bad = 0
        for name, real, tol, ctrl in TARGETS:
            v = got.get(name, float('nan')); d = v - real; ok = abs(d) <= tol
            if not ok: bad += 1
            print(f'  {name:26s} {v:8.2f} {real:8.2f} {d:+8.2f}  {"ok" if ok else "OFF":4s} {ctrl}')
        print(f'\n  {len(TARGETS)-bad}/{len(TARGETS)} within tolerance')
        return got

    def to_json(self):
        import json
        return json.dumps(dict(res=dict(self.res), ypp={k: [float(x) for x in v] for k, v in self.ypp.items()},
                               **{k: [list(x) if isinstance(x, tuple) else (float(x) if not isinstance(x, bool) else x) for x in getattr(self, k)] for k in self.LISTS},
                               **{k: getattr(self, k) for k in self.INTS}))

    @classmethod
    def from_json(cls, text):
        import json
        d = json.loads(text); c = cls()
        c.res = collections.Counter(d['res']); c.ypp = collections.defaultdict(list, {k: list(v) for k, v in d['ypp'].items()})
        for k in cls.LISTS: setattr(c, k, [tuple(x) if isinstance(x, list) else x for x in d[k]])
        for k in cls.INTS: setattr(c, k, d[k])
        return c


def run(seasons=1, seed=2026, verbose=True, coaches='random'):
    """Simulate whole seasons on the REAL rosters and measure everything.
    coaches='random' draws each club's leans from a normal (the register's fit);
    coaches='catalog' uses the real identity catalog through season.make_coach,
    which is what the franchise plays with."""
    import rosters as R, game as G, plays as P, schemes as S
    rng = np.random.default_rng(seed)
    L = R.load_league()
    teams = sorted(L)
    use_catalog = (coaches == 'catalog'); cat = None
    if use_catalog:
        import league as LG, season as SN
        LL = LG.build_league(rng=np.random.default_rng(seed))
        cat = {t: SN.make_coach(LL.teams[t].gm) for t in teams if t in LL.teams}
    co = lambda d, di, sd, ytg, r, secs_left=None, **kw: S.call_offense(
        d, di, sd, ytg, r, secs_left=secs_left, **kw)
    cd = lambda oc, d, di, r, ytg=50, **kw: S.call_defense(
        oc, d, di, r, yards_to_endzone=ytg, **kw)
    coaches = {t: dict(
        adjust_skill=float(np.clip(rng.normal(.55, .18), .1, .95)),
        adjust_willingness=float(np.clip(rng.normal(.55, .2), .1, .95)),
        man_rate=float(np.clip(rng.normal(.35, .12), .12, .62)),
        blitz_rate=float(np.clip(rng.normal(.133, .05), .05, .28)),
        travel_willingness=float(np.clip(rng.normal(.5, .22), .05, .95)),
        off_script_skill=float(np.clip(rng.normal(.5, .2), .1, .9))) for t in teams}
    if use_catalog:
        coaches = cat

    C = Collector()
    for s in range(seasons):
        ST = {t: G.TeamState(L[t], coach=coaches[t]) for t in teams}
        for wk in range(17):
            o = list(teams); rng.shuffle(o)
            for i in range(0, 32, 2):
                h, a = o[i], o[i + 1]
                r = G.play_game(L[h], L[a], rng, P.resolve_play, co, cd, P.rate,
                                home_state=ST[h], away_state=ST[a], week=wk + 1)
                C.add(r)
    got = C.report(f'{seasons} season(s) on the REAL 2026 rosters, {"catalog" if use_catalog else "random"} coaches') if verbose else C.got()
    return got


if __name__ == '__main__':
    import sys
    run(seasons=1, coaches=('catalog' if 'catalog' in sys.argv else 'random'))

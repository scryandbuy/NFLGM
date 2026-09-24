"""
THE FRANCHISE REGISTER. calibrate.run replays the fixed 2026 rosters; this
plays the franchise itself, season after season, with newgens, aging,
retirements, the draft, free agency and the staff carousel all turning the
league over, and measures every game against the same targets.

Run in stretches so no single call runs long:
    python3 franchise_register.py new [seed]        start a franchise, clear tallies
    python3 franchise_register.py weeks N           play up to N stops (weeks/playoffs/offseason steps)
    python3 franchise_register.py report            print this season's and the cumulative register
State lives in /tmp/fr_session.json, /tmp/fr_collect_all.json, /tmp/fr_collect_season.json.
"""
import sys, os, json, time
import numpy as np
import session as S, calibrate as CB

P_SESS, P_ALL, P_SEA, P_LOG = '/tmp/fr_session.json', '/tmp/fr_collect_all.json', '/tmp/fr_collect_season.json', '/tmp/fr_log.json'


def _load():
    s = S.Session.load(open(P_SESS).read())
    C_all = CB.Collector.from_json(open(P_ALL).read()) if os.path.exists(P_ALL) else CB.Collector()
    C_sea = CB.Collector.from_json(open(P_SEA).read()) if os.path.exists(P_SEA) else CB.Collector()
    log = json.load(open(P_LOG)) if os.path.exists(P_LOG) else []
    return s, C_all, C_sea, log


def _save(s, C_all, C_sea, log):
    open(P_SESS, 'w').write(s.save()); open(P_ALL, 'w').write(C_all.to_json()); open(P_SEA, 'w').write(C_sea.to_json()); json.dump(log, open(P_LOG, 'w'))


def _hook(s, C_all, C_sea):
    """Every game the runner plays goes into both collectors."""
    r = s.runner
    if r is None or getattr(r, '_fr_hooked', False): return
    orig = r.play
    def play(home, away, week, playoffs=False):
        res = orig(home, away, week, playoffs)
        if res is not None and not playoffs:
            C_all.add(res); C_sea.add(res)
        return res
    r.play = play; r._fr_hooked = True


def _league_state(s):
    L = s.L
    tops = []
    for t in L.teams.values():
        men = sorted((p.ovr for p in t.active()), reverse=True)[:22]
        if men: tops.append(float(np.mean(men)))
    ages = [p.age for t in L.teams.values() for p in t.active()]
    return dict(year=L.year, players=len([p for p in L.players.values() if not p.retired]), starters_ovr=round(float(np.mean(tops)), 2), mean_age=round(float(np.mean(ages)), 2),
                cap_space=round(float(np.mean([t.cap_space for t in L.teams.values()])), 1), fa_pool=len(L.free_agents))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'report'
    if cmd == 'new':
        seed = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
        for p in (P_ALL, P_SEA, P_LOG):
            if os.path.exists(p): os.remove(p)
        s = S.Session.new('KC', seed=seed)
        log = [dict(event='start', **_league_state(s))]
        _save(s, CB.Collector(), CB.Collector(), log); print('new franchise, seed', seed, log[0]); return
    s, C_all, C_sea, log = _load()
    if cmd == 'weeks':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
        if 'noplan' in sys.argv:
            # the AI game-plan layer off: every club plays its coordinators' base plan all season
            import gameplan_week as GW
            GW.ai_plan = lambda league, state, me, opp, week, rng: (None, [])
        t0 = time.time()
        for _ in range(n):
            if s.stop[0] == 'week' and s.runner is None:
                s.runner = __import__('season').SeasonRunner(s.L, s.rng)
            _hook(s, C_all, C_sea)
            k = s.stop
            r = s.advance()
            if s.runner is not None: _hook(s, C_all, C_sea)
            print(f"  {r['done']:34s} {time.time()-t0:6.0f}s  games so far {C_sea.ngames}")
            if k[0] == 'playoffs':
                # the season is closed: the season's table, then reset the season collector
                got = C_sea.report(f"Season {s.L.year} (franchise)")
                log.append(dict(event='season', ngames=C_sea.ngames, got={k_: round(float(v), 3) for k_, v in got.items()}, **_league_state(s)))
                C_sea = CB.Collector()
            if r.get('done') == 'Cut-Down to 53':
                log.append(dict(event='rolled', **_league_state(s)))
                print('  league after the offseason:', log[-1])
            if time.time() - t0 > 215: print('  stopping this stretch'); break
        _save(s, C_all, C_sea, log)
        print('stop:', s.stop, '| next:', s.next_label()['title'])
        return
    if cmd == 'report':
        for e in log:
            if e['event'] != 'season': print(' ', e)
        C_all.report('All franchise seasons so far')
        return


if __name__ == '__main__':
    main()

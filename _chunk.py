import sys, time, numpy as np, league as LG, season as SN, franchise as FR, staff as ST, collections
t0 = time.time(); step = sys.argv[1]; path = '/home/claude/staff_state.json'
def load():
    L = LG.League.load(open(path).read()); L.user_team = None; return L
if step == 'build':
    L = LG.build_league(rng=np.random.default_rng(2026)); L.user_team = None
    import gameplan_week as GW
    try: GW.post_report(L, 1)
    except Exception: pass
    L.save(path); print(f'built, saved {time.time()-t0:.0f}s')
elif step.startswith('weeks'):
    a, b = map(int, step[5:].split('-'))
    L = load(); r = SN.SeasonRunner(L, np.random.default_rng(1000 + a + 100 * L.year))
    for wk in range(a, b + 1): r.play_week(wk)
    L.save(path); print(f'weeks {a}-{b} played, {time.time()-t0:.0f}s; KC {L.teams["KC"].record}')
elif step == 'offseason':
    L = load()
    before = {a: {r: (c.name if c else None) for r, c in t.staff.items()} for a, t in L.teams.items()}
    fr = FR.Franchise.__new__(FR.Franchise); fr.L = L; fr.rng = np.random.default_rng(77 + L.year); fr.user_team = None; fr.history = []
    SN.run_season = lambda league, rng=None, weeks=18, verbose=False: SN.SeasonRunner(league, rng)
    log = fr.play_year(report=False)
    after = {a: {r: (c.name if c else None) for r, c in t.staff.items()} for a, t in L.teams.items()}
    changed = sum(1 for a in L.teams if any(before[a][r] != after[a][r] for r in ('oc', 'dc', 'st')))
    reasons = collections.Counter(str(e.get('why')) for e in L.transactions if e.get('kind') == 'staff_out' and e.get('year') == L.year - 1)
    hc = sum(1 for e in L.transactions if e.get('kind') == 'staff_out' and 'hired as head coach' in str(e.get('why')))
    holes = sum(1 for t in L.teams.values() for c in t.staff.values() if c is None)
    print(f"year {L.year - 1}: clubs changing a coordinator {changed}/32 ({changed/32:.0%}) · moves {log.get('staff_moves')} · HC hires from coordinators (cum.) {hc} · holes {holes} · pool {len(L.staff_pool)} · fired HCs {log.get('fired')} · {time.time()-t0:.0f}s")
    print('   why they left:', dict(reasons))
    ranks = ST.unit_ranks(L, L.year - 1)
    oc = [(ST.rating(t, 'oc'), ranks[a]['oc']) for a, t in L.teams.items()]; dc = [(ST.rating(t, 'dc'), ranks[a]['dc']) for a, t in L.teams.items()]
    print(f"   OC rating vs offense rank corr {np.corrcoef([x for x,_ in oc],[y for _,y in oc])[0,1]:+.2f} · DC {np.corrcoef([x for x,_ in dc],[y for _,y in dc])[0,1]:+.2f} (negative = better coach, better unit)")
    cands = [c for t in L.teams.values() for c in t.staff.values() if c and c.hc_candidate]; print(f"   HC candidates among sitting coordinators: {len(cands)}")
    L.save(path)

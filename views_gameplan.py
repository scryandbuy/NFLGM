"""
GAME PLAN VIEWS. This Week (the sliders inside the coordinator's range, the
report's suggestions to accept, the game-week decisions) and the Opponent
Report (tendencies, unit ranks, the men who matter, what we would do).

The engine reads league.user_week_plan when the game is played; this page
writes it. A lean can move only as far from the coach's base as RANGE allows,
which is the same clamp the AI coordinators live under.
"""
import numpy as np
from views import club, rail

LEANS = [
    ('offense', 'pass_bias', 'Pass / Run', 'Run more', 'Pass more'),
    ('offense', 'play_action_rate', 'Play Action', 'Less', 'More'),
    ('offense', 'motion_rate', 'Motion', 'Still', 'Constant'),
    ('defense', 'blitz_rate', 'Blitz', 'Rush four', 'Send heat'),
    ('defense', 'man_rate', 'Coverage', 'Zone', 'Man'),
    ('defense', 'shell_lean', 'Safeties', 'Single high', 'Two high'),
    ('defense', 'zone_aggression', 'Underneath Zones', 'Sink', 'Sit on the quick game'),
    ('defense', 'box_bias', 'Box', 'Light', 'Loaded'),
]
DEPTH_LABELS = ('Short', 'Medium', 'Deep')
PROTECTIONS = ['half_slide', 'full_slide', 'six', 'empty']
PROT_WORDS = {'half_slide': 'Half slide', 'full_slide': 'Full slide', 'six': 'Six-man', 'empty': 'Empty'}


def _base_plan(session, league, abbr):
    import gameplan as GP, season as SN
    r = getattr(session, 'runner', None)
    st = r.states.get(abbr) if r is not None else None
    if st is not None and getattr(st, 'base_plan', None) is not None: return st.base_plan
    return GP.base_plan(SN.make_coach(league.teams[abbr].gm))


def _week(session, league):
    return session.stop[1] if session.stop[0] == 'week' else None


def _saved(league, week):
    wp = getattr(league, 'user_week_plan', None)
    if wp and wp.get('week') == week and wp.get('year') == league.year: return dict(wp.get('changes', {}))
    return {}


def _preview(base, changes):
    import gameplan_week as GW
    plan = base.copy(); GW.apply_changes(plan, base, changes); return plan


def this_week(session, league, abbr):
    import gameplan_week as GW
    wk = _week(session, league)
    r = rail(session, league, abbr)
    if wk is None: return dict(rail=r, off=True, note='The plan is set in season, the week before a game.')
    opp = session._opponent(wk)
    if opp is None: return dict(rail=r, off=True, bye=True, note=f'Week {wk} is your bye.')
    opp_abbr, away = opp
    base = _base_plan(session, league, abbr)
    changes = _saved(league, wk)
    plan = _preview(base, changes)
    rep = GW.opponent_report(league, abbr, opp_abbr, wk)
    leans = []
    for side, k, label, lo, hi in LEANS:
        b = float(getattr(base, k)); rng_ = GW.RANGE[k]
        leans.append(dict(side=side, key=k, label=label, lo=lo, hi=hi, base=round(b, 3), value=round(float(getattr(plan, k)), 3), min=round(b - rng_, 3), max=round(b + rng_, 3), range=rng_,
                          delta=round(float(changes.get(k, 0.0)), 3) if isinstance(changes.get(k, 0.0), (int, float)) else 0.0))
    sugg = []
    for i, s in enumerate(rep['suggestions']):
        taken = all(_change_in(changes, k, v) for k, v in s['changes'].items())
        sugg.append(dict(i=i, side=('offense' if s['side'] == 'offence' else 'defense'), text=s['text'], why=s['why'], changes={k: (list(v) if isinstance(v, tuple) else v) for k, v in s['changes'].items()}, taken=taken))
    bracket = plan.bracket; bp = league.player(bracket) if bracket else None
    their_wrs = [dict(pid=p.pid, name=p.name, ovr=round(p.ovr)) for p in league.teams[opp_abbr].depth.get('WR', [])[:3] if p.out_until is None]
    import staff as ST
    t = league.teams[abbr]
    return dict(rail=r, off=False, week=wk, opp=club(opp_abbr), away=away, leans=leans,
                depth=dict(base=[round(float(x), 3) for x in base.depth_mix], value=[round(float(x), 3) for x in plan.depth_mix], labels=list(DEPTH_LABELS)),
                protection=dict(base=base.protection, value=plan.protection, options=[dict(key=k, word=PROT_WORDS[k]) for k in PROTECTIONS]),
                travel=bool(plan.travel), bracket=(dict(pid=bp.pid, name=bp.name) if bp else None), their_wrs=their_wrs,
                suggestions=sugg, changes={k: (list(v) if isinstance(v, tuple) else v) for k, v in changes.items()},
                coordinators=dict(oc=_coord(t, 'oc'), dc=_coord(t, 'dc')), coach=rep['coach'], forecast=rep.get('forecast'))


def _coord(t, role):
    c = (getattr(t, 'staff', None) or {}).get(role)
    return dict(name=c.name, rating=round(c.rating)) if c else None


def _change_in(changes, k, v):
    cur = changes.get(k)
    if cur is None: return False
    if isinstance(v, (tuple, list)): return all(abs(float(a) - float(b)) < 1e-6 for a, b in zip(cur, v))
    if isinstance(v, (int, float)) and isinstance(cur, (int, float)): return abs(float(cur) - float(v)) < 1e-6
    return cur == v


def _merge(changes, add):
    """Suggestion deltas stack; a slider sets its delta outright."""
    out = dict(changes)
    for k, v in add.items():
        if k == 'depth_mix':
            cur = out.get('depth_mix', (0.0, 0.0, 0.0)); out['depth_mix'] = tuple(float(a) + float(b) for a, b in zip(cur, v))
        elif k in ('protection', 'travel', 'bracket'): out[k] = v
        elif k == 'screen_boost': out[k] = float(out.get(k, 0.0)) + float(v)
        else: out[k] = float(out.get(k, 0.0)) + float(v)
    return out


def act_take(session, league, abbr, i):
    import gameplan_week as GW
    wk = _week(session, league); opp = session._opponent(wk)
    rep = GW.opponent_report(league, abbr, opp[0], wk)
    if int(i) >= len(rep['suggestions']): return dict(ok=False, why='that suggestion is gone')
    s = rep['suggestions'][int(i)]
    changes = _merge(_saved(league, wk), s['changes'])
    GW.set_user_plan(league, wk, changes)
    return dict(ok=True, line=f"Taken: {s['text']}.")


def act_untake(session, league, abbr, i):
    import gameplan_week as GW
    wk = _week(session, league); opp = session._opponent(wk)
    rep = GW.opponent_report(league, abbr, opp[0], wk)
    s = rep['suggestions'][int(i)]
    neg = {k: (tuple(-float(x) for x in v) if isinstance(v, (tuple, list)) else (-float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None)) for k, v in s['changes'].items()}
    changes = _saved(league, wk)
    for k, v in neg.items():
        if v is None: changes.pop(k, None)
        else: changes = _merge(changes, {k: v})
    changes = {k: v for k, v in changes.items() if not (isinstance(v, float) and abs(v) < 1e-9) and not (isinstance(v, tuple) and all(abs(x) < 1e-9 for x in v))}
    GW.set_user_plan(league, wk, changes)
    return dict(ok=True, line=f"Put back: {s['text']}.")


def act_set_lean(session, league, abbr, key, value):
    """A slider: the value the user wants, stored as the delta from the coach's base, clamped to the range."""
    import gameplan_week as GW
    wk = _week(session, league)
    base = _base_plan(session, league, abbr)
    if key not in GW.RANGE: return dict(ok=False, why='not a lean')
    b = float(getattr(base, key)); d = float(np.clip(float(value) - b, -GW.RANGE[key], GW.RANGE[key]))
    changes = _saved(league, wk); changes[key] = d
    if abs(d) < 1e-9: changes.pop(key, None)
    GW.set_user_plan(league, wk, changes)
    return dict(ok=True, value=round(b + d, 3))


def act_set_depth(session, league, abbr, short, medium, deep):
    import gameplan_week as GW
    wk = _week(session, league); base = _base_plan(session, league, abbr)
    want = np.array([float(short), float(medium), float(deep)]); want = want / want.sum()
    changes = _saved(league, wk); changes['depth_mix'] = tuple(float(x) for x in (want - np.array(base.depth_mix)))
    GW.set_user_plan(league, wk, changes); return dict(ok=True)


def act_set_decision(session, league, abbr, key, value):
    import gameplan_week as GW
    wk = _week(session, league); changes = _saved(league, wk)
    if key == 'protection':
        if value in PROTECTIONS: changes['protection'] = value
        else: changes.pop('protection', None)
    elif key == 'travel': changes['travel'] = bool(value)
    elif key == 'bracket':
        if value: changes['bracket'] = value
        else: changes.pop('bracket', None)
    GW.set_user_plan(league, wk, changes); return dict(ok=True)


def act_reset(session, league, abbr):
    import gameplan_week as GW
    wk = _week(session, league); GW.set_user_plan(league, wk, {}); return dict(ok=True, line="Back to the coordinators' plan.")


# ------------------------------------------------------------ the report
def report(session, league, abbr):
    import gameplan_week as GW
    wk = _week(session, league); r = rail(session, league, abbr)
    if wk is None: return dict(rail=r, off=True, note='The report comes in season, the week before a game.')
    opp = session._opponent(wk)
    if opp is None: return dict(rail=r, off=True, note=f'Week {wk} is your bye.')
    opp_abbr, away = opp
    rep = GW.opponent_report(league, abbr, opp_abbr, wk)
    n = len(league.teams)
    def tend(t):
        if not t: return None
        return dict(pass_rate=round(t['pass_rate'] * 100), pa_rate=round(t['pa_rate'] * 100), motion=round(t['motion'] * 100), deep=round(t['deep'] * 100), fourth_go=round(t['fourth_go'] * 100),
                    blitz=round(t['blitz'] * 100), man=round(min(1.0, t['man']) * 100), two_high=round(t['two_high'] * 100), box8=round(t['box8'] * 100), games=round(t['games'], 1))
    lg = _league_tend(league)
    units = [dict(unit=u, rank=v[0], of=v[1]) for u, v in (rep['units'] or {}).items()]
    mine = [dict(unit=u, rank=v[0], of=v[1]) for u, v in (rep['my_units'] or {}).items()]
    changes = _saved(league, wk)
    sugg = [dict(i=i, side=('offense' if s['side'] == 'offence' else 'defense'), text=s['text'], why=s['why'], taken=all(_change_in(changes, k, v) for k, v in s['changes'].items())) for i, s in enumerate(rep['suggestions'])]
    return dict(rail=r, off=False, week=wk, opp=club(opp_abbr), away=away, coach=rep['coach'], tendencies=tend(rep['tendencies']), mine_tend=tend(rep['my_tendencies']), league_tend=lg,
                units=units, my_units=mine, stars=rep['stars'], injured=rep['injured'], strengths=[s['text'] for s in rep['strengths']], weaknesses=[w['text'] for w in rep['weaknesses']],
                suggestions=sugg, forecast=rep.get('forecast'), record=_rec(league, opp_abbr))


def _rec(league, a):
    w, l, d = league.teams[a].record
    return f"{w}–{l}" + (f"–{d}" if d else '')


def _league_tend(league):
    import gameplan_week as GW
    rows = [GW.tendencies(league, a) for a in league.teams]
    rows = [t for t in rows if t]
    if not rows: return None
    keys = ('pass_rate', 'pa_rate', 'motion', 'deep', 'fourth_go', 'blitz', 'man', 'two_high', 'box8')
    return {k: round(float(np.mean([min(1.0, t[k]) for t in rows])) * 100) for k in keys}

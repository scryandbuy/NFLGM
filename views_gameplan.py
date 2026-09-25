"""
GAME PLAN VIEWS. This Week (the sliders inside the coordinator's range, the
report's suggestions to accept, the game-week decisions) and the Opponent
Report (tendencies, unit ranks, the men who matter, what we would do).

The engine reads league.user_week_plan when the game is played; this page
writes it. A lean can move only as far from the coach's base as RANGE allows,
which is the same clamp the AI coordinators live under.
"""
import numpy as np
from views import club, rail, sentence

LEANS = [
    ('offense', 'pass_bias', 'Pass Lean', 'Run more', 'Pass more', 'Share of early-down calls that are passes'),
    ('offense', 'play_action_rate', 'Play Action', 'Less', 'More', 'Off the run game'),
    ('offense', 'motion_rate', 'Motion', 'Still', 'Constant', 'Pre-snap movement rate'),
    ('offense', 'tempo', 'Tempo', 'Huddle', 'Hurry', 'Huddle · Normal · Hurry'),
    ('defense', 'blitz_rate', 'Blitz Rate', 'Rush four', 'Send heat', 'Five or more rushers'),
    ('defense', 'man_rate', 'Man Coverage', 'Zone', 'Man', 'Share of coverage snaps in man'),
    ('defense', 'shell_lean', 'Shell', 'Single high', 'Two high', 'Single-High · Two-High'),
    ('defense', 'zone_aggression', 'Zone Aggression', 'Stay home', 'Drive on the throw', 'Drive on the throw or stay home'),
    ('defense', 'box_bias', 'Box', 'Light', 'Loaded', 'Players near the line against the run'),
]


def _lean_word(k, val):
    """The value as the page shows it: a percentage where the lean is a rate, a word where it is a shape."""
    if k == 'pass_bias': return f"{round(50 + val * 100)}%"
    if k in ('play_action_rate', 'motion_rate', 'blitz_rate', 'man_rate'): return f"{round(min(1.0, max(0.0, val)) * 100)}%"
    if k == 'tempo': return 'Huddle' if val < 0.4 else 'Hurry' if val > 0.6 else 'Normal'
    if k == 'shell_lean': return '1-Hi' if val < 0.42 else '2-Hi' if val > 0.58 else 'Mixed'
    if k == 'zone_aggression': return str(round(val * 100))
    if k == 'box_bias': return str(round(7 + val * 2))
    return f"{val:.2f}"
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
    return session.stop[1] if session.stop[0] == 'week' else 1 if session.stop[0] in ('cutdown', 'wire') else None


def _saved(league, week):
    wp = getattr(league, 'user_week_plan', None)
    if wp and wp.get('week') == week and wp.get('year') == league.year: return dict(wp.get('changes', {}))
    return {}


def _taken(league, week):
    wp = getattr(league, 'user_week_plan', None)
    if wp and wp.get('week') == week and wp.get('year') == league.year: return list(wp.get('taken', []))
    return []


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
    # where the assistants would put each lean, from the suggestions not yet taken (the gold ghost)
    ghost = {}
    for s in rep['suggestions']:
        if s['text'] in _taken(league, wk): continue
        for ck, cv in (s.get('changes') or {}).items():
            if ck in GW.RANGE and isinstance(cv, (int, float)) and not isinstance(cv, bool): ghost[ck] = ghost.get(ck, 0.0) + float(cv)
    for side, k, label, lo, hi, desc in LEANS:
        b = float(getattr(base, k)); rng_ = GW.RANGE[k]; val = float(getattr(plan, k))
        g = (max(b - rng_, min(b + rng_, val + ghost[k])) if k in ghost else None)
        leans.append(dict(side=side, key=k, label=label, lo=lo, hi=hi, desc=desc, base=round(b, 3), value=round(val, 3), word=_lean_word(k, val), min=round(b - rng_, 3), max=round(b + rng_, 3), range=rng_,
                          delta=round(float(changes.get(k, 0.0)), 3) if isinstance(changes.get(k, 0.0), (int, float)) else 0.0, ghost=(round(g, 3) if g is not None else None), ghost_word=(_lean_word(k, g) if g is not None else None)))
    from views import _change_words
    def target_words(s):
        out = []
        for ck, cv in (s.get('changes') or {}).items():
            if ck in GW.RANGE and isinstance(cv, (int, float)) and not isinstance(cv, bool):
                cur = float(getattr(plan, ck)); b = float(getattr(base, ck)); tgt = max(b - GW.RANGE[ck], min(b + GW.RANGE[ck], cur + float(cv)))
                out.append(f"{dict((x[1], x[2]) for x in LEANS).get(ck, ck)} to {_lean_word(ck, tgt)}")
            elif ck == 'depth_mix': d = list(cv); out.append('Depth toward ' + ['short', 'medium', 'deep'][max(range(3), key=lambda j: d[j])])
            elif ck == 'protection': out.append(f"Protection {str(cv).replace('_', ' ')}")
            elif ck == 'travel': out.append('Shadow their WR1' if cv else 'No shadow')
            elif ck == 'bracket': out.append('Bracket their WR1')
        return ' · '.join(out)
    sugg = []
    for i, s in enumerate(rep['suggestions']):
        taken = s['text'] in _taken(league, wk)
        sugg.append(dict(i=i, side=('offense' if s['side'] == 'offence' else 'defense'), text=sentence(s['text']), why=sentence(s['why']), target=target_words(s), changes={k: (list(v) if isinstance(v, tuple) else v) for k, v in s['changes'].items()}, taken=taken))
    bracket = plan.bracket; bp = league.player(bracket) if bracket else None
    their_wrs = [dict(pid=p.pid, name=p.name, ovr=round(p.ovr)) for p in league.teams[opp_abbr].depth.get('WR', [])[:3] if p.out_until is None]
    wr_out = [p.name.split()[-1] for p in league.teams[opp_abbr].depth.get('WR', [])[:2] if p.out_until is not None]
    import staff as ST
    t = league.teams[abbr]
    return dict(rail=r, off=False, week=wk, opp=club(opp_abbr), away=away, leans=leans,
                depth=dict(base=[round(float(x), 3) for x in base.depth_mix], value=[round(float(x), 3) for x in plan.depth_mix], labels=list(DEPTH_LABELS)),
                protection=dict(base=base.protection, value=plan.protection, options=[dict(key=k, word=PROT_WORDS[k]) for k in PROTECTIONS]),
                travel=bool(plan.travel), travel_target=(dict(pid=tp.pid, name=tp.name) if (tp := league.player(changes.get('travel_target'))) else None), my_cb1=_cb1(league, t), bracket=(dict(pid=bp.pid, name=bp.name) if bp else None), their_wrs=their_wrs, wr_out=wr_out,
                suggestions=sugg, changes={k: (list(v) if isinstance(v, tuple) else v) for k, v in changes.items()},
                coordinators=dict(oc=_coord(t, 'oc'), dc=_coord(t, 'dc')), coach=rep['coach'], forecast=rep.get('forecast'))


def _cb1(league, t):
    cbs = sorted((p for p in t.active() if p.pos == 'CB' and p.out_until is None), key=lambda p: -p.ovr)
    return dict(pid=cbs[0].pid, name=cbs[0].name.split()[-1]) if cbs else None


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
    if s['text'] in _taken(league, wk): return dict(ok=True, line='Already taken.')
    changes = _merge(_saved(league, wk), s['changes'])
    GW.set_user_plan(league, wk, changes, taken=_taken(league, wk) + [s['text']])
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
    GW.set_user_plan(league, wk, changes, taken=[t for t in _taken(league, wk) if t != s['text']])
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
    elif key == 'travel_target':
        if value: changes['travel_target'] = value; changes['travel'] = True
        else: changes.pop('travel_target', None)
    elif key == 'bracket':
        if value: changes['bracket'] = value
        else: changes.pop('bracket', None)
    GW.set_user_plan(league, wk, changes); return dict(ok=True)


def act_reset(session, league, abbr):
    import gameplan_week as GW
    wk = _week(session, league); GW.set_user_plan(league, wk, {}, taken=[]); return dict(ok=True, line="Back to the coordinators' plan.")


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
    ROWS = [('Pass Offense', 'QB'), ('Run Offense', 'backs'), ('Pass Defense', 'corners'), ('Run Defense', 'run front'), ('Pass Block', 'pass block'), ('Pass Rush', 'pass rush'), ('Receivers', 'receivers'), ('Corners', 'corners')]
    U, M = rep['units'] or {}, rep['my_units'] or {}
    unit_table = [dict(label=lab, mine=(M[k][0] if k in M else None), theirs=(U[k][0] if k in U else None)) for lab, k in ROWS]
    panels = None
    try:
        import views as V
        pv = V._matchup(session, league, abbr)
        panels = pv.get('panels') if pv else None
    except Exception: panels = None
    changes = _saved(league, wk)
    from views import _change_words
    sugg = [dict(i=i, side=('offense' if s['side'] == 'offence' else 'defense'), text=sentence(s['text']), why=sentence(s['why']), change=_change_words(s.get('changes')), taken=(s['text'] in _taken(league, wk))) for i, s in enumerate(rep['suggestions'])]
    return dict(rail=r, off=False, week=wk, opp=club(opp_abbr), away=away, coach=rep['coach'], tendencies=tend(rep['tendencies']), mine_tend=tend(rep['my_tendencies']), league_tend=lg,
                units=units, my_units=mine, unit_table=unit_table, panels=panels, stars=rep['stars'], injured=rep['injured'], strengths=[sentence(s['text']) for s in rep['strengths']], weaknesses=[sentence(w['text']) for w in rep['weaknesses']],
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

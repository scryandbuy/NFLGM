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
    ('offense', 'pass_bias', 'Run–Pass Balance', 'Run more', 'Pass more', 'Run more · Balanced · Pass more'),
    ('offense', 'play_action_rate', 'Play Action', 'Less', 'More', 'Less · Standard · More'),
    ('offense', 'motion_rate', 'Motion', 'Less', 'More', 'Less · Standard · More'),
    ('offense', 'tempo', 'Tempo', 'Slower', 'Faster', 'Slower · Normal · Faster'),
    ('defense', 'blitz_rate', 'Blitz Frequency', 'Less', 'More', 'Less · Standard · More'),
    ('defense', 'man_rate', 'Coverage Preference', 'Favor zone', 'Favor man', 'Favor zone · Mixed · Favor man'),
    ('defense', 'shell_lean', 'Safety Alignment', 'Favor single-high', 'Favor two-high', 'Favor single-high · Mixed · Favor two-high'),
    ('defense', 'zone_aggression', 'Zone Aggression', 'Protect deeper routes', 'Attack short routes', 'Protect deeper routes · Balanced · Attack short routes'),
    ('defense', 'box_bias', 'Box', 'Light', 'Loaded', 'Tendency to move defenders out of or into the situational box; actual counts stay between 4 and 10'),
]


def _lean_word(k, val):
    """Preferences, not forecasts of the percentage of plays called."""
    if k == 'pass_bias': return 'Run more' if val < -0.02 else 'Pass more' if val > 0.02 else 'Balanced'
    if k in ('play_action_rate', 'motion_rate', 'blitz_rate'):
        # Centers match the engine's neutral settings; these are display bands only.
        center = {'play_action_rate': 0.5, 'motion_rate': 0.581, 'blitz_rate': 0.133}[k]
        return 'Less' if val < center - 0.02 else 'More' if val > center + 0.02 else 'Standard'
    if k == 'man_rate': return 'Favor zone' if val < 0.42 else 'Favor man' if val > 0.58 else 'Mixed'
    if k == 'tempo': return 'Slower' if val < 0.4 else 'Faster' if val > 0.6 else 'Normal'
    if k == 'shell_lean': return 'Favor single-high' if val < 0.42 else 'Favor two-high' if val > 0.58 else 'Mixed'
    if k == 'zone_aggression': return 'Protect deeper routes' if val < 0.42 else 'Attack short routes' if val > 0.58 else 'Balanced'
    if k == 'box_bias':
        shift = round(abs(val) * 4, 6)
        if not shift: return 'Situational box'
        direction = 'Lighter' if val < 0 else 'Heavier'
        if shift <= 1: return f'{direction} box · {round(shift * 100)}% tendency'
        # Larger settings move at least one defender on every snap, rather than
        # implying an impossible probability above 100 percent.
        return f'{direction} box · {shift:g} defenders on average'
    return f"{val:.2f}"
DEPTH_LABELS = ('Short', 'Medium', 'Deep')
PROTECTIONS = ['half_slide', 'full_slide', 'six', 'empty']
PROT_WORDS = {'half_slide': 'Half slide', 'full_slide': 'Full slide', 'six': 'Six-man', 'empty': 'Empty'}


def _base_plan(session, league, abbr):
    import gameplan as GP, season as SN
    r = getattr(session, 'runner', None)
    if r is not None: r.refresh_identity(abbr)
    st = r.states.get(abbr) if r is not None else None
    if st is not None and getattr(st, 'base_plan', None) is not None: return st.base_plan
    return GP.base_plan(SN.make_coach(league.teams[abbr].gm))


def _week(session, league):
    if session.stop[0] == 'week': return session.stop[1]
    if session.stop[0] == 'playoffs' and len(session.stop) > 1 and 0 <= session.stop[1] < 4:
        return 19 + session.stop[1]
    return None


def _saved(league, week):
    wp = getattr(league, 'user_week_plan', None)
    if wp and wp.get('week') == week and wp.get('year') == league.year: return dict(wp.get('changes', {}))
    return {}


def _taken(league, week):
    wp = getattr(league, 'user_week_plan', None)
    if wp and wp.get('week') == week and wp.get('year') == league.year: return list(wp.get('taken', []))
    return []


def status(session, league, abbr):
    """Editing state belongs to this season and game, including playoff rounds."""
    week = _week(session, league)
    wp = getattr(league, 'user_week_plan', None) or {}
    current = wp.get('year') == league.year and wp.get('week') == week
    live = getattr(session.runner, 'live', None) if session.runner is not None else None
    started = bool(session.played or (live and not live.get('done', False)))
    return dict(key=f'{league.year}:{week}:{abbr}', locked=bool(current and wp.get('locked')),
                dirty=bool(current and wp.get('dirty')), started=started)


def act_save(session, league, abbr):
    week = _week(session, league)
    manual, suggestions = _parts(league, week)
    _write(league, week, manual, suggestions)
    league.user_week_plan.update(locked=True, dirty=False)
    return dict(ok=True, line='Game plan saved for Sunday.')


def act_reopen(session, league, abbr):
    if not status(session, league, abbr)['locked']:
        return dict(ok=False, why='The game plan is already open for editing.')
    # Keep every accepted, skipped and manual choice exactly as saved.
    league.user_week_plan['locked'] = False
    return dict(ok=True, line='Game plan reopened for editing.')


def act_save_failed(session, league, abbr):
    """A failed browser write must not leave an apparently saved, locked plan."""
    wp = getattr(league, 'user_week_plan', None)
    if wp and wp.get('year') == league.year and wp.get('week') == _week(session, league):
        wp.update(locked=False, dirty=True)
    return dict(ok=True)


def _preview(base, changes):
    import gameplan_week as GW
    plan = base.copy(); GW.apply_changes(plan, base, changes); return plan


def this_week(session, league, abbr):
    import gameplan_week as GW
    wk = _week(session, league)
    r = rail(session, league, abbr)
    if wk is None:
        return dict(rail=r, off=True, note=('Week 1 planning opens after Post-Cutdown Waivers.'
                    if session.stop[0] in ('cutdown', 'wire') else 'The plan is set in season, the week before a game.'))
    opp = session._opponent(wk)
    if opp is None: return dict(rail=r, off=True, bye=True, note=f"{__import__('views').transaction_period(dict(week=wk))} is your bye.")
    opp_abbr, away = opp
    base = _base_plan(session, league, abbr)
    changes = _saved(league, wk)
    plan = _preview(base, changes)
    rep = GW.opponent_report(league, abbr, opp_abbr, wk)
    leans = []
    # where the assistants would put each lean, from the suggestions not yet taken (the gold ghost)
    ghost = {}
    for s in rep['suggestions']:
        if s['text'] in _taken(league, wk) or s['text'] in _skipped(league, wk): continue
        for ck, cv in (s.get('changes') or {}).items():
            if ck in GW.RANGE and isinstance(cv, (int, float)) and not isinstance(cv, bool): ghost[ck] = ghost.get(ck, 0.0) + float(cv)
    for side, k, label, lo, hi, desc in LEANS:
        b = float(getattr(base, k)); rng_ = GW.RANGE[k]; val = float(getattr(plan, k))
        lower, upper = b-rng_, b+rng_
        if k not in ('pass_bias', 'box_bias'): lower, upper = max(0.0, lower), min(1.0, upper)
        g = (max(b - rng_, min(b + rng_, val + ghost[k])) if k in ghost else None)
        leans.append(dict(side=side, key=k, label=label, lo=lo, hi=hi, desc=desc, base=round(b, 3), value=round(val, 3), word=_lean_word(k, val), min=round(lower, 3), max=round(upper, 3), range=rng_,
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
        sugg.append(dict(i=i, side=('offense' if s['side'] == 'offence' else 'defense'), text=sentence(s['text']), why=sentence(s['why']), target=target_words(s), changes={k: (list(v) if isinstance(v, tuple) else v) for k, v in s['changes'].items()}, taken=taken, skipped=s['text'] in _skipped(league, wk)))
    bracket = plan.bracket; bp = league.player(bracket) if bracket else None
    their_wrs = [dict(pid=p.pid, name=p.name, ovr=round(p.ovr)) for p in league.teams[opp_abbr].depth.get('WR', [])[:3] if p.out_until is None]
    wr_out = [__import__('views').surname(p.name) for p in league.teams[opp_abbr].depth.get('WR', [])[:2] if p.out_until is not None]
    import staff as ST
    t = league.teams[abbr]
    return dict(rail=r, off=False, week=wk, opp=club(opp_abbr), away=away, leans=leans, plan_state=status(session, league, abbr),
                depth=dict(base=[round(float(x), 3) for x in base.depth_mix], value=[round(float(x), 3) for x in plan.depth_mix], labels=list(DEPTH_LABELS)),
                protection=dict(base=base.protection, value=plan.protection, options=[dict(key=k, word=PROT_WORDS[k]) for k in PROTECTIONS]),
                travel=bool(plan.travel), travel_target=(dict(pid=tp.pid, name=tp.name) if (tp := league.player(changes.get('travel_target'))) else None), my_cb1=_cb1(league, t), bracket=(dict(pid=bp.pid, name=bp.name) if bp else None), their_wrs=their_wrs, wr_out=wr_out,
                suggestions=sugg, changes={k: (list(v) if isinstance(v, tuple) else v) for k, v in changes.items()},
                coordinators=dict(oc=_coord(t, 'oc'), dc=_coord(t, 'dc')), coach=rep['coach'], forecast=rep.get('forecast'))


def _cb1(league, t):
    cbs = sorted((p for p in t.active() if p.pos == 'CB' and p.out_until is None), key=lambda p: -p.ovr)
    return dict(pid=cbs[0].pid, name=__import__('views').surname(cbs[0].name)) if cbs else None


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
        elif k in ('protection', 'travel', 'bracket', 'travel_target'): out[k] = v
        elif k == 'screen_boost': out[k] = float(out.get(k, 0.0)) + float(v)
        else: out[k] = float(out.get(k, 0.0)) + float(v)
    return out


def _skipped(league, week):
    wp = getattr(league, 'user_week_plan', None) or {}
    return list(wp.get('skipped', [])) if wp.get('year') == league.year and wp.get('week') == week else []


def act_skip(session, league, abbr, i, skip=True):
    import gameplan_week as GW
    wk = _week(session, league); opp = session._opponent(wk)
    if wk is None or opp is None: return dict(ok=False, why='no game this week')
    suggestions = GW.opponent_report(league, abbr, opp[0], wk)['suggestions']
    if not 0 <= int(i) < len(suggestions): return dict(ok=False, why='that suggestion is gone')
    text = suggestions[int(i)]['text']; skipped = _skipped(league, wk)
    if skip and text not in skipped: skipped.append(text)
    if not skip: skipped = [x for x in skipped if x != text]
    manual, suggestions = _parts(league, wk)
    _write(league, wk, manual, suggestions)
    league.user_week_plan['skipped'] = skipped
    return dict(ok=True)


def _parts(league, week):
    wp = getattr(league, 'user_week_plan', None) or {}
    if wp.get('year') != league.year or wp.get('week') != week: return {}, {}
    # Older plans have no provenance; preserve their effective choices as manual.
    return dict(wp.get('manual', wp.get('changes', {}))), dict(wp.get('suggestions', {}))


def _write(league, week, manual, suggestions):
    import gameplan_week as GW
    combined = {}
    for changes in suggestions.values(): combined = _merge(combined, changes)
    combined.update(manual)  # an explicit GM instruction wins over advice
    wp = GW.set_user_plan(league, week, combined, taken=list(suggestions))
    wp.update(manual=manual, suggestions=suggestions, locked=False, dirty=True)


def _suggestion(session, league, abbr, i):
    import gameplan_week as GW
    wk = _week(session, league); opp = session._opponent(wk)
    if opp is None: return None
    suggestions = GW.opponent_report(league, abbr, opp[0], wk)['suggestions']
    return suggestions[int(i)] if 0 <= int(i) < len(suggestions) else None


def act_take(session, league, abbr, i):
    wk = _week(session, league); suggestion = _suggestion(session, league, abbr, i)
    if suggestion is None: return dict(ok=False, why='that suggestion is gone')
    manual, suggestions = _parts(league, wk)
    suggestions[suggestion['text']] = dict(suggestion['changes'])
    _write(league, wk, manual, suggestions)
    league.user_week_plan['skipped'] = [x for x in _skipped(league, wk) if x != suggestion['text']]
    return dict(ok=True, line=f"Taken: {suggestion['text']}.")


def act_untake(session, league, abbr, i):
    wk = _week(session, league); suggestion = _suggestion(session, league, abbr, i)
    if suggestion is None: return dict(ok=False, why='that suggestion is gone')
    manual, suggestions = _parts(league, wk)
    suggestions.pop(suggestion['text'], None)
    _write(league, wk, manual, suggestions)
    return dict(ok=True, line=f"Put back: {suggestion['text']}.")


def act_set_lean(session, league, abbr, key, value):
    import gameplan_week as GW
    if key not in GW.RANGE: return dict(ok=False, why='not a lean')
    try: value = float(value)
    except (TypeError, ValueError): return dict(ok=False, why='Enter a valid number.')
    if not np.isfinite(value): return dict(ok=False, why='Enter a finite number.')
    wk = _week(session, league); base = _base_plan(session, league, abbr)
    b = float(getattr(base, key)); d = float(np.clip(value-b, -GW.RANGE[key], GW.RANGE[key]))
    manual, suggestions = _parts(league, wk); manual[key] = d
    _write(league, wk, manual, suggestions)
    return dict(ok=True, value=round(b+d, 3))


def act_set_depth(session, league, abbr, short, medium, deep):
    try: want = np.array([float(short), float(medium), float(deep)])
    except (TypeError, ValueError): return dict(ok=False, why='Enter three valid percentages.')
    if not np.all(np.isfinite(want)) or np.any(want < 0) or want.sum() <= 0 or not np.isfinite(want.sum()):
        return dict(ok=False, why='Depth percentages must be nonnegative and total more than zero.')
    want /= want.sum()
    wk = _week(session, league); base = _base_plan(session, league, abbr)
    manual, suggestions = _parts(league, wk)
    manual['depth_mix'] = tuple(float(x) for x in want - np.array(base.depth_mix))
    _write(league, wk, manual, suggestions)
    return dict(ok=True)


def act_set_decision(session, league, abbr, key, value):
    wk = _week(session, league); manual, suggestions = _parts(league, wk)
    if key == 'protection':
        if value not in PROTECTIONS: return dict(ok=False, why='Unknown protection.')
        manual[key] = value
    elif key == 'travel':
        manual[key] = bool(value)
        if not value: manual['travel_target'] = None
    elif key in ('travel_target', 'bracket'):
        if value:
            opp = session._opponent(wk)
            p = league.player(value)
            if not opp or p is None or p.team != opp[0] or p.pos != 'WR' or p.out_until is not None:
                return dict(ok=False, why='Choose an available opposing receiver.')
        manual[key] = value or None
        if key == 'travel_target': manual['travel'] = bool(value)
    else: return dict(ok=False, why='Unknown decision.')
    _write(league, wk, manual, suggestions)
    return dict(ok=True)


def act_reset(session, league, abbr):
    _write(league, _week(session, league), {}, {})
    return dict(ok=True, line="Back to the coordinators' plan.")


# ------------------------------------------------------------ the report
def report(session, league, abbr):
    import gameplan_week as GW
    wk = _week(session, league); r = rail(session, league, abbr)
    if wk is None:
        return dict(rail=r, off=True, note=('The Week 1 opponent report opens after Post-Cutdown Waivers.'
                    if session.stop[0] in ('cutdown', 'wire') else 'The report comes in season, the week before a game.'))
    opp = session._opponent(wk)
    if opp is None: return dict(rail=r, off=True, note=f"{__import__('views').transaction_period(dict(week=wk))} is your bye.")
    opp_abbr, away = opp
    rep = GW.opponent_report(league, abbr, opp_abbr, wk)
    n = len(league.teams)
    def tend(t):
        if not t: return None
        return dict(pass_rate=round(t['pass_rate'] * 100), pa_rate=round(t['pa_rate'] * 100), motion=round(t['motion'] * 100), deep=round(t['deep'] * 100), fourth_go=round(t['fourth_go'] * 100),
                    blitz=round(t['blitz'] * 100), man=round(min(1.0, t['man']) * 100), two_high=round(t['two_high'] * 100), box8=round(t['box8'] * 100), games=int(t['games']))
    lg = _league_tend(league)
    units = [dict(unit=u, rank=v[0] if v else None, of=v[1] if v else n) for u, v in (rep['units'] or {}).items()]
    mine = [dict(unit=u, rank=v[0] if v else None, of=v[1] if v else n) for u, v in (rep['my_units'] or {}).items()]
    unit_table = GW.performance_table(league, abbr, opp_abbr)
    panels = None
    try:
        import views as V
        pv = V._matchup(session, league, abbr)
        panels = pv.get('panels') if pv else None
    except Exception: panels = None
    changes = _saved(league, wk)
    from views import _change_words
    sugg = [dict(i=i, side=('offense' if s['side'] == 'offence' else 'defense'), text=sentence(s['text']), why=sentence(s['why']), change=_change_words(s.get('changes')), taken=(s['text'] in _taken(league, wk)), skipped=(s['text'] in _skipped(league, wk))) for i, s in enumerate(rep['suggestions'])]
    return dict(rail=r, off=False, week=wk, opp=club(opp_abbr), away=away, coach=rep['coach'], tendencies=tend(rep['tendencies']), mine_tend=tend(rep['my_tendencies']), league_tend=lg,
                units=units, my_units=mine, unit_table=unit_table, panels=panels, stars=rep['stars'], injured=rep['injured'], strengths=[sentence(s['text']) for s in rep['strengths']], weaknesses=[sentence(w['text']) for w in rep['weaknesses']],
                suggestions=sugg, forecast=rep.get('forecast'), record=_rec(league, opp_abbr), plan_state=status(session, league, abbr))


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

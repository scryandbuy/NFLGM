"""
FRONT OFFICE VIEWS. Owner, Identity, Staff, Cap: what the pages show and what
their buttons do.
"""
import copy
import numpy as np
from views import club, money, morale_word, player_plate, rail

# the identity leans the user sets, as spectrums. Each: gm attribute, label, the two ends.
LEANS_OFF = [('pass_lean', 'Pass / Run', 'Run first', 'Pass first'), ('play_action', 'Play Action', 'Rare', 'Often'), ('motion', 'Motion', 'Still', 'Constant'),
             ('tempo', 'Tempo', 'Huddle', 'Fast'), ('deep', 'Depth of Target', 'Short game', 'Shots'), ('fourth_down', 'Fourth Down', 'Punt', 'Go for it')]
LEANS_DEF = [('coverage', 'Coverage', 'Zone', 'Man'), ('shell', 'Safeties', 'Single high', 'Two high'), ('blitz', 'Blitz', 'Rush four', 'Send heat'), ('box', 'Box', 'Light', 'Loaded')]
CHOICES = [('off_blocking', 'Run Blocking', ['zone', 'gap', 'mixed']), ('off_personnel', 'Base Personnel', ['11', '12', '21', '13']), ('def_front', 'Front', ['4-3', '3-4', 'multiple'])]


def _gm(league, abbr):
    return league.teams[abbr].gm


# ============================================================ OWNER
OWNER_FIRST = ['Robert', 'Arthur', 'Jerry', 'Stephen', 'Mark', 'Clark', 'Jeffrey', 'Michael', 'David', 'Terry', 'Shahid', 'Amy', 'Gayle', 'Virginia', 'Kim', 'Denise', 'Woody', 'Zygi', 'Jimmy', 'Dean', 'Stan', 'Jody', 'Tom', 'Josh', 'Bill', 'Cal', 'Martha', 'Sheila', 'Carol', 'Janice', 'Paul', 'Edward']
OWNER_LAST = ['Kraft', 'Blank', 'Jones', 'Ross', 'Davis', 'Hunt', 'Lurie', 'Bidwill', 'Tepper', 'Pegula', 'Khan', 'Adams', 'Benson', 'McCaskey', 'Pegula', 'York', 'Johnson', 'Wilf', 'Haslam', 'Spanos', 'Kroenke', 'Allen', 'Glazer', 'Harris', 'Bisciotti', 'McNair', 'Ford', 'Ford', 'Rooney', 'Irsay', 'Brown', 'Snyder']


def _owner(league, t):
    """The owner's name and the year he bought in, drawn once and kept on the club."""
    o = getattr(t, 'owner', None)
    if o is None:
        rng = np.random.default_rng(hash(t.abbr) % (2 ** 32))
        i = int(rng.integers(len(OWNER_FIRST))); j = int(rng.integers(len(OWNER_LAST)))
        t.owner = o = dict(name=f"{OWNER_FIRST[i]} {OWNER_LAST[j]}", since=int(league.year - rng.integers(3, 35)))
    return o


def owner(session, league, abbr):
    import firing_model as FM
    from views import _owner_mood
    t = league.teams[abbr]; h = t.hist(); own = _owner(league, t)
    sec = FM.job_security(h)
    w, l, d = t.record
    exp = float(h.get('expected_pct') or 0.5)
    exp_words = 'a title run' if exp >= 0.72 else 'the playoffs' if exp >= 0.56 else 'a winning season' if exp >= 0.5 else 'progress' if exp >= 0.4 else 'patience while you rebuild'
    pat = float(getattr(t, 'owner_patience', 0.5))
    weights = dict(wins=round(0.5 + 0.3 * (1 - pat), 2), young=round(pat, 2), stars=round(getattr(t, 'owner_star_pull', 0.5), 2), spend=round(getattr(t, 'owner_spend', 0.5), 2))
    draft_word = 'Patient' if pat >= 0.6 else 'Wants results now' if pat <= 0.35 else 'Measured'
    reviews = [dict(year=r.get('year'), record=r.get('record'), line=r.get('line')) for r in (getattr(t, 'owner_reviews', None) or [])]
    import staff as ST
    return dict(rail=rail(session, league, abbr), owner=own, draft_word=draft_word, mood=_owner_mood(t), job=('Secure' if sec >= 0.7 else 'Safe' if sec >= 0.45 else 'Warming' if sec >= 0.25 else 'Hot Seat'), security=round(sec, 2),
                expects=exp_words, expected_pct=round(exp, 2), record=f"{w}–{l}" + (f"–{d}" if d else ''), tenure=int(h.get('tenure') or 0), drought=int(h.get('playoff_drought') or 0),
                prev_pct=round(float(h.get('prev_win_pct') or 0), 3), weights=weights,
                staff_budget=dict(total=round(ST.budget(t), 1), payroll=round(ST.payroll(t), 1), available=round(ST.room(t), 1)),
                patience_word=('patient' if getattr(t, 'owner_patience', 0.5) >= 0.6 else 'impatient' if getattr(t, 'owner_patience', 0.5) <= 0.35 else 'measured'),
                spend_word=('spends freely' if getattr(t, 'owner_spend', 0.5) >= 0.6 else 'holds the purse' if getattr(t, 'owner_spend', 0.5) <= 0.35 else 'pays market'),
                stars_word=('wants stars' if getattr(t, 'owner_star_pull', 0.5) >= 0.6 else 'trusts the process' if getattr(t, 'owner_star_pull', 0.5) <= 0.35 else 'balanced'),
                reviews=reviews)


# ============================================================ IDENTITY
def _leans(gm):
    d = {k: round(float(getattr(gm, k, 0.5)), 2) for k, *_ in LEANS_OFF + LEANS_DEF}
    d.update({k: getattr(gm, k) for k, *_ in CHOICES})
    return d


def _misfits(league, t, gm_after):
    """Whose overall moves the most under the new identity, both ways."""
    import gm_engine as GE, targets as TG
    keys_before = GE.scheme_of(t.gm) or []; keys_after = GE.scheme_of(gm_after) or []
    out = []
    for p in t.active():
        try:
            b = float(TG.position_score(p.ratings, p.pos, keys_before)); a = float(TG.position_score(p.ratings, p.pos, keys_after))
        except Exception: continue
        if abs(a - b) >= 1.0: out.append(dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), delta=round(a - b, 1)))
    losers = sorted([x for x in out if x['delta'] < 0], key=lambda x: x['delta'])[:6]
    gainers = sorted([x for x in out if x['delta'] > 0], key=lambda x: -x['delta'])[:6]
    return losers, gainers


LEAN_ROWS = [('offence', 'pass_lean', 'Pass Lean', 'pct'), ('offence', 'motion', 'Motion', 'pct'), ('offence', 'deep', 'Depth', 'depth'),
             ('defence', 'shell', 'Shell', 'shell'), ('defence', 'blitz', 'Blitz', 'pct'), ('defence', 'coverage', 'Man Coverage', 'pct')]
FIT_GROUPS = [('QB', ['QB']), ('HB', ['HB', 'FB']), ('WR', ['WR']), ('TE', ['TE']), ('OL', ['LT', 'LG', 'C', 'RG', 'RT']), ('EDGE', ['LEDG', 'REDG']), ('DT', ['DT']), ('LB', ['MIKE', 'WILL', 'SAM']), ('CB', ['CB']), ('S', ['FS', 'SS'])]
FIT_N = {'QB': 1, 'HB': 1, 'WR': 3, 'TE': 1, 'OL': 5, 'EDGE': 2, 'DT': 2, 'LB': 2, 'CB': 3, 'S': 2}


def club_identity(league, t):
    """The archetype the club runs on each side. Set from the coach's leans the first time it is asked for."""
    import identity_catalog as IC
    ident = getattr(t, 'identity', None) or {}
    changed = False
    for side in ('offence', 'defence'):
        k = ident.get(side)
        if k in IC.ARCHETYPE_ALIASES: k = IC.ARCHETYPE_ALIASES[k]; changed = True
        if k not in IC.ARCHETYPES: k = IC.nearest_archetype(t.gm, side); changed = True
        ident[side] = k
    if changed: t.identity = ident
    return ident


def _lean_value(k, kind, val):
    if kind == 'pct': return f"{round(float(val) * 100)}%"
    if kind == 'depth': return 'Short' if val < 0.4 else 'Deep' if val > 0.6 else 'Medium'
    if kind == 'shell': return '1-High' if val < 0.4 else '2-High' if val > 0.6 else 'Mixed'
    return str(val)


def _lean_rows(gm_leans, scheme_leans):
    """Grey is every scheme's range, white is this scheme's range, the dot is where your scheme sits."""
    import identity_catalog as IC
    rows = []
    for side, k, label, kind in LEAN_ROWS:
        # every scheme's range means the league's: the archetypes and every real coach in the catalog,
        # so a club whose coach leans further than any archetype still sits inside the grey
        allv = [a[side][k] for a in IC.side_archetypes(side).values()] + [c[side][k] for c in IC.CATALOG.values() if side in c and k in c[side]]
        lo, hi = min(allv), max(allv)
        mine = float(gm_leans.get(k, 0.5)); sch = float(scheme_leans.get(k, mine))
        rows.append(dict(key=k, label=label, all_lo=round(lo * 100), all_hi=round(hi * 100), band_lo=round(max(0.0, sch - 0.08) * 100), band_hi=round(min(1.0, sch + 0.08) * 100), dot=round(mine * 100), value=_lean_value(k, kind, mine)))
    return rows


def _fit_table(league, t, gm_like):
    """Every starter's grade at his spot under a GM's identity, by group; and each man's fit."""
    import gm_engine as GE, targets as TG
    keys = GE.scheme_of(gm_like) or []
    rows = []; men = []
    for g, poss in FIT_GROUPS:
        starters = sorted((p for p in t.active() if p.pos in poss), key=lambda p: -p.ovr)[:FIT_N[g]]
        fits = []
        for p in starters:
            try: base = float(TG.position_score(p.ratings, p.pos, None)); here = float(TG.position_score(p.ratings, p.pos, keys)); f = here - base
            except Exception: f = 0.0
            fits.append(f); men.append((p, f, g))
        avg = float(np.mean(fits)) if fits else 0.0
        rows.append(dict(group=g, fit=round(avg, 1), pct=int(round(np.clip(50 + avg * 25, 5, 100))), n=len(starters)))
    return rows, men


def _best_scheme_for(p, side):
    """The archetype this man grades best in, and the words for why he is a misfit here."""
    import identity_catalog as IC, gm_engine as GE, targets as TG
    class _G: pass
    best, bv = None, None
    for k, a in IC.side_archetypes(side).items():
        g = _G()
        for f, v in a[side].items(): setattr(g, {'blocking': 'off_blocking', 'personnel': 'off_personnel', 'front': 'def_front'}.get(f, f), v)
        for f in ('off_blocking', 'off_personnel', 'def_front', 'coverage', 'shell', 'blitz', 'box', 'pass_lean', 'play_action', 'motion', 'tempo', 'deep', 'fourth_down'):
            if not hasattr(g, f): setattr(g, f, 'zone' if f == 'off_blocking' else '11' if f == 'off_personnel' else '4-3' if f == 'def_front' else 0.5)
        try: v = float(TG.position_score(p.ratings, p.pos, GE.scheme_of(g) or []))
        except Exception: continue
        if bv is None or v > bv: best, bv = k, v
    return best


def _assistants_read(league, t, rows_now, men_now, rows_alt=None, men_alt=None, alt_name=None, applied=False):
    """Three states: the standing assessment, a recommendation on a preview, the assessment after a change."""
    def worst(rows): return sorted(rows, key=lambda r: r['fit'])[:2]
    def best(rows): return sorted(rows, key=lambda r: -r['fit'])[:2]
    if rows_alt is None:
        good = [r['group'] for r in rows_now if r['fit'] >= 0.6]; bad = [r['group'] for r in rows_now if r['fit'] <= -0.6]
        if not good and not bad: line = 'The roster is neutral to this identity; nobody grades far above or below his rating in it.'
        elif len(bad) <= 3: line = 'The roster is built for this identity' + (f" everywhere but {_join(bad)}." if bad else ' across the board.') + (f" {_join(good)} grade best in it." if good else '')
        else: line = f"The roster does not fit this identity: {_join(bad)} all grade below their rating in it."
        top = sorted(men_now, key=lambda x: x[1])[:1]
        if top and top[0][1] <= -1.0:
            p, f, g = top[0]; alt = _best_scheme_for(p, 'offence' if g in ('QB', 'HB', 'WR', 'TE', 'OL') else 'defence')
            import identity_catalog as IC
            an = 'an' if IC.ARCHETYPES[alt]['name'][0] in 'AEIOU' else 'a'
            line += f" {__import__('views').surname(p.name)} is the worst fit; he would grade better in {an} {IC.ARCHETYPES[alt]['name']} {'offense' if g in ('QB', 'HB', 'WR', 'TE', 'OL') else 'defense'}."
        return line
    d = {r['group']: r2['fit'] - r['fit'] for r, r2 in zip(rows_now, rows_alt)}
    up = [g for g, v in sorted(d.items(), key=lambda kv: -kv[1]) if v >= 0.5]; down = [g for g, v in sorted(d.items(), key=lambda kv: kv[1]) if v <= -0.5]
    net = sum(d.values()) / max(1, len(d))
    movers_up = sorted([(p, f2 - f1) for (p, f1, g), (_, f2, _g) in zip(men_now, men_alt)], key=lambda x: -x[1])[:2]
    movers_dn = sorted([(p, f2 - f1) for (p, f1, g), (_, f2, _g) in zip(men_now, men_alt)], key=lambda x: x[1])[:2]
    names_up = ' and '.join(__import__('views').surname(p.name) for p, v in movers_up if v >= 0.8); names_dn = ' and '.join(__import__('views').surname(p.name) for p, v in movers_dn if v <= -0.8)
    if applied:
        line = f"{_join(up).capitalize()} carry this identity" if up else 'No group is a natural fit for this identity'
        line += (f"; {names_up} grade well in it." if names_up else '.')
        if down: line += f" {_join(down).capitalize()} grade below their rating here" + (f", {names_dn} most of all." if names_dn else '.')
        return line
    verdict = 'Worth a look.' if net >= 0.15 else 'Not worth it as the roster stands.' if net <= -0.15 else 'A wash.'
    line = verdict
    if up: line += f" It would play to {_join(up)}" + (f", and {names_up} would be among the best in the league in it." if names_up else '.')
    if down: line += f" The cost is {_join(down)}" + (f": {names_dn} grade well below their rating in it" if names_dn else '') + '.'
    if net <= -0.15: line += ' Only worth it if the plan is to rebuild around it.'
    return line


def _join(items):
    items = list(items)
    if not items: return ''
    if len(items) == 1: return items[0]
    return ', '.join(items[:-1]) + ' and ' + items[-1]


def identity(session, league, abbr, preview=None):
    """The identity page. preview: an archetype key to show the change to, before Apply."""
    import identity_catalog as IC, copy
    t = league.teams[abbr]; gm = t.gm
    ident = club_identity(league, t)
    cur = _leans(gm)
    rows_now, men_now = _fit_table(league, t, gm)
    arche = []
    for side in ('offence', 'defence'):
        for k, a in IC.side_archetypes(side).items():
            arche.append(dict(key=k, name=a['name'], words=a['words'], side=('offense' if side == 'offence' else 'defense'), current=(ident.get(side) == k)))
    scheme_leans = {}
    for side in ('offence', 'defence'):
        scheme_leans.update(IC.ARCHETYPES[ident[side]][side])
    out = dict(rail=rail(session, league, abbr), coach=gm.name, prestige=round(getattr(gm, 'prestige', 50)),
               identity=dict(offense=IC.ARCHETYPES[ident['offence']]['name'], defense=IC.ARCHETYPES[ident['defence']]['name']),
               archetypes=arche, leans=_lean_rows(cur, scheme_leans), fit=rows_now,
               misfits=_misfit_rows(league, t, men_now), say=_assistants_read(league, t, rows_now, men_now), preview=None,
               history=[dict(year=h.get('year'), week=h.get('week'), change=h.get('change')) for h in (getattr(t, 'identity_history', None) or [])])
    if preview and preview in IC.ARCHETYPES and IC.ARCHETYPES[preview].get('side'):
        a = IC.ARCHETYPES[preview]; side = a['side']
        after = copy.copy(gm)
        for f, v in a[side].items(): setattr(after, {'blocking': 'off_blocking', 'personnel': 'off_personnel', 'front': 'def_front'}.get(f, f), v)
        rows_alt, men_alt = _fit_table(league, t, after)
        sl = dict(scheme_leans); sl.update(a[side])
        out['preview'] = dict(key=preview, name=a['name'], side=('offense' if side == 'offence' else 'defense'), fit=rows_alt, leans=_lean_rows(_leans(after), sl),
                              say=_assistants_read(league, t, rows_now, men_now, rows_alt, men_alt, a['name']), misfits=_misfit_rows(league, t, men_alt))
    return out


def _misfit_rows(league, t, men):
    import identity_catalog as IC
    keep = set(getattr(t, 'misfit_keep', []) or [])
    out = []
    for p, f, g in sorted(men, key=lambda x: x[1])[:6]:
        if f > -0.5 or p.pid in keep: continue
        side = 'offence' if g in ('QB', 'HB', 'WR', 'TE', 'OL') else 'defence'
        alt = _best_scheme_for(p, side)
        cur_name = IC.ARCHETYPES[club_identity(league, t)[side]]['name']
        out.append(dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), fit=round(f, 1), reason=f"{IC.ARCHETYPES[alt]['name']} {'offense' if side == 'offence' else 'defense'} player in {'an' if cur_name[0] in 'AEIOU' else 'a'} {cur_name}" if alt else ''))
    return out


def act_apply_identity(league, abbr, key):
    """Apply an archetype on its side: the GM's leans move to it, the scheme keys recompute, the club's identity records it."""
    import identity_catalog as IC, gm_engine as GE
    a = IC.ARCHETYPES.get(key)
    if not a or not a.get('side'): return dict(ok=False, why='no such archetype')
    t = league.teams[abbr]; gm = t.gm; side = a['side']
    ident = club_identity(league, t); before = IC.ARCHETYPES[ident[side]]['name']
    for f, v in a[side].items(): setattr(gm, {'blocking': 'off_blocking', 'personnel': 'off_personnel', 'front': 'def_front'}.get(f, f), v)
    t.scheme = GE.scheme_of(gm); ident[side] = key; t.identity = ident
    t.identity_history = (getattr(t, 'identity_history', None) or []) + [dict(year=league.year, week=league.week, change=f"{'Offense' if side == 'offence' else 'Defense'}: {before} → {a['name']}")]
    rows, men = _fit_table(league, t, gm)
    return dict(ok=True, name=a['name'], say=_assistants_read(league, t, rows, men))


def act_set_identity(league, abbr, changes):
    """Confirm the leans. Writes the GM's leans, recomputes the scheme keys, records the change."""
    import gm_engine as GE
    t = league.teams[abbr]; gm = t.gm
    before = _leans(gm); applied = {}
    for k, v in changes.items():
        if k in [c for c, *_ in CHOICES]:
            opts = next(o for c, _, o in CHOICES if c == k)
            if v in opts: setattr(gm, k, v); applied[k] = v
        elif k in before:
            setattr(gm, k, float(min(1.0, max(0.0, float(v))))); applied[k] = round(float(getattr(gm, k)), 2)
    t.scheme = GE.scheme_of(gm)
    t.identity_history = (getattr(t, 'identity_history', None) or []) + [dict(year=league.year, week=league.week, change=', '.join(f"{k} {before[k]}→{applied[k]}" for k in applied))]
    return dict(ok=True, applied=applied, keys=t.scheme or [])


def act_apply_archetype(league, abbr, key):
    import identity_catalog as IC
    a = IC.ARCHETYPES.get(key)
    if not a: return dict(ok=False, why='no such archetype')
    changes = {}
    for side in a.values():
        for k, v in side.items():
            changes[{'blocking': 'off_blocking', 'personnel': 'off_personnel', 'front': 'def_front'}.get(k, k)] = v
    return act_set_identity(league, abbr, changes)


# ============================================================ STAFF
def staff(session, league, abbr):
    import staff as ST
    t = league.teams[abbr]
    cards = []
    for role in ('oc', 'dc', 'st', 'scout'):
        c = (getattr(t, 'staff', None) or {}).get(role)
        if c is None: cards.append(dict(role=role, role_name=ST.ROLE_NAME.get(role, role), empty=True)); continue
        cd = ST.card(c); cd.update(role_key=role, disgruntled=bool(getattr(c, 'disgruntled', False)), extend_ask=round(ST.ask(c), 2)); cards.append(cd)
    pools = {}
    for role in ('oc', 'dc', 'st', 'scout'):
        pools[role] = [dict(ST.card(c, revealed_only=True), role_key=role, background=(('Head-coaching candidate' if getattr(c, 'hc_candidate', False) else 'Coordinator' if role != 'scout' else 'Scout') + (f" · {c.specialty}" if getattr(c, 'specialty', None) else ''))) for c in ST.pool_for(league, role)[:8]]
    poaches = []
    for p in (getattr(league, 'poaches', None) or []):
        if p.get('team') != abbr or p.get('state') != 'open': continue
        c = (getattr(t, 'staff', None) or {}).get(p.get('role'))
        if c is None: continue
        ask = ST.ask(c); hc_pay = round(ask * 1.6, 2)
        poaches.append(dict(p, salary=round(float(c.salary), 2), years=int(c.years), ask=round(ask, 2), hc_pay=hc_pay, role_name=ST.ROLE_NAME.get(p.get('role'), p.get('role')),
                            room_without=round(ST.room(t, without=p.get('role')), 2), to_club=club(p['to']),
                            opening=({'go': f"{p['coach']} · {ST.ROLE_NAME.get(p.get('role'), '')}: {league.teams[p['to']].abbr} has asked about me for their head-coaching job. I want it. This is what I have worked for, and I hope you will not stand in my way.",
                                      'torn': f"{p['coach']}: {league.teams[p['to']].abbr} has asked about me for their head-coaching job. I like it here and I know what we have. But a head-coaching job does not come around often.",
                                      'stay': f"{p['coach']}: {league.teams[p['to']].abbr} has asked about me for their head-coaching job. I would rather stay if you can make it worth my while."}[p.get('lean', 'torn')]),
                            read=({'go': 'He leans toward going. A raise may move him; blocking him keeps him but not the coach he was.', 'torn': 'He is torn. A real raise would likely keep him; blocking him is a last resort.', 'stay': 'He wants to stay. A modest raise closes it.'}[p.get('lean', 'torn')]),
                            block_read=f"he stays through {league.year + int(c.years)}, coaches worse for the year, and leaves when his contract ends. {league.teams[p['to']].abbr} hires someone else."))
    return dict(rail=rail(session, league, abbr), cards=cards, pools=pools, poaches=poaches,
                budget=dict(total=round(ST.budget(t), 1), payroll=round(ST.payroll(t), 1), available=round(ST.room(t), 1)),
                offseason=(league.phase != 'regular'))


def act_staff_extend(league, abbr, role, years=3, salary=None):
    import staff as ST
    r = ST.extend(league, abbr, role, years=int(years), salary=(float(salary) if salary is not None else None))
    return r if isinstance(r, dict) else dict(ok=bool(r))


def act_staff_release(league, abbr, role):
    import staff as ST
    r = ST.release(league, abbr, role); return r if isinstance(r, dict) else dict(ok=bool(r))


def act_staff_interview(league, abbr, name, question=None):
    import staff as ST
    return ST.interview_ask(league, abbr, name, question) if question else ST.interview(league, abbr, name)


def act_staff_hire(league, abbr, name, years=3):
    import staff as ST
    r = ST.hire(league, abbr, name, years=int(years)); return r if isinstance(r, dict) else dict(ok=bool(r))


def act_poach(league, abbr, tid, action, raise_years=0, raise_to=None):
    import staff as ST
    return ST.answer_poach(league, int(tid), action, raise_years=int(raise_years or 0), raise_to=(float(raise_to) if raise_to is not None else None))


# ============================================================ CAP
GROUPS = {'QB': ['QB'], 'RB': ['HB', 'FB'], 'WR': ['WR'], 'TE': ['TE'], 'OL': ['LT', 'LG', 'C', 'RG', 'RT'], 'DL': ['LEDG', 'REDG', 'DT'], 'LB': ['MIKE', 'WILL', 'SAM'], 'DB': ['CB', 'FS', 'SS'], 'ST': ['K', 'P', 'LS']}


def cap(session, league, abbr):
    from cap_engine import CAP
    import contracts as CT
    t = league.teams[abbr]
    years = []
    for i in range(3):
        yr = league.year + i; by = {g: 0.0 for g in GROUPS}; n = 0
        for p in t.roster:
            if p.contract is None or i >= p.contract.years: continue
            hit = p.contract.cap_hit(i); n += 1
            for g, poss in GROUPS.items():
                if p.pos in poss: by[g] += hit; break
        dead = 0.0
        dm = getattr(t, 'dead_money', None)
        if isinstance(dm, dict): dead = float(dm.get(yr, 0.0) or 0.0)
        elif i == 0: dead = float(getattr(t.cap, 'dead', 0.0) or 0.0) if hasattr(t, 'cap') else 0.0
        limit = CAP.get(yr, CAP.get(league.year, 301.2) * (1.055 ** i))
        rollover = 0.0
        if i == 0 and hasattr(t, 'cap'):
            # this year as the ledger has it: the league cap plus what rolled in from last year
            rollover = float(getattr(t.cap, 'rollover', 0.0) or 0.0); limit = float(t.cap.limit)
        if i == 1:
            # next year as it will roll: unused space carries over, and the dead money already assigned to it counts
            from views import next_year_cap
            limit, _c, rollover, dead_sched = next_year_cap(league, t)
            dead = max(dead, dead_sched)
        committed = sum(by.values()) + dead
        expiring = sorted([p for p in t.roster if p.contract and p.contract.years == i and p.pos not in ('K', 'P', 'LS')], key=lambda p: -p.cap_hit(0))
        import practice_squad as PSQ
        years.append(dict(year=yr, limit=round(limit, 1), est=(i > 0), rollover=round(rollover, 1), by={g: round(v, 1) for g, v in by.items()}, dead=round(dead, 1), committed=round(committed, 1), space=round(limit - committed, 1), under_contract=n,
                          ps_charge=(round(PSQ.ps_charge(t), 1) if i == 0 else None), rookie_pool=(None if i == 0 else round(len([k for k in t.picks if k.year == yr and not k.used_on]) * 1.3, 1)),
                          expiring_into=[__import__('views').surname(p.name) for p in expiring[:3]], expiring_more=max(0, len(expiring) - 3)))
    # the ledger: every man, three years
    rows = []
    for p in sorted(t.roster, key=lambda p: -p.cap_hit(0)):
        if p.contract is None: continue
        c = p.contract
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), yrs=c.years, hits=[round(c.cap_hit(i), 1) if i < c.years else None for i in range(3)], penalty=round(p.dead_if_cut(0), 1),
                         restructurable=round(CT.restructure_room(p, CAP.get(league.year, 301.2)), 1) if hasattr(CT, 'restructure_room') else 0.0,
                         tags=[x for x in [('Final Year' if c.years == 1 else None), ('Rookie Deal' if getattr(c, 'rookie', False) else None), ('Big Penalty' if p.dead_if_cut(0) > 2 * c.cap_hit(0) and c.cap_hit(0) > 5 else None)] if x]))
    # dead money detail: every release and trade this year that left a charge, from the log
    dead_rows = []
    for x in league.transactions:
        if x.get('year') != league.year or x.get('team') != abbr or x.get('kind') not in ('release', 'trade_dead'): continue
        if not x.get('dead'): continue
        p = league.player(x.get('pid')); dead_rows.append(dict(name=(p.name if p else x.get('pid')), pos=(p.pos if p else ''), how=('released' if x['kind'] == 'release' else 'traded'), week=x.get('week'), dead=round(float(x['dead']), 1), dead_next=round(float(x.get('dead_next', 0) or 0), 1)))
    dead_rows.sort(key=lambda r: -r['dead'])
    largest = [dict(pid=r['pid'], name=r['name'], pos=r['pos'], hit=r['hits'][0], share=round(r['hits'][0] / years[0]['limit'] * 100, 1)) for r in rows[:8] if r['hits'][0]]
    # tags and tools: the franchise tag by position on the men whose deals are up, void years carried, the June 1 rule
    import tags as TGS, free_agency as FA
    tag_rows = []
    for p in sorted((p for p in t.roster if p.contract and p.contract.years == 1 and int(p.accrued or 0) >= 4 and p.pos not in ('K', 'P', 'LS')), key=lambda p: -p.ovr):
        try: tag_rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), price=round(TGS.tag_price(p, CAP.get(league.year, 301.2)), 1)))
        except Exception: continue
    void_carried = round(sum(float(p.contract.annual_proration) * max(0, p.contract.proration_years - p.contract.years) for p in t.roster if p.contract and getattr(p.contract, 'void', 0)), 1)
    return dict(rail=rail(session, league, abbr), years=years, rows=rows, cap_space=round(t.cap_space, 1), dead_rows=dead_rows, dead_total=round(float(t.cap.dead), 1), dead_next=round(float(getattr(t.cap, 'dead_next', 0.0) or 0.0), 1), largest=largest,
                top51=(league.phase != 'regular'), tags=tag_rows[:4], void_carried=void_carried,
                june1_rule='Every cut and trade in the offseason is treated as post-June 1: this year\'s proration stays on this year\'s books and the rest lands next year. In season, everything accelerates now.')


def act_restructure_preview(league, abbr, pid, amount=None, void_years=0):
    import contracts as CT
    r = CT.restructure_preview(league, pid, amount=(float(amount) if amount is not None else None), void_years=int(void_years or 0))
    if not isinstance(r, dict) or not r.get('ok'): return r if isinstance(r, dict) else dict(ok=False, why='nothing to restructure')
    # the assistants: what the room buys and what it costs in years he may not be here
    p = league.player(pid); t = league.teams[abbr]
    saves = float(r.get('saves_now', 0)); later = float(sum(r.get('added_later', []) or []))
    expiring = sorted((q for q in t.roster if q.contract and q.contract.years == 1 and q.pid != pid and q.pos not in ('K', 'P', 'LS')), key=lambda q: -q.ovr)
    buys = f"This buys the room to extend {__import__('views').surname(expiring[0].name)}" if expiring and saves >= 3 else f"This frees ${saves:.1f}m this year"
    yrs_left = p.contract.years
    late = (p.age + yrs_left) >= (37 if p.pos == 'QB' else 33)
    age_note = f"; at {int(p.age)} that is the real price of the move" if late else ''
    cost = f"The cost is ${later:.1f}m in years {__import__('views').surname(p.name)} may not be on the roster{age_note}." if late else f"The cost is ${later:.1f}m added across his remaining {yrs_left - 1} years, which he is likely to play."
    r['say'] = f"{buys}. {cost}"
    r['player'] = dict(name=p.name, pos=p.pos, age=int(p.age), hit=round(p.cap_hit(0), 1), yrs=yrs_left, ovr=round(p.ovr))
    return r


def act_restructure(league, abbr, pid, amount=None, void_years=0):
    import contracts as CT
    p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    r = CT.restructure_user(league, pid, amount=(float(amount) if amount is not None else None), void_years=int(void_years or 0))
    return r if isinstance(r, dict) else dict(ok=bool(r))


def season_review(session, league, abbr):
    """The morning after the season ends: the year against what the owner asked for, the seventeen results, the
    units against the league, the men who exceeded and fell short, next year's money and the men whose deals are
    up. Composed once the club is out; readable all offseason."""
    import gameplan_week as GW, staff as ST, firing_model as FM
    from views import _owner_mood, CLUB_NAME, club, surname, next_year_cap
    t = league.teams[abbr]; h = t.hist(); w, l, d = t.record; n = max(1, w + l + d); pct = (w + 0.5 * d) / n
    exp = float(h.get('expected_pct') or 0.5)
    exp_words = 'a title run' if exp >= 0.72 else 'the playoffs' if exp >= 0.56 else 'a winning season' if exp >= 0.5 else 'progress' if exp >= 0.4 else 'patience while you rebuild'
    # the finish: division place, the postseason if any
    st = {}
    try:
        import views_league as VL
        r = VL._state(session); st = r.standings() if r is not None else {}
    except Exception: st = {}
    div_rank = (st.get(abbr) or {}).get('div_rank')
    exit_ = None
    post = getattr(session, 'post_live', None) or getattr(session, 'post', None)
    if post is not None:
        if getattr(post, 'champion', None) == abbr: exit_ = 'Champions'
        else:
            er = (getattr(post, 'exit_round', {}) or {}).get(abbr)
            exit_ = {'WC': 'Lost in the Wild Card round', 'DIV': 'Lost in the Divisional round', 'CONF': 'Lost the Conference Championship', 'SB': 'Lost the Super Bowl'}.get(er)
            if exit_ is None and abbr in {x for sd in (getattr(post, 'seeds', {}) or {}).values() for x in sd}: exit_ = 'In the playoffs'
    if exit_ is None: exit_ = 'Missed the playoffs'
    gap = pct - exp
    verdict = ('He got more than he asked for.' if gap >= 0.12 else 'He got what he asked for.' if gap >= -0.05 else 'He got less than he asked for.' if gap >= -0.18 else 'He got a lot less than he asked for.')
    own = _owner(league, t); mood = _owner_mood(t); sec = FM.job_security(h)
    owner_line = {
        'Pleased': f"{own['name']} is pleased. {exp_words.capitalize()} was the ask and you delivered on it; he wants to know what the next step is.",
        'Settled': f"{own['name']} can live with the year, but only just. He asked for {exp_words} and {verdict.lower()} He wants to hear what changes.",
        'Restless': f"{own['name']} is restless. He asked for {exp_words} and {verdict.lower()} He wants a plan on his desk before the new year.",
        'Angry': f"{own['name']} is angry. He asked for {exp_words}; {verdict.lower()} Your seat is warm.",
    }[mood]
    # the seventeen results
    timeline = []
    for (wk, a, hm, ap, hp) in sorted(league.schedule, key=lambda g: g[0]):
        if wk > 18 or abbr not in (a, hm): continue
        if ap is None: timeline.append(dict(week=wk, bye=True)); continue
        mine, theirs = (ap, hp) if a == abbr else (hp, ap)
        opp = hm if a == abbr else a
        timeline.append(dict(week=wk, opp=club(opp), away=(a == abbr), mine=mine, theirs=theirs, result=('W' if mine > theirs else 'L' if mine < theirs else 'T')))
    weeks_played = {x['week'] for x in timeline}
    for wk in range(1, 19):
        if wk not in weeks_played: timeline.append(dict(week=wk, bye=True))
    timeline.sort(key=lambda x: x['week'])
    # the units against the league (stat-based offense and defense, grade-based subunits)
    try: sr = ST.unit_ranks(league, league.year).get(abbr, {})
    except Exception: sr = {}
    try: ur = GW.unit_ranks(league, t)
    except Exception: ur = {}
    ROWS = [('Pass Offense', 'QB'), ('Run Offense', 'backs'), ('Pass Block', 'pass block'), ('Receivers', 'receivers'), ('Pass Rush', 'pass rush'), ('Run Front', 'run front'), ('Corners', 'corners'), ('Safeties', 'safeties'), ('Linebackers', 'linebackers')]
    units = [dict(label=lab, rank=(ur[k][0] if ur.get(k) else None), of=(ur[k][1] if ur.get(k) else 32)) for lab, k in ROWS]
    sides = dict(offense=sr.get('oc'), defense=sr.get('dc'), kicking=sr.get('st'))
    # who exceeded and who fell short: this season's production against the player's grade
    S = league.stats.get(league.year, {}) or {}
    import xp as XP
    scored = []
    for p in t.active():
        line = S.get(p.pid)
        if not line: continue
        snaps = int(line.get('snaps', 0) or 0)
        if snaps < 200: continue
        epa = float(line.get('pass_epa', 0) or 0) + float(line.get('rush_epa', 0) or 0) + float(line.get('rec_epa', 0) or 0) + float(line.get('def_epa', 0) or 0)
        per = epa / max(1, snaps) * 100.0
        scored.append((per - 0.02 * (p.ovr - 75), p, per, snaps))
    scored.sort(key=lambda x: -x[0])
    def card(p, per, snaps, up):
        line = S.get(p.pid, {})
        bits = []
        if p.pos == 'QB': bits.append(f"{int(line.get('pass_yds', 0))} yds, {int(line.get('pass_td', 0))} TD, {int(line.get('ints', 0))} INT")
        elif p.pos in ('HB', 'FB'): bits.append(f"{int(line.get('rush_yds', 0))} rush yds, {int(line.get('rush_td', 0))} TD")
        elif p.pos in ('WR', 'TE'): bits.append(f"{int(line.get('rec', 0))} rec, {int(line.get('rec_yds', 0))} yds, {int(line.get('rec_td', 0))} TD")
        else: bits.append(f"{int(line.get('tackles', 0))} tkl, {float(line.get('sacks', 0) or 0):.0f} sk, {int(line.get('int_def', 0))} INT")
        return dict(pid=p.pid, name=p.name, pos=p.pos, no=getattr(p, 'number', None), ovr=round(p.ovr), age=int(p.age), line=bits[0], up=up)
    exceeded = [card(p, per, sn, True) for _s, p, per, sn in scored[:3]]
    short = [card(p, per, sn, False) for _s, p, per, sn in scored[-3:][::-1] if p.ovr >= 78]
    # next year's money and the players whose deals are up
    limit_next, committed_next, rollover, dead_next = next_year_cap(league, t)
    expiring = sorted([p for p in t.active() if p.contract and p.contract.years <= 1], key=lambda p: -p.ovr)
    pending = [dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), age=int(p.age), apy=round(float(getattr(p, 'apy', 0.0) or 0.0), 1), starter=(p in (t.depth.get(p.pos) or [])[:1])) for p in expiring[:8]]
    room = limit_next - committed_next
    slot = None
    try:
        import postseason as PS
        slot = PS.provisional_slot(league, getattr(session, 'post_live', None) or getattr(session, 'post', None), abbr)
    except Exception: slot = None
    return dict(rail=rail(session, league, abbr), club=club(abbr), year=league.year, record=f"{w}–{l}" + (f"–{d}" if d else ''), pct=round(pct, 3), expected=exp_words, expected_pct=round(exp, 2), slot=slot,
                finish=exit_, div_rank=div_rank, division=t.division, owner=dict(name=own['name'], mood=mood, line=owner_line, job=('Secure' if sec >= 0.7 else 'Safe' if sec >= 0.45 else 'Warming' if sec >= 0.25 else 'Hot Seat')),
                timeline=timeline, units=units, sides=sides, exceeded=exceeded, short=short, cap=dict(limit=round(limit_next, 1), committed=round(committed_next, 1), dead=round(dead_next, 1), rollover=round(rollover, 1), room=round(room, 1)),
                pending=pending)


# ============================================================ EXIT INTERVIEWS
# The days after the season: a few men want a word. Each meeting is a question in his voice and two or three
# answers; a promise goes on the ledger the negotiation system already keeps, a plain answer moves his morale,
# and what you said comes back later in his own words.
def build_exit_meetings(session, league, abbr):
    import morale as MO, negotiations as NG
    from views import surname
    t = league.teams[abbr]; year = league.year
    store = league.__dict__.setdefault('exit_meetings', {})
    user = getattr(league, 'user_team', None)
    slot = str(year) if abbr == user else f"{abbr}-{year}"
    if slot in store: return store[slot]
    meetings = []
    seen = set()
    def add(kind, p, quote, options):
        if p.pid in seen or len(meetings) >= 5: return
        seen.add(p.pid); meetings.append(dict(pid=p.pid, kind=kind, quote=quote, options=options, answer=None, said=None))
    starters = {pos: (ps[0] if ps else None) for pos, ps in t.depth.items()}
    # 1. the man who wants out
    for p in sorted(t.active(), key=lambda q: -q.ovr):
        if MO.wants_out(p):
            why = MO.request_reason(p)
            q = {'role': "I'm not going to sit behind somebody another year. I want to be somewhere I play.", 'contract': "I've been underpaid here for two years and everybody knows it. Fix it or move me.", 'losing': "I've got a few years left and I want to spend them winning. Are we going to?"}[why]
            add('wants_out', p, q, [dict(key='listen', label="We'll listen to offers", sub='He goes on the block; he settles down knowing you heard him', cost='block'),
                                    dict(key='stay', label="You're not going anywhere", sub='A no-trade promise on the ledger; break it and it costs you', cost='promise:no_trade'),
                                    dict(key='earn', label='Earn it', sub='No promise; he leaves the room angrier', cost='brush')])
            break
    # 2. the expiring starter
    exp = sorted([p for p in t.active() if p.contract and p.contract.years <= 1 and starters.get(p.pos) is p and p.ovr >= 76 and p.pos not in ('K', 'P', 'LS')], key=lambda q: -q.ovr)
    for p in exp[:2]:
        add('expiring', p, f"My deal's up. I'd like to stay, but I'm not going to wait on you into March. Am I coming back?",
            [dict(key='deal', label="We'll get a deal done before the market", sub='An extension by the new year goes on the ledger', cost='promise:extension_by'),
             dict(key='market', label="We'll see what the market says", sub='Honest; he hears it as a no', cost='brush'),
             dict(key='honest_no', label="We're going a different way", sub='He knows where he stands and stops waiting', cost='heard')])
    # 3. the young man behind a veteran
    for pos, ps in t.depth.items():
        if len(ps) < 2: continue
        s0, s1 = ps[0], ps[1]
        if s1.age <= 25 and s0.age >= 29 and s1.ovr >= s0.ovr - 3 and s1.pid not in seen:
            add('young', s1, f"I'm ready. {surname(s0.name)} is {int(s0.age)}. When do I get my shot?",
                [dict(key='camp', label="The job is yours to win in camp", sub='A starting-role promise; sit him in September and it breaks', cost='promise:starting_role'),
                 dict(key='patient', label="Be patient", sub='He leaves unhappy', cost='brush'),
                 dict(key='truth', label="You're the plan for next year, not this one", sub='Told straight; he takes it', cost='heard')])
            break
    # 4. the star with two years left
    for p in sorted(t.active(), key=lambda q: -q.ovr):
        if p.contract and p.contract.years == 2 and p.ovr >= 84 and p.age <= 30 and p.pid not in seen:
            add('star', p, "I'm the best player in this building and I'm on a deal from three years ago. Are we doing this in the spring?",
                [dict(key='spring', label="We'll extend you this offseason", sub='An extension promise by the new year', cost='promise:extension_by'),
                 dict(key='next', label="Next year", sub="He'll remember", cost='brush'),
                 dict(key='captain', label="You're a captain here; the money follows", sub='A captaincy on the ledger, and the extension talk stays open', cost='promise:captaincy')])
            break
    # 5. the unhappy veteran
    def _mv(q):
        m_ = MO.ensure(q)
        if m_ is None: return 60.0
        val = getattr(m_, 'value', 60.0)
        return float(val() if callable(val) else val)
    for p in sorted(t.active(), key=_mv):
        mv = _mv(p)
        if mv < 42 and p.age >= 27 and p.pid not in seen and not MO.wants_out(p):
            add('unhappy', p, "This year wore on me. I need to know the room's going to be different, or I need to know now.",
                [dict(key='captaincy', label="You'll wear the C", sub='A captaincy promise', cost='promise:captaincy'),
                 dict(key='changes', label="There will be changes, and you're part of them", sub='He is heard', cost='heard'),
                 dict(key='march', label="Talk to me in March", sub='Brushed off', cost='brush')])
            break
    store[slot] = meetings
    return meetings


def exit_interviews(session, league, abbr):
    from views import club, surname
    t = league.teams[abbr]
    ms = build_exit_meetings(session, league, abbr)
    rows = []
    for mt in ms:
        p = league.player(mt['pid'])
        if p is None: continue
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, no=getattr(p, 'number', None), ovr=round(p.ovr), age=int(p.age), years=(p.contract.years if p.contract else 0), apy=round(float(getattr(p, 'apy', 0.0) or 0.0), 1),
                         kind=mt['kind'], quote=mt['quote'], options=mt['options'], answer=mt.get('answer'), said=mt.get('said')))
    return dict(rail=rail(session, league, abbr), club=club(abbr), year=league.year, meetings=rows, open=sum(1 for r in rows if not r['answer']))


def exit_answer(session, league, abbr, pid, key):
    """Your answer in the room: the promise on the ledger, the morale, and what he said back."""
    import morale as MO, negotiations as NG, morale_system as MS
    from views import surname
    t = league.teams[abbr]; p = league.player(pid)
    ms = build_exit_meetings(session, league, abbr)
    mt = next((x for x in ms if x['pid'] == pid), None)
    if mt is None or p is None: return dict(ok=False, why='no meeting with him')
    if mt.get('answer'): return dict(ok=False, why='you have already answered him')
    opt = next((o for o in mt['options'] if o['key'] == key), None)
    if opt is None: return dict(ok=False, why='not one of the answers')
    cost = opt['cost']; m = MO.ensure(p)
    said = ''
    if cost.startswith('promise:'):
        kind = cost.split(':', 1)[1]
        NG.record_promise(league, p.pid, abbr, kind, source='exit')
        if m is not None: m.apply('promised')
        said = {'no_trade': "Then I'm here. Don't make me regret saying that.", 'extension_by': "Good. My agent will be calling.", 'starting_role': "I'll be ready. Don't sit me.", 'captaincy': "I'll hold them to it, and you."}.get(kind, "Alright.")
    elif cost == 'block':
        p.xp_spent['_on_block'] = league.year
        if m is not None: m.apply('heard_out')
        said = "That's all I wanted to hear. Wherever it is, thank you for being straight."
    elif cost == 'heard':
        if m is not None: m.apply('heard_out')
        said = "I can work with that. I'd rather know."
    else:
        if m is not None: m.apply('brushed_off')
        said = "Right." if mt['kind'] != 'wants_out' else "Then we'll do this the other way."
    mt['answer'] = key; mt['said'] = said
    import inbox as IB
    IB.post(league, 'club', f"{p.name}, after the meeting", f"You told him: {opt['label'].lower()}. He said: \"{said}\"", sender=surname(p.name))
    return dict(ok=True, said=said)


def ai_exit_meetings(league, abbr, rng):
    """The other clubs hold their meetings too. The GM answers by his nature: a patient builder promises the young
    player his shot and the star his deal, a win-now GM promises less and tells more of them to earn it, and every
    promise goes on the same ledger, so an AI club that breaks one lives with the request that follows."""
    import morale as MO, negotiations as NG
    t = league.teams.get(abbr)
    if t is None or t.gm is None: return 0
    store = league.__dict__.setdefault('exit_meetings', {})
    key = f"{abbr}-{league.year}"
    if key in store: return 0
    ms = build_exit_meetings(None, league, abbr)
    gm = t.gm
    patience = float(getattr(gm, 'youth', 0.5)); win_now = float(getattr(gm, 'aggression', 0.5))
    n = 0
    for mt in ms:
        p = league.player(mt['pid']); m = MO.ensure(p) if p is not None else None
        if p is None: continue
        opts = mt['options']
        promise = [o for o in opts if o['cost'].startswith('promise:')]; heard = [o for o in opts if o['cost'] in ('heard', 'block')]; brush = [o for o in opts if o['cost'] == 'brush']
        r = rng.random()
        p_prom = 0.25 + 0.35 * patience - 0.15 * win_now
        p_brush = 0.15 + 0.15 * win_now
        if r < p_prom and promise: o = promise[0]
        elif r < p_prom + p_brush and brush: o = brush[0]
        else: o = (heard or promise or opts)[0]
        cost = o['cost']
        if cost.startswith('promise:'):
            NG.record_promise(league, p.pid, abbr, cost.split(':', 1)[1], source='exit')
            if m is not None: m.apply('promised')
        elif cost == 'block':
            p.xp_spent['_on_block'] = league.year
            if m is not None: m.apply('heard_out')
        elif cost == 'heard':
            if m is not None: m.apply('heard_out')
        else:
            if m is not None: m.apply('brushed_off')
        mt['answer'] = o['key']; n += 1
    return n

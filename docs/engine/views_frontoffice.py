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
ARCH_WORDS = {'shanahan_tree': ('Shanahan Tree', 'Wide zone, two backs, play action off it, motion everywhere.'), 'mcvay_tree': ('McVay Tree', 'Eleven personnel, zone runs, play action and motion, quick game.'),
              'reid_spread': ('Reid Spread', 'Twelve personnel spread wide, pass first, fourth downs aggressive.'), 'harbaugh_power': ('Harbaugh Power', 'Gap runs from twenty-one, play action shots, go for it.'),
              'air_raid_spread': ('Air Raid', 'Eleven, pass heavy, tempo, shots downfield.'), 'fangio_two_high': ('Fangio Two-High', 'Three-four front, zone, two safeties deep, light box.'),
              'seattle_cover3': ('Seattle Cover 3', 'Four-three, single high zone, rush four.'), 'pressure_man': ('Pressure Man', 'Multiple front, man coverage, blitz heavy.'),
              'flores_blitz': ('Flores Blitz', 'Three-four, zone behind an all-out blitz.')}


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
    weights = dict(wins=round(0.5 + 0.3 * (1 - getattr(t, 'owner_patience', 0.5)), 2), stars=round(getattr(t, 'owner_star_pull', 0.5), 2), spend=round(getattr(t, 'owner_spend', 0.5), 2), acumen=round(getattr(t, 'owner_acumen', 0.5), 2))
    reviews = [dict(year=r.get('year'), record=r.get('record'), line=r.get('line')) for r in (getattr(t, 'owner_reviews', None) or [])]
    import staff as ST
    return dict(rail=rail(session, league, abbr), owner=own, mood=_owner_mood(t), job=('Secure' if sec >= 0.7 else 'Safe' if sec >= 0.45 else 'Warming' if sec >= 0.25 else 'Hot Seat'), security=round(sec, 2),
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


def identity(session, league, abbr, preview=None):
    """preview: dict of lean changes to show before confirming."""
    import gm_engine as GE, identity_catalog as IC
    t = league.teams[abbr]; gm = t.gm
    cur = _leans(gm)
    after = copy.copy(gm)
    if preview:
        for k, v in preview.items():
            if k in cur: setattr(after, k, (float(v) if k not in [c for c, *_ in CHOICES] else v))
    keys = GE.scheme_of(after) or []
    archs = [dict(key=k, name=ARCH_WORDS.get(k, (k, ''))[0], words=ARCH_WORDS.get(k, ('', ''))[1], side=('offense' if 'offence' in v else 'defense'), leans={kk: vv for side in v.values() for kk, vv in side.items()})
             for k, v in IC.ARCHETYPES.items() if 'offence' in v or 'defence' in v]
    losers, gainers = _misfits(league, t, after) if preview else ([], [])
    fit_by_pos, misfits = _fit_by_position(league, t)
    # the archetype each side of the club is closest to, so the page can say what the identity is
    def dist(a):
        d = 0.0; n = 0
        for k, val in a['leans'].items():
            kk = {'blocking': 'off_blocking', 'personnel': 'off_personnel', 'front': 'def_front'}.get(k, k)
            if kk in cur and isinstance(val, (int, float)) and isinstance(cur[kk], (int, float)): d += (float(val) - float(cur[kk])) ** 2; n += 1
            elif kk in cur: d += (0.0 if cur[kk] == val else 0.25); n += 1
        return d / max(1, n)
    nearest = {}
    for side in ('offense', 'defense'):
        cands = [a for a in archs if a['side'] == side]
        if cands: nearest[side] = min(cands, key=dist)['key']
    WORDS = {'pass_lean': ('run-first', 'balanced', 'pass-first'), 'play_action': ('little play action', 'some play action', 'play-action heavy'), 'motion': ('a still offense', 'some motion', 'motion on most snaps'),
             'tempo': ('a huddle offense', 'a normal tempo', 'up-tempo'), 'deep': ('the short game', 'a mixed depth', 'shots downfield'), 'fourth_down': ('punts on fourth', 'plays fourth by the book', 'goes for it'),
             'coverage': ('zone coverage', 'mixed coverage', 'man coverage'), 'shell': ('single high', 'mixed shells', 'two high'), 'blitz': ('rushes four', 'blitzes some', 'sends heat'), 'box': ('a light box', 'a standard box', 'a loaded box')}
    def word(k, val):
        lo, mid, hi = WORDS[k]; return lo if val < 0.38 else hi if val > 0.62 else mid
    lean_words = {k: word(k, float(cur[k])) for k in WORDS if k in cur}
    summary = dict(offense=f"{lean_words['pass_lean'].capitalize()}, {cur['off_blocking']} runs from {cur['off_personnel']} personnel, {lean_words['play_action']}, {lean_words['motion']}, {lean_words['deep']}.",
                   defense=f"{cur['def_front']} front, {lean_words['coverage']}, {lean_words['shell']}, {lean_words['blitz']}, {lean_words['box']}.")
    words = dict(zone='zone runs', gap='gap runs', one_gap='one-gap front', two_gap='two-gap front', man='man coverage', zone_cov='zone coverage', heavy_te='blocking tight ends', spread_te='route-running tight ends')
    return dict(rail=rail(session, league, abbr), coach=gm.name, prestige=round(getattr(gm, 'prestige', 50)), rigidity=round(float(getattr(gm, 'scheme_rigidity', 0.5)), 2),
                leans=cur, after=_leans(after) if preview else None, keys=[words.get(k, k) for k in keys],
                off=[dict(key=k, label=l, lo=lo, hi=hi) for k, l, lo, hi in LEANS_OFF], deff=[dict(key=k, label=l, lo=lo, hi=hi) for k, l, lo, hi in LEANS_DEF],
                choices=[dict(key=k, label=l, options=o) for k, l, o in CHOICES], archetypes=archs, nearest=nearest, lean_words=lean_words, summary=summary, losers=losers, gainers=gainers, fit_by_pos=fit_by_pos, misfits=misfits,
                history=[dict(year=h.get('year'), week=h.get('week'), change=h.get('change')) for h in (getattr(t, 'identity_history', None) or [])])


def _fit_by_position(league, t):
    """How the starters fit the scheme, by group, and the men who fit it worst."""
    import gm_engine as GE
    G = {'QB': ['QB'], 'RB': ['HB', 'FB'], 'WR': ['WR'], 'TE': ['TE'], 'OL': ['LT', 'LG', 'C', 'RG', 'RT'], 'DL': ['LEDG', 'DT', 'REDG'], 'LB': ['MIKE', 'WILL', 'SAM'], 'DB': ['CB', 'FS', 'SS']}
    n = {'QB': 1, 'RB': 1, 'WR': 3, 'TE': 1, 'OL': 5, 'DL': 4, 'LB': 2, 'DB': 5}
    rows = []; allmen = []
    for g, poss in G.items():
        men = sorted((p for p in t.active() if p.pos in poss), key=lambda p: -p.ovr)[:n[g]]
        fits = []
        for p in men:
            try: f = float(GE.scheme_fit(p.ratings, p.pos, t))
            except Exception: f = 0.0
            fits.append(f); allmen.append((p, f))
        rows.append(dict(group=g, fit=(round(float(np.mean(fits)), 1) if fits else 0.0), n=len(men)))
    keep = set(getattr(t, 'misfit_keep', []) or [])
    mis = sorted(allmen, key=lambda x: x[1])[:6]
    misfits = [dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), fit=round(f, 1), kept=(p.pid in keep)) for p, f in mis if f < -1.0]
    return rows, misfits


def act_keep_misfit(league, abbr, pid):
    t = league.teams[abbr]; keep = set(getattr(t, 'misfit_keep', []) or []); keep.add(pid); t.misfit_keep = sorted(keep)
    return dict(ok=True, line='Kept. He stays off the misfit list.')


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
        pools[role] = [dict(ST.card(c), role_key=role) for c in ST.pool_for(league, role)[:8]]
    poaches = [p for p in (getattr(league, 'poaches', None) or []) if p.get('team') == abbr and p.get('state') == 'open']
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
        committed = sum(by.values()) + dead
        years.append(dict(year=yr, limit=round(limit, 1), by={g: round(v, 1) for g, v in by.items()}, dead=round(dead, 1), committed=round(committed, 1), space=round(limit - committed, 1), under_contract=n))
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
    return dict(rail=rail(session, league, abbr), years=years, rows=rows, cap_space=round(t.cap_space, 1), dead_rows=dead_rows, dead_total=round(float(t.cap.dead), 1), dead_next=round(float(getattr(t.cap, 'dead_next', 0.0) or 0.0), 1), largest=largest)


def act_restructure_preview(league, abbr, pid, amount=None, void_years=0):
    import contracts as CT
    r = CT.restructure_preview(league, pid, amount=(float(amount) if amount is not None else None), void_years=int(void_years or 0))
    return r if isinstance(r, dict) else dict(ok=False, why='nothing to restructure')


def act_restructure(league, abbr, pid, amount=None, void_years=0):
    import contracts as CT
    p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    r = CT.restructure_user(league, pid, amount=(float(amount) if amount is not None else None), void_years=int(void_years or 0))
    return r if isinstance(r, dict) else dict(ok=bool(r))

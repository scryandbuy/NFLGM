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
def owner(session, league, abbr):
    import firing_model as FM
    from views import _owner_mood
    t = league.teams[abbr]; h = t.hist()
    sec = FM.job_security(h)
    w, l, d = t.record
    exp = float(h.get('expected_pct') or 0.5)
    exp_words = 'a title run' if exp >= 0.72 else 'the playoffs' if exp >= 0.56 else 'a winning season' if exp >= 0.5 else 'progress' if exp >= 0.4 else 'patience while you rebuild'
    weights = dict(wins=round(0.5 + 0.3 * (1 - getattr(t, 'owner_patience', 0.5)), 2), stars=round(getattr(t, 'owner_star_pull', 0.5), 2), spend=round(getattr(t, 'owner_spend', 0.5), 2), acumen=round(getattr(t, 'owner_acumen', 0.5), 2))
    reviews = [dict(year=r.get('year'), record=r.get('record'), line=r.get('line')) for r in (getattr(t, 'owner_reviews', None) or [])]
    import staff as ST
    return dict(rail=rail(session, league, abbr), mood=_owner_mood(t), job=('Secure' if sec >= 0.7 else 'Safe' if sec >= 0.45 else 'Warming' if sec >= 0.25 else 'Hot Seat'), security=round(sec, 2),
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
    words = dict(zone='zone runs', gap='gap runs', one_gap='one-gap front', two_gap='two-gap front', man='man coverage', zone_cov='zone coverage', heavy_te='blocking tight ends', spread_te='route-running tight ends')
    return dict(rail=rail(session, league, abbr), coach=gm.name, prestige=round(getattr(gm, 'prestige', 50)), rigidity=round(float(getattr(gm, 'scheme_rigidity', 0.5)), 2),
                leans=cur, after=_leans(after) if preview else None, keys=[words.get(k, k) for k in keys],
                off=[dict(key=k, label=l, lo=lo, hi=hi) for k, l, lo, hi in LEANS_OFF], deff=[dict(key=k, label=l, lo=lo, hi=hi) for k, l, lo, hi in LEANS_DEF],
                choices=[dict(key=k, label=l, options=o) for k, l, o in CHOICES], archetypes=archs, losers=losers, gainers=gainers,
                history=[dict(year=h.get('year'), week=h.get('week'), change=h.get('change')) for h in (getattr(t, 'identity_history', None) or [])])


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
    return dict(rail=rail(session, league, abbr), years=years, rows=rows, cap_space=round(t.cap_space, 1))


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

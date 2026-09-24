"""
DRAFT VIEWS. The Scouting Board, Draft Day, and Picks pages, and what their
buttons do. Prospects are seen through YOUR scouts' eyes; the true rating is
never shown.
"""
from views import club, rail

SLOT = lambda pk: f"{pk.round}.{((pk.selection - 1) % 32) + 1}" if pk.selection else f"R{pk.round}"


def _pool(league):
    return list(getattr(league, 'draft_pool', None) or []) or list(getattr(league, 'next_class', None) or [])


def _prospect(league, abbr, p, taken=()):
    v = (getattr(league, 'scouting', None) or {}).get(abbr, {}).get(p.pid)
    c = (getattr(league, 'consensus', None) or {}).get(p.pid)
    if v is None: return None
    mine = round(float(v['ovr']))
    cons = round(float(c['ovr'])) if c else None
    gap = (mine - cons) if cons is not None else None
    comb = getattr(p, 'combine', None) or {}
    flags = list(v.get('flags') or [])
    med = getattr(p, 'medical', None)
    if med and isinstance(med, dict) and med.get('flag'): flags.append(med['flag'])
    import scouting as SC
    return dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), college=getattr(p, 'college', None) or '', small=(not SC._power(p)), visited=('visited' in flags or p.pid in (getattr(league, 'user_visits', None) or [])),
                proj=(f"R{min(7, (c['rank'] - 1) // 32 + 1)}" if c and c.get('rank') else '—'), mine=mine, ceiling=f"{round(float(v['pot_lo']))}–{round(float(v['pot_hi']))}",
                cons=cons, cons_rank=(c.get('rank') if c else None), gap=gap, reads=int(v.get('reads', 1) or 1), flags=flags,
                forty=(round(float(comb['forty']), 2) if comb.get('forty') else None), vert=(round(float(comb['vert']), 1) if comb.get('vert') else None),
                bench=(int(comb['bench']) if comb.get('bench') else None), taken=(p.pid in taken))


def _my_rank(rows):
    """Your board's order, built the way the consensus one is: within each position group by your
    read blended with the ceiling, then each man's rank becomes an expected slot off his position's
    curve, so a punter graded 93 sits where punters go, not at the top."""
    import draft as DFT
    groups = {}
    for r in rows: groups.setdefault(DFT.SLOT_GROUP.get(r['pos'], r['pos']), []).append(r)
    slot = {}
    for g, rs in groups.items():
        rs.sort(key=lambda r: -(0.6 * r['mine'] + 0.4 * float(r['ceiling'].split('–')[1])))
        for i, r in enumerate(rs): slot[r['pid']] = DFT.expected_slot(r['pos'], i)
    for i, r in enumerate(sorted(rows, key=lambda r: slot[r['pid']]), 1): r['my_rank'] = i


def board(session, league, abbr):
    pool = _pool(league)
    taken = set(session.draft.taken) if getattr(session, 'draft', None) else set()
    rows = [r for r in (_prospect(league, abbr, p, taken) for p in pool) if r]
    _my_rank(rows)
    rows.sort(key=lambda r: r['my_rank'])
    import staff as ST
    t = league.teams[abbr]
    scout = (getattr(t, 'staff', None) or {}).get('scout')
    import spring as SP
    visits = list(getattr(league, 'user_visits', None) or [])
    spring_done = any(x.get('year') == league.year for x in (getattr(league, 'spring_news', None) or []))
    return dict(rail=rail(session, league, abbr), rows=rows, count=len(rows), year=(league.year + 1 if not getattr(league, 'draft_pool', None) else league.year),
                visits=visits, visits_max=SP.VISITS, spring_done=spring_done,
                scout=(dict(name=scout.name, rating=round(scout.rating)) if scout else None), live=bool(getattr(session, 'draft', None)),
                note=None if rows else 'The class is scouted in camp; the board fills once the season begins.')


def act_visit(session, league, abbr, pid):
    import spring as SP
    cur = list(getattr(league, 'user_visits', None) or [])
    if pid in cur: cur.remove(pid); SP.set_user_visits(league, cur); return dict(ok=True, line='Visit cancelled.', visits=cur)
    if len(cur) >= SP.VISITS: return dict(ok=False, why=f'all {SP.VISITS} visits are spoken for', visits=cur)
    cur.append(pid); SP.set_user_visits(league, cur); p = league.player(pid)
    return dict(ok=True, line=f"{p.name if p else pid} gets a visit ({len(cur)} of {SP.VISITS}).", visits=cur)


def spring(session, league, abbr):
    """The Spring: stock moves by event, your visits with what the second look found, the flags."""
    news = [x for x in (getattr(league, 'spring_news', None) or []) if x.get('year') == league.year]
    pool = {p.pid: p for p in _pool(league)}
    moves = []
    for x in news:
        if x.get('kind') != 'stock': continue
        p = pool.get(x['pid']) or league.player(x['pid'])
        moves.append(dict(event=x.get('event'), pid=x['pid'], name=x.get('name'), pos=x.get('pos'), college=x.get('college'), frm=x.get('frm'), to=x.get('to'), delta=(x.get('frm') or 0) - (x.get('to') or 0), why=x.get('why', '')))
    risers = sorted([m for m in moves if m['delta'] > 0], key=lambda m: -m['delta'])[:12]
    fallers = sorted([m for m in moves if m['delta'] < 0], key=lambda m: m['delta'])[:12]
    events = []
    for ev in ('combine', 'Senior Bowl', 'pro days', 'visits'):
        ms = [m for m in moves if m['event'] == ev]
        events.append(dict(event=ev.title() if ev != 'Senior Bowl' else ev, n=len(ms), up=sum(1 for m in ms if m['delta'] > 0), down=sum(1 for m in ms if m['delta'] < 0)))
    visited = []
    for pid in (getattr(league, 'user_visits', None) or []):
        p = pool.get(pid) or league.player(pid)
        if p is None: continue
        r = _prospect(league, abbr, p)
        if r: visited.append(r)
    flagged = [r for r in (_prospect(league, abbr, p) for p in pool.values()) if r and any(f for f in r['flags'] if f != 'visited')]
    flagged.sort(key=lambda r: (r['cons_rank'] if r['cons_rank'] is not None else 999))
    done = bool(news)
    return dict(rail=rail(session, league, abbr), done=done, events=events, risers=risers, fallers=fallers, visited=visited, flagged=flagged[:40],
                note=None if done else 'The combine, the Senior Bowl, pro days and the thirty visits happen in the Spring step of the offseason. Name your visits on the board now; the second look is the sharpest read your scouts get.')


def act_sim_round(session, league, abbr):
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    if D.on_user(): return dict(ok=False, why='you are on the clock; make your pick first')
    evs = D.sim_round()
    if D.done: session._draft_over(); return dict(ok=True, line='The draft is over.', done=True)
    return dict(ok=True, line=(f"{len(evs)} picks made; you are on the clock." if D.on_user() else f"{len(evs)} picks made."))


def act_trade_up(session, league, abbr, target, sends):
    """Buy a pick ahead of yours: the target pick (id) for the picks you send (ids), priced by its owner."""
    import views_personnel as VP
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    pk = None
    for q in D.picks[D.i:]:
        if f"{q.year}-{q.round}-{q.original}" == target: pk = q; break
    if pk is None or pk.owner == abbr: return dict(ok=False, why='that pick is not on the board')
    r = VP.act_propose(league, abbr, pk.owner, list(sends), [target])
    if r.get('done'):
        return dict(ok=True, done=False, line=f"Traded up to {SLOT(pk)} with {pk.owner}." + (' You are on the clock.' if D.on_user() else ''))
    return dict(ok=True, done=False, line=r.get('why', 'They passed.'))


def act_read_trade_up(session, league, abbr, target):
    """What the owner would want for the pick, from your picks, cheapest first."""
    import views_personnel as VP
    D = session.draft
    pk = next((q for q in D.picks[D.i:] if f"{q.year}-{q.round}-{q.original}" == target), None)
    if pk is None: return dict(ok=False, why='that pick is not on the board')
    mine = [q for q in D.picks[D.i:] if q.owner == abbr]
    first = [f"{q.year}-{q.round}-{q.original}" for q in mine[:1]]
    r = VP.act_ask(league, abbr, pk.owner, first, [target])
    return dict(ok=True, owner=club(pk.owner), slot=SLOT(pk), line=r.get('line', ''), sends=first + list(r.get('adds', [])))


# ------------------------------------------------------------ Draft Day
def draft_day(session, league, abbr):
    D = getattr(session, 'draft', None)
    r = rail(session, league, abbr)
    if D is None or D.done:
        ld = getattr(league, 'last_draft', None)
        return dict(rail=r, live=False, last=(_results(league, ld) if ld else None), note='The draft is not on. It comes in the offseason after the Spring; you will be on the clock here.')
    pk = D.current()
    results = [dict(sel=s, slot=f"{(s - 1) // 32 + 1}.{(s - 1) % 32 + 1}", team=club(t), name=p.name, pos=p.pos, cons_rank=(league.consensus.get(p.pid) or {}).get('rank')) for s, t, p in D.results[-12:]][::-1]
    mine_next = [dict(sel=q.selection, slot=SLOT(q), round=q.round) for q in D.picks[D.i:] if q.owner == abbr][:4]
    avail = [r for r in (_prospect(league, abbr, p, D.taken) for p in D.available()) if r]
    avail.sort(key=lambda x: (x['cons_rank'] if x['cons_rank'] is not None else 999))
    best = avail[:8]
    _my_rank(avail); my_board = sorted(avail, key=lambda x: x['my_rank'])[:40]
    # who is on the clock and the next few
    clock = [dict(sel=q.selection, slot=SLOT(q), team=club(q.owner), mine=(q.owner == abbr), id=f"{q.year}-{q.round}-{q.original}") for q in D.picks[D.i:D.i + 8]]
    return dict(rail=r, live=True, on_user=D.on_user(), current=(dict(sel=pk.selection, slot=SLOT(pk), round=pk.round, team=club(pk.owner), original=pk.original) if pk else None),
                clock=clock, results=results, mine_next=mine_next, best=best, board=my_board, picks_left=len(D.picks) - D.i, total=len(D.picks), trades=len(D.trades))


def _results(league, ld):
    out = []
    for s, t, pid in ld['results']:
        p = league.player(pid)
        out.append(dict(sel=s, slot=f"{(s - 1) // 32 + 1}.{(s - 1) % 32 + 1}", team=club(t), name=(p.name if p else pid), pos=(p.pos if p else ''), mine=(t == getattr(league, 'user_team', None))))
    return dict(year=ld['year'], rows=out, trades=ld.get('trades', 0))


def act_pick(session, league, abbr, pid):
    D = session.draft
    if D is None or not D.on_user(): return dict(ok=False, why='not your pick')
    try: ev = D.make_pick(pid)
    except ValueError as e: return dict(ok=False, why=str(e))
    p = ev[3]; line = f"You take {p.name}, {p.pos}, at {ev[1]}."
    D.sim_to_user()
    if D.done: session._draft_over(); return dict(ok=True, line=line + ' The draft is over.', done=True)
    return dict(ok=True, line=line, done=False)


def act_sim_to_me(session, league, abbr):
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    if D.on_user(): return dict(ok=True, line='You are on the clock.')
    evs = D.sim_to_user()
    if D.done: session._draft_over(); return dict(ok=True, line='The draft is over.', done=True)
    return dict(ok=True, line=f"{len(evs)} picks made. You are on the clock.")


def act_auto_pick(session, league, abbr):
    """Take the top of your own board at this pick, then sim to your next."""
    D = session.draft
    if D is None or not D.on_user(): return dict(ok=False, why='not your pick')
    rows = D.board_for(abbr)
    return act_pick(session, league, abbr, rows[0][1].pid)


def act_finish_auto(session, league, abbr):
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    D.auto = True; D.sim_all(); session._draft_over()
    return dict(ok=True, line='The rest of the draft ran on auto.', done=True)


def act_offers(session, league, abbr):
    D = session.draft
    if D is None or not D.on_user(): return dict(ok=False, why='offers come when you are on the clock')
    pk = D.current(); offers = D.gather_offers(pk)
    out = [dict(i=i, team=club(o['team']), gm=o['gm'], summary=o['summary'], target_pos=o['target_pos'], value=o['value']) for i, o in enumerate(offers)]
    session._draft_offers = offers
    return dict(ok=True, offers=out, line=(f"{len(out)} clubs want to come up." if out else 'Nobody is calling for this pick.'))


def act_accept_offer(session, league, abbr, i):
    D = session.draft; offers = getattr(session, '_draft_offers', None) or []
    if D is None or not D.on_user() or int(i) >= len(offers): return dict(ok=False, why='that offer is gone')
    o = offers[int(i)]
    ev = D.accept_offer(o)
    session._draft_offers = []
    D.sim_to_user()
    if D.done: session._draft_over(); return dict(ok=True, line='Traded. The draft is over.', done=True)
    return dict(ok=True, line=f"Traded the pick to {o['team']} for {', '.join(o['summary'])}." + (' You are on the clock again.' if D.on_user() else ''), done=False)


# ------------------------------------------------------------ Picks
def picks(session, league, abbr):
    t = league.teams[abbr]
    years = {}
    for pk in sorted(t.picks, key=lambda k: (k.year, k.round, k.selection or 0)):
        if pk.used_on: continue
        years.setdefault(pk.year, []).append(dict(round=pk.round, slot=SLOT(pk), original=pk.original, own=(pk.original == abbr), via=(None if pk.original == abbr else club(pk.original))))
    # picks of ours held by others
    gone = []
    for other, ot in league.teams.items():
        if other == abbr: continue
        for pk in ot.picks:
            if pk.original == abbr and not pk.used_on: gone.append(dict(year=pk.year, round=pk.round, slot=SLOT(pk), holder=club(other)))
    gone.sort(key=lambda g: (g['year'], g['round']))
    ld = getattr(league, 'last_draft', None)
    return dict(rail=rail(session, league, abbr), years=[dict(year=y, picks=v) for y, v in sorted(years.items())], gone=gone, last=(_results(league, ld) if ld else None))

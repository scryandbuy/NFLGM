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
    # the words the board shows for what the room knows
    words = []
    if 'visited' in flags or p.pid in (getattr(league, 'user_visits', None) or []): words.append('Visited')
    if getattr(p, 'age', 22) >= 22 and any(x.get('pid') == p.pid and x.get('event') == 'Senior Bowl' for x in (getattr(league, 'spring_news', None) or [])): words.append('Sr. Bowl')
    if 'character' in flags: words.append('Character')
    if 'medical' in flags or (med and isinstance(med, dict) and med.get('flag')): words.append('Medical')
    if not SC._power(p): words.append('Small School')
    if getattr(p, 'age', 22) < 21.5: words.append('Underclassman')
    mv = next((x for x in reversed(getattr(league, 'spring_news', None) or []) if x.get('pid') == p.pid and x.get('kind') == 'stock'), None)
    if mv and (mv.get('to') or 0) - (mv.get('frm') or 0) >= 10: words.append('Faller')
    elif mv and (mv.get('frm') or 0) - (mv.get('to') or 0) >= 10: words.append('Riser')
    cls_year = ('Senior' if p.age >= 22.5 else 'Junior' if p.age >= 21.5 else 'Sophomore')
    h = getattr(p, 'height', None); size = (f"{int(h) // 12}'{int(h) % 12}\" {int(getattr(p, 'weight', 0) or 0)}".strip() if h else '')
    rk = c.get('rank') if c else None
    proj_range = (f"{max(1, rk - 4)}–{rk + 4}" if rk and rk <= 224 else '—')
    return dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), college=getattr(p, 'college', None) or '', small=(not SC._power(p)), visited=('visited' in flags or p.pid in (getattr(league, 'user_visits', None) or [])),
                cls_year=cls_year, size=size, words=words, proj_range=proj_range, my_round=None,
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
    # my grade as a round, from where my read ranks him against the class
    for r in rows:
        r['my_round'] = f"R{min(7, (r['my_rank'] - 1) // 32 + 1)}" if r.get('my_rank') else None
    needs = _needs(league, league.teams[abbr])
    ub = _user_board(league, rows)
    visits = list(getattr(league, 'user_visits', None) or [])
    spring_done = any(x.get('year') == league.year for x in (getattr(league, 'spring_news', None) or []))
    return dict(rail=rail(session, league, abbr), rows=rows, count=len(rows), year=(league.year + 1 if not getattr(league, 'draft_pool', None) else league.year),
                visits=visits, visits_max=SP.VISITS, spring_done=spring_done, needs=sorted(needs), user_board=ub, my_slot=_my_first_slot(league, abbr), read=_board_read(league, abbr, rows, ub, needs),
                scout=(dict(name=scout.name, rating=round(scout.rating)) if scout else None), live=bool(getattr(session, 'draft', None)),
                note=None if rows else 'The class is scouted in camp; the board fills once the season begins.')


NEED_GROUPS = {'QB': ['QB'], 'RB': ['HB', 'FB'], 'WR': ['WR'], 'TE': ['TE'], 'OL': ['LT', 'LG', 'C', 'RG', 'RT'], 'EDGE': ['LEDG', 'REDG'], 'DT': ['DT'], 'LB': ['MIKE', 'WILL', 'SAM'], 'CB': ['CB'], 'S': ['FS', 'SS']}


def _needs(league, t):
    """The groups where a starter's deal is up or the depth is thin."""
    out = set()
    for g, poss in NEED_GROUPS.items():
        men = sorted((p for p in t.active() if p.pos in poss), key=lambda p: -p.ovr)
        n_start = {'QB': 1, 'RB': 1, 'WR': 3, 'TE': 1, 'OL': 5, 'EDGE': 2, 'DT': 2, 'LB': 2, 'CB': 3, 'S': 2}[g]
        starters = men[:n_start]
        if len(men) < n_start + 1 or any(p.contract and p.contract.years <= 1 for p in starters) or (starters and min(p.ovr for p in starters) < 70): out.add(g)
    return out


def _my_first_slot(league, abbr):
    t = league.teams[abbr]
    pk = next((k for k in sorted(t.picks, key=lambda k: (k.year, k.round, k.selection or 99)) if not k.used_on), None)
    if pk is None: return None
    if pk.selection: return f"{pk.round}.{((pk.selection - 1) % 32) + 1}"
    import views_personnel as VP
    proj = VP._proj_slot(league, pk); return f"{pk.round}.{proj}" if proj else f"R{pk.round}"


def _user_board(league, rows):
    """The GM's own board: his order, plus a Do Not Draft list. Men he has not placed follow his scouts' read."""
    ub = getattr(league, 'user_board', None) or {}
    order = [pid for pid in (ub.get('order') or []) if any(r['pid'] == pid and not r['taken'] for r in rows)]
    dnd = [pid for pid in (ub.get('dnd') or []) if any(r['pid'] == pid and not r['taken'] for r in rows)]
    byid = {r['pid']: r for r in rows}
    placed = [byid[pid] for pid in order]
    # tiers by my grade: first-round grades, second-round grades, the rest
    def tier(r): return 1 if (r.get('my_rank') or 999) <= 32 else 2 if (r.get('my_rank') or 999) <= 64 else 3
    return dict(order=[dict(pid=r['pid'], tier=tier(r)) for r in placed], dnd=[dict(pid=pid, why=(', '.join(w for w in byid[pid]['words'] if w in ('Medical', 'Character')) or 'your call')) for pid in dnd], saved=bool(ub.get('order')))


def _board_read(league, abbr, rows, ub, needs):
    """The assistants on the board: the need, the one player in range graded above the league, the value, and the fallback."""
    t = league.teams[abbr]
    parts = []
    exp = [p for p in t.active() if p.contract and p.contract.years <= 1 and p.ovr >= 74]
    if needs:
        from views import surname
        g = sorted(needs)[0]; men = [surname(p.name) for p in exp if p.pos in NEED_GROUPS[g]][:2]
        parts.append(f"{g} is the need" + (f" with {' and '.join(men)} expiring" if men else ''))
    slot = _my_first_slot(league, abbr)
    try: slot_n = int(slot.split('.')[1]) if slot and '.' in slot else 24
    except Exception: slot_n = 24
    in_range = [r for r in rows if not r['taken'] and r['cons_rank'] and slot_n - 6 <= r['cons_rank'] <= slot_n + 10]
    above = sorted([r for r in in_range if (r.get('gap') or 0) >= 3], key=lambda r: -(r['gap'] or 0))
    from views import surname
    if above: parts.append(f"{surname(above[0]['name'])} is the one player in our range we grade above the league")
    value = sorted([r for r in rows if not r['taken'] and r['cons_rank'] and r['cons_rank'] > slot_n + 40 and (r.get('my_rank') or 999) <= slot_n + 40], key=lambda r: (r.get('my_rank') or 999))
    if value: parts.append(f"{surname(value[0]['name'])} is the value: the consensus has him in the {['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh'][min(6, (value[0]['cons_rank'] - 1) // 32)]} round and our read is a {['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh'][min(6, ((value[0].get('my_rank') or 1) - 1) // 32)]}-round player")
    if above and value: parts.append(f"If {surname(above[0]['name'])} is gone at {slot_n}, trading back and taking {surname(value[0]['name'])} is the play")
    if not parts: parts.append('The board is the class as your scouts see it; name your visits and it sharpens in the Spring')
    from views import sentence
    return sentence('. '.join(parts) + '.')


def act_board(session, league, abbr, order=None, dnd=None, add=None, remove=None, reset=False):
    """Save the GM's board: a whole order, a Do Not Draft list, one man added or removed, or reset to the scouts' read."""
    ub = dict(getattr(league, 'user_board', None) or {}); ub.setdefault('order', []); ub.setdefault('dnd', [])
    if reset: ub = dict(order=[], dnd=[])
    if order is not None: ub['order'] = [str(x) for x in order]
    if dnd is not None: ub['dnd'] = [str(x) for x in dnd]
    if add: ub['order'] = [x for x in ub['order'] if x != add] + [add]; ub['dnd'] = [x for x in ub['dnd'] if x != add]
    if remove: ub['order'] = [x for x in ub['order'] if x != remove]; ub['dnd'] = [x for x in ub['dnd'] if x != remove]
    league.user_board = ub
    return dict(ok=True, line=('Board reset to your scouts\' read.' if reset else 'Board saved.'), n=len(ub['order']))


def act_board_autofill(session, league, abbr):
    """Auto-Fill by Read: the top of your scouts' read becomes your order."""
    rows = board(session, league, abbr)['rows']
    top = [r['pid'] for r in rows if not r['taken']][:75]
    league.user_board = dict(order=top, dnd=list((getattr(league, 'user_board', None) or {}).get('dnd') or []))
    return dict(ok=True, line=f"{len(top)} players on your board, in your scouts' order.")


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
    # who is on the clock and the next few, with each club's needs
    clock = [dict(sel=q.selection, slot=SLOT(q), team=club(q.owner), mine=(q.owner == abbr), id=f"{q.year}-{q.round}-{q.original}", needs=sorted(_needs(league, league.teams[q.owner]))[:3]) for q in D.picks[D.i:D.i + 8]]
    # the board as the GM ordered it, the unplaced men after in the scouts' order; Do Not Draft kept out
    ub = getattr(league, 'user_board', None) or {}; order = [x for x in (ub.get('order') or [])]; dnd = set(ub.get('dnd') or [])
    byid = {x['pid']: x for x in avail}
    my_board = [byid[pid] for pid in order if pid in byid and pid not in dnd] + [x for x in sorted(avail, key=lambda x: x['my_rank']) if x['pid'] not in order and x['pid'] not in dnd]
    my_board = my_board[:40]
    for i, x in enumerate(my_board): x['board_no'] = i + 1
    # the assistants on the clock: what the club picking now needs and who they take, whether your man reaches you
    from views import surname, sentence
    read = ''
    if pk is not None and my_board:
        cur_team = league.teams[pk.owner]; cur_needs = sorted(_needs(league, cur_team))
        top = my_board[0]
        if not D.on_user():
            fit = next((x for x in my_board if any(x['pos'] in NEED_GROUPS[g] for g in cur_needs)), None)
            parts = []
            if fit and fit['pid'] != top['pid']: parts.append(f"{club(pk.owner)['name']} needs {' and '.join(cur_needs[:2]).lower()} and {surname(fit['name'])} is the best one left, so expect him to go at {pk.selection}. {surname(top['name'])} should reach you")
            elif fit and fit['pid'] == top['pid']: parts.append(f"{club(pk.owner)['name']} needs {' and '.join(cur_needs[:2]).lower()} and {surname(top['name'])} is the best one left; he may not reach you")
            else: parts.append(f"{surname(top['name'])} should reach you")
            picks_away = sum(1 for q in D.picks[D.i:] if q.owner != abbr and (D.picks[D.i:].index(q) < next((j for j, z in enumerate(D.picks[D.i:]) if z.owner == abbr), 0)))
            if picks_away >= 2 and len(my_board) > 1: parts.append(f"If he goes, {surname(my_board[1]['name'])} is next on your board")
            read = sentence('. '.join(parts) + '.')
        else:
            read = sentence(f"{surname(top['name'])} is your board's top man and a {top['pos']}" + (f", which is a need" if any(top['pos'] in NEED_GROUPS[g] for g in _needs(league, league.teams[abbr])) else '') + f". The consensus has him {top['cons_rank']}{_ordd(top['cons_rank'])}." if top.get('cons_rank') else f"{surname(top['name'])} is your board's top man.")
    picks_away = next((j for j, z in enumerate(D.picks[D.i:]) if z.owner == abbr), None)
    return dict(rail=r, live=True, on_user=D.on_user(), current=(dict(sel=pk.selection, slot=SLOT(pk), round=pk.round, team=club(pk.owner), original=pk.original, needs=sorted(_needs(league, league.teams[pk.owner]))[:3]) if pk else None),
                clock=clock, results=results, mine_next=mine_next, best=best, board=my_board, picks_left=len(D.picks) - D.i, total=len(D.picks), trades=len(D.trades), picks_away=picks_away, read=read,
                default_pick=(dict(pid=my_board[0]['pid'], name=my_board[0]['name'], pos=my_board[0]['pos'], college=my_board[0]['college']) if my_board else None), my_needs=sorted(_needs(league, league.teams[abbr])))


def _ordd(n):
    return 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


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


def act_sim_pick_one(session, league, abbr):
    """Next Pick: one club picks."""
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    if D.on_user(): return dict(ok=False, why='you are on the clock')
    ev = D.sim_pick()
    if D.done: session._draft_over(); return dict(ok=True, line='The draft is over.', done=True)
    return dict(ok=True, line=(f"{ev[1]} take {ev[2].name}." if isinstance(ev, tuple) and len(ev) >= 3 and hasattr(ev[2], 'name') else 'Pick made.') + (' You are on the clock.' if D.on_user() else ''))


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


def act_sim_draft(session, league, abbr):
    return act_finish_auto(session, league, abbr)


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
        import views_personnel as VP
        prov = (getattr(league, 'pick_provenance', None) or {}).get(f"{pk.year}-{pk.round}-{pk.original}")
        proj = VP._proj_slot(league, pk)
        if pk.original == abbr and pk.year == league.year and not pk.selection: note = f"Projected From a {t.record[0]}–{t.record[1]} Season" if sum(t.record) else 'Own'
        elif pk.original == abbr: note = 'Own' if not proj or pk.selection else f"Projected {max(1, proj - 2)}{_ordd(max(1, proj - 2))}–{min(32, proj + 2)}{_ordd(min(32, proj + 2))}"
        else: note = f"From {club(pk.original)['name']}" + (f" · {prov['how']} · {prov.get('phase', '').replace('_', ' ').title() if not prov.get('week') else 'Week ' + str(prov['week'])} {prov['year']}" if prov else '')
        years.setdefault(pk.year, []).append(dict(round=pk.round, slot=(SLOT(pk) if pk.selection else (f"{pk.round}.{proj}" if proj and pk.year == league.year else f"{pk.round}{_ordd(pk.round)}")), original=pk.original, own=(pk.original == abbr), via=(None if pk.original == abbr else club(pk.original)), note=note))
    # picks of ours held by others
    gone = []
    for other, ot in league.teams.items():
        if other == abbr: continue
        for pk in ot.picks:
            if pk.original == abbr and not pk.used_on:
                prov = (getattr(league, 'pick_provenance', None) or {}).get(f"{pk.year}-{pk.round}-{pk.original}")
                gone.append(dict(year=pk.year, round=pk.round, slot=SLOT(pk), holder=club(other), note=f"To {club(other)['name']}" + (f" · {prov['how']}" if prov else '')))
    gone.sort(key=lambda g: (g['year'], g['round']))
    ld = getattr(league, 'last_draft', None)
    # draft results across years: every drafted man on record with where he was taken, what he was and is, and his role now
    results = []
    for x in league.transactions:
        if x.get('kind') != 'draft': continue
        p = league.player(x.get('pid'))
        if p is None: continue
        tm = league.teams.get(p.team) if p.team else None
        role = 'Retired' if p.retired else ('Free Agent' if tm is None else _role_word(tm, p))
        results.append(dict(pid=p.pid, name=p.name, pos=p.pos, college=getattr(p, 'college', None) or '', year=x.get('year'), pick=f"{x.get('round')}.{((x.get('selection') or 1) - 1) % 32 + 1}", sel=x.get('selection'), team=club(x.get('team')) if x.get('team') in league.teams else None,
                            division=(league.teams[x['team']].division if x.get('team') in league.teams else None), ovr=round(p.ovr), drafted_at=(round(float(x['ovr_then'])) if x.get('ovr_then') is not None else None), cons_was=x.get('consensus_rank'), status=role, now=(club(p.team) if p.team in league.teams else None)))
    results.sort(key=lambda r: (-(r['year'] or 0), r['sel'] or 999))
    return dict(rail=rail(session, league, abbr), years=[dict(year=y, picks=v) for y, v in sorted(years.items())], gone=gone, last=(_results(league, ld) if ld else None), results=results[:400], result_years=sorted({r['year'] for r in results}, reverse=True), my_division=t.division)


def _role_word(t, p):
    d = t.depth.get(p.pos, []); idx = next((i for i, q in enumerate(d) if q.pid == p.pid), None)
    n_start = {'QB': 1, 'HB': 1, 'WR': 3, 'TE': 1, 'LEDG': 1, 'REDG': 1, 'DT': 2, 'MIKE': 1, 'WILL': 1, 'SAM': 1, 'CB': 3, 'FS': 1, 'SS': 1}.get(p.pos, 1)
    if idx is None: return 'Practice Squad' if any(q.pid == p.pid for q in getattr(t, 'practice_squad', []) or []) else 'Reserve'
    return 'Starter' if idx < n_start else 'Rotation' if idx < n_start + 1 else 'Depth'

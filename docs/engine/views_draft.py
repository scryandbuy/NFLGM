from player_background import home_state
"""
DRAFT VIEWS. The Scouting Board, Draft Day, and Picks pages, and what their
buttons do. Prospects are seen through YOUR scouts' eyes; the true rating is
never shown.
"""
from views import club, rail

SLOT = lambda pk: f"{pk.round}.{((pk.selection - 1) % 32) + 1}" if pk.selection else f"R{pk.round}"



def coming_season(league):
    """The season whose draft is next. Picks carry the season year (the draft held after the 2026 season is the
    2027 draft). Read off the calendar the season review uses (league.season_closed_year), not a week heuristic:
    before the New Year step the league year is the season just played, so the coming draft is that year's; after
    the roll the league is a year on but the draft still belongs to the season just played, until it is held; once
    held, or in season, the next draft is this year's."""
    year = int(league.year)
    closed = getattr(league, 'season_closed_year', None)
    if closed is not None and int(closed) == year:
        return year                                                    # pre-roll offseason
    if league.phase in ('offseason', 'free_agency'):
        ld = getattr(league, 'last_draft', None)
        held = ld is not None and int(ld.get('year', -1)) == year - 1
        return year if held else year - 1                             # post-roll, up to and through the draft
    return year


def spring_year(league):
    """The league year this offseason's spring is (or will be) tagged with. The spring runs after the New Year
    roll, so through a post-roll offseason it is league.year, before and after the draft alike; before the roll,
    and in season, the next spring is a year away."""
    year = int(league.year)
    closed = getattr(league, 'season_closed_year', None)
    pre_roll = closed is not None and int(closed) == year
    if pre_roll or league.phase not in ('offseason', 'free_agency'):
        return year + 1
    return year


def _held_this_offseason(league):
    """Whether the draft on record is this offseason's: held after the New Year roll and before the season opens."""
    ld = getattr(league, 'last_draft', None)
    closed = getattr(league, 'season_closed_year', None); pre_roll = closed is not None and int(closed) == int(league.year)
    return ld is not None and int(ld.get('year', -1)) == int(league.year) - 1 and league.phase in ('offseason', 'free_agency') and not pre_roll


def draft_year_of(y):
    from views import draft_year
    return draft_year(y)


def _spring_done(league):
    import spring as SP
    return SP.completed(league, spring_year(league))


def _pool(league):
    return list(getattr(league, 'draft_pool', None) or []) or list(getattr(league, 'next_class', None) or [])


def _prospect(league, abbr, p, taken=()):
    v = (getattr(league, 'scouting', None) or {}).get(abbr, {}).get(p.pid)
    c = (getattr(league, 'consensus', None) or {}).get(p.pid)
    if v is None: return None
    mine = round(float(v['ovr']))
    cons = round(float(c['ovr'])) if c else None
    gap = (mine - cons) if cons is not None else None
    import scouting as _SC
    fit = _SC.scheme_fit_view(league, abbr, p, v)                 # in your scheme, on your scouts' read
    scheme_ovr = round(float(v['ovr']) + fit)
    comb = getattr(p, 'combine', None) or {}
    flags = list(v.get('flags') or [])
    import scouting as SC
    # the words the board shows for what the room knows
    words = []
    if 'visited' in flags or p.pid in (getattr(league, 'user_visits', None) or []): words.append('Visited')
    pre = v.get('pre_visit') if isinstance(v, dict) else None
    visit_move = None
    if pre and 'visited' in flags:
        visit_move = dict(mine_from=round(float(pre.get('ovr', 0) or 0)), ceiling_from=f"{round(float(pre.get('lo', 0) or 0))}–{round(float(pre.get('hi', 0) or 0))}", rank_from=pre.get('rank'))
    if p.xp_spent.get('_senior_bowl') in (league.year, league.year - 1): words.append('Senior Bowl')
    _when = getattr(league, 'user_visit_week', None) or {}
    visit_locked = bool(p.pid in (getattr(league, 'user_visits', None) or []) and _when.get(p.pid) != f"{league.year}-{league.week}-{league.phase}")
    if getattr(p, 'age', 22) >= 22 and any(x.get('pid') == p.pid and x.get('event') == 'Senior Bowl' for x in (getattr(league, 'spring_news', None) or [])): words.append('Sr. Bowl')
    import character_assessment as CA
    words.extend(CA.flags(v))
    if 'medical' in flags: words.append('Medical')
    if not SC._power(p): words.append('Small School')
    if getattr(p, 'age', 22) < 21.5: words.append('Underclassman')
    mv = next((x for x in reversed(getattr(league, 'spring_news', None) or []) if x.get('pid') == p.pid and x.get('kind') == 'stock'), None)
    if mv and (mv.get('to') or 0) - (mv.get('frm') or 0) >= 10: words.append('Faller')
    elif mv and (mv.get('frm') or 0) - (mv.get('to') or 0) >= 10: words.append('Riser')
    cls_year = ('Senior' if p.age >= 22.5 else 'Junior' if p.age >= 21.5 else 'Sophomore')
    h = getattr(p, 'height', None); size = (f"{int(h) // 12}'{int(h) % 12}\" {int(getattr(p, 'weight', 0) or 0)}".strip() if h else '')
    rk = c.get('rank') if c else None
    proj_range = (f"{max(1, rk - 4)}–{rk + 4}" if rk and rk <= 224 else '—')
    return dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), home_state=home_state(p), small=(not SC._power(p)), visited=('visited' in flags or p.pid in (getattr(league, 'user_visits', None) or [])),
                cls_year=cls_year, size=size, words=words, character_report=CA.report(v), proj_range=proj_range, visit_move=visit_move, my_round=None, visit_locked=visit_locked, fit=fit, scheme_ovr=scheme_ovr,
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
    spring_done = _spring_done(league)
    slot = None
    try:
        import postseason as PS
        slot = PS.provisional_slot(league, getattr(session, 'post_live', None) or getattr(session, 'post', None), abbr)
    except Exception: slot = None
    D_ = getattr(session, 'draft', None)
    on_clock = bool(D_ is not None and not D_.done and D_.on_user())
    return dict(rail=rail(session, league, abbr), rows=rows, count=len(rows), year=coming_season(league) + 1, slot=slot, on_clock=on_clock,
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
        # a need for the draft: too few bodies, a starter below the line, or a starter past thirty with his deal
        # up (a young starter with a year left is an extension question, not a hole)
        if len(men) < n_start + 1 or (starters and min(p.ovr for p in starters) < 72) or any(p.contract and p.contract.years <= 1 and p.age >= 31 for p in starters): out.add(g)
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
    return dict(order=[dict(pid=r['pid'], tier=tier(r)) for r in placed], dnd=[dict(pid=pid, why=(', '.join(w for w in byid[pid]['words'] if w in ('Medical', 'Work ethic concern', 'Discipline concern')) or 'your call')) for pid in dnd], saved=bool(ub.get('order')))


def _board_read(league, abbr, rows, ub, needs):
    """The assistants on the board: the need, the one player in range graded above the league, the value, and the fallback."""
    t = league.teams[abbr]
    parts = []
    exp = [p for p in t.active() if p.contract and p.contract.years <= 1 and p.ovr >= 74]
    if needs:
        from views import surname
        g = sorted(needs)[0]; players = [surname(p.name) for p in exp if p.pos in NEED_GROUPS[g]][:2]
        parts.append(f"{g} is the need" + (f" with {' and '.join(players)} expiring" if players else ''))
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


def prospect_card(session, league, abbr, pid):
    """A prospect's card: what your scouts see. Attributes carry the room's error (physical
    and skill groups shifted by the read's error terms), never the true rating."""
    import views_club as VC, scouting as SC
    p = next((q for q in _pool(league) if q.pid == pid), None) or league.player(pid)
    if p is None: return dict(error='no such prospect')
    row = _prospect(league, abbr, p, (getattr(session, 'draft', None).taken if getattr(session, 'draft', None) else ()))
    taken_now = bool(getattr(session, 'draft', None) is not None and p.pid in getattr(session.draft, 'taken', set())) or bool(p.team)
    if row is None: return dict(error='your scouts have no read on him')
    view = league.scouting[abbr][p.pid]
    e_phys = float(view.get('e_phys', 0.0)); e_skill = float(view.get('e_skill', 0.0))
    # the whole rating set as your scouts see it, for the scheme rows
    import xp as XP_
    seen_ratings = {k: float(max(20.0, min(99.0, float(v_) + (e_phys if (k in XP_.PHYSICAL or k in XP_.TOOLS) else e_skill)))) for k, v_ in p.ratings.items()}
    fam = VC.FAM.get(p.pos, 'DB')
    def col(keys, err):
        rows = []
        for k, label in keys:
            true = p.ratings.get(k)
            if true is None: continue
            seen = int(round(max(20, min(99, float(true) + err))))
            rows.append(dict(key=k, label=label, v=seen, tier=('hi' if seen >= 85 else 'md' if seen >= 72 else 'lo')))   # 'md', not 'mid': .mid is the game-day midfield layout and centred the row
        return rows
    phys = dict(title='Physical', rows=col(VC.ATTR['phys'], e_phys), extra=None)
    if fam == 'DB': skill = dict(title='Coverage', rows=col(VC.ATTR['coverage'], e_skill), extra=dict(title='Run Defense', rows=col(VC.ATTR['rundef'], e_skill)))
    elif fam in ('LB', 'DL'): skill = dict(title=VC.SKILL_TITLE.get(fam, 'Skill'), rows=col([k for k in VC.ATTR[fam] if k[0] not in ('tackle_rating', 'hit_power_rating', 'pursuit_rating', 'block_shed_rating')], e_skill), extra=dict(title='Run Defense', rows=col(VC.ATTR['rundef'], e_skill)))
    else: skill = dict(title=VC.SKILL_TITLE.get(fam, 'Skill'), rows=col(VC.ATTR.get(fam, VC.ATTR['DB']), e_skill), extra=None)
    mental = dict(title='Mental', rows=col(VC.ATTR['mental'], e_skill), extra=None)
    comb = getattr(p, 'combine', None) or {}
    combine = [dict(label=l, v=(f"{comb[k]:.2f}" if k in ('forty', 'shuttle') and comb.get(k) is not None else (f"{comb[k]:.1f}\"" if k == 'vertical' and comb.get(k) is not None else (str(comb[k]) if comb.get(k) is not None else '—')))) for k, l in (('forty', 'Forty'), ('vertical', 'Vertical'), ('bench', 'Bench'), ('shuttle', 'Shuttle'))]
    ub = getattr(league, 'user_board', None) or {}
    on_board = (ub.get('order') or []).index(p.pid) + 1 if p.pid in (ub.get('order') or []) else None
    reads = int(view.get('reads', 1) or 1)
    confidence = 'Visited' if ('visited' in (view.get('flags') or []) or p.pid in (getattr(league, 'user_visits', None) or [])) else 'Not visited'
    return dict(rail=rail(session, league, abbr), pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), cls_year=row['cls_year'], size=row['size'], fit=row.get('fit', 0.0), scheme_ovr=row.get('scheme_ovr'), home_state=row['home_state'],
                small=row['small'], mine=row['mine'], ceiling=row['ceiling'], cons=row['cons'], cons_rank=row['cons_rank'], gap=row['gap'], proj_range=row['proj_range'], my_rank=row.get('my_rank'), my_round=(f"R{min(7, (row['my_rank'] - 1) // 32 + 1)}" if row.get('my_rank') else None),
                words=row['words'], visited=row['visited'], taken=row['taken'], cols=[phys, skill, mental], combine=combine,
                medical=('Concern found at visit' if 'medical' in (view.get('flags') or []) else 'No concern found at visit' if 'visited' in (view.get('flags') or []) else 'Unknown until visit'),
                on_clock=bool(getattr(session, 'draft', None) is not None and not session.draft.done and session.draft.on_user() and not taken_now),
                schemes=VC.scheme_rows(seen_ratings, p.pos, VC._club_arch(league, abbr, p.pos)),
                reads=reads, confidence=confidence, on_board=on_board, dnd=(p.pid in (ub.get('dnd') or [])), personality='', character_report=row['character_report'], spring_done=_spring_done(league),
                read=_prospect_read(league, abbr, p, row, view))


def _prospect_read(league, abbr, p, row, view):
    """The scouts on one man: the grade against the room, where he goes, what the flags mean."""
    from views import sentence, surname
    parts = []
    gap = row.get('gap')
    if gap is not None and gap >= 3: parts.append(f"we have {surname(p.name)} {gap} points above the league; if the room is right he is a value wherever he goes")
    elif gap is not None and gap <= -3: parts.append(f"we have him {abs(gap)} points under the consensus; the league likes him more than we do")
    else: parts.append(f"our read is in line with the league on {surname(p.name)}")
    if row.get('cons_rank'): parts.append(f"the consensus puts him in the {['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh'][min(6, (row['cons_rank'] - 1) // 32)]} round")
    lo, hi = row['ceiling'].split('–') if '–' in row['ceiling'] else (None, None)
    if lo and hi and int(hi) - int(lo) >= 8: parts.append('the ceiling is wide, which is the room saying it does not know yet')
    if 'Medical' in row['words']: parts.append('the medical is a real concern and the later he goes the more it explains')
    for report in row.get('character_report', []):
        if report['status'] in ('concern', 'strength'):
            parts.append(f"{report['summary']} ({report['confidence'].lower()} confidence): {report['explanation'].rstrip('.')}")
    if 'Small School' in row['words']: parts.append('the small-school tape makes every number here softer')
    if not row['visited'] and not _spring_done(league): parts.append('a visit would tighten this read')
    return sentence('. '.join(parts) + '.')


def act_visit(session, league, abbr, pid):
    """Name a visit, or cancel one named this week. Once the week rolls a visit is locked in: the scouts have made the call."""
    import spring as SP
    if _spring_done(league):
        return dict(ok=False, why='Spring visits are complete; selections are locked.', locked=True,
                    visits=list(getattr(league, 'user_visits', None) or []))
    cur = list(getattr(league, 'user_visits', None) or [])
    when = league.__dict__.setdefault('user_visit_week', {})
    stamp = f"{league.year}-{league.week}-{league.phase}"
    if pid in cur:
        if when.get(pid) != stamp: return dict(ok=False, why='that visit is locked in; visits can only be cancelled the week they are named', visits=cur, locked=True)
        cur.remove(pid); when.pop(pid, None); SP.set_user_visits(league, cur); return dict(ok=True, line='Visit cancelled.', visits=cur)
    if len(cur) >= SP.VISITS: return dict(ok=False, why=f'all {SP.VISITS} visits are spoken for', visits=cur)
    cur.append(pid); when[pid] = stamp; SP.set_user_visits(league, cur); p = league.player(pid)
    return dict(ok=True, line=f"{p.name if p else pid} gets a visit ({len(cur)} of {SP.VISITS}). Locks in when the week rolls.", visits=cur)


def spring(session, league, abbr):
    """The Spring: stock moves by event, your visits with what the second look found, the flags."""
    news = [x for x in (getattr(league, 'spring_news', None) or []) if x.get('year') == spring_year(league)]
    pool = {p.pid: p for p in _pool(league)}
    moves = []
    for x in news:
        if x.get('kind') != 'stock': continue
        p = pool.get(x['pid']) or league.player(x['pid'])
        moves.append(dict(event=x.get('event'), pid=x['pid'], name=x.get('name'), pos=x.get('pos'), home_state=home_state(p) if p else x.get('home_state'), frm=x.get('frm'), to=x.get('to'), delta=(x.get('frm') or 0) - (x.get('to') or 0), why=x.get('why', '')))
    # flags your room uncovered at visits this spring, folded into the player's line
    uncovered = {}
    for x in news:
        if x.get('kind') == 'flag':
            label = {'character': 'work ethic', 'work_ethic': 'work ethic'}.get(x.get('flag'), x.get('flag'))
            if label and label not in uncovered.setdefault(x['pid'], []): uncovered[x['pid']].append(label)
    EVENT_WORDS = {'combine': 'the combine', 'Senior Bowl': 'the Senior Bowl', 'pro days': 'his pro day', 'visits': 'the visit'}
    for m in moves:
        ev = EVENT_WORDS.get(m['event'], m['event']); fl = uncovered.get(m['pid'], [])
        head = (f"Uncovered a {' and a '.join(fl)} flag at the visit; " if fl and m['event'] == 'visits' else '')
        m['line'] = head + (f"rank went from {m['frm']} to {m['to']} after {ev}." if not head else f"rank went from {m['frm']} to {m['to']}.")
        m['line'] = m['line'][0].upper() + m['line'][1:]
    # a flag uncovered with no rank move of its own gets a line too
    moved = {m['pid'] for m in moves if m['event'] == 'visits'}
    flag_lines = []
    for pid, fl in uncovered.items():
        if pid in moved: continue
        p = pool.get(pid) or league.player(pid)
        if p is None: continue
        flag_lines.append(dict(event='visits', pid=pid, name=p.name, pos=p.pos, home_state=home_state(p), frm=None, to=None, delta=0, kind='flag', line=f"Uncovered a {' and a '.join(fl)} flag at the visit."))
    risers = sorted([m for m in moves if m['delta'] > 0], key=lambda m: -m['delta'])[:12]
    fallers = sorted([m for m in moves if m['delta'] < 0], key=lambda m: m['delta'])[:12]
    events = []
    for ev in ('Senior Bowl', 'combine', 'pro days', 'visits'):
        ms = [m for m in moves if m['event'] == ev]
        events.append(dict(event=ev.title() if ev != 'Senior Bowl' else ev, n=len(ms), up=sum(1 for m in ms if m['delta'] > 0), down=sum(1 for m in ms if m['delta'] < 0)))
    visited = []
    for pid in (getattr(league, 'user_visits', None) or []):
        p = pool.get(pid) or league.player(pid)
        if p is None: continue
        r = _prospect(league, abbr, p)
        if r: visited.append(r)
    flagged = flag_lines
    # the visits table: what the second look changed, before and after
    for r in visited:
        v = (getattr(league, 'scouting', {}) or {}).get(abbr, {}).get(r['pid']) or {}
        pre = v.get('pre_visit')
        if pre:
            r['before'] = dict(mine=round(float(pre.get('ovr', 0) or 0)), ceiling=f"{round(float(pre.get('lo', 0) or 0))}–{round(float(pre.get('hi', 0) or 0))}", cons_rank=pre.get('rank'))
            r['uncovered'] = [f for f in v.get('flags', []) if f in ('medical', 'character') and f not in (pre.get('flags') or [])]
            import character_assessment as CA
            r['uncovered'] += [f for f in CA.flags(v) if f not in (pre.get('character_flags') or [])]
    done = bool(news)
    return dict(rail=rail(session, league, abbr), done=done, events=events, risers=risers, fallers=fallers, visited=visited, flagged=flagged[:40],
                note=None if _spring_done(league) else 'The Senior Bowl takes place after the conference championships, before the Championship Game. The combine, pro days and the thirty visits follow in the Spring step of the offseason. Name your visits on the board before Spring.')


def act_sim_round(session, league, abbr):
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    if D.on_user(): return dict(ok=False, why='you are on the clock; make your pick first')
    evs = D.sim_round()
    if D.done: session._draft_over(); return dict(ok=True, line='The draft is over.', done=True)
    return dict(ok=True, line=(f"{len(evs)} picks made; you are on the clock." if D.on_user() else f"{len(evs)} picks made."))


def act_trade_up(session, league, abbr, target, sends):
    """Buy a pick ahead of yours: the target pick (id) for the picks you send (ids), priced by its owner."""
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    pk = None
    for q in D.picks[D.i:]:
        if f"{q.year}-{q.round}-{q.original}" == target: pk = q; break
    if pk is None or pk.owner == abbr: return dict(ok=False, why='that pick is not on the board')
    seller = pk.owner
    r = session.personnel_act('propose', other=seller, a_sends=list(sends), b_sends=[target])
    if r.get('done'):
        return dict(ok=True, done=False, line=f"Traded up to {SLOT(pk)} with {seller}." + (' You are on the clock.' if D.on_user() else ''))
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
        # the results shown are this offseason's draft, once it is held; in season and before the roll the page names
        # the coming draft instead of replaying last year's
        ld = getattr(league, 'last_draft', None)
        held = _held_this_offseason(league)
        year_next = draft_year_of(coming_season(league))
        return dict(rail=r, live=False, last=(_results(league, ld) if (ld and held) else None), year_next=year_next,
                    note=(f'The {year_next} draft comes in the offseason after the Spring; you will be on the clock here.' if not held else 'The draft is over. The results are below.'))
    pk = D.current()
    results = [dict(sel=s, slot=f"{(s - 1) // 32 + 1}.{(s - 1) % 32 + 1}", team=club(t), name=p.name, pos=p.pos, cons_rank=(league.consensus.get(p.pid) or {}).get('rank')) for s, t, p in D.results[-12:]][::-1]
    mine_next = [dict(sel=q.selection, slot=SLOT(q), round=q.round) for q in D.picks[D.i:] if q.owner == abbr][:4]
    avail = [r for r in (_prospect(league, abbr, p, D.taken) for p in D.available()) if r]
    avail.sort(key=lambda x: (x['cons_rank'] if x['cons_rank'] is not None else 999))
    best = avail[:40]
    _my_rank(avail); my_board = sorted(avail, key=lambda x: x['my_rank'])[:40]
    # who is on the clock and the next few, with each club's needs
    clock = [dict(sel=q.selection, slot=SLOT(q), team=club(q.owner), mine=(q.owner == abbr), id=f"{q.year}-{q.round}-{q.original}", needs=sorted(_needs(league, league.teams[q.owner]))[:3]) for q in D.picks[D.i:D.i + 8]]
    # THE PICK BOARD: every slot of the draft, eight to a row, four rows a round. A made pick carries the player;
    # one still to come carries the club and the number. Each is a door to a trade for that pick.
    made = {s: (t, p) for s, t, p in D.results}
    squares = {}
    for s, (t_, p) in made.items():
        squares[s] = dict(sel=s, slot=f"{(s - 1) // 32 + 1}.{(s - 1) % 32 + 1:02d}", round=(s - 1) // 32 + 1, team=club(t_), mine=(t_ == abbr), id=None, now=False, done=True, name=p.name, pos=p.pos, original=None)
    cur_sel = D.current().selection if D.current() is not None else None
    for q in D.picks:
        s = q.selection
        if s in squares: continue
        squares[s] = dict(sel=s, slot=SLOT(q), round=q.round, team=club(q.owner), mine=(q.owner == abbr), id=f"{q.year}-{q.round}-{q.original}", now=(s == cur_sel),
                          done=False, name=None, pos=None, original=(q.original if q.original != q.owner else None))
    pick_board = [squares[s] for s in sorted(squares)]
    # the board as the GM ordered it, the unplaced players after in the scouts' order; Do Not Draft kept out
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
            read = sentence(f"{surname(top['name'])} is your board's top player and a {top['pos']}" + (f", which is a need" if any(top['pos'] in NEED_GROUPS[g] for g in _needs(league, league.teams[abbr])) else '') + f". The consensus has him {top['cons_rank']}{_ordd(top['cons_rank'])}." if top.get('cons_rank') else f"{surname(top['name'])} is your board's top man.")
    picks_away = next((j for j, z in enumerate(D.picks[D.i:]) if z.owner == abbr), None)
    return dict(rail=r, live=True, on_user=D.on_user(), current=(dict(sel=pk.selection, slot=SLOT(pk), round=pk.round, team=club(pk.owner), original=pk.original, needs=sorted(_needs(league, league.teams[pk.owner]))[:3]) if pk else None),
                clock=clock, order=pick_board, results=results, mine_next=mine_next, best=best, board=my_board, has_custom_board=bool(order or dnd), picks_left=len(D.picks) - D.i, total=len(D.picks), trades=len(D.trades), picks_away=picks_away, read=read,
                default_pick=(dict(pid=my_board[0]['pid'], name=my_board[0]['name'], pos=my_board[0]['pos'], home_state=my_board[0]['home_state']) if my_board else None), my_needs=sorted(_needs(league, league.teams[abbr])))


def _ordd(n):
    return 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def _results(league, ld):
    out = []
    for s, t, pid in ld['results']:
        p = league.player(pid)
        snap = (ld.get('scouting') or {}).get(pid) or {}
        rank = snap.get('cons_rank') or ((getattr(league, 'consensus', None) or {}).get(pid) or {}).get('rank')
        out.append(dict(sel=s, slot=f"{(s - 1) // 32 + 1}.{(s - 1) % 32 + 1}", team=club(t), pid=pid,
                        name=(p.name if p else pid), pos=(p.pos if p else ''), cons_rank=rank,
                        mine=(t == getattr(league, 'user_team', None))))
    return dict(year=__import__('views').draft_year(ld['year']), rows=out, trades=ld.get('trades', 0))


def act_pick(session, league, abbr, pid):
    D = session.draft
    if D is None or not D.on_user(): return dict(ok=False, why='not your pick')
    try: ev = D.make_pick(pid)
    except ValueError as e: return dict(ok=False, why=str(e))
    session._draft_offers = []
    p = ev[3]; line = f"You take {p.name}, {p.pos}, at {ev[1]}."
    if D.done: session._draft_over(); return dict(ok=True, line=line + ' The draft is over.', done=True)
    return dict(ok=True, line=line, done=False)


def act_sim_pick_one(session, league, abbr):
    """Next Pick: one selection, using the user's board when they own the pick."""
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    if D.done: return dict(ok=False, why='The draft is already over.', done=True)
    if D.on_user(): return act_auto_pick(session, league, abbr)
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
    """Take the top eligible player on your board at this pick only."""
    D = session.draft
    if D is None or not D.on_user(): return dict(ok=False, why='not your pick')
    p = D.user_pick()
    return act_pick(session, league, abbr, p.pid) if p else dict(ok=False, why='Every available prospect is on Do Not Draft')


def act_sim_draft(session, league, abbr):
    return act_finish_auto(session, league, abbr)


def act_finish_auto(session, league, abbr):
    D = session.draft
    if D is None: return dict(ok=False, why='no draft on')
    D.auto = True; D.sim_all()
    if not D.done:
        D.auto = False
        return dict(ok=False, why='Every available prospect is on Do Not Draft; choose a player to continue')
    session._draft_over()
    return dict(ok=True, line='The rest of the draft ran on auto.', done=True)


def act_offers(session, league, abbr):
    D = session.draft
    if D is None or not D.on_user(): return dict(ok=False, why='offers come when you are on the clock')
    pk = D.current(); offers = D.gather_offers(pk)
    out = [dict(i=i, team=club(o['team']), summary=o['summary']) for i, o in enumerate(offers)]
    session._draft_offers = offers
    return dict(ok=True, offers=out, line=(f"{len(out)} clubs want to come up." if out else 'Nobody is calling for this pick.'))


def act_accept_offer(session, league, abbr, i):
    D = session.draft; offers = getattr(session, '_draft_offers', None) or []
    if D is None or not D.on_user() or not 0 <= int(i) < len(offers): return dict(ok=False, why='that offer is gone')
    o = offers[int(i)]
    if o['asks'][0] is not D.current() or o['asks'][0].used_on:
        session._draft_offers = []
        return dict(ok=False, why='that offer was for an earlier pick')
    ev = D.accept_offer(o)
    if ev is None: return dict(ok=False, why='The offer is no longer available on these terms')
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
        if pk.original == abbr and pk.year == coming_season(league) and not pk.selection: note = f"Projected From a {t.record[0]}–{t.record[1]} Season" if sum(t.record) else ''
        elif pk.original == abbr: note = '' if not proj or pk.selection else f"Projected {max(1, proj - 2)}{_ordd(max(1, proj - 2))}–{min(32, proj + 2)}{_ordd(min(32, proj + 2))}"
        else: note = ''
        years.setdefault(pk.year, []).append(dict(round=pk.round, slot=(SLOT(pk) if pk.selection else (f"{pk.round}.{proj}" if proj and pk.year == coming_season(league) else f"{pk.round}{_ordd(pk.round)}")), original=pk.original, own=(pk.original == abbr), via=(None if pk.original == abbr else club(pk.original)), frm=(None if pk.original == abbr else pk.original), note=note))
    ld = getattr(league, 'last_draft', None)
    # draft results across years: every drafted man on record with where he was taken, what he was and is, and his role now
    results = []
    for x in league.transactions:
        if x.get('kind') != 'draft': continue
        p = league.player(x.get('pid'))
        if p is None: continue
        tm = league.teams.get(p.team) if p.team else None
        role = 'Retired' if p.retired else ('Free Agent' if tm is None else _role_word(tm, p))
        results.append(dict(pid=p.pid, name=p.name, pos=p.pos, home_state=home_state(p), year=x.get('year'), pick=f"{x.get('round')}.{((x.get('selection') or 1) - 1) % 32 + 1}", sel=x.get('selection'), team=club(x.get('team')) if x.get('team') in league.teams else None,
                            dev=getattr(p, 'dev', 'normal'), ovr=round(p.ovr), drafted_at=(round(float(x['ovr_then'])) if x.get('ovr_then') is not None else None), cons_was=x.get('consensus_rank'), status=role, now=(club(p.team) if p.team in league.teams else None)))
    results.sort(key=lambda r: (-(r['year'] or 0), r['sel'] or 999))
    from views import draft_year
    # WHICH DRAFT THE RESULTS TAB OPENS ON. The draft held this offseason, if it has been; otherwise the coming
    # draft, which has no results yet and says so, with the past drafts on the year chips. Without this the tab
    # opened on last year's draft all through the new season as if it were this year's.
    held_this_offseason = _held_this_offseason(league)
    default_year = draft_year_of(ld['year']) if held_this_offseason else draft_year_of(coming_season(league))
    return dict(rail=rail(session, league, abbr), years=[dict(year=draft_year(y), this_draft=(y == coming_season(league)), picks=v) for y, v in sorted(years.items())], last=(_results(league, ld) if (ld and held_this_offseason) else None), results=results[:400], result_years=sorted({r['year'] for r in results}, reverse=True), my_division=t.division,
                default_year=default_year, default_held=held_this_offseason)


def _role_word(t, p):
    d = t.depth.get(p.pos, []); idx = next((i for i, q in enumerate(d) if q.pid == p.pid), None)
    n_start = {'QB': 1, 'HB': 1, 'WR': 3, 'TE': 1, 'LEDG': 1, 'REDG': 1, 'DT': 2, 'MIKE': 1, 'WILL': 1, 'SAM': 1, 'CB': 3, 'FS': 1, 'SS': 1}.get(p.pos, 1)
    if idx is None: return 'Practice Squad' if any(q.pid == p.pid for q in getattr(t, 'practice_squad', []) or []) else 'Reserve'
    return 'Starter' if idx < n_start else 'Rotation' if idx < n_start + 1 else 'Depth'


def draft_text(session, league, abbr):
    """The whole draft as plain text, every pick with the club, the player, his position, school, the consensus rank
    and the user's read, and the trades, so the draft can be pasted for a look."""
    ld = getattr(league, 'last_draft', None)
    D = getattr(session, 'draft', None)
    rows = []
    if D is not None and not D.done:
        results = [(s, t, p.pid) for s, t, p in D.results]; trades = list(D.trades); year = D.year
    elif ld:
        results = [tuple(x) for x in ld.get('results', [])]; trades = ld.get('trade_log', []) or []; year = ld['year']
    else:
        return dict(ok=False, text='', why='no draft has been run yet')
    cons = getattr(league, 'consensus', None) or {}
    snapshot = (ld or {}).get('scouting') or {} if D is None or D.done else {}
    from views import draft_year
    lines = [f"{draft_year(year)} Draft"]
    for s, t, pid in results:
        p = league.player(pid)
        c = cons.get(pid, {}) or {}
        old = snapshot.get(pid) or {}
        v = ((getattr(league, 'scouting', None) or {}).get(abbr) or {}).get(pid) or {}
        read = old.get('user_ovr') if old else v.get('ovr')
        mine = f"{round(float(read))}" if read is not None else '—'
        cr = old.get('cons_rank') if old else c.get('rank')
        co = old.get('cons_ovr') if old else c.get('ovr')
        lines.append(f"{(s - 1) // 32 + 1}.{(s - 1) % 32 + 1:02d} ({s:3d}) {t:3s} {p.name if p else pid} · {p.pos if p else '?'} · {home_state(p) if p else ''} · consensus #{cr if cr is not None else '—'} ({round(float(co)) if co is not None else '—'}) · your read {mine} · age {int(p.age) if p else '—'}" + (f" · {p.ovr:.0f} ovr now" if p and p.team else ''))
    if trades:
        lines.append(''); lines.append('Trades on the clock')
        for tr in trades:
            try: sel, buyer, seller, desc = tr[0], tr[1], tr[2], tr[3]
            except Exception: continue
            lines.append(f"pick {sel}: {buyer} from {seller} for {', '.join(str(x) for x in desc)}")
    return dict(ok=True, text='\n'.join(lines))


def draft_csv(session, league, abbr):
    """The whole draft as a CSV file: every pick with the club, the player, his position, school, age, the consensus
    rank and grade, your scouts' read, his overall now, and every one of his attributes as the engine holds them."""
    ld = getattr(league, 'last_draft', None)
    D = getattr(session, 'draft', None)
    if D is not None and not D.done:
        results = [(s, t, p.pid) for s, t, p in D.results]; year = D.year
    elif ld:
        results = [tuple(x) for x in ld.get('results', [])]; year = ld['year']
    else:
        return dict(ok=False, why='no draft has been run yet')
    cons = getattr(league, 'consensus', None) or {}
    snapshot = (ld or {}).get('scouting') or {} if D is None or D.done else {}
    from views import draft_year
    attrs = sorted({k for _s, _t, pid in results for k in ((league.player(pid).ratings if league.player(pid) else {}) or {}) if k.endswith('_rating')})
    labels = {}
    import views_club as VC
    for grp in VC.ATTR.values():
        for k, lab in grp: labels[k] = lab
    head = ['pick', 'round', 'slot', 'team', 'player', 'pos', 'age', 'home_state', 'consensus_rank', 'consensus_grade', 'your_read', 'overall_now', 'dev'] + [labels.get(k, k.replace('_rating', '')) for k in attrs]
    rows = [head]
    for s, t, pid in results:
        p = league.player(pid)
        c = cons.get(pid, {}) or {}
        old = snapshot.get(pid) or {}
        v = ((getattr(league, 'scouting', None) or {}).get(abbr) or {}).get(pid) or {}
        cr = old.get('cons_rank') if old else c.get('rank')
        co = old.get('cons_ovr') if old else c.get('ovr')
        read = old.get('user_ovr') if old else v.get('ovr')
        base = [s, (s - 1) // 32 + 1, f"{(s - 1) // 32 + 1}.{(s - 1) % 32 + 1:02d}", t, (p.name if p else pid), (p.pos if p else ''), (int(p.age) if p else ''), (home_state(p) if p else ''),
                cr if cr is not None else '', (round(float(co)) if co is not None else ''), (round(float(read)) if read is not None else ''), (round(float(p.ovr)) if p else ''), (VC.DEV_WORD.get(str(getattr(p, 'dev', 'normal')).lower(), getattr(p, 'dev', '')) if p else '')]
        rows.append(base + [(round(float(p.ratings.get(k, 0))) if p else '') for k in attrs])
    def cell(x):
        x = '' if x is None else str(x)
        return '"' + x.replace('"', '""') + '"' if (',' in x or '"' in x) else x
    return dict(ok=True, name=f"draft-{draft_year(year)}.csv", text='\n'.join(','.join(cell(x) for x in r) for r in rows))


def class_csv(session, league, abbr):
    """The coming class as a CSV: every prospect with the truth beside your room's read, so the class builder and
    the scouting can be checked. Truth: overall, ceiling, development trait, the tape, every attribute. Your room:
    the estimate, the ceiling read, the consensus rank and grade, certainty, flags."""
    pool = list(getattr(league, 'draft_pool', None) or []) or list(getattr(league, 'next_class', None) or [])
    if not pool: return dict(ok=False, why='no class has been built yet')
    cons = getattr(league, 'consensus', None) or {}
    views = ((getattr(league, 'scouting', None) or {}).get(abbr) or {})
    attrs = sorted({k for p in pool for k in (p.ratings or {}) if k.endswith('_rating')})
    import views_club as VC
    labels = {}
    for grp in VC.ATTR.values():
        for k, lab in grp: labels[k] = lab
    from views import draft_year
    head = ['name', 'pos', 'age', 'home_state', 'class_year', 'true_overall', 'true_ceiling_lo', 'true_ceiling_hi', 'dev', 'tape', 'tape_role',
            'consensus_rank', 'consensus_grade', 'your_read', 'your_ceiling_lo', 'your_ceiling_hi', 'your_certainty', 'flags'] + [labels.get(k, k.replace('_rating', '')) for k in attrs]
    rows = [head]
    for p in sorted(pool, key=lambda p: -p.ovr):
        c = cons.get(p.pid, {}) or {}; v = views.get(p.pid) or {}
        lo, hi = (p.potential_range or (p.ovr, p.ovr))
        rows.append([p.name, p.pos, int(p.age), home_state(p), getattr(p, 'class_year', '') or '', round(float(p.ovr)), round(float(lo)), round(float(hi)), VC.DEV_WORD.get(str(p.dev).lower(), p.dev),
                     round(float(p.xp_spent.get('_tape', 0) or 0), 1), p.xp_spent.get('_tape_role', ''),
                     c.get('rank', ''), (round(float(c['ovr'])) if c.get('ovr') else ''), (round(float(v['ovr'])) if v.get('ovr') else ''),
                     (round(float(v['pot_lo'])) if v.get('pot_lo') else ''), (round(float(v['pot_hi'])) if v.get('pot_hi') else ''),
                     (round(float(v.get('cert', 0) or 0), 2) if v else ''), ' '.join(v.get('flags', []) or [])]
                    + [round(float(p.ratings.get(k, 0))) for k in attrs])
    def cell(x):
        x = '' if x is None else str(x)
        return '"' + x.replace('"', '""') + '"' if (',' in x or '"' in x) else x
    yr = coming_season(league) + 1
    return dict(ok=True, name=f"class-{yr}.csv", text='\n'.join(','.join(cell(x) for x in r) for r in rows))

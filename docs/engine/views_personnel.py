"""
PERSONNEL VIEWS. Trades, Free Agency, Waivers, Extensions: what the pages show
and what their buttons do. Every action goes through the engine's own
functions; nothing here decides a deal.
"""
import numpy as np
from views import club, money, morale_word, player_plate, rail

CLUBS = ['ARI', 'ATL', 'BAL', 'BUF', 'CAR', 'CHI', 'CIN', 'CLE', 'DAL', 'DEN', 'DET', 'GB', 'HOU', 'IND', 'JAX', 'KC', 'LV', 'LAC', 'LA', 'MIA', 'MIN', 'NE', 'NO', 'NYG', 'NYJ', 'PHI', 'PIT', 'SF', 'SEA', 'TB', 'TEN', 'WAS']


def _rng(league, salt=0):
    return np.random.default_rng((league.year * 1000 + int(league.week or 0)) * 7 + salt)


# ============================================================ TRADES
def _pick_row(league, pk):
    yrs = pk.year - league.year
    return dict(id=f"{pk.year}-{pk.round}-{pk.original}", year=pk.year, round=pk.round, original=pk.original, owner=pk.owner,
                slot=(f"{pk.round}.{((pk.selection - 1) % 32) + 1}" if pk.selection else f"R{pk.round}"), label=f"{pk.year} R{pk.round}" + (f" ({pk.original})" if pk.original != pk.owner else ''),
                years_out=yrs, used=bool(pk.used_on))


def _find_pick(league, abbr, pid_str):
    for pk in league.teams[abbr].picks:
        if f"{pk.year}-{pk.round}-{pk.original}" == pid_str and not pk.used_on: return pk
    return None


def _plate(league, p, note=''):
    pl = player_plate(p, note); pl['age'] = int(p.age); pl['yrs'] = p.contract.years if p.contract else 0; pl['hit'] = round(p.cap_hit(0), 1); pl['penalty'] = round(p.dead_if_cut(0), 1)
    return pl


def trades(session, league, abbr, other=None, a_sends=(), b_sends=()):
    import trades as TR, valuation as VAL
    me = league.teams[abbr]; other = other or ('DEN' if abbr != 'DEN' else 'KC'); them = league.teams[other]
    rng = _rng(league, 3); pool = VAL.pool_from_league(league)
    my_surplus, my_needs = TR.surplus_and_needs(league, me, pool, rng)
    their_surplus, their_needs = TR.surplus_and_needs(league, them, pool, rng)
    deadline = league.week is not None and 1 <= int(league.week) <= TR.TRADE_DEADLINE_WEEK
    offseason = league.phase in ('offseason', 'free_agency', 'preseason') or not league.week
    can_trade = offseason or deadline
    pkg = _evaluate(league, abbr, other, list(a_sends), list(b_sends)) if (a_sends or b_sends) else None
    return dict(rail=rail(session, league, abbr), clubs=[club(c) for c in CLUBS if c != abbr], other=club(other),
                me=dict(club=club(abbr), cap=round(me.cap_space, 1), roster=[_plate(league, p) for p in sorted(me.active(), key=lambda p: -p.ovr)],
                        picks=[_pick_row(league, pk) for pk in sorted(me.picks, key=lambda k: (k.year, k.round)) if not pk.used_on],
                        surplus=[dict(pid=x['pid'], why=('asked out' if x.get('wants_out') else 'depth behind a starter')) for x in my_surplus], needs=sorted(my_needs)),
                them=dict(club=club(other), cap=round(them.cap_space, 1), roster=[_plate(league, p) for p in sorted(them.active(), key=lambda p: -p.ovr)],
                          picks=[_pick_row(league, pk) for pk in sorted(them.picks, key=lambda k: (k.year, k.round)) if not pk.used_on],
                          surplus=[dict(pid=x['pid'], why=('asked out' if x.get('wants_out') else 'depth behind a starter')) for x in their_surplus], needs=sorted(their_needs),
                          coach=them.gm.name if them.gm else '', prestige=round(getattr(them.gm, 'prestige', 50)) if them.gm else None),
                package=pkg, can_trade=can_trade, deadline_week=TR.TRADE_DEADLINE_WEEK,
                note=None if can_trade else 'The trade deadline has passed. Trades reopen after the season.')


def _assets(league, abbr, items, pool, rng, viewer):
    """items: pids or pick ids -> asset dicts priced through the viewer's eyes."""
    import trades as TR
    out = []
    for it in items:
        pk = _find_pick(league, abbr, it) if '-' in str(it) else None
        if pk is not None: out.append(TR.pick_asset(league, pk)); continue
        p = league.player(it)
        if p is None or p.team != abbr: continue
        out.append(TR.player_asset(league, league.teams[abbr], p, pool, rng, viewer=viewer))
    return out


def _evaluate(league, abbr, other, a_sends, b_sends):
    """Both clubs price the package. Returns the read in words, never the dollars."""
    import trades as TR, trade_engine as TE, valuation as VAL
    me, them = league.teams[abbr], league.teams[other]
    rng = _rng(league, 5); pool = VAL.pool_from_league(league)
    ga, gb = TR.persona(me.gm), TR.persona(them.gm)
    offer_a = dict(a_sends=_assets(league, abbr, a_sends, pool, rng, viewer=them), a_gets=_assets(league, other, b_sends, pool, rng, viewer=me))
    r = TE.evaluate(offer_a, me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb)
    # words for their side
    g = r['b_gain']
    if r.get('blocked'): read = f"It does not work on the cap: {r['blocked']}."; verdict = 'blocked'
    elif g >= 4: read = f"{them.abbr} would take this and feel they won it. You are giving more than you need to."; verdict = 'overpay'
    elif g >= 0.5: read = f"This is fair for {them.abbr}. They would take it."; verdict = 'fair'
    elif g >= -3: read = f"Close, a touch short for {them.abbr}. A mid-round pick or a depth piece would get it done."; verdict = 'short'
    else: read = f"Well short. {them.abbr} would not consider this as it stands."; verdict = 'far'
    mine = r['a_gain']
    my_read = 'Your assistants like your side of it.' if mine > 1 else 'Your assistants call your side about even.' if mine > -2 else 'Your assistants think you are giving up too much.'
    # roster counts after
    return dict(verdict=verdict, read=read, my_read=my_read, roster_after=dict(me=len(me.active()) - len([x for x in a_sends if '-' not in str(x)]) + len([x for x in b_sends if '-' not in str(x)]),
                                                                              them=len(them.active()) + len([x for x in a_sends if '-' not in str(x)]) - len([x for x in b_sends if '-' not in str(x)])),
                cap_after=dict(me=round(me.cap_space - sum(league.player(x).cap_hit(0) for x in b_sends if '-' not in str(x) and league.player(x)) + sum(league.player(x).cap_hit(0) for x in a_sends if '-' not in str(x) and league.player(x)), 1)),
                would_accept=bool(r.get('accepted', False)) or (g >= 0.5 and not r.get('blocked')))


def act_propose(league, abbr, other, a_sends, b_sends):
    import trades as TR
    ev = _evaluate(league, abbr, other, list(a_sends), list(b_sends))
    if ev['verdict'] == 'blocked': return dict(ok=False, done=False, why=ev['read'])
    them = league.teams[other]
    rng = _rng(league, 11)
    # their GM answers: the engine's acceptance roll on their gain
    import trade_engine as TE, valuation as VAL
    pool = VAL.pool_from_league(league); me = league.teams[abbr]
    r = TE.evaluate(dict(a_sends=_assets(league, abbr, a_sends, pool, rng, viewer=them), a_gets=_assets(league, other, b_sends, pool, rng, viewer=me)), me.ctx(), them.ctx(), me.cap_space, them.cap_space, TR.persona(me.gm), TR.persona(them.gm))
    yes = TR.will_accept(r['b_gain'], rng, TR.persona(them.gm)['aggression'], selling=True)
    if not yes:
        return dict(ok=True, done=False, why=f"{them.abbr} declines. " + ev['read'])
    a_items = [(_find_pick(league, abbr, x) if '-' in str(x) else x) for x in a_sends]; b_items = [(_find_pick(league, other, x) if '-' in str(x) else x) for x in b_sends]
    league.trade(abbr, other, [x for x in a_items if x is not None], [x for x in b_items if x is not None])
    league.log('trade', a=abbr, b=other, a_sends=[str(x) for x in a_sends], b_sends=[str(x) for x in b_sends], user=True)
    return dict(ok=True, done=True, why=f"Done. {them.abbr} accepts.")


def act_ask(league, abbr, other, a_sends, b_sends):
    """What would it take: add their cheapest asks from your picks until they would take it."""
    import trades as TR, trade_engine as TE, valuation as VAL
    me, them = league.teams[abbr], league.teams[other]; rng = _rng(league, 13); pool = VAL.pool_from_league(league)
    ga, gb = TR.persona(me.gm), TR.persona(them.gm)
    a = list(a_sends); adds = []
    picks = [pk for pk in sorted(me.picks, key=lambda k: (k.year, k.round)) if not pk.used_on and f"{pk.year}-{pk.round}-{pk.original}" not in a]
    picks.sort(key=lambda k: (-k.round, k.year))          # cheapest first
    for _ in range(4):
        r = TE.evaluate(dict(a_sends=_assets(league, abbr, a, pool, rng, viewer=them), a_gets=_assets(league, other, list(b_sends), pool, rng, viewer=me)), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb)
        if r.get('blocked'): return dict(ok=False, adds=[], line=f"It does not work on the cap: {r['blocked']}.", why=f"It does not work on the cap: {r['blocked']}.")
        if r['b_gain'] >= 0.5: break
        best = None
        for pk in picks:
            pid = f"{pk.year}-{pk.round}-{pk.original}"
            if pid in a: continue
            r2 = TE.evaluate(dict(a_sends=_assets(league, abbr, a + [pid], pool, rng, viewer=them), a_gets=_assets(league, other, list(b_sends), pool, rng, viewer=me)), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb)
            if r2['b_gain'] >= 0.5 and (best is None or pk.round > best[0].round): best = (pk, pid, r2)
            if best is None or (r2['b_gain'] < 0.5 and r2['b_gain'] > (best[2]['b_gain'] if best else -99) and best[2]['b_gain'] < 0.5): best = best or (pk, pid, r2)
        if best is None: break
        a.append(best[1]); adds.append(_pick_row(league, best[0]))
    r = TE.evaluate(dict(a_sends=_assets(league, abbr, a, pool, rng, viewer=them), a_gets=_assets(league, other, list(b_sends), pool, rng, viewer=me)), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb)
    if r['b_gain'] < 0.5: return dict(ok=True, adds=[x['id'] for x in adds], line=f"{them.abbr} would want more than your picks can add. Put a player in.")
    return dict(ok=True, adds=[x['id'] for x in adds], line=(f"{them.abbr} would do it if you add " + ', '.join(x['label'] for x in adds) + '.') if adds else f"{them.abbr} would take it as it is.")


def act_gather(league, abbr, pid):
    """What the league would give for one of your men: each club's best single-asset offer, in words."""
    import trades as TR, trade_engine as TE, valuation as VAL
    me = league.teams[abbr]; p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    rng = _rng(league, 17); pool = VAL.pool_from_league(league); ga = TR.persona(me.gm)
    offers = []
    for other, them in league.teams.items():
        if other == abbr: continue
        gb = TR.persona(them.gm)
        cands = [pk for pk in them.picks if not pk.used_on and pk.year - league.year <= 1]
        best = None
        for pk in sorted(cands, key=lambda k: (k.round, k.year)):
            r = TE.evaluate(dict(a_sends=_assets(league, abbr, [pid], pool, rng, viewer=them), a_gets=[TR.pick_asset(league, pk)]), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb)
            if r.get('blocked'): continue
            if r['b_gain'] >= 0.5: best = (pk, r); break
        if best: offers.append(dict(club=club(other), pick=_pick_row(league, best[0]), gain=best[1]['a_gain']))
    offers.sort(key=lambda o: (o['pick']['round'], -o['gain']))
    return dict(ok=True, name=p.name, offers=offers[:6], line=(f"{len(offers)} clubs would give a pick for {p.name}." if offers else f"No club would give a pick for {p.name} right now."))


# ============================================================ FREE AGENCY
def free_agency(session, league, abbr):
    import negotiations as NG, valuation as VAL
    me = league.teams[abbr]
    rows = []
    for pid in list(league.free_agents)[:400]:
        p = league.player(pid)
        if p is None or p.retired: continue
        t = NG.open_for(league, pid)
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), ovr=round(p.ovr), last=getattr(p, 'last_team', None) or '', accrued=int(p.accrued or 0),
                         talks=(t['state'] if t else None), ask=(t['ask'] if t else None), years=(t['years'] if t else None), thread=(t['id'] if t else None)))
    rows.sort(key=lambda r: -r['ovr'])
    phase = league.phase
    step = getattr(league, 'fa_step', None)
    threads = [_thread(league, t) for t in NG._threads(league) if t['kind'] in ('fa_offseason', 'fa_inseason') and t.get('team') == abbr and t['state'] not in ('expired', 'void')]
    watch = getattr(league, 'watchlist', None) or set()
    for r in rows: r['watch'] = r['pid'] in watch
    # around the league: the latest signings by other clubs
    feed = []
    for x in reversed(league.transactions[-600:]):
        if x.get('kind') in ('sign', 'extension') and x.get('team') != abbr:
            p = league.player(x.get('pid')); 
            if p is None: continue
            feed.append(dict(team=club(x['team']), name=p.name, pos=p.pos, kind=('signs' if x['kind'] == 'sign' else 'extends'), years=x.get('years'), apy=(round(float(x['apy']), 1) if x.get('apy') else None), week=x.get('week'), year=x.get('year')))
            if len(feed) >= 14: break
    return dict(rail=rail(session, league, abbr), rows=rows[:300], count=len(rows), cap=round(me.cap_space, 1), roster=len(me.active()),
                in_season=(phase == 'regular'), phase=phase, step=step, threads=threads, feed=feed, positions=sorted({r['pos'] for r in rows}))


def _thread(league, t):
    p = league.player(t['pid'])
    return dict(id=t['id'], pid=t['pid'], name=p.name if p else t['pid'], pos=p.pos if p else '', kind=t['kind'], state=t['state'], ask=t.get('ask'), years=t.get('years'), mood=t.get('mood'),
                offers=t.get('offers', []), counter=t.get('counter'), rival=t.get('rival'), due=t.get('due'), patience=t.get('patience'), log=t.get('log', []))


def act_open_talks(league, abbr, pid, kind):
    import negotiations as NG
    return NG.open_talks(league, pid, kind)


def act_offer(league, abbr, tid, apy, years, bonus=None, front_load=None, promises=(), sign_today=False):
    import negotiations as NG
    return NG.make_offer(league, tid, float(apy), int(years), bonus=bonus, front_load=front_load, promises=list(promises), sign_today=sign_today)


def act_match(league, abbr, tid):
    import negotiations as NG
    return NG.match(league, tid)


def act_withdraw(league, abbr, tid):
    import negotiations as NG
    return NG.withdraw(league, tid)


def act_watch(league, abbr, pid):
    w = getattr(league, 'watchlist', None)
    if w is None: w = league.watchlist = set()
    if pid in w: w.discard(pid); return dict(ok=True, on=False)
    w.add(pid); return dict(ok=True, on=True)


def act_match_counter(league, abbr, tid):
    import negotiations as NG
    t = NG.find(league, tid)
    if not t or not t.get('counter'): return dict(ok=False, why='no counter on the table')
    c = t['counter']; return NG.make_offer(league, tid, c['apy'], c['years'], front_load=c.get('front_load'))


# ============================================================ WAIVERS
def waivers(session, league, abbr):
    import waivers as WV
    me = league.teams[abbr]; week = int(league.week or 0)
    entries = WV.pending(league)
    order = WV.priority(league, week)
    rows = []
    for e in entries:
        p = league.player(e['pid']) if isinstance(e, dict) else league.player(e.pid)
        if p is None: continue
        d = e if isinstance(e, dict) else e.__dict__
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), ovr=round(p.ovr), frm=d.get('from_team') or d.get('team') or '', hit=round(p.cap_hit(0), 1), penalty=round(p.dead_if_cut(0), 1),
                         yrs=p.contract.years if p.contract else 0, accrued=int(p.accrued or 0), claimed=(abbr in (d.get('claims') or []))))
    rows.sort(key=lambda r: -r['ovr'])
    rel = {(e['pid'] if isinstance(e, dict) else e.pid): (e.get('release_if_awarded') if isinstance(e, dict) else None) for e in entries}
    mine = [dict(r, release=rel.get(r['pid']), release_name=(league.player(rel[r['pid']]).name if rel.get(r['pid']) and league.player(rel[r['pid']]) else None)) for r in rows if r['claimed']]
    awarded = []
    for x in reversed(league.transactions[-400:]):
        if x.get('kind') == 'waiver_claim' and x.get('year') == league.year and (x.get('week') == league.week or x.get('week') == (league.week or 0) - 1 or not league.week):
            p = league.player(x.get('pid'))
            if p: awarded.append(dict(team=club(x['team']), name=p.name, pos=p.pos, frm=x.get('from_team') or '', mine=(x['team'] == abbr)))
        if len(awarded) >= 12: break
    cut_options = [dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(p.ovr), penalty=round(p.dead_if_cut(0), 1)) for p in sorted(me.active(), key=lambda p: p.ovr)[:12]]
    return dict(rail=rail(session, league, abbr), rows=rows, claims=mine, awarded=awarded, cut_options=cut_options, priority=[club(a) for a in order], my_priority=(order.index(abbr) + 1 if abbr in order else None),
                roster=len(me.active()), roster_full=(len(me.active()) >= 53), cap=round(me.cap_space, 1), awards='at the next advance')


def act_claim(league, abbr, pid, release_pid=None):
    import waivers as WV
    r = WV.user_claim(league, pid, release_pid=release_pid)
    return dict(ok=bool(r), line=('Claim lodged. Awarded at the next advance by priority.' if r else 'He is not on the wire.'))


def act_withdraw_claim(league, abbr, pid):
    import waivers as WV
    return dict(ok=bool(WV.user_withdraw(league, pid)), line='Claim withdrawn.')


# ============================================================ EXTENSIONS
def extensions(session, league, abbr):
    import extensions as EXT, negotiations as NG
    me = league.teams[abbr]
    rows = []
    import free_agency as FA_
    for p in sorted(me.active(), key=lambda p: (p.contract.years if p.contract else 0, -p.ovr)):
        yrs = p.contract.years if p.contract else 0
        if yrs > 2: continue
        t = NG.open_for(league, p.pid, 'extension')
        cls = FA_.fa_class(p.accrued, p.contract_years_left) if yrs == 0 else None
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), ovr=round(p.ovr), yrs=yrs, fa_class=cls, hit=round(p.cap_hit(0), 1) if p.contract else 0.0, morale=morale_word(p),
                         eligible=bool(EXT.eligible(p, league)), talks=(t['state'] if t else None), thread=(t['id'] if t else None), ask=(t['ask'] if t else None), years=(t['years'] if t else None), mood=(t.get('mood') if t else None)))
    threads = [_thread(league, t) for t in NG._threads(league) if t['kind'] == 'extension' and t.get('team') == abbr and t['state'] not in ('expired', 'void')]
    promises = [dict(pid=pr['pid'], name=(league.player(pr['pid']).name if league.player(pr['pid']) else pr['pid']), kind=pr['kind'], made=pr['made'], status=pr['status']) for pr in (getattr(league, 'promises', None) or []) if pr.get('team') == abbr]
    import tags as TG_, contracts as CT
    from cap_engine import CAP
    cap = CAP.get(league.year, 301.2)
    done = []
    for x in reversed(league.transactions[-600:]):
        if x.get('kind') in ('extension', 'franchise_tag') and x.get('team') == abbr and x.get('year') == league.year:
            p = league.player(x.get('pid'))
            if p: done.append(dict(pid=p.pid, name=p.name, pos=p.pos, kind=('tagged' if x['kind'] == 'franchise_tag' else 'extended'), years=x.get('years'), apy=(round(float(x.get('apy') or x.get('price') or 0), 1))))
    for r in rows:
        p = league.player(r['pid']); r['tag_price'] = round(TG_.tag_price(p, cap), 1) if r['yrs'] <= 1 else None
        r['restructurable'] = round(CT.restructure_room(p, cap), 1) if hasattr(CT, 'restructure_room') else 0.0
    tag_open = TG_.user_tag_window(league); choice = getattr(league, 'user_tag_choice', None)
    # before the New Year a man's last season shows as one year left; after it his deal is up (0) and he is a UFA, RFA or ERFA until tagged, tendered or re-signed
    return dict(rail=rail(session, league, abbr), rows=rows, expiring=[r for r in rows if r['yrs'] <= 1], two_left=[r for r in rows if r['yrs'] == 2], done=done, threads=threads, promises=promises, cap=round(me.cap_space, 1),
                tag=dict(open=tag_open, used=(choice not in (None, 'none')), none=(choice == 'none'), tagged=(league.player(choice).name if choice not in (None, 'none') and league.player(choice) else None)),
                promise_kinds=[dict(key=k, label=v_['label']) for k, v_ in __import__('negotiation_engine').PROMISES.items()])


def act_tag(league, abbr, pid):
    import tags as TG_
    if not TG_.user_tag_window(league): return dict(ok=False, why='the tag window is the offseason, before Extensions and Tags')
    return TG_.user_tag(league, pid)

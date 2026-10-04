from inbox import player_name as inbox_player
from player_background import home_state
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
def _proj_slot(league, pk):
    """Where a future pick projects today: the original club's place in the current standings, worst record first."""
    if pk.selection: return ((pk.selection - 1) % 32) + 1
    order = sorted(league.teams.values(), key=lambda t: ((t.record[0] + 0.5 * t.record[2]) / max(1, sum(t.record)), t.record[0]))
    try: return [t.abbr for t in order].index(pk.original) + 1
    except ValueError: return None


def _ordp(n):
    return 'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')


def _pick_row(league, pk):
    yrs = pk.year - league.year; proj = _proj_slot(league, pk)
    return dict(id=f"{pk.year}-{pk.round}-{pk.original}", year=pk.year, round=pk.round, original=pk.original, owner=pk.owner,
                slot=(f"{pk.round}.{((pk.selection - 1) % 32) + 1}" if pk.selection else f"R{pk.round}"), label=f"{__import__('views').draft_year(pk.year)} R{pk.round}" + (f" ({pk.original})" if pk.original != pk.owner else ''),
                words=f"{__import__('views').draft_year(pk.year)} {['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth', 'Seventh'][pk.round - 1] if 1 <= pk.round <= 7 else str(pk.round)} Round", draft_year=__import__('views').draft_year(pk.year), own_words=(f"{club(pk.original)['nick'].title()}{'’' if club(pk.original)['nick'].endswith('S') else '’s'} Own" if pk.original == pk.owner and pk.original in league.teams else f"via {pk.original}"),
                proj=(f"Projected {proj}{_ordp(proj)}" if proj and not pk.selection else (f"Pick {pk.round}.{((pk.selection - 1) % 32) + 1}" if pk.selection else '')), years_out=yrs, used=bool(pk.used_on))


def _find_pick(league, abbr, pid_str):
    for pk in league.teams[abbr].picks:
        if f"{pk.year}-{pk.round}-{pk.original}" == pid_str and not pk.used_on: return pk
    return None


def _plate(league, p, note=''):
    pl = player_plate(p, note); pl['age'] = int(p.age); pl['yrs'] = p.contract.years if p.contract else 0; pl['hit'] = round(p.cap_hit(0), 1); pl['penalty'] = round(p.dead_if_cut(0), 1)
    return pl


def _trade_ids(league, abbr, items):
    """Accept typed UI assets and legacy links; resolve real ownership, never ID punctuation."""
    result = []
    for item in items:
        typed = isinstance(item, dict)
        ident = item.get('id') if typed else item
        kind = item.get('kind') if typed else None
        player = league.player(ident)
        pick = _find_pick(league, abbr, ident)
        actual = 'player' if player is not None and player.team == abbr else 'pick' if pick is not None else None
        if actual is None or (typed and kind != actual):
            raise ValueError('Trade asset is unavailable or has the wrong type')
        if ident not in result: result.append(ident)
    return result


def _trade_player(league, ident):
    return league.player(ident) is not None


def trades(session, league, abbr, other=None, a_sends=(), b_sends=()):
    a_sends = _trade_ids(league, abbr, a_sends)
    b_sends = _trade_ids(league, other or ('DEN' if abbr != 'DEN' else 'KC'), b_sends)
    import trades as TR, valuation as VAL
    me = league.teams[abbr]; other = other or ('DEN' if abbr != 'DEN' else 'KC'); them = league.teams[other]
    rng = _rng(league, 3); pool = VAL.pool_from_league(league)
    my_surplus, my_needs = TR.surplus_and_needs(league, me, pool, rng)
    their_surplus, their_needs = TR.surplus_and_needs(league, them, pool, rng)
    from trade_calendar import trading_open
    can_trade = trading_open(league)
    pkg = _evaluate(league, abbr, other, list(a_sends), list(b_sends)) if (a_sends or b_sends) else None
    draft_live = None
    D = getattr(session, 'draft', None)
    if D is not None and not D.done and D.current() is not None:
        q = D.current(); draft_live = dict(slot=f"{q.round}.{q.selection - 32 * (q.round - 1):02d}", sel=q.selection, team=q.owner)
    return dict(rail=rail(session, league, abbr), draft_live=draft_live, clubs=[club(c) for c in CLUBS if c != abbr], other=club(other),
                me=dict(club=club(abbr), cap=round(me.cap_space, 1), roster=[_plate(league, p) for p in sorted(me.active(), key=lambda p: -p.ovr)],
                        picks=[_pick_row(league, pk) for pk in sorted(me.picks, key=lambda k: (k.year, k.round)) if not pk.used_on],
                        surplus=[dict(pid=x['pid'], why=_surplus_why(league, me, x)) for x in my_surplus], needs=sorted(my_needs)),
                them=dict(club=club(other), cap=round(them.cap_space, 1), roster=[_plate(league, p) for p in sorted(them.active(), key=lambda p: -p.ovr)],
                          picks=[_pick_row(league, pk) for pk in sorted(them.picks, key=lambda k: (k.year, k.round)) if not pk.used_on],
                          surplus=[dict(pid=x['pid'], why=_surplus_why(league, them, x)) for x in their_surplus], needs=sorted(their_needs),
                          coach=them.gm.name if them.gm else '', prestige=round(getattr(them.gm, 'prestige', 50)) if them.gm else None),
                package=pkg, cap_year=league.year, can_trade=can_trade, deadline_week=TR.TRADE_DEADLINE_WEEK, balance=f"{len([x for x in a_sends if _trade_player(league, x)])} for {len([x for x in b_sends if _trade_player(league, x)])}",
                note=None if can_trade else 'The trade deadline has passed. Trades reopen after the season.')


def _assets(league, abbr, items, pool, rng, viewer):
    """items: pids or pick ids -> asset dicts priced through the viewer's eyes."""
    import trades as TR
    out = []
    for it in items:
        pk = _find_pick(league, abbr, it)
        if pk is not None: out.append(TR.pick_asset(league, pk)); continue
        p = league.player(it)
        if p is None or p.team != abbr: continue
        out.append(TR.player_asset(league, league.teams[abbr], p, pool, rng, viewer=viewer))
    return out


def _cap_block_read(reason, other):
    name = club(other)['name']
    messages = {
        'a_dead_money': 'Your front office will not take on the dead-money charge from this trade.',
        'b_dead_money': "We won't take on the dead-money charge from this trade.",
        'a_cannot_fit': 'Your team does not have enough cap space for this trade.',
        'b_cannot_fit': "We don't have enough cap space for this trade.",
    }
    reason = {'a_space': 'a_cannot_fit', 'b_space': 'b_cannot_fit'}.get(reason, reason)
    return messages.get(reason, 'This trade cannot proceed under the current cap constraints.')


def _evaluate(league, abbr, other, a_sends, b_sends):
    """Both clubs price the package. Returns the read in words, never the dollars."""
    a_sends = _trade_ids(league, abbr, a_sends)
    b_sends = _trade_ids(league, other, b_sends)
    import trades as TR, trade_engine as TE, valuation as VAL
    me, them = league.teams[abbr], league.teams[other]
    rng = _rng(league, 5); pool = VAL.pool_from_league(league)
    ga, gb = TR.persona(me.gm), TR.persona(them.gm)
    offer_a = dict(a_sends=_assets(league, abbr, a_sends, pool, rng, viewer=them), a_gets=_assets(league, other, b_sends, pool, rng, viewer=me))
    r = TE.evaluate(offer_a, me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb, user_a=True)
    plan_read = None
    required_gain = 0.9
    if not r.get('blocked'):
        items_a = [x if _trade_player(league, x) else _find_pick(league, abbr, x) for x in a_sends]
        items_b = [x if _trade_player(league, x) else _find_pick(league, other, x) for x in b_sends]
        decision = TR.cpu_trade_check(league, me, them, items_a, items_b)
        required_gain = max(required_gain, float(decision.get('required_gain', 0.)))
        if not decision['approved']:
            r = dict(r, blocked='cpu_plan', accepted=False)
            plan_read = decision['why']
    # Broad, deterministic interest estimate, not acceptance probability.
    target = max(1., float(r.get('b_out', 0.)) + required_gain)
    ratio = max(0., float(r.get('b_in', 0.))) / target
    interest = int(min(95, max(0, round(70 * ratio))))
    interest_band = 'low' if interest < 45 else 'medium' if interest < 63 else 'high'
    # words for their side
    g = r['b_gain']
    if r.get('blocked'):
        read = ("We need more value in return." if r['blocked'] == 'cpu_plan' and decision.get('needs_more') and r['b_gain'] < -3 else plan_read) or _cap_block_read(r['blocked'], other); verdict = 'blocked'
    elif g >= 4: read = "Strong offer; we're interested."; verdict = 'overpay'
    elif g >= 0.5: read = "Competitive offer; we're interested."; verdict = 'fair'
    elif g >= -3: read = "We're close, but we'd need more in return."; verdict = 'short'
    else: read = "We need substantially more value in return."; verdict = 'far'
    mine = r['a_gain']
    my_read = ('Change the player package or clear cap room before proceeding.' if verdict == 'blocked' else
               'Your assistants like your side of it.' if mine > 1 else
               'Your assistants call your side about even.' if mine > -2 else
               'Your assistants think you are giving up too much.')
    extra = []
    outgoing = {pid for pid in a_sends if _trade_player(league, pid)}
    incoming = [league.player(pid) for pid in b_sends if _trade_player(league, pid)]
    positions = sorted({league.player(pid).pos for pid in outgoing})
    for pos in positions:
        remaining = [p for p in me.active() if p.pid not in outgoing] + incoming
        healthy = [p for p in remaining if p.pos == pos and p.out_until is None]
        extra.append(f"Your {pos} depth after this trade: {len(healthy)} healthy player{'s' if len(healthy) != 1 else ''}.")
    my_read += (' ' + ' '.join(extra) if extra else '')
    # roster counts after
    return dict(verdict=verdict, read=read, my_read=my_read, interest=interest, interest_band=interest_band, roster_after=dict(me=len(me.active()) - len([x for x in a_sends if _trade_player(league, x)]) + len([x for x in b_sends if _trade_player(league, x)]),
                                                                              them=len(them.active()) + len([x for x in a_sends if _trade_player(league, x)]) - len([x for x in b_sends if _trade_player(league, x)])),
                cap_after=dict(
                    me=round(__import__('cap_accounting').trade_projection(league, me.abbr, a_sends, b_sends).space(me.phase), 1),
                    them=round(__import__('cap_accounting').trade_projection(league, them.abbr, b_sends, a_sends).space(them.phase), 1)),
                would_accept=not r.get('blocked') and (bool(r.get('accepted', False)) or g >= 0.5))


def _words(league, items):
    out = []
    for x in items:
        if x is None: continue
        if hasattr(x, 'round') and hasattr(x, 'year'): out.append(f"{__import__('views').draft_year(x.year)} R{x.round}")
        else:
            p = league.player(getattr(x, 'pid', x))
            if p is not None: out.append(f"{inbox_player(p)} ({p.pos})")
    return out or ['nothing']


def _need_groups():
    return {'QB': ['QB'], 'RB': ['HB', 'FB'], 'WR': ['WR'], 'TE': ['TE'], 'OL': ['LT', 'LG', 'C', 'RG', 'RT'], 'DL': ['LEDG', 'DT', 'REDG'], 'LB': ['MIKE', 'WILL', 'SAM'], 'CB': ['CB'], 'S': ['FS', 'SS'], 'ST': ['K', 'P', 'LS']}


def _surplus_why(league, t, x):
    p = league.player(x['pid'])
    if p is None: return ''
    if x.get('wants_out'): return 'Unhappy · Asked Out'
    d = t.depth.get(p.pos, []); idx = next((i for i, q in enumerate(d) if q.pid == p.pid), None)
    words = []
    if idx is not None and idx >= 1: words.append(['First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth'][min(idx, 5)] + ' on the chart')
    elif idx == 0: words.append('Starter at a deep spot')
    try:
        import gm_engine as GE
        f = float(GE.scheme_fit(p.ratings, p.pos, t))
        if f <= -0.5: words.append(f"Fit {f:+.1f}")
    except Exception: pass
    if p.contract: words.append(f"{p.contract.years} Yr{'s' if p.contract.years != 1 else ''}")
    return ' · '.join(words) or 'Depth behind a starter'


def act_save_trade_counter(league, abbr, msg_id, other, a_sends, b_sends):
    import inbox as IB
    m = next((m for m in IB._box(league) if m['id'] == int(msg_id)), None)
    pl = (m or {}).get('payload') or {}
    draft = pl.get('counter') or {}
    if (not m or m.get('kind') != 'trade_offer' or m.get('status') != 'countered'
            or pl.get('user_team', abbr) != abbr or pl.get('buyer') != other
            or draft.get('state') not in ('draft', 'declined')):
        return dict(ok=False, why='This counter is no longer available.')
    try:
        a = _trade_ids(league, abbr, a_sends); b = _trade_ids(league, other, b_sends)
    except ValueError as e:
        return dict(ok=False, why=str(e))
    def typed(ids):
        return [dict(kind='player' if _trade_player(league, x) else 'pick', id=x) for x in ids]
    draft.update(a=typed(a), b=typed(b), state='draft')
    return dict(ok=True)


def act_propose(league, abbr, other, a_sends, b_sends, counter_id=None):
    counter = None
    if counter_id is not None:
        saved = act_save_trade_counter(league, abbr, counter_id, other, a_sends, b_sends)
        if not saved['ok']: return dict(**saved, done=False)
        counter = next(m for m in league.inbox if m['id'] == int(counter_id))['payload']['counter']
    a_sends = _trade_ids(league, abbr, a_sends)
    b_sends = _trade_ids(league, other, b_sends)
    import trades as TR
    ev = _evaluate(league, abbr, other, list(a_sends), list(b_sends))
    if ev['verdict'] == 'blocked': return dict(ok=False, done=False, why=ev['read'])
    them = league.teams[other]
    rng = _rng(league, 11)
    # their GM answers: the engine's acceptance roll on their gain
    import trade_engine as TE, valuation as VAL
    pool = VAL.pool_from_league(league); me = league.teams[abbr]
    r = TE.evaluate(dict(a_sends=_assets(league, abbr, a_sends, pool, rng, viewer=them), a_gets=_assets(league, other, b_sends, pool, rng, viewer=me)), me.ctx(), them.ctx(), me.cap_space, them.cap_space, TR.persona(me.gm), TR.persona(them.gm), user_a=True)
    a_items = [(x if _trade_player(league, x) else _find_pick(league, abbr, x)) for x in a_sends]; b_items = [(x if _trade_player(league, x) else _find_pick(league, other, x)) for x in b_sends]
    decision = TR.cpu_trade_check(league, me, them, a_items, b_items)
    if not decision['approved']:
        if counter is not None: counter['state'] = 'declined'
        return dict(ok=False, done=False, why=decision['why'])
    yes = TR.will_accept(r['b_gain'], rng, TR.persona(them.gm)['aggression'], selling=True)
    if not yes:
        if counter is not None: counter['state'] = 'declined'
        return dict(ok=True, done=False, why=(ev['read'] if ev['verdict'] in ('short', 'far') else "We are not ready to accept this offer."))
    try: league.trade(abbr, other, [x for x in a_items if x is not None], [x for x in b_items if x is not None])
    except ValueError as e: return dict(ok=False, done=False, why=str(e))
    if counter is not None: counter['state'] = 'accepted'
    import inbox as IB
    IB.post(league, 'trade_done', f"Trade with {other} is done", '', sender=other,
            payload=dict(user_team=abbr, mail_layout='trade',
                         mail_sections=IB.trade_sections(abbr, other, _words(league, a_items), _words(league, b_items))))
    return dict(ok=True, done=True, why=f"Done. {them.abbr} accepts.")


def act_ask(league, abbr, other, a_sends, b_sends):
    """Find a verified seller-acceptable package, without mutating the offer."""
    a_sends = _trade_ids(league, abbr, a_sends)
    b_sends = _trade_ids(league, other, b_sends)
    import trades as TR, trade_engine as TE, valuation as VAL
    me, them = league.teams[abbr], league.teams[other]
    if not b_sends: return dict(ok=False, adds=[], why='Select something you want from them first.')
    pool = VAL.pool_from_league(league); ga, gb = TR.persona(me.gm), TR.persona(them.gm)
    # Match Propose's valuation seed and value existing players only once.
    rng = _rng(league, 11)
    outgoing = _assets(league, abbr, a_sends, pool, rng, viewer=them)
    incoming = _assets(league, other, b_sends, pool, rng, viewer=me)
    def evaluate(extra):
        return TE.evaluate(dict(a_sends=outgoing + extra, a_gets=incoming), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb, user_a=True)
    initial = evaluate([])
    if initial.get('blocked'):
        return dict(ok=False, adds=[], why=_cap_block_read(initial['blocked'], other))
    def plan_check(ids):
        sent = [_find_pick(league, abbr, x) or x for x in ids]
        received = [_find_pick(league, other, x) or x for x in b_sends]
        return TR.cpu_trade_check(league, me, them, sent, received)
    # Use the same roster and funding checks as Propose before promising that
    # a larger pick package fixes the deal. The seller may choose future value
    # if its remaining roster still covers the essential jobs.
    decision = plan_check(a_sends)
    if not decision['approved'] and not decision.get('needs_more'):
        return dict(ok=False, adds=[], why=decision['why'])
    required_gain = max(0.9, float(decision.get('required_gain', 0.9)))
    candidates = []
    for pk in me.picks:
        pid = f"{pk.year}-{pk.round}-{pk.original}"
        if not pk.used_on and pid not in a_sends:
            asset = TR.pick_asset(league, pk)
            if asset is not None: candidates.append((pk, pid, asset))
    candidates.sort(key=lambda x: (x[0].year, x[0].round, x[1]))
    def alternative_ids(original, ids):
        seller_ask = max(0.0, -TE.evaluate(dict(a_sends=[], a_gets=incoming), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb, user_a=True)['b_gain'])
        alternative = TR.seller_pick_counter(original, [x[2] for x in candidates], them.ctx(), gb, them.cap_space,
                                             seller_ask=seller_ask)
        if not alternative: return ids
        def asset_id(a):
            if a['kind'] == 'player': return a['pid']
            pk = a['obj']
            return f"{pk.year}-{pk.round}-{pk.original}"
        alt_ids = [asset_id(a) for a in alternative]
        check = TE.evaluate(dict(a_sends=alternative, a_gets=incoming), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb, user_a=True)
        if not check.get('blocked') and check['b_gain'] > required_gain and plan_check(alt_ids)['approved']:
            return alt_ids
        return ids
    def response(ids):
        adds = [x for x in ids if x not in a_sends]
        removes = [x for x in a_sends if x not in ids]
        if not adds and not removes:
            return dict(ok=True, adds=[], removes=[], line=f"{other} would take it as it is.")
        add_labels = [_pick_row(league, _find_pick(league, abbr, x))['label'] for x in adds]
        remove_labels = [_pick_row(league, _find_pick(league, abbr, x))['label'] for x in removes]
        line = f"{other} proposes adding " + ', '.join(add_labels)
        if removes: line += ' in place of ' + ', '.join(remove_labels)
        return dict(ok=True, adds=adds, removes=removes, line=line + '.')
    if decision['approved'] and initial['b_gain'] > required_gain:
        return response(alternative_ids(outgoing, a_sends))
    # Bounded beam search explores combinations instead of repeatedly taking the first late pick.
    frontier = [()]; best = None
    for size in range(1, min(4, len(candidates)) + 1):
        pending = []
        for prefix in frontier:
            for i in range(prefix[-1] + 1 if prefix else 0, len(candidates)):
                package = prefix + (i,)
                result = evaluate([candidates[j][2] for j in package])
                if result.get('blocked'): continue
                cost = result['b_gain'] - initial['b_gain']  # Seller values compensation; never read the buyer's private gain.
                if result['b_gain'] > required_gain:
                    key = (cost, size, package)
                    if best is None or key < best[0]: best = (key, package)
                else:
                    pending.append((max(0, required_gain + .01 - result['b_gain']), cost, package))
        pending.sort()
        frontier = [row[2] for row in pending[:64]]
        if not frontier: break
    if best is None:
        return dict(ok=False, adds=[], why=f"{other} could not find an acceptable package of up to four additional picks. Add a player or change the target.")
    chosen = [candidates[i] for i in best[1]]
    # Reprice the complete offer exactly as Propose will, then verify the final package.
    rng = _rng(league, 11)
    final = TE.evaluate(dict(a_sends=_assets(league, abbr, a_sends + [x[1] for x in chosen], pool, rng, viewer=them), a_gets=_assets(league, other, b_sends, pool, rng, viewer=me)), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb, user_a=True)
    if final.get('blocked') or final['b_gain'] <= required_gain:
        return dict(ok=False, adds=[], why='No acceptable counteroffer was found. Your offer has not changed.')
    decision = plan_check(a_sends + [x[1] for x in chosen])
    if not decision['approved']:
        return dict(ok=False, adds=[], why=decision['why'])
    final_ids = a_sends + [x[1] for x in chosen]
    return response(alternative_ids(outgoing + [x[2] for x in chosen], final_ids))


def act_gather(league, abbr, pid):
    """What the league would give for one of your players: every club's best offer, as a package. A package is a
    pick, two picks, or a pick and a surplus player; a club makes it only if it thinks it gained, and the offer
    shown is the one that pays you the most. All offers are returned; the page scrolls them."""
    import trades as TR, trade_engine as TE, valuation as VAL, itertools
    me = league.teams[abbr]; p = league.player(pid)
    if p is None or p.team != abbr: return dict(ok=False, why='not on your roster')
    rng = _rng(league, 17); pool = VAL.pool_from_league(league); ga = TR.persona(me.gm)
    mine = _assets(league, abbr, [pid], pool, rng, viewer=None)
    my_value = sum(x.get('trade_value', 0.0) for x in mine) if mine else 0.0
    offers = []
    for other, them in league.teams.items():
        if other == abbr: continue
        gb = TR.persona(them.gm)
        picks = [pk for pk in them.picks if not pk.used_on and pk.year - league.year <= 1]
        picks.sort(key=lambda k: (k.year, k.round))
        try: their_surplus, _n = TR.surplus_and_needs(league, them, pool, rng)
        except Exception: their_surplus = []
        sur = [x for x in their_surplus if league.player(x['pid']) is not None][:4]
        cands = [[('pick', pk)] for pk in picks]
        # two picks: a later pick sweetening an earlier one, when one pick alone falls short of him
        if my_value >= 1.5:
            for a_, b_ in itertools.combinations(picks, 2):
                if a_.round >= 2 or b_.round >= 2: cands.append([('pick', a_), ('pick', b_)])
            for pk in picks:
                for x in sur: cands.append([('pick', pk), ('player', x['pid'])])
        best = None
        sends_them = _assets(league, abbr, [pid], pool, rng, viewer=them)            # my man through their eyes, once a club
        asset_cache = {}
        def asset_of(kind, it):
            k = (kind, it if kind != 'pick' else f"{it.year}-{it.round}-{it.original}")
            if k not in asset_cache: asset_cache[k] = TR.pick_asset(league, it) if kind == 'pick' else TR.player_asset(league, them, league.player(it), pool, rng)
            return asset_cache[k]
        for pkg in cands[:24]:
            gets = [asset_of(kind, it) for kind, it in pkg]
            r = TE.evaluate(dict(a_sends=sends_them, a_gets=gets), me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb, user_a=True)
            if r.get('blocked') or r['b_gain'] < 0.5: continue
            ids = [f'{it.year}-{it.round}-{it.original}' if kind == 'pick' else it for kind, it in pkg]
            # Match Propose's checks and deterministic GM decision, including
            # the same valuation RNG sequence. Never advertise a rejected deal.
            if _evaluate(league, abbr, other, [pid], ids)['verdict'] == 'blocked': continue
            answer_rng = _rng(league, 11)
            answer = TE.evaluate(dict(
                a_sends=_assets(league, abbr, [pid], pool, answer_rng, viewer=them),
                a_gets=_assets(league, other, ids, pool, answer_rng, viewer=me)),
                me.ctx(), them.ctx(), me.cap_space, them.cap_space, ga, gb, user_a=True)
            if answer.get('blocked') or not TR.will_accept(answer['b_gain'], answer_rng, gb['aggression'], selling=True): continue
            if best is None or r['a_gain'] > best[1]['a_gain']: best = (pkg, r)
        if best:
            pkg, r = best
            items = [(_pick_row(league, it) if kind == 'pick' else None) for kind, it in pkg]
            words = [(_pick_row(league, it)['label'] if kind == 'pick' else f"{league.player(it).name} ({league.player(it).pos}, {round(league.player(it).ovr)})") for kind, it in pkg]
            ids = [(f"{it.year}-{it.round}-{it.original}" if kind == 'pick' else it) for kind, it in pkg]
            first_round = min((it.round for kind, it in pkg if kind == 'pick'), default=8)
            offers.append(dict(club=club(other), words=words, ids=ids, assets=[dict(kind=kind, id=ident) for (kind, _), ident in zip(pkg, ids)], gain=r['a_gain'], first_round=first_round, n=len(pkg)))
    offers.sort(key=lambda o: -o['gain'])
    return dict(ok=True, name=p.name, offers=offers, line=(f"{len(offers)} club{'s' if len(offers) != 1 else ''} would deal for {p.name}." if offers else f"No club would give anything for {p.name} right now."))


# ============================================================ FREE AGENCY
def free_agency(session, league, abbr):
    import negotiations as NG, valuation as VAL
    import player_roles as PR
    me = league.teams[abbr]
    depth = me.depth
    rows = []
    # Send the full market so position filters and name search can find every
    # available player. The browser limits only the currently drawn rows.
    ordered = sorted(list(league.free_agents), key=lambda x: -(league.player(x).ovr if league.player(x) else 0))
    for pid in ordered:
        p = league.player(pid)
        if p is None or p.retired: continue
        display_pos = PR.fa_position(p, me)
        filter_positions = list(PR.fa_positions(p, me))
        t = NG.open_for(league, pid)
        mine = [o for o in (t.get('offers') or [])] if t else []
        my_offer = (f"${mine[-1]['apy']:.1f}m × {mine[-1]['years']}" if mine else None)
        interest = (None if not t else 'Match Asked' if t.get('rival') and t['state'] not in ('accepted', 'declined') else 'Agreed' if t['state'] in ('accepted', 'signed') else 'Countered' if t['state'] == 'countered' else 'Mulling' if t['state'] == 'waiting' else 'Walked' if t['state'] in ('broken_off', 'declined') else 'Talking' if mine else 'Not Yet')
        try: fit = round(float(__import__('gm_engine').scheme_fit(p.ratings, p.pos, me)), 1)
        except Exception: fit = 0.0
        wk = int(league.week or 0); prorate = ((19 - wk) / 18.0) if (league.phase == 'regular' and 1 <= wk <= 18) else 1.0
        ask_now = (round(float(t['ask']) * prorate, 2) if t and t.get('ask') else None)
        hole = None
        d = depth.get(p.pos, [])
        out_men = [q for q in d[:2] if q.out_until is not None]
        if out_men: hole = f"Fills the hole at {display_pos} with {__import__('views').surname(out_men[0].name)} out" + (f" to week {out_men[0].out_until}" if isinstance(out_men[0].out_until, int) else '')
        elif len(d) <= 1: hole = f"Only {len(d)} healthy {display_pos} on the roster"
        import practice_squad as PSQ
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, display_pos=display_pos, filter_positions=filter_positions,
                         age=int(p.age), ovr=round(p.ovr), fit=fit, starter=(p.ovr >= 76), rookie=bool(p.college and p.draft_round is None and p.draft_year == league.year), last=getattr(p, 'last_team', None) or '', accrued=int(p.accrued or 0), ps_ok=PSQ.can_add(me, p),
                         talks=(t['state'] if t else None), ask=(t['ask'] if t else None), ask_now=ask_now, years=(t['years'] if t else None), thread=(t['id'] if t else None), interest=interest, my_offer=my_offer, hole=hole))
    rows.sort(key=lambda r: -r['ovr'])
    phase = league.phase
    step = getattr(league, 'fa_step', None)
    # the round's lodged bids: how many clubs are in on each player (the numbers stay private; the interest is known)
    bids = getattr(league, 'fa_bids', None) or {}
    for r in rows: r['bidders'] = len(bids.get(r['pid'], []) or [])
    fa_round = getattr(league, 'fa_bids_phase', None)
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
    steps = ['Tags', 'Market Day 1', 'Market Days 2–3', 'Post-Draft', 'Camp']
    step_i = None
    if phase in ('offseason', 'free_agency'):
        step_i = 0 if step is None else 1 if step == 1 else 2 if step in (2, 3) else 3
    elif phase == 'preseason': step_i = 4
    from views import next_year_cap, cap_focus
    limit_next, committed_next, _ro, _dn = next_year_cap(league, me)
    focus = cap_focus(league, me)
    from offer_reservations import pending_offers
    outstanding = pending_offers(league, abbr)
    for t_ in threads: t_['cap'] = focus
    import practice_squad as PSQ
    ps_n = len(PSQ.squad(me))
    return dict(rail=rail(session, league, abbr), cap_focus=focus, rows=rows, count=len(rows), cap=focus['space'], pending_offers=outstanding, roster=len(me.active()), ps=ps_n, committed_next=committed_next, limit_next=limit_next, steps=steps, step_i=step_i, top51=(phase != 'regular'),
                weeks_left=(19 - int(league.week or 0) if phase == 'regular' else None),
                in_season=(phase == 'regular'), phase=phase, step=step, fa_round=fa_round, threads=threads, feed=feed,
                positions=sorted({r['pos'] for r in rows}), position_filters=PR.fa_position_filters(me))


def _thread(league, t):
    import negotiations as NG
    p = league.player(t['pid'])
    mood = t.get('mood') or 'open'
    temper = {'eager': 'Eager', 'firm': 'Firm', 'open': 'Open', 'deferring': 'Deferring'}.get(mood, mood.capitalize())
    pat = t.get('patience'); pat_word = ('Patient' if (pat or 0) >= 3 else 'Short on patience' if (pat or 0) <= 1 else 'Measured')
    offseason = league.phase in ('offseason', 'free_agency', 'draft')
    answers = ('at the next step of the market' if t['kind'].startswith('fa_offseason') else 'at the next Advance' if t['kind'] == 'fa_inseason' else 'on the spot' if offseason else 'within a week or two')
    op = t.get('opened')
    ROUNDS_ = {19: 'Wild Card', 20: 'Divisional', 21: 'Conf. Finals', 22: 'Championship Game'}     # the playoffs run as weeks 19 to 22 inside
    opened = ((f"Week {op}" if op <= 18 else ROUNDS_.get(op, 'the playoffs')) if op is not None and op < 100 else ('the offseason' if op == 100 else f"FA step {op - 100}") if op is not None else '')
    return dict(id=t['id'], pid=t['pid'], name=p.name if p else t['pid'], pos=p.pos if p else '', kind=t['kind'], state=t['state'], ask=t.get('ask'), years=t.get('years'), mood=mood, opened=opened,
                offers=t.get('offers', []), counter=t.get('counter'), rival=t.get('rival'), due=t.get('due'), patience=pat, log=t.get('log', []), sign_today_offer=NG.sign_today_offer(league, t),
                agent_line=f"The agent is {temper} and {pat_word}. He answers {answers}.")


def act_offer_preview(league, abbr, pid, apy, years, bonus=None, front_load=None, promises=()):
    """What an offer would cost by year: the cap hit each season, the year-one hit, the total."""
    from cap_engine import CAP
    p = league.player(pid); t = league.teams[abbr]
    if p is None: return dict(ok=False, why='no such player')
    import contract_offer as CO, negotiations as NG
    thread = NG.open_for(league, pid)
    kind = thread['kind'] if thread else ('extension' if p.team == abbr and p.contract else 'fa_offseason')
    try:
        package = CO.canonical(league, p, t, dict(apy=apy, years=years, bonus=bonus, front_load=front_load, promises=list(promises)), kind)
        bonus, front_load = package['bonus'], package['front_load']
        interest = NG._assessment(league, p, thread, package) if thread and thread.get('ask') and thread.get('years') else None
        interest = ({k: interest[k] for k in ('acceptable', 'ratio', 'interest', 'reasons')} if interest else None)
    except (TypeError, ValueError, OverflowError) as exc:
        return dict(ok=False, why=str(exc))
    import practice_squad as PS
    if p.contract is None or (p.team in league.teams and p in PS.squad(league.teams[p.team])):
        import market as MK
        d = MK.signing_terms(league, p, t, float(apy), int(years), CAP.get(league.year, 301.2), float(front_load) if front_load is not None else None, bonus)
        hits = d['cap_hits']
        return dict(ok=True, interest=interest, bonus=bonus, front_load=front_load, hits=hits, years=[d['start_year'] + i for i in range(int(years))], total=round(d['total'], 2), year1=hits[0], cash_this_season=round(d['cash_this_season'], 2), prorated=d['fraction'] < 1, annual_apy=float(apy), dead_if_cut=[])
    import extensions as EXT
    try:
        c = EXT.build(p, int(years), float(apy), CAP.get(league.year, 301.2), t.gm, league,
                      front_load=float(front_load) if front_load is not None else None, bonus=bonus)
    except ValueError as e:
        return dict(ok=False, why=str(e))
    # Contract index zero is still the current league year before the rollover.
    hits = [round(c.cap_hit(i), 3) for i in range(c.years)]
    expiry = round(c.remaining_proration(c.years), 3)
    if expiry: hits.append(expiry)
    def charge(contract, i):
        if i < contract.years: return contract.cap_hit(i)
        return contract.remaining_proration(i) if i == contract.years else 0.0
    impact = [dict(year=league.year+i, existing=round(charge(p.contract, i), 3),
                   change=round(charge(c, i)-charge(p.contract, i), 3),
                   total=round(charge(c, i), 3)) for i in range(len(hits))]
    return dict(ok=True, interest=interest, bonus=bonus, front_load=front_load, extension=True, existing_years=p.contract.years,
                hits=hits, years=[league.year + i for i in range(len(hits))],
                expiry_year=league.year + c.years if expiry else None,
                total=round(float(apy) * int(years), 2), year1=hits[0], cap_impact=impact,
                dead_if_cut=[c.release(i, league.post_june1())[0] for i in range(c.years)])


def act_open_talks(league, abbr, pid, kind):
    import negotiations as NG
    return NG.open_talks(league, pid, kind)


def act_offer(league, abbr, tid, apy, years, bonus=None, front_load=None, promises=(), sign_today=False):
    import negotiations as NG
    from offer_reservations import check_offer
    thread = NG.find(league, tid)
    if thread is None or thread.get('team') != abbr:
        return dict(ok=False, why='no such negotiation')
    why = check_offer(league, abbr, thread, apy, years, bonus, front_load)
    if why:
        return dict(ok=False, why=why)
    return NG.make_offer(league, tid, float(apy), int(years), bonus=bonus, front_load=front_load, promises=list(promises), sign_today=sign_today)


def act_match(league, abbr, tid):
    import negotiations as NG
    from offer_reservations import check_offer
    thread = NG.find(league, tid)
    if thread is None or thread.get('team') != abbr:
        return dict(ok=False, why='no such negotiation')
    rival = thread.get('rival') or {}
    if thread.get('state') == 'match_requested' and rival:
        why = check_offer(league, abbr, thread, rival['apy'], rival['years'], bonus=rival.get('bonus'), front_load=rival.get('front_load'))
        if why:
            return dict(ok=False, why=why)
    return NG.match(league, tid)


def act_withdraw(league, abbr, tid):
    import negotiations as NG
    return NG.withdraw(league, tid)


def act_poach_ps(league, abbr, pid):
    """Sign another club's practice-squad man to your 53. The real rule: any club may, he is promoted at a 53-man
    salary, and he must stay on your active roster three weeks. His agent hears the number first (a one-year deal
    at the minimum or a little over); Sign in the thread takes him off their squad and onto your roster."""
    import practice_squad as PSQ, negotiations as NG
    p = league.player(pid)
    if p is None or p.team is None or p.team == abbr: return dict(ok=False, why='not on another club\'s practice squad')
    other = league.teams.get(p.team)
    if other is None or p not in PSQ.squad(other): return dict(ok=False, why='he is not on a practice squad')
    me = league.teams[abbr]
    r = NG.open_talks(league, pid, kind='fa_inseason')
    if r.get('ok'): r['line'] = f"{p.name}'s agent will listen: a 53-man deal at ${r['ask']:.1f}m. Sign him from the thread and he leaves {p.team}'s squad for your roster."
    return r


def act_sign_ps(league, abbr, pid):
    """Sign a free agent to the practice squad. He can say no: a man who grades as a roster player wants a
    53-man deal, and an ambitious one will not take a squad spot unless he has nowhere else to go."""
    import practice_squad as PSQ
    t = league.teams[abbr]; p = league.player(pid)
    if p is None or pid not in league.free_agents: return dict(ok=False, why='he is not on the market')
    if not PSQ.can_add(t, p): return dict(ok=False, why=('the squad is full' if len(PSQ.squad(t)) >= PSQ.SIZE else 'the squad has no room for him under its rules (six veterans at most)'))
    amb = float((getattr(p, 'traits', None) or {}).get('ambition', 50))
    if p.ovr >= 76: return dict(ok=False, why=f"{p.name} wants a roster spot, not the practice squad.")
    if p.ovr >= 72 and amb >= 58: return dict(ok=False, why=f"{p.name} turned it down; he believes he can start somewhere.")
    if not PSQ.sign_to_squad(league, abbr, pid): return dict(ok=False, why='the squad could not take him')
    import inbox as IB
    IB.post(league, 'squad', f"{inbox_player(p)} to the practice squad", f"{inbox_player(p)} ({p.pos}, {round(p.ovr)}) signed to your practice squad at the weekly rate.", sender='assistants')
    return dict(ok=True, line=f"{p.name} signed to the practice squad.")


def act_watch(league, abbr, pid):
    w = getattr(league, 'watchlist', None)
    if w is None: w = league.watchlist = set()
    if pid in w: w.discard(pid); return dict(ok=True, on=False)
    w.add(pid); return dict(ok=True, on=True)


def act_match_counter(league, abbr, tid):
    import negotiations as NG
    t = NG.find(league, tid)
    if not t or t['state'] != 'countered' or not t.get('counter'): return dict(ok=False, why='no counter on the table')
    c = t['counter']
    previous = (t.get('offers') or [{}])[-1]
    # Older counters omitted bonus/promises; preserve the last offer's terms.
    bonus = c.get('bonus', previous.get('bonus'))
    if bonus is not None: bonus = min(float(bonus), c['apy'] * c['years'])
    return NG.make_offer(league, tid, c['apy'], c['years'], bonus=bonus,
                         front_load=c.get('front_load', previous.get('front_load')),
                         promises=c.get('promises', previous.get('promises', [])))


# ============================================================ WAIVERS
def waivers(session, league, abbr):
    import waivers as WV
    me = league.teams[abbr]; week = int(league.week or 0)
    entries = WV.pending(league)
    order = WV.priority(league, week)
    rows = []
    for e in entries:
        p = league.player(e['pid']) if isinstance(e, dict) else league.player(e.pid)
        if p is None or p.team is not None: continue        # signed to a squad since he was waived: not available
        d = e if isinstance(e, dict) else e.__dict__
        if d.get('from_team') == abbr: continue              # your own waived men are not yours to claim
        if not WV.reaches_user(league, d, week): continue    # a club ahead of you will take him; you never see him
        try: fit = round(float(__import__('gm_engine').scheme_fit(p.ratings, p.pos, me)), 1)
        except Exception: fit = 0.0
        frm = d.get('from_team') or d.get('team') or ''
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), ovr=round(p.ovr), fit=fit, home_state=home_state(p), frm=frm, hit=round(p.cap_hit(0), 1), penalty=round(p.dead_if_cut(0), 1),
                         yrs=p.contract.years if p.contract else 0, inherited=(f"${p.cap_hit(0):.1f}m · {p.contract.years} Yr{'s' if p.contract.years != 1 else ''}" if p.contract else 'Min'), accrued=int(p.accrued or 0), claimed=(abbr in (d.get('claims') or [])),
                         read=_claim_read(league, me, p, frm, order, abbr)))
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
    # YOUR OWN PLAYERS ON THE WIRE. Waived, not yet cleared: off your roster, not a free agent, and not claimable by
    # you, so without this list they were nowhere on any page until the wire ran
    intent = getattr(league, 'ps_intent', None) or {}
    outbound = []
    for e in entries:
        d = e if isinstance(e, dict) else e.__dict__
        if d.get('from_team') != abbr: continue
        p = league.player(d['pid'])
        if p is None or p.team is not None: continue
        outbound.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), ovr=round(p.ovr), claims=len(d.get('claims') or []),
                             intent=('Practice squad if he clears' if intent.get(p.pid) == abbr else 'Released if he clears')))
    return dict(rail=rail(session, league, abbr), rows=rows, claims=mine, awarded=awarded, outbound=outbound, cut_options=cut_options, priority=[club(a) for a in order], my_priority=(order.index(abbr) + 1 if abbr in order else None),
                roster=len(me.active()), roster_full=(len(me.active()) >= 53), cap=round(me.cap_space, 1), awards='at the next advance')


def _claim_read(league, me, p, frm, order, abbr):
    """The assistants on a claim: where he would sit, why the other club let him go, who is ahead of you."""
    d = me.depth.get(p.pos, []); better = sum(1 for q in d if q.ovr > p.ovr)
    place = ('a starter here' if better == 0 else f"{['second', 'third', 'fourth', 'fifth'][min(better - 1, 3)]} on the chart at {p.pos}")
    thin = len(d) <= 2 or (len(d) >= 2 and d[1].ovr < d[0].ovr - 12)
    try:
        import gm_engine as GE
        f = float(GE.scheme_fit(p.ratings, p.pos, me)); fitw = ' and grades well in our scheme' if f >= 0.5 else ' though he grades below his rating in our scheme' if f <= -0.5 else ''
    except Exception: fitw = ''
    why = 'a cap move, not a judgment on his play' if p.contract and p.apy >= 3.0 else 'a numbers cut at a deep spot'
    ahead = (order.index(abbr) if abbr in order else 0)
    return f"He would be {place}{fitw}. {p.pos} is {'thin' if thin else 'covered'} behind the starter. {frm} let him go as {why}. {ahead} club{'s are' if ahead != 1 else ' is'} ahead of you in priority."


def act_claim(league, abbr, pid, release_pid=None):
    import waivers as WV
    r = WV.user_claim(league, pid, release_pid=release_pid)
    return dict(ok=bool(r), line=('Claim lodged. Awarded at the next advance by priority.' if r else 'He is not on the wire.'))


def act_withdraw_claim(league, abbr, pid):
    import waivers as WV
    return dict(ok=bool(WV.user_withdraw(league, pid)), line='Claim withdrawn.')


# ============================================================ EXTENSIONS
def retain(session, league, abbr):
    import tags as TG, extensions as EXT
    sheet = TG.user_resign_sheet(league)
    sheet['ufa'] = [r for r in sheet['ufa'] if not r['tagged']]
    for row in sheet['ufa']:
        row['eligible'] = EXT.eligible(league.player(row['pid']), league)
    return dict(rail=rail(session, league, abbr), **sheet)


def extensions(session, league, abbr):
    import extensions as EXT, negotiations as NG
    me = league.teams[abbr]
    # the offseason room answers on the spot: a thread left waiting from before the room existed is answered now
    if league.phase in ('offseason', 'free_agency', 'draft'):
        for t in NG._threads(league):
            if t['kind'] == 'extension' and t.get('team') == abbr and t['state'] == 'waiting' and t.get('offers'):
                p = league.player(t['pid'])
                if p is None: t['state'] = 'expired'; continue
                offer = t['offers'][-1]; NG._answer(league, t, p, offer, t.get('pending_floor') or NG._floor(league, p, t, offer), quiet=True)
    rows = []
    import free_agency as FA_
    for p in sorted(me.active(), key=lambda p: (p.contract.years if p.contract else 0, -p.ovr)):
        yrs = p.contract.years if p.contract else 0
        t = NG.open_for(league, p.pid, 'extension')
        cls = FA_.fa_class(p.accrued, p.contract_years_left) if yrs == 0 else None
        rows.append(dict(pid=p.pid, name=p.name, pos=p.pos, age=int(p.age), ovr=round(p.ovr), yrs=yrs, fa_class=cls, hit=round(p.cap_hit(0), 1) if p.contract else 0.0, morale=morale_word(p),
                         rookie_option=EXT.rookie_option_price(league, p),
                         eligible=bool(EXT.eligible(p, league)), talks=(t['state'] if t else None), thread=(t['id'] if t else None), ask=(t.get('ask') if t else None), years=(t.get('years') if t else None), mood=(t.get('mood') if t else None)))
    threads = [_thread(league, t) for t in NG._threads(league) if t['kind'] == 'extension' and t.get('team') == abbr and t['state'] not in ('expired', 'void', 'accepted', 'signed')]
    promises = [dict(pid=pr['pid'], name=(league.player(pr['pid']).name if league.player(pr['pid']) else pr['pid']), kind=pr['kind'], made=pr['made'], status=pr['status']) for pr in (getattr(league, 'promises', None) or []) if pr.get('team') == abbr]
    import tags as TG_, contracts as CT
    from cap_engine import CAP
    cap = CAP.get(league.year, 301.2)
    done = []
    for x in reversed(league.transactions[-600:]):
        if x.get('kind') in ('extension', 'franchise_tag', 'rookie_option') and x.get('team') == abbr and x.get('year') == league.year:
            p = league.player(x.get('pid'))
            if p: done.append(dict(pid=p.pid, name=p.name, pos=p.pos, kind=('tagged' if x['kind'] == 'franchise_tag' else 'option exercised' if x['kind'] == 'rookie_option' else 'extended'), years=x.get('years'), apy=(round(float(x.get('apy') or x.get('price') or 0), 1))))
    for r in rows:
        p = league.player(r['pid']); r['tag_price'] = round(TG_.tag_price(p, cap), 1) if r['yrs'] <= 1 else None
        r['restructurable'] = round(CT.restructure_room(p, cap), 1) if hasattr(CT, 'restructure_room') else 0.0
    tag_open = TG_.user_tag_window(league); choice = getattr(league, 'user_tag_choice', None)
    # before the New Year a man's last season shows as one year left; after it his deal is up (0) and he is a UFA, RFA or ERFA until tagged, tendered or re-signed
    from views import cap_focus
    from cap_accounting import next_year_ledger
    limit_next, committed_next, _ro, _dn = next_year_ledger(league, me)
    extension_cap = dict(year=int(league.year) + 1, limit=round(limit_next, 1),
                         committed=round(committed_next, 1),
                         space=round(limit_next - committed_next, 1))
    current_cap = dict(year=int(league.year), limit=round(me.cap.limit, 1),
                       committed=round(me.cap.charges(me.phase), 1), space=round(me.cap_space, 1))
    focus = cap_focus(league, me)
    for t_ in threads:
        t_['cap'] = focus
        t_['extension_cap'] = extension_cap
        t_['current_cap'] = current_cap
        offer = t_.get('counter') if t_.get('state') == 'countered' else (
            (t_.get('offers') or [None])[-1] if t_.get('state') == 'waiting' else None)
        if offer:
            t_['offer_cap_preview'] = act_offer_preview(league, abbr, t_['pid'],
                offer['apy'], offer['years'], bonus=offer.get('bonus'), front_load=offer.get('front_load'))
    for r in rows:
        st = r.get('talks')
        r['talks_word'] = ({'waiting': 'Waiting', 'countered': 'Countered', 'open': 'Talking', 'accepted': 'Agreed', 'signed': 'Agreed', 'declined': 'Declined', 'broken_off': 'Broke Off'}.get(st, 'Not Started') if st else ('Not Started' if r.get('eligible') else 'After Season' if r.get('yrs', 0) <= 1 else 'Not Eligible'))
        r['ask_word'] = (f"${r['ask']}m × {r['years']}" if r.get('ask') else ('Ask First' if r.get('eligible') else '—'))
        yrs = r['yrs']
        r['tag_line'] = ('Expiring' if yrs == 0 else f"{yrs} Year{'s' if yrs != 1 else ''} Left") + (' · Eligible' if r.get('eligible') and yrs > 1 else '')
    return dict(rail=rail(session, league, abbr), cap_focus=focus, current_cap=current_cap, extension_cap=extension_cap, rows=rows, expiring=[r for r in rows if r['yrs'] == 0], one_left=[r for r in rows if r['yrs'] == 1], two_left=[r for r in rows if r['yrs'] == 2], long_term=[r for r in rows if r['yrs'] > 2], done=done, threads=threads, promises=promises, cap=round(me.cap_space, 1), committed_next=round(committed_next, 1), limit_next=round(limit_next, 1),
                tag=dict(open=tag_open, used=(choice not in (None, 'none')), none=(choice == 'none'), tagged=(league.player(choice).name if choice not in (None, 'none') and league.player(choice) else None)),
                promise_kinds=[dict(key=k, label=v_['label']) for k, v_ in __import__('negotiation_engine').PROMISES.items()])


def act_rookie_option(league, abbr, pid):
    p = league.player(pid)
    if p is None or p.team != abbr:
        return dict(ok=False, why='player is not on your team')
    import extensions as EXT
    return EXT.exercise_rookie_option(league, pid)


def act_tag(league, abbr, pid):
    import tags as TG_
    if not TG_.user_tag_window(league): return dict(ok=False, why='the tag window is the offseason, before Extensions and Tags')
    return TG_.user_tag(league, pid)

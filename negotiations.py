"""
NEGOTIATIONS. One live thread per man you are talking to, resolved at the
advance the way everything else is.

  open_talks(league, pid, kind)     the agent's ballpark and mood; no offer made, no patience spent
  make_offer(league, tid, ...)      an offer onto the thread; the agent answers now or at the advance
  resolve(league, week=None, fa_step=None)   called by the calendar: answers come to the inbox
  match(league, tid)                meet a rival's terms on a match request: he signs now
  withdraw(league, tid)

THE RULES
  Extensions: a conversation, then the agent gets back to you after a number
  of weeks set by the situation: a loyal man being offered the market answers
  within a week; a star in his final year takes two or three and watches the
  market; an unhappy man takes longer. Agents can decline to negotiate in
  season at all ("we will talk after the season") when a man is playing well
  in his final year and wants the leverage.
  In-season free agency: mostly uncontested. He decides at the advance
  against whatever else came in, unless you ask him to sign today so he can
  play Sunday, which costs you the ask with no discount, and he may still
  take another club's deal if one is on the table.
  Offseason free agency: nobody signs on the spot unless there is a reason
  (your offer is clearly the best and he is loyal or wants certainty, or you
  are the only club talking to him). Otherwise he mulls and at the next step
  of the market you get yes, no, a counter, or a request to match a rival;
  match and he signs then. Two match rounds per man per step, then he picks.
  Talks can break off: an offer a quarter under the ask is an insult and ends
  talks for four weeks; every lowball under 90% of the ask spends patience,
  and when it is gone he is done with you until the next offseason.

THE PROMISES. Every promise on a signed deal goes into league.promises with
the man, the club, the kind and the year. Each week the ledger is checked:
a starting role not held by week four is broken; an extension_by not signed
by its year is broken; a tag on a man promised none is broken. Breaking one
is the morale hit and the trust cost morale_system already defines.
"""
import numpy as np, itertools

_ids = itertools.count(1)
INSULT = 0.75            # under this share of the ask, talks break off
LOWBALL = 0.90           # under this, patience is spent
PATIENCE = 3
BREAK_WEEKS = 4
MATCH_ROUNDS = 2
SIGN_TODAY_PREMIUM = 0.00     # he signs today at the ask, no discount; nothing above it


def _threads(league):
    if not hasattr(league, 'negotiations') or league.negotiations is None:
        league.negotiations = []
    return league.negotiations


def find(league, tid):
    return next((t for t in _threads(league) if t['id'] == tid), None)


def open_for(league, pid, kind=None):
    return next((t for t in _threads(league) if t['pid'] == pid and t['state'] in ('open', 'waiting', 'countered', 'match_requested')
                 and (kind is None or t['kind'] == kind)), None)


# ------------------------------------------------------------ the agent's read
def _situation(league, p):
    import personality as PT
    tr = getattr(p, 'traits', None) or {}
    m = getattr(p, 'morale', None)
    return dict(loyalty=tr.get('loyalty', 50) / 100.0, money=tr.get('financial_priority', 50) / 100.0,
                morale=(m.value if m else 50.0), star=p.ovr >= 88, final_year=(p.contract is not None and p.contract.years <= 1),
                in_season=(league.phase in ('regular_season', 'season', 'regular', 'playoffs') or (1 <= int(league.week or 0) <= 18)))


def _say(t, who, text):
    t.setdefault('log', []).append(dict(who=who, text=text))


def open_talks(league, pid, kind='extension'):
    """The agent's ballpark and mood. Costs nothing."""
    import extensions as EXT, valuation as VAL
    p = league.player(pid)
    if p is None:
        return dict(ok=False, why='no such player')
    t = open_for(league, pid, kind)
    if t and t['state'] == 'broken_off' and t.get('broken_until', 0) > _clock(league):
        return dict(ok=False, why=f"his agent is not taking your calls until week {t['broken_until']}")
    s = _situation(league, p)
    if kind == 'extension':
        if not EXT.eligible(p, league):
            return dict(ok=False, why='not eligible: more than two years left, or a rookie deal before his third season')
        tm = EXT.terms(league, p, np.random.default_rng(abs(hash(pid)) % (2**32)))
        if tm is None:
            return dict(ok=False, why='no market read on him')
        # an agent can decline to talk in season: a star in his final year who is playing well wants the leverage
        if s['in_season'] and s['star'] and s['final_year'] and s['money'] > 0.55 and s['morale'] >= 40 and (abs(hash(pid)) % 100) < 60:
            return dict(ok=True, will_talk=False, mood='deferring', ask=None, years=tm['years'],
                        line=f"{p.name}'s agent says they will talk after the season. He is playing well and they want to see the market first.")
        ask = tm['ask']; years = tm['years']
    else:
        v = VAL.value_player(league, p, side='agent', rng=None)
        if not v: return dict(ok=False, why='no market read on him')
        ask, years = v['apy'], int(np.clip(v['years'], 1, 4))
        # a Recruiter over his position: he wants to play for that coach, and the ask comes down a little
        import staff as ST
        _pull, ask_mult = ST.recruit_pull(league.teams[league.user_team], p.pos)
        ask = round(ask * ask_mult, 2)
    mood = ('eager' if s['loyalty'] > 0.62 and s['morale'] >= 45 else 'firm' if s['money'] > 0.62 or s['star'] else 'open')
    line = {'eager': f"{p.name} wants to stay. His agent will move quickly on a fair deal.",
            'firm': f"{p.name}'s agent knows the market for his position and will not go under it.",
            'open': f"{p.name}'s agent is open to talking and expects something near the market."}[mood]
    if s['morale'] < 30: line += " He is unhappy here, and it will show in the number."
    if not t:
        t = dict(id=next(_ids), pid=pid, team=p.team if kind == 'extension' else getattr(league, 'user_team', None), kind=kind,
                 state='open', offers=[], patience=PATIENCE, opened=_clock(league), ask=round(ask, 2), years=years,
                 mood=mood, due=None, counter=None, rival=None, match_rounds=0, broken_until=0)
        _threads(league).append(t)
    return dict(ok=True, will_talk=True, thread=t['id'], ask=round(ask, 2), years=years, mood=mood, line=line, patience=t['patience'])


def _clock(league):
    return int(league.week or 0) if league.phase not in ('offseason', 'free_agency') else 100 + int(getattr(league, 'fa_step', 0))


# ------------------------------------------------------------ the offer
def make_offer(league, tid, apy, years, bonus=None, front_load=None, promises=(), sign_today=False):
    import extensions as EXT
    t = find(league, tid)
    if t is None: return dict(ok=False, why='no such negotiation')
    if t['state'] in ('accepted', 'declined', 'broken_off', 'expired'):
        return dict(ok=False, why=f"this negotiation is {t['state']}")
    p = league.player(t['pid']); s = _situation(league, p)
    offer = dict(apy=float(apy), years=int(years), bonus=bonus, front_load=front_load, promises=list(promises), when=_clock(league), by='you')
    t['offers'].append(offer)
    _say(t, 'you', f"${float(apy):.1f}m a year over {int(years)}" + (f", {'front' if (front_load or 0.5) >= 0.66 else 'back' if (front_load or 0.5) <= 0.34 else 'even'}-loaded" if front_load is not None else '') + (f", with {', '.join(str(x).replace('_', ' ') for x in promises)}" if promises else '') + '.')
    ask = t['ask']
    # an insult ends it
    if apy < INSULT * ask:
        t['state'] = 'broken_off'; t['broken_until'] = _clock(league) + BREAK_WEEKS; _say(t, 'agent', 'That is an insult. We are done talking for now.')
        _post(league, t, f"{p.name}'s agent has ended talks", f"An offer of ${apy:.1f}m against an ask of ${ask:.1f}m is not a negotiation. He will not take your calls for {BREAK_WEEKS} weeks.")
        return dict(ok=True, state='broken_off')
    # a lowball spends patience
    if apy < LOWBALL * ask:
        t['patience'] -= 1
        if t['patience'] <= 0:
            t['state'] = 'broken_off'; t['broken_until'] = _clock(league) + 30; _say(t, 'agent', 'You keep coming in low. He is going to look elsewhere.')
            _post(league, t, f"{p.name}'s agent is done for now", "Three offers under the market. They will revisit it in the offseason.")
            return dict(ok=True, state='broken_off')
    # what he will take, shape and loyalty and morale included (extensions.py knows the floor logic)
    floor = _floor(league, p, t, offer)
    if sign_today and t['kind'] == 'fa_inseason':
        # today means the ask, no discount; and another club may already have him
        if apy + 1e-9 >= ask and not t.get('rival'):
            return _accept(league, t, offer, how='signed today')
        _say(t, 'agent', f"To sign today he wants the ask, ${ask:.1f}m." + (" Another club is also talking to him." if t.get('rival') else ''))
        return dict(ok=True, state='open', line=t['log'][-1]['text'])
    # when does he answer
    t['state'] = 'waiting'
    if t['kind'] == 'extension':
        wait = 1 + (2 if s['star'] and s['final_year'] else 0) + (1 if s['morale'] < 35 else 0) - (1 if s['loyalty'] > 0.62 else 0)
        t['due'] = _clock(league) + max(1, wait)
    else:
        t['due'] = _clock(league) + 1                    # the next advance or the next step of the market
    # an on-the-spot yes, when there is a reason
    if t['kind'] == 'fa_offseason' and apy >= floor and not t.get('rival') and (s['loyalty'] > 0.62 or s['money'] < 0.4):
        return _accept(league, t, offer, how='signed on the spot')
    t['pending_floor'] = floor
    _say(t, 'agent', f"{p.name}'s agent will get back to you" + (f" in about {t['due'] - _clock(league)} week{'s' if t['due'] - _clock(league) != 1 else ''}." if t['kind'] == 'extension' else ' at the next step.'))
    return dict(ok=True, state='waiting', due=t['due'], line=t['log'][-1]['text'])


def _floor(league, p, t, offer):
    import extensions as EXT, personality as PT, morale_system as MS
    ask = t['ask']
    if t['kind'] == 'extension':
        tm = EXT.terms(league, p, np.random.default_rng(1)) or {}
        disc = tm.get('discount', 0.0)
        floor = ask * (1.0 - disc)
    else:
        floor = ask * 0.96
        # a Recruiter over his position: the club's money reads richer to him
        import staff as ST
        pull, _m = ST.recruit_pull(league.teams[league.user_team], p.pos)
        floor = floor / pull
    fl = offer.get('front_load')
    if fl is not None:
        fp = (getattr(p, 'traits', None) or {}).get('financial_priority', 50) / 100.0
        floor *= 1.0 + (0.5 - float(fl)) * 0.12 * (0.7 + 0.6 * fp)
    if getattr(p, 'morale', None) is not None:
        ne = MS.negotiation_effect(p.morale); floor *= 1.0 + ne['demand_premium']
    # promises are worth something to him
    import negotiation_engine as NE
    for k in offer.get('promises', []):
        floor *= 1.0 - NE.PROMISES.get(k, {}).get('base', 0.0)
    return floor


# ------------------------------------------------------------ the advance
def resolve(league, week=None, fa_step=None):
    """Answers due now come back to the inbox; broken-off talks reopen when their time is up."""
    now = _clock(league)
    out = []
    for t in _threads(league):
        if t['state'] == 'broken_off' and t.get('broken_until', 0) <= now:
            t['state'] = 'expired'
            pp = league.player(t['pid'])
            if pp is not None: _post(league, t, f"{pp.name}'s agent will talk again", 'The break he took after your last offer is over. Ask again if you still want him.')
        if t['state'] != 'waiting' or (t.get('due') or 0) > now:
            continue
        p = league.player(t['pid'])
        if p is None or (t['kind'] == 'extension' and p.team != t['team']):
            t['state'] = 'expired'; continue
        offer = t['offers'][-1]; floor = t.get('pending_floor') or _floor(league, p, t, offer)
        # a rival in the offseason market: the match request
        rival = t.get('rival')
        if t['kind'] == 'fa_offseason' and rival and rival['apy'] > offer['apy'] and t['match_rounds'] < MATCH_ROUNDS \
                and (rival['apy'] - offer['apy']) / rival['apy'] <= 0.12:
            t['state'] = 'match_requested'; t['match_rounds'] += 1; _say(t, 'agent', f"He has a better offer on the table. Match it and he is yours.")
            _post(league, t, f"{p.name} asks you to match", f"{league.teams[rival['team']].abbr if rival['team'] in league.teams else rival['team']} has offered ${rival['apy']:.1f}m over {rival['years']} years. He would rather be here. Match it and he signs today.",
                  payload=dict(rival=rival, thread=t['id'], link=f'negotiation:{t["id"]}'))
            out.append((t, 'match_requested')); continue
        if offer['apy'] + 1e-9 >= floor and not (rival and rival['apy'] > offer['apy'] * 1.12):
            r = _accept(league, t, offer, how='agreed')
            if not r.get('ok'):
                # the agent agreed but the deal could not be written (cap, eligibility, a roster spot): the
                # thread closes with the reason instead of sitting there and failing every week
                t['state'] = 'declined'; _say(t, 'agent', f"The deal fell through: {r.get('why') or 'it could not be written'}.")
                _post(league, t, f"{p.name}: the deal fell through", f"He agreed to your terms but the deal could not be written: {r.get('why') or 'it could not be written'}. Open talks again once that is fixed.")
                out.append((t, 'failed')); continue
            out.append((t, r['how'])); continue
        if rival and rival['apy'] > offer['apy'] * 1.12:
            t['state'] = 'declined'; _say(t, 'agent', 'Another club is well above you and he is going to take it.'); _post(league, t, f"{p.name} says no", f"Another club is well above you and he is going to take it."); out.append((t, 'declined')); continue
        # a counter: toward the floor, not all the way
        counter = round(min(t['ask'], floor * (1.0 + 0.03 * max(0, t['patience'] - 1))), 2)    # never above his own ask
        t['state'] = 'countered'; t['counter'] = dict(apy=counter, years=t['years'], front_load=0.5); _say(t, 'agent', f"Close. He would do it at ${counter:.1f}m a year.")
        _post(league, t, f"{p.name}'s agent counters at ${counter:.1f}m", f"Over {t['years']} years at the league shape. " + ("He is close." if counter <= offer['apy'] * 1.06 else "There is a gap."),
              payload=dict(counter=t['counter'], thread=t['id'], link=f'negotiation:{t["id"]}'))
        out.append((t, 'countered'))
    return out


def set_rival(league, pid, team, apy, years):
    """The market tells the thread another club is in."""
    t = open_for(league, pid, 'fa_offseason') or open_for(league, pid, 'fa_inseason')
    if t: t['rival'] = dict(team=team, apy=float(apy), years=int(years))


def match(league, tid):
    t = find(league, tid)
    if t is None or t['state'] != 'match_requested': return dict(ok=False, why='nothing to match')
    r = t['rival']; offer = dict(apy=r['apy'], years=r['years'], bonus=None, front_load=0.5, promises=[], when=_clock(league), by='you (matched)')
    t['offers'].append(offer)
    return _accept(league, t, offer, how='matched and signed')


def withdraw(league, tid):
    t = find(league, tid)
    if t: t['state'] = 'declined'
    return dict(ok=True)


def _accept(league, t, offer, how):
    import extensions as EXT, market as MK
    from cap_engine import CAP
    p = league.player(t['pid'])
    if t['kind'] == 'extension':
        r = EXT.extend(league, p.pid, offer['apy'], offer['years'], front_load=offer.get('front_load'), agreed=True)
        if r['result'] != 'accepted':
            return dict(ok=False, why=r.get('why'))
    else:
        team = league.teams[t['team']]; cap = CAP.get(league.year, 301.2)
        if len(team.active()) >= 53 and p not in team.roster: return dict(ok=False, why='the 53 is full; open a roster spot')
        o = MK.Offer(t['team'], p.pid, offer['apy'], offer['years'], promises=offer.get('promises', ()), front_load=offer.get('front_load'))
        try: MK.sign(league, p, o, cap); team.sync_cap()
        except Exception as e: return dict(ok=False, why=str(e)[:120] or 'the contract could not be written')
    t['state'] = 'accepted'; _say(t, 'agent', f"Done. {p.name} is signed.")
    for k in offer.get('promises', []):
        record_promise(league, p.pid, t['team'], k)
    _post(league, t, (f"{p.name} extended" if t['kind'] == 'extension' else f"{p.name} signs"), f"{offer['years']} years at ${offer['apy']:.1f}m a year, {how}.")
    return dict(ok=True, state='accepted', how=how)


def _post(league, t, subject, body, payload=None):
    import inbox as IB
    user = getattr(league, 'user_team', None)
    if user and t.get('team') == user:
        pl = dict(payload or {}); pl.setdefault('thread', t['id']); pl['kind'] = t.get('kind'); pl['pid'] = t.get('pid')
        pl['link'] = f"negotiation:{t.get('kind')}:{t['id']}"
        IB.post(league, 'negotiation', subject, body, sender=league.player(t['pid']).name if league.player(t['pid']) else 'agent', payload=pl)


# ------------------------------------------------------------ the promise ledger
def record_promise(league, pid, team, kind, year=None):
    league.promises = getattr(league, 'promises', None) or []
    league.promises.append(dict(pid=pid, team=team, kind=kind, made=league.year, year=year or (league.year + 1 if kind == 'extension_by' else None), status='open'))


def check_promises(league, week):
    """Weekly. A promise not kept is broken, with the hit the morale module defines."""
    import morale_system as MS
    broken = []
    for pr in getattr(league, 'promises', None) or []:
        if pr['status'] != 'open': continue
        p = league.player(pr['pid']); team = league.teams.get(pr['team'])
        if p is None or team is None or p.team != pr['team']:
            pr['status'] = 'void'; continue
        ok = None
        if pr['kind'] == 'starting_role' and week and week >= 4:
            ps = team.depth.get(p.pos, []); ok = bool(ps) and ps[0] is p
            if p.out_until is not None: ok = None                     # hurt men are not judged
        elif pr['kind'] == 'extension_by' and league.year > (pr['year'] or 9999):
            ok = False
        elif pr['kind'] == 'no_franchise' and getattr(p, 'tagged_year', None) == league.year:
            ok = False
        elif pr['kind'] == 'no_trade' and p.team != pr['team']:
            ok = False
        if ok is False:
            pr['status'] = 'broken'
            if p.morale is not None:
                p.morale.break_promise(pr['kind'])
            league.log('promise_broken', pid=p.pid, team=pr['team'], promise=pr['kind'])
            broken.append(pr)
        elif ok is True and pr['kind'] == 'starting_role' and week and week >= 8:
            pr['status'] = 'kept'
    return broken


def ledger(league, team=None):
    return [pr for pr in (getattr(league, 'promises', None) or []) if team is None or pr['team'] == team]

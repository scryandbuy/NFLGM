from inbox import player_name as inbox_player
from stable import stable_seed
"""
NEGOTIATIONS. One live thread per man you are talking to, resolved at the
advance the way everything else is.

  open_talks(league, pid, kind)     the agent's ballpark and mood; no offer made, no patience spent
  make_offer(league, tid, ...)      an offer onto the thread; the agent answers now or at the advance
  resolve(league, week=None, fa_step=None)   called by the calendar: answers come to the inbox
  match(league, tid)                meet a rival's terms on a match request: he signs now
  withdraw(league, tid)

THE RULES
  Extensions, offseason: the whole conversation happens in the room. Every
  offer is answered on the spot: he takes it, counters, or walks, and you can
  come back at a counter as many times as his patience lasts. Nothing waits
  for the advance.
  Extensions, in season: a conversation, then the agent gets back to you after a number
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
import numpy as np, itertools, math

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
    for t in league.negotiations:
        if t.get('counter'):
            c = t['counter']; previous = (t.get('offers') or [{}])[-1]
            c.setdefault('bonus', previous.get('bonus'))
            if c['bonus'] is not None: c['bonus'] = min(float(c['bonus']), c['apy'] * c['years'])
            c.setdefault('promises', list(previous.get('promises', [])))
        if t.get('kind') == 'fa_inseason' and t.get('state') not in ('accepted', 'declined', 'expired', 'void'):
            t['years'] = 1
            if t.get('counter'): t['counter']['years'] = 1
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
        tm = EXT.terms(league, p, np.random.default_rng(stable_seed(pid)))
        if tm is None:
            return dict(ok=False, why='no market read on him')
        # A firm refusal to negotiate is independent of package valuation.
        if s['in_season'] and s['star'] and s['final_year'] and s['money'] > 0.55 and s['morale'] >= 40 and (stable_seed(pid) % 100) < 60:
            return dict(ok=True, will_talk=False, mood='deferring', ask=None, years=tm['years'],
                        line=f"{p.name}'s agent says they will talk after the season. He is playing well and they want to see the market first.")
        ask = tm['ask']; years = tm['years']
    else:
        v = VAL.value_player(league, p, side='agent', rng=None)
        if not v: return dict(ok=False, why='no market read on him')
        from contract_terms import MAX_OFFER_YEARS
        ask, years = v['apy'], (1 if kind == 'fa_inseason' else int(np.clip(v['years'], 1, MAX_OFFER_YEARS)))
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
        if kind == 'extension': t['discount'] = tm['discount']
    if kind == 'fa_offseason':
        # a round is open: the agent tells you who else is in, and how much
        bids = (getattr(league, 'fa_bids', None) or {}).get(pid) or []
        if bids:
            import market as MK
            best = MK.best_offer(league, p, [MK.Offer.from_save(b) for b in bids])
            set_rival(league, pid, best.team, best.apy, best.years, best.bonus, best.front_load, best.promises)
            line += f" {len(bids)} other club{'s' if len(bids) != 1 else ''} {'are' if len(bids) != 1 else 'is'} in on him."
    return dict(ok=True, will_talk=True, thread=t['id'], ask=round(ask, 2), years=years, mood=mood, line=line, patience=t['patience'])


def _clock(league):
    return int(league.week or 0) if league.phase not in ('offseason', 'free_agency') else 100 + int(getattr(league, 'fa_step', 0) or 0)   # fa_step is None before the market opens


# ------------------------------------------------------------ the offer
def make_offer(league, tid, apy, years, bonus=None, front_load=None, promises=(), sign_today=False):
    import extensions as EXT
    t = find(league, tid)
    if t is None: return dict(ok=False, why='no such negotiation')
    if t['state'] in ('accepted', 'declined', 'broken_off', 'expired'):
        return dict(ok=False, why=f"this negotiation is {t['state']}")
    if t['state'] == 'match_requested':
        return dict(ok=False, why='Match the competing offer or let him sign with the other team.')
    c = t.get('counter') if t['state'] == 'countered' else None
    p = league.player(t['pid']); s = _situation(league, p)
    offer = dict(apy=float(apy), years=int(years), bonus=bonus, front_load=front_load, promises=list(promises), when=_clock(league), by='you')
    import contract_offer as CO
    try:
        offer = CO.canonical(league, p, league.teams[t['team']], offer, t['kind'])
        assessment = _assessment(league, p, t, offer)
    except (ValueError, TypeError, OverflowError) as exc:
        return dict(ok=False, why=str(exc))
    # Validate before consuming patience or replacing a standing counter.
    from offer_reservations import check_offer
    why = check_offer(league, t['team'], t, offer['apy'], offer['years'], offer['bonus'], offer['front_load'])
    if why: return dict(ok=False, why=why)
    t['counter'] = None
    t['offers'].append(offer)
    _say(t, 'you', f"${float(apy):.1f}m a year over {int(years)}" + (f", {'front' if front_load > 0.5 else 'back' if front_load < 0.5 else 'even'}-loaded" if front_load is not None else '') + (f", with {', '.join(str(x).replace('_', ' ') for x in promises)}" if promises else '') + '.')
    # HIS OWN NUMBER IS A YES. An offer that meets the agent's standing counter (his money and his years) is the
    # deal he asked for: it is signed on the spot, whatever the kind of talk or the time of year. It had gone back
    # into the queue as a fresh offer and the agent took a week to say yes to his own terms.
    agreed_counter = CO.canonical(league, p, league.teams[t['team']], c, t['kind']) if c else None
    if (agreed_counter and offer['apy'] + 1e-9 >= agreed_counter['apy'] and offer['years'] == agreed_counter['years']
            and offer['bonus'] == agreed_counter['bonus'] and offer['front_load'] == agreed_counter['front_load']
            and set(offer['promises']) == set(agreed_counter['promises'])):
        result = _accept(league, t, offer, how='counter accepted')
        if not result.get('ok'): t['counter'] = c
        return result
    ask = t['ask']
    room = (t['kind'] == 'extension' and not s['in_season'])      # the offseason room: he answers here, and a walk is a walk
    # an insult ends it
    if assessment['ratio'] < INSULT:
        if room:
            t['state'] = 'declined'; _say(t, 'agent', f"That is an insult. ${apy:.1f}m against ${ask:.1f}m is not a negotiation. He will test the market.")
            return dict(ok=True, state='declined', line=t['log'][-1]['text'])
        t['state'] = 'broken_off'; t['broken_until'] = _clock(league) + BREAK_WEEKS; _say(t, 'agent', 'That is an insult. We are done talking for now.')
        _post(league, t, f"{p.name}'s agent has ended talks", f"An offer of ${apy:.1f}m against an ask of ${ask:.1f}m is not a negotiation. He will not take your calls for {BREAK_WEEKS} weeks.")
        return dict(ok=True, state='broken_off')
    # a lowball spends patience
    if assessment['ratio'] < LOWBALL:
        t['patience'] -= 1
        if t['patience'] <= 0:
            if room:
                t['state'] = 'declined'; _say(t, 'agent', 'You keep coming in low. He is done here and will see what the market says.')
                return dict(ok=True, state='declined', line=t['log'][-1]['text'])
            t['state'] = 'broken_off'; t['broken_until'] = _clock(league) + 30; _say(t, 'agent', 'You keep coming in low. He is going to look elsewhere.')
            _post(league, t, f"{p.name}'s agent is done for now", "Three offers under the market. They will revisit it in the offseason.")
            return dict(ok=True, state='broken_off')
    # what he will take, shape and loyalty and morale included (extensions.py knows the floor logic)
    floor = _floor(league, p, t, offer, assessment)
    if sign_today and t['kind'] == 'fa_inseason':
        # today means the ask, no discount; and another club may already have him
        if _assessment(league, p, t, offer, immediate=True)['acceptable'] and not t.get('rival'):
            return _accept(league, t, offer, how='signed today')
        _say(t, 'agent', f"To sign today he wants the ask, ${ask:.1f}m." + (" Another club is also talking to him." if t.get('rival') else ''))
        return dict(ok=True, state='open', line=t['log'][-1]['text'])
    # the offseason room: an extension is answered on the spot, in the conversation, and nothing goes to the inbox
    if t['kind'] == 'extension' and not s['in_season']:
        state = _answer(league, t, p, offer, floor, quiet=True)
        return dict(ok=True, state=state, line=(t['log'][-1]['text'] if t.get('log') else ''), counter=t.get('counter'))
    # when does he answer
    t['state'] = 'waiting'
    if t['kind'] == 'extension':
        wait = 1 + (2 if s['star'] and s['final_year'] else 0) + (1 if s['morale'] < 35 else 0) - (1 if s['loyalty'] > 0.62 else 0)
        t['due'] = _clock(league) + max(1, wait)
    elif t['kind'] == 'fa_offseason' and league.phase == 'free_agency':
        t['due'] = _clock(league)                        # an offer made in an open round is answered when that round closes
    else:
        t['due'] = _clock(league) + 1                    # the next advance
    # an on-the-spot yes, when there is a reason
    if t['kind'] == 'fa_offseason' and apy >= floor and not t.get('rival') and (s['loyalty'] > 0.62 or s['money'] < 0.4):
        return _accept(league, t, offer, how='signed on the spot')
    t['pending_floor'] = floor
    _say(t, 'agent', f"{p.name}'s agent will get back to you" + (f" in about {t['due'] - _clock(league)} week{'s' if t['due'] - _clock(league) != 1 else ''}." if t['kind'] == 'extension' else ' at the next step.'))
    return dict(ok=True, state='waiting', due=t['due'], line=t['log'][-1]['text'])


def _assessment(league, p, t, offer, immediate=False):
    import extensions as EXT, personality as PT, morale_system as MS
    ask = t['ask']
    if t['kind'] == 'extension':
        if 'discount' not in t:
            tm = EXT.terms(league, p, np.random.default_rng(1)) or {}
            t['discount'] = tm.get('discount', 0.0)
        disc = t['discount']
        floor = ask * (1.0 - disc)
    else:
        floor = ask * (1.0 if immediate else 0.96)
        # a Recruiter over his position: the club's money reads richer to him
        import staff as ST
        pull, _m = ST.recruit_pull(league.teams[league.user_team], p.pos)
        floor = floor / pull
    if getattr(p, 'morale', None) is not None:
        ne = MS.negotiation_effect(p.morale); floor *= 1.0 + ne['demand_premium']
        if t['kind'] == 'extension' and not ne['will_discount']:
            floor = max(floor, ask * (1.0 + ne['demand_premium']) * .98)
    # promises are worth something to him
    import negotiation_engine as NE
    for k in offer.get('promises', []):
        floor *= 1.0 - NE.PROMISES.get(k, {}).get('base', 0.0)
    import contract_offer as CO
    return CO.assess(league, p, league.teams[t['team']], offer, max(.01, floor), t['years'], t['kind'])


def _floor(league, p, t, offer, assessment=None):
    result = assessment or _assessment(league, p, t, offer)
    return float(offer['apy']) / max(.000001, result['ratio'])


def _rival_gap(league, p, t, offer):
    if not t.get('rival'): return 0.
    import market as MK
    profile = MK.profile_for(league, p, None)
    mine = MK.Offer(t['team'], p.pid, offer['apy'], offer['years'], bonus=offer.get('bonus'),
                    front_load=offer.get('front_load'), promises=offer.get('promises', ()))
    r = t['rival']
    theirs = MK.Offer(r['team'], p.pid, r['apy'], r['years'], bonus=r.get('bonus'),
                      front_load=r.get('front_load'), promises=r.get('promises', ()))
    a = MK.utility_of(league, p, mine, profile, t['ask'], t.get('years'))
    b = MK.utility_of(league, p, theirs, profile, t['ask'], t.get('years'))
    return (b - a) / max(.1, abs(b))


def _counter_package(league, p, t, offer):
    """Price the offered term/structure, or return a complete standard option."""
    import contract_offer as CO
    candidate = dict(offer)
    low, high = max(.01, candidate['bonus'] / candidate['years']), max(t['ask'] * 2, candidate['apy'])
    candidate['apy'] = high
    assessment = _assessment(league, p, t, candidate)
    if not assessment['acceptable']:
        candidate = dict(assessment['reference_package'], promises=list(offer.get('promises', [])))
        return CO.canonical(league, p, league.teams[t['team']], candidate, t['kind'])
    for _ in range(22):
        mid = (low + high) / 2; candidate['apy'] = mid
        if _assessment(league, p, t, candidate)['acceptable']: high = mid
        else: low = mid
    candidate['apy'] = math.ceil((high + .000001) * 100) / 100
    return CO.canonical(league, p, league.teams[t['team']], candidate, t['kind'])


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
        offer = t['offers'][-1]; floor = _floor(league, p, t, offer)
        out.append((t, _answer(league, t, p, offer, floor)))
    return out


def _answer(league, t, p, offer, floor, quiet=False):
    """The agent's decision on the offer in front of him: match request, yes, no, or a counter. quiet=True is the
    offseason room, where the answer is spoken in the thread and nothing goes to the inbox. Returns the state."""
    import contract_offer as CO
    offer = CO.canonical(league, p, league.teams[t['team']], offer, t['kind'])
    post = (lambda *a, **k: None) if quiet else (lambda *a, **k: _post(league, t, *a, **k))
    rival = t.get('rival')
    gap = _rival_gap(league, p, t, offer)
    if t['kind'] == 'fa_offseason' and rival and gap > 1e-9 and t['match_rounds'] < MATCH_ROUNDS and gap <= 0.12:
        t['state'] = 'match_requested'; t['counter'] = None; t['due'] = None; t['match_rounds'] += 1; _say(t, 'agent', f"He has a better offer on the table. Match it and he is yours.")
        post(f"{p.name} asks you to match", f"{league.teams[rival['team']].abbr if rival['team'] in league.teams else rival['team']} has offered ${rival['apy']:.1f}m over {rival['years']} years. He would rather be here. Match it and he signs today.",
             payload=dict(rival=rival, thread=t['id'], link=f'negotiation:{t["id"]}'))
        return 'match_requested'
    if _assessment(league, p, t, offer)['acceptable'] and gap <= .12:
        r = _accept(league, t, offer, how='agreed', quiet=quiet)
        if not r.get('ok'):
            # the agent agreed but the deal could not be written (cap, eligibility, a roster spot): the
            # thread closes with the reason instead of sitting there and failing every week
            t['state'] = 'declined'; _say(t, 'agent', f"The deal fell through: {r.get('why') or 'it could not be written'}.")
            post(f"{p.name}: the deal fell through", f"He agreed to your terms but the deal could not be written: {r.get('why') or 'it could not be written'}. Open talks again once that is fixed.")
            return 'failed'
        return r['how']
    if rival and gap > .12:
        t['state'] = 'declined'; _say(t, 'agent', 'Another club is well above you and he is going to take it.'); post(f"{p.name} says no", f"Another club is well above you and he is going to take it.")
        return 'declined'
    # a counter: toward the floor, not all the way
    t['counter'] = _counter_package(league, p, t, offer)
    counter, counter_years, counter_bonus = t['counter']['apy'], t['counter']['years'], t['counter']['bonus']
    t['state'] = 'countered'
    _say(t, 'agent', f"Close. He would do it at ${counter:.1f}m a year.")
    post(f"{p.name}'s agent counters at ${counter:.1f}m", f"Over {counter_years} year(s), keeping the offered salary structure. " + (f"Signing bonus: ${counter_bonus:.2f}m. " if counter_bonus is not None else "Signing bonus uses the standard structure. ") + ("He is close." if counter <= offer['apy'] * 1.06 else "There is a gap."),
         payload=dict(counter=t['counter'], thread=t['id'], link=f'negotiation:{t["id"]}'))
    return 'countered'


def set_rival(league, pid, team, apy, years, bonus=None, front_load=None, promises=()):
    """The market tells the thread another club is in."""
    t = open_for(league, pid, 'fa_offseason') or open_for(league, pid, 'fa_inseason')
    if t:
        import contract_offer as CO
        t['rival'] = CO.canonical(league, league.player(pid), league.teams[team],
                                  dict(team=team, apy=float(apy), years=int(years), bonus=bonus,
                                       front_load=front_load, promises=list(promises)))


def match(league, tid):
    t = find(league, tid)
    if t is None or t['state'] != 'match_requested' or not t.get('rival'): return dict(ok=False, why='nothing to match')
    r = t['rival']
    import contract_offer as CO
    r = CO.canonical(league, league.player(t['pid']), league.teams[r['team']], r)
    t['rival'] = r
    offer = dict(r, when=_clock(league), by='you (matched)')
    from offer_reservations import check_offer
    why = check_offer(league, t['team'], t, offer['apy'], offer['years'], offer['bonus'], offer['front_load'])
    if why: return dict(ok=False, why=why)
    result = _accept(league, t, offer, how='matched and signed')
    if result.get('ok'): t['offers'].append(offer)
    return result


def withdraw(league, tid):
    """You pull out: the offer on the table is rescinded and the thread closes. Works whether he is mulling it,
    has countered, or has asked you to match."""
    t = find(league, tid)
    if t is None: return dict(ok=False, why='no such negotiation')
    if t['state'] in ('accepted', 'declined', 'expired', 'broken_off'): return dict(ok=False, why=f"this negotiation is already {t['state']}")
    if t['state'] == 'match_requested' and t.get('rival'):
        import market as MK
        from cap_engine import CAP
        r = t['rival']; p = league.player(t['pid'])
        if p is None or p.team is not None or r['team'] not in league.teams:
            return dict(ok=False, why='The competing offer is no longer available.')
        offer = MK.Offer(r['team'], p.pid, r['apy'], r['years'], bonus=r.get('bonus'),
                         front_load=r.get('front_load'), promises=r.get('promises', ()))
        try:
            MK.sign(league, p, offer, CAP.get(league.year, 301.2))
            league.teams[r['team']].sync_cap()
        except ValueError as e:
            return dict(ok=False, why=f"The other team could not complete its offer: {e}")
        t['state'] = 'declined'; t['counter'] = None; t['due'] = None
        league.__dict__.setdefault('fa_signed', []).append((r['team'], p.pid, offer.apy, offer.years, getattr(league, 'fa_step', 0)))
        line = f"{p.name} signed with {r['team']} for ${offer.apy:.1f}m a year over {offer.years} years."
        _say(t, 'you', 'Declined to match.'); _say(t, 'agent', line)
        _post(league, t, f"{p.name} signs with {r['team']}", line)
        return dict(ok=True, state='declined', line=line)
    t['state'] = 'declined'; t['counter'] = None; t['due'] = None
    _say(t, 'you', 'Offer withdrawn.')
    return dict(ok=True, line='Offer withdrawn.')


def _accept(league, t, offer, how, quiet=False):
    import extensions as EXT, market as MK
    from cap_engine import CAP
    p = league.player(t['pid'])
    pay_concern_resolved = False
    if t['kind'] == 'extension':
        r = EXT.extend(league, p.pid, offer['apy'], offer['years'], front_load=offer.get('front_load'), agreed=True, bonus=offer.get('bonus'))
        if r['result'] != 'accepted':
            return dict(ok=False, why=r.get('why'))
        pay_concern_resolved = r.get('pay_concern_resolved', False)
        if getattr(p, 'fa_class', None) == 'tendered':
            # a tendered restricted free agent signing long term: the tender is replaced and he leaves the market
            p.fa_class = 'under_contract'; p.tender_team = None
            if p.pid in league.free_agents: league.free_agents.remove(p.pid)
    else:
        team = league.teams[t['team']]; cap = CAP.get(league.year, 301.2)
        o = MK.Offer(t['team'], p.pid, offer['apy'], offer['years'], promises=offer.get('promises', ()), front_load=offer.get('front_load'))
        try: MK.sign(league, p, o, cap, bonus=offer.get('bonus'), market_apy=t['ask']); team.sync_cap()
        except Exception as e: return dict(ok=False, why=str(e)[:120] or 'the contract could not be written')
    t['state'] = 'accepted'; t['counter'] = None; t['due'] = None; _say(t, 'agent', f"Done. {p.name} is signed.")
    for k in offer.get('promises', []):
        record_promise(league, p.pid, t['team'], k)
    if not quiet or pay_concern_resolved:
        body = f"{offer['years']} years at ${offer['apy']:.1f}m a year, {how}."
        if pay_concern_resolved:
            body += f" {p.name} is pleased with his new salary. His concern about being underpaid is resolved."
        _post(league, t, (f"{p.name} extended" if t['kind'] == 'extension' else f"{p.name} signs"), body)
    return dict(ok=True, state='accepted', how=how)


def _post(league, t, subject, body, payload=None):
    import inbox as IB
    user = getattr(league, 'user_team', None)
    if user and t.get('team') == user:
        pl = dict(payload or {}); pl.setdefault('thread', t['id']); pl['kind'] = t.get('kind'); pl['pid'] = t.get('pid')
        pl['link'] = f"negotiation:{t.get('kind')}:{t['id']}"
        IB.post(league, 'negotiation', subject, body, sender=league.player(t['pid']).name if league.player(t['pid']) else 'agent', payload=pl)


# ------------------------------------------------------------ the promise ledger
def record_promise(league, pid, team, kind, year=None, source=None):
    league.promises = getattr(league, 'promises', None) or []
    existing = next((pr for pr in league.promises if pr.get('status') == 'open' and pr.get('pid') == pid and pr.get('team') == team and pr.get('kind') == kind), None)
    if existing is not None: return existing
    p = league.player(pid)
    orig = (int(getattr(p.contract, 'signed', 0) or 0), int(p.contract.years)) if p is not None and p.contract is not None else None
    league.promises.append(dict(pid=pid, team=team, kind=kind, made=league.year, year=year or (league.year + 1 if kind == 'extension_by' else None), status='open', source=source, orig=orig))


def check_promises(league, week):
    """Weekly. A promise not kept is broken, with the hit the morale module defines."""
    import morale_system as MS
    broken = []
    promises = getattr(league, 'promises', None) or []
    def identity(pr):
        return (pr.get('pid'), pr.get('team'), pr.get('kind'), pr.get('made'), pr.get('year'))
    seen = {identity(pr) for pr in promises if pr.get('status') in ('kept', 'broken')}
    for pr in promises:
        if pr['status'] != 'open': continue
        key = identity(pr)
        if key in seen:
            pr['status'] = 'superseded'
            continue
        seen.add(key)
        p = league.player(pr['pid']); team = league.teams.get(pr['team'])
        if p is None or team is None:
            pr['status'] = 'void'; continue
        if p.team != pr['team']:
            # he is gone: a no-trade promise is broken by that; anything else is moot
            if pr['kind'] == 'no_trade' and not pr.get('released'): ok = False
            else: pr['status'] = 'void'; continue
        else:
            ok = None
            if pr['kind'] == 'starting_role' and week and week >= 4:
                ps = team.depth.get(p.pos, []); ok = bool(ps) and ps[0] is p
                if p.out_until is not None: ok = None                     # hurt players are not judged
            elif pr['kind'] == 'extension_by':
                cur = (int(getattr(p.contract, 'signed', 0) or 0), int(p.contract.years)) if p.contract is not None else None
                if cur is not None and cur != tuple(pr.get('orig') or ()) and cur[0] >= int(pr['made']) and cur[1] >= 2:
                    ok = True                                          # a new deal since the promise: kept
                elif league.year > (pr['year'] or 9999) or (league.year == (pr['year'] or 9999) and league.phase == 'regular'):
                    ok = False                                         # the new year came and went with no deal
            elif pr['kind'] == 'no_franchise' and getattr(p, 'tagged_year', None) == league.year:
                ok = False
            elif pr['kind'] == 'captaincy':
                if p.xp_spent.get('_captain'): ok = True
                elif league.year > int(pr['made']) and week and week >= 2: ok = False        # the season started and he is not wearing it
            elif pr['kind'] == 'no_trade' and league.year > int(pr['made']) + 1:
                ok = True                                              # a full season kept
        if ok is False:
            pr['status'] = 'broken'
            if p.morale is not None:
                p.morale.break_promise(pr['kind'])
            league.log('promise_broken', pid=p.pid, team=pr['team'], promise=pr['kind'])
            broken.append(pr)
            _promise_words(league, p, pr, kept=False)
        elif ok is True and (pr['kind'] != 'starting_role' or (week and week >= 8)):
            pr['status'] = 'kept'
            if p.morale is not None:
                try: p.morale.apply('promise_kept')
                except Exception: pass
            league.log('promise_kept', pid=p.pid, team=pr['team'], promise=pr['kind'])
            _promise_words(league, p, pr, kept=True)
    return broken


def _promise_words(league, p, pr, kept):
    """What he says when a promise is kept or broken, in the inbox, in his own words, for the user's club only."""
    import inbox as IB
    from views import surname
    user = getattr(league, 'user_team', None)
    if not user or pr['team'] != user: return
    when = f"in January" if pr.get('source') == 'exit' else "when we talked"
    KEPT = {'starting_role': f"You told me {when} the job was mine to win. I won it, and you kept your word. That matters in here.",
            'extension_by': f"You said {when} we would get it done before the market, and we did. I'm here, and I'm all in.",
            'captaincy': f"You said {when} I would wear the C. I do. Thank you for that.",
            'no_trade': f"You told me {when} I wasn't going anywhere, and the season came and went and I'm still here. I remember that.",
            'no_franchise': f"You said you wouldn't tag me, and you didn't. I'll take that into the next talk."}
    BROKEN = {'starting_role': f"You told me {when} the job was mine to win. It wasn't, was it. I'll play, but I heard what I heard.",
              'extension_by': f"You said {when} we would have a deal before the market. It's the new year and my agent hasn't had a real number from you. I'm done waiting.",
              'captaincy': f"You told me {when} I'd wear the C. Somebody else is wearing it. Don't tell me things in that office you don't mean.",
              'no_trade': f"You looked me in the eye {when} and said I wasn't going anywhere. Then you traded me. Everybody in that locker room knows now what your word is worth.",
              'no_franchise': f"You said no tag. Then you tagged me. We'll talk through my agent from here."}
    words = (KEPT if kept else BROKEN).get(pr['kind'])
    if not words: return
    IB.post(league, 'club', f"{inbox_player(p)}: {'a promise kept' if kept else 'a promise broken'}", f'"{words}"', sender=surname(p.name), payload=dict(pid=p.pid, link='club:player:' + p.pid))


def ledger(league, team=None):
    return [pr for pr in (getattr(league, 'promises', None) or []) if team is None or pr['team'] == team]

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
        tm = EXT.terms(league, p, np.random.default_rng(stable_seed(pid)))
        if tm is None:
            return dict(ok=False, why='no market read on him')
        # an agent can decline to talk in season: a star in his final year who is playing well wants the leverage
        if s['in_season'] and s['star'] and s['final_year'] and s['money'] > 0.55 and s['morale'] >= 40 and (stable_seed(pid) % 100) < 60:
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
    if kind == 'fa_offseason':
        # a round is open: the agent tells you who else is in, and how much
        bids = (getattr(league, 'fa_bids', None) or {}).get(pid) or []
        if bids:
            best = max(bids, key=lambda b: b['apy'])
            set_rival(league, pid, best['team'], best['apy'], best['years'])
            line += f" {len(bids)} other club{'s' if len(bids) != 1 else ''} {'are' if len(bids) != 1 else 'is'} in on him."
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
    room = (t['kind'] == 'extension' and not s['in_season'])      # the offseason room: he answers here, and a walk is a walk
    # an insult ends it
    if apy < INSULT * ask:
        if room:
            t['state'] = 'declined'; _say(t, 'agent', f"That is an insult. ${apy:.1f}m against ${ask:.1f}m is not a negotiation. He will test the market.")
            return dict(ok=True, state='declined', line=t['log'][-1]['text'])
        t['state'] = 'broken_off'; t['broken_until'] = _clock(league) + BREAK_WEEKS; _say(t, 'agent', 'That is an insult. We are done talking for now.')
        _post(league, t, f"{p.name}'s agent has ended talks", f"An offer of ${apy:.1f}m against an ask of ${ask:.1f}m is not a negotiation. He will not take your calls for {BREAK_WEEKS} weeks.")
        return dict(ok=True, state='broken_off')
    # a lowball spends patience
    if apy < LOWBALL * ask:
        t['patience'] -= 1
        if t['patience'] <= 0:
            if room:
                t['state'] = 'declined'; _say(t, 'agent', 'You keep coming in low. He is done here and will see what the market says.')
                return dict(ok=True, state='declined', line=t['log'][-1]['text'])
            t['state'] = 'broken_off'; t['broken_until'] = _clock(league) + 30; _say(t, 'agent', 'You keep coming in low. He is going to look elsewhere.')
            _post(league, t, f"{p.name}'s agent is done for now", "Three offers under the market. They will revisit it in the offseason.")
            return dict(ok=True, state='broken_off')
    # what he will take, shape and loyalty and morale included (extensions.py knows the floor logic)
    floor = _floor(league, p, t, offer)
    # HIS OWN NUMBER IS A YES. An offer that meets the agent's standing counter (his money and his years) is the
    # deal he asked for: it is signed on the spot, whatever the kind of talk or the time of year. It had gone back
    # into the queue as a fresh offer and the agent took a week to say yes to his own terms.
    c = t.get('counter')
    if c and apy + 1e-9 >= float(c.get('apy', apy)) and int(years) == int(c.get('years', years)):
        return _accept(league, t, offer, how='counter accepted')
    if sign_today and t['kind'] == 'fa_inseason':
        # today means the ask, no discount; and another club may already have him
        if apy + 1e-9 >= ask and not t.get('rival'):
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
        out.append((t, _answer(league, t, p, offer, floor)))
    return out


def _answer(league, t, p, offer, floor, quiet=False):
    """The agent's decision on the offer in front of him: match request, yes, no, or a counter. quiet=True is the
    offseason room, where the answer is spoken in the thread and nothing goes to the inbox. Returns the state."""
    post = (lambda *a, **k: None) if quiet else (lambda *a, **k: _post(league, t, *a, **k))
    rival = t.get('rival')
    if t['kind'] == 'fa_offseason' and rival and rival['apy'] > offer['apy'] and t['match_rounds'] < MATCH_ROUNDS \
            and (rival['apy'] - offer['apy']) / rival['apy'] <= 0.12:
        t['state'] = 'match_requested'; t['match_rounds'] += 1; _say(t, 'agent', f"He has a better offer on the table. Match it and he is yours.")
        post(f"{p.name} asks you to match", f"{league.teams[rival['team']].abbr if rival['team'] in league.teams else rival['team']} has offered ${rival['apy']:.1f}m over {rival['years']} years. He would rather be here. Match it and he signs today.",
             payload=dict(rival=rival, thread=t['id'], link=f'negotiation:{t["id"]}'))
        return 'match_requested'
    if offer['apy'] + 1e-9 >= floor and not (rival and rival['apy'] > offer['apy'] * 1.12):
        r = _accept(league, t, offer, how='agreed', quiet=quiet)
        if not r.get('ok'):
            # the agent agreed but the deal could not be written (cap, eligibility, a roster spot): the
            # thread closes with the reason instead of sitting there and failing every week
            t['state'] = 'declined'; _say(t, 'agent', f"The deal fell through: {r.get('why') or 'it could not be written'}.")
            post(f"{p.name}: the deal fell through", f"He agreed to your terms but the deal could not be written: {r.get('why') or 'it could not be written'}. Open talks again once that is fixed.")
            return 'failed'
        return r['how']
    if rival and rival['apy'] > offer['apy'] * 1.12:
        t['state'] = 'declined'; _say(t, 'agent', 'Another club is well above you and he is going to take it.'); post(f"{p.name} says no", f"Another club is well above you and he is going to take it.")
        return 'declined'
    # a counter: toward the floor, not all the way
    counter = round(min(t['ask'], floor * (1.0 + 0.03 * max(0, t['patience'] - 1))), 2)    # never above his own ask
    t['state'] = 'countered'; t['counter'] = dict(apy=counter, years=t['years'], front_load=0.5); _say(t, 'agent', f"Close. He would do it at ${counter:.1f}m a year.")
    post(f"{p.name}'s agent counters at ${counter:.1f}m", f"Over {t['years']} years at the league shape. " + ("He is close." if counter <= offer['apy'] * 1.06 else "There is a gap."),
         payload=dict(counter=t['counter'], thread=t['id'], link=f'negotiation:{t["id"]}'))
    return 'countered'


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
    """You pull out: the offer on the table is rescinded and the thread closes. Works whether he is mulling it,
    has countered, or has asked you to match."""
    t = find(league, tid)
    if t is None: return dict(ok=False, why='no such negotiation')
    if t['state'] in ('accepted', 'declined', 'expired', 'broken_off'): return dict(ok=False, why=f"this negotiation is already {t['state']}")
    t['state'] = 'declined'; t['counter'] = None; t['due'] = None
    _say(t, 'you', 'Offer withdrawn.')
    return dict(ok=True, line='Offer withdrawn.')


def _accept(league, t, offer, how, quiet=False):
    import extensions as EXT, market as MK
    from cap_engine import CAP
    p = league.player(t['pid'])
    if t['kind'] == 'extension':
        r = EXT.extend(league, p.pid, offer['apy'], offer['years'], front_load=offer.get('front_load'), agreed=True)
        if r['result'] != 'accepted':
            return dict(ok=False, why=r.get('why'))
        if getattr(p, 'fa_class', None) == 'tendered':
            # a tendered restricted free agent signing long term: the tender is replaced and he leaves the market
            p.fa_class = 'under_contract'; p.tender_team = None
            if p.pid in league.free_agents: league.free_agents.remove(p.pid)
    else:
        team = league.teams[t['team']]; cap = CAP.get(league.year, 301.2)
        o = MK.Offer(t['team'], p.pid, offer['apy'], offer['years'], promises=offer.get('promises', ()), front_load=offer.get('front_load'))
        try: MK.sign(league, p, o, cap); team.sync_cap()
        except Exception as e: return dict(ok=False, why=str(e)[:120] or 'the contract could not be written')
    t['state'] = 'accepted'; _say(t, 'agent', f"Done. {p.name} is signed.")
    for k in offer.get('promises', []):
        record_promise(league, p.pid, t['team'], k)
    if not quiet: _post(league, t, (f"{p.name} extended" if t['kind'] == 'extension' else f"{p.name} signs"), f"{offer['years']} years at ${offer['apy']:.1f}m a year, {how}.")
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
    p = league.player(pid)
    orig = (int(getattr(p.contract, 'signed', 0) or 0), int(p.contract.years)) if p is not None and p.contract is not None else None
    league.promises.append(dict(pid=pid, team=team, kind=kind, made=league.year, year=year or (league.year + 1 if kind == 'extension_by' else None), status='open', source=source, orig=orig))


def check_promises(league, week):
    """Weekly. A promise not kept is broken, with the hit the morale module defines."""
    import morale_system as MS
    broken = []
    for pr in getattr(league, 'promises', None) or []:
        if pr['status'] != 'open': continue
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
    IB.post(league, 'club', f"{p.name}: {'a promise kept' if kept else 'a promise broken'}", f'"{words}"', sender=surname(p.name), payload=dict(pid=p.pid, link='club:player:' + p.pid))


def ledger(league, team=None):
    return [pr for pr in (getattr(league, 'promises', None) or []) if team is None or pr['team'] == team]

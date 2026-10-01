"""Periodic, optional staff acquisition reports. Never make a roster move.

Only the weekly roll writes reports. Reads and candidate assessment use no live
random stream. The small history lives in notes_sent, already saved by League.
"""
import copy
import numpy as np
import roster_needs as RN
import practice_squad as PS
import waivers as WV
import cap_accounting as CA
from cap_engine import CAP, Contract
from stable import stable_seed

OFFENSE = {'QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT'}
DEV = {'star': 'Rare', 'superstar': 'Epic', 'xfactor': 'Legendary'}


def _tick(league, week):
    return int(league.year) * 32 + int(week)


def _state(league):
    if getattr(league, 'notes_sent', None) is None:
        league.notes_sent = {}
    return league.notes_sent.setdefault('_roster_advisor', {}).setdefault(
        league.user_team, {'last': None, 'next': None, 'seen': {}})


def _healthy(p):
    return not p.retired and p.out_until is None


def _grade(league, team, p):
    # This is the same rating/fit visible in roster and player-card views.
    import gm_engine as GE
    return PS.view_ovr(league, team.abbr, p) + GE.scheme_fit(p.ratings, p.pos, team)


def _copy_team(team):
    out = copy.copy(team)
    out.cap = copy.deepcopy(team.cap)
    return out


def _terms(league, team, p, source, pool):
    """Price the route the user's actual action uses, without opening talks."""
    import valuation as VAL, staff as ST, min_salary as MS, market as MK
    if source == 'waiver':
        c = WV.claim_contract(league, p, team.abbr)
        order = WV.priority(league, league.week)
        rank = order.index(team.abbr)+1 if team.abbr in order else '?'
        return c, f'Inherited cap charge: ${c.cap_hit(0):.2f}m this season. Claim before Advance; priority {rank}. A higher-priority claim can win.'
    if source == 'trade':
        if not p.contract or p.contract.years < 1:
            return None, ''
        c = CA.transfer_contract(p.contract, team.cap.paid_week)
        return c, f'Inherited cap charge: ${c.cap_hit(0):.2f}m; {c.years} year(s) left.'
    v = VAL.value_player(league, p, side='agent', pool=pool, rng=None)
    if not v:
        return None, ''
    _, mult = ST.recruit_pull(team, p.pos)
    annual = max(MS.minimum_salary(p.accrued or 0, CAP.get(league.year, 301.2)),
                 round(v['apy'] * mult, 2))
    terms = MK.signing_terms(league, p, team, annual, 1, CAP.get(league.year, 301.2))
    c = Contract(1, terms['base'], signing_bonus=terms['signing_bonus'],
                 signed=league.year, pay_start=team.cap.paid_week)
    line = f'Estimated one-year ask: ${annual:.2f}m annual rate, about ${c.cap_hit(0):.2f}m remaining cap charge including bonus. Terms require negotiation.'
    if source == 'ps':
        line += ' Must join the active roster and stay for three games.'
    return c, line


def _trade_offer(league, team, p, pool, week):
    """A plausible single-pick offer, through the existing two-sided evaluator."""
    import trades as TR, trade_engine as TE
    if week > TR.TRADE_DEADLINE_WEEK or p.team not in league.teams:
        return None
    seller = league.teams[p.team]
    if PS.protected(seller, p, league):
        return None
    healthy = [q for q in seller.active() if _healthy(q)]
    # Never suggest stripping a seller of an actual starting assignment.
    before = RN.assess(seller, healthy, strict_roles=True)
    if any(a['player'] is p for a in before['assignments']):
        return None
    after = RN.assess(seller, [q for q in healthy if q.pid != p.pid], strict_roles=True)
    if after['uncovered'] != before['uncovered'] or before['score']-after['score'] > 6:
        return None
    rng = np.random.default_rng(stable_seed(('roster-advisor', league.year, week, p.pid)))
    asset = TR.player_asset(league, seller, p, pool, rng, viewer=team)
    if not asset:
        return None
    # Seller cap consequences are tested too, using an isolated cap ledger.
    shadow = copy.copy(league)
    shadow.teams = dict(league.teams, **{seller.abbr: _copy_team(seller)})
    trial = CA.trade_projection(shadow, seller.abbr, [p.pid], [])
    if trial.charges(seller.phase) > trial.limit and trial.charges(seller.phase) > shadow.teams[seller.abbr].cap.charges(seller.phase)+.0005:
        return None
    picks = [pk for pk in team.picks if not pk.used_on and pk.owner == team.abbr
             and league.year <= pk.year <= league.year+1 and pk.round >= 3]
    picks.sort(key=lambda pk: (-pk.round, -pk.year))
    for pk in picks:
        offer = TE.evaluate(dict(a_sends=[TR.pick_asset(league, pk)], a_gets=[asset]),
                            team.ctx(), seller.ctx(), team.cap_space, seller.cap_space,
                            TR.persona(team.gm), TR.persona(seller.gm))
        if offer.get('accepted') and not offer.get('blocked'):
            return dict(id=f'{pk.year}-{pk.round}-{pk.original}',
                        label=f'{pk.year+1} round {pk.round} pick ({pk.original})')
    return None


def candidates(league, week):
    """Rank actionable improvements; max one recommendation per position."""
    import valuation as VAL
    team = league.teams[league.user_team]
    active = list(team.active())
    healthy = [p for p in active if _healthy(p)]
    full = list({p.pid: p for p in active + list(getattr(team, 'ir', []) or [])}.values())
    report = RN.assess(team, healthy, strict_roles=True)
    full_report = RN.assess(team, full, strict_roles=True)
    own_ps = [p for p in PS.squad(team) if _healthy(p)]
    wire = {e['pid']: e for e in WV.pending(league) if e.get('from_team') != team.abbr}
    pool = VAL.pool_from_league(league)
    options = [(league.player(pid), 'fa') for pid in league.free_agents if pid not in wire]
    options += [(league.player(pid), 'waiver') for pid in wire]
    for other in league.teams.values():
        if other.abbr == team.abbr:
            continue
        options += [(p, 'ps') for p in PS.squad(other)]
        if week <= __import__('trades').TRADE_DEADLINE_WEEK:
            options += [(p, 'trade') for p in other.active()]
    ranked = []
    in_talks = {t['pid'] for t in (getattr(league, 'negotiations', None) or [])
                if t.get('team') == team.abbr and t.get('state') in ('open', 'waiting', 'countered', 'accepted', 'broken_off')}
    for p, source in options:
        if p is None or not _healthy(p) or p.team == team.abbr or PS.shunned(p, team.abbr, league):
            continue
        if p.pid in in_talks or (source == 'waiver' and team.abbr in wire[p.pid].get('claims', [])):
            continue
        if source == 'fa' and p.team is not None:
            continue
        if source == 'trade' and PS.locked(p, week):
            continue
        grade = _grade(league, team, p)
        same = [q for q in healthy if q.pos == p.pos]
        internal = [q for q in own_ps if q.pos == p.pos]
        best_internal = max(internal, key=lambda q: _grade(league, team, q), default=None)
        if best_internal and _grade(league, team, best_internal) >= grade-2:
            continue
        need = report['needs'].get(p.pos, 0)
        dev = DEV.get(str(p.dev).lower())  # public development tier; no hidden ceiling
        young = bool(dev and p.age <= 25)
        worst = min((_grade(league, team, q) for q in same), default=55)
        best = max((_grade(league, team, q) for q in same), default=55)
        if need < .25 and not (young and grade >= worst+2) and grade < best+4:
            continue
        if grade < max(65, worst+2) and not (need >= .9 and grade >= 60):
            continue
        injured = [q for q in full if q.pos == p.pos and not _healthy(q)]
        short = bool(injured and all(isinstance(q.out_until, (int, float)) and q.out_until <= week+2 for q in injured))
        # A rental for an imminent return must be cheap, and never costs a pick.
        if short and source == 'trade':
            continue
        outgoing = PS.room_candidate(league, team, p) if len(active) >= 53 else None
        if len(active) >= 53 and outgoing is None:
            continue
        after = RN.assess(team, [q for q in healthy if q is not outgoing]+[p], strict_roles=True)
        gain = after['score']-report['score']
        if gain < 2 and not (young and grade >= worst+3 and gain >= 0):
            continue
        if any(role not in report['uncovered'] for role in after['uncovered']):
            continue
        c, cost_line = _terms(league, team, p, source, pool)
        if c is None:
            continue
        if need < .25 and not role_improvement(report, after, p) and c.cap_hit(0) > .02*team.cap.limit:
            continue  # Do not spend starter money on a development-only addition.
        if short and c.cap_hit(0) > 2*max(.1, (18-team.cap.paid_week)/18):
            continue
        try:
            CA.require_room(league, _copy_team(team), p.pid, c,
                            release_pid=outgoing.pid if outgoing else None)
        except ValueError:
            continue
        # Protect the healthy roster the club expects to have when injuries clear.
        full_after = RN.assess(team, [q for q in full if q is not outgoing]+[p], strict_roles=True)
        if full_after['score'] < full_report['score']-2:
            continue
        pick = _trade_offer(league, team, p, pool, week) if source == 'trade' else None
        if source == 'trade' and not pick:
            continue
        if injured:
            reason = f"{', '.join(q.name for q in injured[:2])} unavailable at {p.pos}. "
            reason += 'Short-term cover; reassess when he returns.' if short else 'Adds cover while the injured players recover.'
        elif young:
            reason = f'{dev} development at age {int(p.age)}; a development option in our {p.pos} room.'
            incumbent = max((q for q in full if q.pos == p.pos), key=lambda q: q.ovr, default=None)
            if incumbent and (incumbent.age >= 30 or (incumbent.contract and incumbent.contract.years == 1)):
                reason += f' Succession option behind {incumbent.name}, age {int(incumbent.age)}' + (' and in his final contract year.' if incumbent.contract and incumbent.contract.years == 1 else '.')
        else:
            reason = f'Our coach’s personnel needs more quality or healthy depth at {p.pos}.'
        role = next((a['role'] for a in after['assignments'] if a['player'] is p), None)
        reason += f' Projects as {role or "a depth option"}; scheme-adjusted grade {grade:.1f}.'
        if best_internal:
            reason += f' Internal alternative: {best_internal.name} ({_grade(league, team, best_internal):.1f}).'
        if outgoing:
            cost_line += f' Roster is full: review releasing {outgoing.name}; no release is automatic from this report.'
        if pick:
            cost_line += f' Starting trade proposal: our {pick["label"]}. Recheck before offering.'
        context = [source, p.team, sorted(q.pid for q in injured), role, round(grade/3)]
        ranked.append(dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(PS.view_ovr(league, team.abbr, p)),
                           dev=dev, source=source, owner=p.team, reason=reason, cost=cost_line,
                           pick=pick, release=outgoing.pid if outgoing else None, context=context,
                           score=round(gain+need*5+(3 if young else 0)-(3 if source == 'trade' else 0), 2),
                           urgent=source == 'waiver' or bool(injured and gain >= 8)))
    return sorted(ranked, key=lambda r: (-r['score'], r['pid']))


def role_improvement(before, after, p):
    old = {a['role']: a for a in before['assignments']}
    return any(a['player'] is p and (old[a['role']]['grade'] is None or
               a['grade'] >= old[a['role']]['grade']+3) for a in after['assignments'])


def weekly(league, week):
    """Called after the completed week's transactions; advice is for next week."""
    if league.phase != 'regular' or not getattr(league, 'user_team', None) or not 1 <= week < 18:
        return None
    target = week+1
    now = _tick(league, target)
    state = _state(league)
    if state.get('checked', -1) >= now:
        return None
    state['seen'] = {pid: v for pid, v in state['seen'].items() if now-v['tick'] < 32}
    due = state['next'] is None or now >= state['next']
    rows, positions = [], set()
    for r in candidates(league, target):
        old = state['seen'].get(r['pid'])
        if old and now-old['tick'] < 6 and old['context'] == r['context']:
            continue
        if not due and not r['urgent']:
            continue
        if r['pos'] in positions:
            continue
        positions.add(r['pos']); rows.append(r)
        if len(rows) == 3:
            break
    state['checked'] = now
    if not rows:
        return None  # Do not invent a signing simply to fill an email.
    import inbox as IB
    team = league.teams[league.user_team]
    sides = {'st' if r['pos'] in ('K', 'P', 'LS') else 'oc' if r['pos'] in OFFENSE else 'dc' for r in rows}
    role = next(iter(sides)) if len(sides) == 1 else 'hc'
    coach = team.gm if role == 'hc' else (getattr(team, 'staff', {}) or {}).get(role)
    sender = getattr(coach, 'name', None) or {'oc': 'Offensive Coordinator', 'dc': 'Defensive Coordinator', 'st': 'Special Teams Coordinator', 'hc': 'Coaching Staff'}[role]
    body = 'We reviewed the active roster, injured players, our practice squad and the available market. These are the moves worth reviewing; no move has been made.'
    msg = IB.post(league, 'roster_report', f'Roster recommendations · Week {target}', body,
                  sender=sender, payload=dict(recommendations=rows, report_week=target), expires_week=target+3)
    msg['week'] = target
    for r in rows:
        state['seen'][r['pid']] = dict(tick=now, context=r['context'])
        if r['source'] == 'waiver':
            for entry in WV.pending(league):
                if entry['pid'] == r['pid']:
                    entry['user_notified'] = True
            # Consolidate only availability notices for this still-pending player.
            league.inbox[:] = [m for m in league.inbox if not (
                m.get('kind') == 'waiver_notice' and m.get('subject', '').startswith('Available on waivers:')
                and (m.get('payload') or {}).get('pid') == r['pid'] and m.get('status') in ('unread', 'open'))]
    state['last'] = now
    if due:
        state['next'] = now + (2 if any(r['urgent'] for r in rows) else 3 if any(r['score'] >= 8 for r in rows) else 4)
    return msg


def recommendations(league, message):
    """Read-only live availability; old emails never promise an expired target."""
    rows = []
    for saved in (message.get('payload') or {}).get('recommendations', []):
        row = dict(saved)
        p = league.player(row['pid'])
        available = p is not None and _healthy(p) and message.get('year') == league.year and league.phase == 'regular'
        if available:
            if row['source'] == 'fa':
                available = p.team is None and p.pid in league.free_agents and not any(e['pid'] == p.pid for e in WV.pending(league))
            elif row['source'] == 'waiver':
                available = any(e['pid'] == p.pid for e in WV.pending(league))
            elif row['source'] == 'ps':
                available = p.team == row['owner'] and p.team in league.teams and p in PS.squad(league.teams[p.team])
            else:
                import trades as TR
                available = p.team == row['owner'] and league.phase == 'regular' and (league.week or 0) <= TR.TRADE_DEADLINE_WEEK
        row['available'] = bool(available and not row.get('dismissed') and message.get('status') != 'expired')
        row['status'] = 'Dismissed' if row.get('dismissed') else 'Review opportunity' if row['available'] else 'No longer available'
        rows.append(row)
    return rows


def dismiss(league, mid, pid):
    m = next((m for m in league.inbox if m['id'] == int(mid) and m.get('kind') == 'roster_report'), None)
    if m:
        for r in m['payload']['recommendations']:
            if r['pid'] == pid:
                r['dismissed'] = True
                _state(league)['seen'][pid] = dict(tick=_tick(league, max(league.week or 1, m['payload'].get('report_week', 1))), context=r['context'])
                return dict(ok=True, line='Recommendation dismissed.')
    return dict(ok=False, why='Recommendation no longer exists.')

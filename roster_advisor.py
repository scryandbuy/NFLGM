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
import valuation as VAL
from cap_engine import CAP, Contract
from stable import stable_seed

OFFENSE = {'QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT'}
DEV = {'star': 'Rare', 'superstar': 'Epic', 'xfactor': 'Legendary'}
DEV_RANK = {'normal': 0, 'star': 1, 'superstar': 2, 'xfactor': 3}


def development_case(league, team, target, room):
    """A future role must be unfilled; public development alone is not a need."""
    tier = DEV_RANK.get(str(target.dev).lower(), 0)
    if target.age > 25 or not tier:
        return None
    room = [q for q in room if q.pos == target.pos and not q.retired]
    grade = _grade(league, team, target)
    prospects = [q for q in room if q.age <= 25 and DEV_RANK.get(str(q.dev).lower(), 0)]
    # Existing younger talent gets time to develop, including injured/PS players.
    if any(DEV_RANK.get(str(q.dev).lower(), 0) >= tier and q.age <= target.age+1
           and _grade(league, team, q) >= grade-5 for q in prospects):
        return None
    starter = max(room, key=lambda q: _grade(league, team, q), default=None)
    if starter and (starter.age >= (33 if target.pos == 'QB' else 29)
                    or (starter.contract and starter.contract.years == 1)):
        if not prospects and grade >= _grade(league, team, starter)-6:
            return f'Unfilled succession need behind {starter.name}.'
    # Exceptional prospects need a plausible rotation role, not another stash.
    if tier >= 2 and not any(DEV_RANK.get(str(q.dev).lower(), 0) >= tier for q in prospects):
        ordered = sorted((_grade(league, team, q) for q in room), reverse=True)
        if grade >= (ordered[1] if len(ordered)>1 else ordered[0] if ordered else 65):
            return 'Exceptional development prospect with a path into the rotation.'
    return None


def investment_hurdle(source, contract, pick, cap_limit):
    """A pick and a short contract require more immediate roster benefit."""
    if source != 'trade': return 2.0
    rnd = int(pick.get('round', 3))
    return ({3:8, 4:6, 5:4, 6:3, 7:2}.get(rnd, 10)
            + (4 if contract.years <= 1 else 0)
            + max(0, contract.cap_hit(0)/max(1, cap_limit)*100-1))


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
    line = f'Estimated remaining cap cost: ${c.cap_hit(0):.2f}m.'
    return c, line


def _seller_read(seller, assessments):
    if assessments is not None and seller.abbr in assessments:
        return assessments[seller.abbr]
    healthy = [q for q in seller.active() if _healthy(q)]
    prepared = RN.assessment_inputs(seller, healthy)
    before = RN.assess(seller, healthy, strict_roles=True, prepared=prepared)
    result = (healthy, prepared, before)
    if assessments is not None:
        assessments[seller.abbr] = result
    return result


def _trade_offer(league, team, p, pool, week, *, assessments=None):
    """A plausible single-pick offer, through the existing two-sided evaluator."""
    import trades as TR, trade_engine as TE
    if week > TR.TRADE_DEADLINE_WEEK or p.team not in league.teams:
        return None
    seller = league.teams[p.team]
    if PS.protected(seller, p, league):
        return None
    healthy, prepared, before = _seller_read(seller, assessments)
    # Never suggest stripping a seller of an actual starting assignment.
    if any(a['player'] is p for a in before['assignments']):
        return None
    after = RN.assess(seller, [q for q in healthy if q.pid != p.pid], strict_roles=True, prepared=prepared)
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
            return dict(id=f'{pk.year}-{pk.round}-{pk.original}', round=pk.round,
                        label=f'{pk.year+1} round {pk.round} pick ({pk.original})')
    return None


def performance_case(league, team, p, comparator, internal):
    """A measured recent weakness plus a credible, attribute-specific role."""
    if comparator is None: return None
    recent = sorted((g for g in league.schedule if 1 <= g[0] <= 18 and g[3] is not None
                     and team.abbr in (g[1], g[2])), reverse=True)[:4]
    own, opponents = [], []
    for wk, away, home, ap, hp in recent:
        game = (getattr(league, 'team_game_stats', {}) or {}).get(f'{league.year}-{wk}-{home}-{away}', {})
        other = away if home == team.abbr else home
        if 'dropbacks' in game.get(team.abbr, {}) and 'dropbacks' in game.get(other, {}):
            own.append(game[team.abbr]); opponents.append(game[other])
    if len(own) < 3: return None
    total = lambda rows, key: sum(r.get(key, 0) for r in rows)
    cases = []
    if p.pos in ('LT','LG','C','RG','RT') and total(own,'dropbacks') >= 60 and total(own,'sacks') / total(own,'dropbacks') >= .08:
        cases.append(('pass protection', 'pass_block_rating'))
    if p.pos in ('DT','LEDG','REDG') and total(opponents,'dropbacks') >= 60 and total(opponents,'pressures') / total(opponents,'dropbacks') < .18:
        cases.extend([('pass rush','power_moves_rating'),('pass rush','finesse_moves_rating')])
    if p.pos in ('DT','LEDG','REDG','MIKE','WILL','SAM') and total(opponents,'designed_runs') >= 40 and total(opponents,'designed_run_yards') / total(opponents,'designed_runs') >= 5:
        cases.append(('run defense','block_shed_rating'))
    for area, attr in cases:
        value = p.ratings.get(attr)
        old = comparator.ratings.get(attr)
        if value is None or old is None or value < 80 or value < old + 8: continue
        if any(q.pos == p.pos and q.ratings.get(attr, 0) >= value - 3
               and _grade(league,team,q) >= _grade(league,team,p)-3 for q in internal): continue
        if _grade(league,team,p) < _grade(league,team,comparator)-3: continue
        skill = attr.replace('_rating','').replace('_',' ')
        return f'Our {area} has struggled over {len(own)} recent games. His {skill} ({round(value)}) could improve the {p.pos} rotation over {comparator.name}.'
    return None


def acquisition_case(league, team, p, report, after, healthy, injured, own_ps, future_case):
    """Compare the actual assignment, or the first useful reserve, not the weakest stash."""
    for index, assignment in enumerate(after['assignments']):
        if assignment['player'] is not p: continue
        old = report['assignments'][index]
        if old['player'] is None:
            return f'Fills the uncovered {assignment["role"]} role.', None
        if assignment['grade'] >= old['grade'] + 3:
            return f'Could improve {assignment["role"]} over {old["player"].name}.', old['player']
    room = sorted([q for q in healthy if q.pos == p.pos],key=lambda q:-_grade(league,team,q))
    starters = sum(a['player'] is not None and a['player'].pos == p.pos for a in report['assignments'])
    # Reserve jobs must be near the rotation; improving a fourth-stringer is insufficient.
    index = max(0, starters if p.pos in ('DT','LEDG','REDG','WR','CB') else min(starters,1))
    comparator = room[min(index,len(room)-1)] if room else None
    special = performance_case(league,team,p,comparator,own_ps)
    if special: return special, comparator
    if injured and (comparator is None or _grade(league,team,p) >= _grade(league,team,comparator)+3):
        return f'Adds {p.pos} cover while {injured[0].name} is unavailable.', comparator
    if future_case: return future_case, comparator
    if comparator and comparator.age <= 25 and comparator.contract and comparator.contract.years >= 2:
        if DEV_RANK.get(str(comparator.dev).lower(),0) >= max(1,DEV_RANK.get(str(p.dev).lower(),0)):
            return None, comparator  # Preserve an established development path.
    if comparator and _grade(league,team,p) >= _grade(league,team,comparator)+4:
        return f'Could strengthen the {p.pos} rotation over {comparator.name}.', comparator
    return None, comparator


@VAL.comparison_batch()
def candidates(league, week):
    """Rank actionable improvements; max one recommendation per position."""
    import valuation as VAL
    team = league.teams[league.user_team]
    active = list(team.active())
    healthy = [p for p in active if _healthy(p)]
    full = list({p.pid: p for p in active + list(getattr(team, 'ir', []) or [])}.values())
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
    # This entire search only reads the league. Reuse fixed coach/player
    # inputs, but assign every hypothetical lineup and price each acquisition.
    prepared = RN.assessment_inputs(team, full + own_ps + [p for p, _ in options if p is not None])
    report = RN.assess(team, healthy, strict_roles=True, prepared=prepared)
    full_report = RN.assess(team, full, strict_roles=True, prepared=prepared)
    room = PS.room_review(league, team) if len(active) >= 53 else None
    sellers = {}
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
        if source == 'trade':
            seller = league.teams[p.team]
            # These same hard refusals already apply in _trade_offer. Check
            # before pricing a hypothetical release on our own full roster.
            if PS.protected(seller, p, league):
                continue
            _, _, seller_report = _seller_read(seller, sellers)
            if any(a['player'] is p for a in seller_report['assignments']):
                continue
        grade = _grade(league, team, p)
        internal = [q for q in own_ps if q.pos == p.pos]
        best_internal = max(internal, key=lambda q: _grade(league, team, q), default=None)
        if best_internal and _grade(league, team, best_internal) >= grade-2:
            continue
        need = report['needs'].get(p.pos, 0)
        dev = DEV.get(str(p.dev).lower())  # public development tier; no hidden ceiling
        if grade < 65 and not (need >= .9 and grade >= 60):
            continue
        injured = [q for q in full if q.pos == p.pos and not _healthy(q)]
        short = bool(injured and all(isinstance(q.out_until, (int, float)) and q.out_until <= week+2 for q in injured))
        # A rental for an imminent return must be cheap, and never costs a pick.
        if short and source == 'trade':
            continue
        outgoing = PS.room_candidate(league, team, p, review=room) if len(active) >= 53 else None
        if len(active) >= 53 and outgoing is None:
            continue
        after = RN.assess(team, [q for q in healthy if q is not outgoing]+[p], strict_roles=True, prepared=prepared)
        gain = after['score']-report['score']
        future_case = development_case(league, team, p, full + own_ps)
        reason, comparator = acquisition_case(league, team, p, report, after, healthy, injured, own_ps, future_case)
        if not reason or gain < 0:
            continue
        if outgoing and outgoing.age <= 25 and DEV_RANK.get(str(outgoing.dev).lower(), 0):
            # Do not discard controlled young talent for a marginal acquisition.
            if (DEV_RANK.get(str(outgoing.dev).lower(), 0) >= DEV_RANK.get(str(p.dev).lower(), 0)
                    and outgoing.age <= p.age and outgoing.contract
                    and gain < 8):
                continue
        if any(role not in report['uncovered'] for role in after['uncovered']):
            continue
        c, cost_line = _terms(league, team, p, source, pool)
        if c is None:
            continue
        if not role_improvement(report, after, p) and c.cap_hit(0) > .01*team.cap.limit:
            continue  # Do not spend starter money on a development-only addition.
        if short and c.cap_hit(0) > 2*max(.1, (18-team.cap.paid_week)/18):
            continue
        try:
            CA.require_room(league, _copy_team(team), p.pid, c,
                            release_pid=outgoing.pid if outgoing else None)
        except ValueError:
            continue
        # Protect the healthy roster the club expects to have when injuries clear.
        full_after = RN.assess(team, [q for q in full if q is not outgoing]+[p], strict_roles=True, prepared=prepared)
        if full_after['score'] < full_report['score']-2:
            continue
        pick = _trade_offer(league, team, p, pool, week, assessments=sellers) if source == 'trade' else None
        if source == 'trade' and not pick:
            continue
        hurdle = investment_hurdle(source, c, pick, team.cap.limit)
        if source == 'trade' and gain < hurdle:
            # Only a cheap, controlled future addition can justify a development trade.
            if not (future_case and c.years >= 2 and pick['round'] >= 6
                    and c.cap_hit(0) <= .01*team.cap.limit):
                continue
        role = next((a['role'] for a in after['assignments'] if a['player'] is p), None)
        if source == 'trade' and c.years == 1:
            cost_line += ' Contract expires after this season; keeping him requires a new deal.'
        if outgoing:
            cost_line += f' Roster is full: review releasing {outgoing.name}; no release is automatic from this report.'
        if pick:
            cost_line += f' Starting trade proposal: our {pick["label"]}. Recheck before offering.'
        context = [source, p.team, sorted(q.pid for q in injured), role, round(grade/3)]
        ranked.append(dict(pid=p.pid, name=p.name, pos=p.pos, ovr=round(PS.view_ovr(league, team.abbr, p)),
                           dev=dev, source=source, owner=p.team, reason=reason, cost=cost_line,
                           pick=pick, release=outgoing.pid if outgoing else None, context=context,
                           score=round(gain+need*5+(2 if future_case else 0)-(hurdle if source == 'trade' else 0), 2),
                           urgent=source == 'waiver' or bool(injured and gain >= 8)))
    return sorted(ranked, key=lambda r: (-r['score'], r['pid']))


def role_improvement(before, after, p):
    return any(a['player'] is p and (old['grade'] is None or
               a['grade'] >= old['grade']+3)
               for old, a in zip(before['assignments'], after['assignments']))


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
    body = 'These moves could address a roster need.'
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
        if not isinstance(saved, dict) or 'source' not in saved:
            continue  # Legacy saves lost the explanation; do not invent the old proposal.
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
        row['status'] = 'Dismissed' if row.get('dismissed') else '' if row['available'] else 'No longer available'
        rows.append(row)
    return rows


def dismiss(league, mid, pid):
    m = next((m for m in league.inbox if m['id'] == int(mid) and m.get('kind') == 'roster_report'), None)
    if m:
        for r in m['payload']['recommendations']:
            if not isinstance(r, dict) or 'context' not in r: continue
            if r['pid'] == pid:
                r['dismissed'] = True
                _state(league)['seen'][pid] = dict(tick=_tick(league, max(league.week or 1, m['payload'].get('report_week', 1))), context=r['context'])
                return dict(ok=True, line='Recommendation dismissed.')
    return dict(ok=False, why='Recommendation no longer exists.')

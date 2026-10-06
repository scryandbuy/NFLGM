"""
EXTENSIONS.

A club extends a man it wants to keep before he reaches the market. The
remaining years of his deal stay as signed; the new years are added on top
and the new signing bonus prorates over up to five years from now. Cap
hits, dead money and the trade engine read the result like any contract.

WHO CAN. Veterans may extend with any number of years remaining. Drafted
rookies wait three seasons, undrafted rookies two. CPU clubs prefer two or
fewer years left (first-rounders carry the fifth-year option separately).

THE PRICE. The agent asks the market's agent-side number; the club offers
its team-side number. The player takes a small certainty discount for money
now, which shrinks to nothing for a star in his final year, who has no
reason to give one. A deal is done when the club's number clears the ask
less the discount.

THE AI. Each offseason before the market opens, and once more before week
one, each club reviews its expiring men: starters and near-starters on the
right side of the age curve, who fit the scheme, and whom it can afford
against next year's books. Two to four a club a year is the real pace.

THE USER. extend(league, pid, apy, years) returns accepted, countered or
refused with the agent's reasoning; the inbox gets a note when one of his
men enters his final year.
"""
from cap_engine import forecast_cap
from inbox import player_name as inbox_player
import numpy as np
import math
from cap_engine import Contract, CAP, MAX_PRORATION_YEARS
import contract_structure as CS
import valuation as VAL
import contract_terms as CT

MAX_PER_CLUB = 6                 # throttle optional early renewals, never unresolved expiries
AGE_LIMIT = {'QB': 36, 'K': 38, 'P': 38}
CERTAINTY_DISCOUNT = 0.07


def eligible(p, league):
    c = p.contract
    if p.team is None or (c is None and (league.phase != 'offseason' or getattr(league, 'tags_done_year', None) == league.year)):
        return False
    if p.draft_year is not None and c is not None and c.signed <= p.draft_year:
        required = 3 if p.draft_round is not None else 2
        completed = league.year - p.draft_year
        from cap_accounting import pre_roll
        if getattr(league, 'phase', '') == 'playoffs' or pre_roll(league):
            completed += 1
        if completed < required:
            return False
    return True


def ai_eligible(p, league):
    return eligible(p, league) and (p.contract is None or p.contract.years <= 2)


def rookie_option_price(league, p):
    """The fixed fifth-year salary for an eligible first-round rookie."""
    if (p is None or p.team is None or p.contract is None or p.draft_round != 1
            or p.contract.years != 1 or p.draft_year is None
            or league.year != p.draft_year + 3
            or p.xp_spent.get('_fifth_year_option')):
        return None
    import tags as TAG
    cap = CAP.get(league.year + 1, CAP.get(league.year, 301.2) * 1.07)
    return round(0.8 * TAG.tag_price(p, cap), 3)


def exercise_rookie_option(league, pid, by_ai=False):
    p = league.player(pid)
    price = rookie_option_price(league, p)
    if price is None:
        return dict(ok=False, why='the fifth-year option is not available')
    team = league.teams[p.team]
    if price > next_year_room(team, CAP.get(league.year + 1, CAP.get(league.year, 301.2) * 1.07)):
        return dict(ok=False, why='the fifth-year salary will not fit next year’s cap')
    if by_ai:
        import copy
        preview = copy.deepcopy(p.contract)
        preview.years += 1
        preview.base.append(price)
        preview.rb.append(0.0)
        decision = _retention_budget(league, team, p, preview, 'rookie_option')
        if not decision['approved']:
            return dict(ok=False, why=decision['reason'])
    p.contract.years += 1
    p.contract.base.append(price)
    p.contract.rb.append(0.0)
    p.xp_spent['_fifth_year_option'] = league.year
    team.sync_cap()
    league.log('rookie_option', pid=p.pid, team=p.team, price=price, ai=by_ai)
    return dict(ok=True, price=price, line=f"{p.name}'s fifth-year option is exercised at ${price:.1f}m.")


def ai_rookie_options(league):
    """AI clubs keep valuable first-rounders when the option fits the books."""
    import valuation as VAL
    done = []
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None):
            continue
        for p in team.active():
            price = rookie_option_price(league, p)
            if price is None or p.ovr < 74:
                continue
            value = VAL.value_player(league, p, side='buyer')
            if value and float(value.get('apy', 0)) >= price * 0.8:
                if exercise_rookie_option(league, p.pid, by_ai=True)['ok']:
                    done.append((abbr, p.pid, price))
    return done


def honors_premium(league, p):
    """An agent prices the hardware: a major award in the last two seasons adds 12%, a first-team All-Pro 6%, a
    second team 3%, the best two counted, capped at 20%."""
    prem = []
    for yr in (league.year, league.year - 1):
        a = (getattr(league, 'awards', {}) or {}).get(yr, {}) or {}
        for k, v in a.items():
            ids = v if isinstance(v, list) else [v]
            if p.pid not in ids: continue
            if k in ('mvp', 'opoy', 'dpoy', 'oroy', 'droy', 'protector'): prem.append(0.12)
            elif k == 'all_pro_1': prem.append(0.06)
            elif k == 'all_pro_2': prem.append(0.03)
    return 1.0 + min(0.20, sum(sorted(prem, reverse=True)[:2]))


def terms(league, p, rng, pool=None):
    """Return the agent ask, team offer, requested new years and discount."""
    if pool is None:
        pool = VAL.pool_from_league(league)
    a = VAL.value_player(league, p, side='agent', rng=rng, pool=pool, extension=True)
    t = VAL.value_player(league, p, side='team', rng=rng, pool=pool, extension=True)
    if not a or not t:
        return None
    import personality as PT
    left = p.contract.years if p.contract else 0
    star = p.ovr >= 88 and left <= 1
    disc = 0.0 if star else CERTAINTY_DISCOUNT * (1.0 if left <= 1 else 1.4)
    disc = disc * PT.certainty_discount_mult(p) + PT.extension_discount(p)    # money and loyalty
    disc = float(np.clip(disc, -0.05, 0.25))
    ask = a['apy'] * PT.ask_mult(p) * honors_premium(league, p)
    years = int(np.clip(a['years'], 1, CT.MAX_OFFER_YEARS))
    return dict(ask=ask, offer=t['apy'], years=years, discount=disc)


def build(p, add_years, apy, cap, gm, league, front_load=None, bonus=None):
    """The extended contract: old years kept, new years appended, new bonus prorated from now."""
    if not 1 <= add_years <= CT.MAX_OFFER_YEARS or not np.isfinite(apy) or apy <= 0:
        raise ValueError('Offer must have a positive salary and one to seven years')
    if bonus is not None and (not np.isfinite(float(bonus)) or not 0 <= float(bonus) <= apy * add_years):
        raise ValueError('Signing bonus must be between zero and the total contract value')
    old = p.contract if p.contract is not None else Contract(0, [])
    left = old.years
    st = CS.structure(apy, add_years, p.pos, cap, gm, front_load=front_load)
    if bonus is not None:
        st['signing_bonus'] = float(bonus)
        base_total = apy * add_years - float(bonus)
        shape = float(st.get('front_load', 0.5))
        weights = [1 + (shape - 0.5) * 2 * (1 - 2 * i / max(1, add_years - 1)) for i in range(add_years)]
        st['base'] = [base_total * w / sum(weights) for w in weights]
    # the old bonus still owed keeps its proration; the new bonus spreads over
    # everything left, up to five years
    new_years = left + add_years
    base = list(old.base) + list(st['base'])
    rb = list(old.rb) + [0.0] * add_years
    c = Contract(years=new_years, base=base, bonus_schedule=old.bonus_schedule,
                 roster_bonus=rb, signed=league.year, void_years=max(0,len(old.bonus_schedule)-new_years),
                 market_cap=cap,
                 earned_base=old.earned_base, earned_roster=old.earned_roster, pay_start=old.pay_start, start_offset=old.start_offset)
    from cap_accounting import pre_roll
    c.add_bonus(st['signing_bonus'], 1 if pre_roll(league) else 0)
    return c


def extend(league, pid, apy, years, rng=None, by_ai=False, front_load=None, agreed=False, bonus=None, pool=None):
    """The offer to the man. Returns dict(result, ...)."""
    rng = rng or np.random.default_rng()
    p = league.player(pid)
    if p is None or p.team is None:
        return dict(result='refused', why='not under contract to a club')
    if not eligible(p, league):
        return dict(result='refused', why='not eligible to extend: rookie-contract waiting period or no retained contract rights')
    if by_ai:
        why = _ai_refusal(league, p)
        if why: return dict(result='refused', why=why)
    tm = terms(league, p, rng, pool=pool)
    if tm is None:
        return dict(result='refused', why='no market read on him')
    floor = tm['ask'] * (1.0 - tm['discount'])
    if getattr(p, 'morale', None) is not None:
        import morale_system as MS
        ne = MS.negotiation_effect(p.morale)
        floor *= 1.0 + ne['demand_premium']
        if not ne['will_discount']: floor = max(floor, tm['ask'] * (1.0 + ne['demand_premium']) * (1.0 - 0.02))
    team = league.teams[p.team]
    import contract_offer as CO
    try:
        package = CO.canonical(league, p, team, dict(apy=apy, years=years, bonus=bonus, front_load=front_load), 'extension')
        assessment = CO.assess(league, p, team, package, floor, tm['years'], 'extension')
    except (TypeError, ValueError) as exc:
        return dict(result='refused', why=str(exc))
    bonus, front_load = package['bonus'], package['front_load']
    # a number the agent has already agreed to in talks is not re-priced here: the negotiation set the
    # floor with the same morale and shape terms, and a second floor that disagreed by a few cents made
    # an agreed deal 'fall through' and left the thread failing every week
    if not agreed and not assessment['acceptable']:
        counter = dict(assessment['reference_package'])
        # Round up the complete neutral package so accepting the published
        # counter cannot fall a fraction of a cent below its own assessment.
        price = math.ceil(counter['apy'] * 100) / 100
        counter['bonus'] *= price / counter['apy']
        counter['apy'] = price
        counter = CO.canonical(league, p, team, counter, 'extension')
        return dict(result='countered', ask=price, years=counter['years'], counter=counter,
            why=f"his agent wants ${price:.2f}m a year over {counter['years']} years, "
                f"with ${counter['bonus']:.2f}m signing bonus and evenly distributed new salaries")
    if years < 1:
        return dict(result='refused', why='at least one new year')
    cap = CAP.get(league.year, 301.2)
    if front_load is None and by_ai:
        front_load = CS.choose_shape(team, years)
    from cap_accounting import require_room
    import morale as MO
    pay_concern = MO.pay_concern(league, p)
    try:
        c = build(p, years, apy, cap, team.gm, league, front_load=front_load, bonus=bonus)
        require_room(league, team, p.pid, c)
    except ValueError as e: return dict(result='refused', why=str(e))
    p.contract = c
    CO.remember(league, p, c, apy, tm['ask'])
    team.sync_cap()
    MO.shock(league, pid, 'extension_signed')
    if MO.wants_out(p) and p.xp_spent['_request'].get('reason') == 'contract':
        MO.resolve_request(league, pid, 'extension')
    if pay_concern:
        p.xp_spent.pop('_contract_concern', None)
        if p.morale is not None:
            p.morale._contract_drag = 0.0
    import retention_plan as RP
    league.log('extension', pid=pid, team=p.team, apy=round(apy, 2), years=years, ai=by_ai,
               front_load=front_load, role_intent=RP.committed_role(team, p))
    __import__('inbox').reconcile(league)
    return dict(result='accepted', apy=round(apy, 2), years=years, contract=c,
                front_load=front_load, pay_concern_resolved=pay_concern)


def next_year_room(team, cap_next):
    """What the club has committed next year against next year's cap."""
    committed = sum(p.contract.cap_hit(1) for p in team.active() if p.contract and p.contract.years > 1)
    return cap_next - committed - team.cap.dead_next


def can_afford_extension(league, team, player, apy, years, front_load=None, bonus=None):
    """Compare each projected annual cap charge with that year's budget.

    Total multi-year cash is not a one-year cap charge. Preserve current-year
    validation in extend(), and avoid double counting the replaced contract.
    """
    cap = CAP.get(league.year, 301.2)
    try:
        import contract_offer as CO
        offer = CO.canonical(league, player, team, dict(apy=apy, years=years,
            front_load=front_load, bonus=bonus), 'extension')
        preview = build(player, years, apy, cap, team.gm, league,
                        front_load=offer['front_load'], bonus=offer['bonus'])
        from cap_accounting import require_room
        require_room(league, team, player.pid, preview)
    except ValueError:
        return False
    from cap_accounting import next_year_ledger
    limit_next, committed_next, _, _ = next_year_ledger(league, team)
    def charge(contract, index):
        if contract is None: return 0.0
        if index < contract.years: return contract.cap_hit(index)
        return contract.remaining_proration(index) if index == contract.years else 0.0
    for i in range(1, preview.years + 1):
        if i == 1:
            limit, committed = limit_next, committed_next
        else:
            limit = forecast_cap(league, league.year+i)
            committed = sum(charge(p.contract, i) for p in team.roster)
        old = charge(player.contract, i)
        new = charge(preview, i)
        if committed - old + new > limit + .0005 and new > old + .0005:
            return False
    return True


def _ai_refusal(league, p):
    import negotiations as NG
    if NG.extension_defers(league, p):
        return 'His agent will not negotiate an extension during the season'
    for t in reversed(getattr(league, 'negotiations', None) or []):
        if t.get('pid') == p.pid and t.get('team') == p.team and t.get('kind') == 'extension':
            if t.get('state') == 'declined' or (t.get('state') == 'broken_off'
                    and t.get('broken_until', float('inf')) > NG._clock(league)):
                return 'His extension negotiation is closed'
            break
    return None


def _retention_budget(league, team, player, contract, action='extension', *,
                      benefit=None, before=None, market=None, _cache=None):
    import financial_plan as FP
    import roster_needs as RN
    if benefit is None:
        benefit = max(0.0, RN.departure_loss(team, player), RN.retention_value(team, player))
    prepared = None
    if _cache is not None:
        # Disposable purchase-review snapshot: roster, contracts, pending
        # offers and prior renewal intents stay fixed; only picks can vary.
        # Reprice those rookie obligations on every call.
        if 'market' not in _cache: _cache['market'] = FP.retention_market(league)
        market = _cache['market']
        if 'before' not in _cache:
            _cache['before'] = FP.prepare_snapshot(league, team, market=market)
        before = FP.snapshot(league, team, market=market, prepared=_cache['before'])
        key = (player.pid, repr(vars(contract)))
        after = _cache.setdefault('after', {})
        if key not in after:
            after[key] = FP.prepare_snapshot(league, team, additions=[(player,contract)], market=market)
        prepared = after[key]
    return FP.evaluate(league, team, additions=[(player, contract)],
                       gain=benefit, action=action, before=before, market=market, prepared_after=prepared)


def negotiate_ai(league, p, apy, years, rng=None, pool=None):
    """One budget, one term, at most four alternative payment packages.

    The club may move cash earlier or add up to ten percentage points of
    upfront bonus. It never increases its price/term ceiling to force a yes.
    """
    import contract_offer as CO
    if p.team is None or p.team == getattr(league, 'user_team', None):
        return dict(result='refused', why='CPU negotiations require a CPU team')
    why = _ai_refusal(league, p)
    if why: return dict(result='refused', why=why)
    team = league.teams[p.team]
    original = CO.canonical(league, p, team, dict(apy=apy, years=years), 'extension')
    # Assess the original even if its shape misses a budget: a different
    # payment schedule can fit. No signing happens outside both cap guards.
    budget, total = float(apy), float(apy) * years
    max_bonus = min(total * .78, original['bonus'] + total * .10)
    candidates = [original]
    seen = set(); last = dict(result='refused', why='No affordable agreement within the club budget')
    attempts = 0
    while candidates:
        package = candidates.pop(0)
        key = (package['apy'], package['years'], package['bonus'], package['front_load'])
        if key in seen: continue
        seen.add(key)
        if (package['years'] != years or package['apy'] > budget + 1e-9
                or package['apy'] * years > total + 1e-9 or package['bonus'] > max_bonus + 1e-9):
            continue
        if not can_afford_extension(league, team, p, package['apy'], years,
                                    package['front_load'], package['bonus']):
            if package is original:
                candidates.extend([dict(original, front_load=.5), dict(original, front_load=.85),
                    dict(original, front_load=.5, bonus=min(max_bonus, total*.445))])
            continue
        preview = build(p, years, package['apy'], CAP.get(league.year, 301.2),
                        team.gm, league, front_load=package['front_load'], bonus=package['bonus'])
        decision = _retention_budget(league, team, p, preview)
        if not decision['approved']:
            last = dict(result='refused', why=decision['reason'])
            if package is original:
                candidates.extend([dict(original, front_load=.5), dict(original, front_load=.85),
                    dict(original, front_load=.5, bonus=min(max_bonus, total*.445))])
            continue
        attempts += 1
        result = extend(league, p.pid, package['apy'], years, rng, by_ai=True,
                        pool=pool, front_load=package['front_load'], bonus=package['bonus'])
        last = dict(result, attempts=attempts)
        if result['result'] in ('accepted', 'refused'): return last
        if package is original:
            candidates.extend([dict(original, front_load=.5), dict(original, front_load=.85),
                dict(original, front_load=.5, bonus=min(max_bonus, total*.445)), result['counter']])
    return dict(last, attempts=attempts)


@VAL.comparison_batch()
def ai_round(league, rng, verbose=False):
    """Review real package jobs before reserves; agreement still needs both sides."""
    import retention_plan as RP
    import draft as DFT
    done = []
    pool = None
    scale = DFT.position_scale(league)
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None) or team.gm is None:
            continue
        if pool is None: pool = VAL.pool_from_league(league)
        import trade_retention as TRE
        planned = TRE.pursue(league,team,rng,pool)
        done.extend(planned)
        if planned: pool = VAL.pool_from_league(league)
        RP.refresh(league,team,pool=pool)
        n = 0
        for p, inputs in RP.candidates(league,team,scale):
            intent=p.xp_spent.get(TRE.KEY,{})
            if intent.get('team')==abbr and intent.get('last_attempt')==[league.year,league.phase,league.week]: continue
            # Cap/financial/agent checks determine how many expiring men can
            # stay. An arbitrary renewal count must not send a seventh useful,
            # affordable incumbent to free agency without a negotiation.
            if n >= MAX_PER_CLUB and p.contract and p.contract.years > 0: continue
            # Useful reserve retention remains discretionary. Important starting
            # roles receive a real review instead of a coin flip that skips them.
            if inputs['role_share'] < .15 and rng.random() > .25+.25*team.gm.loyalty: continue
            res = _pursue_retention(league,team,p,rng,pool,scale)
            if res['result'] == 'accepted':
                n += 1; done.append((abbr, p.name, p.pos, round(p.ovr), res['apy'], res['years']))
                pool = VAL.pool_from_league(league)
    if verbose:
        print(f'  {len(done)} extensions')
    return done


def _pursue_retention(league, team, p, rng, pool=None, scale=None):
    import retention_plan as RP
    plan = RP.assess(league,team,p,pool=pool,scale=scale)
    RP.record(league,plan)
    if (plan['decision']!='retain' or not plan['affordable']
            or plan.get('veteran_viable') is False or _ai_refusal(league,p)):
        return dict(result='refused',why=', '.join(plan['reasons']))
    tm = terms(league,p,rng,pool=pool)
    if tm is None: return dict(result='refused',why='No market read')
    want = .75+.25*plan['role_share']-.10*max(0.,team.gm.youth-.5)*(p.age>=28)
    offer = round(min(tm['offer']*(1.+.12*want),tm['ask']),2)
    # Actual player asks/terms retain negotiation uncertainty; the plan is a
    # forecast, never authority to force acceptance or bypass current finances.
    years = min(tm['years'],plan.get('max_new_years',tm['years']))
    res = negotiate_ai(league,p,offer,years,rng,pool=pool)
    c=p.contract
    outcome=dict(plan,contract_years=c.years if c else 0,contract_signed=c.signed if c else None,
                 extension_result=res['result'],extension_reason=res.get('why',''))
    RP.record(league,outcome)
    return res


@VAL.comparison_batch()
def in_season_round(league, rng, week):
    """Clubs extend in September through December too: each week a few clubs get one of their expiring starters
    done ahead of the market. Real clubs sign dozens of in-season extensions a year; this engine signed none."""
    wk = int(week or 0)
    if not (1 <= wk <= 22): return []
    # in the playoffs only the clubs whose season is over work the window: a real club in the bracket is not signing
    # extensions the week of a game
    alive = set()
    if wk >= 18:
        post = getattr(league, '_post_ref', None)
        alive = set(getattr(post, 'alive_now', lambda: set())()) if post is not None else set()
    done = []
    import retention_plan as RP
    import draft as DFT
    scale=DFT.position_scale(league)
    pool=None
    for abbr, team in league.teams.items():
        if abbr == getattr(league, 'user_team', None) or team.gm is None: continue
        if wk >= 18 and abbr in alive: continue
        import trade_retention as TRE
        if any(TRE.active_plan(league,team,p) for p in team.roster):
            if pool is None: pool=VAL.pool_from_league(league)
            planned=TRE.pursue(league,team,rng,pool)
            done.extend((a,n,pos,apy,years) for a,n,pos,ovr,apy,years in planned)
            if planned: pool=VAL.pool_from_league(league)
        if 6 <= wk <= 9:
            if pool is None: pool=VAL.pool_from_league(league)
            RP.refresh(league,team,pool=pool)
        # the eliminated clubs work it harder: the window is short and the market is coming
        if rng.random() > (0.085 if wk <= 17 else 0.16): continue
        if pool is None: pool=VAL.pool_from_league(league)
        for p,inputs in RP.candidates(league,team,scale)[:4]:
            intent=p.xp_spent.get(TRE.KEY,{})
            if intent.get('team')==abbr and intent.get('last_attempt')==[league.year,league.phase,league.week]: continue
            res=_pursue_retention(league,team,p,rng,pool,scale)
            if res.get('result') == 'accepted':
                done.append((abbr,p.name,p.pos,res['apy'],res['years']))
                pool=VAL.pool_from_league(league)
                break
    return done


def notify_user(league):
    """The inbox: your men entering their final year."""
    import inbox as IB
    user = getattr(league, 'user_team', None)
    if not user: return 0
    n = 0
    for p in league.teams[user].active():
        if p.contract and p.contract.years == 1 and eligible(p, league) and p.ovr >= 76:
            IB.post(league, 'contract_year', f'{inbox_player(p)} enters his final year',
                    f"{inbox_player(p)} ({p.pos}, {p.ovr:.0f}, age {int(p.age)}) is in the last year of his deal at ${p.apy:.1f}m. "
                    f"He can be extended now; his agent will price him at the market.", sender=user,
                    payload=dict(pid=p.pid, link=f'player:{p.pid}'), expires_week=None)
            n += 1
    return n

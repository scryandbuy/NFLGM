"""Funded renewal intent for premium purchases of expiring players.

Unsigned years never increase trade value. A second-round-equivalent net
investment triggers a concrete renewal review; inexpensive coverage/rentals
keep the ordinary roster, price and funding checks. This price benchmark is
a policy boundary, not an empirical probability or a limit on pick counts.
"""
import copy

KEY = '_trade_extension_plan'


def active_plan(league, team, player):
    plan = player.xp_spent.get(KEY)
    if not plan or plan.get('team') != team.abbr or player.team != team.abbr:
        return None
    if plan.get('state') not in ('pending', 'deferred', 'countered') or player.retired:
        return None
    # The original contract's expiry survives rollover; a separate extension
    # or option supersedes this intention without creating a second reserve.
    expiry = league.year + (player.contract.years if player.contract else 0)
    if expiry != plan['expiry']:
        return None
    return plan


def reserved_contracts(league, team, excluded=()):
    """Forecast planned extensions only. Never book them in the legal ledger."""
    import extensions as EXT
    excluded = set(excluded)
    for p in team.roster:
        plan = active_plan(league, team, p)
        if plan is None or p.pid in excluded:
            continue
        yield p, EXT.build(p, plan['years'], plan['apy'], team.cap.cap,
                           team.gm, league, front_load=plan['front_load'], bonus=plan['bonus'])


def _projection(league, team, removed, received, picks):
    from cap_accounting import trade_projection
    shadow = copy.copy(league)
    club = copy.copy(team)
    shadow.teams = dict(league.teams, **{team.abbr: club})
    shadow.players = dict(league.players)
    club.league = shadow
    # trade_projection syncs its source; even that cache update stays isolated.
    club.roster = [copy.copy(p) for p in team.roster]
    club.practice_squad = [copy.copy(p) for p in team.practice_squad]
    club.cap = copy.copy(team.cap)
    club.cap.contracts = list(team.cap.contracts)
    for p in club.roster + club.practice_squad:
        p.xp_spent = copy.deepcopy(p.xp_spent)
        p._team_ref = club
        shadow.players[p.pid] = p
    club.cap = trade_projection(shadow, team.abbr, removed, received)
    contracts = {pid: c for pid, c, _ in club.cap.contracts}
    club.roster = [p for p in club.roster if p.pid not in removed]
    for pid in received:
        if not isinstance(pid, str): continue
        p = copy.copy(league.player(pid))
        p.xp_spent = copy.deepcopy(p.xp_spent)
        p.team, p.contract, p._team_ref = team.abbr, contracts[pid], club
        club.roster.append(p)
        shadow.players[pid] = p
    club.ir = [shadow.players[p.pid] for p in team.ir if p.pid not in removed]
    club.picks = [copy.copy(pk) for pk in picks]
    for pk in club.picks: pk.owner = team.abbr
    club.sync_cap()
    return shadow, club


def purchase_plans(league, ta, tb, outgoing, incoming, *, cache=None):
    import trades as TR
    import trade_engine as TE
    import valuation as VAL
    import retention_plan as RP
    import extensions as EXT
    import contract_offer as CO
    cache = {} if cache is None else cache
    # All callers discard this cache after any roster/contract/market change.
    key = ('purchase_extension', ta.abbr, tb.abbr,
           tuple(str(x) for x in outgoing), tuple(str(x) for x in incoming))
    if key in cache: return cache[key]
    from cap_accounting import pre_roll
    def potentially_expiring(items):
        for item in items:
            p=league.player(item) if isinstance(item,str) else None
            c=p.contract if p else None
            if c and c.years-max(int(pre_roll(league)),c.start_offset)<=1: return True
        return False
    if not any(team.abbr!=getattr(league,'user_team',None) and potentially_expiring(items)
               for team,items in ((ta,incoming),(tb,outgoing))):
        return dict(approved=True,plans=[],reason='no_expiring_purchase')
    if 'purchase_pool' not in cache: cache['purchase_pool'] = VAL.pool_from_league(league)
    pool = cache['purchase_pool']
    def quotes(team, items):
        result = []
        for item in items:
            if not isinstance(item, str): result.append(TR.pick_asset(league, item)); continue
            qkey = ('purchase_quote', team.abbr, item)
            if qkey not in cache:
                p = league.player(item)
                cache[qkey] = TR.player_asset(league, team, p, pool, None) if p else None
            result.append(cache[qkey])
        return result
    result = dict(approved=True, plans=[], reason='no_premium_expiring_purchase')
    for team, seller, sent, received in ((ta,tb,outgoing,incoming),(tb,ta,incoming,outgoing)):
        if team.abbr == getattr(league, 'user_team', None) or team.gm is None: continue
        got = quotes(seller, received)
        if any(x is None for x in got):
            result.update(approved=False, reason='unavailable_trade_asset'); break
        expiring = [q for q in got if q['kind']=='player' and q['valued_contract_years']==1]
        if not expiring: continue
        paid = quotes(team, sent)
        if any(x is None for x in paid):
            result.update(approved=False, reason='unavailable_trade_asset'); break
        # Credit actual picks/controlled players coming back; no imagined
        # resale or future extension subsidizes the acquisition price.
        net = sum(TE.market_price(x) for x in paid)-sum(TE.market_price(x) for x in got if x not in expiring)
        threshold = TE.pick_price_dollars(64, cap=team.cap.cap)
        if net < threshold: continue
        removed = [x for x in sent if isinstance(x,str)]
        sent_ids = {id(x) for x in sent if not isinstance(x,str)}
        picks = [pk for pk in team.picks if id(pk) not in sent_ids]+[x for x in received if not isinstance(x,str)]
        shadow, club = _projection(league,team,removed,received,picks)
        # Evaluate all expiring members together: each successful plan reserves
        # its contract before the next player can claim the same future space.
        for asset in sorted(expiring, key=lambda q: -TE.market_price(q)):
            p = shadow.player(asset['pid'])
            plan = RP.assess(shadow,club,p,pool=pool,acquisition=True)
            if (plan['decision']!='retain' or not plan['affordable']
                    or plan.get('veteran_viable') is False or plan['extension_probability']<.35
                    or 'price_gap' in plan['reasons']):
                result.update(approved=False, reason='no_funded_extension_plan', team=team.abbr,
                              pid=p.pid, assessment=plan)
                break
            package = CO.canonical(shadow,p,club,dict(apy=plan['offer_apy'],years=plan['years']),'extension')
            # Select a shape the existing actual negotiator can fund too.
            total=package['apy']*package['years']
            alternatives=[package,dict(package,front_load=.5),dict(package,front_load=.85),
                dict(package,front_load=.5,bonus=min(total*.445,package['bonus']+total*.10))]
            chosen=None
            for terms in alternatives:
                if not EXT.can_afford_extension(shadow,club,p,terms['apy'],terms['years'],terms['front_load'],terms['bonus']): continue
                contract=EXT.build(p,terms['years'],terms['apy'],club.cap.cap,club.gm,shadow,
                                   front_load=terms['front_load'],bonus=terms['bonus'])
                if EXT._retention_budget(shadow,club,p,contract)['approved']:
                    chosen=terms; break
            if chosen is None:
                result.update(approved=False,reason='no_funded_extension_plan',team=team.abbr,pid=p.pid); break
            intent=dict(chosen,team=team.abbr,pid=p.pid,year=league.year,week=league.week,
                expiry=league.year+p.contract.years,state='pending',role_intent=RP.committed_role(club,p),
                investment=round(net,3),expected_apy=plan['expected_apy'])
            p.xp_spent[KEY]=intent
            result['plans'].append(intent)
        if not result['approved']: break
    if result['approved'] and result['plans']: result['reason']='funded_extension_plan'
    if len(cache)>2048: cache.clear()
    cache[key]=result
    return result


def remember(league, plans):
    for plan in plans:
        p=league.player(plan['pid'])
        if p is not None and p.team==plan['team']:
            p.xp_spent[KEY]=copy.deepcopy(plan)
            league.log('trade_extension_plan', **{k:v for k,v in plan.items() if k not in ('year','week')})


def pursue(league, team, rng, pool=None):
    """Priority talks, without a random club skip or forced player agreement."""
    import extensions as EXT
    import retention_plan as RP
    done=[]
    for p in team.roster:
        intent=active_plan(league,team,p)
        if intent is None: continue
        clock=[league.year,league.phase,league.week]
        if intent.get('last_attempt')==clock: continue
        intent['last_attempt']=clock
        refusal=EXT._ai_refusal(league,p)
        if refusal:
            result=dict(result='deferred' if 'during the season' in refusal else 'refused',why=refusal)
        else:
            # Re-evaluate actual roles, aging and finances; an acquisition plan
            # is not a permanent obligation when the football situation changes.
            plan=RP.assess(league,team,p,pool=pool,acquisition=True)
            if (plan['decision']!='retain' or not plan['affordable'] or plan.get('veteran_viable') is False
                    or 'price_gap' in plan['reasons']):
                result=dict(result='abandoned',why=', '.join(plan['reasons']))
            else:
                result=EXT.negotiate_ai(league,p,plan['offer_apy'],plan['years'],rng,pool=pool)
        intent['state']=result['result']
        intent['reason']=result.get('why','')
        league.log('trade_extension_attempt',team=team.abbr,pid=p.pid,result=intent['state'],why=intent['reason'])
        if result['result']=='accepted':
            done.append((team.abbr,p.name,p.pos,round(p.ovr),result['apy'],result['years']))
            import valuation as VAL
            pool=VAL.pool_from_league(league)
    return done

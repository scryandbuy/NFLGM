"""Explainable CPU retain/shop/let-walk choices; never executes a transaction.

Assessments are deterministic. Actual negotiations and fair-price trade/cap
guards decide whether a proposed path succeeds. Saved transaction rows are the
durable record; the refresh cache only avoids duplicate work in one process.
"""
import draft as DFT
import roster_needs as RN
import trade_engine as TE
import valuation as VAL
from cap_engine import CAP


def stage(league):
    return ('deadline' if league.phase == 'regular' else
            'postseason' if league.phase == 'playoffs' else 'offseason')


def role_inputs(league, team, player, baseline=None, scale=None):
    return _role_read(league,team,player,baseline,scale)[0]


def committed_role(team, player, report=None):
    """Public roster intent saved only when a new contract is actually signed."""
    report = RN.assess(team) if report is None else report
    share = sum(r['weight'] for r in report['package_assignments']
                if r['player'] is not None and r['player'].pid == player.pid)
    if player.pos in ('K', 'P', 'LS') and team.by_pos(player.pos)[:1] == [player]:
        share = 1.
    return dict(role_share=round(min(1., share), 4),
                departure_loss=round(max(0., RN.departure_loss(team, player, report)), 4))


def extension_continuity(league, team, removed, report, *, cache=None):
    """A finite preference for an unchanged, recently renewed football role.

    This is not bonus repayment, a trade ban, or a promise of an available bid.
    Existing asset quotes price age/control/pay and the joint financial preview
    accounts for dead money. A lost starting role, reduced depth need, request,
    or cap casualty can reduce this separate preference for following the plan.
    """
    import morale
    if not removed or float(team.cap_space) < -.0005:
        return dict(reserve=0., players=[])
    cache = {} if cache is None else cache
    key = ('extension_intents', team.abbr)
    if key not in cache:
        year, week = int(league.year), int(league.week or 0)
        offseason = league.phase not in ('regular', 'playoffs')
        intents, waiting = {}, set()
        for tx in reversed(getattr(league, 'transactions', ())):
            ey, ew = int(tx.get('year', year)), int(tx.get('week') or 0)
            phase = tx.get('phase')
            if offseason:
                if phase in ('regular', 'playoffs') or ey < year - 1: break
            elif ey != year or (phase == 'regular' and week - ew > 3): break
            elif phase != 'regular' and week > 3: break
            if tx.get('team') != team.abbr: continue
            pid = tx.get('pid')
            if tx.get('kind') == 'extension' and pid not in intents:
                intents[pid] = tx.get('role_intent')
                if intents[pid] is None: waiting.add(pid)
            elif tx.get('kind') == 'cpu_retention_decision' and pid in waiting:
                # Older saves may contain the actual pre-extension assessment.
                # With no recorded intent, do not invent the earlier roster.
                if 'role_share' in tx and 'departure_loss' in tx:
                    intents[pid] = {k: tx[k] for k in ('role_share', 'departure_loss')}
                waiting.remove(pid)
        cache[key] = intents
    gm = team.gm
    trait = lambda name: max(0., min(1., float(getattr(gm, name, .5))))
    # Reuse the acquisition-continuity scale in trades. These are soft GM
    # preferences, not empirical odds or an extra charge for a paid bonus.
    weight = .5 + .5*trait('patience') + .25*trait('loyalty') - .25*trait('aggression')
    players = []
    for p in report['players']:
        prior = cache[key].get(p.pid)
        if p.pid not in removed or not prior or morale.wants_out(p): continue
        now = committed_role(team, p, report)
        share, loss = float(prior['role_share']), float(prior['departure_loss'])
        # A starting plan is measured by the actual assignments it retains.
        # Rotational DTs and other reserves can matter despite few starts;
        # use the same marginal depth value that supported their renewal.
        if share >= .15:
            same_role = min(1., now['role_share'] / share)
        else:
            same_role = min(1., now['departure_loss'] / loss) if loss > 0 else 0.
        importance = min(1., max(share / .15, loss / 2.))
        reserve = 3. * weight * importance * same_role
        players.append(dict(pid=p.pid, prior=prior, current=now,
                            same_role=round(same_role, 4), reserve=round(reserve, 4)))
    return dict(reserve=round(min(6., sum(p['reserve'] for p in players)), 4), players=players)


def retention_priority(pos, normalized_grade, role_share, departure_loss):
    """Bounded review order, separate from the transaction's budget benefit.

    Common-scale quality contributes 45 points, expected role 35, and
    replacement difficulty at most 20. Empty-slot penalties cannot grow
    without limit and consume a franchise player's first negotiation chance.
    Apply the existing draft positional premiums (LS shares the specialist
    tier); a reserve QB still has to earn priority through quality and role.
    These are decision weights, not fitted probabilities of re-signing.
    """
    quality = max(0., min(1., (normalized_grade - 62.5) / 25.))
    share = max(0., min(1., role_share))
    loss = max(0., departure_loss)
    replacement = loss / (loss + 8.)
    value = DFT.PREMIUM.get(pos, DFT.PREMIUM['P'] if pos == 'LS' else 1.)
    value = max(0., min(1., value / max(DFT.PREMIUM.values())))
    return round((45.*quality + 35.*share + 20.*replacement) * value, 4)


def _role_read(league, team, player, baseline=None, scale=None):
    report = RN.assess(team) if baseline is None else baseline
    scale = DFT.position_scale(league) if scale is None else scale
    rows = [r for r in report['package_assignments'] if r['player'] is player]
    share = min(1., sum(r['weight'] for r in rows))
    if player.pos in ('K','P','LS') and team.by_pos(player.pos)[:1] == [player]: share = 1.
    loss = max(0., RN.departure_loss(team, player, baseline=report))
    normalized = DFT.common_scale(player.ovr, player.pos, scale)
    reserves = [p for p in report['players'] if p.pid != player.pid and p.pos == player.pos
                and not p.retired and p.out_until is None]
    # Explain the next body; exact package departure loss is authoritative
    # when cross-position replacements or multiple starting slots apply.
    own = team.by_pos(player.pos)
    rank = next((i for i,p in enumerate(own) if p.pid == player.pid), len(own))
    next_body = own[rank+1] if rank+1 < len(own) else min(reserves, key=lambda p: p.ovr, default=None)
    replacement = next_body.ovr if next_body is not None else 55.
    retention=RN.retention_value(team,player)
    important = bool(share >= .15 or loss >= 2. or retention >= 2.)
    row=dict(role_share=round(share,4), roles=sorted({r['role'] for r in rows}),
        departure_loss=round(loss,4), replacement_grade=round(replacement,3),
        replacement_pid=next_body.pid if next_body is not None else None,
        normalized_grade=round(normalized,3), important=important,
        importance=retention_priority(player.pos, normalized, share, loss))
    return row,max(loss,retention)  # unrounded benefit preserves financial thresholds


def _review_context(league,team,baseline=None,scale=None):
    """Read-only work shared only inside one unchanged team review.

    Never persisted or reused across a transaction. Every candidate still gets
    its own full proposed-contract projection and authoritative cap check.
    """
    return dict(report=RN.assess(team) if baseline is None else baseline,
                scale=DFT.position_scale(league) if scale is None else scale,
                inputs={},financial=None)


def veteran_plan(team, player, inputs, scale, window):
    """A short bridge must still beat the replacement after expected aging.

    Use the engine's aging curves at neutral longevity and annual variation,
    not the player's hidden longevity or future random draws. Existing years
    count toward the forecast because an extension adds years at the end.
    """
    import copy
    from types import SimpleNamespace
    import regression as REG
    left = int(getattr(player.contract, 'years', 0))
    def forecast(p):
        projected = copy.copy(p)
        projected.ratings = dict(p.ratings)
        projected.longevity = 1.
        grades = []
        for year in range(1, left + 3):
            REG.decline(projected, SimpleNamespace(normal=lambda *args: 1.), age=p.age + year)
            if year > left: grades.append(projected.ovr)
        return grades
    grades = forecast(player)
    successor = next((p for p in team.active() if p.pid == inputs.get('replacement_pid')), None)
    replacements = forecast(successor) if successor is not None else [inputs['replacement_grade']]*2
    youth = max(0., min(1., float(team.gm.youth)))
    threshold = 2. + 6.*youth + (2. if window in ('rebuilding','retooling') else
                               -1. if window in ('contending','win_now') else 0.)
    grade = DFT.common_scale(grades[0], player.pos, scale)
    edge = grades[0] - replacements[0]
    viable = bool(inputs['important'] and grade >= 70.+4.*youth and edge >= threshold)
    two_years = (viable and youth <= .5 and grade >= 78.
                 and grades[1] >= replacements[1] + threshold
                 and player.ovr - grades[1] <= 5.)
    return dict(veteran_viable=viable, veteran_projected_grade=round(grades[0],3),
                veteran_projected_replacement=round(replacements[0],3),
                veteran_replacement_edge=round(edge,3), veteran_required_edge=round(threshold,3),
                max_new_years=2 if two_years else 1)


def candidates(league, team, scale=None):
    """Package starters and useful reserves, including WR3, TE2 and nickel CB."""
    import extensions as EXT
    report = RN.assess(team)
    scale = DFT.position_scale(league) if scale is None else scale
    out = []
    for p in report['players']:
        if p.retired or not EXT.ai_eligible(p, league): continue
        row = role_inputs(league,team,p,report,scale)
        if not row['important']: continue
        if p.contract and p.contract.years >= 2 and row['normalized_grade'] < 80: continue
        out.append((p,row))
    # Resolve contracts that have actually expired before buying optional
    # extra control on men who will already be here next season.
    return sorted(out,key=lambda pr:((pr[0].contract.years if pr[0].contract else 0)
                  if league.phase in ('offseason','free_agency') else 0,
                  -pr[1]['importance'],str(pr[0].pid)))


def assess(league, team, player, pool=None, baseline=None, scale=None, *, _context=None,
           acquisition=False):
    import extensions as EXT
    import contract_offer as CO
    from trade_calendar import trading_open
    context=_review_context(league,team,baseline,scale) if _context is None else _context
    fixed = context.get('fixed')
    def unchanged(name, read):
        # Only immutable purchase searches supply this mapping. Picks cannot
        # change an agent's ask, public aging read, refusal or current role.
        if fixed is None: return read()
        key = (player.pid, name)
        if key not in fixed: fixed[key] = read()
        return fixed[key]
    if player.pid not in context['inputs']:
        context['inputs'][player.pid]=_role_read(league,team,player,context['report'],context['scale'])
    inputs,benefit=context['inputs'][player.pid]
    row=dict(inputs)
    c = player.contract
    row.update(team=team.abbr,pid=player.pid,decision='let_walk',reasons=[],
        expected_apy=0.,offer_apy=0.,years=0,extension_probability=0.,
        affordable=False,financial_reason='no_market_read',trade_floor=0.,
        contract_years=c.years if c else 0,contract_signed=c.signed if c else None)
    if player.team != team.abbr or player.retired or not EXT.ai_eligible(player,league):
        row['reasons']=['not_eligible']; return row
    tm = unchanged('terms', lambda: EXT.terms(league,player,None,pool=pool))
    if not tm:
        row['reasons']=['no_market_read']; return row
    race = unchanged('race', team.ctx)
    if 'games_played' not in race: race=dict(race,**TE.race_context(team))
    window = TE.window(race)
    years = tm['years']
    renewal_age = player.age + (max(0, c.years) if acquisition and c else 0)
    if renewal_age > EXT.AGE_LIMIT.get(player.pos,31):
        row.update(unchanged('veteran', lambda: veteran_plan(team,player,inputs,context['scale'],window)))
        years = min(years,row['max_new_years'])
    from min_salary import demand_quote
    minimum_offer = demand_quote(league, player, 0, years, 'extension')
    ask = max(tm['ask'], minimum_offer)
    want = .75 + .25*row['role_share'] - .10*max(0.,team.gm.youth-.5)*(player.age>=28)
    ceiling = tm['offer']*(1.+.12*want)
    # A GM can refuse the legal minimum, but must never plan an impossible
    # subminimum offer. Cap and roster review below decide whether to pay it.
    apy = max(minimum_offer, round(min(ceiling,ask),2))
    floor = max(minimum_offer, ask*(1.-tm['discount']))
    row.update(expected_apy=round(ask,2),offer_apy=apy,years=years)
    refusal = unchanged('refusal', lambda: EXT._ai_refusal(league,player))
    # Evaluate the same bounded payment alternatives as the negotiator; never
    # declare someone unaffordable solely because the first schedule misses.
    original = CO.canonical(league,player,team,dict(apy=apy,years=years),'extension')
    total = apy*years; bonus = min(total*.78,original['bonus']+total*.10)
    packages = [original,dict(original,front_load=.5),dict(original,front_load=.85),
                dict(original,front_load=.5,bonus=min(bonus,total*.445))]
    legal_extension_possible = False
    for package in packages:
        shape = (apy,years,package['front_load'],package['bonus'])
        if not unchanged(('legal_cap',shape), lambda: EXT.can_afford_extension(
                league,team,player,apy,years,package['front_load'],package['bonus'])):
            row['financial_reason']='legal_cap_failure'; continue
        legal_extension_possible = True
        preview = EXT.build(player,years,apy,CAP.get(league.year,301.2),team.gm,league,
                            front_load=package['front_load'],bonus=package['bonus'])
        budget_cache = context.get('budget_cache')
        if budget_cache is not None:
            budget = EXT._retention_budget(league,team,player,preview,
                                          benefit=benefit,_cache=budget_cache)
        else:
            if context['financial'] is None:
                import financial_plan as FP
                market=FP.retention_market(league)
                context['financial']=(FP.snapshot(league,team,market=market),market)
            before,market=context['financial']
            budget = EXT._retention_budget(league,team,player,preview,
                                          benefit=benefit,before=before,market=market)
        row['financial_reason']=budget['reason']
        if budget['approved']:
            row['affordable']=True; break
    # Legal cap accounting reads signed contracts and pending offer holds,
    # not a hypothetical draft-pick inventory. Keep this proof in the local
    # context only; funded-roster/flexibility refusals remain pick-dependent.
    context['legal_extension_possible'] = legal_extension_possible
    ratio = apy/max(.01,floor)
    probability = max(.05,min(.9,.55+(ratio-1.)*2.+.12*row['role_share']))
    # A player can defer talks until the offseason without destroying a
    # buyer's intention to negotiate then. A closed negotiation is different.
    deferred = bool(refusal and 'during the season' in refusal)
    if refusal and not (acquisition and deferred): probability = .15 if deferred else .05
    if not row['affordable']: probability = .05
    row['extension_probability']=round(probability,3)
    # The reservation price buys the same remaining service and cash as the
    # trade quote. Completed seasons and calendar stubs are not extra control.
    # Use neutral pricing here; seller attachment and lost roles remain separate.
    from trades import player_asset
    def trade_floor():
        asset = player_asset(league,team,player,pool,None)
        if not asset: return 0.
        fraction = .5 if asset['valued_contract_years'] <= 1 else .75
        return round(max(0.,asset['trade_value'])*fraction,2)
    row['trade_floor'] = unchanged('trade_floor', trade_floor)
    retain = (row['important'] and row['affordable'] and ratio>=(1. if acquisition else .90)
              and probability>=.35 and row.get('veteran_viable',True))
    if retain:
        row['decision']='retain'; row['reasons']=['valuable_role','viable_extension']
        if 'veteran_viable' in row: row['reasons'].append('short_term_veteran')
    elif (c and c.years>0 and trading_open(league) and row['trade_floor']>.25
          and (window in ('rebuilding','retooling') or row['departure_loss']<=6.)
          and window not in ('contending','win_now')):
        row['decision']='shop'; row['reasons']=['unlikely_extension','seek_fair_return']
    elif c and c.years>0 and row['role_share']>=.15 and window in ('contending','win_now','middling'):
        row['decision']='retain'; row['reasons']=['keep_for_current_run','revisit_after_season']
    else:
        row['reasons']=['replacement_or_future_flexibility']
    if refusal: row['reasons'].append('agent_defers' if 'during the season' in refusal else 'agent_declines')
    if not row['affordable']: row['reasons'].append(row['financial_reason'])
    if ratio<(1. if acquisition else .90): row['reasons'].append('price_gap')
    if row.get('veteran_viable') is False: row['reasons'].append('prefer_veteran_replacement')
    return row


def choices(league, team):
    """Cheap saved decisions, invalidated by ownership or contract changes."""
    found={}; seen=set()
    owned={p.pid:p for p in team.active()}
    for e in reversed(getattr(league,'transactions',())):
        if e.get('kind')!='cpu_retention_decision' or e.get('team')!=team.abbr or e.get('year')!=league.year: continue
        pid=e.get('pid')
        if pid in seen: continue
        seen.add(pid)
        p=owned.get(pid)
        if not p: continue
        c=p.contract
        if e.get('contract_years')!=(c.years if c else 0) or e.get('contract_signed')!=(c.signed if c else None): continue
        found[pid]={k:v for k,v in e.items() if k not in ('kind','year','week','phase')}
    return list(found.values())


def record(league, row, stage=None):
    review_stage=stage or globals()['stage'](league)
    material=(row['decision'],tuple(row['reasons']),round(row.get('expected_apy',0)/2.),
              row.get('contract_years'),row.get('contract_signed'))
    for e in reversed(getattr(league,'transactions',())):
        if (e.get('kind')=='cpu_retention_decision' and e.get('year')==league.year
            and e.get('team')==row['team'] and e.get('pid')==row['pid'] and e.get('review_stage')==review_stage):
            old=(e['decision'],tuple(e['reasons']),round(e.get('expected_apy',0)/2.),
                 e.get('contract_years'),e.get('contract_signed'))
            if old==material and ('extension_result' not in row
                    or e.get('extension_result')==row['extension_result']): return False
            break
    league.log('cpu_retention_decision',review_stage=review_stage,**row)
    return True


def refresh(league, team, pool=None, stage=None):
    """One plan per unchanged calendar/roster state, outside trade pair loops."""
    if team.abbr==getattr(league,'user_team',None) or not team.gm: return []
    review_stage=stage or globals()['stage'](league)
    signature=(league.year,review_stage,league.phase,league.week,getattr(league,'game_date',None),
        tuple(team.record),round(team.cap_space,1),
        repr(vars(team.gm)),
        tuple((e.get('pid'),e.get('state'),e.get('broken_until'))
              for e in (getattr(league,'negotiations',None) or []) if e.get('team')==team.abbr),
        tuple((p.pid,p.contract.years if p.contract else 0,p.contract.signed if p.contract else None,
               round(p.apy,1),round(p.ovr,1),p.out_until) for p in team.active()))
    cache=getattr(team,'_retention_review_signature',None)
    if signature==cache: return choices(league,team)
    report=RN.assess(team);scale=DFT.position_scale(league)
    context=_review_context(league,team,report,scale)
    if pool is None: pool=VAL.pool_from_league(league)
    for p in report['players']:
        if p.contract and p.contract.years>1: continue
        inputs,benefit=_role_read(league,team,p,report,scale)
        context['inputs'][p.pid]=(inputs,benefit)
        if not inputs['important']: continue
        record(league,assess(league,team,p,pool,report,scale,_context=context),review_stage)
    team._retention_review_signature=signature
    return choices(league,team)

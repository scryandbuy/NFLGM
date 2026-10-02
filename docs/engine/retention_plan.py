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
    replacement = own[rank+1].ovr if rank+1 < len(own) else min((p.ovr for p in reserves), default=55.)
    important = share >= .15 or loss >= 2. or RN.retention_value(team, player) >= 2.
    return dict(role_share=round(share,4), roles=sorted({r['role'] for r in rows}),
        departure_loss=round(loss,4), replacement_grade=round(replacement,3),
        normalized_grade=round(normalized,3), important=important,
        importance=round(3.*loss + 12.*share + (normalized-75.)*.7,4))


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
        if p.age > EXT.AGE_LIMIT.get(p.pos,31)+2: continue
        out.append((p,row))
    # Resolve contracts that have actually expired before buying optional
    # extra control on men who will already be here next season.
    return sorted(out,key=lambda pr:((pr[0].contract.years if pr[0].contract else 0)
                  if league.phase in ('offseason','free_agency') else 0,
                  -pr[1]['importance'],str(pr[0].pid)))


def assess(league, team, player, pool=None, baseline=None, scale=None):
    import extensions as EXT
    import contract_offer as CO
    from development_value import player_credit
    from trade_calendar import trading_open
    row = role_inputs(league,team,player,baseline,scale)
    c = player.contract
    row.update(team=team.abbr,pid=player.pid,decision='let_walk',reasons=[],
        expected_apy=0.,offer_apy=0.,years=0,extension_probability=0.,
        affordable=False,financial_reason='no_market_read',trade_floor=0.,
        contract_years=c.years if c else 0,contract_signed=c.signed if c else None)
    if player.team != team.abbr or player.retired or not EXT.ai_eligible(player,league):
        row['reasons']=['not_eligible']; return row
    tm = EXT.terms(league,player,None,pool=pool)
    if not tm:
        row['reasons']=['no_market_read']; return row
    want = .75 + .25*row['role_share'] - .10*max(0.,team.gm.youth-.5)*(player.age>=28)
    ceiling = tm['offer']*(1.+.12*want)
    apy = round(min(ceiling,tm['ask']),2)
    floor = tm['ask']*(1.-tm['discount'])
    row.update(expected_apy=round(tm['ask'],2),offer_apy=apy,years=tm['years'])
    refusal = EXT._ai_refusal(league,player)
    # Evaluate the same bounded payment alternatives as the negotiator; never
    # declare someone unaffordable solely because the first schedule misses.
    original = CO.canonical(league,player,team,dict(apy=apy,years=tm['years']),'extension')
    total = apy*tm['years']; bonus = min(total*.78,original['bonus']+total*.10)
    packages = [original,dict(original,front_load=.5),dict(original,front_load=.85),
                dict(original,front_load=.5,bonus=min(bonus,total*.445))]
    for package in packages:
        if not EXT.can_afford_extension(league,team,player,apy,tm['years'],
                                       package['front_load'],package['bonus']):
            row['financial_reason']='legal_cap_failure'; continue
        preview = EXT.build(player,tm['years'],apy,CAP.get(league.year,301.2),team.gm,league,
                            front_load=package['front_load'],bonus=package['bonus'])
        budget = EXT._retention_budget(league,team,player,preview)
        row['financial_reason']=budget['reason']
        if budget['approved']:
            row['affordable']=True; break
    ratio = apy/max(.01,floor)
    probability = max(.05,min(.9,.55+(ratio-1.)*2.+.12*row['role_share']))
    if refusal: probability = .15 if 'during the season' in refusal else .05
    if not row['affordable']: probability = .05
    if player.age > EXT.AGE_LIMIT.get(player.pos,31): probability *= .7
    row['extension_probability']=round(probability,3)
    value = VAL.value_player(league,player,side='team',pool=pool,rng=None)
    if value and c and c.years>0:
        asset=dict(age=player.age,apy=player.apy,ovr=player.ovr,madden_position=player.pos,
                   contract_years_left=c.years,development_credit=player_credit(player))
        row['trade_floor']=round(max(0.,TE.trade_value(asset,value))*(.5 if c.years==1 else .75),2)
    context = team.ctx()
    if 'games_played' not in context: context=dict(context,**TE.race_context(team))
    window = TE.window(context)
    retain = (row['important'] and row['affordable'] and ratio>=.90
              and probability>=.35 and player.age<=EXT.AGE_LIMIT.get(player.pos,31)+1)
    if retain:
        row['decision']='retain'; row['reasons']=['valuable_role','viable_extension']
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
    if ratio<.90: row['reasons'].append('price_gap')
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
    if pool is None: pool=VAL.pool_from_league(league)
    for p in report['players']:
        if p.contract and p.contract.years>1: continue
        inputs=role_inputs(league,team,p,report,scale)
        if not inputs['important']: continue
        record(league,assess(league,team,p,pool,report,scale),review_stage)
    team._retention_review_signature=signature
    return choices(league,team)

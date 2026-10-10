"""Read a save; compare negotiations on disposable in-memory state only."""
import argparse
import copy
import gzip
import itertools
import json
from pathlib import Path

import contract_offer as CO
import negotiation_discussions as ND
import negotiation_engine as NE
import negotiations as NG
import trades as TR
import trade_engine as TE
import valuation as VAL
import views_personnel as VP
from session import Session
from test_negotiation_discussions import DiscussionTests


def contracts():
    rows = []
    for profile in NE.ARCHETYPES:
        case = DiscussionTests(); case.setUp(); case.profile(profile)
        L, t, p = case.L, case.t, case.p
        ND.player_reply(L, t, 'priorities')
        line = t['discussion']['log'][-1]['text']
        ND.player_reply(L, t, 'finish'); ND.player_reply(L, t, 'proposal')
        offer = CO.canonical(L, p, L.teams['GB'], dict(apy=18, years=3), 'extension')
        NG._answer(L, t, p, offer, 22, quiet=True)
        rounds = []
        for _ in range(4):
            c = copy.deepcopy(t.get('counter'))
            rounds.append(dict(state=t['state'], counter=c, final=t.get('final_offer', False)))
            if not c or t.get('final_offer'): break
            r = NG.make_offer(L, t['id'], c['apy'] * .99, c['years'], bonus=c['bonus'], front_load=c['front_load'], promises=c['promises'])
            assert r['ok'], r
        # A material change in what the player values, unlike repeating a
        # smaller cash offer, can earn acceptance below the standing counter.
        fresh = DiscussionTests(); fresh.setUp(); fresh.profile(profile)
        l2, t2, p2 = fresh.L, fresh.t, fresh.p
        first = CO.canonical(l2, p2, l2.teams['GB'], dict(apy=18, years=3), 'extension')
        NG._answer(l2, t2, p2, first, 22, quiet=True)
        c = copy.deepcopy(t2['counter']); improved = dict(c, apy=round(c['apy'] * .98, 2), promises=['no_trade'])
        assessment = NG._assessment(l2, p2, t2, improved)
        with_commitment = NG._counter_package(l2,p2,t2,dict(c,promises=['no_trade']))['apy']
        p2.xp_spent['_negotiation_profile']['trust'] = .4
        low_trust = NG._counter_package(l2,p2,t2,dict(c,promises=['no_trade']))['apy']
        p2.xp_spent['_negotiation_profile']['trust'] = 1.
        reply = NG.make_offer(l2, t2['id'], **{k:improved[k] for k in ('apy','years','bonus','front_load','promises')})
        rows.append(dict(profile=profile, priorities=line, rounds=rounds,
                         changed_terms=dict(before=c,offer=improved,ratio=assessment['ratio'],result=reply, state=t2['state'],
                                            commitment_floor=with_commitment,low_trust_floor=low_trust)))
    return rows


def pick_boundaries(L, me, mine, pool):
    """Cheaply find real owned packages near a price boundary, then run guards."""
    rows=[]
    combos=[list(c) for n in (1,2,3) for c in itertools.combinations(mine,n)]
    a=L.teams[me]
    for other in ('BAL','MIN'):
        b=L.teams[other]
        targets=[p for p in b.picks if not p.used_on and p.round in (1,2)][:4]
        for pk in targets:
            target=VP._pick_row(L,pk)['id']; L.trade_discussions={}
            assert ND.start_trade(L,me,other,target,'acquire')['ok']
            for choice in ('picks','finish','proposal'): assert ND.trade_reply(L,me,other,choice)['ok']
            d=ND.trade_state(L,me,other); give=d['concession']
            base=TR.persona(b.gm); good=ND.trade_persona(L,me,other,[mine[0]],[target])
            price=lambda asset,gm,owns: TE.team_price(asset,b.ctx(),b.cap_space,gm,owns=owns)
            outgoing={pid:price(TR.pick_asset(L,VP._find_pick(L,me,pid)),base,False) for pid in mine}
            asset=TR.pick_asset(L,pk); before=price(asset,base,True); after=price(asset,good,True)
            close=sorted(combos,key=lambda ids:abs(sum(outgoing[i] for i in ids)-(before+after)/2-.5))[:12]
            football_cache={};financial_cache={}
            for sends in close:
                d['concession']=0
                old=VP._evaluate(L,me,other,sends,[target],pool=pool,football_cache=football_cache,financial_cache=financial_cache)
                d['concession']=give
                new=VP._evaluate(L,me,other,sends,[target],pool=pool,football_cache=football_cache,financial_cache=financial_cache)
                rows.append(dict(team=other,target=target,sends=sends,price_before=before,price_after=after,before=old,after=new))
        print('PICK BOUNDARIES',other,'accepted changes',sum(x['before']['would_accept']!=x['after']['would_accept'] for x in rows if x['team']==other),flush=True)
    return rows


def run(save):
    with gzip.open(save, 'rt', encoding='utf-8') as f: s = Session.load(f.read())
    L = s.L; me = s.user_team; team = L.teams[me]
    rng_before = copy.deepcopy(s.rng.bit_generator.state)
    transactions_before = len(L.transactions)
    result = dict(source=Path(save).name, year=L.year, week=L.week, team=me,
                  active=len(team.active()), cap_space=team.cap_space,
                  injuries=[dict(pid=p.pid,name=p.name,pos=p.pos,out_until=p.out_until,on_ir=p in team.ir) for p in team.roster if p.out_until],
                  contracts=contracts(), trades=[])
    pool = VAL.pool_from_league(L)
    mine = [VP._pick_row(L,p)['id'] for p in team.picks if not p.used_on and p.year >= L.year]
    mine = mine[:14]
    packages = [[p] for p in mine] + [list(p) for p in itertools.combinations(mine[:7],2)]
    for other in ('BAL','BUF','MIN','SF'):
        them=L.teams[other]
        candidates=sorted([p for p in them.active() if p.out_until is None and p.pos in ('WR','HB','CB')],key=lambda p:p.ovr,reverse=True)
        targets=[candidates[0],candidates[-1]]
        for p in targets:
            L.trade_discussions={}
            r=ND.start_trade(L,me,other,p.pid,'acquire'); assert r['ok'],r
            ND.trade_reply(L,me,other,'needs'); ND.trade_reply(L,me,other,'picks')
            ND.trade_reply(L,me,other,'finish'); ND.trade_reply(L,me,other,'proposal')
            d=ND.trade_state(L,me,other)
            saved=copy.deepcopy(d)
            row=dict(team=other,gm=TR.persona(them.gm),window=TE.window(them.ctx()),
                     target=dict(pid=p.pid,name=p.name,pos=p.pos,age=p.age,ovr=p.ovr,years=p.contract.years,hit=p.cap_hit(0),status=TR.seller_willingness(them,p)),
                     concession=d['concession'],dialogue=d['log'],packages=[])
            football_cache={}; financial_cache={}
            for sends in packages:
                d['concession']=0
                before=VP._evaluate(L,me,other,sends,[p.pid],pool=pool,football_cache=football_cache,financial_cache=financial_cache)
                d['concession']=saved['concession']
                after=VP._evaluate(L,me,other,sends,[p.pid],pool=pool,football_cache=football_cache,financial_cache=financial_cache)
                row['packages'].append(dict(sends=sends,before=before,after=after))
            assert not ND.trade_reply(L,me,other,'picks')['ok']
            assert ND.trade_state(L,me,other)['concession']==saved['concession']
            result['trades'].append(row)
            print(other,p.name,'concession',saved['concession'],'accept changes',sum(x['before']['would_accept']!=x['after']['would_accept'] for x in row['packages']),flush=True)
    result['pick_boundaries']=pick_boundaries(L,me,mine,pool)
    result['transactions_unchanged']=len(L.transactions)==transactions_before
    result['rng_unchanged']=s.rng.bit_generator.state==rng_before
    assert result['transactions_unchanged'] and result['rng_unchanged']
    flip=next((x for x in result['pick_boundaries'] if not x['before']['would_accept'] and x['after']['would_accept']),None)
    if flip:
        # One separate controlled execution on the disposable memory copy:
        # verify the actual Propose owner, not only its preview, honors the deal.
        L.trade_discussions={}
        assert ND.start_trade(L,me,flip['team'],flip['target'],'acquire')['ok']
        for choice in ('picks','finish','proposal'): assert ND.trade_reply(L,me,flip['team'],choice)['ok']
        executed=VP.act_propose(L,me,flip['team'],flip['sends'],[flip['target']])
        result['controlled_trade_execution']=dict(case=flip,result=executed,
            received=VP._find_pick(L,me,flip['target']) is not None,
            sent=all(VP._find_pick(L,flip['team'],x) is not None for x in flip['sends']),week_after=L.week)
        assert executed['ok'] and result['controlled_trade_execution']['received'] and result['controlled_trade_execution']['sent'],executed
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('save');parser.add_argument('output');a=parser.parse_args()
    Path(a.output).write_text(json.dumps(run(a.save),indent=2,default=str),encoding='utf-8')


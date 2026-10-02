"""Observe real CPU extension decisions without changing their offers or RNG."""
import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
from unittest.mock import patch
import numpy as np
import session as SS
import extensions as EXT
import contract_offer as CO
import market as MK
from cap_engine import CAP
from cap_accounting import next_year_ledger, require_room


def fits(L, team, p, package):
    """Actual cap validation plus the CPU's existing future-budget guard."""
    c = EXT.build(p, package['years'], package['apy'], CAP[L.year], team.gm, L,
                  front_load=package['front_load'], bonus=package['bonus'])
    try:
        require_room(L, team, p.pid, c)
    except ValueError as exc:
        return False, str(exc)
    def charge(contract, i):
        if contract is None: return 0.
        if i < contract.years: return contract.cap_hit(i)
        return contract.remaining_proration(i) if i == contract.years else 0.
    for i in range(1, c.years + 1):
        if i == 1:
            limit, committed, _, _ = next_year_ledger(L, team)
        else:
            limit = CAP.get(L.year+i, CAP[L.year] * 1.055**i)
            committed = sum(charge(q.contract, i) for q in team.roster)
        old, new = charge(p.contract, i), charge(c, i)
        if committed-old+new > limit+.0005 and new > old+.0005:
            return False, f'Projected cap in {L.year+i}'
    return True, None


def audit(source, seed, full_market=False):
    raw = source.read_bytes()
    s = SS.Session.load(raw.decode('utf8')); s.rng = np.random.default_rng(seed)
    L = s.L; L.negotiations = []
    rows, quotes, current = [], {}, {}
    original_terms, original_assess, original_extend = EXT.terms, CO.assess, EXT.extend

    def terms(*args, **kwargs):
        result = original_terms(*args, **kwargs)
        quotes[args[1].pid] = copy.deepcopy(result)
        return result

    def assess(*args, **kwargs):
        result = original_assess(*args, **kwargs)
        if current:
            current['assessment'] = copy.deepcopy(result)
        return result

    def extend(league, pid, apy, years, *args, **kwargs):
        p = league.player(pid); team = league.teams[p.team]
        current.update(pid=pid, name=p.name, team=p.team, pos=p.pos, age=round(p.age,1),
            ovr=round(p.ovr,1), remaining_years=p.contract.years if p.contract else 0,
            offered_apy=float(apy), offered_years=years,
            initial_quote=copy.deepcopy(quotes.get(pid)), cap_space=team.cap_space,
            morale=round(p.morale.value,1) if p.morale else None)
        result = original_extend(league, pid, apy, years, *args, **kwargs)
        current.update(outcome=result['result'], reason=result.get('why'),
                       final_quote=copy.deepcopy(quotes.get(pid)))
        if result['result'] == 'countered' and 'assessment' in current:
            a = current['assessment']; ref = a['reference_package']; offer = a['package']
            state = copy.deepcopy(s.rng.bit_generator.state)
            alternatives = {}
            for label, proposal in (
                ('same_cash_even_salary', dict(offer, front_load=.5)),
                ('same_cash_earlier_salary', dict(offer, front_load=.85)),
                ('same_apy_neutral_package', dict(ref, apy=apy, years=years,
                    bonus=ref['bonus'] * apy * years / (ref['apy'] * ref['years']))),
                ('agent_reference_package', ref)):
                check = original_assess(league,p,team,proposal,ref['apy'],ref['years'],'extension')
                legal, why = fits(league,team,p,check['package'])
                alternatives[label] = dict(acceptable=bool(check['acceptable']), fits=legal, why=why,
                    ratio=check['ratio'], package=check['package'])
            assert state == s.rng.bit_generator.state
            current['alternatives'] = alternatives
        rows.append(copy.deepcopy(current)); current.clear()
        return result

    with patch.object(EXT,'terms',terms), patch.object(CO,'assess',assess), patch.object(EXT,'extend',extend):
        s.step_extensions()
    print(f'Seed {seed}: extension decisions {dict(Counter(r["outcome"] for r in rows))}',flush=True)
    if full_market:
        for phase in (1,2,3):
            MK.open_round(L,s.rng,phase,user_team=s.user_team)
            MK.resolve_round(L,s.rng,phase,user_team=s.user_team)
            print(f'Seed {seed}: completed FA round {phase}',flush=True)
        MK.close_market(L,s.rng,user_team=s.user_team)
        for row in rows:
            if row['outcome']=='accepted': continue
            p=L.player(row['pid']); c=p.contract
            row['after_market'] = dict(team=p.team, years=c.years if c else 0, apy=p.apy,
                                       contract_signed=c.signed if c else None, fa_class=p.fa_class)
    assert source.read_bytes() == raw
    rejected=[r for r in rows if r['outcome']=='countered']
    summary=dict(seed=seed,decisions=dict(Counter(r['outcome'] for r in rows)),
        countered_unique_players=len({r['pid'] for r in rejected}),
        same_cash_even_salary_accepted_and_affordable=sum(r['alternatives']['same_cash_even_salary']['acceptable'] and r['alternatives']['same_cash_even_salary']['fits'] for r in rejected),
        same_apy_neutral_accepted_and_affordable=sum(r['alternatives']['same_apy_neutral_package']['acceptable'] and r['alternatives']['same_apy_neutral_package']['fits'] for r in rejected),
        agent_reference_accepted_and_affordable=sum(r['alternatives']['agent_reference_package']['acceptable'] and r['alternatives']['agent_reference_package']['fits'] for r in rejected),
        moving_quotes=sum(r['initial_quote'] != r['final_quote'] for r in rows),
        full_market=full_market,source_untouched=True,source_sha256=hashlib.sha256(raw).hexdigest())
    return dict(summary=summary,rows=rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--save',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seed',type=int,required=True)
    parser.add_argument('--full-market',action='store_true')
    args=parser.parse_args()
    result=audit(args.save,args.seed,args.full_market)
    args.output.write_text(json.dumps(result,indent=2,default=lambda x:x.item())+'\n',encoding='utf8')
    print(json.dumps(result['summary']))

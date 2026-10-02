"""Read-only coach-transition probes on a save/checkpoint; prints JSON.

Owner choice is fixed to isolate installation of the proposed coach. No games,
transactions or RNG draws are written back to disk. This is a counterfactual
role/cutdown probe, not a prediction of hiring frequency or season outcomes.
"""
import argparse
import copy
import json
from unittest.mock import patch
import numpy as np
import coaching_pool as CP
import league as LG
import roster_needs as RN
import retention_plan as RP
import cutdown as CD


def audit(path, teams):
    with open(path,encoding='utf-8-sig') as source:
        raw=json.load(source)
    blob=raw.get('session',raw)
    result=[]
    for abbr in teams:
        L=LG.League.load(copy.deepcopy(blob));t=L.teams[abbr]
        before=RN.assess(t);coverage=RN.essential_coverage(t,report=before)
        front=before['front'];personnel=t.gm.off_personnel
        old_candidates={p.pid:r for p,r in RP.candidates(L,t)}
        incoming=copy.deepcopy(t.gm);incoming.name='Audit Transition Coach'
        incoming.def_front='3-4' if front!='3-4' else '4-3'
        incoming.off_personnel='12' if personnel!='12' else '10'
        ids={p.pid for p in t.roster};events=len(L.transactions)
        with patch.object(CP,'owner_hire',return_value=(incoming,{})):
            CP.fire_and_hire(L,t,np.random.default_rng(43))
        after=RN.assess(t);new_candidates={p.pid:r for p,r in RP.candidates(L,t)}
        keep=RN.select_cutdown(t,CD.rows_for(t),53)
        retained=[p for p in t.active() if p.pid in keep]
        final=RN.assess(t,retained)
        result.append(dict(team=abbr,old_front=front,new_front=incoming.def_front,
            old_personnel=personnel,new_personnel=incoming.off_personnel,
            same_roster_ids=ids=={p.pid for p in t.roster},
            events=L.transactions[events:],old_essential=coverage['shortages'],
            new_essential=RN.essential_coverage(t,report=after)['shortages'],
            cutdown_essential=RN.essential_coverage(t,report=final)['shortages'],
            cutdown_does_not_worsen=RN.coverage_not_worse(RN.essential_coverage(t,report=after),RN.essential_coverage(t,report=final)),
            retention_changes=[dict(pid=pid,old_share=old_candidates.get(pid,{}).get('role_share'),
                new_share=new_candidates.get(pid,{}).get('role_share'))
                for pid in sorted(set(old_candidates)|set(new_candidates))
                if old_candidates.get(pid,{}).get('role_share')!=new_candidates.get(pid,{}).get('role_share')]))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('save');parser.add_argument('--teams',nargs='+',default=['SEA','ATL','GB'])
    args=parser.parse_args()
    print(json.dumps(audit(args.save,args.teams),indent=2,default=str))

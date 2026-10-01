"""Real candidate identities, controlled successful coordinator recruitment."""
import copy,json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import league as LG,coaching_pool as CP,staff as STF

L=LG.build_league(rng=np.random.default_rng(93044));L.user_team='GB'
old=copy.deepcopy(L.teams['MIN'].gm); create=CP.make_candidate
fields=('def_front','off_personnel','off_blocking','coverage','shell','blitz')
identity=lambda g:{k:getattr(g,k) for k in fields}
results=[]
for seed in range(93044,93054):
    for take_first in (True,False):
        rng=np.random.default_rng(seed); L.teams['MIN'].gm=copy.deepcopy(old)
        co=NS(name='Study coordinator',team='GB',role='oc',prestige=100,age=45,rating=99,unit_ranks=[1,1])
        L.teams['GB'].staff={'oc':co}; L.pending_hires={};L.poaches=[]
        fallback=create(rng);fallback.name='Fallback';fallback.reputation=0;fallback.prestige=1
        L.coach_pool=[fallback];generated=[]
        def record(*args,**kwargs):
            g=create(*args,**kwargs); generated.append(g);return g
        with patch.object(CP,'coordinators_as_candidates',return_value=[co]),patch.object(CP,'make_candidate',side_effect=record),patch.object(CP,'roster_fit',return_value=(0,[])),patch.object(STF,'ask',return_value=1),patch.object(STF,'budget',return_value=100),patch.object(STF,'payroll',return_value=0),patch.object(STF,'poach_request',return_value={'id':'study','state':'open'}):
            hired,reason=CP.owner_hire(L,L.teams['MIN'],rng)
            assert hired is None and reason.get('pending'),reason
            evaluated=identity(generated[0]) if take_first else identity(fallback)
            installed=CP.complete_pending_hire(L,'MIN',rng,take_first)
        results.append(dict(seed=seed,take_first=take_first,evaluated=evaluated,installed=identity(installed),changed=evaluated!=identity(installed)))
Path('../../outputs/pending-coach-identities.json').write_text(json.dumps(results,indent=2))
print(json.dumps(dict(first_changed=sum(r['changed'] for r in results if r['take_first']),second_changed=sum(r['changed'] for r in results if not r['take_first']),samples_per_path=10,example=results[0]),indent=2))

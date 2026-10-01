"""Reproduce immediate/pending hire conversion-hook asymmetry without edits."""
import copy, json
from unittest.mock import patch
import numpy as np
import league as LG, coaching_pool as CP, position_change as PC

rng=np.random.default_rng(93042)
league=LG.build_league(rng=rng)
incoming=copy.deepcopy(league.teams['GB'].gm)
incoming.name='Controlled coach'; incoming.background='former head coach'; incoming.def_front='3-4'
league.teams['GB'].identity={'old':'identity'}
with patch.object(CP,'owner_hire',return_value=(incoming,{})), patch.object(PC,'convert_misfits',return_value=[]) as convert:
    CP.fire_and_hire(league,league.teams['GB'],rng)
    immediate=convert.call_count
second=copy.deepcopy(incoming); second.name='Second choice'
CP.pool(league).append(second)
league.pending_hires={'MIN':dict(second=second.name)}
league.teams['MIN'].identity={'old':'identity'}
with patch.object(PC,'convert_misfits',return_value=[]) as convert:
    CP.complete_pending_hire(league,'MIN',rng,take_first=False)
    pending=convert.call_count
print(json.dumps(dict(seed=93042,immediate_conversion_calls=immediate,pending_conversion_calls=pending,
    immediate_identity_reset=league.teams['GB'].identity is None,pending_identity_reset=league.teams['MIN'].identity is None)))

# The delayed coordinator route stores no evaluated candidate object. Verify it
# calls the random generator again rather than retaining the assessed identity.
from types import SimpleNamespace
league.teams['GB'].staff={'oc':SimpleNamespace(name='Pending OC',prestige=40,age=45,rating=80)}
league.pending_hires={'ATL':dict(first='Pending OC',first_from=['GB','oc'],second=None)}
replacement=copy.deepcopy(incoming); replacement.def_front='4-3'; replacement.off_personnel='10'
with patch.object(CP,'make_candidate',return_value=replacement) as generator:
    hire=CP.complete_pending_hire(league,'ATL',rng,take_first=True)
print(json.dumps(dict(pending_regenerates_identity=bool(generator.call_count),installed_front=hire.def_front,installed_personnel=hire.off_personnel)))

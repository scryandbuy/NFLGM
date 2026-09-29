import copy
from session import Session
import newgens
s=Session.new('GB',seed=23)
assert all(p.potential is not None for p in s.L.players.values() if p.potential_range)
rng=copy.deepcopy(s.rng.bit_generator.state)
a=s.progression(); s.progression(); s.development(a['rows'][0]['pid'])
assert rng==s.rng.bit_generator.state, 'views consumed random state'
saved=s.save(); loaded=Session.load(saved)
assert loaded.rng.bit_generator.state==s.rng.bit_generator.state
assert {p.pid:p.potential for p in s.L.players.values()}=={p.pid:p.potential for p in loaded.L.players.values()}
print('PASS: new league and draft potential fixed; repeated views preserve RNG; save/load preserves potential and RNG')

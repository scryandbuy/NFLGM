"""Read a copied franchise and export its read-only view for browser inspection."""
import hashlib
import json
from pathlib import Path
import time
from session import Session

out = Path('outputs/upcoming-fa'); out.mkdir(parents=True, exist_ok=True)
source = Path('C:/Users/HP/Downloads/nflgm-2033-week-4.json')
session = Session.load_file(source)
before = repr(session.rng.bit_generator.state)
start = time.perf_counter()
view = session.personnel('upcoming_free_agents')
elapsed = time.perf_counter() - start
assert before == repr(session.rng.bit_generator.state)
assert view['market_year'] == 2034
expected = {p.pid for t in session.L.teams.values() for p in t.roster
            if not p.retired and p.team == t.abbr and p.contract and p.contract.years == 1}
assert {r['pid'] for r in view['rows']} == expected
for row in view['rows']:
    p = session.L.player(row['pid'])
    assert row['age'] == int(p.age)
    assert row['hit'] == round(p.cap_hit(0), 1)
    assert row['fa_class'] in ('UFA', 'RFA')
(out/'view.json').write_text(json.dumps(view), encoding='utf-8')
report = dict(source=source.name, year=session.L.year, phase=session.L.phase,
              market_year=view['market_year'], players=view['count'],
              teams=len({r['team'] for r in view['rows']}), seconds=round(elapsed, 3),
              rng_unchanged=True, exact_contract_membership=True,
              all_current_ages_and_cap_hits_match=True, sample=view['rows'][:8])
(out/'audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))

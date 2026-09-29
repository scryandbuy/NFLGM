import math,copy
import numpy as np
from league import build_league,League
from session import Session
import views_frontoffice as VF
from cap_accounting import settle_week,next_year_ledger
L=build_league(rng=np.random.default_rng(17)); s=Session(L,np.random.default_rng(17),'GB')
for abbr,t in L.teams.items():
    t.sync_cap()
    assert math.isfinite(t.cap_space)
    v=VF.cap(s,L,abbr)
    assert abs(v['years'][0]['committed']-t.cap.charges(t.phase))<=.051,(abbr,v['years'][0])
    import views
    portal=views._cap(L,t)
    for index,row in enumerate(v['years']):
        assert portal['years'][index]['cap']==row['limit']
        assert portal['years'][index]['committed']==row['committed']
    for p in t.roster:
        if p.contract:
            c=copy.deepcopy(p.contract); total=c.sb; booked=0
            while c.years>0:
                booked+=c.bonus_at(0); c.advance()
            assert abs(total-booked-c.sb)<1e-7
# Weekly earnings and reload cannot alter combined accounting.
L.set_phase('regular'); settle_week(L,1)
loaded=League.load(L.save())
for abbr,t in L.teams.items():
    assert abs(t.cap_space-loaded.teams[abbr].cap_space)<.001
    assert loaded.teams[abbr].cap.paid_week==1
print('PASS: 32 teams, cap views, all seeded bonus schedules, weekly settlement and full save/reload')

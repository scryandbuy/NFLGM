import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import practice_squad as PS
from cap_engine import Contract

class RosterReviewTests(unittest.TestCase):
    def test_two_clubs_cannot_sign_the_same_cached_free_agent(self):
        def player(pid, ovr, team):
            return NS(pid=pid,pos='WR',ovr=ovr,team=team,ratings={},out_until=None,
                      retired=False,apy=1,accrued=2,contract=None,xp_spent={},dead_if_cut=lambda _:0)
        free=player('free',90,None)
        clubs={abbr:NS(gm=NS(),cap_space=100,ps=[],active=lambda q=player(abbr,60,abbr):[q]*50)
               for abbr in ('AAA','AAE')}
        released=[]
        league=NS(phase='regular',year=2026,teams=clubs,free_agents=['free'],player=lambda _:free,
                  release=lambda pid:released.append(pid),log=lambda *a,**k:None)
        def sign(pid,abbr,contract,**kw):
            free.team=abbr;free.contract=contract
        league.sign=sign
        with patch.object(PS,'protected',return_value=False),patch.object(PS,'locked',return_value=False), \
             patch.object(PS,'shunned',return_value=False),patch.object(PS,'squad',side_effect=lambda t:t.ps), \
             patch('gm_engine.scheme_fit',return_value=0),patch.object(PS.MS,'minimum_salary',return_value=1), \
             patch.object(PS,'minimum_contract',return_value=Contract(1,[1])), \
             patch('cap_accounting.require_room'), patch.object(PS,'_cpu_move_budget',return_value=True), \
             patch('valuation.pool_from_league', return_value=None), \
             patch('replacement_contracts.minimum_acceptance', return_value={'accepts': True}):
            moves=PS.roster_review(league,None,1)
        self.assertEqual(len(moves),1)
        self.assertEqual(released,['AAA'])
        self.assertEqual(free.team,'AAA')
        self.assertEqual(league.free_agents,[])

if __name__=='__main__':unittest.main()

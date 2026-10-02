import unittest
from types import SimpleNamespace
from unittest.mock import patch
import market as M

class FaFillUserControl(unittest.TestCase):
    def fixture(self, user='GB'):
        def team():
            return SimpleNamespace(active=lambda:[], cap_space=50,
                                   by_pos=lambda pos:[], sync_cap=lambda:None)
        L=SimpleNamespace(year=2028,user_team=user,teams={'GB':team(),'DEN':team()})
        pool=[SimpleNamespace(pid='FA1',ovr=70,pos='WR',accrued=3)]
        return L,pool
    def run_fill(self,L,pool,**kwargs):
        with patch('roster_needs.assess',return_value={'needs':{'WR':1}}), patch.object(M,'sign') as sign:
            count=M.fill_out_rosters(L,pool,None,**kwargs)
            return count,[call.args[2].team for call in sign.call_args_list]
    def test_saved_user_excluded_cpu_still_signs(self):
        L,pool=self.fixture()
        self.assertEqual(self.run_fill(L,pool),(1,['DEN']))
    def test_explicit_user_excluded_without_saved_user(self):
        L,pool=self.fixture(None)
        self.assertEqual(self.run_fill(L,pool,user_team='GB'),(1,['DEN']))
    def test_user_only_league_leaves_pool_unchanged(self):
        L,pool=self.fixture();L.teams.pop('DEN')
        original=list(pool)
        self.assertEqual(self.run_fill(L,pool),(0,[]))
        self.assertEqual(pool,original)
    def test_unmanaged_simulation_can_fill_all_teams(self):
        L,pool=self.fixture(None)
        self.assertEqual(self.run_fill(L,pool),(1,['GB']))

if __name__=='__main__':unittest.main()

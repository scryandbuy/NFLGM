import unittest
from types import SimpleNamespace as NS
import fa_window as F
from offseason_calendar import STEPS
from league import League
import market
import practice_squad as PS
import negotiations

class FAWindow(unittest.TestCase):
    def test_calendar_and_saved_lock(self):
        L=League(2030); L.phase='offseason'
        for index in range(len(STEPS)):
            F.sync(NS(L=L,stop=('offseason',index),OFFSEASON=STEPS))
            self.assertEqual(F.closed(L),8<=index<=10)
        F.set_closed(L,True)
        self.assertTrue(F.closed(League.load(L.save())))
        L.year+=1
        self.assertFalse(F.closed(L))
    def test_all_team_signing_and_pool_guards(self):
        L=League(2030); L.phase='offseason'; F.set_closed(L,True)
        L.free_agents=['test']
        for team in ('GB','PIT'):
            with self.assertRaisesRegex(ValueError,'reopens after the draft'):
                L.sign('test',team,None)
            with self.assertRaisesRegex(ValueError,'reopens after the draft'):
                market.sign(L,None,NS(team=team),300)
            self.assertFalse(PS.sign_to_squad(L,team,'test')['ok'])
        self.assertEqual(market._pool(L),[])
        self.assertEqual(PS.available_free_agents(L),[])
        self.assertFalse(negotiations.open_talks(L,'test','fa')['ok'])
    def test_finish_reopens_only_after_undrafted_added(self):
        from draft_day import Draft
        L=League(2030); L.phase='offseason'; F.set_closed(L,True)
        p=NS(pid='rookie',draft_round=1,draft_overall=1)
        L.draft_pool=[p]; L.free_agents=[]
        Draft._finish(NS(L=L,taken=set()))
        self.assertIn('rookie',L.free_agents)
        self.assertFalse(F.closed(L))

if __name__=='__main__': unittest.main()

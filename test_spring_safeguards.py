import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import spring as SP
import scouting as SC
import views_draft as VD
from session import Session

class SpringSafeguards(unittest.TestCase):
    def league(self, news):
        return SimpleNamespace(year=2028, phase='free_agency', season_closed_year=2027,
                               spring_news=news, user_visits=['p1'])
    def test_repeat_does_not_consume_rng_or_rebuild_class(self):
        L=self.league([dict(year=2028,kind='complete',event='spring')])
        rng=np.random.default_rng(7); before=copy.deepcopy(rng.bit_generator.state)
        self.assertTrue(SP.run_spring(L,rng)['already_completed'])
        s=Session.__new__(Session);s.L=L;s.rng=rng
        s.step_spring()
        self.assertEqual(rng.bit_generator.state,before)
        self.assertEqual(len(L.spring_news),1)
    def test_legacy_and_new_completion_lock_add_and_cancel(self):
        for event,kind in [('spring','complete'),('visits','stock'),('pro days','stock')]:
            L=self.league([dict(year=2028,event=event,kind=kind)])
            for pid in ('p1','p2'):
                self.assertFalse(VD.act_visit(None,L,'GB',pid)['ok'])
            with self.assertRaises(ValueError):SP.set_user_visits(L,['p2'])
            self.assertEqual(L.user_visits,['p1'])
    def test_early_event_does_not_lock_visits(self):
        L=self.league([dict(year=2028,event='Senior Bowl',kind='event')])
        self.assertFalse(VD._spring_done(L))
        self.assertEqual(SP.set_user_visits(L,['p2','p2']),['p2'])
    def test_fallback_calls_shared_event_with_current_spring_year(self):
        L=self.league([]);L.scouting={}
        with patch.object(SC,'senior_bowl',return_value=[]) as shared:
            self.assertEqual(SP.senior_bowl(L,None),(0,[]))
        shared.assert_called_once_with(L,None,event_year=2028)
    def test_old_class_completion_does_not_block_new_class(self):
        L=self.league([dict(year=2027,event='spring',kind='complete')])
        self.assertFalse(SP.completed(L))

    def test_workouts_leave_a_visit_window_before_spring_is_complete(self):
        L=self.league([dict(year=2028,event='pre_visits',kind='stage')])
        self.assertTrue(SP.pre_visits_completed(L))
        self.assertFalse(SP.completed(L))
        SP.set_user_visits(L,['p2'])
        self.assertEqual(L.user_visits,['p2'])

    def test_senior_bowl_invites_high_middle_and_lower_ranked_seniors(self):
        people=[SimpleNamespace(pid=f'p{i}',age=23,pos='WR',xp_spent={}) for i in range(180)]
        L=SimpleNamespace(year=2027,user_team=None,draft_pool=people,next_class=[],
                          consensus={p.pid:dict(rank=i+1) for i,p in enumerate(people)},
                          scouting={},teams={},spring_news=[])
        SC.senior_bowl(L,np.random.default_rng(17),event_year=2028)
        invited=[i for i,p in enumerate(people) if p.xp_spent.get('_senior_bowl')==2027]
        self.assertEqual(len(invited),110)
        self.assertGreater(sum(i<60 for i in invited),30)
        self.assertGreater(sum(60<=i<120 for i in invited),25)
        self.assertGreater(sum(i>=120 for i in invited),20)

if __name__=='__main__':unittest.main()

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

if __name__=='__main__':unittest.main()

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import spring as SP
import scouting as SC
import views_draft as VD
from session import Session
from test_cap_accounting import fixture, player

class SpringSafeguards(unittest.TestCase):
    def test_senior_bowl_flag_combines_attendance_and_legacy_news(self):
        L=fixture(); p=player(L,'prospect'); p.age=23
        L.scouting={'GB':{p.pid:dict(ovr=75,pot_lo=80,pot_hi=90)}}
        L.consensus={p.pid:dict(ovr=76,rank=20)}
        for marker,news,expected in [(True,True,1),(True,False,1),(False,True,1),(False,False,0)]:
            with self.subTest(marker=marker,news=news):
                p.xp_spent.pop('_senior_bowl',None)
                if marker: p.xp_spent['_senior_bowl']=L.year-1
                L.spring_news=[dict(pid=p.pid,event='Senior Bowl')] if news else []
                with patch.object(SC,'scheme_fit_view',return_value=0):
                    words=VD._prospect(L,'GB',p)['words']
                self.assertEqual(words.count('Senior Bowl'),expected)
                self.assertNotIn('Sr. Bowl',words)

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

    def test_visit_scheduling_is_open_only_at_private_visits_stop(self):
        L=self.league([dict(year=2028,event='pre_visits',kind='stage')])
        L.user_visits=[];L.draft_pool=[SimpleNamespace(pid='p2')];L.next_class=[]
        s=SimpleNamespace(stop=('offseason',9),OFFSEASON=Session.OFFSEASON)
        self.assertTrue(VD.act_visit(s,L,'GB','p2')['ok'])
        self.assertEqual(L.user_visits,['p2'])
        self.assertTrue(VD.act_visit(s,L,'GB','p2')['ok'])
        self.assertEqual(L.user_visits,[])
        s.stop=('offseason',10)
        self.assertFalse(VD.act_visit(s,L,'GB','p2')['ok'])

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

    def test_visit_improves_reports_without_changing_prospect_talent(self):
        league=fixture(); p=player(league)
        league.teams={'GB':league.teams['GB']}; league.user_team='GB'
        league.draft_pool=[p]; league.user_visits=[p.pid]
        league.consensus={p.pid:dict(rank=1)}
        p.traits={'work_ethic':55,'discipline':55}
        p.potential_range=(70,85)
        view=dict(e_phys=0.,e_skill=0.,e_pot=0.,reads=1.,flags=[],cert=.5,cert0=.35)
        SC._refresh(view,p)
        league.scouting={'GB':{p.pid:view}}
        import character_assessment as CA
        CA.background(p,'GB',view,{'character':'normal'},4.,1)
        before_error=CA.assessments(view)['work_ethic']['error']
        true_before=(p.ovr,copy.deepcopy(p.ratings),copy.deepcopy(p.traits),p.potential_range)
        with patch('draft.league_starter_level',return_value={}), patch.object(SC,'consensus',return_value={}):
            looks,_=SP.visits(league,np.random.default_rng(23))
        self.assertEqual(looks,1)
        self.assertAlmostEqual(SC.certainty(view),.575)
        self.assertLessEqual(CA.assessments(view)['work_ethic']['error'],before_error*.85)
        self.assertEqual((p.ovr,p.ratings,p.traits,p.potential_range),true_before)

if __name__=='__main__':unittest.main()

import unittest
from contextlib import ExitStack
from types import SimpleNamespace as N
from unittest.mock import patch
from test_cap_accounting import fixture, player
from season import SeasonRunner
import club_notes as CN

class PlayoffInjuryMail(unittest.TestCase):
    def run_game(self, week=19, injured=True, playoffs=True, win=True):
        L=fixture(); L.user_team='GB'; L.week=week
        p=player(L,'hurt'); r=SeasonRunner.__new__(SeasonRunner); r.L=L
        r.states={a:N(last_snaps={},snaps={},roster={}) for a in L.teams}
        res=dict(home=20 if win else 3,away=10,drives=[],injuries=[dict(player=p.pid,weeks_out=2,kind='ankle',season_ending=False)] if injured else [])
        with ExitStack() as stack:
            for name in ('gameplan_week.record_game','gameplan_week.record_team_performance','practice_integration.record_health','game_recap.post','game_recap.post_snap_counts'):
                stack.enter_context(patch(name))
            r._record('GB','MIN',week,res,N(p={}),playoffs)
        return L,p

    def test_all_rounds_report_even_after_loss(self):
        for week in range(19,23):
            for win in (True,False):
                L,p=self.run_game(week=week,win=win)
                mails=[m for m in L.inbox if m['kind']=='injury']
                self.assertEqual(len(mails),1)
                self.assertIn('ankle',mails[0]['body'])
                self.assertEqual(p.out_until,week+2)
                CN._injury_report(L,L.teams['GB'],week,[])
                self.assertEqual(len([m for m in L.inbox if m['kind']=='injury']),1)

    def test_no_new_injury_no_email(self):
        L,_=self.run_game(injured=False)
        self.assertFalse(getattr(L, 'inbox', []))

    def test_regular_season_still_waits_for_weekly_report(self):
        L,_=self.run_game(week=1,playoffs=False)
        self.assertFalse(getattr(L, 'inbox', []))
        CN._injury_report(L,L.teams['GB'],1,[])
        self.assertEqual(len(L.inbox),1)


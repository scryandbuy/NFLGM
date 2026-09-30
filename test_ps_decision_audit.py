"""Audit regressions: failures identify unsafe transaction boundaries."""
import unittest
import practice_squad as PS
import views_club as VC
from test_cap_accounting import fixture, player


class PSDecisionAudit(unittest.TestCase):
    def test_retired_free_agent_cannot_join_squad(self):
        league=fixture(); p=player(league,team=None); p.retired=True
        league.free_agents.append(p.pid)
        self.assertFalse(PS.sign_to_squad(league,'GB',p.pid))

    def test_other_squad_player_cannot_be_signed_to_second_squad(self):
        league=fixture(); p=player(league,team='MIN')
        league.teams['MIN'].roster.remove(p); PS.squad(league.teams['MIN']).append(p)
        self.assertFalse(PS.sign_to_squad(league,'GB',p.pid))
        self.assertEqual(p.team,'MIN')

    def test_user_callup_requires_user_to_choose_cut(self):
        league=fixture(); league.user_team='GB'
        for i in range(53): player(league,pid=str(i))
        p=player(league,pid='ps'); league.teams['GB'].roster.remove(p)
        PS.squad(league.teams['GB']).append(p)
        before={x.pid for x in league.teams['GB'].roster}
        result=VC.act_call_up(league,'GB',p.pid)
        self.assertFalse(result['ok'])
        self.assertEqual({x.pid for x in league.teams['GB'].roster},before)

    def test_playoff_callup_respects_active_roster_limit(self):
        league=fixture(); league.set_phase('playoffs')
        for i in range(53): player(league,pid=str(i))
        p=player(league,pid='ps'); league.teams['GB'].roster.remove(p)
        PS.squad(league.teams['GB']).append(p)
        PS.call_up(league,'GB',p.pid)
        self.assertLessEqual(len(league.teams['GB'].active()),53)

    def test_veteran_squad_move_reports_cap_failure_without_cut(self):
        league=fixture(); team=league.teams['GB']; team.cap.cap=.1; team.cap.rollover=0
        p=player(league); p.accrued=5
        result=VC.act_to_squad(league,'GB',p.pid)
        self.assertFalse(result['ok'])
        self.assertIn(p,team.roster)


if __name__=='__main__': unittest.main()

"""Audit regressions: failures identify unsafe transaction boundaries."""
import unittest
from unittest.mock import patch
import numpy as np
import waivers as W
import practice_squad as PS
import views_club as VC
from test_cap_accounting import fixture, player


class PSDecisionAudit(unittest.TestCase):
    def test_failed_poach_preserves_source_and_user_roster(self):
        league=fixture(); league.user_team='GB'
        for i in range(53): player(league,pid=str(i))
        p=player(league,pid='poach',team='MIN')
        league.teams['MIN'].roster.remove(p); PS.squad(league.teams['MIN']).append(p)
        before={x.pid for x in league.teams['GB'].roster}
        self.assertFalse(PS.poach(league,'GB',p.pid,1))
        self.assertEqual({x.pid for x in league.teams['GB'].roster},before)
        self.assertIn(p,PS.squad(league.teams['MIN']))
        self.assertEqual(p.team,'MIN')
        league.teams['GB'].roster.pop(); league.teams['GB'].cap.cap=.01
        self.assertFalse(PS.poach(league,'GB',p.pid,1))
        self.assertIn(p,PS.squad(league.teams['MIN']))
        self.assertEqual(p.team,'MIN')

    def test_waiver_claim_only_releases_explicit_user_choice(self):
        for chosen in (None,'0'):
            league=fixture(); league.user_team='GB'
            for i in range(53): player(league,pid=str(i))
            p=player(league,pid='claim',team=None)
            league.free_agents.append(p.pid)
            entry=dict(pid=p.pid,from_team='MIN',claims=['GB'])
            if chosen: entry['release_if_awarded']=chosen
            league.waivers=[entry]
            before={x.pid for x in league.teams['GB'].roster}
            with patch.object(W,'priority',return_value=['GB']), patch('valuation.pool_from_league',return_value=None), patch('valuation.value_player',return_value={'value':1}):
                result=W.process(league,np.random.default_rng(7),1)
            after={x.pid for x in league.teams['GB'].roster}
            if chosen:
                self.assertEqual(result,[(p.pid,'GB')])
                self.assertEqual(before-after,{chosen})
                self.assertEqual(len(after),53)
            else:
                self.assertEqual(result,[])
                self.assertEqual(after,before)
                self.assertIsNone(p.team)

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

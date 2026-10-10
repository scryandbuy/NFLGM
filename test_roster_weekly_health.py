"""Next-game insurance, temporary elevations, and safe IR roster decisions."""
import unittest
from unittest.mock import patch
import numpy as np
import cutdown as CD
import game_availability as GA
import practice_squad as PS
import roster_needs as RN
import targets as TG
from cap_engine import Contract
from injury_status import InjuryDesk
from league import Player
from test_draft_planning import fixture


class WeeklyHealthTests(unittest.TestCase):
    def roster(self):
        league, team = fixture()
        kept = RN.select_cutdown(team, CD.rows_for(team), 53)
        team.roster = [p for p in team.roster if p.pid in kept]
        league.set_phase('regular'); league.week = 8
        team.cap.cap = 1000; team.sync_cap()
        self.assertEqual(len(team.active()), 53)
        self.assertEqual(len(team.by_pos('QB')), 2)
        return league, team

    def reserve(self, league, team, pos='QB', pid='insurance'):
        p = Player(pid, pid, pos, 24, {k: 72 for k in TG.DEPTH_WEIGHTS[pos]}, team=team.abbr)
        league.players[pid] = p
        PS.squad(team).append(p); p.xp_spent['_ps'] = True
        return p

    def third_quarterback(self, league, team):
        """Injured incumbent, healthy starter, and healthy temporary insurance."""
        insurance = self.reserve(league, team, pid='third-qb')
        PS.squad(team).remove(insurance)
        insurance.xp_spent.pop('_ps', None)
        team.roster.remove(team.by_pos('CB')[-1])
        team.roster.append(insurance)
        self.assertEqual(len(team.active()), 53)
        return insurance

    def test_short_absence_is_planning_depth_but_not_available_backup(self):
        league, team = self.roster()
        team.by_pos('QB')[0].out_until = 9
        self.assertNotIn('QB', PS.essential_depth(team, week=8)['shortages'])
        self.assertEqual(PS.healthy_depth(team)['shortages']['QB'], 1)
        backup = self.third_quarterback(league, team)
        incoming = self.reserve(league, team, 'CB')
        # Planning counts three QBs; cutting insurance still leaves two on
        # paper, but only one who can dress. Preserve that second healthy QB.
        self.assertNotIn(backup, list(PS._room_candidates(league, team, incoming)))

    def test_full_roster_elevates_short_term_backup_without_permanent_move(self):
        league, team = self.roster(); starter = team.by_pos('QB')[0]
        starter.out_until = 9
        reserve = self.reserve(league, team)
        roster = [p.pid for p in team.roster]; transactions = list(league.transactions)
        self.assertGreater(len(GA.dressed(team, None, 8)), 46)
        GA.ensure(league, team, None, 8)
        self.assertIn(reserve, team._elevated)
        self.assertEqual(PS.healthy_depth(team, GA.dressed(team, None, 8))['counts']['QB'], 2)
        self.assertEqual([p.pid for p in team.roster], roster)
        self.assertEqual(league.transactions, transactions)
        GA.ensure(league, team, None, 8)
        self.assertEqual(reserve.xp_spent['_elevations'], 1)
        # Recovery removes the reason for another elevation the following game.
        starter.out_until = None; PS.clear_elevations(team)
        GA.ensure(league, team, None, 9)
        self.assertNotIn(reserve, team._elevated)

    def test_weekly_cpu_cover_uses_position_need_and_preserves_user_choice(self):
        league, team = self.roster(); team.by_pos('QB')[0].out_until = 9
        reserve = self.reserve(league, team)
        with patch.object(PS, 'keep_groups_whole', return_value=[]), patch.object(PS, 'roster_review', return_value=[]):
            PS.weekly(league, np.random.default_rng(1), 7, user_team='GB')
            self.assertIn(reserve, team._elevated)
            league.user_team = team.abbr
            uses = reserve.xp_spent['_elevations']
            PS.weekly(league, np.random.default_rng(1), 7, user_team=team.abbr)
            self.assertIn(reserve, team._elevated)  # Week 8 choice survives a repeated roll of week 7.
            self.assertEqual(reserve.xp_spent['_elevations'], uses)
            PS.weekly(league, np.random.default_rng(1), 8, user_team=team.abbr)
            self.assertNotIn(reserve, team._elevated)

    def test_temporary_limits_do_not_force_permanent_cover_but_playoffs_allow_reuse(self):
        league, team = self.roster(); team.by_pos('QB')[0].out_until = 9
        reserve = self.reserve(league, team); reserve.xp_spent['_elevations'] = 3
        with patch.object(PS, 'call_up') as promote:
            GA.ensure(league, team, None, 8)
            self.assertNotIn(reserve, getattr(team, '_elevated', []))
            GA.ensure(league, team, None, 8, playoffs=True)
            self.assertIn(reserve, team._elevated)
            promote.assert_not_called()
        self.assertEqual(reserve.xp_spent['_elevations'], 3)

    def test_injured_or_uncleared_reserve_cannot_be_used(self):
        league, team = self.roster(); team.by_pos('QB')[0].out_until = 9
        reserve = self.reserve(league, team); reserve.out_until = 9
        GA.ensure(league, team, None, 8)
        self.assertNotIn(reserve, getattr(team, '_elevated', []))

    def test_essential_game_role_wins_before_reserve_depth_with_two_elevation_limit(self):
        league, team = self.roster()
        for p in team.by_pos('QB') + team.by_pos('WR')[:2] + team.by_pos('DT')[:2]:
            p.out_until = 9
        quarterback = self.reserve(league, team, pid='available-qb')
        for pos in ('WR', 'DT'):
            p = self.reserve(league, team, pos, 'reserve-' + pos)
            p.ratings = {k: 99 for k in TG.DEPTH_WEIGHTS[pos]}
        PS.elevate_for_coverage(league, team, 8)
        self.assertIs(team._elevated[0], quarterback)
        self.assertEqual(len(team._elevated), 2)
        self.assertEqual(len(team.active()), 53)

    def test_ir_return_finds_alternative_to_live_injury_cover(self):
        league, team = self.roster()
        starter = team.by_pos('QB')[0]; starter.out_until = 9
        backup = self.third_quarterback(league, team)
        # An unrelated star is eligible to return; selector initially spends QB2.
        returning = Player('returning', 'Returning defender', 'CB', 26,
                           {k: 95 for k in TG.DEPTH_WEIGHTS['CB']},
                           team=team.abbr, contract=Contract(1, [1]))
        returning.out_until = 8
        returning.xp_spent.update(_ir_week=3, _ir_return=True)
        league.players[returning.pid] = returning; team.roster.append(returning)
        team.ir = [returning]; team.ir_returns_used = 0
        preferred = {p.pid for p in team.roster if p is not backup}
        before = PS.healthy_depth(team)['shortages']
        with patch.object(RN, 'select_cutdown', return_value=preferred):
            result = InjuryDesk().activate_from_ir(league, team, 8)
        self.assertEqual(result, [returning])
        self.assertIn(backup, team.active()); self.assertIn(starter, team.active())
        self.assertEqual(len(team.active()), 53)
        self.assertEqual(team.ir_returns_used, 1)
        self.assertTrue(all(n <= before.get(g, 0) for g, n in PS.healthy_depth(team)['shortages'].items()))

    def test_ir_return_waits_when_all_safe_departures_are_protected(self):
        league, team = self.roster()
        starter = team.by_pos('QB')[0]; starter.out_until = 9
        backup = self.third_quarterback(league, team)
        returning = self.reserve(league, team, 'CB', 'returning')
        PS.squad(team).remove(returning); team.roster.append(returning)
        returning.out_until = 8; returning.xp_spent.update(_ir_week=3, _ir_return=True)
        team.ir = [returning]; team.ir_returns_used = 0
        preferred = {p.pid for p in team.roster if p is not backup}
        with patch.object(RN, 'select_cutdown', return_value=preferred), \
             patch.object(PS, 'protected', side_effect=lambda tm,p,L: p is not backup):
            self.assertEqual(InjuryDesk().activate_from_ir(league, team, 8), [])
        self.assertIn(backup, team.active()); self.assertEqual(team.ir, [returning])
        self.assertEqual(returning.out_until, 8); self.assertEqual(team.ir_returns_used, 0)

    def emergency_market(self):
        league, team = self.roster()
        for p in team.by_pos('QB'):
            p.out_until = 12
        keeper = team.by_pos('QB')[0]
        keeper.contract = Contract(4, [20] * 4)
        team.sync_cap(); team.cap.cap = team.cap.charges(team.phase)
        star = Player('high-ask', 'High ask', 'QB', 27,
                      {k: 95 for k in TG.DEPTH_WEIGHTS['QB']}, accrued=4)
        league.players[star.pid] = star; league.free_agents.append(star.pid)
        return league, team, star

    def test_emergency_refusal_precedes_every_cut_and_restructure(self):
        league, team, star = self.emergency_market()
        before = league.save()
        with patch('valuation.value_player', return_value={'apy': 40}), \
             patch.object(GA, '_funding', wraps=GA._funding) as funding:
            self.assertFalse(GA._acquire(league, team, GA.dressed(team, None, 8), ('QB',), None, 8))
            funding.assert_not_called()
        self.assertEqual(league.save(), before)

    def test_emergency_refusal_tries_willing_alternative_with_one_comp_pool(self):
        import valuation as VAL
        league, team, star = self.emergency_market()
        reserve = Player('willing', 'Willing reserve', 'QB', 24,
                         {k: 65 for k in TG.DEPTH_WEIGHTS['QB']})
        league.players[reserve.pid] = reserve; league.free_agents.append(reserve.pid)
        with patch.object(VAL, 'value_player', side_effect=lambda L,p,**kw:
                          {'apy': 40 if p is star else 1}), \
             patch.object(VAL, 'pool_from_league', wraps=VAL.pool_from_league) as comps, \
             patch.object(GA, '_funding', wraps=GA._funding) as funding:
            self.assertTrue(GA._acquire(league, team, GA.dressed(team, None, 8), ('QB',), None, 8))
            comps.assert_called_once()
            self.assertTrue(all(call.args[2] is reserve for call in funding.call_args_list))
        self.assertIn(reserve, team.active()); self.assertIn(star.pid, league.free_agents)
        self.assertEqual(len(team.active()), 53)
        self.assertGreaterEqual(team.cap_space, -.0005)


if __name__ == '__main__': unittest.main()

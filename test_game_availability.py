"""Emergency availability, legal funding, persistence, and calendar retry gates."""
import unittest
from types import SimpleNamespace

import cutdown
import game
import game_availability as GA
import practice_squad as PS
import roster_needs as RN
from cap_engine import Contract
from league import League, Player, Team
from postseason import Postseason
from season import SeasonRunner
from session import Session
from test_draft_planning import fixture


class AvailabilityTests(unittest.TestCase):
    def roster(self):
        league, team = fixture()
        keep = RN.select_cutdown(team, cutdown.rows_for(team), 53)
        team.roster = [p for p in team.roster if p.pid in keep]
        league.set_phase('regular'); league.week = 2
        team.cap.cap = 300; team.sync_cap()
        self.assertEqual(len(team.active()), 53)
        self.assertFalse(GA.shortages(GA.dressed(team, None, 2)))
        for p in team.by_pos('QB'): p.out_until = 8
        return league, team

    def candidate(self, league, team=None, pos='QB', pid='replacement'):
        p = Player(pid, pid, pos, 24, {}, team=team.abbr if team else None)
        league.players[p.pid] = p
        if team:
            PS.squad(team).append(p); p.xp_spent['_ps'] = True
        else: league.free_agents.append(p.pid)
        return p

    def test_own_squad_elevates_even_with_46_healthy_and_survives_reload(self):
        league, team = self.roster(); p = self.candidate(league, team)
        self.assertGreaterEqual(len(GA.dressed(team, None, 2)), 46)
        GA.ensure(league, team, None, 2)
        self.assertIn(p, team._elevated)
        self.assertEqual(p.xp_spent['_elevations'], 1)
        loaded = League.load(league.save()); other = loaded.teams[team.abbr]
        before = len(loaded.transactions)
        GA.ensure(loaded, other, None, 2)
        self.assertEqual([p.pid for p in other._elevated], ['replacement'])
        self.assertEqual(loaded.player(p.pid).xp_spent['_elevations'], 1)
        self.assertEqual(before, len(loaded.transactions))
        self.assertEqual(len(other.active()), 53)
        PS.reset_season(loaded)
        self.assertEqual(other._elevated, [])

    def test_fourth_regular_use_needs_contract_but_playoffs_can_elevate(self):
        league, team = self.roster(); p = self.candidate(league, team)
        p.xp_spent['_elevations'] = 3
        GA.ensure(league, team, None, 2)
        self.assertIn(p, team.active()); self.assertIsNotNone(p.contract)
        self.assertNotIn(p, PS.squad(team)); self.assertEqual(len(team.active()), 53)
        league, team = self.roster(); p = self.candidate(league, team)
        p.xp_spent['_elevations'] = 3; league.set_phase('playoffs')
        GA.ensure(league, team, None, 19, playoffs=True)
        self.assertIn(p, team._elevated); self.assertIsNone(p.contract)
        self.assertEqual(p.xp_spent['_elevations'], 3)

    def test_partial_restructure_pays_replacement_and_keeps_injured_qbs(self):
        league, team = self.roster(); p = self.candidate(league)
        starter = team.by_pos('QB')[0]
        starter.contract = Contract(4, [20]*4)
        for q in team.active():
            if q is not starter: q.contract = Contract(1, [.1])
        team.sync_cap(); team.cap.cap = team.cap.charges(team.phase)
        old_total = sum(starter.contract.base) + starter.contract.sb
        GA.ensure(league, team, None, 2)
        self.assertIn(starter, team.active()); self.assertEqual(starter.out_until, 8)
        self.assertIn(p, team.active()); self.assertEqual(len(team.active()), 53)
        self.assertGreaterEqual(team.cap_space, 0)
        self.assertLess(team.cap_space, .01)
        self.assertAlmostEqual(sum(starter.contract.base) + starter.contract.sb, old_total, places=3)
        self.assertEqual(starter.contract.years, 4)
        self.assertTrue(any(row['kind'] == 'restructure' for row in league.transactions))
        before = len(league.transactions); GA.ensure(league, team, None, 2)
        self.assertEqual(len(league.transactions), before)

    def test_cap_funding_never_converts_salary_already_earned(self):
        league, team = self.roster(); p = self.candidate(league)
        keeper = team.by_pos('QB')[0]
        keeper.contract = Contract(4, [20]*4)
        keeper.contract.earned_base = 19.9
        for q in team.active():
            if q is not keeper: q.contract = Contract(1, [.01])
        team.cap.paid_week = 9; team.sync_cap()
        team.cap.cap = team.cap.charges(team.phase)
        before = league.save()
        with self.assertRaises(GA.FieldabilityError): GA.ensure(league, team, None, 10)
        self.assertEqual(league.save(), before)
        self.assertEqual(keeper.contract.earned_base, 19.9)

    def test_core_starters_never_sacrificed_when_surplus_is_locked(self):
        league, team = self.roster(); self.candidate(league)
        starters = {row['player'].pid for row in RN.assess(team)['assignments'] if row['player'] is not None}
        for q in team.active():
            if q.pid not in starters: q.xp_spent['_poach_lock'] = 5
        before = league.save()
        with self.assertRaises(GA.FieldabilityError): GA.ensure(league, team, None, 2)
        self.assertEqual(league.save(), before)

    def test_unfundable_team_stays_unchanged_and_blocks(self):
        league, team = self.roster(); self.candidate(league)
        for p in team.active(): p.contract = Contract(1, [.1])
        team.sync_cap(); team.cap.cap = team.cap.charges(team.phase)
        before = league.save()
        with self.assertRaisesRegex(GA.FieldabilityError, 'MIN.*QB'):
            GA.ensure(league, team, None, 2)
        self.assertEqual(league.save(), before)

    def test_user_never_gets_automatic_acquisition_or_elevation(self):
        league, team = self.roster(); league.user_team = team.abbr
        self.candidate(league); self.candidate(league, team, pid='squad')
        before = league.save()
        with self.assertRaises(GA.FieldabilityError): GA.ensure(league, team, None, 2)
        self.assertEqual(league.save(), before)

    def test_injured_and_pending_waiver_candidates_cannot_fill_hole(self):
        league, team = self.roster(); p = self.candidate(league); p.out_until = 5
        with self.assertRaises(GA.FieldabilityError): GA.ensure(league, team, None, 2)
        p.out_until = None
        import waivers
        waivers.waive(league, p, 'ATL', 2)
        with self.assertRaises(GA.FieldabilityError): GA.ensure(league, team, None, 2)
        self.assertIsNone(p.team)

    def test_other_mandatory_position_repaired_without_churning_healthy_team(self):
        league, team = self.roster()
        for p in team.by_pos('QB'): p.out_until = None
        self.candidate(league, pos='P')
        before = len(league.transactions); GA.ensure(league, team, None, 2)
        self.assertEqual(before, len(league.transactions))
        old = team.by_pos('P')[0]; old.out_until = 6
        GA.ensure(league, team, None, 2)
        self.assertIn(old, team.active())
        self.assertFalse(GA.shortages(GA.dressed(team, None, 2)))

    def test_center_can_cover_long_snaps_when_no_ls_is_available(self):
        league, team = self.roster()
        for p in team.by_pos('QB'): p.out_until = None
        snapper = team.by_pos('LS')[0]
        team.roster.remove(snapper)
        snapper.team = None
        self.assertFalse(any(label == 'LS' for label, _, _ in GA.shortages(GA.dressed(team, None, 2))))
        GA.ensure(league, team, None, 2)
        self.assertIsNone(snapper.team)

    def test_other_squad_is_last_resort_and_poach_lock_applies(self):
        league, team = self.roster()
        other = Team('ATL', 'United South', 'United'); other.league = league
        league.teams['ATL'] = other
        p = self.candidate(league, other)
        GA.ensure(league, team, None, 2)
        self.assertIn(p, team.active()); self.assertNotIn(p, PS.squad(other))
        self.assertTrue(PS.locked(p, 2)); self.assertGreaterEqual(team.cap_space, 0)

    def test_new_signings_are_not_cut_for_the_emergency(self):
        league, team = self.roster(); self.candidate(league)
        for p in team.active(): league.log('sign', pid=p.pid, team=team.abbr)
        before = league.save()
        with self.assertRaises(GA.FieldabilityError): GA.ensure(league, team, None, 2)
        self.assertEqual(league.save(), before)

    def runner(self):
        r = SeasonRunner.__new__(SeasonRunner)
        r.L = SimpleNamespace(schedule=[(1, 'A', 'B', None, None), (1, 'C', 'D', None, None)],
                              week=1, week_book={})
        r.week = 1; r.desks = {}; r.states = {}; r._listed_week = 1
        r.last_games = []; r.last_played = []
        r.prepare_practice = lambda *args: None
        return r

    def test_missing_result_blocks_and_retry_does_not_replay_completed_game(self):
        r = self.runner(); r._book = game.StatBook()
        r.play = lambda h,a,w: {'home':17,'away':10} if h == 'B' else None
        r._after_games = lambda *args: None
        with self.assertRaises(GA.FieldabilityError): r.play_games(1)
        self.assertEqual(r.L.schedule[0][-2:], (10,17))
        self.assertIsNone(r.L.schedule[1][-1])
        with self.assertRaises(GA.FieldabilityError): r.roll_week(1)
        calls = []
        def finish(h,a,w): calls.append(h); return {'home':21,'away':14}
        r.play = finish
        r.play_games(1)
        self.assertEqual(calls, ['D'])
        self.assertEqual(len(r.last_games), 2); GA.require_scores(r.L, 1)

    def test_incomplete_week_never_settles_and_session_surfaces_reason(self):
        r = self.runner(); r._after_games(1, [])
        self.assertIsNone(getattr(r, '_after_done', None))
        s = Session.__new__(Session); s.runner = r
        s.blocking = lambda: []; s.next_label = lambda: 'Play Week 1'
        s._advance = lambda: GA.require_scores(r.L, 1)
        result = s.advance()
        self.assertEqual(result['done'], 'Blocked')
        self.assertIn('unplayed games', result['why'])

    def test_playoff_retry_uses_schedule_and_never_fabricates_winner(self):
        r = self.runner(); r.L.schedule = [(19,'A','B',None,None),(19,'C','D',None,None)]
        r.L.log = lambda *args, **kwargs: None
        r.require_available = lambda *args, **kwargs: None
        post = Postseason(r); post.seeds = {'Continental':['A','B','C','D']}
        post.alive = {'Continental':{1:'B',2:'A',3:'D',4:'C'}}
        r.play = lambda h,a,w,**kw: {'home':20,'away':10} if h == 'B' else None
        with self.assertRaises(GA.FieldabilityError): post.play_round('WC')
        self.assertEqual(len(post.games), 1)
        calls = []
        def finish(h,a,w,**kw): calls.append(h); return {'home':24,'away':17}
        r.play = finish; post.play_round('WC')
        self.assertEqual(calls, ['D']); self.assertEqual(len(post.games), 2)
        GA.require_scores(r.L, 19)


if __name__ == '__main__': unittest.main()

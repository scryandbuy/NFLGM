"""Weekly squad vacancies use the actual market and existing offer rules."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

from league import Player, Team
from test_draft_planning import fixture
import targets as TG
import practice_squad as PS


class WeeklySquadRecruitmentTests(unittest.TestCase):
    def setup_league(self):
        league, team = fixture()
        league.set_phase('regular'); league.week = 8
        team.cap.cap = 500; team.sync_cap()
        league.free_agents = []; league.waivers = []
        return league, team

    def free_player(self, league, pid, pos='LT', grade=73, accrued=0, age=22):
        player = Player(pid, pid, pos, age,
                        {key: grade for key in TG.DEPTH_WEIGHTS[pos]})
        player.accrued = accrued
        league.players[pid] = player; league.free_agents.append(pid)
        return player

    def seed_squad(self, league, team, count, vets=0):
        positions = ('WR', 'CB', 'HB', 'TE', 'DT', 'WILL', 'FS', 'LG')
        players = []
        for i in range(count):
            player = self.free_player(league, f'squad-{i}', positions[i % len(positions)],
                                      grade=68, accrued=4 if i < vets else 0)
            self.assertTrue(PS.sign_to_squad(league, team.abbr, player.pid))
            players.append(player)
        return players

    def test_poached_slot_refilled_without_touching_active_rosters(self):
        league, team = self.setup_league()
        members = self.seed_squad(league, team, PS.SIZE)
        other = Team('GB', 'United North', 'United'); other.league = league
        league.teams['GB'] = other; other.cap.cap = 500
        self.assertTrue(PS.poach(league, 'GB', members[0].pid, league.week))
        prospect = self.free_player(league, 'replacement')
        active_before = {abbr: list(t.roster) for abbr, t in league.teams.items()}
        self.assertEqual(PS.replenish_squads(league, np.random.default_rng(4)), 1)
        self.assertEqual(len(PS.squad(team)), PS.SIZE)
        self.assertIn(prospect, PS.squad(team))
        self.assertEqual({abbr: t.roster for abbr, t in league.teams.items()}, active_before)
        self.assertIn(members[0], other.roster)

    def test_full_cpu_and_user_squads_are_untouched(self):
        for full in (False, True):
            league, team = self.setup_league()
            if full:
                self.seed_squad(league, team, PS.SIZE)
            else:
                league.user_team = team.abbr
            prospect = self.free_player(league, 'untouched')
            before = list(league.transactions), list(team.roster), list(PS.squad(team))
            self.assertEqual(PS.replenish_squads(league, np.random.default_rng(4)), 0)
            self.assertEqual((league.transactions, team.roster, PS.squad(team)), before)
            self.assertIsNone(prospect.team)

    def test_scarce_and_unwilling_market_leaves_vacancies(self):
        league, team = self.setup_league()
        self.free_player(league, 'starter-young', grade=87)
        self.free_player(league, 'starter-vet', grade=82, accrued=5, age=30)
        before = list(league.free_agents)
        self.assertEqual(PS.replenish_squads(league, np.random.default_rng(4)), 0)
        self.assertEqual(PS.squad(team), [])
        self.assertEqual(league.free_agents, before)

    def test_crowded_position_market_does_not_force_sixteen_recruits(self):
        league, team = self.setup_league()
        for i in range(20):
            self.free_player(league, f'quarterback-{i}', pos='QB', grade=70)
        recruited = PS.replenish_squads(league, np.random.default_rng(4))
        self.assertGreater(recruited, 0)
        self.assertLess(recruited, PS.SIZE)
        self.assertTrue(league.free_agents)

    def test_six_veteran_limit_still_allows_young_recruit(self):
        league, team = self.setup_league()
        self.seed_squad(league, team, 6, vets=6)
        veteran = self.free_player(league, 'seventh-vet', grade=76, accrued=5, age=30)
        young = self.free_player(league, 'young')
        self.assertEqual(PS.replenish_squads(league, np.random.default_rng(4)), 1)
        self.assertIn(young, PS.squad(team)); self.assertIsNone(veteran.team)
        self.assertEqual(sum(not PS.is_young(p) for p in PS.squad(team)), PS.VET_MAX)

    def test_pending_waiver_and_stale_owned_entries_are_not_recruited(self):
        league, team = self.setup_league()
        pending = self.free_player(league, 'pending', grade=80)
        league.waivers = [dict(pid=pending.pid, from_team='GB', claims=['GB'])]
        owned = team.roster[0]; league.free_agents.append(owned.pid)
        available = self.free_player(league, 'available')
        self.assertEqual(PS.replenish_squads(league, np.random.default_rng(4)), 1)
        self.assertIn(available, PS.squad(team)); self.assertIsNone(pending.team)
        self.assertIn(owned, team.roster); self.assertNotIn(owned, PS.squad(team))
        self.assertEqual(league.waivers[0]['claims'], ['GB'])

    def test_repeat_review_is_saved_and_does_not_consume_more_rng(self):
        league, team = self.setup_league()
        player = self.free_player(league, 'recruit')
        rng = np.random.default_rng(4)
        self.assertEqual(PS.replenish_squads(league, rng), 1)
        before = list(league.transactions), list(PS.squad(team)), copy.deepcopy(rng.bit_generator.state)
        self.assertEqual(PS.replenish_squads(league, rng), 0)
        self.assertEqual((league.transactions, PS.squad(team), rng.bit_generator.state), before)
        self.assertEqual(league.notes_sent['_ps_recruitment'], [league.year, league.week])
        # A later same-week movement cannot trigger a recruit/release/recruit loop.
        PS.release_from_squad(league, team.abbr, player.pid)
        self.assertEqual(PS.replenish_squads(league, rng), 0)
        self.assertIsNone(player.team)

    def test_same_week_reversals_are_excluded_but_cleared_camp_cut_can_return(self):
        league, team = self.setup_league()
        released = self.free_player(league, 'released-squad')
        undone = self.free_player(league, 'undone-active')
        old_cut = self.free_player(league, 'cleared-cut')
        league.log('ps_release', pid=released.pid, team=team.abbr)
        league.log('sign', pid=undone.pid, team=team.abbr)
        league.log('release', pid=undone.pid, team=team.abbr)
        league.transactions.append(dict(kind='release', pid=old_cut.pid, team=team.abbr,
                                        year=league.year, week=0))
        self.assertEqual(PS.replenish_squads(league, np.random.default_rng(4)), 1)
        self.assertIn(old_cut, PS.squad(team))
        self.assertIsNone(released.team); self.assertIsNone(undone.team)

    def test_club_scouting_controls_competing_same_position_recruits(self):
        league, team = self.setup_league()
        self.seed_squad(league, team, PS.SIZE - 1)
        actual_better = self.free_player(league, 'better', grade=78)
        preferred = self.free_player(league, 'preferred', grade=72)
        league.scouting[team.abbr].update({actual_better.pid: {'ovr': 69},
                                          preferred.pid: {'ovr': 81}})
        self.assertEqual(PS.replenish_squads(league, np.random.default_rng(4)), 1)
        self.assertIn(preferred, PS.squad(team)); self.assertIsNone(actual_better.team)

    def test_public_development_breaks_equal_talent_tie_without_hidden_ceiling(self):
        league, team = self.setup_league()
        self.seed_squad(league, team, PS.SIZE - 1)
        ordinary = self.free_player(league, 'z-ordinary')
        prospect = self.free_player(league, 'a-prospect')
        prospect.dev = 'superstar'; prospect.potential = 74
        ordinary.potential = 99
        self.assertEqual(PS.replenish_squads(league, np.random.default_rng(4)), 1)
        self.assertIn(prospect, PS.squad(team)); self.assertIsNone(ordinary.team)

    def test_weekly_entry_point_refills_vacancy_created_by_roster_movement(self):
        league, team = self.setup_league()
        members = self.seed_squad(league, team, PS.SIZE)
        prospect = self.free_player(league, 'after-callup')
        def callup_during_review(*args, **kwargs):
            self.assertTrue(PS.call_up(league, team.abbr, members[0].pid))
            return []
        with patch.object(PS, 'keep_groups_whole', return_value=[]), \
             patch.object(PS, 'roster_review', side_effect=callup_during_review), \
             patch.object(PS, 'elevate_for_coverage', return_value=[]):
            PS.weekly(league, np.random.default_rng(4), league.week)
        self.assertIn(members[0], team.roster)
        self.assertIn(prospect, PS.squad(team))
        self.assertEqual(len(PS.squad(team)), PS.SIZE)


if __name__ == '__main__':
    unittest.main()

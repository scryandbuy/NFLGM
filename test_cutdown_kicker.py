"""A missing kicker must use a legal, qualified player without inventing talent."""
import copy
import unittest

import cutdown as CD
import practice_squad as PS
import roster_needs as RN
import waivers
from cap_engine import Contract
from league import League
import test_roster_cap_recovery as recovery_tests


class KickerRecoveryTests(unittest.TestCase):
    def fixture(self):
        league, team = recovery_tests.RecoveryTests.roster(self)
        team.by_pos('K')[0].pos = 'TE'
        self.assertEqual(RN.assess(team)['uncovered'], ['K'])
        return league, team

    def punter(self, league, team, pid='street-punter', accuracy=83, power=93):
        p = copy.deepcopy(team.by_pos('P')[0]); p.pid = pid; p.name = pid
        p.team = None; p.contract = None; p.accrued = 5
        p.ratings.update(kick_acc_rating=accuracy, kick_power_rating=power)
        league.players[pid] = p; league.free_agents.append(pid)
        return p

    def test_street_punter_trains_with_real_ratings_and_keeps_starting_punter(self):
        league, team = self.fixture(); starter = team.by_pos('P')[0]
        p = self.punter(league, team); ratings = dict(p.ratings)
        ids = set(league.players)
        self.assertEqual(CD.repair_shape(league), 1)
        self.assertEqual(set(league.players), ids)
        self.assertIn(starter, team.active()); self.assertEqual(starter.pos, 'P')
        self.assertIn(p, team.active()); self.assertEqual(p.pos, 'K')
        self.assertEqual(p.ratings, ratings); self.assertEqual(p.transition['penalty'], 5)
        self.assertLess(p.ovr, p.score_at('K'))
        self.assertEqual(len(team.active()), 53)
        self.assertGreaterEqual(team.cap_space, 0)
        self.assertFalse(CD.violations(league))
        releases = [row for row in league.transactions if row['kind'] == 'release']
        self.assertEqual(len(releases), 1)
        self.assertTrue(any(row['pid'] == releases[0]['pid'] for row in waivers.pending(league)))

    def test_reload_and_retry_preserve_training_without_duplicate_moves(self):
        league, team = self.fixture(); p = self.punter(league, team)
        CD.repair_shape(league)
        saved = League.load(league.save()); transactions = list(saved.transactions)
        self.assertEqual(CD.repair_shape(saved), 0)
        self.assertEqual(saved.transactions, transactions)
        self.assertEqual(saved.player(p.pid).transition, p.transition)
        self.assertFalse(CD.violations(saved))

    def test_available_kicker_takes_priority_over_conversion(self):
        league, team = self.fixture(); p = self.punter(league, team)
        kicker = self.punter(league, team, pid='street-kicker'); kicker.pos = 'K'
        self.assertEqual(CD.repair_shape(league), 1)
        self.assertEqual(kicker.team, team.abbr)
        self.assertIsNone(p.team)
        self.assertFalse(any(row['kind'] == 'position_change' for row in league.transactions))

    def test_power_without_accuracy_does_not_qualify(self):
        league, team = self.fixture(); p = self.punter(league, team, accuracy=45, power=99)
        before = league.save()
        self.assertEqual(CD.repair_shape(league), 0)
        self.assertEqual(league.save(), before)
        self.assertIn('K', CD.violations(league)[0]['missing'])

    def test_injured_waived_and_future_prospect_are_not_signed(self):
        league, team = self.fixture(); hurt = self.punter(league, team); hurt.out_until = 3
        waived = self.punter(league, team, pid='on-waivers'); waivers.waive(league, waived, 'GB', 0)
        future = self.punter(league, team, pid='future'); league.free_agents.remove(future.pid)
        future.draft_year = league.year + 1; league.next_class = [future]
        before = league.save()
        self.assertEqual(CD.repair_shape(league), 0)
        self.assertEqual(league.save(), before)
        self.assertTrue(all(p.team is None for p in (hurt, waived, future)))

    def test_unaffordable_conversion_makes_no_release_or_rating_change(self):
        league, team = self.fixture(); p = self.punter(league, team)
        for q in team.active(): q.contract = Contract(1, [.1])
        team.sync_cap(); team.cap.cap = team.cap.charges(team.phase)
        before = league.save()
        self.assertEqual(CD.repair_shape(league), 0)
        self.assertEqual(league.save(), before)
        self.assertIsNone(p.transition)

    def test_user_and_only_starting_punter_are_never_repurposed(self):
        league, team = self.fixture(); self.punter(league, team)
        league.user_team = team.abbr; before = league.save()
        self.assertEqual(CD.repair_shape(league), 0); self.assertEqual(league.save(), before)
        league, team = self.fixture(); before = league.save()
        self.assertEqual(CD.repair_shape(league), 0); self.assertEqual(league.save(), before)

    def test_qualified_own_reserve_avoids_an_unnecessary_signing(self):
        league, team = self.fixture(); starter = team.by_pos('P')[0]
        starter.ratings.update(kick_acc_rating=92, kick_power_rating=96)
        reserve = team.by_pos('TE')[-1]; reserve.pos = 'P'
        reserve.ratings.update(kick_acc_rating=81, kick_power_rating=91)
        self.punter(league, team, accuracy=90, power=99)
        ids = {p.pid for p in team.active()}
        self.assertEqual(CD.repair_shape(league), 1)
        self.assertEqual(ids, {p.pid for p in team.active()})
        self.assertEqual(starter.pos, 'P'); self.assertEqual(reserve.pos, 'K')
        self.assertEqual([row['kind'] for row in league.transactions], ['position_change'])


if __name__ == '__main__': unittest.main()

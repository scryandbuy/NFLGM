"""Exercise the UI's negotiation path for another club's squad player."""
import unittest
from unittest.mock import patch

from league import League
from session import Session
from test_roster_advisor import fixture, player
import negotiations as NG
import offer_reservations as OR
import practice_squad as PS
import views_personnel as VP


class PracticeSquadOfferTests(unittest.TestCase):
    def setUp(self):
        self.l = fixture()
        self.p = player('squad-target', 'CB', 70, 'MIN')
        self.p.xp_spent['_ps'] = True
        self.l.players[self.p.pid] = self.p
        self.l.teams['MIN'].practice_squad = [self.p]

    def open(self):
        with patch('valuation.value_player', return_value=dict(apy=2., years=1)):
            result = VP.act_poach_ps(self.l, 'GB', self.p.pid)
        self.assertTrue(result['ok'], result)
        return NG.find(self.l, result['thread'])

    def test_sign_at_53_then_block_advance_until_cut(self):
        team = self.l.teams['GB']
        while len(team.active()) < 53:
            p = player(f'fill-{len(team.roster)}', team='GB')
            self.l.players[p.pid] = p
            team.roster.append(p)
        team.sync_cap()
        self.assertEqual(len(team.active()), 53)
        thread = self.open()
        result = VP.act_offer(self.l, 'GB', thread['id'], 2., 1, sign_today=True)
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['state'], 'accepted')
        self.assertEqual(len(team.active()), 54)
        self.assertEqual(self.p.team, 'GB')
        self.assertNotIn(self.p, PS.squad(self.l.teams['MIN']))
        self.assertTrue(PS.locked(self.p, self.l.week + 2))
        s = Session.__new__(Session)
        s.L = self.l; s.runner = None; s.user_team = 'GB'; s.stop = ('week', 3)
        self.assertTrue(any(x['kind'] == 'roster' and '54' in x['subject'] for x in s.blocking()))
        self.l.release(next(p.pid for p in team.roster if p is not self.p))
        self.assertFalse(any(x['kind'] == 'roster' for x in s.blocking()))

    def test_pending_squad_offer_holds_cap_and_survives_save_load(self):
        thread = self.open()
        result = VP.act_offer(self.l, 'GB', thread['id'], 2., 1)
        self.assertEqual(result.get('state'), 'waiting', result)
        held = OR.held(self.l, 'GB')
        self.assertGreater(held, 0)
        loaded = League.load(self.l.save())
        self.assertAlmostEqual(OR.held(loaded, 'GB'), held)
        self.assertIsNone(OR.check_offer(loaded, 'GB', thread, 2., 1))

    def test_promoted_or_own_squad_player_is_unavailable_and_hold_clears(self):
        thread = self.open()
        VP.act_offer(self.l, 'GB', thread['id'], 2., 1)
        self.l.teams['MIN'].practice_squad.remove(self.p)
        self.l.teams['MIN'].roster.append(self.p)
        self.assertIsNotNone(OR.check_offer(self.l, 'GB', thread, 2., 1))
        self.assertEqual(OR.held(self.l, 'GB'), 0)
        self.p.team = 'GB'
        self.l.teams['GB'].practice_squad = [self.p]
        self.assertIsNotNone(OR.check_offer(self.l, 'GB', thread, 2., 1))

    def test_cap_failure_leaves_player_on_original_squad(self):
        thread = self.open()
        self.l.teams['GB'].cap.cap = 0
        result = VP.act_offer(self.l, 'GB', thread['id'], 2., 1, sign_today=True)
        self.assertFalse(result['ok'])
        self.assertIn('cap room', result['why'])
        self.assertEqual(self.p.team, 'MIN')
        self.assertIn(self.p, self.l.teams['MIN'].practice_squad)
        self.assertEqual(thread['offers'], [])


if __name__ == '__main__':
    unittest.main()

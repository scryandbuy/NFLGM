"""Pending free-agent bids affect available room without becoming contracts."""

import unittest
from league import League
from gm_engine import GM
from test_cap_accounting import fixture, player
import offer_reservations as OR
import market as MK
import views_personnel as VP
from views import cap_focus, next_year_cap


class OfferReservationTests(unittest.TestCase):
    def setUp(self):
        self.league = fixture()
        self.league.user_team = 'GB'
        self.league.set_phase('free_agency')
        self.team = self.league.teams['GB']
        self.team.gm = GM()
        self.player = player(self.league, 'target', team=None)
        self.other = player(self.league, 'other', team=None)
        self.league.free_agents.extend((self.player.pid, self.other.pid))
        self.offer = dict(apy=30.0, years=4, bonus=None, front_load=0.5)
        self.thread = dict(id=1, pid=self.player.pid, team='GB', kind='fa_offseason',
                           state='waiting', offers=[self.offer], ask=30.0)
        self.league.negotiations = [self.thread]

    def test_offer_reduces_displayed_room_then_releases_on_resolution(self):
        hit = OR.offer_hit(self.league, self.team, self.player, self.offer)
        original = self.team.cap_space
        self.assertAlmostEqual(OR.available(self.league, 'GB'), original - hit, places=3)
        self.assertAlmostEqual(cap_focus(self.league, self.team)['space'], round(original - hit, 1), places=1)
        self.assertAlmostEqual(self.team.cap_space, original, places=3)  # no signed contract yet
        loaded = League.load(self.league.save())
        self.assertAlmostEqual(OR.held(loaded, 'GB'), hit, places=3)
        self.thread['state'] = 'countered'
        self.assertEqual(OR.held(self.league, 'GB'), 0)
        self.thread['state'] = 'declined'
        self.assertEqual(OR.held(self.league, 'GB'), 0)

    def test_new_offer_cannot_spend_money_held_for_another_player(self):
        second = dict(id=2, pid=self.other.pid, team='GB', kind='fa_offseason',
                      state='open', offers=[], ask=20.0)
        self.league.negotiations.append(second)
        first_hit = OR.held(self.league, 'GB')
        next_hit = OR.offer_hit(self.league, self.team, self.other,
                                dict(apy=20.0, years=3, bonus=None, front_load=0.5))
        self.team.cap.cap = first_hit + next_hit - 0.1
        result = VP.act_offer(self.league, 'GB', 2, 20.0, 3, front_load=0.5)
        self.assertFalse(result['ok'])
        self.assertIn('outstanding offers', result['why'])
        self.assertEqual(second['offers'], [])

    def test_match_checks_the_increased_rival_price_before_signing(self):
        self.thread['state'] = 'match_requested'
        self.thread['rival'] = dict(team='MIN', apy=60.0, years=4)
        self.team.cap.cap = OR.held(self.league, 'GB') + 0.1
        result = VP.act_match(self.league, 'GB', self.thread['id'])
        self.assertFalse(result['ok'])
        self.assertEqual(self.thread['state'], 'match_requested')
        self.assertIsNone(self.player.team)

    def test_revising_same_offer_replaces_its_hold(self):
        first_hit = OR.held(self.league, 'GB')
        self.team.cap.cap = first_hit + 0.1
        self.assertIsNone(OR.check_offer(self.league, 'GB', self.thread, 30.0, 4,
                                          front_load=0.5))
        self.assertIsNotNone(OR.check_offer(self.league, 'GB', self.thread, 50.0, 4,
                                             front_load=0.5))

    def test_signing_replaces_hold_with_real_contract_charge(self):
        hit = OR.held(self.league, 'GB')
        self.team.cap.cap = hit + 1.0
        before = OR.available(self.league, 'GB')
        MK.sign(self.league, self.player, MK.Offer('GB', self.player.pid, 30.0, 4,
                                                  front_load=0.5), 301.2)
        self.team.sync_cap()
        self.assertEqual(OR.held(self.league, 'GB'), 0)
        self.assertAlmostEqual(OR.available(self.league, 'GB'), before, places=2)

    def test_immediate_signing_cannot_spend_another_live_offers_room(self):
        first_hit = OR.held(self.league, 'GB')
        next_hit = OR.offer_hit(self.league, self.team, self.other,
                                dict(apy=20.0, years=3, bonus=None, front_load=0.5))
        self.team.cap.cap = first_hit + next_hit - 0.1
        with self.assertRaisesRegex(ValueError, 'Not enough cap space'):
            MK.sign(self.league, self.other, MK.Offer('GB', self.other.pid, 20.0, 3,
                                                      front_load=0.5), 301.2)
        self.assertIsNone(self.other.team)

    def test_next_year_focus_uses_the_same_reservation(self):
        self.league.set_phase('offseason')
        self.league.season_closed_year = self.league.year
        limit, committed, _, _ = next_year_cap(self.league, self.team)
        hit = OR.held(self.league, 'GB')
        focus = cap_focus(self.league, self.team)
        self.assertEqual(focus['year'], self.league.year + 1)
        self.assertAlmostEqual(focus['space'], round(limit - committed - hit, 1), places=1)


if __name__ == '__main__':
    unittest.main()

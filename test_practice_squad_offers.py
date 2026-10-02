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
import morale_system as MS
import copy


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

    def test_ui_quote_signs_unhappy_player_at_every_season_stage(self):
        for week in (1, 9, 18, 20):
            for morale in (0, 20, 40, 70):
                with self.subTest(week=week, morale=morale):
                    self.setUp()
                    self.l.week = week
                    self.l.set_phase('playoffs' if week > 18 else 'regular')
                    self.p.morale = MS.Morale(self.p.pid, baseline=morale)
                    thread = self.open()
                    # Existing saves have only the headline ask, no cached quote.
                    self.l = League.load(self.l.save())
                    self.l.user_team = 'GB'  # Session.load restores the human team.
                    thread = NG.find(self.l, thread['id'])
                    q = VP._thread(self.l, thread)['sign_today_offer']
                    self.assertGreaterEqual(q['apy'], thread['ask'])
                    s = Session.__new__(Session)
                    s.L = self.l; s.user_team = 'GB'
                    r = s.personnel_act('offer', tid=thread['id'], **q, sign_today=True)
                    self.assertEqual(r.get('state'), 'accepted', r)
                    p = self.l.player(self.p.pid)
                    self.assertEqual(p.team, 'GB')
                    self.assertIn(p, self.l.teams['GB'].active())
                    self.assertNotIn(p, PS.squad(self.l.teams['MIN']))
                    self.assertTrue(PS.locked(p, week + 2))
                    self.assertFalse(NG.sign_today_offer(self.l, thread))
                    again = VP.act_offer(self.l, 'GB', thread['id'], **q, sign_today=True)
                    self.assertFalse(again['ok'])
                    self.assertEqual(sum(x.pid == p.pid for x in self.l.teams['GB'].roster), 1)

    def test_below_immediate_terms_is_visible_and_preserves_pending_offer(self):
        self.p.morale = MS.Morale(self.p.pid, baseline=20)
        t = self.open()
        r = VP.act_offer(self.l, 'GB', t['id'], 2.1, 1)
        self.assertTrue(r['ok'])
        before = copy.deepcopy(t)
        r = VP.act_offer(self.l, 'GB', t['id'], t['ask'], t['years'], sign_today=True)
        self.assertFalse(r['ok'], r)
        self.assertIn('immediate-signing request', r['why'])
        self.assertGreater(r['sign_today_offer']['apy'], t['ask'])
        self.assertEqual(t, before)
        self.assertEqual(self.p.team, 'MIN')

    def test_immediate_quote_does_not_bypass_competitor_or_cap(self):
        self.p.morale = MS.Morale(self.p.pid, baseline=20)
        t = self.open(); q = VP._thread(self.l, t)['sign_today_offer']
        t['rival'] = dict(team='DAL', apy=3., years=1)
        r = VP.act_offer(self.l, 'GB', t['id'], **q, sign_today=True)
        self.assertFalse(r['ok']); self.assertIn('Another team', r['why'])
        self.assertEqual(t['offers'], [])
        t['rival'] = None
        self.l.teams['GB'].cap.cap = 0
        r = VP.act_offer(self.l, 'GB', t['id'], **q, sign_today=True)
        self.assertFalse(r['ok']); self.assertIn('cap room', r['why'])
        self.assertEqual(t['offers'], [])
        self.assertEqual(self.p.team, 'MIN')


if __name__ == '__main__':
    unittest.main()

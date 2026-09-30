import unittest
from unittest.mock import patch
from test_cap_accounting import fixture, player
import negotiations as NG
import views_personnel as VP
from league import League
from gm_engine import GM


class NegotiationStageTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture(); self.L.user_team = 'GB'; self.L.set_phase('free_agency')
        for team in self.L.teams.values(): team.gm = GM()
        self.p = player(self.L, 'pickens', team=None); self.L.free_agents.append(self.p.pid)
        self.t = dict(id=1, pid=self.p.pid, team='GB', kind='fa_offseason', state='countered',
                      offers=[dict(apy=19, years=3)], ask=22, years=3, patience=3, due=None,
                      counter=dict(apy=21, years=3), rival=dict(team='MIN', apy=20, years=3), match_rounds=0)
        self.L.negotiations = [self.t]

    def test_revised_counter_waits_and_old_counter_cannot_be_accepted(self):
        with patch.object(NG, '_floor', return_value=22):
            result = VP.act_offer(self.L, 'GB', 1, 20, 3)
        self.assertEqual(result['state'], 'waiting')
        self.assertIsNone(self.t['counter'])
        self.assertFalse(VP.act_match_counter(self.L, 'GB', 1)['ok'])
        loaded = League.load(self.L.save())
        self.assertEqual(NG.find(loaded, 1)['state'], 'waiting')
        self.assertIsNone(NG.find(loaded, 1)['counter'])

    def test_rival_stage_replaces_counter_and_match_signs_now(self):
        NG._answer(self.L, self.t, self.p, self.t['offers'][-1], 22)
        self.assertEqual(self.t['state'], 'match_requested')
        self.assertIsNone(self.t['counter'])
        count = len(self.t['offers'])
        self.assertFalse(VP.act_offer(self.L, 'GB', 1, 19.5, 3)['ok'])
        self.assertEqual(len(self.t['offers']), count)
        self.assertFalse(VP.act_match_counter(self.L, 'GB', 1)['ok'])
        self.assertTrue(VP.act_match(self.L, 'GB', 1)['ok'])
        self.assertEqual(self.p.team, 'GB')
        self.assertEqual(self.t['state'], 'accepted')
        self.assertNotIn(self.p.pid, self.L.free_agents)
        self.assertFalse(VP.act_match(self.L, 'GB', 1)['ok'])

    def test_decline_match_signs_rival_once_and_survives_load(self):
        self.t['state'] = 'match_requested'
        result = VP.act_withdraw(self.L, 'GB', 1)
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.p.team, 'MIN')
        self.assertEqual(self.t['state'], 'declined')
        self.assertIsNone(self.t['counter'])
        self.assertNotIn(self.p.pid, self.L.free_agents)
        self.assertEqual(len(self.L.fa_signed), 1)
        self.assertFalse(VP.act_withdraw(self.L, 'GB', 1)['ok'])
        self.assertEqual(League.load(self.L.save()).player(self.p.pid).team, 'MIN')

    def test_failed_rival_signing_keeps_decision_available(self):
        self.t['state'] = 'match_requested'
        self.L.teams['MIN'].cap.cap = 0
        result = VP.act_withdraw(self.L, 'GB', 1)
        self.assertFalse(result['ok'])
        self.assertEqual(self.t['state'], 'match_requested')
        self.assertIsNone(self.p.team)

    def test_informational_rival_is_not_a_match_request(self):
        self.assertFalse(VP.act_match(self.L, 'GB', 1)['ok'])
        with patch.object(NG, '_floor', return_value=22):
            self.assertTrue(VP.act_match_counter(self.L, 'GB', 1)['ok'])
        self.assertEqual(self.p.team, 'GB')


if __name__ == '__main__': unittest.main()

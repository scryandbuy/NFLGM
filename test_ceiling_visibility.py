import copy
import unittest
from unittest.mock import patch

import numpy as np
import targets as TG
import xp as XP
import views_club as VC
from league import League
from session import Session
from test_cap_accounting import fixture, player


class CeilingVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture()
        self.p = player(self.L)
        # These tests exercise an unconfirmed rookie estimate. Veterans now
        # correctly reveal their ceiling at 28 under the new knowledge rules.
        self.p.age = 22
        self.p.accrued = 0
        self.p.entry_year = 2026
        self.p.ratings = {k: 70.0 for k in TG.DEPTH_WEIGHTS['QB']}
        self.p.potential = 70.5
        self.p.potential_range = (70, 75)
        self.p.xp = 1_000_000
        self.s = Session(self.L, np.random.default_rng(3), 'GB')

    def reach(self):
        for _ in range(30):
            if XP.at_ceiling(self.p): return
            self.assertIsNotNone(XP.buy(self.p, 'awareness_rating', year=2026, source='You'))
        self.fail('Test player did not reach ceiling')

    def test_development_and_progression_keep_the_same_range_and_estimated_room(self):
        before = copy.deepcopy(self.s.rng.bit_generator.state)
        d = VC.development(self.s, self.L, 'GB', self.p.pid)
        with patch.object(VC, 'rail', return_value={}):
            row = VC.progression(self.s, self.L, 'GB')['rows'][0]
            overview = VC.card(self.s, self.L, self.p.pid)
        self.assertEqual(d['ceiling'], '70–75')
        self.assertEqual(d['room'], '0–5')
        self.assertTrue(d['ceiling_estimated'])
        self.assertEqual((d['ceiling'], d['room']), (row['ceiling'], row['room']))
        self.assertEqual(d['ceiling'], overview['ceiling'])
        self.assertEqual(self.p.potential, 70.5)
        self.assertEqual(before, self.s.rng.bit_generator.state)

    def test_unlock_updates_estimate_without_revealing_resolved_potential(self):
        result = VC.act_unlock_ceiling(self.L, 'GB', self.p.pid)
        self.assertTrue(result['ok'])
        self.assertEqual(self.p.potential, 71.5)
        self.assertNotIn('71.5', result['line'])
        self.assertNotIn('72', result['line'])
        self.assertEqual(VC.ceiling_read(self.p)['ceiling'], '71–76')
        self.assertEqual(VC.development(self.s, self.L, 'GB', self.p.pid)['ceiling'], '71–76')

    def test_each_new_ceiling_notifies_and_ack_survives_save(self):
        self.assertFalse(self.s.development_notices()['players'])
        self.reach()
        first = self.s.development_notices()['players'][0]
        self.assertEqual(first['unlocks'], 0)
        ledger = copy.deepcopy(self.p.xp_spent)
        rng = copy.deepcopy(self.s.rng.bit_generator.state)
        self.s.development_notices()
        self.assertEqual(ledger, self.p.xp_spent, 'reading cannot consume the notice')
        self.assertEqual(rng, self.s.rng.bit_generator.state)
        self.assertTrue(self.s.dismiss_ceiling_notice(self.p.pid, 0)['ok'])
        loaded = Session.load(self.s.save())
        self.assertFalse(loaded.development_notices()['players'])
        self.assertIsNotNone(XP.unlock(self.p))
        self.assertFalse(self.s.development_notices()['players'])
        self.reach()
        self.assertEqual(self.s.development_notices()['players'][0]['unlocks'], 1)
        self.assertFalse(self.s.dismiss_ceiling_notice(self.p.pid, 0)['ok'], 'stale notice cannot dismiss a higher ceiling')

    def test_return_after_regression_notifies_again_at_same_ceiling(self):
        self.reach()
        self.s.dismiss_ceiling_notice(self.p.pid, 0)
        self.p.ratings['awareness_rating'] -= 3
        self.assertFalse(self.s.development_notices()['players'])
        self.reach()
        self.assertEqual(self.s.development_notices()['players'][0]['unlocks'], 0)

    def test_cpu_players_excluded_and_maximum_has_no_unlock_promise(self):
        cpu = player(self.L, 'cpu', 'MIN')
        cpu.ratings = dict(self.p.ratings)
        cpu.potential = cpu.ovr
        self.assertFalse(self.s.development_notices()['players'])
        self.p.ratings = {k: 99.0 for k in self.p.ratings}
        self.p.potential = 99
        self.assertFalse(self.s.development_notices()['players'][0]['can_unlock'])
        self.assertFalse(self.s.dismiss_ceiling_notice('cpu', 0)['ok'])


if __name__ == '__main__':
    unittest.main()

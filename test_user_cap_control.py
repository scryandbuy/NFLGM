"""The user's cap moves are manual; AI clubs retain automatic compliance."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

import contracts as CT
import session as SS
from cap_engine import Contract
from league import contract_to_dict
from test_cap_accounting import fixture, player


class UserCapControlTests(unittest.TestCase):
    def setup_league(self):
        L = fixture()
        L.user_team = 'GB'
        L.set_phase('offseason')
        for abbr, t in L.teams.items():
            t.cap.cap = 30
            t.cap.rollover = 0
            player(L, pid=abbr, team=abbr, contract=Contract(3, [60]*3, signing_bonus=6))
            player(L, pid=abbr+'2', team=abbr, contract=Contract(1, [1]))
        return L

    def test_auto_cleanup_changes_ai_but_never_user_contracts_or_roster(self):
        L = self.setup_league()
        user = L.teams['GB']
        before = [(p.pid, contract_to_dict(p.contract)) for p in user.roster]
        rng = np.random.default_rng(12)
        CT.run(L, rng)
        CT.enforce(L, rng)
        CT._fix_one(L, user, rng, 10)
        self.assertEqual(before, [(p.pid, contract_to_dict(p.contract)) for p in user.roster])
        self.assertLess(user.cap_space, 0)
        self.assertGreaterEqual(L.teams['MIN'].cap_space, 0)
        self.assertFalse(any(x.get('team') == 'GB' for x in L.transactions))

    def test_cap_blocks_backend_before_rng_or_calendar_work_and_manual_move_unblocks(self):
        L = self.setup_league()
        s = SS.Session(L, np.random.default_rng(12), 'GB')
        s.stop = ('offseason', 0)
        before = copy.deepcopy(s.rng.bit_generator.state)
        contracts = [(p.pid, contract_to_dict(p.contract)) for p in L.teams['GB'].roster]
        with patch.object(s, '_advance', side_effect=AssertionError('must not advance')):
            result = s.advance()
        self.assertEqual(result['done'], 'Blocked')
        self.assertIn('over the cap', result['why'])
        self.assertEqual(s.stop, ('offseason', 0))
        self.assertEqual(before, s.rng.bit_generator.state)
        self.assertEqual(contracts, [(p.pid, contract_to_dict(p.contract)) for p in L.teams['GB'].roster])
        block = next(b for b in s.blocking() if b['kind'] == 'cap')
        self.assertEqual(block['go'], '#frontoffice/cap')
        self.assertTrue(CT.restructure_user(L, 'GB')['ok'])
        self.assertFalse(any(b['kind'] == 'cap' for b in s.blocking()))
        with patch.object(s, '_advance', return_value=dict(done='Advanced')) as advance:
            self.assertEqual(s.advance()['done'], 'Advanced')
            advance.assert_called_once()

    def test_manual_release_unblocks_and_keeps_offseason_split(self):
        L = self.setup_league()
        s = SS.Session(L, np.random.default_rng(12), 'GB')
        s.stop = ('offseason', 6)
        L.release('GB')
        self.assertAlmostEqual(L.teams['GB'].cap.dead, 2)
        self.assertAlmostEqual(L.teams['GB'].cap.dead_next, 4)
        self.assertFalse(any(b['kind'] == 'cap' for b in s.blocking()))

    def test_cutdown_checks_full_roster_before_mutating_accounting_phase(self):
        L = fixture(); L.user_team = 'GB'; L.set_phase('free_agency')
        t = L.teams['GB']; t.cap.cap = 103; t.cap.rollover = 0
        for i in range(53): player(L, pid=str(i), contract=Contract(1, [2]))
        s = SS.Session(L, np.random.default_rng(12), 'GB')
        s.stop = ('offseason', 10)
        self.assertEqual(t.cap_space, 1)
        self.assertFalse(any(b['kind'] == 'cap' for b in s.blocking()))
        for stop in [('cutdown',), ('offseason', 13), ('wire',)]:
            s.stop = stop
            self.assertTrue(any(b['kind'] == 'cap' for b in s.blocking()))
            self.assertEqual(s.advance()['done'], 'Blocked')
            self.assertEqual(s.stop, stop)
        self.assertEqual(t.phase, 'free_agency')


if __name__ == '__main__':
    unittest.main()

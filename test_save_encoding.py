"""Save encoding parity and single-parse loading regression checks."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import league
import session


class SaveEncodingTests(unittest.TestCase):
    def make_session(self):
        return session.Session(league.League(2026), np.random.default_rng(731), None)

    def test_single_encoding_matches_previous_round_trip(self):
        s = self.make_session()
        # Representative league-only extended JSON values and historical keys.
        s.L.stats = {2026: {'test': {'yards': np.int64(81),
                                   'rate': np.float64(2.5),
                                   'splits': np.array([1, 2]),
                                   'flags': {'b', 'a'}}}}
        s.gameday = {'score': [np.int64(24), 17]}
        s.runner = SimpleNamespace(save_state=lambda: {'listed_week': 3}, live=None)
        s.fired = [('GB', 'coach')]
        before = copy.deepcopy(s.rng.bit_generator.state)
        raw = s.L.to_dict()
        # The old Session.save first encoded and parsed the league snapshot.
        normalized = json.loads(json.dumps(raw, default=league._json_default))
        with patch.object(s.L, 'to_dict', return_value=normalized):
            old = json.loads(s.save())
        self.assertEqual(json.loads(s.save()), old)
        self.assertEqual(s.rng.bit_generator.state, before)
        self.assertIsInstance(s.L.stats[2026]['test']['splits'], np.ndarray)
        self.assertEqual(s.L.stats[2026]['test']['flags'], {'a', 'b'})

    def test_load_parses_once_and_preserves_rng(self):
        s = self.make_session()
        blob = s.save()
        real_loads = json.loads
        with patch.object(session.json, 'loads', wraps=real_loads) as loads:
            restored = session.Session.load(blob)
        self.assertEqual(loads.call_count, 1)
        self.assertEqual(restored.rng.bit_generator.state, s.rng.bit_generator.state)
        self.assertEqual(restored.rng.integers(0, 1000000), s.rng.integers(0, 1000000))
        again = session.Session.load(restored.save())
        self.assertEqual(json.loads(restored.save()), json.loads(again.save()))

    def test_existing_session_scalar_fallback(self):
        s = self.make_session()
        s.gameday = {'flag': np.bool_(True)}
        self.assertIs(json.loads(s.save())['_gameday']['flag'], True)


if __name__ == '__main__':
    unittest.main()

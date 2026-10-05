import unittest
from unittest.mock import patch
import plays as P
from test_fourth_down_routes import FourthDownRoutes

class ThrowawayDecision(unittest.TestCase):
    def test_down_pressure_and_window(self):
        with patch.object(P, 'rate', return_value=.8):
            early = P.throwaway_probability({}, 2, .8, .2)
            fourth = P.throwaway_probability({}, 4, .8, .2)
            self.assertGreater(early, 0)
            self.assertGreater(fourth, 0)
            self.assertLess(fourth, early / 20)
            self.assertLess(P.throwaway_probability({}, 2, .8, .9), early)
            self.assertEqual(P.throwaway_probability({}, 2, .2, .2), 0)
            self.assertEqual(P.throwaway_probability({}, 2, .8, .2, True), 0)

    def test_throwaway_precedes_accuracy_and_has_no_target(self):
        FourthDownRoutes.setUpClass()
        fixture = FourthDownRoutes()
        found = False
        with patch.object(P, 'throwaway_probability', return_value=1), patch.object(P, 'resolve_throw', side_effect=AssertionError('accuracy ran')), patch.object(P, 'resolve_zone', side_effect=AssertionError('accuracy ran')):
            for seed in range(20):
                out = fixture.play(seed, down=2)
                if out.get('throwaway'):
                    self.assertIsNone(out['target'])
                    self.assertIsNone(out['pass_def'])
                    self.assertEqual(out['type'], 'incomplete')
                    found = True
                    break
        self.assertTrue(found)

if __name__ == '__main__': unittest.main()

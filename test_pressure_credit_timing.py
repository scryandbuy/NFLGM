import unittest
from unittest.mock import patch
import plays as P

class PressureCreditTiming(unittest.TestCase):
    def resolve(self, kind, arrivals, release=3.5, **extra):
        def fake(*args, pressure_context=None, **kwargs):
            pressure_context.update(release=release, severity=.4)
            return dict(type=kind, rush_arrivals=arrivals, ttt=1.5, **extra)
        with patch.object(P, '_resolve_pass_play', side_effect=fake):
            return P._pass_play({}, {}, {}, {}, 50, None)

    def test_sack_excludes_arrivals_after_finish(self):
        out=self.resolve('sack',[('winner',1.5),('near',2.),('late',3.)],by='winner')
        self.assertEqual(out['rush_pressures'],['near','winner'])

    def test_escape_excludes_later_pocket_arrivals(self):
        out=self.resolve('scramble',[('first',1.5),('late',2.)])
        self.assertEqual(out['rush_pressures'],['first'])

    def test_throwaway_retains_cause_not_later_arrivals(self):
        out=self.resolve('incomplete',[('first',1.5),('late',2.)],throwaway=True)
        self.assertEqual(out['rush_pressures'],['first'])

    def test_marginal_arrival_is_not_pressure(self):
        out=self.resolve('complete',[('mild',3.49),('too_late',3.6)])
        self.assertEqual(out['rush_pressures'],[])

    def test_late_checkdown_does_not_rewind_window(self):
        out=self.resolve('complete',[('rusher',2.9)],depth='short',read='checkdown')
        self.assertEqual(out['rush_pressures'],['rusher'])

    def test_sacker_after_planned_window_still_counts(self):
        out=self.resolve('sack',[('winner',4.)],by='winner')
        self.assertEqual(out['rush_pressures'],['winner'])

    def test_clean_scramble_stays_clean(self):
        out=self.resolve('scramble',[('late',4.)])
        self.assertFalse(out['pressured'])

    def test_rounding_does_not_erase_causal_rusher(self):
        out=self.resolve('scramble',[('first',1.5004)])
        self.assertTrue(out['pressured'])

if __name__ == '__main__': unittest.main()

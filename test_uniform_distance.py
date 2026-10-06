import unittest
from types import SimpleNamespace as NS
import ticker as T
import schemes as S

class DisplayDistanceTests(unittest.TestCase):
    def test_distance_tracks_spots_across_fractional_movement(self):
        for teams in [('GB','TEN'),('TEN','GB')]:
            for n in range(110,900):
                start=n/10
                sticks=start-10
                for loss in (.1,.4,.5,.6,3.4,3.5,3.6,13.5):
                    end=start+loss
                    shown_loss=T.display_drive_yards(end,start,*teams)
                    self.assertEqual(T.display_distance(end,end-sticks,*teams),10+shown_loss)
    def test_reported_ten_sack_sequence(self):
        # Exact 3.4-yard loss crossing the visible fourth yard.
        self.assertEqual(T.display_distance(81.8,13.4,'TEN','GB'),14)
        self.assertEqual(T._down(2,13.4,81.8,'TEN','GB'),'2nd & 14')
    def test_inches_goal_and_no_mutation(self):
        self.assertEqual(T._down(4,.1,40.2),'4th & Inches')
        self.assertEqual(T._down(2,8.3,8.3),'2nd & Goal')
    def test_fourth_four_prioritizes_conversion_but_keeps_variation(self):
        low=S.pass_rate(4,4,7,15,'12',-.2,3195)
        high=S.pass_rate(4,4,7,15,'12',.2,3195)
        self.assertGreater(low,.90)
        self.assertGreater(high,low)
        self.assertLess(high,1.)
        self.assertLess(S.pass_rate(4,1,7,15,'12',-.2,3195),low)

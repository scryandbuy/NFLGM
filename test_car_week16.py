import unittest
from types import SimpleNamespace as NS
import game as G
import ticker

class CarolinaWeek16(unittest.TestCase):
    def test_timeout_cannot_defeat_remaining_live_knees(self):
        self.assertEqual(G._kneel_interval(3,2,3,warning_pending=False), (0.,False,False))
        self.assertEqual(G._kneel_interval(8,1,3,warning_pending=False), (0.,False,False))

    def test_timeout_still_helps_when_clock_can_be_saved(self):
        self.assertEqual(G._kneel_interval(10,1,3,warning_pending=False), (8.,True,False))
        self.assertEqual(G._kneel_interval(3,3,3,warning_pending=False), (0.,False,False))
        self.assertEqual(G._kneel_interval(5,3,3,warning_pending=False), (3.,True,False))

    def test_warning_still_stops_clock(self):
        self.assertEqual(G._kneel_interval(121,1,3), (119.,False,True))

    def timeout(self,margin=0,spot=79,down=3,yards=6):
        dr=NS(yardline=spot,score_diff=margin,down=down,togo=7,quarter=4)
        tos=G.Timeouts()
        return G._timeout_call(dr,'complete',dict(yards=yards),tos,'away',None,19)

    def test_tied_failed_third_does_not_spend_timeout_to_punt(self):
        self.assertEqual(self.timeout(),(False,None))

    def test_trailing_team_and_scoring_range_keep_timeout(self):
        self.assertEqual(self.timeout(margin=-3),(True,'away'))
        self.assertEqual(self.timeout(spot=30),(True,'away'))
        self.assertEqual(self.timeout(yards=8),(True,'away'))

    def test_return_start_label_is_explicit(self):
        self.assertEqual(ticker.drive_start_text('CAR 4',True),'Kickoff return from the CAR 4')
        self.assertEqual(ticker.drive_start_text('CAR 10'),'Started at the CAR 10')

class TimeoutAttackIntent(unittest.TestCase):
    def call(self, plan, seconds=19, half_end=None):
        dr=NS(yardline=56,score_diff=0,down=3,togo=7,quarter=4)
        tos=G.Timeouts()
        return G._timeout_call(dr,'complete',dict(yards=6),tos,'home',half_end,seconds,plan=plan)

    def test_midfield_conversion_plan_can_save_clock(self):
        self.assertEqual(self.call(dict(choice='play',hurry=True)),(True,'home'))

    def test_punt_kneel_and_no_plan_preserve_timeout(self):
        for plan in (None,dict(choice='punt',hurry=True),dict(choice='kneel',hurry=False),dict(choice='play',hurry=False)):
            self.assertEqual(self.call(plan),(False,None))

    def test_insufficient_time_for_conversion_and_score(self):
        self.assertEqual(self.call(dict(choice='play',hurry=True),seconds=14),(False,None))

    def test_direct_shot_plan_can_save_clock(self):
        self.assertEqual(self.call(dict(choice='shot',hurry=True),seconds=14),(True,'home'))

    def test_first_half_guard_unchanged(self):
        self.assertEqual(self.call(dict(choice='play',hurry=True),half_end=1800),(False,None))

import unittest
from types import SimpleNamespace as NS
import game
import ticker

class TurnoverFoulReport(unittest.TestCase):
    def test_recovering_team_foul_keeps_ball_without_awarding_old_offense_first_down(self):
        dr=NS(yardline=25.)
        pen=dict(type='penalty',penalty='Unnecessary Roughness',yards=15.,rule_yards=15.,on_offense=False,auto_first=True)
        game._enforce_turnover_penalty(dr,pen)
        self.assertEqual(dr.yardline,12.5)
        self.assertFalse(pen['auto_first'])
        line=ticker.play_line(NS(player=lambda pid:None),pen,'GB','LV')
        self.assertIn('after the turnover',str(line))
        self.assertIn('LV keeps possession.',str(line))
        self.assertNotIn('automatic first down',str(line))
    def test_former_offense_foul_advances_new_offense(self):
        dr=NS(yardline=25.)
        pen=dict(type='penalty',penalty='Unnecessary Roughness',yards=15.,rule_yards=15.,on_offense=True,auto_first=False)
        game._enforce_turnover_penalty(dr,pen)
        self.assertEqual(dr.yardline,40.)
        line=ticker.play_line(NS(player=lambda pid:None),pen,'GB','LV')
        self.assertIn('LV keeps possession.',str(line))
        self.assertIn('the GB',str(line))

if __name__=='__main__':unittest.main()

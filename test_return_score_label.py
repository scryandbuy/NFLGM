import unittest
from types import SimpleNamespace as NS
import ticker

class ReturnScoreLabel(unittest.TestCase):
    def test_kick_scores_are_special_teams(self):
        for kind in ('punt', 'kickoff'):
            dr=NS(result='Defensive touchdown', log=[dict(type=kind,touchdown=True),dict(type='extra_point')])
            self.assertEqual(ticker.drive_result(dr),'Special-teams touchdown')
    def test_defensive_scores_remain_defensive(self):
        for kind in ('interception','run'):
            dr=NS(result='Defensive touchdown',log=[dict(type=kind,defensive_td=True)])
            self.assertEqual(ticker.drive_result(dr),'Defensive touchdown')
    def test_nullified_return_does_not_relabel_score(self):
        dr=NS(result='Touchdown',log=[dict(type='punt',touchdown=True,nullified=True),dict(type='run',touchdown=True)])
        self.assertEqual(ticker.drive_result(dr),'Touchdown')

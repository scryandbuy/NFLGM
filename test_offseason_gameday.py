import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from session import Session

class OffseasonGameDayTests(unittest.TestCase):
    def fixture(self,phase='offseason'):
        s=Session.__new__(Session)
        s.L=SimpleNamespace(phase=phase,year=2028)
        s.user_team='GB';s.stop=('offseason',9);s.played=True
        s.gameday=dict(week=22,scores=[],game=None)
        s.gamedays={'2027-22':s.gameday}
        s.runner=Mock();s.runner.live={'done':False}
        return s
    @patch('views.rail',return_value={})
    def test_offseason_hides_old_game_and_blocks_stale_live(self,rail):
        for phase in ('offseason','free_agency','draft'):
            s=self.fixture(phase)
            self.assertTrue(s.gameday_view()['empty'])
            self.assertTrue(s.live_step('finish')['empty'])
            self.assertIsNone(s.live_state())
            self.assertFalse(s._finish_live())
            s.runner.live_step.assert_not_called()
            s.runner.live_partial.assert_not_called()
    @patch('views.rail',return_value={})
    def test_explicit_history_still_available(self,rail):
        s=self.fixture()
        self.assertEqual(s.gameday_view(week=22,year=2027)['week'],22)
        self.assertFalse(s.gameday_view(week=22,year=2027)['empty'])

if __name__=='__main__':unittest.main()

import unittest
from unittest.mock import patch
import session
import draft

class DraftScorePrecision(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s=session.Session.new('GB',seed=91)
        cls.L=cls.s.L
        cls.L.draft_pool=cls.L.next_class
        cls.level=draft.league_starter_level(cls.L)
        cls.scale=draft.position_scale(cls.L)
    def test_economic_plateaus_preserve_underlying_board_order(self):
        for team,selection in [('GB',160),('HOU',161),('BAL',109)]:
            with self.subTest(team=team):
                with patch.object(draft,'slot_value',side_effect=lambda slot:-slot):
                    precise=[p.pid for _,p in draft.board(self.L,team,selection,self.level,set(),self.scale)]
                with patch.object(draft,'slot_value',return_value=1.0):
                    flat=[p.pid for _,p in draft.board(self.L,team,selection,self.level,set(),self.scale)]
                self.assertEqual(precise,flat)

if __name__=='__main__':unittest.main()

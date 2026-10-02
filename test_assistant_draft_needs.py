import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from draft_day import Draft

class AssistantDraftNeeds(unittest.TestCase):
    def fixture(self):
        d=Draft.__new__(Draft);d.user='GB';d.L=SimpleNamespace(user_board={})
        a=SimpleNamespace(pid='qb');b=SimpleNamespace(pid='guard')
        d.available=lambda:[a,b]
        d.board_for=Mock(return_value=[(10,b),(5,a)])
        return d,a,b
    def test_uses_roster_board_instead_of_scout_order(self):
        d,a,b=self.fixture();self.assertIs(d.user_pick(),b)
        d.board_for.assert_called_once_with('GB')
    def test_explicit_priority_remains_authoritative(self):
        d,a,b=self.fixture();d.L.user_board={'order':[a.pid]}
        self.assertIs(d.user_pick(),a);d.board_for.assert_not_called()
    def test_exclusions_override_priority_and_fallback(self):
        d,a,b=self.fixture();d.L.user_board={'order':[a.pid],'dnd':[a.pid]}
        self.assertIs(d.user_pick(),b)
        d.L.user_board={'dnd':[a.pid,b.pid]};self.assertIsNone(d.user_pick())
    def test_reassesses_each_pick(self):
        d,a,b=self.fixture();self.assertIs(d.user_pick(),b)
        d.board_for.return_value=[(10,a),(5,b)]
        self.assertIs(d.user_pick(),a);self.assertEqual(d.board_for.call_count,2)

if __name__=='__main__':unittest.main()

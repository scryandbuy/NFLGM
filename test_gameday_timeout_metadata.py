import unittest
from types import SimpleNamespace
import gameday


class TimeoutMetadata(unittest.TestCase):
    def test_timeout_keeps_owner_and_remaining_count(self):
        league = SimpleNamespace(player=lambda pid: None)
        for side, team in (('home', 'GB'), ('away', 'MIN')):
            for left in (2, 1, 0):
                line = gameday.write_play(league, dict(type='timeout', side=side,
                    side_abbr=team, left=left, clock=80), None, 'GB', 'MIN')
                self.assertEqual(line['timeout_side'], side)
                self.assertEqual(line['timeout_team'], team)
                self.assertEqual(line['timeouts_left'], left)


if __name__ == '__main__':
    unittest.main()

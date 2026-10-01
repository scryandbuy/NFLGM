"""A return touchdown remains a turnover in the register."""
import unittest

from calibrate import Collector


class DefensiveReturnRegister(unittest.TestCase):
    def test_return_touchdown_counts_as_turnover_not_offensive_touchdown(self):
        book = Collector()
        book.ngames = book.drives_total = 1
        book.sc = [(7, 0)]
        book.inj = [0]
        book.fd = [0]
        book.plays_pd = [1]
        book.res['Defensive touchdown'] = 1
        got = book.got()
        self.assertEqual(got['drive_turnover_pct'], 100)
        self.assertEqual(got['drive_touchdown_pct'], 0)


if __name__ == '__main__':
    unittest.main()

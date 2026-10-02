"""Kicker performance rewards should grow skills without overwhelming costs."""

import unittest

import xp


class KickerXpBalanceTests(unittest.TestCase):
    def test_good_and_bad_kicking_days_keep_their_distinction(self):
        good = dict(fg_att=3, fg_made=3, xp_att=4, xp_made=4)
        misses = dict(fg_att=3, fg_made=0)
        self.assertEqual(xp.event_xp(good), 520)
        self.assertEqual(xp.event_xp(misses), -360)

    def test_big_season_bonus_and_other_specialists(self):
        self.assertEqual(xp.goal_xp(dict(fg_made=32, xp_made=40), xp.SEASON), 4250)
        self.assertEqual(xp.event_xp(dict(punts=5, punt_yds=240, punt_in20=1)), 431)
        self.assertEqual(xp.long_snap_xp(dict(snaps=9, ls_fg_made=2,
                                              ls_xp_made=3, ls_good_punts=4)), 364)


if __name__ == '__main__':
    unittest.main()

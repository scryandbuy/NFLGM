import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import club_notes as CN


class FirstStartMailTests(unittest.TestCase):
    def setUp(self):
        self.p = NS(pid='rookie', name='Kells Helton', pos='LG', age=22,
                    accrued=0, xp_spent={'_starts': 1})
        self.team = NS(abbr='GB', active=lambda: [self.p])
        self.line = dict(pb_snaps=30, pb_wins=27, pressures_allowed=3,
                         sacks_allowed=0.5, rb_snaps=24, rb_wins=18)
        self.L = NS(year=2029, week=2, notes_sent={}, stats={2029: {'rookie': {'pass_yds': 500}}},
                    game_stats={'2029-1-GB-MIN': {'rookie': self.line},
                                '2029-2-GB-CHI': {'rookie': {'pb_snaps': 99}}})

    def test_email_uses_exact_game_and_posts_once(self):
        with patch.object(CN.IB, 'post') as post:
            CN._milestones(self.L, self.team, 1)
            CN._milestones(self.L, self.team, 1)
        self.assertEqual(post.call_count, 1)
        body = post.call_args.args[3]
        self.assertIn('27/30 wins; 3 pressures and 0.5 sacks allowed', body)
        self.assertIn('18/24 wins', body)
        self.assertNotIn('99', body)

    def test_missing_game_never_uses_season_or_scratch_stats(self):
        self.L.game_stats = {}
        self.L.week_book = {'rookie': self.line}
        self.assertEqual(CN._first_start_line(self.L, self.team, self.p, 1), '')

    def test_position_lines_and_compacted_zeroes(self):
        cases = [
            ('QB', dict(pass_cmp=18, pass_att=28, pass_yds=241, pass_td=2, ints=1), '18/28, 241 yards, 2 TD, 1 INT'),
            ('HB', dict(rush_att=17, rush_yds=94, rec=2, tgt=3, rec_yds=15), '17 carries, 94 yards'),
            ('WR', dict(rec=6, tgt=9, rec_yds=105, rec_td=1), '6 catches on 9 targets, 105 yards, 1 TD'),
            ('CB', dict(tackles=7, int_def=1, pass_def=2), '1 interceptions, 2 passes defended'),
            ('LEDG', dict(tackles=4, sacks=1.5, pressures=5), '1.5 sacks, 5 pressures'),
            ('K', dict(fg_made=2, fg_att=3, xp_made=3, xp_att=3), '2/3 field goals; 3/3 extra points'),
            ('P', dict(punts=4, punt_yds=180, punt_net_yds=160, punt_in20=2), '45.0 yards per punt, 40.0 net'),
            ('LS', dict(snaps=7), '7 long snaps'),
        ]
        for pos, line, expected in cases:
            with self.subTest(pos=pos):
                self.p.pos = pos
                self.L.game_stats['2029-1-GB-MIN']['rookie'] = line
                self.assertIn(expected, CN._first_start_line(self.L, self.team, self.p, 1))

    def test_defensive_line_omits_secondary_stats_and_defense_prefix(self):
        for pos in ('DT', 'LEDG', 'REDG'):
            self.p.pos = pos
            self.L.game_stats['2029-1-GB-MIN']['rookie'] = dict(tackles=4, sacks=1, pressures=3, int_def=1, pass_def=2)
            text = CN._first_start_line(self.L, self.team, self.p, 1)
            self.assertTrue(text.startswith('4 tackles'))
            self.assertNotIn('Defense:', text)
            self.assertNotIn('interceptions', text)
            self.assertNotIn('passes defended', text)


if __name__ == '__main__':
    unittest.main()

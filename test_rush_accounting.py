import copy
import json
import unittest
import numpy as np
import advanced_stats as AS
import game as G
import league as LG
import rush_stats_migration as M


def legacy():
    line = dict(pr_reps=12, pr_wins=4, pressures=2, def_plays=8, sacks=1)
    return dict(year=2027, game_stats={'2027-8-GB-DAL': {'edge': dict(line)}},
        stats={'2027': {'edge': dict(line)}},
        players={'edge': {'career': {'2027': dict(line)}}},
        _runner_state={'week': 8}, _week_book={'edge': dict(line)})


class RushAccountingTests(unittest.TestCase):
    def test_record_and_epa_book_one_rep_on_all_dropback_outcomes(self):
        off = dict(qb={'pid': 'qb'})
        defense = dict(dl=[{'pid': 'edge'}], lb=[], db=[{'pid': 'corner'}])
        for kind in ('incomplete', 'drop', 'interception', 'complete', 'sack', 'scramble'):
            with self.subTest(kind=kind):
                book = G.StatBook()
                out = dict(type=kind, pr_reps=[('edge', True)], pb_reps=[('lt', False)],
                           pressured=True, by='edge', yards=3, target='wr', tackler='corner')
                book.record(out, off, defense, np.random.default_rng(1))
                AS.book_play(book, out, off, defense, 0.2)
                self.assertEqual((book.p['edge']['pr_reps'], book.p['edge']['pr_wins'], book.p['edge']['pressures']), (1, 1, 1))
                self.assertEqual(book.p['edge']['sacks'], int(kind == 'sack'))
                self.assertEqual(book.p['lt']['pb_snaps'], 1)

    def test_nullified_play_has_no_stats(self):
        book = G.StatBook()
        out = dict(type='sack', nullified=True, pr_reps=[('edge', True)])
        book.record(out, {}, {}, np.random.default_rng(1))
        AS.book_play(book, out, {}, {}, 1)
        self.assertEqual(book.p, {})

    def test_repair_consistent_and_idempotent(self):
        data = legacy(); report = M.migrate(data)
        self.assertEqual(report['repaired_player_games'], 1)
        for line in (data['game_stats']['2027-8-GB-DAL']['edge'], data['stats']['2027']['edge'],
                     data['players']['edge']['career']['2027'], data['_week_book']['edge']):
            self.assertEqual(M.pair(line), (6, 2))
            self.assertEqual((line['pressures'], line['sacks']), (2, 1))
        saved = json.dumps(data, sort_keys=True)
        M.migrate(data)
        self.assertEqual(json.dumps(data, sort_keys=True), saved)

    def test_correct_mixed_ambiguous_or_incomplete_records_untouched(self):
        for change in ('correct', 'mixed', 'zero', 'possible', 'aggregate', 'career'):
            with self.subTest(change=change):
                data = legacy()
                line = data['game_stats']['2027-8-GB-DAL']['edge']
                if change == 'correct': line.update(pr_reps=6, pr_wins=2)
                if change == 'mixed': data['game_stats']['2027-8-GB-DAL']['other'] = dict(pr_reps=3, pr_wins=1, pressures=1)
                if change == 'zero': line.update(pr_wins=0, pressures=0)
                if change == 'possible': line['def_plays'] = 15
                if change == 'aggregate': data['stats']['2027']['edge']['pr_reps'] = 14
                if change == 'career': data['players']['edge']['career']['2027']['pr_reps'] = 14
                before = copy.deepcopy(data)
                self.assertEqual(M.migrate(data)['repaired_player_games'], 0)
                for key in before: self.assertEqual(before[key], data[key])

    def test_postseason_repair_does_not_change_regular_career(self):
        data = legacy()
        data['game_stats']['2027-19-GB-DAL'] = data['game_stats'].pop('2027-8-GB-DAL')
        data['post_stats'] = copy.deepcopy(data['stats'])
        before = copy.deepcopy(data['stats'])
        M.migrate(data)
        self.assertEqual(M.pair(data['post_stats']['2027']['edge']), (6, 2))
        self.assertEqual(data['stats'], before)

    def test_new_books_survive_league_save_load_without_halving(self):
        league = LG.League(2027)
        player = LG.Player('edge', 'Test Edge', 'REDG', 25, {}, team='GB')
        league.players[player.pid] = player
        line = dict(pr_reps=12, pr_wins=4, pressures=4)
        league.record_stats(2027, 'edge', line, game='2027-8-GB-DAL')
        restored = LG.League.load(league.save())
        for value in (restored.stats[2027]['edge'], restored.game_stats['2027-8-GB-DAL']['edge'], restored.players['edge'].career[2027]):
            self.assertEqual(M.pair(value), (12, 4))


if __name__ == '__main__': unittest.main()

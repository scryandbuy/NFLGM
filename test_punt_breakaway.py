from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import numpy as np

import game as G
import kick_returns as KR
import plays as P
from league import League, Player


def man(pid, grade=80, **ratings):
    row = {key: grade for group in (KR.YAC['carrier'], KR.YAC['tackler'])
           for weights in group.values() for key in weights}
    row.update(pid=pid, kick_ret_rating=grade, run_block_rating=grade, **ratings)
    return row


class PuntBreakaways(unittest.TestCase):
    def rng(self, miss=False):
        return NS(uniform=lambda a, b: (a+b)/2, random=lambda: 0. if miss else 1.,
                  normal=lambda *args: .9)

    def test_trailing_slow_defender_does_not_reappear_in_front(self):
        runner, slow, punter = man('return', 95), man('slow', 65), man('punter', 40)
        out = KR._punt_breakaway(80., 15., runner, [slow], punter, 25., self.rng(), P.rate)
        self.assertEqual([x['pid'] for x in out['contacts']], ['punter'])
        self.assertAlmostEqual(out['yards'], 55.9)

    def test_faster_coverage_can_run_returner_down_before_punter(self):
        runner, fast, punter = man('return', 65), man('fast', 95), man('punter', 40)
        out = KR._punt_breakaway(80., 15., runner, [fast], punter, 25., self.rng(), P.rate)
        self.assertEqual(out['contacts'][0]['pid'], 'fast')
        self.assertLess(out['yards'], 55.)

    def test_actual_punter_is_unique_and_can_miss(self):
        runner, fast, punter = man('return', 65), man('fast', 95), man('punter', 40)
        out = KR._punt_breakaway(80., 15., runner, [fast, fast, punter], punter, 25., self.rng(True), P.rate)
        self.assertEqual([x['pid'] for x in out['contacts']], ['fast', 'punter'])
        self.assertEqual(out['yards'], 80.)
        self.assertIsNone(out['tackler'])

    def test_better_punter_tackling_prevents_scores(self):
        runner, trailing = man('return', 85), man('trailing', 75)
        counts = []
        for tackle in (30, 95):
            punter = man('punter', 50, tackle_rating=tackle, pursuit_rating=tackle)
            rng = np.random.default_rng(930)
            counts.append(sum(KR._punt_breakaway(80., 15., runner, [trailing], punter,
                                                25., rng, P.rate)['yards'] >= 80 for _ in range(2000)))
        self.assertGreater(counts[0], counts[1] * 3)

    def test_better_pursuit_catches_same_speed_runner_earlier(self):
        runner, punter = man('return', 70), man('punter', 40)
        distances = []
        for pursuit in (40, 95):
            defender = man('defender', 95, pursuit_rating=pursuit, awareness_rating=pursuit)
            distances.append(KR._punt_breakaway(95., 15., runner, [defender], punter,
                                                5., self.rng(), P.rate)['yards'])
        self.assertLess(distances[1], distances[0])

    def test_ordinary_punt_and_kickoff_do_not_use_punt_chase(self):
        rng = NS(random=lambda: 1., integers=lambda n: 0)
        with patch('events.fumble_check', return_value=None), patch.object(KR, '_punt_breakaway') as chase:
            out = KR.resolve(80., 10., man('r'), rng, P.rate, [man('c')], [man('b')], event='punt_return')
            self.assertEqual(out['ret'], 10.)
            KR.resolve(95., 25., man('r'), rng, P.rate, [man('c')], [man('b')], event='kick_return')
            chase.assert_not_called()

    def test_kickoff_breakaway_keeps_original_resolver(self):
        rng = NS(random=lambda: 0., integers=lambda n: 0)
        with patch('events.fumble_check', return_value=None), patch.object(KR, '_punt_breakaway') as punt, \
                patch.object(P, 'resolve_yards_after', return_value=dict(yards=95.)) as original:
            out = KR.resolve(95., 25., man('r'), rng, P.rate, [man('c')], [man('b')])
        self.assertTrue(out['touchdown']); punt.assert_not_called(); original.assert_called_once()

    def test_punt_supplies_actual_last_defender_and_original_line(self):
        punter = man('punter', 85)
        rng = NS(random=lambda: .5, normal=lambda *args: 45., gamma=lambda *args: 18.)
        with patch.dict(G.PUNT, return_rate=1.), patch.object(KR, 'resolve', return_value={}) as resolve:
            G.punt(75., punter, man('return'), rng, P.rate)
        self.assertIs(resolve.call_args.kwargs['punt_safety'], punter)
        self.assertEqual(resolve.call_args.kwargs['punt_safety_spot'], 25.)

    def test_touchback_and_fair_catch_never_enter_return_model(self):
        rng = NS(random=lambda: .99, normal=lambda *args: 60.)
        with patch.object(KR, 'resolve') as resolve:
            self.assertTrue(G.punt(40., man('p'), man('r'), rng, P.rate)['touchback'])
            with patch.dict(G.PUNT, return_rate=0.):
                self.assertEqual(G.punt(85., man('p'), man('r'), rng, P.rate)['how'], 'fair_catch')
            resolve.assert_not_called()

    def test_return_td_survives_stat_aggregation_and_reload(self):
        league = League(2031); player = Player('r', 'Returner', 'WR', 24, {})
        league.players[player.pid] = player
        book = G.StatBook()
        KR.book_return(book, 'pr', dict(returner='r', ret=80., touchdown=True))
        league.record_stats(2031, 'r', book.p['r'])
        restored = League.load(league.save())
        self.assertEqual(restored.stats[2031]['r']['pr_td'], 1)
        self.assertEqual(restored.stats[2031]['r']['pr_yds'], 80.)
        self.assertEqual(restored.stats[2031]['r']['rec_td'], 0)

    def test_new_breakaway_scores_in_drive_and_return_flag_can_erase_it(self):
        from test_kick_return_outcomes import ReturnTests
        draws = iter([.99, 0., 0., 0.])  # no block; return; clear lane; missed punter
        rng = NS(random=lambda: next(draws), normal=lambda *args: 45., gamma=lambda *args: 18.,
                 uniform=lambda a,b: (a+b)/2, integers=lambda n: 0)
        with patch('events.fumble_check', return_value=None):
            out = G.punt(75., man('p', 40), man('pr', 95), rng, P.rate,
                         return_coverage=[man('coverage', 70)], return_blockers=[man('block', 80)])
        self.assertTrue(out['breakaway_opportunity'])
        self.assertEqual(out['punt_pursuit'][0]['pid'], 'p')
        self.assertEqual((out['ret'], out['touchdown']), (70., True))
        fixture = ReturnTests(); fixture.setUp()
        drive, book = fixture.punt_drive(out)
        self.assertEqual(drive.points, -7)
        self.assertEqual(book.p['pr']['pr_td'], 1)
        drive, book = fixture.punt_drive(out, dict(penalty='Return Holding', yards=10, on_offense=False))
        self.assertEqual(drive.points, 0)
        self.assertEqual(book.p['pr']['pr_td'], 0)


if __name__ == '__main__': unittest.main()

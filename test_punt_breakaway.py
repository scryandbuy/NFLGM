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
        self.assertGreater(out['yards'], 15.)
        self.assertLess(out['yards'], 55.)  # punter runs toward the returner

    def test_faster_coverage_can_run_returner_down_before_punter(self):
        runner, fast, punter = man('return', 65), man('fast', 95), man('punter', 40)
        out = KR._punt_breakaway(95., 15., runner, [fast], punter, 0., self.rng(), P.rate)
        self.assertEqual(out['contacts'][0]['pid'], 'fast')
        self.assertLess(out['yards'], 55.)

    def test_actual_punter_is_unique_and_can_miss(self):
        runner, fast, punter = man('return', 65), man('fast', 95), man('punter', 40)
        out = KR._punt_breakaway(80., 15., runner, [fast, fast, punter], punter, 25., self.rng(True), P.rate)
        self.assertCountEqual([x['pid'] for x in out['contacts']], ['fast', 'punter'])
        self.assertEqual([x['at'] for x in out['contacts']], sorted(x['at'] for x in out['contacts']))
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

    def test_leverage_can_stop_faster_runner_but_not_from_behind(self):
        self.assertIsNotNone(KR._punt_intercept(9., 7., ahead=10., lateral=5.))
        self.assertIsNone(KR._punt_intercept(9., 7., ahead=-10., lateral=5.))
        self.assertIsNone(KR._punt_intercept(9., 7., ahead=10., lateral=30.))
        self.assertIsNone(KR._punt_intercept(9., 7., ahead=10., lateral=5., reaction=2.))

    def test_punter_already_passed_cannot_reappear_beside_runner(self):
        out = KR._punt_breakaway(80.,70.,man('r',95),[man('c',70)],man('p',40),25.,self.rng(),P.rate)
        self.assertEqual(out['yards'],80.)
        self.assertEqual(out['contacts'],[])

    def test_intercept_respects_distance_and_elapsed_time(self):
        from math import hypot
        for runner, defender, ahead, lateral, reaction in ((8.,8.,10.,6.,0.), (8.,9.,-5.,0.,0.),
                                                           (9.,7.,10.,5.,.1)):
            traveled = KR._punt_intercept(runner, defender, ahead, lateral, reaction)
            elapsed = traveled / runner
            self.assertAlmostEqual(hypot(traveled-ahead, lateral), defender*(elapsed-reaction))

    def test_outside_contain_player_can_make_breakaway_stop(self):
        runner, punter = man('return', 95), man('punter', 40)
        unit = [man('gunner1', 95), man('gunner2', 94), man('contain1', 85), man('contain2', 84)]
        rng = self.rng()
        rng.uniform = lambda a,b: -15. if (a,b)==(-18.,18.) else (a+b)/2
        out = KR._punt_breakaway(80., 15., runner, unit, punter, 25., rng, P.rate)
        self.assertEqual(out['tackler']['pid'], 'contain1')
        self.assertEqual(out['contacts'][0]['leverage'], 'contain')
        self.assertLess(out['yards'], 30.)

    def test_coverage_order_and_duplicates_do_not_create_extra_chances(self):
        unit = [man('gunner1',95), man('gunner2',94), man('contain1',85), man('contain2',84)]
        a = KR._punt_breakaway(80.,15.,man('r',95),unit,man('p',40),25.,np.random.default_rng(52),P.rate)
        b = KR._punt_breakaway(80.,15.,man('r',95),list(reversed(unit))+[unit[2]],man('p',40),25.,np.random.default_rng(52),P.rate)
        self.assertEqual(a,b)

    def test_stronger_contain_tackling_stops_more_open_lanes(self):
        touchdowns = []
        for tackle in (30,95):
            unit = [man('g1',95),man('g2',94),man('c1',85,tackle_rating=tackle),man('c2',84,tackle_rating=tackle)]
            touchdowns.append(sum(KR._punt_breakaway(80.,15.,man('r',95),unit,man('p',40),25.,
                                  np.random.default_rng(seed),P.rate)['yards'] >= 80. for seed in range(1000)))
        self.assertGreater(touchdowns[0],touchdowns[1])

    def test_ordinary_punt_and_kickoff_do_not_use_punt_chase(self):
        rng = NS(random=lambda: 1., integers=lambda n: 0)
        with patch('events.fumble_check', return_value=None), patch.object(KR, '_punt_breakaway') as chase:
            out = KR.resolve(80., 10., man('r'), rng, P.rate, [man('c')], [man('b')], event='punt_return')
            self.assertEqual(out['ret'], 10.)
            KR.resolve(95., 25., man('r'), rng, P.rate, [man('c')], [man('b')], event='kick_return')
            chase.assert_not_called()

    def test_kickoff_breakaway_uses_kickoff_pursuit(self):
        rng = np.random.default_rng(4)
        with patch('events.fumble_check', return_value=None), patch.object(KR, '_punt_breakaway') as punt, \
                patch.object(KR, 'KICKOFF_BREAKAWAY_BASE', .99), \
                patch.object(KR, 'KICKOFF_BREAKAWAY_UPPER', .99):
            out = KR.resolve(95., 25., man('r'), rng, P.rate, [man('c')], [man('b')])
        self.assertTrue(out['breakaway_opportunity'])
        self.assertIn('kickoff_pursuit', out)
        punt.assert_not_called()

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

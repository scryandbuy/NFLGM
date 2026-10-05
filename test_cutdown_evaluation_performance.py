"""Cutdown shortcuts must preserve football decisions and expire after a sweep."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import roster_needs as RN
import waivers as WV
import cutdown as CD
from test_roster_needs import Team, player


class CutdownEvaluationTests(unittest.TestCase):
    def test_failed_repair_stops_when_nothing_changes_but_retries_after_a_move(self):
        for progress in (False, True):
            league = SimpleNamespace(teams={}, transactions=[])
            with patch.object(CD, 'trim_specialists', return_value=[]), \
                 patch.object(CD, 'run', return_value=([], [])) as run, \
                 patch.object(CD, 'fill_short', return_value=0), \
                 patch.object(CD, 'repair_shape', side_effect=[1, 0] if progress else [0]), \
                 patch.object(CD, 'repair_depth', return_value=0), \
                 patch.object(CD, 'violations', return_value=[{'missing': ['K']}]):
                self.assertEqual(CD.finalize(league, None), ([], 0))
                self.assertEqual(run.call_count, 2 if progress else 1)

    def test_score_matches_full_report_for_fronts_packages_and_missing_roles(self):
        pool = [player(pos, n) for pos in RN.POSITIONS for n in range(3)]
        for i, p in enumerate(pool):
            p.ovr = 58.0 + (i * 7 % 36)
        for front in ('4-3', '3-4', 'Multiple'):
            for offense in ('11', '12', '21'):
                team = Team(front, offense, pool)
                prepared = RN.assessment_inputs(team, pool)
                variants = [pool, pool[::2], [p for p in pool if p.pos not in ('LT', 'LS', 'CB')], []]
                for players in variants:
                    with self.subTest(front=front, offense=offense, size=len(players)):
                        expected = RN.assess(team, players, prepared=prepared)['score']
                        self.assertEqual(RN.assess(team, players, prepared=prepared, score_only=True), expected)

    def test_notification_results_match_uncached_reads_and_refresh_next_sweep(self):
        team = Team(players=[player(pos, n) for pos in RN.POSITIONS for n in range(4)])
        team.cap_space = 100.0
        team.ctx = lambda: {}
        candidates = [player('QB', 10), player('HB', 10), player('CB', 10)]
        for p in candidates:
            p.ovr = 70.0
            p.contract = None
            p.accrued = 1
        lookup = {p.pid: p for p in candidates}
        league = SimpleNamespace(teams={'DAL': team, 'GB': Team()}, user_team='GB',
                                 phase='offseason', year=2027, transactions=[], player=lookup.get)

        def entries():
            return [dict(pid=p.pid, from_team='MIN', user_notified=False) for p in candidates]

        real_reaches = WV.reaches_user
        def uncached(league, entry, week, market=None, **_):
            return real_reaches(league, entry, week, market=market)

        with patch.object(WV, 'priority', return_value=['DAL', 'GB']), \
             patch('valuation.pool_from_league', return_value=None), \
             patch('valuation.value_player', return_value={'value': 1}), \
             patch('gm_surfaces.claim_value', return_value=1), \
             patch('inbox.post') as post:
            for changed in (False, True):
                if changed:
                    team.roster = [p for p in team.roster if p.pos not in ('QB', 'HB')]
                    team.gm.off_personnel = '21'
                original, optimized = entries(), entries()
                post.reset_mock()
                with patch.object(WV, 'reaches_user', side_effect=uncached):
                    WV.notify_user(league, original, 0, digest=True)
                expected_mail = [(c.args[1:], copy.deepcopy(c.kwargs)) for c in post.call_args_list]
                post.reset_mock()
                with patch.object(RN, 'assess', wraps=RN.assess) as assess:
                    WV.notify_user(league, optimized, 0, digest=True)
                self.assertEqual(optimized, original)
                # Compare message contents, excluding the mutable league argument.
                self.assertEqual([(c.args[1:], c.kwargs) for c in post.call_args_list],
                                 expected_mail)
                self.assertEqual(assess.call_count, 1)


if __name__ == '__main__':
    unittest.main()

"""Recorded blitz production has value regardless of the defender's position."""
import unittest
from types import SimpleNamespace as NS
from awards import Ballot


class DefensiveBackRushAwards(unittest.TestCase):
    def setUp(self):
        self.ballot = Ballot.__new__(Ballot)

    def test_zero_rush_evidence_preserves_coverage_score(self):
        line = dict(int_def=3, tackles=80, ff=2, pass_def=12)
        for pos in ('CB', 'FS', 'SS'):
            with self.subTest(pos=pos):
                self.assertEqual(self.ballot.def_score(NS(pos=pos), line), 106.)
                self.assertEqual(self.ballot.def_score(NS(pos=pos), {}), 0.)

    def test_same_rush_production_same_credit_including_half_sacks(self):
        for line, value in ((dict(sacks=.5), 1.5),
                            (dict(sacks=2.5, pressures=9), 16.5)):
            for pos in ('CB', 'FS', 'SS', 'LEDG', 'DT', 'MIKE'):
                with self.subTest(pos=pos, line=line):
                    self.assertEqual(self.ballot.def_score(NS(pos=pos), line), value)

    def test_coverage_remains_an_alternative_to_blitz_production(self):
        players = [NS(pid='blitzer',pos='SS'), NS(pid='cover',pos='CB')]
        lines = [dict(sacks=4.5, pressures=20, tackles=50),
                 dict(int_def=6, pass_def=18, tackles=55)]
        self.ballot.players = lambda filt=None: iter(zip(players, lines))
        self.assertEqual(self.ballot.dpoy().pid, 'cover')
        first, second = self.ballot.all_pro()
        self.assertEqual({p.pid for p in first}, {'blitzer', 'cover'})
        self.assertEqual(second, [])
        # An otherwise identical safety with actual blitz production can
        # beat a teammate; merely appearing in a pass rush earns no points.
        players[1].pos = 'SS'
        lines[0] = dict(tackles=60, sacks=.5, pressures=2)
        lines[1] = dict(tackles=60, pr_reps=100)
        self.assertEqual(self.ballot.dpoy().pid, 'blitzer')
        first, second = self.ballot.all_pro()
        self.assertEqual(first[0].pid, 'blitzer')
        self.assertEqual(second[0].pid, 'cover')


if __name__ == '__main__': unittest.main()

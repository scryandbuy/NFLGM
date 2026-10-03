"""Annual staff credit survives transactions and uses actual specialist work."""
import copy
import unittest
from types import SimpleNamespace as NS

import staff as ST


def fixture():
    teams = {a: NS(roster=[]) for a in ('A', 'B')}
    def line(team, epa, net):
        return dict(team=team, pass_plays=40, rush_plays=20, pass_epa=epa,
                    rush_epa=0, def_epa=-epa, def_plays=60,
                    fg_att=20, fg_made=18, punts=40, punt_net_yds=net * 40)
    return NS(year=2028, teams=teams, stats={2028: {}},
              schedule=[(1, 'A', 'B', 24, 17)], game_stats={
                  '2028-1-B-A': {'traded': line('A', 12, 30),
                                 'released': line('B', -12, 50)}})


class AnnualEvidence(unittest.TestCase):
    def test_trades_cuts_and_ir_do_not_transfer_staff_credit(self):
        L = fixture()
        expected = ST.unit_ranks(L, 2028)
        self.assertEqual(expected['A']['oc'], 1)
        self.assertEqual(expected['B']['dc'], 1)
        L.teams['B'].roster = [NS(pid='traded')]
        L.teams['A'].ir = [NS(pid='released')]
        L.stats[2028] = {'traded': {'pass_epa': 5000, 'pass_plays': 1}}
        self.assertEqual(ST.unit_ranks(L, 2028), expected)

    def test_punt_quality_changes_rank_but_volume_does_not(self):
        L = fixture()
        book = L.game_stats['2028-1-B-A']
        self.assertEqual(ST.unit_ranks(L, 2028)['B']['st'], 1)
        book['traded']['punt_net_yds'] = 60 * 40
        self.assertEqual(ST.unit_ranks(L, 2028)['A']['st'], 1)
        book['released']['punts'] *= 3
        book['released']['punt_net_yds'] *= 3
        self.assertEqual(ST.unit_ranks(L, 2028)['A']['st'], 1)

    def test_playoffs_other_years_and_current_roster_cannot_fill_missing_books(self):
        L = fixture()
        expected = ST.unit_ranks(L, 2028)
        enormous = {'x': dict(team='B', pass_epa=9999, pass_plays=1)}
        L.game_stats.update({'2028-19-B-A': enormous, '2027-1-B-A': enormous})
        self.assertEqual(ST.unit_ranks(L, 2028), expected)
        L.schedule.append((2, 'A', 'B', 3, 7))
        self.assertTrue(all(v is None for r in ST.unit_ranks(L, 2028).values() for v in r.values()))

    def test_missing_unit_evidence_is_not_zero_ranked_performance(self):
        L = fixture()
        L.game_stats['2028-1-B-A']['released'] = dict(team='B', snaps=10)
        self.assertEqual(ST.unit_ranks(L, 2028)['B'], dict(oc=None, dc=None, st=None))
        L.game_stats = {}
        self.assertTrue(all(v is None for r in ST.unit_ranks(L, 2028).values() for v in r.values()))

    def test_canonical_zero_beats_legacy_punt_alias(self):
        L = fixture()
        row = L.game_stats['2028-1-B-A']['released']
        row.update(punt_net_yds=0, punt_net=10000)
        self.assertEqual(ST.unit_ranks(L, 2028)['A']['st'], 1)
        del row['punt_net_yds']
        self.assertEqual(ST.unit_ranks(L, 2028)['B']['st'], 1)

    def test_evaluation_reads_do_not_change_books(self):
        L = fixture()
        original = copy.deepcopy(vars(L))
        ST.unit_ranks(L, 2028)
        ST.midseason_evidence(L, 18)
        self.assertEqual(vars(L), original)


if __name__ == '__main__':
    unittest.main()

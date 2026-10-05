"""Coverage repair should compare the value of its actual departures."""
import unittest

from cap_engine import Contract
import cutdown as CD
import roster_needs as RN
from test_draft_planning import set_grade
import test_essential_roster_repair as essential_tests


class RepairReplacementValueTests(unittest.TestCase):
    def fixture(self):
        league, team, incoming = essential_tests.EssentialRosterTests().roster()
        weak = league.player('SAM1')
        weak.contract = Contract(1, [1.]); set_grade(weak, 55)
        valuable = league.player('LEDG2')
        valuable.contract = Contract(1, [1.]); set_grade(valuable, 79)
        for pid in ('LEDG0', 'LEDG1', 'REDG0', 'REDG1'):
            set_grade(league.player(pid), 90)
        # This deliberately crowded edge room leaves both departures outside
        # the current packages, as in the saved Thomas/fullback replacement.
        for pid in ('WR4', 'HB2'):
            p = league.player(pid); p.pos = 'LEDG'; set_grade(p, 90)
        team.roster.remove(valuable); team.roster.insert(0, valuable)
        team.sync_cap()
        return league, team, incoming, valuable, weak

    def test_equal_coverage_does_not_make_unequal_assets_interchangeable(self):
        for order in ('first', 'last', 'renamed'):
            with self.subTest(order=order):
                league, team, incoming, valuable, weak = self.fixture()
                if order == 'last':
                    team.roster.remove(valuable); team.roster.append(valuable)
                if order == 'renamed':
                    valuable.name = 'Different Veteran'; weak.name = 'Other Reserve'
                    valuable.potential = 50; weak.potential = 99
                before = RN.assess(team); coverage = RN.essential_coverage(team, report=before)
                # The old decision key tied despite 79-vs-55 reserve value.
                gains = [RN.assess(team, [p for p in team.active() if p is not out]
                                  + [incoming])['score'] - before['score']
                         - RN.retention_value(team, out) for out in (valuable, weak)]
                self.assertAlmostEqual(*gains)
                self.assertGreater(gains[0], 0)
                self.assertEqual(CD.repair_shape(league), 1)
                self.assertIn(valuable, team.active()); self.assertNotIn(weak, team.active())
                self.assertIn(incoming, team.active()); self.assertEqual(len(team.active()), 53)
                self.assertTrue(RN.coverage_not_worse(coverage, RN.essential_coverage(team)))
                self.assertGreaterEqual(team.cap_space, 0)
                self.assertEqual([x['pid'] for x in league.transactions if x['kind'] == 'release'], [weak.pid])

    def test_required_job_is_not_blocked_by_optional_market_threshold(self):
        league, team, incoming, valuable, weak = self.fixture()
        team.gm.aggression = 0.; team.gm.patience = 1.
        self.assertEqual(CD.repair_shape(league), 1)
        self.assertIn(valuable, team.active()); self.assertIn(incoming, team.active())
        self.assertNotIn('offense:C:0', RN.essential_coverage(team)['shortages'])

    def test_valuable_surplus_is_not_untouchable_when_other_departures_protected(self):
        league, team, incoming, valuable, weak = self.fixture()
        for p in team.active():
            if p is not valuable:
                p.draft_round = 1; p.draft_year = league.year
        self.assertEqual(CD.repair_shape(league), 1)
        self.assertNotIn(valuable, team.active()); self.assertIn(weak, team.active())
        self.assertIn(incoming, team.active())
        self.assertNotIn('offense:C:0', RN.essential_coverage(team)['shortages'])


if __name__ == '__main__': unittest.main()

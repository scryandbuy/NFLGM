"""A coach hired after a coordinator answer must be the coach the owner evaluated."""
import unittest
from dataclasses import asdict
from unittest.mock import patch

import coaching_pool as CP
from gm_engine import GM
from league import League
from staff import Coach
from test_cap_accounting import fixture
from test_trade_roster_limit import fixture as roster_fixture


class PendingHireIdentityTests(unittest.TestCase):
    def test_owner_fit_recognizes_personnel_the_roster_can_field(self):
        league, _star, _pick = roster_fixture()
        team = league.teams['GB']
        for player in team.roster:
            if player.pos in ('WR', 'TE'):
                player.ratings = {key: (95 if player.pos == 'WR' else 55)
                                  for key in player.ratings}
        receiver_coach = GM(off_personnel='11')
        tight_end_coach = GM(off_personnel='13')
        receiver_fit, _ = CP.roster_fit(team, receiver_coach)
        tight_end_fit, _ = CP.roster_fit(team, tight_end_coach)
        self.assertGreater(receiver_fit, tight_end_fit + .1)
        self.assertGreater(CP.scheme_similarity(team.gm, receiver_coach),
                           CP.scheme_similarity(team.gm, tight_end_coach))

    def test_saved_first_choice_keeps_identity_and_runs_conversion(self):
        league = fixture()
        coordinator = Coach('Mira Vale', 'dc', 85, 60, 'coverage disguise', 42, team='GB')
        league.teams['GB'].staff = {'dc': coordinator}
        league.teams['MIN'].staff = {}
        evaluated = GM(name=coordinator.name, def_front='3-4', off_personnel='21',
                       coverage=.735, blitz=.828, off_blocking='gap')
        league.pending_hires = {'MIN': dict(first=coordinator.name, first_from=['GB', 'dc'],
                                           first_gm=asdict(evaluated), first_hc_ask=8.4,
                                           second=None, year=league.year)}
        league = League.load(league.save())

        with patch.object(CP, 'make_candidate', side_effect=AssertionError('coach rerolled')), \
                patch('position_change.convert_misfits', return_value=['converted']) as convert:
            hired = CP.complete_pending_hire(league, 'MIN', __import__('numpy').random.default_rng(7), True)

        self.assertEqual((hired.def_front, hired.off_personnel, hired.coverage, hired.blitz),
                         ('3-4', '21', .735, .828))
        self.assertEqual(hired.salary, 8.4)
        self.assertIs(league.teams['MIN'].gm, hired)
        self.assertIsNone(league.teams['GB'].staff['dc'])
        convert.assert_called_once()
        self.assertEqual(league.transactions[-1]['conversions'], 1)


if __name__ == '__main__':
    unittest.main()

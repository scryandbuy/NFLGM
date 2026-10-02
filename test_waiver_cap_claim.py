"""Waiver awards must account for the roster cut that makes room."""

import unittest
from unittest.mock import patch

import numpy as np

from cap_engine import Contract
from league import League, Player, Team
import waivers


def fixture(space, second_candidate=False):
    league = League(2026)
    team = Team('GB', 'United North', 'United')
    team.league = league
    league.teams['GB'] = team
    league.set_phase('regular')
    league.week = 10

    def add(pid, rating, contract, club='GB'):
        player = Player(pid, pid, 'C', 26, {'test_ovr': rating},
                        team=club, contract=contract, accrued=5)
        league.players[pid] = player
        if club:
            team.roster.append(player)
        return player

    for i in range(51 if second_candidate else 52):
        add(f'keep{i}', 90, Contract(1, [1.0]))
    # The future bonus accelerates on release: $0.40m dead against a $0.25m hit.
    bad = add('bad_cut', 50, Contract(2, [.05, .05], signing_bonus=.4))
    good = add('good_cut', 55, Contract(1, [.2])) if second_candidate else None
    incoming = add('claim', 80, Contract(1, [.1]), club=None)
    team.sync_cap()
    team.cap.cap = team.cap.charges('regular') + space
    league.waivers = [dict(pid=incoming.pid, from_team='MIN', week=10,
                           year=2026, claims=[], user_notified=False)]
    return league, team, bad, good, incoming


class WaiverCapClaimTests(unittest.TestCase):
    def run_wire(self, league):
        def move_gain(team, incoming, outgoing=None):
            return 2.0 if outgoing is None or outgoing.pid == 'bad_cut' else 1.0

        with patch('targets.position_score', side_effect=lambda p, pos, scheme=None: p.get('test_ovr', 0)), \
             patch('waivers.priority', return_value=['GB']), \
             patch('waivers.wants', return_value=True), \
             patch('waivers._claim_budget', return_value=True), \
             patch('valuation.pool_from_league', return_value=None), \
             patch('valuation.value_player', return_value={'value': 1}), \
             patch('roster_needs.move_gain', side_effect=move_gain), \
             patch('practice_squad.locked', return_value=False), \
             patch('practice_squad.protected', return_value=False), \
             patch('inbox.pending', return_value=[]):
            return waivers.process(league, np.random.default_rng(1), 10)

    def test_rejects_claim_when_required_cut_creates_cap_violation(self):
        league, team, bad, _, incoming = fixture(.12)
        awarded = self.run_wire(league)
        self.assertEqual(awarded, [])
        self.assertEqual(bad.team, 'GB')
        self.assertIsNone(incoming.team)
        self.assertEqual(len(team.active()), 53)
        self.assertGreaterEqual(team.cap_space, 0)

    def test_awards_claim_when_combined_release_and_contract_fit(self):
        league, team, bad, _, incoming = fixture(.30)
        awarded = self.run_wire(league)
        self.assertEqual(awarded, [(incoming.pid, 'GB')])
        self.assertIsNone(bad.team)
        self.assertEqual(incoming.team, 'GB')
        self.assertEqual(len(team.active()), 53)
        self.assertGreaterEqual(team.cap_space, 0)

    def test_tries_next_eligible_cut_when_preferred_cut_cannot_fit(self):
        league, team, bad, good, incoming = fixture(.12, second_candidate=True)
        awarded = self.run_wire(league)
        self.assertEqual(awarded, [(incoming.pid, 'GB')])
        self.assertEqual(bad.team, 'GB')
        self.assertIsNone(good.team)
        self.assertEqual(incoming.team, 'GB')
        self.assertEqual(len(team.active()), 53)
        self.assertGreaterEqual(team.cap_space, 0)


if __name__ == '__main__':
    unittest.main()

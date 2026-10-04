"""FA valuation must keep the same offers while reusing immutable roster work."""

import unittest
from unittest.mock import patch

import numpy as np

import market
import roster_needs as RN
from test_draft_planning import fixture


def uncached_gains(team, players, baseline=None):
    baseline = RN.assess(team) if baseline is None else baseline
    return {p.pid: RN.move_gain(team, p, baseline=baseline) for p in players}


class FACandidateCacheTests(unittest.TestCase):
    def test_gains_and_bids_match_uncached_path_without_rng_changes(self):
        league, team = fixture()
        team.gm.off_personnel = '21'
        team.gm.def_front = '3-4'
        pool = league.draft_pool

        expected = uncached_gains(team, pool)
        self.assertEqual(RN.candidate_gains(team, pool), expected)

        # The candidate cache belongs to one pass. Changing the coach must
        # recompute both the offensive floor and package mix on the next pass.
        team.gm.off_personnel = '10'
        self.assertEqual(RN.candidate_gains(team, pool), uncached_gains(team, pool))

        first_rng = np.random.default_rng(815)
        second_rng = np.random.default_rng(815)
        with patch.object(RN, 'candidate_gains', side_effect=uncached_gains):
            original = market.ai_bids(league, pool, 1, first_rng)
        optimized = market.ai_bids(league, pool, 1, second_rng)
        saved = lambda bids: {pid: [offer.to_save() for offer in offers]
                              for pid, offers in bids.items()}
        self.assertEqual(saved(optimized), saved(original))
        self.assertEqual(second_rng.bit_generator.state, first_rng.bit_generator.state)


if __name__ == '__main__':
    unittest.main()

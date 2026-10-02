"""Economic release gates for avoidable late salaries.

These assertions describe desired economic behavior, not v1's implementation.
The model must not go live while they fail. Case independently found by
Review code changes (3).
"""
import unittest
import contract_offer_model as M


class EconomicReleaseGates(unittest.TestCase):
    def test_preference_and_acceptance_cannot_disagree(self):
        for security in (0., .5, 1.):
            beliefs = M.PlayerBeliefs(27, 'WR', 20, security, .5)
            reference = M.OfferCash((16., 16.), 8.)
            for apy in (10., 18., 19., 20., 25.):
                for share in (0., .2, .5, .75):
                    offer = M.OfferCash((apy * (1-share),) * 5, apy * 5 * share)
                    result = M.compare(offer, reference, beliefs)
                    self.assertEqual(result['preferred'], result['acceptable'])
                    self.assertEqual(result['acceptable'], result['ratio'] >= 1 - 1e-9)

    def test_actual_builder_backload_cannot_substitute_for_security(self):
        from types import SimpleNamespace as N
        import market
        from test_cap_accounting import fixture, player
        L = fixture(); L.set_phase('free_agency')
        p = player(L); p.pos = 'WR'
        team = L.teams['GB']; team.gm = N(restructure_depth=.5)
        terms = market.signing_terms(L, p, team, 14, 5, 301.2, front_load=0, bonus=0)
        offer = M.OfferCash(tuple(terms['base']), terms['signing_bonus'])
        self.assertEqual(offer.base, (0, 7, 14, 21, 28))
        b = M.PlayerBeliefs(24, 'WR', 10, security=1, money=0)
        reference = M.OfferCash((8, 8), 4)
        self.assertFalse(M.compare(offer, reference, b)['acceptable'],
                         'Real builder output overvalues avoidable late salaries')

    def test_unprotected_balloon_is_not_security_for_young_player(self):
        b = M.PlayerBeliefs(24, 'WR', 10, security=1, money=0)
        reference = M.OfferCash((8, 8), 4)
        balloon = M.OfferCash((3, 3, 3, 3, 60), 0)
        self.assertFalse(M.compare(balloon, reference, b)['acceptable'],
                         'Unprotected $60m fifth year is being overvalued')

    def test_unprotected_balloon_is_not_security_for_older_player(self):
        b = M.PlayerBeliefs(30, 'WR', 10, security=1, money=0)
        reference = M.OfferCash((8, 8), 4)
        balloon = M.OfferCash((3, 3, 3, 3, 60), 0)
        self.assertFalse(M.compare(balloon, reference, b)['acceptable'],
                         'Older age does not make the balloon protected')


if __name__ == '__main__':
    unittest.main()

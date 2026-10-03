import copy
import unittest
from types import SimpleNamespace as N
import numpy as np
import personality as PT
from league import League
from test_cap_accounting import fixture, player


class CharacterTraits(unittest.TestCase):
    def test_legacy_migration_preserves_traits_rng_and_input_save(self):
        league = fixture(); p = player(league)
        p.traits = dict(work_ethic=20, loyalty=60, ambition=50, financial_priority=40)
        p.dev = 'superstar'; p.potential = 92.; p.xp = 1234.
        blob = league.save(); before = copy.deepcopy(blob)
        a = League.load(blob); b = League.load(blob)
        self.assertEqual(blob, before)
        self.assertEqual(a.player('p').traits, b.player('p').traits)
        self.assertEqual({k: a.player('p').traits[k] for k in p.traits}, p.traits)
        self.assertEqual((a.player('p').xp, a.player('p').dev, a.player('p').potential), (1234., 'superstar', 92.))
        self.assertEqual(League.load(a.save()).player('p').traits, a.player('p').traits)

    def test_generation_does_not_shift_existing_trait_draws(self):
        rng = np.random.default_rng(35); expected = PT.draw(rng); state = copy.deepcopy(rng.bit_generator.state)
        rng2 = np.random.default_rng(35); p = N(pid='rookie', traits=None)
        PT.ensure(p, rng2)
        self.assertEqual({k: p.traits[k] for k in expected}, expected)
        self.assertEqual(rng2.bit_generator.state, state)
        before = copy.deepcopy(p.traits); PT.ensure(p, rng2)
        self.assertEqual(p.traits, before)
        self.assertEqual(rng2.bit_generator.state, state)

    def test_discipline_has_no_xp_or_contract_effect(self):
        p = N(traits=dict(work_ethic=20, financial_priority=70, loyalty=40, ambition=60))
        functions = (PT.xp_mult, PT.ask_mult, PT.extension_discount, PT.entitlement_mult)
        before = [f(p) for f in functions]
        for value in (0, 50, 100):
            p.traits['discipline'] = value
            self.assertEqual([f(p) for f in functions], before)
        self.assertAlmostEqual(PT.xp_mult(p), .88)

    def test_bounded_penalty_multipliers_for_player_and_sim_dict(self):
        for value in (0, 50, 100):
            for name, strength in [('False Start', .1), ('Roughing the Passer', .2),
                                   ('Return Holding', .05), ('Illegal Block in Back', .05),
                                   ('Delay of Game', 0), ('Too Many Men', 0)]:
                expected = 1 + strength*(50-value)/50
                for p in (N(traits={'discipline': value}), {'traits': {'discipline': value}}, {'discipline': value}):
                    self.assertAlmostEqual(PT.penalty_multiplier(p, name), expected)
        self.assertEqual(PT.penalty_multiplier({}, 'False Start'), 1.)
        for invalid in (None, 'invalid', float('nan')):
            self.assertEqual(PT.discipline({'discipline': invalid}), 50.)


if __name__ == '__main__': unittest.main()

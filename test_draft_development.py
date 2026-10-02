"""Development opportunity must not depend solely on a position's OVR scale."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import draft_class as DC
import newgens as NG
from league import League, Player


def prospect(pid, pos, ovr):
    return SimpleNamespace(pid=pid, pos=pos, ovr=ovr)


def probabilities(rank, pos='TE'):
    class Capture:
        def choice(self, size, p):
            self.probabilities = p.copy()
            return 0
    rng = Capture()
    DC.draw_dev(rank, rng, pos=pos)
    return rng.probabilities


class DevelopmentRankTests(unittest.TestCase):
    def fixture(self):
        return [prospect(f'{pos}{i}', pos, top-i*.3)
                for pos, top in [('WR', 83), ('CB', 82), ('TE', 69), ('LG', 76)]
                for i in range(30)]

    def test_top_low_scale_position_has_access_to_all_tiers(self):
        men = self.fixture()
        ranks = DC.development_percentiles(men)
        old_rank = next(i for i, p in enumerate(sorted(men, key=lambda p: -p.ovr))
                        if p.pid == 'TE0') / (len(men)-1)
        self.assertEqual(probabilities(old_rank)[2:].tolist(), [0, 0])
        self.assertTrue(all(value > 0 for value in probabilities(ranks['TE0'])))
        self.assertLess(probabilities(ranks['TE0'])[3], .05)

    def test_position_tail_stays_unlikely_to_earn_elite_development(self):
        ranks = DC.development_percentiles(self.fixture())
        for pos in ('WR', 'CB', 'TE', 'LG'):
            self.assertLess(ranks[pos+'0'], ranks[pos+'10'])
            self.assertLess(ranks[pos+'10'], ranks[pos+'29'])
            np.testing.assert_array_equal(probabilities(ranks[pos+'29']), [.95, .05, 0, 0])

    def test_stronger_position_class_improves_its_odds(self):
        weak = self.fixture()
        strong = copy.deepcopy(weak)
        for p in strong:
            if p.pos == 'TE': p.ovr += 10
        w, s = DC.development_percentiles(weak), DC.development_percentiles(strong)
        self.assertLess(s['TE0'], w['TE0'])
        self.assertGreater(probabilities(s['TE0'])[3], probabilities(w['TE0'])[3])

    def test_equal_grades_and_input_order_do_not_change_odds(self):
        men = self.fixture()
        men[1].ovr = men[0].ovr
        a = DC.development_percentiles(men)
        self.assertEqual(a[men[0].pid], a[men[1].pid])
        self.assertEqual(a, DC.development_percentiles(list(reversed(men))))

    def test_specialists_keep_separate_policy(self):
        self.assertEqual(DC.development_percentiles([prospect('k', 'K', 99)]), {})
        for pos in ('K', 'P', 'LS'):
            self.assertEqual(probabilities(0, pos)[2:].tolist(), [0, 0])

    def test_empty_and_single_player_classes(self):
        self.assertEqual(DC.development_percentiles([]), {})
        self.assertEqual(DC.development_percentiles([prospect('te', 'TE', 70)]), {'te': 0})


class GenerationBoundaryTests(unittest.TestCase):
    def test_generation_and_reload_preserve_existing_players(self):
        L = League(2028)
        p = Player('existing', 'Existing Player', 'TE', 24,
                   {'catch_rating': 80}, dev='superstar', potential=89)
        L.players[p.pid] = p
        before = copy.deepcopy(vars(p)) if hasattr(p, '__dict__') else (p.dev, dict(p.ratings), p.potential)
        with patch.object(DC, 'COUNTS', {'TE': 5, 'WR': 5, 'K': 2}):
            NG.build(L, np.random.default_rng(43), 2029)
        self.assertEqual(NG.upgrade_saved_te_class(L), 0)
        after = copy.deepcopy(vars(p)) if hasattr(p, '__dict__') else (p.dev, dict(p.ratings), p.potential)
        self.assertEqual(before, after)
        saved_devs = {pid: p.dev for pid, p in L.players.items()}
        with patch.object(DC, 'shape_class', side_effect=AssertionError('no saved class reroll')), \
             patch.object(DC, 'draw_dev', side_effect=AssertionError('no saved player reroll')):
            loaded = League.load(L.save())
        self.assertEqual(saved_devs, {pid: p.dev for pid, p in loaded.players.items()})


if __name__ == '__main__':
    unittest.main()

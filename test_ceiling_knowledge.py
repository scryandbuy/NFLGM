import copy
import unittest
from unittest.mock import patch

import numpy as np
import ceiling_knowledge as CK
import player_age as PA
import targets as TG
import views_club as VC
import xp as XP
from league import League
from session import Session
from test_cap_accounting import fixture, player


class CeilingKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture()
        self.p = player(self.L)
        self.p.age = 22
        self.p.accrued = 0
        self.p.entry_year = 2026
        self.p.ratings = {k: 60. for k in TG.DEPTH_WEIGHTS['QB']}
        self.p.potential = 80.3
        self.p.potential_range = (70., 90.)
        self.p.xp = 1_000_000

    def bounds(self):
        return CK.visible_range(self.p, self.L)

    def test_completed_seasons_narrow_once_including_early_offseason(self):
        CK.sync(self.L)
        self.assertEqual(self.bounds(), (70, 90))
        self.L.season_closed_year = 2026
        CK.sync(self.L)
        self.assertEqual(self.bounds(), (71, 89))
        self.L.year = 2027
        CK.sync(self.L)
        self.assertEqual(self.bounds(), (71, 89))
        self.L.season_closed_year = 2027
        self.assertEqual(self.bounds(), (72, 88))

    def test_snaps_499_500_1000_and_postseason_without_duplicates(self):
        self.L.record_stats(2026, self.p.pid, dict(snaps=499))
        self.assertEqual(self.bounds(), (70, 90))
        self.L.record_stats(2026, self.p.pid, dict(snaps=1))
        self.assertEqual(self.bounds(), (71, 89))
        self.L.record_stats(2026, self.p.pid, dict(snaps=499), postseason=True)
        self.assertEqual(self.bounds(), (71, 89))
        self.L.record_stats(2026, self.p.pid, dict(snaps=1), postseason=True)
        self.assertEqual(self.bounds(), (72, 88))
        self.assertEqual(self.p.xp_spent[CK.KEY]['snaps'], 1000)

    def test_28_birthday_reveals_even_with_room_to_grow(self):
        self.p.birth_date = '1998-10-02'
        PA.set_date(self.L, '2026-10-01')
        self.assertTrue(CK.display(self.p)['ceiling_estimated'])
        PA.set_date(self.L, '2026-10-02')
        self.assertEqual(CK.display(self.p)['ceiling'], 80)
        self.assertEqual(CK.display(self.p)['ceiling_reason'], 'age')
        self.assertFalse(XP.at_ceiling(self.p))

    def test_reaching_cap_confirms_and_stays_known_after_regression_unlock(self):
        self.p.potential = TG.position_score(self.p.ratings, self.p.pos) + .3
        CK.sync(self.L)
        while not XP.at_ceiling(self.p):
            self.assertIsNotNone(XP.buy(self.p, 'awareness_rating'))
        self.assertTrue(self.p.xp_spent[CK.KEY]['known'])
        self.p.ratings['awareness_rating'] -= 5
        self.assertFalse(XP.at_ceiling(self.p))
        self.assertFalse(CK.display(self.p)['ceiling_estimated'])
        old = self.p.potential
        self.assertIsNotNone(XP.unlock(self.p))
        self.assertEqual(CK.display(self.p)['ceiling'], round(old + 1))
        self.assertFalse(CK.display(self.p)['ceiling_estimated'])

    def test_unlock_at_reached_cap_persists_confirmation_before_raising_it(self):
        self.p.potential = TG.position_score(self.p.ratings, self.p.pos)
        self.assertIsNotNone(XP.unlock(self.p))
        self.assertFalse(XP.at_ceiling(self.p))
        self.assertTrue(self.p.xp_spent[CK.KEY]['known'])

    def test_preemptive_unlock_shifts_estimate_without_confirming_it(self):
        before = self.bounds()
        XP.unlock(self.p)
        self.assertEqual(self.bounds(), tuple(v + 1 for v in before))
        self.assertFalse(self.p.xp_spent[CK.KEY]['known'])

    def test_truth_contained_and_minimum_width_preserved(self):
        for pot in (0., .2, 50., 73.1, 98.9, 99.):
            for original in ((0, 99), (72.8, 90.9), (99, 99), (0, 0)):
                with self.subTest(pot=pot, original=original):
                    self.p.potential = pot
                    self.p.potential_range = original
                    self.p.xp_spent = {}
                    with patch.object(XP, 'at_ceiling', return_value=False):
                        CK.sync(self.L)
                        previous = self.bounds()
                        for steps in range(0, 105):
                            self.p.xp_spent[CK.KEY]['snaps'] = steps * 500
                            lo, hi = self.bounds()
                            self.assertLessEqual(lo, pot)
                            self.assertGreaterEqual(hi, pot)
                            self.assertGreaterEqual(hi - lo, 2)
                            self.assertGreaterEqual(lo, previous[0])
                            self.assertLessEqual(hi, previous[1])
                            previous = lo, hi

    def test_legacy_migration_preserves_ability_xp_and_purchase_ledger(self):
        self.p.potential_range = None
        self.p.age = 25
        self.p.xp_spent = {'_purchases': [{'kind': 'buy', 'cost': 100}], '_unlocks': 2, 'awareness_rating': 1}
        original = copy.deepcopy(self.L.save())
        loaded = League.load(original)
        p = loaded.player(self.p.pid)
        self.assertEqual(original, self.L.save(), 'loading must not mutate input')
        self.assertEqual(p.ratings, self.p.ratings)
        self.assertEqual(p.potential, self.p.potential)
        self.assertEqual(p.xp, self.p.xp)
        for k, v in self.p.xp_spent.items():
            self.assertEqual(p.xp_spent[k], v)
        self.assertTrue(CK.display(p, loaded)['ceiling_estimated'])
        state = copy.deepcopy(p.xp_spent[CK.KEY])
        reloaded = League.load(loaded.save())
        self.assertEqual(reloaded.player(p.pid).xp_spent[CK.KEY], state)

    def test_legacy_acknowledged_ceiling_stays_known(self):
        self.p.xp_spent['_ceiling_notice_ack'] = 0
        CK.sync(self.L)
        self.assertTrue(self.p.xp_spent[CK.KEY]['known'])

    def test_planning_uses_confirmed_knowledge_but_leaves_prospects_alone(self):
        self.assertEqual(CK.observed_range(self.p), (70., 90.))
        self.p.potential = TG.position_score(self.p.ratings, self.p.pos)
        CK.sync(self.L)
        self.assertEqual(CK.observed_range(self.p), (60, 60))
        self.p.xp_spent = {}
        self.assertEqual(CK.observed_range(self.p), (70., 90.))

    def test_prospect_reports_untouched_until_professional(self):
        self.L.draft_pool = [self.p]
        self.p.team = None
        CK.sync(self.L)
        self.assertNotIn(CK.KEY, self.p.xp_spent)
        self.p.team = 'GB'
        CK.sync(self.L)
        self.assertIn(CK.KEY, self.p.xp_spent)

    def test_views_agree_are_pure_and_explain_position_learning(self):
        self.p.potential = TG.position_score(self.p.ratings, self.p.pos)
        self.p.transition = dict(frm='HB', to='QB', penalty=3., games_left=10, games_total=10)
        s = Session(self.L, np.random.default_rng(8), 'GB')
        before = copy.deepcopy(self.p.to_dict())
        rng = copy.deepcopy(s.rng.bit_generator.state)
        d = VC.development(s, self.L, 'GB', self.p.pid)
        with patch.object(VC, 'rail', return_value={}):
            row = VC.progression(s, self.L, 'GB')['rows'][0]
            card = VC.card(s, self.L, self.p.pid)
        self.assertEqual(d['ceiling'], row['ceiling'])
        self.assertEqual(d['ceiling'], card['ceiling'])
        roster = VC._row(s, self.L, self.L.teams['GB'], self.p)
        self.assertEqual(roster['pot'], d['ceiling'])
        self.assertIsNone(roster['pot_range'])
        self.assertTrue(d['at_ceiling'])
        self.assertGreater(d['development_ovr'], d['ovr'])
        self.assertGreater(d['learning_penalty'], 0)
        self.assertLess(max(r['gain'] for r in d['rows']), 1)
        self.assertEqual(self.p.to_dict(), before)
        self.assertEqual(s.rng.bit_generator.state, rng)


if __name__ == '__main__':
    unittest.main()

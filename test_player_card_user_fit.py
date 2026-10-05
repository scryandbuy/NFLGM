import unittest
from unittest.mock import patch
import numpy as np
import gm_engine as GE
import targets as TG
import views_club as VC
import views_personnel as VP
import views_frontoffice as VF
from views import user_player_grade
from session import Session
from test_cap_accounting import fixture, player


class PlayerCardUserFitTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture()
        self.p = player(self.L, team='MIN')
        self.p.ratings = {k: 75. for k in TG.DEPTH_WEIGHTS['QB']}
        self.p.ratings.update(throw_power_rating=98., throw_acc_deep_rating=98.,
                              throw_acc_short_rating=50., throw_acc_mid_rating=55.)
        self.s = Session(self.L, np.random.default_rng(9), 'GB')
        self.L.teams['GB'].scheme = ['quick_game']
        self.L.teams['MIN'].scheme = ['deep_game']
        self.addCleanup(patch.stopall)
        patch.object(VC, 'rail', return_value={}).start()
        patch.object(VP, 'rail', return_value={}).start()

    def assert_grade(self, row):
        expected = user_player_grade(self.L, self.p, 'GB')
        self.assertEqual((row['ovr'], row['fit']), (expected['ovr'], expected['fit']))

    def test_opponent_roster_and_depth_use_user_grade_without_changing_lineup(self):
        self.assert_grade(VC._row(self.s, self.L, self.L.teams['MIN'], self.p))
        for i, pos in enumerate(('HB', 'FB', 'WR', 'WR', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT')):
            q = player(self.L, pid=f'depth{i}', team='MIN')
            q.pos = pos
            q.ratings = {key: 70. for key in TG.DEPTH_WEIGHTS[pos]}
        before = {pos: [p.pid for p in men] for pos, men in self.L.teams['MIN'].depth.items()}
        view = VC.depth(self.s, self.L, 'MIN')
        slot = next(s for c in view['sides']['offense'] for s in c['slots'] if s['pid'] == self.p.pid)
        self.assert_grade(slot)
        self.assertTrue(slot['start'])
        self.assertEqual(before, {pos: [p.pid for p in men] for pos, men in self.L.teams['MIN'].depth.items()})
        self.assertEqual(self.L.teams['MIN'].scheme, ['deep_game'])

    def test_trade_grade_and_fit_note_use_user_team(self):
        self.assert_grade(VP._plate(self.L, self.p))
        text = VP._surplus_why(self.L, self.L.teams['MIN'], {'pid': self.p.pid})
        self.assertIn(f"Your fit {user_player_grade(self.L, self.p)['fit']:+.1f}", text)

    def test_market_and_waivers_match_card(self):
        import waivers as WV
        self.L.teams['MIN'].roster.remove(self.p); self.p.team = None
        self.L.free_agents.append(self.p.pid)
        market = VP.free_agency(self.s, self.L, 'GB')
        self.assert_grade(next(r for r in market['rows'] if r['pid'] == self.p.pid))
        entry = dict(pid=self.p.pid, from_team='MIN', claims=[])
        with patch.object(WV, 'pending', return_value=[entry]), patch.object(WV, 'priority', return_value=['GB', 'MIN']), patch.object(WV, 'reaches_user', return_value=True):
            view = VP.waivers(self.s, self.L, 'GB')
        self.assert_grade(view['rows'][0])

    def test_identity_uses_same_fit_formula_including_rigidity(self):
        from types import SimpleNamespace
        t = self.L.teams['GB']
        self.L.teams['MIN'].roster.remove(self.p); t.roster.append(self.p); self.p.team = 'GB'
        t.gm = SimpleNamespace(scheme_rigidity=0.9)
        with patch.object(GE, 'scheme_of', return_value=t.scheme):
            rows, men = VF._fit_table(self.L, t, t.gm)
        fit = next(f for p, f, group in men if p.pid == self.p.pid)
        self.assertEqual(round(fit, 1), user_player_grade(self.L, self.p)['fit'])

    def test_overall_uses_unrounded_fit(self):
        with patch.object(GE, 'scheme_fit', return_value=0.449):
            expected = round(self.p.ovr + 0.449)
            self.assertEqual(user_player_grade(self.L, self.p)['ovr'], expected)

    def test_trade_offer_popup_matches_trade_list(self):
        self.L.inbox = [dict(id=1, kind='trade_offer', status='open',
                            payload=dict(buyer='MIN', sends=[self.p.pid], gets=[]))]
        with patch.object(VP, '_evaluate', return_value={}):
            view = self.s.trade_offer_view(1)
        self.assert_grade(view['they'][0])

    def test_scheme_comparisons_are_user_hypotheticals_and_current_matches_card(self):
        import identity_catalog as IC
        key = next(k for k, v in IC.ARCHETYPES.items() if v.get('side') == 'offence')
        rows = VC.scheme_rows(self.p.ratings, self.p.pos, key, self.L.teams['GB'])
        own = next(r for r in rows if r['mine'])
        self.assertEqual(own['fit'], user_player_grade(self.L, self.p)['fit'])
        # Owner identity changes must not leak into any comparison.
        self.L.teams['MIN'].scheme = ['quick_game']
        self.assertEqual(rows, VC.scheme_rows(self.p.ratings, self.p.pos, key, self.L.teams['GB']))

    def test_opponent_card_uses_user_fit_and_adjusted_overall(self):
        expected = GE.scheme_fit(self.p.ratings, self.p.pos, self.L.teams['GB'])
        owner_fit = GE.scheme_fit(self.p.ratings, self.p.pos, self.L.teams['MIN'])
        self.assertLess(expected, 0)
        self.assertGreater(owner_fit, 0)
        card = VC.card(self.s, self.L, self.p.pid)
        self.assertEqual(card['fit'], round(expected, 1))
        self.assertEqual(card['ovr'], round(self.p.ovr + expected))
        self.assertEqual(card['grades'][0]['ovr'], card['ovr'])
        self.assertEqual(card['team']['abbr'], 'MIN')

    def test_owner_change_does_not_change_card_evaluation(self):
        before = VC.card(self.s, self.L, self.p.pid)
        self.L.teams['MIN'].roster.remove(self.p)
        self.L.teams['GB'].roster.append(self.p); self.p.team = 'GB'
        after = VC.card(self.s, self.L, self.p.pid)
        self.assertEqual((before['ovr'], before['fit']), (after['ovr'], after['fit']))

    def test_free_agent_uses_same_evaluation_and_user_scheme_change_updates_it(self):
        before = VC.card(self.s, self.L, self.p.pid)
        self.L.teams['MIN'].roster.remove(self.p); self.p.team = None
        self.L.free_agents.append(self.p.pid)
        free = VC.card(self.s, self.L, self.p.pid)
        self.assertEqual((before['ovr'], before['fit']), (free['ovr'], free['fit']))
        self.L.teams['GB'].scheme = ['deep_game']
        updated = VC.card(self.s, self.L, self.p.pid)
        self.assertGreater(updated['fit'], 0)
        self.assertGreater(updated['ovr'], free['ovr'])


if __name__ == '__main__': unittest.main()

"""Regression checks for draft decisions and data carried across seasons."""
import copy
import unittest
from unittest.mock import patch

import numpy as np

import draft_day
import extensions
import newgens
import scouting
import session
import trades
import views_draft
from cap_engine import Contract


class _FixedDraws:
    def __init__(self, value):
        self.value = value

    def normal(self, *_args):
        return self.value


class DraftIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = session.Session.new('KC', seed=91).save()

    def test_scouting_evidence_and_private_medical(self):
        s = session.Session.load(self.initial)
        self.assertEqual(sum(p.pos == 'LS' for p in s.L.next_class), 3)
        p = s.L.next_class[len(s.L.next_class) // 2]
        v = s.L.scouting['KC'][p.pid]
        plus, minus = copy.deepcopy(v), copy.deepcopy(v)
        scouting.second_look(plus, p, 4.0, _FixedDraws(12.0))
        scouting.second_look(minus, p, 4.0, _FixedDraws(-12.0))
        self.assertGreater(plus['ovr'], minus['ovr'])
        self.assertGreater(plus['pot_hi'], minus['pot_hi'])
        old_medical, old_flags = p.medical, list(v['flags'])
        try:
            p.medical = {'flag': 'knee'}
            v['flags'] = [x for x in v['flags'] if x != 'medical' and x != 'visited']
            self.assertNotIn('Medical', views_draft._prospect(s.L, 'KC', p)['words'])
            self.assertEqual(views_draft.prospect_card(s, s.L, 'KC', p.pid)['medical'], 'Unknown until visit')
        finally:
            p.medical, v['flags'] = old_medical, old_flags

    def test_new_class_and_rejected_clock_trade(self):
        s = session.Session.load(self.initial)
        L = s.L
        newgens.build(L, np.random.default_rng(34), draft_year=2028)
        self.assertEqual(sum(p.pos == 'LS' for p in L.next_class), 3)
        L.draft_pool = L.next_class
        pk = next(pk for pk in L.teams['KC'].picks if pk.year == 2026)
        pk.selection = 100
        D = draft_day.Draft(L, s.rng, 2026, user_team='KC')
        buyer_picks = [x for x in L.teams['DEN'].picks if x.year == 2026][:3]
        for i, buyer_pick in enumerate(buyer_picks, 2):
            buyer_pick.selection = i
        assets = [trades.pick_asset(L, x) for x in buyer_picks]
        def price(item, _ctx, _space, _gm, owns=False):
            if item['obj'] is pk:
                return 50.0 if owns else 100.0
            return 10.0 if owns else 20.0
        with patch.object(D, '_bank', return_value=assets), patch('trade_engine.team_price', side_effect=price), patch('trade_engine.evaluate', return_value=dict(accepted=False, a_gain=3, b_gain=3)) as evaluate:
            offer, result = D._offer_for('DEN', 'KC', pk, 1.0)
        self.assertTrue(evaluate.called)
        self.assertIsNone(offer)
        self.assertIsNone(result)
        with patch.object(D, '_bank', return_value=assets), patch('trade_engine.team_price', side_effect=price), patch('trade_engine.evaluate', return_value=dict(accepted=True, a_gain=3, b_gain=3)):
            offer, result = D._offer_for('DEN', 'KC', pk, 1.0)
        self.assertEqual(len(offer['a_sends']), 3)
        self.assertTrue(result['accepted'])

    def test_auto_board_live_save_and_historical_exports(self):
        s = session.Session.load(self.initial)
        L = s.L
        L.year = 2027
        L.phase = 'offseason'
        L.season_closed_year = 2026
        L.draft_pool, L.next_class = L.next_class, []
        picks = [pk for pk in L.teams['KC'].picks if pk.year == 2026][:2]
        self.assertEqual(len(picks), 2)
        for i, pk in enumerate(picks, 1):
            pk.selection = i
        D = draft_day.Draft(L, s.rng, 2026, user_team='KC', auto_pick=True)
        s.draft = D
        first, second = L.draft_pool[:2]
        L.user_board = dict(order=[first.pid, second.pid], dnd=[first.pid])
        self.assertEqual(D.user_pick().pid, second.pid)
        D.sim_pick()
        self.assertEqual(D.results[0][2].pid, second.pid)
        s._draft_offers = [dict(asks=[picks[0]], team='DEN', sends=[], summary=[])]
        self.assertFalse(views_draft.act_accept_offer(s, L, 'KC', 0)['ok'])
        with self.assertRaises(ValueError):
            L.trade('KC', 'DEN', [picks[0]], [])
        txt = views_draft.draft_text(s, L, 'KC')['text']
        csv = views_draft.draft_csv(s, L, 'KC')['text']
        self.assertIn(second.name, txt)
        self.assertIn(second.name, csv)
        D.trades.append((1, 'KC', 'DEN', ['a future pick']))
        D.dealt.add(frozenset(('KC', 'DEN')))
        D.last_dealt = 'DEN'
        resumed = session.Session.load(s.save())
        self.assertEqual(len(resumed.draft.trades), 1)
        self.assertEqual(resumed.draft.last_dealt, 'DEN')
        self.assertEqual(len(resumed.draft.dealt), 1)
        p = resumed.draft.user_pick()
        resumed.draft.make_pick(p.pid)
        resumed._draft_over()
        old_read = resumed.L.last_draft['scouting'][second.pid]['user_ovr']
        resumed.step_camp()
        self.assertEqual(resumed.L.last_draft['scouting'][second.pid]['user_ovr'], old_read)
        self.assertIn(second.name, views_draft.draft_text(resumed, resumed.L, 'KC')['text'])
        self.assertIn(str(round(old_read)), views_draft.draft_csv(resumed, resumed.L, 'KC')['text'])

    def test_pick_calendar_and_fifth_year_option(self):
        s = session.Session.load(self.initial)
        L = s.L
        L.year = 2027
        L.phase = 'offseason'
        L.season_closed_year = 2026
        future = next(pk for pk in L.teams['KC'].picks if pk.year == 2027)
        self.assertEqual(trades.pick_asset(L, future)['years_out'], 1)
        L.last_draft = {'year': 2026}
        self.assertEqual(trades.pick_asset(L, future)['years_out'], 0)
        p = L.teams['KC'].active()[0]
        p.draft_round = 1
        p.draft_year = 2024
        p.contract = Contract(1, [2.0])
        L.teams['KC'].sync_cap()
        price = extensions.rookie_option_price(L, p)
        self.assertIsNotNone(price)
        result = extensions.exercise_rookie_option(L, p.pid)
        self.assertTrue(result['ok'])
        self.assertEqual(p.contract.years, 2)
        self.assertEqual(p.contract.base[-1], price)
        self.assertIsNone(extensions.rookie_option_price(L, p))


if __name__ == '__main__':
    unittest.main()

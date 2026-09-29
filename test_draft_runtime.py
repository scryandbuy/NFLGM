"""Live draft persistence and post-payment trade-target regression checks."""
import json
import unittest
from unittest.mock import patch

import draft as DFT
import draft_day
import session
import trades


class DraftRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = session.Session.new('GB', seed=91)
        L = s.L
        L.year = 2027
        L.phase = 'offseason'
        L.season_closed_year = 2026
        s.stop = ('offseason', 11)
        L.draft_pool, L.next_class = L.next_class, []
        order = sorted(L.teams)
        for t in L.teams.values():
            for pk in t.picks:
                if pk.year == 2026:
                    pk.selection = (pk.round - 1) * 32 + order.index(pk.original) + 1
        s.draft = draft_day.Draft(L, s.rng, 2026, user_team='GB', auto_pick=True)
        cls.initial = s.save()

    def fresh(self):
        return session.Session.load(self.initial)

    def test_potential_and_benchmarks_survive_cpu_user_picks_and_resume(self):
        s = self.fresh()
        D = s.draft
        original = {p.pid: p.potential for p in D.available()}
        start_level, start_scale = dict(D.level), dict(D.scale)
        with patch.object(D, '_maybe_trade', return_value=None):
            for _ in range(13):  # includes Green Bay's user-auto selection
                D.sim_pick()
        self.assertTrue(all(p.potential is not None for _, _, p in D.results))
        self.assertEqual({p.pid: p.potential for _, _, p in D.results},
                         {p.pid: original[p.pid] for _, _, p in D.results})
        with patch.object(DFT, 'league_starter_level', side_effect=AssertionError('must use saved level')), \
             patch.object(DFT, 'position_scale', side_effect=AssertionError('must use saved scale')):
            resumed = session.Session.load(s.save())
        self.assertEqual(resumed.draft.level, start_level)
        self.assertEqual(resumed.draft.scale, start_scale)
        self.assertEqual(resumed.rng.bit_generator.state, s.rng.bit_generator.state)
        for _, _, p in resumed.draft.results:
            self.assertEqual(p.potential, original[p.pid])
        for abbr in ('GB', 'KC', 'DEN', 'ATL'):
            a = [(score, p.pid) for score, p in D.board_for(abbr)]
            b = [(score, p.pid) for score, p in resumed.draft.board_for(abbr)]
            self.assertEqual(a, b, abbr)
        with patch.object(D, '_maybe_trade', return_value=None), \
             patch.object(resumed.draft, '_maybe_trade', return_value=None):
            for _ in range(6):
                D.sim_pick()
                resumed.draft.sim_pick()
        self.assertEqual([(sel, t, p.pid, p.potential) for sel, t, p in D.results],
                         [(sel, t, p.pid, p.potential) for sel, t, p in resumed.draft.results])
        self.assertEqual(resumed.rng.bit_generator.state, s.rng.bit_generator.state)

    def test_legacy_draft_save_gets_one_fallback_snapshot(self):
        data = json.loads(self.initial)
        for key in ('level', 'scale', 'trade_targets'):
            data['_draft_live'].pop(key, None)
        resumed = session.Session.load(json.dumps(data))
        self.assertTrue(resumed.draft.level)
        self.assertTrue(resumed.draft.scale)
        next_save = json.loads(resumed.save())['_draft_live']
        self.assertEqual(next_save['level'], resumed.draft.level)
        self.assertEqual(resumed.draft.trade_targets, {})

    def test_package_assessment_includes_ir_and_rejects_collateral_that_changes_target(self):
        s = self.fresh()
        D, L = s.draft, s.L
        buyer = L.teams['DEN']
        incumbent = buyer.roster[0]
        buyer.ir.append(incumbent)
        target, replacement = D.available()[:2]
        pk = D.current()
        original_roster = [p.pid for p in buyer.roster]
        observed = []
        def board(*args, players=None, **kwargs):
            observed.append({p.pid for p in players})
            return [(100, target if incumbent.pid in observed[-1] else replacement)]
        with patch.object(DFT, 'board', side_effect=board):
            self.assertTrue(D._trade_target_valid('DEN', {'a_sends': []}, pk, target))
            self.assertFalse(D._trade_target_valid('DEN', {'a_sends': [{'kind':'player','pid':incumbent.pid}]}, pk, target))
        self.assertIn(incumbent.pid, observed[0])
        self.assertNotIn(incumbent.pid, observed[1])
        self.assertEqual([p.pid for p in buyer.roster], original_roster)

    def test_offer_search_skips_bad_player_collateral_but_keeps_viable_pick_package(self):
        s = self.fresh()
        D, L = s.draft, s.L
        pk = D.current()
        target, alternative = D.available()[:2]
        incumbent = L.teams['DEN'].roster[0]
        player_asset = {'kind':'player','pid':incumbent.pid}
        pick = next(p for p in L.teams['DEN'].picks if p.year == D.year)
        pick_asset = trades.pick_asset(L, pick)
        def price(item, *args, owns=False, **kwargs):
            if item.get('obj') is pk:
                return 50.0 if owns else 100.0
            return 60.0 if item['kind'] == 'player' else 80.0
        def board(*args, players=None, **kwargs):
            return [(100, target if incumbent.pid in {p.pid for p in players} else alternative)]
        with patch.object(D, '_bank', return_value=[player_asset, pick_asset]), \
             patch.object(DFT, 'board', side_effect=board), \
             patch('trade_engine.pick_price_dollars', return_value=50), \
             patch('trade_engine.team_price', side_effect=price), \
             patch('trade_engine.evaluate', return_value={'accepted':True,'a_gain':5,'b_gain':5}):
            offer, result = D._offer_for('DEN', pk.owner, pk, 1.0, target_player=target)
        self.assertTrue(result['accepted'])
        self.assertEqual(offer['a_sends'], [pick_asset])

    def test_executed_target_is_drafted_and_saved_between_trade_and_pick(self):
        s = self.fresh()
        D, L = s.draft, s.L
        pk = D.current()
        seller = pk.owner
        target, other = D.available()[:2]
        outgoing = next(p for p in L.teams['DEN'].picks if p.year == D.year)
        asset = trades.pick_asset(L, outgoing)
        offer = dict(a_sends=[asset], a_gets=[D._pick_asset(pk)])
        with patch.object(DFT, 'board', return_value=[(100, target)]):
            ev = D._execute('DEN', seller, offer, pk, target)
        self.assertIsNotNone(ev)
        self.assertEqual(pk.owner, 'DEN')
        resumed = session.Session.load(s.save())
        self.assertEqual(resumed.draft.trade_targets[pk.selection]['pid'], target.pid)
        for draft in (D, resumed.draft):
            with patch.object(draft, '_maybe_trade', return_value=None), \
                 patch.object(draft, 'board_for', return_value=[(100, other)]):
                draft.sim_pick()
            self.assertEqual(draft.results[-1][2].pid, target.pid)
            self.assertNotIn(pk.selection, draft.trade_targets)
        self.assertEqual(resumed.draft.results[-1][2].potential, target.potential)

    def test_execute_rechecks_target_before_mutating_rosters(self):
        s = self.fresh()
        D, L = s.draft, s.L
        pk = D.current()
        target, changed = D.available()[:2]
        outgoing = next(p for p in L.teams['DEN'].picks if p.year == D.year)
        offer = {'a_sends':[trades.pick_asset(L,outgoing)], 'a_gets':[D._pick_asset(pk)]}
        before = pk.owner
        with patch.object(DFT, 'board', return_value=[(100, changed)]), patch.object(L, 'trade') as trade:
            self.assertIsNone(D._execute('DEN', before, offer, pk, target))
        trade.assert_not_called()
        self.assertEqual(pk.owner, before)
        self.assertFalse(D.trade_targets)

    def test_trade_down_offer_revalidates_and_preserves_its_target(self):
        s = self.fresh()
        D, L = s.draft, s.L
        pk = D.current()
        D.user = pk.owner
        target, other = D.available()[:2]
        outgoing = next(p for p in L.teams['DEN'].picks if p.year == D.year)
        offer = dict(team='DEN', asks=[pk], sends=[trades.pick_asset(L, outgoing)], target_pid=target.pid)
        with patch('trade_engine.evaluate', return_value={'accepted':True}), \
             patch.object(DFT, 'board', return_value=[(100, other)]):
            self.assertIsNone(D.accept_offer(offer))
        self.assertEqual(pk.owner, D.user)
        with patch('trade_engine.evaluate', return_value={'accepted':True}), \
             patch.object(DFT, 'board', return_value=[(100, target)]):
            self.assertIsNotNone(D.accept_offer(offer))
        self.assertEqual(D.trade_targets[pk.selection], {'buyer':'DEN','pid':target.pid})
        with patch.object(D, '_maybe_trade', return_value=None):
            D.sim_pick()
        self.assertEqual(D.results[-1][2].pid, target.pid)

    def test_real_trade_target_check_uses_complete_proposed_roster(self):
        import draft_plan
        s = self.fresh()
        D, L = s.draft, s.L
        buyer = L.teams['DEN']
        outgoing = buyer.roster[0]
        players = [p for p in draft_plan.projected_players(buyer) if p.pid != outgoing.pid]
        rows = DFT.board(L, 'DEN', D.current().selection, D.level, D.taken, D.scale, players=players)
        offer = {'a_sends':[{'kind':'player','pid':outgoing.pid}]}
        self.assertTrue(D._trade_target_valid('DEN', offer, D.current(), rows[0][1]))
        self.assertFalse(D._trade_target_valid('DEN', offer, D.current(), rows[-1][1]))


if __name__ == '__main__':
    unittest.main()

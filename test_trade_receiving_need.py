"""A wanted upgrade is not automatically a hole in the receiving roster."""
import copy
import random
import unittest
from unittest.mock import patch

from cap_engine import Contract
from test_draft_planning import fixture, set_grade
import trades as TR
import trade_engine as TE
import roster_needs as RN


class ReceivingNeedTests(unittest.TestCase):
    def setUp(self):
        self.L, self.t = fixture()
        self.t.gm.off_personnel = '11'

    def incoming(self, pos='HB', grade=94):
        player = copy.deepcopy(self.t.by_pos(pos)[0])
        player.pid = 'incoming-' + pos
        player.team = 'DEN'
        player.contract = Contract(3, [8.] * 3)
        set_grade(player, grade)
        return player

    def test_real_star_upgrade_over_covered_position_remains_eligible(self):
        player = self.incoming()
        asset = dict(pid=player.pid, obj=player, seen_ovr=94)
        ranked = TR.package_trade_targets(self.t, [asset])
        self.assertEqual([p['pid'] for p in ranked], [player.pid])
        self.assertGreater(ranked[0]['package_gain'], TR.UPGRADE_GAP)
        self.assertFalse(TR.receiving_need(self.t, player))

    def test_weak_starter_and_missing_backup_are_real_needs(self):
        player = self.incoming()
        for q in self.t.by_pos('HB'):
            set_grade(q, 60)
        self.assertTrue(TR.receiving_need(self.t, player))
        self.t.roster = [q for q in self.t.roster if q.pos != 'QB' or q.pid == 'QB0']
        set_grade(self.t.by_pos('QB')[0], 95)
        player = self.incoming('QB', 75)
        self.assertTrue(TR.receiving_need(self.t, player))

    def test_short_absence_keeps_returnee_but_extended_loss_creates_need(self):
        player = self.incoming('QB', 87)
        for q in self.t.by_pos('QB'):
            set_grade(q, 55)
        starter = self.t.by_pos('QB')[0]
        set_grade(starter, 93)
        starter.out_until = 10
        self.assertFalse(TR.receiving_need(self.t, player, 9))
        starter.out_until = 16
        self.assertTrue(TR.receiving_need(self.t, player, 9))

    def test_unrelated_weak_tackle_does_not_make_halfback_a_need(self):
        for q in self.t.by_pos('LT'):
            set_grade(q, 50)
        self.assertIn('LT', TR.roster_need_labels(self.t))
        self.assertFalse(TR.receiving_need(self.t, self.incoming()))
        self.assertTrue(TR.receiving_need(self.t, self.incoming('LT')))

    def test_compatible_edge_and_receiving_package_jobs_count(self):
        for pos in ('LEDG', 'REDG'):
            for q in self.t.by_pos(pos):
                set_grade(q, 55)
        self.assertTrue(TR.receiving_need(self.t, self.incoming('REDG')))
        for i, q in enumerate(self.t.by_pos('WR')):
            set_grade(q, 95 if i == 0 else 55)
        self.assertTrue(TR.receiving_need(self.t, self.incoming('WR')))

    def test_arrival_removes_premium_for_next_same_position_purchase(self):
        for q in self.t.by_pos('HB'):
            set_grade(q, 55)
        first = self.incoming(grade=84)
        later = self.incoming(grade=96)
        later.pid = 'later-star'
        self.assertTrue(TR.receiving_need(self.t, first))
        self.t.roster.append(first)
        self.assertFalse(TR.receiving_need(self.t, later))
        self.assertGreater(RN.move_gain(self.t, later), TR.UPGRADE_GAP)

    def test_quote_uses_same_need_as_selected_target_and_no_hidden_potential(self):
        player = self.incoming()
        seller = copy.copy(self.t)
        seller.abbr = 'DEN'
        with patch.object(TR.VAL, 'value_player', return_value={'apy': 20.}), \
                patch.object(TR, '_street_alternative', return_value=None):
            quote = TR.player_asset(self.L, seller, player, None, None, viewer=self.t)
            self.assertEqual(quote['need'], TR.receiving_need(self.t, player))
            self.assertFalse(quote['need'])
            player.potential = 99
            self.assertFalse(TR.receiving_need(self.t, player))
            for q in self.t.by_pos('HB'):
                set_grade(q, 55)
            quote = TR.player_asset(self.L, seller, player, None, None, viewer=self.t)
            self.assertTrue(quote['need'])

    def test_same_price_can_favor_hole_over_upgrade_and_gms_still_disagree(self):
        ctx = dict(win_pct=.7, avg_age=26.)
        asset = dict(kind='player', age=28, apy=8., inherit=8.,
                     trade_value=20., trade_value_buyer=20., need=False)
        gm = TE.GM_ARCHETYPES['balanced']
        luxury = TE.team_price(asset, ctx, 60., gm)
        needed = TE.team_price(dict(asset, need=True), ctx, 60., gm)
        paid = (luxury + needed) / 2
        self.assertLess(luxury - paid, 0)
        self.assertGreater(needed - paid, 0)
        self.assertGreater(luxury - 10., .5)  # A worthwhile star deal still clears.
        patient = TE.team_price(asset, ctx, 60., TE.GM_ARCHETYPES['hoarder'])
        urgent = TE.team_price(asset, ctx, 60., TE.GM_ARCHETYPES['gunslinger'])
        self.assertGreater(urgent, patient)

    def test_surplus_currency_prices_receiving_clubs_need_without_stale_flag(self):
        seller = copy.deepcopy(self.t)
        seller.abbr = 'DEN'
        seller.league = self.L
        for q in seller.roster:
            q.pid = 'seller-' + q.pid
            q.team = 'DEN'
            if q.pos == 'WR': set_grade(q, 55)
            self.L.players[q.pid] = q
        self.L.teams['DEN'] = seller
        target = self.incoming()
        seller.roster.append(target)
        self.L.players[target.pid] = target
        spare = self.t.by_pos('WR')[-1]
        def asset(p, value, buyer=None):
            return dict(kind='player', pid=p.pid, obj=p, trade_value=value,
                        trade_value_buyer=value if buyer is None else buyer,
                        age=p.age, apy=p.apy, inherit=0., need=False)
        currency = asset(spare, 5.)
        arrival = asset(target, 5., 20.)
        arrival['package_gain'] = RN.move_gain(self.t, target)
        seen=[]
        real_price=TE.team_price
        def price(a, *args, **kw):
            if a.get('pid') == spare.pid: seen.append(a['need'])
            return real_price(a, *args, **kw)
        with patch.object(TR,'_picks_by_price',return_value=[]), \
                patch.object(TE,'team_price',side_effect=price), \
                patch.object(TR,'_financial_trade',return_value=True):
            TR._negotiate(self.L,self.t,seller,arrival,
                TR.persona(self.t.gm),TR.persona(seller.gm),
                TR.context(self.t),TR.context(seller),100.,100.,[currency],random.Random(4))
        self.assertTrue(seen)
        self.assertTrue(all(seen))
        self.assertFalse(currency['need'])  # Never alter the seller's shared list.
        with patch.object(TR.VAL,'value_player',return_value={'apy':20.}), \
                patch.object(TR,'_street_alternative',return_value=None):
            direct=TR.player_asset(self.L,self.t,spare,None,None,viewer=seller)
        self.assertTrue(direct['need'])
        for q in seller.by_pos('WR'): set_grade(q, 90)
        self.assertFalse(TR.receiving_need(seller, spare))


if __name__ == '__main__':
    unittest.main()

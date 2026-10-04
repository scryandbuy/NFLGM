import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import trades as TR
import trade_engine as TE

class SellerWillingnessTests(unittest.TestCase):
    def player(self, pid, pos='SS', ovr=89):
        return NS(pid=pid,pos=pos,ovr=ovr,out_until=None)
    def test_core_and_bench_classification(self):
        for pos in ('SS','REDG','QB'):
            p=self.player('core',pos); backup=self.player('backup',pos,72)
            team=NS(depth={pos:[p,backup]})
            with patch.object(TR,'context',return_value={}), patch.object(TE,'window',return_value='contending'), patch('morale.wants_out',return_value=False):
                self.assertEqual(TR.seller_willingness(team,p)['seller_ask'],1.12)
                self.assertEqual(TR.seller_willingness(team,backup)['seller_ask'],1)
            with patch.object(TR,'context',return_value={}), patch.object(TE,'window',return_value='rebuilding'), patch('morale.wants_out',return_value=False):
                self.assertEqual(TR.seller_willingness(team,p)['seller_ask'],1)
    def test_request_removes_willingness(self):
        with patch('morale.wants_out',return_value=True):
            self.assertEqual(TR.seller_willingness(NS(),self.player('a'))['seller_ask'],1)
    def price(self,owner,star=False):
        a=dict(kind='player',trade_value=100,age=25,need=False,apy=1,seller_ask=1.12,star=star,ask=1.6)
        with patch.object(TE,'situational_shift',return_value=dict(own_bias=owner,target_bias=1)):
            return TE.team_price(a,dict(win_pct=.7,avg_age=27),100,gm={'x':1},owns=True)
    def test_routes_equal_without_stacked_markup(self):
        self.assertAlmostEqual(self.price(1.08),112)
        self.assertEqual(self.price(1.08),self.price(1.08,True))
        self.assertAlmostEqual(self.price(1.2),120)
    def test_discount_is_preserved(self):
        self.assertAlmostEqual(self.price(.9),90)
    def test_unsigned_players_remain_ineligible(self):
        p=NS(contract=None)
        self.assertIsNone(TR.player_asset(None,None,p,None,None))

if __name__=='__main__': unittest.main()

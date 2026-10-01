import unittest
from unittest.mock import patch
import inbox, trade_engine, trades
from test_trade_offer_lifecycle import TradeOfferLifecycleTests
class ExpiredTradeTests(TradeOfferLifecycleTests):
 def test_expired_offer(self):
  self.player.contract=None; self.player.accrued=4
  before=[p for p in self.L.teams['DEN'].picks]
  with self.assertRaises(ValueError): inbox.accept(self.L,self.m['id'],'GB')
  self.assertEqual(self.m['status'],'done')
  self.assertEqual(self.player.fa_class,'UFA')
  self.assertEqual(before,self.L.teams['DEN'].picks)
  self.assertEqual(self.player.team,'GB')
 def test_unsigned_rfa_not_tradeable(self):
  self.player.contract=None; self.player.accrued=3
  self.assertIsNone(trades.player_asset(self.L,self.L.teams['GB'],self.player,None,None))
  with self.assertRaises(ValueError):self.L.trade('DEN','GB',[self.pick],[self.player.pid])
 def test_unsigned_tender_not_tradeable(self):
  self.player.fa_class='tendered'
  self.assertIsNone(trades.player_asset(self.L,self.L.teams['GB'],self.player,None,None))
  with self.assertRaises(ValueError):self.L.trade('DEN','GB',[self.pick],[self.player.pid])
 def test_zero_control_no_value(self):
  self.assertEqual(trade_engine.trade_value(dict(contract_years_left=0,ovr=90,apy=0),dict(apy=20)),0)
 def test_dates(self):
  self.assertEqual(inbox.date_label(dict(year=2028,week=22,phase='offseason')),'Offseason 2028')
  self.assertIn('Wild Card',inbox.date_label(dict(year=2028,week=19,phase='playoffs')))
if __name__=='__main__':unittest.main()

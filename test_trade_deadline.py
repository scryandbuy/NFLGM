import unittest
from types import SimpleNamespace
import trade_calendar as C
from league import League
import inbox

class TradeDeadlineTests(unittest.TestCase):
    def test_calendar(self):
        for phase, week, expected in [('regular',9,True),('regular',10,False),('playoffs',9,False),('playoffs',0,False),('offseason',22,True),('draft',22,True),('camp',0,True)]:
            self.assertEqual(C.trading_open(SimpleNamespace(phase=phase,week=week)),expected)
    def test_transaction_blocks_before_touching_assets(self):
        with self.assertRaisesRegex(ValueError,'deadline'):
            League.trade(SimpleNamespace(phase='regular',week=10),'GB','DEN',[],[])
    def test_offer_cannot_survive_deadline_or_season(self):
        m=dict(year=2028,phase='regular',expires_week=10)
        for phase,week,year in [('regular',10,2028),('offseason',22,2028),('regular',1,2029)]:
            self.assertTrue(C.offer_expired(SimpleNamespace(phase=phase,week=week,year=year),m))
        self.assertFalse(C.offer_expired(SimpleNamespace(phase='regular',week=9,year=2028),m))
    def test_counter_cannot_resume_after_deadline(self):
        m=dict(id=1,kind='trade_offer',status='countered',year=2028,phase='regular',payload={})
        L=SimpleNamespace(phase='regular',week=10,year=2028,inbox=[m])
        with self.assertRaisesRegex(ValueError,'expired'): inbox.counter(L,1,'GB')
        self.assertEqual(m['status'],'expired')

if __name__ == '__main__': unittest.main()

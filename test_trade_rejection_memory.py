import unittest
from types import SimpleNamespace as NS
import trades as T

class RejectionMemory(unittest.TestCase):
    def test_exact_identity_order_direction_and_new_year(self):
        L=NS(year=2030)
        pick=NS(year=2031,round=2,original='PIT',selection=None)
        T.remember_trade_rejection(L,'GB','PIT',['p1',pick],['p2'])
        encoded=dict(pick=True,year=2031,round=2,original='PIT',selection=45)
        self.assertTrue(T.trade_was_rejected(L,'PIT','GB',['p2'],[encoded,'p1']))
        self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1'],['p2']))
        self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1',pick],['p3']))
        self.assertFalse(T.trade_was_rejected(L,'GB','MIN',['p1',pick],['p2']))
        L.year=2031
        self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1',pick],['p2']))

if __name__=='__main__': unittest.main()

import unittest
import trade_engine as E

class TradeValueBalance(unittest.TestCase):
    def value(self,pos='SS',years=4,ovr=90,age=28,apy=20,worth=20,dev=0):
        return E.trade_value(dict(age=age,apy=apy,ovr=ovr,contract_years_left=years,madden_position=pos,development_credit=dev),dict(apy=worth))

    def test_certainty_does_not_repeat_in_full_every_year(self):
        for pos in ('QB','SS','WR','HB','LEDG','K'):
            with self.subTest(pos=pos):
                one=self.value(pos,1)
                self.assertGreater(self.value(pos,4),one)
                self.assertLess(self.value(pos,4),2*one)

    def test_youth_discount_contract_and_development_still_matter(self):
        self.assertGreater(self.value(apy=5),self.value(apy=20))
        self.assertGreater(self.value(age=25),self.value(age=34))
        self.assertGreater(self.value(dev=1),self.value(dev=0))
        self.assertAlmostEqual(self.value(dev=1),self.value(dev=0)*1.2,delta=.02)
        self.assertLess(self.value(ovr=75,apy=35,worth=5),0)
        self.assertEqual(self.value(years=0),0)

    def test_premium_positions_and_specialists(self):
        self.assertGreater(self.value(pos='QB'),self.value(pos='SS'))
        self.assertGreater(self.value(pos='WR'),self.value(pos='HB'))
        self.assertLess(self.value(pos='K'),self.value(pos='SS')/2)

    def test_pick_price_does_not_collapse_with_gm_taste(self):
        asset=dict(kind='pick',pick=16,years_out=0,cap=400)
        market=E.pick_price_dollars(16,0,400)
        from unittest.mock import patch
        for lens in (0,.5,1):
            with patch.object(E,'situational_shift',return_value=dict(pick_lens=lens,aggression=1,own_bias=1,target_bias=1)),patch.object(E,'window',return_value='contending'):
                value=E.team_price(asset,{},100,{'present':True},owns=False)
            self.assertGreaterEqual(value,market*.85*.85-.01)

if __name__=='__main__': unittest.main()

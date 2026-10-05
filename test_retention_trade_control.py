"""A seller's retention ask prices the service actually available to trade."""
import copy
import unittest
from unittest.mock import patch

from cap_engine import Contract
from cap_accounting import transfer_contract
from test_draft_planning import fixture, set_grade
import extensions as EXT
import retention_plan as RP
import trades as TR


class RetentionTradeControlTests(unittest.TestCase):
    def setUp(self):
        self.L,self.t=fixture()
        self.L.set_phase('regular');self.L.week=9
        self.t.record=[2,6,0];self.t.cap.cap=500
        self.p=self.t.by_pos('WR')[0];set_grade(self.p,88);self.p.age=27
        self.p.contract=Contract(1,[6.]);self.t.sync_cap()
        for ctx in (patch.object(EXT,'terms',return_value=dict(ask=10.,offer=10.,years=1,discount=.07)),
                    patch.object(EXT,'_ai_refusal',return_value='His agent will not negotiate during the season'),
                    patch.object(RP.VAL,'value_player',return_value={'apy':28.})):
            ctx.start();self.addCleanup(ctx.stop)

    def read(self):
        self.t.sync_cap()
        before=self.L.save()
        row=RP.assess(self.L,self.t,self.p)
        self.assertEqual(self.L.save(),before)
        return row

    def test_half_season_rental_halves_floor_without_forcing_sale(self):
        # The one-team fixture has no meaningful division race. Supply the
        # competitive window explicitly, keeping contract/roster checks real.
        with patch.object(RP.TE,'window',return_value='rebuilding'):
            full=self.read()
            self.t.cap.paid_week=9;self.p.contract.earned_base=3
            half=self.read()
        self.assertGreater(half['trade_floor'],0)
        self.assertAlmostEqual(half['trade_floor'],full['trade_floor']/2,delta=.01)
        self.assertEqual(half['decision'],'shop')
        self.assertIn(self.p,self.t.roster)
        self.assertEqual(self.L.transactions,[])
        # A contender can refuse to shop the same rental despite failed talks.
        self.t.record=[7,1,0]
        held=self.read()
        self.assertEqual(held['decision'],'retain')
        self.assertEqual(held['trade_floor'],half['trade_floor'])

    def test_transfer_does_not_restore_full_year_floor(self):
        self.t.cap.paid_week=9;self.p.contract.earned_base=3
        before=self.read()['trade_floor']
        self.p.contract=transfer_contract(self.p.contract,9)
        self.assertEqual(self.read()['trade_floor'],before)

    def test_closed_season_has_no_transferable_service(self):
        self.L.set_phase('offseason');self.L.season_closed_year=self.L.year
        self.assertEqual(self.read()['trade_floor'],0)
        self.assertIsNone(TR.player_asset(self.L,self.t,self.p,None,None))

    def test_calendar_stub_and_contract_roll_preserve_actual_control(self):
        self.L.set_phase('offseason');self.L.season_closed_year=self.L.year
        for future_years in (1,2):
            with self.subTest(future_years=future_years):
                self.p.contract=Contract(future_years+1,[0]+[6.]*future_years,start_offset=1)
                asset=TR.player_asset(self.L,self.t,self.p,None,None)
                before=self.read()['trade_floor']
                if future_years==2:
                    # Three calendar years remain ineligible for AI renewal;
                    # pricing corrections must not bypass that policy.
                    self.assertEqual(before,0)
                    self.assertEqual(self.read()['reasons'],['not_eligible'])
                    continue
                self.assertEqual(before,round(max(0,asset['trade_value'])*(.5 if future_years==1 else .75),2))
                self.p.contract.advance();self.L.year+=1
                self.assertEqual(self.read()['trade_floor'],before)
                self.L.year-=1

    def test_remaining_cash_and_future_years_match_transfer_quote(self):
        self.t.cap.paid_week=9
        self.p.contract=Contract(2,[6.,20.],signing_bonus=9.,earned_base=3.)
        before=copy.deepcopy(vars(self.p.contract))
        asset=TR.player_asset(self.L,self.t,self.p,None,None)
        self.assertEqual(self.read()['trade_floor'],round(max(0,asset['trade_value'])*.75,2))
        self.assertEqual(vars(self.p.contract),before)
        self.p.contract.base[1]+=10
        self.assertLess(self.read()['trade_floor'],round(max(0,asset['trade_value'])*.75,2))


if __name__=='__main__':
    unittest.main()

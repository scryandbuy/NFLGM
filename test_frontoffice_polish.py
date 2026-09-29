"""Front Office display calendar and staff offer action regression checks."""
import copy
import unittest
from unittest.mock import patch
from test_cap_accounting import fixture, player
from cap_engine import Contract
from cap_accounting import next_year_ledger
import views_frontoffice as V

class FrontOfficePolishTests(unittest.TestCase):
    def view(self, league):
        with patch.object(V, 'rail', return_value={}):
            return V.cap(None, league, 'GB')

    def test_closed_season_shifts_display_once(self):
        league=fixture()
        p=player(league, contract=Contract(4,[10,20,30,40],signing_bonus=12))
        self.assertEqual([x['year'] for x in self.view(league)['years']],[2026,2027,2028])
        league.set_phase('offseason'); league.season_closed_year=2026
        before=copy.deepcopy(p.contract.__dict__)
        view=self.view(league)
        self.assertEqual([x['year'] for x in view['years']],[2027,2028,2029])
        self.assertEqual(view['rows'][0]['hits'],[23,33,43])
        self.assertEqual(view['rows'][0]['yrs'],3)
        self.assertFalse(view['years'][0]['current'])
        self.assertEqual(view['tag_year'],2027)
        self.assertEqual(p.contract.__dict__,before)
        self.assertEqual(league.year,2026)
        limit, committed, _, dead=next_year_ledger(league,league.teams['GB'])
        self.assertEqual(view['cap_space'],round(limit-committed,1))
        self.assertEqual(view['dead_total'],round(dead,1))
        league.roll_year(); league.advance_contracts()
        rolled=self.view(league)
        self.assertEqual([x['year'] for x in rolled['years']],[2027,2028,2029])
        self.assertTrue(rolled['years'][0]['current'])
        self.assertEqual(rolled['rows'][0]['hits'],view['rows'][0]['hits'])

    def test_camp_does_not_shift(self):
        league=fixture();league.set_phase('camp');league.season_closed_year=2025
        self.assertEqual(self.view(league)['years'][0]['year'],2026)

    def test_shifted_dead_and_void_charges(self):
        league=fixture();player(league,'cut',contract=Contract(3,[18]*3,signing_bonus=30))
        player(league,'void',contract=Contract(1,[1],signing_bonus=30,void_years=2))
        league.set_phase('offseason');league.season_closed_year=2026
        league.release('cut')
        view=self.view(league)
        self.assertEqual(view['dead_total'],40)
        self.assertEqual(view['dead_rows'][0]['dead'],20)
        self.assertEqual(view['dead_rows'][0]['dead_next'],0)
        self.assertEqual(view['rows'][0]['hits'],[None,None,None])
        self.assertEqual(view['rows'][0]['penalty'],20)

    def test_shifted_largest_and_restructure(self):
        league=fixture();player(league,'oldbig',contract=Contract(3,[80,5,5]))
        player(league,'newbig',contract=Contract(3,[5,40,40]))
        league.set_phase('offseason');league.season_closed_year=2026
        view=self.view(league)
        self.assertEqual(view['largest'][0]['pid'],'newbig')
        preview=V.act_restructure_preview(league,'GB','newbig',amount=10)
        self.assertTrue(preview['ok'])
        self.assertEqual(preview['cap_year'],2027)
        self.assertEqual(preview['player']['hit'],40)
        self.assertEqual(preview['player']['yrs'],2)

    def test_invalid_staff_terms_do_not_reach_engine(self):
        with patch('staff.extend') as extend, patch('staff.hire') as hire:
            for years in (0,6,1.5,float('inf'),'bad'):
                self.assertFalse(V.act_staff_extend(None,'GB','oc',years=years)['ok'])
                self.assertFalse(V.act_staff_hire(None,'GB','name',years=years)['ok'])
            for salary in (-1,float('nan'),float('inf')):
                self.assertFalse(V.act_staff_extend(None,'GB','oc',salary=salary)['ok'])
            extend.assert_not_called();hire.assert_not_called()

if __name__=='__main__':unittest.main()

import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
from test_cap_accounting import fixture, player
from cap_engine import Contract
import min_salary as MS
import extensions as E
import negotiations as NG
import contract_offer as CO

class MinimumDemands(unittest.TestCase):
    def test_low_extension_valuation_floored_high_value_preserved(self):
        L=fixture(); p=player(L,contract=Contract(2,[5,5])); L.teams['GB'].gm=N(restructure_depth=.5)
        for value in (.1,30):
            with patch.object(E.VAL,'value_player',return_value=dict(apy=value,years=3)), patch('personality.ask_mult',return_value=1), patch.object(E,'honors_premium',return_value=1):
                terms=E.terms(L,p,None,pool=[])
            self.assertEqual(terms['ask'],MS.demand_quote(L,p,value,3,'extension'))
            package=CO.canonical(L,p,L.teams['GB'],dict(apy=terms['ask'],years=3),'extension')
            built=E.build(p,3,package['apy'],301.2,L.teams['GB'].gm,L,bonus=package['bonus'],front_load=package['front_load'])
            self.assertEqual(built.base[:2],[5,5])
            for base,floor in zip(built.base[2:],MS.demand_minima(L,p,3,'extension')):
                self.assertGreaterEqual(base+1e-9,floor)

    def test_live_quotes_update_but_historical_offers_do_not(self):
        for kind in ('extension','fa_offseason','fa_inseason'):
            L=fixture();p=player(L,team='GB' if kind=='extension' else None)
            t=dict(id=1,pid=p.pid,team='GB',kind=kind,state='countered',ask=.1,years=1,
                   offers=[dict(apy=.1,years=1)],counter=dict(apy=.5,years=1,bonus=.2))
            L.negotiations=[t];NG._threads(L)
            self.assertGreaterEqual(t['ask'],MS.player_minimum(L,p))
            self.assertGreaterEqual(t['counter']['apy'],MS.player_minimum(L,p)+.2)
            self.assertEqual(t['offers'][0]['apy'],.1)
            before=dict(t['counter']);NG._threads(L);self.assertEqual(t['counter'],before)

    def test_floor_rounds_up_and_bonus_is_additional(self):
        L=fixture();p=player(L)
        for years in (1,3,7):
            q=MS.demand_quote(L,p,0,years,bonus=.5)
            self.assertGreaterEqual(q*years,sum(MS.demand_minima(L,p,years))+.5)
            self.assertEqual(MS.demand_quote(L,p,50,years),50)

if __name__=='__main__':unittest.main()

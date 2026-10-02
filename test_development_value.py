import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from development_value import development_credit as credit, player_credit
import trade_engine as TE
import roster_needs as RN


class DevelopmentValueTests(unittest.TestCase):
    def player(self, dev='normal', age=23, years=4):
        return NS(pid='p', dev=dev, age=age, ovr=80, accrued=0,
                  contract=NS(years=years), potential_range=(88, 92),
                  draft_round=4, pos='HB')

    def test_tiers_and_bounds(self):
        values=[credit(d,23,80,4,(88,92)) for d in ['normal','star','superstar','xfactor']]
        self.assertEqual(values,[0,.35,.65,1])
        self.assertEqual(credit('xfactor',18,60,10,(99,99)),1)

    def test_age_control_and_room(self):
        self.assertGreater(credit('star',23,80,4,(88,92)),credit('star',27,80,4,(88,92)))
        self.assertEqual(credit('xfactor',29,80,4,(88,92)),0)
        self.assertEqual(credit('xfactor',23,80,0,(88,92)),0)
        self.assertEqual(credit('xfactor',23,90,4,(80,90)),0)
        self.assertLess(credit('xfactor',23,80,1,(88,92)),credit('xfactor',23,80,4,(88,92)))

    def test_hidden_ceiling_does_not_matter(self):
        p=self.player('star');p.potential=81;a=player_credit(p)
        p.potential=99;self.assertEqual(a,player_credit(p))

    def test_trade_premium_bounded_and_bad_deal_unchanged(self):
        row=dict(age=23,ovr=84,apy=2,contract_years_left=4,madden_position='HB')
        normal=TE.trade_value(row,dict(apy=8))
        legend=TE.trade_value(dict(row,development_credit=1),dict(apy=8))
        self.assertGreater(legend,normal);self.assertAlmostEqual(legend,normal*1.15,delta=.02)
        bad=dict(row,apy=90)
        self.assertEqual(TE.trade_value(bad,dict(apy=8)),TE.trade_value(dict(bad,development_credit=1),dict(apy=8)))

    def test_retention_reacts_to_upgrade_without_changing_rating(self):
        p=self.player();team=NS(gm=NS(dev_belief=.5),active=lambda:[p])
        a=RN.retention_value(team,p);p.dev='xfactor';b=RN.retention_value(team,p)
        self.assertGreater(b,a);self.assertLessEqual(b-a,2);self.assertLessEqual(b,6)
        self.assertEqual(p.ovr,80)

    def test_live_trade_asset_reads_current_tier(self):
        import trades
        from cap_engine import Contract
        p=self.player();p.contract=Contract(4,[2]*4);p.contract_years_left=4;p.fa_class=None
        p.apy=2;p.team='GB';p.name='Prospect'
        team=NS(abbr='GB');league=NS(post_june1=lambda:True)
        with patch.object(trades.VAL,'value_player',return_value={'apy':8}):
            a=trades.player_asset(league,team,p,None,None)
            p.dev='xfactor'
            b=trades.player_asset(league,team,p,None,None)
        self.assertGreater(b['trade_value'],a['trade_value'])
        self.assertGreater(b['trade_value_buyer'],a['trade_value_buyer'])

    def test_elite_development_does_not_erase_crowded_room(self):
        from test_draft_planning import fixture
        from test_draft_redundancy import room
        import draft_plan as DP
        L,t=fixture()
        room(L,t,'HB',[(85,23,4),(84,24,4),(82,24,3),(80,23,3)])
        for p in t.roster:
            if p.pos=='HB': p.dev='xfactor';p.potential_range=(88,92)
        plan=DP.assess(L,'MIN');target=L.player('rookie-HB0')
        self.assertGreater(DP.redundancy_penalty(plan,target,grade=77,gain=0),0)


if __name__=='__main__': unittest.main()

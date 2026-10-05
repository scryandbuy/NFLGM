"""Final draft consent uses the current scouting preference in every guard."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import draft_day as DD
import draft_plan as DP
import trade_portfolio as TP
import trades as TR


class DraftTradeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.sent = NS(year=2029, round=2, original='MIN', owner='MIN', used_on=None)
        self.target = NS(year=2029, round=1, original='GB', owner='GB', used_on=None)
        def team(abbr, picks):
            return NS(abbr=abbr, picks=picks, gm=None, cap_space=100,
                      ctx=lambda: dict(win_pct=.5, avg_age=26, games_played=17))
        self.L = NS(year=2030, user_team='GB', teams={
            'MIN':team('MIN',[self.sent]), 'GB':team('GB',[self.target])})
        self.draft = DD.Draft.__new__(DD.Draft)
        self.draft.L, self.draft.user = self.L, 'GB'
        self.draft._pick_asset = lambda p: dict(kind='pick', obj=p)
        self.prospect = NS(pid='scouted-rookie')
        self.offer = dict(a_sends=[dict(kind='pick', obj=self.sent)],
                          a_gets=[dict(kind='pick', obj=self.target, draft_target_premium=1.4)])

    def review(self, premium):
        # Fixed economic quotes isolate the integration boundary: ordinary
        # willingness accepts all three raw margins; the actual portfolio
        # guard must use the freshly priced target before subtracting $4.
        margins = {1.1:2., 1.3:5., 1.4:6.}
        seen = []
        def evaluate(offer, *args, **kwargs):
            value = offer['a_gets'][0]['draft_target_premium']
            seen.append(value)
            return dict(a_gain=margins[value], b_gain=2., accepted=True, blocked=None)
        refreshed = dict(kind='pick', obj=self.target, draft_target_premium=premium)
        original = copy.deepcopy(self.offer)
        with patch.object(self.draft, '_target_asset', return_value=refreshed), \
             patch.object(DP, 'observed_prospect', return_value=self.prospect), \
             patch.object(TP, 'assess', return_value=dict(cost=4.)), \
             patch.object(TR.TE, 'evaluate', side_effect=evaluate), \
             patch.object(TR.TE, 'market_price', return_value=10.), \
             patch.object(TR, '_financial_trade', return_value=True) as funding:
            accepted = self.draft._package_valid('MIN','GB',self.offer,self.target,self.prospect)
        self.assertEqual(self.offer, original)
        return accepted, seen, funding

    def test_stale_high_premium_cannot_override_current_portfolio_restraint(self):
        accepted, seen, funding = self.review(1.1)
        self.assertFalse(accepted)  # Current +2 margin becomes -2 after options.
        self.assertEqual(seen, [1.1, 1.1])
        funding.assert_not_called()

    def test_strong_current_preference_still_reaches_funding_with_same_offer(self):
        accepted, seen, funding = self.review(1.3)
        self.assertTrue(accepted)  # Current +5 margin remains +1 after options.
        self.assertTrue(all(value == 1.3 for value in seen))
        funding.assert_called_once()
        self.assertEqual(funding.call_args.kwargs['offer']['a_gets'][0]['draft_target_premium'],1.3)
        self.assertIs(funding.call_args.kwargs['consumed_pick'],self.target)


if __name__ == '__main__':
    unittest.main()

"""The same earned scouting evidence must drive cards and draft decisions."""
import copy
import unittest
from unittest.mock import patch

import draft_plan as DP
import scouting as SC
import spring as SP
import views_draft as VD
from session import Session


class ScoutingConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.saved = Session.new('GB', seed=633).save()

    def fresh(self):
        return Session.load(self.saved)

    def test_card_attributes_and_trade_proxy_share_the_room_read(self):
        session = self.fresh()
        league = session.L
        p = league.next_class[0]
        view = league.scouting['GB'][p.pid]
        observed = SC.scouted_ratings(p, view)
        card = VD.prospect_card(session, league, 'GB', p.pid)
        self.assertNotIn('error', card)
        for column in card['cols']:
            for row in column['rows'] + (column.get('extra') or {}).get('rows', []):
                self.assertEqual(row['v'], round(observed[row['key']]))
        proxy = DP.observed_prospect(league, 'GB', p)
        self.assertEqual(proxy.ratings, observed)
        self.assertEqual(proxy.ovr, view['ovr'])
        self.assertIsNot(proxy, p)
        expected = 'Strong' if SC.certainty(view) >= .75 else 'Moderate' if SC.certainty(view) >= .5 else 'Limited'
        self.assertEqual(card['confidence'], expected)
        self.assertEqual(card['visit_status'], 'Not visited')

    def test_initial_exposure_is_not_a_perfect_hidden_overall_split(self):
        league = self.fresh().L
        pool = league.next_class
        true_deep = {p.pid for p in sorted(pool, key=lambda p: -p.ovr)[len(pool) // 2:]}
        exposed_deep = {p.pid for p in pool if
                        abs(league.scouting['GB'][p.pid]['cert0'] -
                            (SC.CERT_START_DEEP + (SC.CERT_SMALL_SCHOOL if not SC._power(p) else 0))) < 1e-9}
        self.assertEqual(len(exposed_deep), len(pool) // 2)
        self.assertNotEqual(exposed_deep, true_deep)

    def test_hidden_talent_change_with_same_scouted_read_keeps_trade_proxy(self):
        session = self.fresh()
        league = session.L
        p = league.next_class[0]
        before = DP.observed_prospect(league, 'GB', p)
        old = copy.deepcopy(p.ratings)
        try:
            p.ratings = {key: value - 5 for key, value in old.items()}
            for key in ('e_phys', 'e_skill'):
                league.scouting['GB'][p.pid][key] += 5
            after = DP.observed_prospect(league, 'GB', p)
            for key in before.ratings:
                self.assertAlmostEqual(before.ratings[key], after.ratings[key])
            self.assertEqual(before.ovr, after.ovr)
        finally:
            p.ratings = old

    def test_spring_character_visit_receives_raw_scout_error(self):
        session = self.fresh()
        league = session.L
        league.user_visits = [league.next_class[0].pid]
        team = league.teams['GB']
        expected = SC.error_sd(team.gm, team)
        seen = []
        with patch.object(SP, '_visit_targets', return_value=[]), \
             patch.object(SP.DP, 'assess', return_value={}), \
             patch.object(SP, '_character', side_effect=lambda *args: seen.append(args[4])), \
             patch.object(SP, '_medical'), \
             patch.object(SP, '_stock_moves', return_value=[]), \
             patch.object(SC, 'consensus'):
            SP.visits(league, session.rng)
        self.assertEqual(seen, [expected])


if __name__ == '__main__':
    unittest.main()

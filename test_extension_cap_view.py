"""Extensions page and talks share the actual next-year ledger in every phase."""
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
from cap_engine import Contract
from cap_accounting import next_year_ledger
from test_cap_accounting import fixture, player
import views_personnel as VP
import extensions as EXT
from league import League


class ExtensionCapViewTests(unittest.TestCase):
    def test_next_year_budget_in_page_and_popup_across_season_phases(self):
        for phase in ('regular', 'offseason', 'free_agency'):
            with self.subTest(phase=phase):
                league = fixture(); league.set_phase(phase)
                league.season_closed_year = league.year if phase == 'offseason' else None
                team = league.teams['GB']
                player(league, contract=Contract(4, [5, 20, 21, 22]))
                team.cap.dead_next = 7.125
                thread = dict(id=1, kind='extension', team='GB', state='open')
                with patch.object(VP, 'rail', return_value={}), \
                     patch('negotiations._threads', return_value=[thread]), \
                     patch.object(VP, '_thread', side_effect=lambda league, row: dict(row)):
                    data = VP.extensions(None, league, 'GB')
                limit, committed, rollover, dead = next_year_ledger(league, team)
                expected = dict(year=league.year+1, limit=round(limit, 1),
                                committed=round(committed, 1), space=round(limit-committed, 1))
                self.assertEqual(data['extension_cap'], expected)
                self.assertEqual(data['threads'][0]['extension_cap'], expected)
                now = dict(year=league.year, limit=round(team.cap.limit, 1),
                           committed=round(team.cap.charges(team.phase), 1), space=round(team.cap_space, 1))
                self.assertEqual(data['current_cap'], now)
                self.assertEqual(data['threads'][0]['current_cap'], now)
                self.assertGreater(rollover, 0)
                self.assertGreaterEqual(committed, 27.125)
                self.assertNotEqual(expected['space'], round(team.cap_space, 1))

    def test_preview_current_and_future_changes_match_signed_contract_and_reload(self):
        for phase in ('regular', 'offseason', 'free_agency'):
            with self.subTest(phase=phase):
                league = fixture(); league.set_phase(phase)
                league.season_closed_year = league.year if phase == 'offseason' else None
                team = league.teams['GB']; team.gm = N(restructure_depth=.5)
                p = player(league, contract=Contract(1, [10], signing_bonus=10))
                before = team.cap_space
                preview = VP.act_offer_preview(league, 'GB', p.pid, 40, 4, bonus=75, front_load=.5)
                self.assertTrue(preview['ok'])
                expected_change = 0 if phase == 'offseason' else 15
                self.assertEqual(preview['cap_impact'][0]['change'], expected_change)
                self.assertEqual(preview['cap_impact'][0]['existing'], 20)
                with patch.object(EXT, 'terms', return_value=dict(ask=40, discount=0, years=4)):
                    result = EXT.extend(league, p.pid, 40, 4, agreed=True, bonus=75, front_load=.5)
                self.assertEqual(result['result'], 'accepted')
                self.assertAlmostEqual(before-team.cap_space, expected_change)
                self.assertEqual([r['total'] for r in preview['cap_impact']],
                                 [round(p.contract.cap_hit(i),3) for i in range(p.contract.years)])
                team.gm = None  # The fixture's lightweight pricing stub is not a saved GM.
                loaded = League.load(league.save()); contract = loaded.player(p.pid).contract
                contract.advance()
                self.assertEqual(round(contract.cap_hit(0),3), preview['cap_impact'][1]['total'])

    def test_counter_and_submitted_offer_use_their_exact_terms(self):
        for state in ('countered', 'waiting'):
            with self.subTest(state=state):
                league = fixture(); league.set_phase('regular')
                team = league.teams['GB']; team.gm = N(restructure_depth=.5)
                p = player(league, contract=Contract(4, [5, 20, 21, 22]))
                offer = dict(apy=30, years=3, front_load=.5)
                if state == 'waiting': offer.update(bonus=27, front_load=.8)
                thread = dict(id=1, kind='extension', team='GB', pid=p.pid, state=state,
                              counter=offer if state == 'countered' else None, offers=[offer])
                with patch.object(VP, 'rail', return_value={}), \
                     patch('negotiations._threads', return_value=[thread]), \
                     patch.object(VP, '_thread', side_effect=lambda league, row: dict(row)):
                    data = VP.extensions(None, league, 'GB')
                expected = VP.act_offer_preview(league, 'GB', p.pid, offer['apy'], offer['years'],
                                                bonus=offer.get('bonus'), front_load=offer['front_load'])
                self.assertTrue(expected['ok'])
                self.assertEqual(data['threads'][0]['offer_cap_preview'], expected)

    def test_existing_void_charge_is_included_in_comparison(self):
        league = fixture(); team = league.teams['GB']; team.gm = N(restructure_depth=.5)
        p = player(league, contract=Contract(1, [10], signing_bonus=30, void_years=2))
        preview = VP.act_offer_preview(league, 'GB', p.pid, 15, 1, bonus=0, front_load=.5)
        self.assertEqual(preview['cap_impact'][1]['existing'], 20)
        self.assertEqual(preview['cap_impact'][1]['total'], 25)
        self.assertEqual(preview['cap_impact'][2], dict(year=2028, existing=0, change=10, total=10))


if __name__ == '__main__': unittest.main()

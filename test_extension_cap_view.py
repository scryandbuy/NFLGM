"""Extensions page and talks share the actual next-year ledger in every phase."""
import unittest
from unittest.mock import patch
from cap_engine import Contract
from cap_accounting import next_year_ledger
from test_cap_accounting import fixture, player
import views_personnel as VP


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
                self.assertGreater(rollover, 0)
                self.assertGreaterEqual(committed, 27.125)
                self.assertNotEqual(expected['space'], round(team.cap_space, 1))


if __name__ == '__main__': unittest.main()

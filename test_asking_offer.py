"""Player asking terms must open as a fundable contract, even near the minimum."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from cap_engine import Contract
from test_cap_accounting import fixture, player
from min_salary import demand_minima
import contract_offer as CO
import views_personnel as VP


def asking_cases():
    for phase in ('regular', 'offseason', 'free_agency'):
        for left in (None, 0, 1, 4):
            for years in (1, 2, 7):
                for ask in (3.53, 60):
                    league = fixture(); league.year = 2033; league.user_team = 'GB'
                    league.teams['GB'].gm = SimpleNamespace(restructure_depth=.5)
                    league.set_phase(phase)
                    league.season_closed_year = league.year if phase == 'offseason' else None
                    p = player(league, contract=None if left is None else Contract(left, [8] * left))
                    p.accrued = 10
                    kind = 'fa_offseason' if left is None else 'extension'
                    thread = dict(id=1, pid=p.pid, team='GB', kind=kind, state='open', ask=ask, years=years)
                    yield league, p, thread


class AskingOfferTests(unittest.TestCase):
    def test_asking_package_funds_minimums_and_previews(self):
        for league, p, thread in asking_cases():
            with self.subTest(phase=league.phase, left=getattr(p.contract, 'years', None), years=thread['years'], ask=thread['ask']):
                view = VP._thread(league, thread)
                offer = view['ask_offer']
                self.assertEqual(offer['apy'], view['ask'])
                self.assertEqual(CO.canonical(league, p, league.teams['GB'], offer, thread['kind']), offer)
                self.assertGreaterEqual(offer['apy'] * offer['years'] - offer['bonus'] + 1e-9,
                                        sum(demand_minima(league, p, offer['years'], thread['kind'])))
                with patch('negotiations.open_for', return_value=None):
                    preview = VP.act_offer_preview(league, 'GB', p.pid, offer['apy'], offer['years'],
                                                   bonus=offer['bonus'], front_load=offer['front_load'])
                self.assertTrue(preview['ok'], preview)
                if thread['ask'] == 60:
                    self.assertEqual(offer['apy'], 60)

    def test_manual_excess_bonus_still_rejected(self):
        league = fixture(); p = player(league)
        with self.assertRaises(ValueError):
            CO.canonical(league, p, league.teams['GB'], dict(apy=3.53, years=2, bonus=7), 'extension')


if __name__ == '__main__': unittest.main()

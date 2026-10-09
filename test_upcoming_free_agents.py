"""The next-market list follows actual contracts without making transactions."""
import copy
import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

from cap_engine import Contract
from cap_accounting import next_year_ledger
from league import League
from test_cap_accounting import fixture, player
import views_personnel as VP


def view(league):
    with patch.object(VP, 'rail', return_value={}):
        return VP.upcoming_free_agents(N(user_team='GB'), league, 'GB')


class UpcomingFreeAgentsTests(unittest.TestCase):
    def test_league_wide_ir_and_real_cap_hit_not_annual_average(self):
        league = fixture()
        veteran = player(league, 'veteran', contract=Contract(1, [4], signing_bonus=3, roster_bonus=[2]))
        veteran.age = 29
        other = player(league, 'injured', team='MIN', contract=Contract(1, [5]))
        league.teams['MIN'].ir.append(other)
        player(league, 'long', contract=Contract(2, [8, 9]))
        player(league, 'unsigned', team=None)
        retired = player(league, 'retired', contract=Contract(1, [2])); retired.retired = True
        squad = player(league, 'squad', team=None); squad.team = 'GB'
        league.teams['GB'].practice_squad.append(squad)
        before = copy.deepcopy(league.save())
        result = view(league)
        self.assertEqual({r['pid'] for r in result['rows']}, {'veteran', 'injured'})
        row = next(r for r in result['rows'] if r['pid'] == 'veteran')
        self.assertEqual((row['age'], row['hit'], row['fa_class']), (29, 9, 'UFA'))
        self.assertEqual(result['market_year'], 2027)
        self.assertEqual(league.save(), before)

    def test_game_rfa_rule_projects_one_accrued_season_only(self):
        league = fixture()
        for accrued in (0, 2, 3, 5):
            p = player(league, str(accrued), contract=Contract(1, [1])); p.accrued = accrued
        result = {r['pid']: r['fa_class'] for r in view(league)['rows']}
        self.assertEqual(result, {'0': 'RFA', '2': 'RFA', '3': 'UFA', '5': 'UFA'})

    def test_same_class_before_and_after_roll_and_saved_reload(self):
        league = fixture()
        p = player(league, 'expiring', contract=Contract(1, [8])); p.accrued = 3
        player(league, 'next_class', contract=Contract(2, [10, 11]))
        league.set_phase('offseason'); league.season_closed_year = league.year
        before = view(league)
        self.assertEqual([r['pid'] for r in before['rows']], ['expiring'])
        self.assertEqual(before['market_year'], 2027)
        league.year += 1; league.advance_contracts()
        for current in (league, League.load(league.save())):
            result = view(current)
            self.assertEqual([r['pid'] for r in result['rows']], ['expiring'])
            self.assertEqual(result['rows'][0]['fa_class'], 'UFA')
            self.assertEqual(result['rows'][0]['hit'], 0)
            self.assertEqual(result['market_year'], 2027)
        league.set_phase('free_agency')
        result = view(league)
        self.assertEqual([r['pid'] for r in result['rows']], ['next_class'])
        self.assertEqual(result['market_year'], 2028)

    def test_contract_control_and_ownership_changes_refresh(self):
        league = fixture()
        p = player(league, 'p', contract=Contract(1, [8]))
        self.assertEqual(view(league)['count'], 1)
        p.contract = Contract(3, [8, 9, 10])  # extension / option adds control
        self.assertEqual(view(league)['count'], 0)
        p.contract = Contract(1, [8])
        league.teams['GB'].roster.remove(p); league.teams['MIN'].roster.append(p); p.team = 'MIN'
        self.assertEqual(view(league)['rows'][0]['team'], 'MIN')
        league.teams['MIN'].roster.remove(p); p.team = None; league.free_agents.append(p.pid)
        self.assertEqual(view(league)['count'], 0)

    def test_retention_tag_or_tender_removes_from_imminent_market(self):
        league = fixture(); league.set_phase('offseason'); league.season_closed_year = league.year - 1
        p = player(league, contract=None)
        self.assertEqual(view(league)['count'], 1)
        p.contract = Contract(1, [15])
        self.assertEqual(view(league)['count'], 0)

    def test_projected_room_matches_target_year_ledger(self):
        league = fixture(); player(league, contract=Contract(2, [5, 8]))
        limit, committed, _, _ = next_year_ledger(league, league.teams['GB'])
        self.assertEqual(view(league)['projected_space'], round(limit - committed, 1))
        league.set_phase('offseason'); league.season_closed_year = league.year - 1
        team = league.teams['GB']
        self.assertEqual(view(league)['projected_space'], round(team.cap.limit - team.cap.charges(team.phase), 1))


if __name__ == '__main__':
    unittest.main()

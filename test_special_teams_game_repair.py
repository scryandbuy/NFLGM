import unittest
from types import SimpleNamespace

from league import repair_special_teams_games


class Player:
    def __init__(self):
        self.career = {}

    def record_season(self, year, line):
        self.career[year] = dict(line)


class SpecialTeamsGameRepair(unittest.TestCase):
    def test_repair_counts_only_proven_missing_appearances(self):
        players = {pid: Player() for pid in ('returner', 'two_way', 'snapper', 'unknown')}
        def units(*pids):
            return {'offense': {'players': {pid: 1 for pid in pids}}}
        league = SimpleNamespace(
            game_stats={
                '2033-1-CIN-GB': {'returner': {'kr': 5}, 'two_way': {'kr': 2},
                                  'snapper': {'games': 1, 'snaps': 8}},
                '2033-2-CIN-GB': {'returner': {'kr': 3}},
                '2033-3-CIN-GB': {'unknown': {'kr': 4}},
            },
            team_game_stats={
                '2033-1-CIN-GB': {'CIN': {'snap_counts': units('two_way')},
                                  'GB': {'snap_counts': units('other')}},
                '2033-2-CIN-GB': {'CIN': {'snap_counts': units('other')},
                                  'GB': {'snap_counts': units('other2')}},
                '2033-3-CIN-GB': {'CIN': {}, 'GB': {}},
            },
            stats={2033: {'returner': {'games': 0}, 'two_way': {'games': 1},
                          'snapper': {'games': 1}, 'unknown': {'games': 0}}},
            post_stats={}, player=players.get,
        )
        repair_special_teams_games(league)
        self.assertEqual({pid: row['games'] for pid, row in league.stats[2033].items()},
                         {'returner': 2, 'two_way': 1, 'snapper': 1, 'unknown': 0})
        self.assertEqual(players['returner'].career[2033]['games'], 2)


if __name__ == '__main__':
    unittest.main()

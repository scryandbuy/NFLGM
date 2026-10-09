import unittest

from session import Session
from season import SeasonRunner


class SpecialTeamsAppearances(unittest.TestCase):
    def test_game_credits_special_teams_players_once(self):
        session = Session.new('GB', seed=27)
        runner = SeasonRunner(session.L, session.rng)
        runner.play('MIN', 'GB', 19, playoffs=True)
        league = session.L
        key = f'{league.year}-19-MIN-GB'
        game = league.game_stats[key]
        snap_pids = {pid for side in ('MIN', 'GB')
                     for pid in runner.states[side].last_snaps}
        special = {pid for pid, line in game.items()
                   if any(line.get(stat, 0) for stat in ('kr', 'pr', 'fg_att', 'xp_att', 'punts'))}
        special_only = special - snap_pids
        self.assertTrue(special_only)
        for pid in special_only:
            self.assertEqual(game[pid].get('games'), 1)
        for pid in set(game) | snap_pids:
            self.assertEqual(league.post_stats[league.year][pid].get('games'), 1)
        restored = Session.load(session.save())
        for pid in special_only:
            self.assertEqual(restored.L.post_stats[league.year][pid].get('games'), 1)


if __name__ == '__main__':
    unittest.main()

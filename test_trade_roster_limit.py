"""An in-season player trade must leave both clubs with playable active rosters."""
import unittest

from cap_engine import Contract
import gm_engine as GE
from league import DraftPick, League, Player, Team
import roster_needs as RN
import targets as TG


COUNTS = {'QB': 2, 'HB': 3, 'FB': 1, 'WR': 7, 'TE': 3,
          'LT': 2, 'LG': 2, 'C': 2, 'RG': 2, 'RT': 2,
          'LEDG': 2, 'REDG': 2, 'DT': 4, 'MIKE': 2, 'WILL': 2, 'SAM': 2,
          'CB': 6, 'FS': 2, 'SS': 2, 'K': 1, 'P': 1, 'LS': 1}
RATINGS = {key for weights in TG.DEPTH_WEIGHTS.values() for key in weights}


def fixture():
    league = League(2026)
    league.set_phase('regular')
    league.week = 2
    for abbr in ('GB', 'MIN'):
        team = Team(abbr, 'United North', 'United', gm=GE.GM())
        team.league = league
        team.phase = 'season'
        team.scheme = GE.scheme_of(team.gm)
        league.teams[abbr] = team
        for pos, count in COUNTS.items():
            for i in range(count):
                pid = f'{abbr}-{pos}-{i}'
                player = Player(pid, pid, pos, 27, {key: 75 for key in RATINGS},
                                team=abbr, contract=Contract(1, [1]), accrued=3)
                league.players[pid] = player
                team.roster.append(player)
        team.sync_cap()
    star = Player('STAR', 'Trade Star', 'WR', 25, {key: 95 for key in RATINGS},
                  team='MIN', contract=Contract(1, [1]), accrued=3)
    league.players[star.pid] = star
    league.teams['MIN'].roster.append(star)
    league.teams['MIN'].sync_cap()
    pick = DraftPick(2026, 7, 'GB', 'GB')
    league.teams['GB'].picks = [pick]
    return league, star, pick


class TradeRosterLimitTests(unittest.TestCase):
    def test_both_buyers_choose_cuts_after_acquisition(self):
        from game_availability import settle_roster, FieldabilityError
        for user in (None, 'GB'):
            league, star, pick = fixture()
            league.user_team = user
            before = {p.pid for p in league.teams['GB'].active()}
            league.trade('GB', 'MIN', [pick], [star.pid])
            self.assertEqual(len(league.teams['GB'].active()), 54)
            self.assertEqual(before | {star.pid}, {p.pid for p in league.teams['GB'].active()})
            self.assertFalse(any(e['kind'] == 'release' for e in league.transactions))
            if user:
                with self.assertRaises(FieldabilityError):
                    settle_roster(league, league.teams['GB'], 2)
            else:
                settle_roster(league, league.teams['GB'], 2)
                self.assertEqual(len(league.teams['GB'].active()), 53)
                self.assertIn(star, league.teams['GB'].active())
                self.assertGreaterEqual(league.teams['GB'].cap_space, 0)

    def test_offseason_can_temporarily_carry_more_than_53(self):
        league, star, pick = fixture()
        league.set_phase('offseason')
        league.trade('GB', 'MIN', [pick], [star.pid])
        self.assertEqual(len(league.teams['GB'].active()), 54)


if __name__ == '__main__':
    unittest.main()

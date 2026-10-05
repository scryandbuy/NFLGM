"""Regular-season award evidence is calendar-safe and credits actual roles."""
import copy
import unittest
from types import SimpleNamespace as NS

import awards as AW


def team(wins, prior=None, older=None):
    history = []
    if older is not None:
        history.append(dict(year=2026, win_pct=older / 17))
    if prior is not None:
        history.append(dict(year=2027, win_pct=prior / 17))
    return NS(win_pct=wins / 17, history=history)


def player(pid, pos='WR', club='A', entry=2028, accrued=0, career=None, draft=None):
    return NS(pid=pid, pos=pos, team=club, entry_year=entry, accrued=accrued,
              career=career or {}, draft_year=draft)


def league(players=(), lines=None, teams=None):
    players = {p.pid: p for p in players}
    return NS(year=2028, teams=teams or {'A': team(10)},
              stats={2028: lines or {}}, player=players.get)


class CoachYearEvidenceTests(unittest.TestCase):
    def test_previous_year_not_history_position_and_current_append_is_irrelevant(self):
        l = league(teams={'MIA': team(12, prior=9, older=2.5),
                          'LV': team(13, prior=9, older=10),
                          'CAR': team(12, prior=8, older=6)})
        self.assertEqual(AW.Ballot(l).coty(), 'LV')
        for t in l.teams.values():
            t.history.append(dict(year=2028, win_pct=t.win_pct))
        self.assertEqual(AW.Ballot(l).coty(), 'LV')
        for t in l.teams.values():
            t.history.reverse()
        self.assertEqual(AW.Ballot(l).coty(), 'LV')

    def test_no_prior_year_uses_existing_neutral_fallback_not_distant_history(self):
        l = league(teams={'A': team(10, older=0), 'B': team(11)})
        self.assertEqual(AW.Ballot(l).coty(), 'B')
        l.teams['A'].history.append(dict(year=2028, win_pct=10 / 17))
        self.assertEqual(AW.Ballot(l).coty(), 'B')

    def test_previous_year_decline_still_excludes_coach(self):
        l = league(teams={'A': team(12, prior=14, older=2),
                          'B': team(10, prior=8, older=12)})
        self.assertEqual(AW.Ballot(l).coty(), 'B')


class ProtectorScoringTests(unittest.TestCase):
    def test_each_offensive_touchdown_counts_once_regardless_of_pass_or_run(self):
        a, b = player('a', 'LT', 'A'), player('b', 'LT', 'B')
        qa, wa, hb, qb, wb = (player('qa', 'QB'), player('wa', 'WR'),
                              player('hb', 'HB', 'B'), player('qb', 'QB', 'B'),
                              player('wb', 'WR', 'B'))
        blocking = dict(pb_snaps=500, pb_wins=450, rb_snaps=400, rb_wins=320,
                        sacks_allowed=3, pressures_allowed=10)
        lines = {'a': dict(blocking), 'b': dict(blocking),
                 'qa': dict(pass_td=10), 'wa': dict(rec_td=10, rush_yds=1000),
                 'hb': dict(rush_td=11, rush_yds=1000), 'qb': {}, 'wb': {}}
        l = league([a, b, qa, wa, hb, qb, wb], lines,
                   {'A': team(10), 'B': team(10)})
        self.assertIs(AW.Ballot(l).protector(), b)
        # Moving B's eleven TDs from runs to completed passes does not change
        # the team scoring advantage or count the QB's mirror stats twice.
        lines['hb']['rush_td'] = 0
        lines['qb']['pass_td'] = lines['wb']['rec_td'] = 11
        self.assertIs(AW.Ballot(l).protector(), b)


class DefensiveEvidenceTests(unittest.TestCase):
    def test_half_sack_credit_survives_awards_and_award_card_text(self):
        import views_league as VL
        for pos in ('LEDG','MIKE'):
            with self.subTest(pos=pos):
                a,b=player('a',pos),player('b',pos)
                l=league([a,b],{'a':dict(sacks=12,tackles=60),
                                'b':dict(sacks=12.5,tackles=60)})
                ballot=AW.Ballot(l)
                self.assertAlmostEqual(ballot.def_score(b,l.stats[2028]['b'])-
                                       ballot.def_score(a,l.stats[2028]['a']),1.5)
                self.assertIs(ballot.dpoy(),b)
                self.assertIs(ballot.droy(),b)
                self.assertIn('12.5 sacks',VL._award_line(l,b,2028))
                l.game_stats={'2028-22-A-B':{'a':dict(sacks=1), 'b':dict(sacks=1.5)}}
                post=NS(champion='A',games=[('SB','', 'A','B',21,14)])
                self.assertIs(AW.championship_game_mvp(l,post,2028),b)
                self.assertIn('1.5',VL._sb_line(l,b,2028))

    def test_zero_canonical_ball_production_matches_absent_fields(self):
        ballot = AW.Ballot(league())
        for pos in ('MIKE', 'CB'):
            p = player(pos, pos)
            self.assertEqual(ballot.def_score(p, {'tackles': 40}),
                             ballot.def_score(p, dict(tackles=40, pass_def=0, int_def=0)))

    def test_ball_production_improves_each_defensive_role_without_team_epa_blame(self):
        ballot = AW.Ballot(league())
        line = dict(tackles=65, sacks=4, pressures=12, ff=1, pass_def=3, int_def=1)
        for pos in ('LEDG', 'DT', 'MIKE', 'WILL', 'SAM', 'CB', 'FS', 'SS'):
            p = player(pos, pos)
            baseline = ballot.def_score(p, line)
            with self.subTest(pos=pos):
                self.assertGreater(ballot.def_score(p, dict(line, pass_def=4)), baseline)
                self.assertGreater(ballot.def_score(p, dict(line, int_def=2)), baseline)
                self.assertEqual(ballot.def_score(p, dict(line, def_epa=-999)), baseline)
                self.assertEqual(ballot.def_score(p, dict(line, cov_snaps=1)), baseline)

    def test_recorded_corner_pass_defenses_affect_dpoy_and_all_pro(self):
        white, taylor, surtain = (player(n, 'CB', entry=2025, accrued=3)
                                  for n in ('White', 'Taylor-Britt', 'Surtain'))
        l = league([white, taylor, surtain], {
            white.pid: dict(int_def=7, pass_def=4, tackles=57, ff=1),
            taylor.pid: dict(int_def=5, pass_def=5, tackles=75),
            surtain.pid: dict(int_def=4, pass_def=18, tackles=88)})
        ballot = AW.Ballot(l)
        self.assertIs(ballot.dpoy(), surtain)
        first, second = ballot.all_pro()
        self.assertEqual(first, [surtain, white])
        self.assertEqual(second, [taylor])

    def test_linebacker_interception_breaks_equal_rush_production_for_rookie_honors(self):
        first, second = player('first', 'MIKE'), player('second', 'MIKE')
        base = dict(tackles=100, sacks=5, pressures=15, ff=2, pass_def=5)
        l = league([first, second], {'first': dict(base), 'second': dict(base, int_def=2)})
        ballot = AW.Ballot(l)
        self.assertIs(ballot.droy(), second)
        self.assertIs(ballot.dpoy(), second)
        self.assertEqual(ballot.all_pro(), ([second], [first]))


class RookieEligibilityTests(unittest.TestCase):
    def test_empty_production_does_not_award_an_arbitrary_player(self):
        defender = player('defender', 'MIKE')
        receiver = player('receiver')
        l = league([defender, receiver], {'defender': {'snaps': 40},
                                         'receiver': {'games': 2}})
        ballot = AW.Ballot(l)
        for award in ('opoy', 'oroy', 'dpoy', 'droy'):
            self.assertIsNone(getattr(ballot, award)(), award)
        l.awards = {}
        votes = AW.vote(l)
        self.assertFalse(set(AW.DEV_TIER_AWARDS) & set(l.awards[2028]))
        self.assertFalse(any(votes[a] for a in ('opoy','oroy','dpoy','droy')))

    def test_actual_rookie_production_wins_over_empty_entries(self):
        defender = player('defender', 'MIKE')
        receiver = player('receiver')
        l = league([defender, receiver], {'defender': {'tackles': 90, 'sacks': 5},
                                         'receiver': {'rec': 50, 'rec_yds': 800, 'rec_td': 6}})
        ballot = AW.Ballot(l)
        self.assertIs(ballot.oroy(), receiver)
        self.assertIs(ballot.opoy(), receiver)
        self.assertIs(ballot.droy(), defender)
        self.assertIs(ballot.dpoy(), defender)

    def test_entry_year_is_independent_of_contract_service(self):
        ballot = AW.Ballot(league())
        self.assertTrue(ballot.is_rookie(player('new', entry=2028, accrued=1)))
        self.assertFalse(ballot.is_rookie(player('old', entry=2027, accrued=0)))
        self.assertFalse(ballot.is_rookie(player('future', entry=2029, accrued=0)))

    def test_previous_entry_squad_only_player_does_not_become_a_new_entrant(self):
        p = player('previous-squad', entry=2027, accrued=0,
                   career={2027: {'games': 0, 'snaps': 0}})
        self.assertFalse(AW.Ballot(league()).is_rookie(p))

    def test_previous_participation_excludes_zero_service_and_bad_entry_metadata(self):
        ballot = AW.Ballot(league())
        for line in ({'games': 9, 'snaps': 24}, {'fg_att': 1}, {'punts': 1}):
            for entry in (None, 2027, 2028):
                with self.subTest(line=line, entry=entry):
                    p = player('prior', entry=entry, career={'2027': line})
                    self.assertFalse(ballot.is_rookie(p))

    def test_legacy_year_and_service_fallback_and_league_participation(self):
        l = league()
        ballot = AW.Ballot(l)
        self.assertTrue(ballot.is_rookie(player('drafted', entry=None, draft=2028)))
        self.assertFalse(ballot.is_rookie(player('old-draft', entry=None, draft=2027)))
        self.assertTrue(ballot.is_rookie(player('legacy', entry=None)))
        self.assertFalse(ballot.is_rookie(player('veteran', entry=None, accrued=1)))
        p = player('prior', entry=None)
        l.stats[2027] = {'prior': {'snaps': 10}}
        self.assertFalse(ballot.is_rookie(p))
        # Empty historical season rows alone are not participation evidence.
        l.stats[2027]['prior'] = {'games': 0, 'snaps': 0}
        self.assertTrue(ballot.is_rookie(p))

    def test_previous_reserve_cannot_win_rookie_award_over_true_entrant(self):
        old = player('old', career={2027: {'games': 2, 'snaps': 10}}, entry=2027)
        new = player('new')
        lines = {'old': dict(rec=100, rec_yds=1500, rec_td=15),
                 'new': dict(rec=60, rec_yds=900, rec_td=6)}
        l = league([old, new], lines)
        before = copy.deepcopy((l.stats, old.career))
        self.assertIs(AW.Ballot(l).oroy(), new)
        self.assertEqual((l.stats, old.career), before)


if __name__ == '__main__':
    unittest.main()

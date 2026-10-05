"""Player-level award comparisons; no prescribed positional winner frequency."""
import copy
import unittest

import awards as AW
from test_award_evidence import league, player, team


def pocket():
    return dict(pass_att=650, pass_cmp=450, pass_yds=5200, pass_td=52,
                ints=5, rush_yds=80)


def receiver():
    return dict(rec=100, rec_yds=1500, rec_td=12)


def back():
    return dict(rush_yds=1400, rush_td=12, rec=35, rec_yds=250, rec_td=2)


class OffensiveAwardComparisons(unittest.TestCase):
    def ballot(self, qb=None, hb=None, wr=None):
        people = [player('Quarterback', 'QB'), player('Back', 'HB'),
                  player('Receiver', 'WR')]
        return AW.Ballot(league(people, dict(Quarterback=qb or pocket(),
                                            Back=hb or back(),
                                            Receiver=wr or receiver())))

    def assert_offensive_winner(self, ballot, name):
        self.assertEqual(ballot.opoy().pid, name)
        self.assertEqual(ballot.oroy().pid, name)

    def test_exceptional_passer_can_beat_good_skill_seasons(self):
        self.assert_offensive_winner(self.ballot(), 'Quarterback')

    def test_exceptional_receiver_can_beat_exceptional_passer(self):
        wr = dict(rec=130, rec_yds=1900, rec_td=18)
        self.assert_offensive_winner(self.ballot(wr=wr), 'Receiver')

    def test_exceptional_all_purpose_back_can_beat_both(self):
        hb = dict(rush_yds=2200, rush_td=18, rec=40, rec_yds=300, rec_td=2)
        wr = dict(rec=130, rec_yds=1900, rec_td=18)
        self.assert_offensive_winner(self.ballot(hb=hb, wr=wr), 'Back')

    def test_combined_dual_threat_season_wins_but_modest_rushing_does_not(self):
        qb = dict(pass_att=520, pass_cmp=340, pass_yds=3700, pass_td=28,
                  ints=9, rush_yds=1000, rush_td=10)
        wr = dict(rec=130, rec_yds=1900, rec_td=18)
        self.assert_offensive_winner(self.ballot(qb=qb, wr=wr), 'Quarterback')
        qb.update(rush_yds=180, rush_td=2)
        self.assert_offensive_winner(self.ballot(qb=qb, wr=wr), 'Receiver')

    def test_turnover_heavy_volume_does_not_automatically_win(self):
        qb = dict(pass_att=650, pass_cmp=400, pass_yds=4800, pass_td=35,
                  ints=30, rush_yds=100)
        self.assert_offensive_winner(self.ballot(qb=qb), 'Back')
        qb['ints'] = 5
        self.assert_offensive_winner(self.ballot(qb=qb), 'Quarterback')

    def test_fumble_cost_counts_canonical_or_legacy_loss_once(self):
        b = self.ballot()
        base = pocket()
        for score in (b.offensive_score, b.passer_score, b.skill_score):
            clean = score(base)
            canonical = score(dict(base, fumbles_lost=3))
            self.assertLess(canonical, clean)
            self.assertEqual(canonical, score(dict(base, fum_lost=3)))
            self.assertEqual(canonical, score(dict(base, fumbles_lost=3, fum_lost=3)))
            self.assertEqual(clean, score(dict(base, fumbles=3)))
        # Close race flips on actual surrendered possessions, not recoveries.
        qb = dict(pocket(), pass_yds=4350, pass_td=40)
        self.assert_offensive_winner(self.ballot(qb=qb), 'Quarterback')
        qb['fumbles_lost'] = 3
        self.assert_offensive_winner(self.ballot(qb=qb), 'Back')

    def test_rushing_gains_count_even_when_passing_is_larger_component(self):
        b = self.ballot()
        base = pocket()
        self.assertEqual(b.offensive_score(dict(base, rush_yds=180)) -
                         b.offensive_score(base), 100)
        self.assertEqual(b.offensive_score(dict(base, rush_td=1)) -
                         b.offensive_score(base), 20)
        # A quarterback's scrimmage yards use the same unit as a back's.
        self.assertEqual(b.offensive_score(dict(rush_yds=100)), 100)

    def test_no_200_attempt_cliff_in_cross_position_awards(self):
        b = self.ballot()
        line = dict(pass_att=199, pass_cmp=140, pass_yds=1700, pass_td=15,
                    ints=3, rush_yds=250, rush_td=2)
        self.assertEqual(b.offensive_score(line),
                         b.offensive_score(dict(line, pass_att=200)))
        self.assert_offensive_winner(self.ballot(qb=line), 'Back')

    def test_rookie_field_only_changes_eligibility_not_production_scale(self):
        b = self.ballot()
        b.L.player('Quarterback').entry_year = 2027
        self.assertEqual(b.opoy().pid, 'Quarterback')
        self.assertEqual(b.oroy().pid, 'Back')

    def test_no_record_rating_or_insertion_order_boost(self):
        b = self.ballot()
        before = copy.deepcopy(b.lines)
        b.L.teams['A'].win_pct = 0
        for p, line in b.players():
            p.ovr, p.potential = 20, 99
        self.assert_offensive_winner(b, 'Quarterback')
        b.lines = dict(reversed(list(b.lines.items())))
        self.assert_offensive_winner(b, 'Quarterback')
        self.assertEqual(before, b.L.stats[2028])


class MVPComparisons(unittest.TestCase):
    def field(self, skill_line=None, skill_pos='HB', skill_wins=10, qb_wins=12):
        passer = player('Passer', 'QB', 'A')
        challenger = player('Challenger', skill_pos, 'B')
        lines = dict(Passer=dict(pass_att=550, pass_cmp=350, pass_yds=4000,
                                pass_td=32, ints=10),
                     Challenger=skill_line or dict(rush_yds=1650, rush_td=16,
                         rec=70, rec_yds=600, rec_td=4))
        return AW.Ballot(league([passer, challenger], lines,
                               {'A': team(qb_wins), 'B': team(skill_wins)}))

    def test_all_purpose_back_below_2000_rushing_can_beat_credible_qb(self):
        b = self.field()
        self.assertGreater(b.passer_score(b.lines['Passer']), 0)
        self.assertEqual(b.mvp().pid, 'Challenger')
        b.lines['Challenger'] = back()
        self.assertEqual(b.mvp().pid, 'Passer')

    def test_exceptional_receiver_can_win_without_rushing_yards(self):
        b = self.field(dict(rec=150, rec_yds=2200, rec_td=20), 'WR')
        self.assertEqual(b.mvp().pid, 'Challenger')
        # The same receiver does not receive a guaranteed position slot.
        b.lines['Passer'] = pocket()
        self.assertEqual(b.mvp().pid, 'Passer')

    def test_nonleading_rusher_is_not_excluded(self):
        b = self.field()
        other = player('RushingLeader', 'HB', 'A')
        previous_lookup = b.L.player
        b.L.player = lambda pid: other if pid == other.pid else previous_lookup(pid)
        b.lines[other.pid] = dict(rush_yds=1700, rush_td=9)
        self.assertEqual(b.mvp().pid, 'Challenger')

    def test_record_affects_close_case_without_blocking_losing_team(self):
        b = self.field(dict(rec=150, rec_yds=2200, rec_td=20), 'WR', skill_wins=4)
        self.assertEqual(b.mvp().pid, 'Challenger')
        # Identical production reasonably favors the stronger team.
        b.lines['Challenger'] = dict(b.lines['Passer'])
        self.assertEqual(b.mvp().pid, 'Passer')
        b.L.teams['B'].win_pct = 14 / 17
        self.assertEqual(b.mvp().pid, 'Challenger')

    def test_rank_ten_eleven_has_no_eligibility_or_scoring_cliff(self):
        b = self.field()
        challenger = b.L.player('Challenger')
        before = b.mvp_score(challenger, b.lines['Challenger'])
        # Other teams can move him outside the top ten without changing
        # anything about his own performance or club's record.
        for i in range(11):
            b.L.teams[f'Other{i}'] = team(14)
        reranked = AW.Ballot(b.L)
        self.assertGreater(reranked.rec_rank['B'], 10)
        self.assertEqual(reranked.mvp_score(challenger, b.lines['Challenger']), before)
        self.assertEqual(reranked.mvp().pid, 'Challenger')

    def test_1999_to_2000_rushing_yards_has_no_step_change(self):
        b = self.field()
        p = b.L.player('Challenger')
        low = b.mvp_score(p, dict(rush_yds=1999, rush_td=12))
        high = b.mvp_score(p, dict(rush_yds=2000, rush_td=12))
        self.assertAlmostEqual(high - low, 0.85 + 0.3 * 10 / 17)

    def test_efficiency_matters_but_small_trick_pass_cannot_multiply_season(self):
        b = self.field()
        p = b.L.player('Passer')
        line = b.lines['Passer']
        self.assertGreater(b.mvp_score(p, dict(line, pass_att=500)),
                           b.mvp_score(p, dict(line, pass_att=650)))
        receiver = dict(rec=130, rec_yds=1900, rec_td=18)
        diff = (b.mvp_score(p, dict(receiver, pass_att=1, pass_yds=80, pass_td=1))
                - b.mvp_score(p, receiver))
        self.assertLess(diff, 80)
        # A weak-efficiency adjustment must not make turnovers beneficial.
        negative = dict(pass_att=500, pass_yds=100, ints=10)
        self.assertLess(b.mvp_score(p, negative), 0)

    def test_offensive_position_label_does_not_change_identical_production(self):
        b = self.field()
        p = b.L.player('Challenger')
        expected = b.mvp_score(p, b.lines[p.pid])
        for pos in ('QB', 'HB', 'FB', 'WR', 'TE'):
            p.pos = pos
            self.assertEqual(b.mvp_score(p, b.lines[p.pid]), expected)
            self.assertIs(b.mvp(), p)

    def test_mvp_costs_actual_possession_losses_once(self):
        b = self.field()
        p = b.L.player('Passer')
        line = b.lines[p.pid]
        clean = b.mvp_score(p, line)
        self.assertLess(b.mvp_score(p, dict(line, ints=11)), clean)
        lost = b.mvp_score(p, dict(line, fumbles_lost=2))
        self.assertLess(lost, clean)
        self.assertEqual(lost, b.mvp_score(p, dict(line, fum_lost=2)))
        self.assertEqual(lost, b.mvp_score(p, dict(line, fum_lost=2, fumbles_lost=2)))
        self.assertEqual(clean, b.mvp_score(p, dict(line, fumbles=2)))

    def test_no_empty_mvp_and_unattached_production_has_neutral_record(self):
        p = player('FreeAgent', 'WR', club=None)
        b = AW.Ballot(league([p], {p.pid: {}}))
        self.assertIsNone(b.mvp())
        b.lines[p.pid] = dict(rec=130, rec_yds=1900, rec_td=18)
        self.assertIs(b.mvp(), p)
        self.assertEqual(b.mvp_score(p, b.lines[p.pid]), b.skill_score(b.lines[p.pid]))


class QuarterbackHonors(unittest.TestCase):
    def test_rushing_can_change_mvp_and_all_pro_but_does_not_guarantee_them(self):
        pocket_qb, runner = player('Pocket', 'QB'), player('Runner', 'QB')
        lines = {
            'Pocket': dict(pass_att=550, pass_cmp=370, pass_yds=4500,
                           pass_td=38, ints=8),
            'Runner': dict(pass_att=510, pass_cmp=340, pass_yds=3800,
                           pass_td=30, ints=8, rush_yds=900, rush_td=8),
        }
        b = AW.Ballot(league([pocket_qb, runner], lines))
        self.assertIs(b.mvp(), runner)
        self.assertEqual(b.all_pro(), ([runner], [pocket_qb]))
        lines['Runner'].update(rush_yds=100, rush_td=2)
        self.assertIs(b.mvp(), pocket_qb)
        self.assertEqual(b.all_pro(), ([pocket_qb], [runner]))

    def test_receiving_scores_and_negative_rush_yards_are_real_contributions(self):
        b = AW.Ballot(league())
        line = pocket()
        self.assertAlmostEqual(b.passer_score(dict(line, rec_td=1)) -
                               b.passer_score(line), 4.2)
        self.assertLess(b.passer_score(dict(line, rush_yds=-20)),
                        b.passer_score(dict(line, rush_yds=0)))


if __name__ == '__main__':
    unittest.main()


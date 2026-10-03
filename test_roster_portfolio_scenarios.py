"""Controlled portfolio scenarios, not replays of incomplete historical saves.

Use real players/contracts and production roster, bid, draft, trade and funding
paths. No mocked need, valuation, approval, or acquisition result is supplied.
"""
import copy
import unittest

import numpy as np

import draft
import draft_plan as DP
import financial_plan as FP
import market
import roster_needs as RN
import trades
import valuation
from cap_engine import CAP, Contract
from test_draft_planning import fixture, set_grade


def scenario(position, front='4-3'):
    league, team = fixture()
    league.user_team = None
    team.picks = []
    team.cap.year = league.year
    team.cap.cap = CAP.get(league.year, 301.2)
    league.cap_history[league.year] = team.cap.cap
    team.gm.def_front = front
    for player in team.by_pos(position):
        set_grade(player, 60)
    if position == 'DT':
        for player in team.by_pos('LEDG') + team.by_pos('REDG'):
            set_grade(player, 60)
    candidates = []
    for number in range(5):
        player = copy.deepcopy(team.by_pos(position)[0])
        player.pid = f'candidate-{position}-{number}'
        player.name = player.pid
        player.team = None
        player.contract = None
        player.fa_class = 'UFA'
        player.age = 28
        set_grade(player, 82)
        league.players[player.pid] = player
        league.free_agents.append(player.pid)
        candidates.append(player)
    return league, team, candidates


def acquire(league, team, player, years=3):
    # Exercise the actual signing and transaction-log path on a fresh fixture.
    league.sign(player.pid, team.abbr, Contract(years, [3.] * years))


class RosterPortfolioScenarios(unittest.TestCase):
    def test_equal_hbs_and_left_tackles_do_not_each_claim_one_open_job(self):
        for position in ('HB', 'LT'):
            with self.subTest(position=position):
                league, team, candidates = scenario(position)
                need_before = DP.assess(league, team.abbr)['positions'][position]['need']
                bids = market.ai_bids(league, candidates, 1, np.random.default_rng(87))
                self.assertEqual(sum(map(len, bids.values())), 1)
                winner = league.player(next(iter(bids)))
                acquire(league, team, winner)
                remaining = [p for p in candidates if p is not winner]
                self.assertTrue(all(RN.move_gain(team, p) <= 1 for p in remaining))
                self.assertEqual(market.ai_bids(league, remaining, 1,
                                               np.random.default_rng(87)), {})
                self.assertLess(DP.assess(league, team.abbr)['positions'][position]['need'],
                                need_before)

    def test_corners_keep_separate_jobs_but_fifth_duplicate_loses_its_bid(self):
        league, team, candidates = scenario('CB')
        original_gain = RN.move_gain(team, candidates[1])
        separate_bid = market.ai_bids(league, [candidates[1]], 1,
                                     np.random.default_rng(87))[candidates[1].pid][0]
        bids = market.ai_bids(league, candidates, 1, np.random.default_rng(87))
        self.assertGreaterEqual(len(bids), 3)
        self.assertLess(len(bids), len(candidates))
        self.assertLess(min(o.planning_gain for rows in bids.values() for o in rows),
                        original_gain)
        acquire(league, team, candidates[0])
        self.assertGreater(RN.move_gain(team, candidates[1]), 8)
        self.assertIsNotNone(market.reconsider_bid(league, candidates[1], separate_bid))
        for player in candidates[1:4]:
            acquire(league, team, player)
        self.assertLessEqual(RN.move_gain(team, candidates[4]), 1)
        self.assertEqual(market.ai_bids(league, [candidates[4]], 1,
                                       np.random.default_rng(87)), {})

    def test_three_four_front_values_distinct_dts_and_discourages_extra_draft_depth(self):
        league, team, candidates = scenario('DT', '3-4')
        gains = []
        for player in candidates[:4]:
            gains.append(RN.move_gain(team, player))
            acquire(league, team, player, years=4)
        self.assertTrue(all(gain > 1 for gain in gains[:3]))
        self.assertLessEqual(gains[3], 1)
        plan = DP.assess(league, team.abbr)
        ordinary = candidates[4]
        ordinary_gain = RN.move_gain(team, ordinary)
        self.assertGreater(DP.redundancy_penalty(plan, ordinary,
                                                grade=ordinary.ovr, gain=ordinary_gain), 0)
        set_grade(ordinary, 96)
        upgrade_gain = RN.move_gain(team, ordinary)
        self.assertGreater(upgrade_gain, 4)
        self.assertEqual(DP.redundancy_penalty(plan, ordinary,
                                              grade=ordinary.ovr, gain=upgrade_gain), 0)

    def test_stale_bid_is_withdrawn_without_touching_signed_contract(self):
        league, team, candidates = scenario('LT')
        target = candidates[1]
        bid = market.ai_bids(league, [target], 1,
                             np.random.default_rng(87))[target.pid][0]
        first = candidates[0]
        acquire(league, team, first)
        contract_before = copy.deepcopy(vars(first.contract))
        self.assertIsNone(market.reconsider_bid(league, target, bid))
        self.assertEqual(vars(first.contract), contract_before)
        self.assertEqual(first.team, team.abbr)
        self.assertIn(first, team.roster)
        self.assertIsNone(target.team)

    def test_expiring_tackle_has_real_succession_need_until_successor_arrives(self):
        league, team, candidates = scenario('LT')
        incumbent = league.player('LT0')
        set_grade(incumbent, 88)
        incumbent.age = 33
        incumbent.contract = Contract(1, [8.])
        prospect = next(p for p in league.draft_pool if p.pos == 'LT')
        before = DP.assess(league, team.abbr)['positions']['LT']
        board_before = next(score for score, p in draft.board(
            league, team.abbr, 32, {}, set()) if p is prospect)
        successor = candidates[0]
        successor.age = 22
        acquire(league, team, successor, years=4)
        after = DP.assess(league, team.abbr)['positions']['LT']
        board_after = next(score for score, p in draft.board(
            league, team.abbr, 32, {}, set()) if p is prospect)
        self.assertEqual(before['starter'], 0)
        self.assertGreater(before['future'], 6)
        self.assertLess(after['future'], before['future'])
        self.assertLess(board_after, board_before)
        self.assertIn(incumbent, team.roster)

    def test_financial_preferences_differ_for_same_real_marginal_upgrade(self):
        league, team, candidates = scenario('HB')
        set_grade(league.player('HB0'), 80)
        target = candidates[0]
        gain = RN.move_gain(team, target)
        self.assertGreater(gain, 1)
        league.set_phase('regular')
        team.sync_cap()
        team.cap.dead += team.cap.limit - team.cap.charges(team.phase) - 9.
        decisions = []
        for cautious in (True, False):
            team.gm.patience = 1 if cautious else 0
            team.gm.risk = 0 if cautious else 1
            team.gm.aggression = 0 if cautious else 1
            team.gm.job_security = 1 if cautious else .1
            decisions.append(FP.evaluate(league, team,
                additions=[(target, Contract(1, [3.]))], gain=gain))
        self.assertFalse(decisions[0]['approved'])
        self.assertEqual(decisions[0]['reason'], 'preserve_flexibility')
        self.assertTrue(decisions[1]['approved'])
        self.assertGreaterEqual(decisions[1]['after']['raw_room'], 0)

    def test_affordable_strong_upgrade_survives_an_already_filled_position(self):
        league, team, candidates = scenario('HB')
        set_grade(league.player('HB0'), 80)
        target = candidates[0]
        set_grade(target, 94)
        gain = RN.move_gain(team, target)
        offer = market.Offer(team.abbr, target.pid, 3., 2, planning_gain=gain)
        self.assertTrue(market.acquisition_read(league, team, target, offer, gain)['approved'])
        contract = market.offer_contract(league, target, offer)
        self.assertTrue(FP.evaluate(league, team, additions=[(target, contract)],
                                    gain=gain)['approved'])
        self.assertIn(target.pid, market.ai_bids(league, [target], 1,
                                                np.random.default_rng(87)))

    def test_new_arrival_is_given_trial_even_when_a_better_player_becomes_available(self):
        league, team, candidates = scenario('HB')
        arrival = candidates[0]
        acquire(league, team, arrival)
        for player, grade in zip(candidates[1:3], (95, 90)):
            set_grade(player, grade)
            acquire(league, team, player)
        self.assertIn(arrival.pid, trades.recent_acquisitions(league, team))
        pool = valuation.pool_from_league(league)
        surplus, _ = trades.surplus_and_needs(league, team, pool,
                                             np.random.default_rng(87))
        self.assertNotIn(arrival.pid, [row['pid'] for row in surplus])
        league.set_phase('regular')
        league.week = 4
        self.assertNotIn(arrival.pid, trades.recent_acquisitions(league, team))
        self.assertEqual(arrival.team, team.abbr)


if __name__ == '__main__':
    unittest.main()

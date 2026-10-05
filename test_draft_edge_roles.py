"""Interchangeable edge jobs must have label-independent recruiting value."""
import copy
import unittest

import draft_plan as DP
import roster_needs as RN
import targets as TG
from cap_engine import Contract
from league import Player
from test_draft_planning import fixture


def edge(pid, pos='LEDG', grade=80, age=25, years=3):
    return Player(pid, pid, pos, age,
                  {key: grade for key in TG.DEPTH_WEIGHTS['LEDG']},
                  contract=Contract(years, [2] * years))


def club(front='4-3', grades=(88, 85, 79, 76, 71)):
    league, team = fixture()
    team.gm.def_front = front
    team.roster = [p for p in team.roster if p.pos not in RN.EDGE_FAMILY]
    edges = [edge(f'edge-{i}', grade=grade) for i, grade in enumerate(grades)]
    team.roster.extend(edges)
    league.players.update({p.pid: p for p in edges})
    return league, team, edges


class DraftEdgeRoleTests(unittest.TestCase):
    def test_side_labels_do_not_change_room_depth_value_or_crowding(self):
        for front in ('4-3', '3-4'):
            with self.subTest(front=front):
                league, team, edges = club(front)
                snapshots = []
                for labels in (['LEDG'] * 5, ['REDG'] * 5,
                               ['LEDG', 'REDG', 'LEDG', 'REDG', 'LEDG']):
                    for player, label in zip(edges, labels):
                        player.pos = label
                    plan = DP.assess(league, 'MIN', {'LEDG': 81, 'REDG': 85})
                    left, right = (plan['positions'][pos] for pos in RN.EDGE_FAMILY)
                    for key in ('retention', 'starter', 'depth', 'future', 'need'):
                        self.assertEqual(left[key], right[key])
                    self.assertEqual(left['family_count'], 5)
                    self.assertEqual(left['family_starters'], 2)
                    self.assertAlmostEqual(left['retention']['capacity'], 4)
                    prospects = [edge('new-' + pos, pos, grade=70)
                                 for pos in RN.EDGE_FAMILY]
                    gains = RN.candidate_gains(plan['_roster'], prospects,
                                               baseline=plan['_roster_report'])
                    self.assertAlmostEqual(*gains.values())
                    penalties = [DP.redundancy_penalty(plan, p, grade=70,
                                                       gain=gains[p.pid])
                                 for p in prospects]
                    self.assertEqual(penalties[0], penalties[1])
                    self.assertGreater(penalties[0], 0)
                    snapshots.append((left['retention'], left['future'],
                                      plan['roster_score'], gains, penalties))
                self.assertEqual(snapshots[0], snapshots[1])
                self.assertEqual(snapshots[0], snapshots[2])

    def test_real_empty_and_one_edge_rooms_keep_vacancy_priority(self):
        for front in ('4-3', '3-4'):
            for grades in ((), (85,)):
                with self.subTest(front=front, grades=grades):
                    league, team, _ = club(front, grades)
                    plan = DP.assess(league, 'MIN')
                    self.assertGreater(plan['positions']['LEDG']['starter'], 0)
                    arrivals = [edge('new-' + pos, pos, grade=84)
                                for pos in RN.EDGE_FAMILY]
                    gains = RN.candidate_gains(plan['_roster'], arrivals,
                                               baseline=plan['_roster_report'])
                    self.assertAlmostEqual(*gains.values())
                    self.assertGreater(min(gains.values()), 15)
                    for p in arrivals:
                        self.assertEqual(DP.redundancy_penalty(plan, p, grade=84,
                                                              gain=gains[p.pid]), 0)

    def test_marginal_addition_and_departure_have_no_native_side_floor_bonus(self):
        for front in ('4-3', '3-4'):
            league, team, edges = club(front, (85, 83))
            newcomer = edge('reserve', 'REDG', 70)
            before = RN.assess(team)
            gain = RN.move_gain(team, newcomer, baseline=before)
            after = RN.assess(team, team.roster + [newcomer])
            self.assertAlmostEqual(gain, after['score'] - before['score'])
            self.assertAlmostEqual(gain, RN.departure_loss(team, newcomer, baseline=after))
            # Merely naming the reserve LEDG cannot remove or add four points
            # for an otherwise identical, already-covered edge position.
            newcomer.pos = 'LEDG'
            self.assertAlmostEqual(gain, RN.move_gain(team, newcomer, baseline=before))
            for p in edges:
                p.pos = 'REDG'
            relabeled = RN.assess(team)
            self.assertAlmostEqual(before['score'], relabeled['score'])
            self.assertAlmostEqual(gain, RN.move_gain(team, newcomer, baseline=relabeled))

    def test_succession_uses_actual_starters_and_preserves_age_and_expiry(self):
        for front in ('4-3', '3-4'):
            league, team, edges = club(front, (90, 87, 65))
            for p in edges[:2]:
                p.pos = 'REDG'
            weak = edges[-1]
            weak.age = 34
            weak.contract = Contract(1, [2])
            covered = DP.assess(league, 'MIN')
            self.assertEqual(covered['positions']['LEDG']['future'], 0)
            self.assertEqual(covered['positions']['REDG']['future'], 0)
            # Both actual starters now expire; the native LEDG reserve must
            # neither invent a third starting job nor hide either departure.
            for p in edges[:2]:
                p.contract = Contract(1, [2])
            exposed = DP.assess(league, 'MIN')
            self.assertGreater(exposed['positions']['LEDG']['future'], 6)
            self.assertEqual(exposed['positions']['LEDG']['expiring'], 2)
            for p in edges:
                p.age = 33
                p.contract = Contract(3, [2] * 3)
            aged = DP.assess(league, 'MIN')
            self.assertGreater(aged['positions']['LEDG']['future'], 6)
            team.roster.append(edge('young-successor', 'LEDG', 85, age=23))
            successor = DP.assess(league, 'MIN')
            self.assertLess(successor['positions']['LEDG']['future'],
                            aged['positions']['LEDG']['future'])

    def test_expiring_crowded_room_and_genuine_upgrade_are_not_blocked(self):
        for front in ('4-3', '3-4'):
            league, team, edges = club(front, (82, 81, 79, 78, 77))
            weak = edge('low-gain', grade=70)
            controlled = DP.assess(league, 'MIN')
            self.assertGreater(DP.redundancy_penalty(controlled, weak, grade=70), 0)
            upgrade = edge('upgrade', grade=95)
            gain = RN.candidate_gains(controlled['_roster'], [upgrade],
                                      baseline=controlled['_roster_report'])[upgrade.pid]
            self.assertGreater(gain, 4)
            self.assertEqual(DP.redundancy_penalty(controlled, upgrade, grade=95, gain=gain), 0)
            for p in edges:
                p.age = 33
                p.contract = Contract(1, [2])
            expiring = DP.assess(league, 'MIN')
            self.assertGreater(expiring['positions']['LEDG']['future'], 6)
            self.assertLess(DP.redundancy_penalty(expiring, weak, grade=70),
                            DP.redundancy_penalty(controlled, weak, grade=70))

    def test_returning_ir_edges_remain_in_plan_without_mutating_availability(self):
        for front in ('4-3', '3-4'):
            league, team, edges = club(front)
            before = DP.assess(league, 'MIN')['positions']
            team.ir = edges[:2]
            for p in team.ir:
                p.out_until = 99
            self.assertTrue(all(p not in team.active() for p in team.ir))
            state = copy.deepcopy(league.save())
            self.assertEqual(DP.assess(league, 'MIN')['positions'], before)
            self.assertEqual(league.save(), state)
            self.assertEqual([p.out_until for p in team.ir], [99, 99])


if __name__ == '__main__':
    unittest.main()

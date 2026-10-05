"""Waiver decisions must include the CPU's already-eligible IR returns."""
import copy
import unittest
from unittest.mock import patch

from cap_engine import Contract
from gm_engine import GM
from league import League, Player, Team
import injury_status as IS
import roster_needs as RN
import targets
import waivers as WV


def fixture(rating=69.85):
    # Controlled version of the observed MIN roster shape. Public grades and
    # inexpensive contracts isolate the return/claim seam, not historic replay.
    grades = dict(C=[75.68, 71.06], CB=[85.67, 82.67, 81.36, 75.21, 72.47],
        DT=[80.92, 79.79, 76.96, 70.51, 69.82], FB=[73.5],
        FS=[77.59, 76.11, 74.21], HB=[84.57, 84.3, 78.86, 77.44], K=[93.4],
        LEDG=[78.96, 75.48, 73.01], LG=[78.21, 72.18], LS=[70],
        LT=[89.66, 77.21], MIKE=[81.93, 77.71], P=[88.5], QB=[79.04, 78.09],
        REDG=[82.51, 74.91], RG=[80.72, 71.13], RT=[88.1, 76], SS=[81.17, 75.8],
        TE=[79.629, 72.352, 68.137], WILL=[79.03, 81.89],
        WR=[94.07, 88.01, 84.75, 76.69, 75.11, 74.91, 77.86])
    attrs = {k for weights in targets.DEPTH_WEIGHTS.values() for k in weights}
    league = League(2026)
    team = Team('MIN', 'United North', 'United',
                gm=GM(def_front='3-4', off_personnel='11'))
    league.teams['MIN'] = team
    team.league = league
    league.set_phase('regular')
    league.week = 10
    league.user_team = None
    league.waivers = []
    for pos, values in grades.items():
        for index, grade in enumerate(values):
            pid = f'{pos}{index}'
            p = Player(pid, pid, pos, 27, {k: grade for k in attrs}, team='MIN',
                       contract=Contract(2, [1., 1.]), accrued=5)
            league.players[pid] = p
            team.roster.append(p)
    returning = league.players['RT0']
    returning.out_until = 11
    returning.xp_spent.update(_ir_week=5, _ir_return=True)
    team.ir = [returning]
    team.ir_returns_used = 0
    # This is the order used by roll_week, before the wire and IR activation.
    IS.clear_recovered(league, 11)
    incoming = Player('CLAIM', 'Claim', 'RT', 27, {k: rating for k in attrs},
                      contract=Contract(1, [.85]), accrued=5)
    league.players[incoming.pid] = incoming
    entry = dict(pid=incoming.pid, from_team='PIT', year=2026, week=10,
                 claims=[], user_notified=False)
    team.sync_cap()
    team.cap.cap = 600.
    return league, team, incoming, returning, entry


def state(league, team):
    cap = {k: copy.deepcopy(v) for k, v in vars(team.cap).items() if k != 'contracts'}
    cap['contracts'] = [(pid, id(c), copy.deepcopy(vars(c)), year)
                        for pid, c, year in team.cap.contracts]
    return (tuple(p.pid for p in team.roster), tuple(p.pid for p in team.ir),
            team.ir_returns_used, cap,
            copy.deepcopy(league.transactions), copy.deepcopy(league.waivers),
            [(p.pid, p.team, p.out_until, id(p.contract), id(p._team_ref),
              copy.deepcopy(p.xp_spent)) for p in league.players.values()])


class WaiverIRProjectionTests(unittest.TestCase):
    def project(self, league, team, incoming):
        return IS.project_ir_returns(league, team, 11,
            additions=[(incoming, WV.claim_contract(league, incoming, team.abbr))])

    def test_marginal_claim_rejected_without_blocking_a_worthwhile_upgrade(self):
        for risk in (.2, .8):
            for grade, expected in ((69.85, False), (90., True)):
                with self.subTest(risk=risk, grade=grade):
                    league, team, incoming, returning, entry = fixture(grade)
                    team.gm.risk, team.gm.youth = risk, 1-risk
                    # Money is deliberately separated from the roster decision
                    # here; dedicated tests below exercise real release charges.
                    with patch('waivers._claim_budget', return_value=True):
                        self.assertEqual(WV.make_room(league, 'MIN', incoming, entry), expected)
                    self.assertIn(returning, team.ir)
                    self.assertEqual(team.ir_returns_used, 0)
                    self.assertEqual(league.transactions, [])
                    if expected:
                        plan = self.project(league, team, incoming)
                        WV.award(league, entry, 'MIN')
                        returned = IS.InjuryDesk().activate_from_ir(league, team, 11)
                        self.assertEqual([p.pid for p in returned], plan['returns'])
                        self.assertEqual({p.pid for p in team.active()}, plan['active'])
                        self.assertIn(incoming, team.active())
                        self.assertIn(returning, team.active())
                        self.assertEqual(len(team.active()), 53)

    def test_preview_is_read_only_including_live_cap_and_player_references(self):
        league, team, incoming, _, _ = fixture(90.)
        before = state(league, team)
        plan = self.project(league, team, incoming)
        self.assertTrue(plan['returns'])
        self.assertEqual(before, state(league, team))

    def test_multiple_returns_consume_only_remaining_designations_in_order(self):
        league, team, incoming, first, entry = fixture(90.)
        second = league.players['LT0']
        second.xp_spent.update(_ir_week=5, _ir_return=True)
        team.ir.append(second)
        team.ir_returns_used = 7
        plan = self.project(league, team, incoming)
        self.assertEqual(plan['returns'], [first.pid])
        self.assertEqual(plan['returns_used'], 8)
        self.assertNotIn(second.pid, plan['active'])
        self.assertEqual(team.ir_returns_used, 7)
        WV.award(league, entry, 'MIN')
        returned = IS.InjuryDesk().activate_from_ir(league, team, 11)
        self.assertEqual([p.pid for p in returned], plan['returns'])
        self.assertEqual({p.pid for p in team.active()}, plan['active'])
        self.assertIn(second, team.ir)

    def test_unready_season_ir_and_exhausted_returns_are_not_assumed_back(self):
        for case in ('injured', 'minimum_absence', 'season_ir', 'limit'):
            with self.subTest(case=case):
                league, team, incoming, returning, _ = fixture()
                if case == 'injured': returning.out_until = 12
                if case == 'minimum_absence': returning.xp_spent['_ir_week'] = 9
                if case == 'season_ir': returning.xp_spent['_ir_return'] = False
                if case == 'limit': team.ir_returns_used = 8
                plan = self.project(league, team, incoming)
                self.assertEqual(plan['returns'], [])
                self.assertNotIn(returning.pid, plan['active'])
                self.assertIn(incoming.pid, plan['active'])

    def test_two_returns_share_the_updated_roster_and_release_ledger(self):
        league, team, incoming, first, entry = fixture(90.)
        second = league.players['LT0']
        second.xp_spent.update(_ir_week=5, _ir_return=True)
        team.ir.append(second)
        for p in team.roster:
            p.contract = Contract(2, [1., 1.], signing_bonus=.8)
        team.sync_cap()
        plan = self.project(league, team, incoming)
        self.assertEqual(plan['returns'], [first.pid, second.pid])
        self.assertEqual(plan['returns_used'], 2)
        self.assertEqual(len(plan['cuts']), 2)
        self.assertAlmostEqual(plan['dead'], 1.6)
        WV.award(league, entry, 'MIN')
        returned = IS.InjuryDesk().activate_from_ir(league, team, 11)
        self.assertEqual([p.pid for p in returned], plan['returns'])
        self.assertEqual({p.pid for p in team.active()}, plan['active'])
        self.assertAlmostEqual(team.cap.charges(team.phase), plan['charges'])
        self.assertAlmostEqual(team.cap.dead, plan['dead'])

    def test_claims_named_release_is_included_before_return_planning(self):
        league, team, incoming, _, entry = fixture(90.)
        outgoing = league.players['FB0']
        outgoing.contract = Contract(2, [.3, .3], signing_bonus=.8, earned_base=.1)
        team.sync_cap()
        before = state(league, team)
        plan = IS.project_ir_returns(league, team, 11,
            additions=[(incoming, WV.claim_contract(league, incoming, 'MIN'))],
            removals=[outgoing.pid])
        self.assertEqual(before, state(league, team))
        self.assertNotIn(outgoing.pid, plan['active'])
        league.release(outgoing.pid)
        WV.award(league, entry, 'MIN')
        IS.InjuryDesk().activate_from_ir(league, team, 11)
        self.assertEqual({p.pid for p in team.active()}, plan['active'])
        self.assertAlmostEqual(team.cap.charges(team.phase), plan['charges'])
        self.assertAlmostEqual(team.cap.dead, plan['dead'])

    def test_user_roster_is_never_automatically_activated(self):
        league, team, incoming, _, _ = fixture()
        league.user_team = 'MIN'
        before = state(league, team)
        self.assertEqual(self.project(league, team, incoming)['returns'], [])
        self.assertEqual(before, state(league, team))

    def test_release_acceleration_can_defer_return_and_matches_actual_ledger(self):
        for space, permitted in ((1.45, False), (1.65, True)):
            with self.subTest(space=space):
                league, team, incoming, returning, entry = fixture(90.)
                # 52 active: claim fills the spot; returning RT needs one cut.
                team.roster.remove(league.players['FB0'])
                outgoing = league.players['C1']
                outgoing.contract = Contract(2, [.1, .1], signing_bonus=1.6,
                                             earned_base=.03)
                team.sync_cap()
                team.cap.cap = team.cap.charges(team.phase) + space
                before = state(league, team)
                # Fix only which reserve the selector proposes, so this case
                # isolates real cap preflight rather than choosing a free cut.
                def select(club, rows, limit=53, available=None):
                    return {r['pid'] for r in rows if r['pid'] != outgoing.pid}
                with patch('roster_needs.select_cutdown', side_effect=select):
                    plan = self.project(league, team, incoming)
                    self.assertEqual(bool(plan['returns']), permitted)
                    self.assertEqual(before, state(league, team))
                    WV.award(league, entry, 'MIN')
                    returned = IS.InjuryDesk().activate_from_ir(league, team, 11)
                self.assertEqual(bool(returned), permitted)
                self.assertAlmostEqual(team.cap.charges(team.phase), plan['charges'])
                self.assertAlmostEqual(team.cap.dead, plan['dead'])
                self.assertAlmostEqual(team.cap.dead_next, plan['dead_next'])
                if permitted:
                    self.assertAlmostEqual(plan['dead'], 1.6)
                    self.assertNotIn(outgoing, team.roster)
                else:
                    self.assertIn(returning, team.ir)
                    self.assertIn(outgoing, team.roster)


if __name__ == '__main__':
    unittest.main()

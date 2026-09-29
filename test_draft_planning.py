"""Decision-level checks for the roster plan shared by scouting and drafting."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

import draft as D
import draft_plan as DP
import spring as SP
import scouting as SC
import gm_engine as GM
import targets as TG
from league import League, Team, Player, DraftPick
from cap_engine import Contract


def fixture():
    L = League(2027); L.user_team = 'GB'; L.season_closed_year = 2026
    t = Team('MIN', 'NFC North', 'NFC'); t.league = L
    t.gm = GM.GM(); L.teams['MIN'] = t; L.set_phase('free_agency')
    counts = dict(QB=2, HB=3, FB=1, WR=5, TE=3, LT=2, LG=2, C=2, RG=2, RT=2,
                  LEDG=3, REDG=3, DT=4, MIKE=2, WILL=2, SAM=2, CB=6, FS=2, SS=2, K=1, P=1, LS=1)
    for pos, n in counts.items():
        for i in range(n):
            p = Player(f'{pos}{i}', f'{pos} {i}', pos, 25,
                       {k: 82 if i == 0 else 76 for k in TG.DEPTH_WEIGHTS[pos]},
                       team='MIN', contract=Contract(4, [1]*4))
            t.roster.append(p); L.players[p.pid] = p
    t.picks = [DraftPick(2026, 1, 'MIN', 'MIN', selection=32)]
    L.draft_pool = []
    for pos in ('QB', 'WR', 'LT', 'CB', 'LEDG', 'TE', 'HB', 'DT'):
        for i in range(8):
            p = Player(f'rookie-{pos}{i}', f'Prospect {pos}{i}', pos, 22,
                       {k: 83 - i for k in TG.DEPTH_WEIGHTS[pos]},
                       potential=89-i, potential_range=(87-i, 91-i))
            p.xp_spent['_tape'] = 0
            L.players[p.pid] = p; L.draft_pool.append(p)
    L.scouting = {'MIN': {p.pid: dict(ovr=p.ovr, pot_lo=87, pot_hi=91, flags=[],
                                        e_phys=0, e_skill=0) for p in L.draft_pool}}
    L.consensus = {p.pid: dict(ovr=p.ovr, pot=89) for p in L.draft_pool}
    SC._rank(L, L.draft_pool, L.consensus)
    return L, t


def set_grade(p, value):
    p.ratings = {k: value for k in TG.DEPTH_WEIGHTS[p.pos]}


class DraftPlanningTests(unittest.TestCase):
    def test_missing_backup_is_not_a_starting_qb_hole(self):
        L, t = fixture(); starter = L.player('QB0'); set_grade(starter, 95)
        backup = L.player('QB1'); t.roster.remove(backup)
        missing = DP.assess(L, 'MIN')['positions']['QB']
        board = [(v, p.pid) for v, p in D.board(L, 'MIN', 10, {}, set())]
        set_grade(backup, 55); t.roster.append(backup)
        weak = DP.assess(L, 'MIN')['positions']['QB']
        self.assertEqual(missing['starter'], 0)
        self.assertEqual(missing['future'], 0)
        self.assertGreater(missing['depth'], 0)
        self.assertEqual(missing['need'], weak['need'])
        self.assertEqual(board, [(v, p.pid) for v, p in D.board(L, 'MIN', 10, {}, set())])
        qb_rank = next(i+1 for i, (_, pid) in enumerate(board) if L.player(pid).pos == 'QB')
        self.assertGreater(qb_rank, 10)

    def test_empty_qb_still_gets_a_real_starter_priority(self):
        L, t = fixture(); t.roster = [p for p in t.roster if p.pos != 'QB']
        self.assertEqual(DP.assess(L, 'MIN')['positions']['QB']['starter'], 12)
        self.assertEqual(D.board(L, 'MIN', 10, {}, set())[0][1].pos, 'QB')

    def test_ir_return_is_included_without_changing_gameday_availability(self):
        L, t = fixture(); starter = L.player('QB0'); set_grade(starter, 95)
        before = DP.assess(L, 'MIN')['positions']
        t.ir = [starter]; starter.out_until = 99
        self.assertNotIn(starter, t.active())
        self.assertEqual(DP.assess(L, 'MIN')['positions'], before)
        self.assertEqual(starter.out_until, 99)
        self.assertEqual(t.ir, [starter])

    def test_expired_or_retired_player_is_not_assumed_to_return(self):
        L, t = fixture(); p = L.player('QB0'); p.contract = None
        L.player('QB1').retired = True
        self.assertEqual(DP.assess(L, 'MIN')['positions']['QB']['starter'], 12)

    def test_contract_expiry_changes_plan_and_board(self):
        L, t = fixture(); starter = L.player('LT0'); reserve = L.player('LT1')
        set_grade(reserve, 60)
        before = DP.assess(L, 'MIN')['positions']['LT']
        board_before = dict((p.pid, v) for v, p in D.board(L, 'MIN', 20, {}, set()))
        starter.contract = Contract(1, [1])
        after = DP.assess(L, 'MIN')['positions']['LT']
        board_after = dict((p.pid, v) for v, p in D.board(L, 'MIN', 20, {}, set()))
        self.assertGreater(after['future'], before['future'])
        self.assertGreater(board_after['rookie-LT0'], board_before['rookie-LT0'])

    def test_young_successor_reduces_aging_starter_need(self):
        L, t = fixture(); starter = L.player('QB0'); reserve = L.player('QB1')
        starter.age = 36; set_grade(reserve, 60)
        exposed = DP.assess(L, 'MIN')['positions']['QB']['future']
        reserve.age = 23; set_grade(reserve, 78); reserve.potential_range = (85, 91)
        covered = DP.assess(L, 'MIN')['positions']['QB']['future']
        self.assertGreaterEqual(exposed, 6)
        self.assertLess(covered, 6)

    def test_one_successor_cannot_cover_multiple_expiring_receivers(self):
        L, t = fixture()
        for p in t.by_pos('WR')[:3]: p.contract = Contract(1, [1])
        t.roster = [p for p in t.roster if p.pid != 'WR4']
        set_grade(L.player('WR3'), 81)
        plan = DP.assess(L, 'MIN')['positions']['WR']
        self.assertGreater(plan['future'], 0)
        self.assertEqual(plan['expiring'], 2)  # strong reserve takes one of the three starting jobs

    def test_expensive_future_contract_matters_only_with_cap_pressure(self):
        L, t = fixture(); L.player('LT0').contract = Contract(3, [40]*3)
        normal = DP.assess(L, 'MIN')['positions']['LT']['contract']
        for pos in ('QB', 'WR', 'CB'): L.player(pos+'0').contract = Contract(3, [100]*3)
        stressed = DP.assess(L, 'MIN')
        self.assertGreater(stressed['positions']['LT']['contract'], normal)
        self.assertGreater(stressed['cap_pressure'], 0)

    def test_proposed_roster_is_used_and_assessment_does_not_mutate(self):
        L, t = fixture(); before = copy.deepcopy(L.save())
        proposed = [p for p in t.roster if p.pos != 'QB']
        plan = DP.assess(L, 'MIN', players=proposed)
        self.assertEqual(plan['positions']['QB']['starter'], 12)
        self.assertEqual(L.save(), before)
        self.assertEqual(D.board(L, 'MIN', 10, {}, set(), players=proposed)[0][1].pos, 'QB')

    def test_base_personnel_and_front_still_change_role_requirements(self):
        L, t = fixture()
        t.gm.off_personnel = '13'; t.gm.def_front = '3-4'
        p = DP.assess(L, 'MIN')
        self.assertEqual(p['positions']['TE']['starters'], 3)
        self.assertEqual(p['positions']['WR']['starters'], 1)
        self.assertEqual(p['positions']['DT']['starters'], 3)
        self.assertEqual(len({r['player'].pid for r in p['assignments'] if r['player']}),
                         sum(r['player'] is not None for r in p['assignments']))

    def test_visit_windows_follow_exact_slots_and_acquired_late_picks(self):
        L, t = fixture(); t.picks[0].selection = 1
        first = SP._pick_range(L, 'MIN')
        t.picks[0].selection = 32
        self.assertNotEqual(first, SP._pick_range(L, 'MIN'))
        t.picks.append(DraftPick(2026, 6, 'KC', 'MIN', selection=190))
        windows = SP._pick_windows(L, 'MIN')
        self.assertEqual([w[2] for w in windows], [32, 190])
        for i, p in enumerate(L.draft_pool): L.consensus[p.pid]['rank'] = i*4+1
        chosen = SP._visit_targets(L, 'MIN', L.draft_pool, DP.assess(L, 'MIN'))
        ranks = [L.consensus[p.pid]['rank'] for p in chosen]
        self.assertTrue(any(178 <= r <= 210 for r in ranks))
        self.assertTrue(any(20 <= r <= 52 for r in ranks))
        self.assertLessEqual(len(chosen), 30)
        self.assertEqual(len(chosen), len({p.pid for p in chosen}))

    def test_scouting_prioritizes_completely_empty_position(self):
        L, t = fixture(); t.roster = [p for p in t.roster if p.pos != 'QB']
        for i, p in enumerate(L.draft_pool): L.consensus[p.pid]['rank'] = i+1
        target = L.player('rookie-QB0'); L.consensus[target.pid]['rank'] = 50
        chosen = SP._visit_targets(L, 'MIN', L.draft_pool, DP.assess(L, 'MIN'))
        self.assertEqual(chosen[0].pid, target.pid)

    def test_medical_penalty_uses_risk_not_aggression(self):
        L, t = fixture(); p = L.player('rookie-WR0'); p.ratings['injury_rating'] = 66
        p.medical = {'cut': 70}; v = copy.deepcopy(L.scouting['MIN'][p.pid])
        def adjustment(risk, aggression):
            t.gm.risk = risk; t.gm.aggression = aggression
            L.scouting['MIN'][p.pid] = copy.deepcopy(v)
            SP._medical(L, 'MIN', t, p, np.random.default_rng(1))
            return L.scouting['MIN'][p.pid]['adj']
        self.assertLess(adjustment(0, .5), adjustment(1, .5))
        self.assertEqual(adjustment(.5, 0), adjustment(.5, 1))


if __name__ == '__main__': unittest.main()

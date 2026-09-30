"""FA commitments and rookie roster decisions share the actual package plan."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

import market as M
import roster_needs as RN
import cutdown as CD
from cap_engine import CAP, Contract
from league import Player
from test_draft_planning import fixture, set_grade


class CommitmentTests(unittest.TestCase):
    def setUp(self):
        self.L, self.t = fixture()
        self.t.cap.cap = 1000
        self.t.sync_cap()

    def prospect(self, pos, number, grade):
        p = copy.deepcopy(self.L.player(f'{pos}0'))
        p.pid = number; p.team = None; p.contract = None
        p._team_ref = None
        set_grade(p, grade)
        self.L.players[p.pid] = p; self.L.free_agents.append(p.pid)
        return p

    def test_stale_bid_reprices_after_role_improves_and_survives_save(self):
        set_grade(self.L.player('QB0'), 60)
        set_grade(self.L.player('QB1'), 55)
        p = self.prospect('QB', 'target', 90)
        original = M.Offer('MIN', p.pid, 30, 3, planning_gain=RN.move_gain(self.t, p))
        restored = M.Offer.from_save(original.to_save())
        set_grade(self.L.player('QB0'), 82)
        revised = M.reconsider_bid(self.L, p, restored)
        self.assertIsNotNone(revised)
        self.assertLess(revised.apy, 15)
        self.assertEqual(original.apy, 30)
        self.assertEqual(restored.apy, 30)
        self.assertEqual(M.reconsider_bid(self.L, p, restored, user_team='MIN'), restored)

    def test_filled_role_withdraws_bid(self):
        p = self.prospect('QB', 'target', 80)
        self.assertIsNone(M.reconsider_bid(self.L, p, M.Offer('MIN', p.pid, 20, planning_gain=20)))

    def test_complementary_receivers_remain_recruitable(self):
        for p in self.t.roster:
            if p.pos == 'WR': set_grade(p, 60)
        a = self.prospect('WR', 'first', 88)
        b = self.prospect('WR', 'second', 87)
        offer = M.Offer('MIN', b.pid, 15, 3, planning_gain=RN.move_gain(self.t, b))
        self.t.roster.append(a)
        revised = M.reconsider_bid(self.L, b, offer)
        self.assertIsNotNone(revised)
        self.assertGreater(revised.apy, 10)

    def test_contract_hit_cannot_consume_roster_completion_reserve(self):
        p = self.prospect('QB', 'target', 95)
        with patch.object(M, 'power', return_value=2):
            self.assertIsNone(M.reconsider_bid(self.L, p, M.Offer('MIN', p.pid, 20, 3)))

    def test_old_saved_bids_remain_readable(self):
        offer = M.Offer.from_save(dict(team='MIN', pid='p', apy=8, years=1))
        self.assertIsNone(offer.planning_gain)
        self.assertEqual(offer.apy, 8)

    def test_round_resolves_first_signing_then_reconsiders_remaining_offer(self):
        set_grade(self.L.player('QB0'),60);set_grade(self.L.player('QB1'),55)
        first=self.prospect('QB','first',82);second=self.prospect('QB','second',90)
        bids={p.pid:[M.Offer('MIN',p.pid,20 if p is first else 30,3,
                           planning_gain=RN.move_gain(self.t,p))] for p in (first,second)}
        with patch.object(M.VAL,'pool_from_league',return_value=[]), \
             patch.object(M.VAL,'value_player',return_value=dict(apy=20,years=3)), \
             patch.object(M,'profile_for',return_value={}), \
             patch.object(M,'utility_of',side_effect=lambda L,p,o,*args:o.apy):
            signed,waiting,_=M.resolve_phase(self.L,[first,second],bids,1,np.random.default_rng(3))
        self.assertEqual([p.pid for _,p,_ in signed],['first'])
        self.assertIn(second,waiting)
        self.assertEqual(first.team,'MIN')
        self.assertIsNone(second.team)
        self.assertLess(bids['second'][0].apy,20)

    def test_pending_user_answer_drops_unfunded_cpu_rival(self):
        p = self.prospect('QB', 'target', 95)
        thread = dict(id='talk', team='GB', pid=p.pid, kind='fa_offseason', state='waiting',
                      rival=dict(team='MIN', apy=20, years=3))
        self.L.negotiations = [thread]
        with patch.object(M, 'power', return_value=1):
            M.refresh_negotiation_rivals(self.L, {p.pid:[M.Offer('MIN', p.pid, 20)]}, 'GB')
        self.assertIsNone(thread['rival'])

    def test_retention_values_control_growth_and_succession_without_hidden_ceiling(self):
        p = self.L.player('QB1'); p.age=22; p.accrued=0; p.draft_round=2
        p.potential_range=(84, 90)
        starter=self.L.player('QB0'); starter.age=35
        value=RN.retention_value(self.t,p)
        self.assertGreater(value,2)
        p.potential=99
        self.assertEqual(RN.retention_value(self.t,p),value)
        p.contract=Contract(1,[1])
        self.assertEqual(RN.retention_value(self.t,p),0)
        p.contract=Contract(4,[1]*4);set_grade(p,45)
        self.assertEqual(RN.retention_value(self.t,p),0)

    def test_cutdown_prefers_near_equal_rookie_over_expiring_old_backup(self):
        p=self.L.player('QB1');p.age=33;p.accrued=10;p.contract=Contract(1,[1]);set_grade(p,77)
        rookie=copy.deepcopy(p);rookie.pid='rookie';rookie.age=22;rookie.accrued=0
        rookie.draft_round=2;rookie.potential_range=(85,90);rookie.contract=Contract(4,[1]*4)
        set_grade(rookie,76);self.t.roster.append(rookie)
        # Keep the normal 53-player allocation/lineup safeguards in this test.
        selected=RN.select_cutdown(self.t,CD.rows_for(self.t))
        self.assertEqual(len(selected),53)
        self.assertIn(rookie.pid,selected)
        self.assertNotIn(p.pid,selected)
        self.assertEqual(RN.lineup_strength(self.t,[q for q in self.t.active() if q.pid in selected])[0],0)
        set_grade(rookie,45)
        self.assertNotIn(rookie.pid,RN.select_cutdown(self.t,CD.rows_for(self.t)))


if __name__ == '__main__': unittest.main()

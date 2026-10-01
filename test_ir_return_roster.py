import copy
import unittest
from unittest.mock import patch
from session import Session
from injury_status import InjuryDesk

class IRReturnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Session.new('GB', seed=23)

    def setUp(self):
        self.s = copy.deepcopy(self.base)
        self.L = self.s.L
        self.L.week = 8
        self.t = self.L.teams['CHI']
        # Build a full roster plus one healthy, eligible returning player.
        self.t.roster = self.t.roster[:54]
        self.p = self.t.roster[0]
        self.t.ir = [self.p]
        self.p.xp_spent.update(_ir_week=3, _ir_return=True)
        self.p.out_until = 8
        self.t.ir_returns_used = 0
        self.t.cap.rollover = 10000
        self.desk = InjuryDesk()

    def test_real_cutdown_selector_retains_star_return(self):
        self.p = max(self.t.roster, key=lambda q:q.ovr)
        self.t.ir = [self.p]
        self.p.xp_spent.update(_ir_week=3, _ir_return=True)
        self.p.out_until = 8
        # Remove financial/draft protections to isolate real roster selection.
        for q in self.t.roster:
            q.contract = None
            q.draft_round = None
        self.assertEqual(self.desk.activate_from_ir(self.L,self.t,8), [self.p])
        self.assertEqual(len(self.t.active()),53)

    def test_manual_overage_and_eligibility(self):
        self.assertFalse(self.t.activate_from_ir(self.p, 6)['ok'])
        self.assertFalse(self.t.activate_from_ir(self.p, 7)['ok'])
        self.assertTrue(self.t.activate_from_ir(self.p, 8)['ok'])
        self.assertEqual(len(self.t.active()), 54)
        self.assertEqual(self.t.ir_returns_used, 1)
        self.assertFalse(self.t.activate_from_ir(self.p, 8)['ok'])

    def run_return(self, reject=False, protected=False):
        cut = self.p if reject else self.t.roster[-1]
        kept = {p.pid for p in self.t.roster if p is not cut}
        with patch('roster_needs.select_cutdown', return_value=kept), \
             patch('roster_needs.lineup_strength', return_value=(0,80)), \
             patch('practice_squad.protected', return_value=protected), \
             patch('practice_squad.locked', return_value=False):
            return self.desk.activate_from_ir(self.L,self.t,8)

    def test_full_roster_return_commits_one_cut(self):
        self.assertEqual(self.run_return(), [self.p])
        self.assertEqual(len(self.t.active()), 53)
        self.assertEqual(self.t.ir_returns_used, 1)
        self.assertEqual(self.desk.activate_from_ir(self.L,self.t,8), [])

    def test_rejected_candidate_and_protected_cut_leave_ir_intact(self):
        for options in ({'reject':True},{'protected':True}):
            self.assertEqual(self.run_return(**options), [])
            self.assertEqual(self.t.ir, [self.p])
            self.assertEqual(self.p.out_until,8)
            self.assertEqual(self.t.ir_returns_used,0)
            self.assertEqual(len(self.t.roster),54)

    def test_cap_failure_leaves_ir_intact(self):
        self.t.cap.rollover = -10000
        self.assertEqual(self.run_return(),[])
        self.assertEqual(self.t.ir_returns_used,0)
        self.assertEqual(len(self.t.roster),54)

    def test_user_never_automatically_activated(self):
        self.L.user_team = 'CHI'
        self.assertEqual(self.run_return(),[])
        self.assertEqual(self.t.ir,[self.p])

    def test_overage_blocks_regular_and_playoff_advance_even_after_game(self):
        self.s.runner = None
        for stop in (('week',8),('playoffs',)):
            self.s.stop = stop
            self.s.played = True
            self.assertTrue(any(b['kind']=='roster' for b in self.s.blocking()))
            self.assertEqual(self.s.advance()['done'],'Blocked')

if __name__ == '__main__': unittest.main()


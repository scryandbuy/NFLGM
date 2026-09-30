"""Audit reproduction: advancing a legal user roster must not auto-recruit."""
import unittest
import copy
import cutdown
from session import Session


class CutdownUserControlAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial=Session.new('GB',seed=93030).save()

    def test_legal_fifty_two_player_user_roster_remains_a_user_choice(self):
        s=Session.load(self.initial)
        t=s.L.teams['GB']
        # Isolate the user's legal roster from unrelated CPU cap/cutdown work.
        t.roster=t.roster[:52]
        s.L.teams={'GB':t}
        t.cap.cap=1000
        t.sync_cap()
        before={p.pid for p in t.active()}
        self.assertFalse(any(b['kind'] in ('roster','cap') for b in s.blocking()))
        result=s.advance()
        self.assertEqual(result['done'],'Cutdown')
        self.assertEqual({p.pid for p in t.active()},before)

    def test_illegal_user_roster_still_blocks_before_automatic_moves(self):
        for size in (45,54):
            s=Session.load(self.initial);t=s.L.teams['GB']
            t.roster=t.roster[:size];t.cap.cap=1000;t.sync_cap()
            before={p.pid for p in t.active()}
            state=copy.deepcopy(s.rng.bit_generator.state)
            self.assertEqual(s.advance()['done'],'Blocked')
            self.assertEqual({p.pid for p in t.active()},before)
            self.assertEqual(s.rng.bit_generator.state,state)

    def test_ai_fills_while_user_keeps_legal_vacancy(self):
        s=Session.load(self.initial)
        s.L.teams={key:s.L.teams[key] for key in ('GB','MIN')}
        for t in s.L.teams.values():
            t.roster=t.roster[:52];t.cap.cap=1000;t.sync_cap()
        before={p.pid for p in s.L.teams['GB'].active()}
        self.assertEqual(cutdown.fill_short(s.L,s.rng),1)
        self.assertEqual({p.pid for p in s.L.teams['GB'].active()},before)
        self.assertEqual(len(s.L.teams['MIN'].active()),53)

    def test_emergency_fill_never_signs_for_over_cap_user(self):
        s=Session.load(self.initial);t=s.L.teams['GB']
        t.roster=t.roster[:52];s.L.teams={'GB':t};t.cap.cap=1;t.sync_cap()
        before={p.pid for p in t.active()}
        self.assertEqual(cutdown.emergency_fill(s.L,s.rng),0)
        self.assertEqual({p.pid for p in t.active()},before)
        self.assertTrue(any(b['kind']=='cap' for b in s.blocking()))


if __name__=='__main__':unittest.main()

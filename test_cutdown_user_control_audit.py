"""Audit reproduction: advancing a legal user roster must not auto-recruit."""
import unittest
from session import Session


class CutdownUserControlAuditTests(unittest.TestCase):
    def test_legal_fifty_two_player_user_roster_remains_a_user_choice(self):
        s=Session.new('GB',seed=93030)
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


if __name__=='__main__':unittest.main()

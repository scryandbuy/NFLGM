import unittest
from unittest.mock import patch, Mock
import club_notes as CN
import injury_status as IS
from test_cap_accounting import fixture, player

class InjuryOwnershipTests(unittest.TestCase):
    def test_report_filters_former_player_in_body_and_subject(self):
        L=fixture(); L.user_team='GB'
        former=player(L,'former','MIN'); current=player(L,'current')
        L.transactions=[dict(kind='injury',pid=p.pid,team='GB',weeks=2) for p in (former,current)]
        with patch.object(CN.IB,'post') as post:
            CN._injury_report(L,L.teams['GB'],1,[])
        post.assert_called_once()
        self.assertNotIn('former',str(post.call_args))
        self.assertIn('current',str(post.call_args))

    def test_no_report_for_former_player_only(self):
        L=fixture(); p=player(L,team=None)
        L.transactions=[dict(kind='injury',pid=p.pid,team='GB',weeks=2)]
        with patch.object(CN.IB,'post') as post:
            CN._injury_report(L,L.teams['GB'],1,[])
        post.assert_not_called()
        self.assertEqual(L.notes_sent['_inj_idx'],1)

    def test_current_player_still_receives_medical_processing(self):
        L=fixture(); p=player(L); p.out_until=4
        desk=IS.InjuryDesk(); desk.playing_hurt[p.pid]='questionable'
        rng=Mock(); rng.random.return_value=0; rng.integers.return_value=2
        with patch.object(IS,'hurt_profile',return_value=({},1)):
            result=desk.flare(L,L.teams['GB'],1,rng)
        self.assertEqual(result,[(p,2)])
        self.assertEqual(p.out_until,4)

    def test_stale_medical_entries_cannot_change_former_player(self):
        for club in (None,'MIN'):
            L=fixture(); p=player(L,team=club); p.out_until=4
            desk=IS.InjuryDesk(); desk.pending[p.pid]='questionable'
            desk.playing_hurt[p.pid]='questionable'; desk.status[p.pid]='questionable'
            rng=Mock()
            desk.resolve_pending(L,L.teams['GB'],rng)
            self.assertEqual(desk.flare(L,L.teams['GB'],1,rng),[])
            self.assertEqual(p.out_until,4)
            self.assertFalse(desk.pending)
            self.assertFalse(desk.playing_hurt)
            rng.random.assert_not_called()

if __name__=='__main__': unittest.main()

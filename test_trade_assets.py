import unittest
from types import SimpleNamespace
from unittest.mock import patch
import views_personnel as VP
from session import Session

class TradeAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = Session.new('GB', seed=45)
        cls.v = cls.s.personnel('trades', other='DEN')

    def test_typed_and_legacy_evaluation_match(self):
        a=[self.v['me']['roster'][0]['pid'], self.v['me']['picks'][0]['id']]
        b=[self.v['them']['roster'][0]['pid']]
        typed=[dict(kind='player',id=a[0]),dict(kind='pick',id=a[1])]
        self.assertEqual(VP._evaluate(self.s.L,'GB','DEN',a,b), VP._evaluate(self.s.L,'GB','DEN',typed,[dict(kind='player',id=b[0])]))
        self.assertEqual(VP.act_ask(self.s.L,'GB','DEN',a,b),VP.act_ask(self.s.L,'GB','DEN',typed,[dict(kind='player',id=b[0])]))

    def test_trade_view_keeps_far_future_picks_available_to_counteroffers(self):
        from league import DraftPick
        for abbr in ('GB','DEN'):
            team=self.s.L.teams[abbr]
            pick=DraftPick(year=self.s.L.year+3,round=1,original=abbr,owner=abbr)
            team.picks.append(pick)
            try:
                view=self.s.personnel('trades',other='DEN')
                side='me' if abbr=='GB' else 'them'
                self.assertIn(f'{pick.year}-1-{abbr}',[p['id'] for p in view[side]['picks']])
            finally:
                team.picks.remove(pick)

    def test_type_ownership_and_duplicate_validation(self):
        pid=self.v['me']['roster'][0]['pid']
        self.assertEqual(VP._trade_ids(self.s.L,'GB',[pid,dict(kind='player',id=pid)]),[pid])
        for asset in [dict(kind='pick',id=pid),dict(kind='player',id=self.v['them']['roster'][0]['pid']),dict(kind='player',id='missing')]:
            with self.assertRaises(ValueError): VP._trade_ids(self.s.L,'GB',[asset])

    def test_hyphenated_player_id_is_a_player(self):
        player=SimpleNamespace(team='GB')
        league=SimpleNamespace(player=lambda x: player if x=='player-with-hyphens' else None,teams={'GB':SimpleNamespace(picks=[])})
        self.assertEqual(VP._trade_ids(league,'GB',[dict(kind='player',id='player-with-hyphens')]),['player-with-hyphens'])
        self.assertTrue(VP._trade_player(league,'player-with-hyphens'))

    def test_typed_propose_reaches_existing_engine(self):
        a=self.v['me']['picks'][0]['id']; b=self.v['them']['picks'][0]['id']
        with patch('trades.will_accept',return_value=True), patch.object(self.s.L,'trade') as trade:
            r=VP.act_propose(self.s.L,'GB','DEN',[dict(kind='pick',id=a)],[dict(kind='pick',id=b)])
            self.assertTrue(r['done']);trade.assert_called_once()
            self.assertEqual(trade.call_args.args[2][0].owner,'GB')
            self.assertEqual(trade.call_args.args[3][0].owner,'DEN')

    def test_draft_log_accepts_typed_and_legacy_picks(self):
        from unittest.mock import Mock
        for typed in (False, True):
            pk=SimpleNamespace(year=2026,round=2,original='DEN',selection=40)
            draft=SimpleNamespace(done=False,picks=[pk],year=2026,trades=[])
            shell=SimpleNamespace(L=SimpleNamespace(log=Mock()),user_team='GB',draft=draft)
            item=dict(kind='pick',id='2026-2-DEN') if typed else '2026-2-DEN'
            with patch.object(VP,'act_propose',return_value=dict(ok=True,done=True)):
                Session.personnel_act(shell,'propose',other='DEN',a_sends=[],b_sends=[item])
            self.assertEqual(draft.trades[0][:3],(40,'GB','DEN'))
            shell.L.log.assert_called_once()

if __name__=='__main__': unittest.main()

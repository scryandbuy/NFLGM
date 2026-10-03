import unittest
from contextlib import ExitStack
from types import SimpleNamespace as N
from unittest.mock import patch

import views_personnel as VP


class TradeFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.players = {
            'send1': N(pid='send1', name='First Receiver', pos='WR', team='GB', out_until=None),
            'send2': N(pid='send2', name='Second Receiver', pos='WR', team='GB', out_until=None),
            'hurt': N(pid='hurt', name='Hurt Receiver', pos='WR', team='GB', out_until=8),
            'keep': N(pid='keep', name='George Pickens', pos='WR', team='GB', out_until=None),
            'incoming': N(pid='incoming', name='Incoming Receiver', pos='WR', team='NYG', out_until=None),
        }
        def team(abbr, space):
            return N(abbr=abbr, gm=None, cap_space=space, picks=[], phase='season', ctx=lambda: {},
                     active=lambda: [p for p in self.players.values() if p.team == abbr])
        self.L=N(year=2026, week=4, teams={'GB':team('GB',100), 'NYG':team('NYG',1)},
                 player=self.players.get)
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch('valuation.pool_from_league',return_value=[]))
        self.stack.enter_context(patch('trades.persona',return_value={}))
        self.stack.enter_context(patch('trades.cpu_trade_check',return_value={'approved':True}))
        self.stack.enter_context(patch('cap_accounting.trade_projection',return_value=N(space=lambda phase:110)))
        self.stack.enter_context(patch.object(VP,'_assets',side_effect=lambda L,a,ids,*args,**kw:
            [dict(kind='player',inherit=10,out_hit=10,dead=0) for pid in ids]))

    def test_actual_receiving_cap_block_is_readable_and_not_an_overpay(self):
        result=VP._evaluate(self.L,'GB','NYG',['send1'],[])
        self.assertEqual(result['verdict'],'blocked')
        self.assertFalse(result['would_accept'])
        self.assertTrue(result['read'].startswith('We '))
        self.assertIn('cap space',result['read'])
        for text in ('b_cannot_fit','deepest','Pickens','Sunday'):
            self.assertNotIn(text,result['read'])
        self.assertNotIn('giving up too much',result['my_read'])
        self.assertIn('Your WR depth after this trade: 2 healthy players.',result['my_read'])

    def test_whole_package_depth_excludes_outgoing_and_injured_includes_incoming(self):
        with patch('trade_engine.evaluate',return_value=dict(a_gain=2,b_gain=2,accepted=True)):
            result=VP._evaluate(self.L,'GB','NYG',['send1','send2'],['incoming'])
        self.assertIn('2 healthy players',result['my_read'])
        self.assertEqual(result['my_read'].count('Your WR depth'),1)
        self.assertNotIn('Your WR depth',result['read'])

    def test_trade_read_projects_both_teams_current_cap(self):
        def preview(league, abbr, outgoing, incoming):
            self.assertEqual((outgoing, incoming),
                             (['send1'], ['incoming']) if abbr == 'GB' else (['incoming'], ['send1']))
            return N(space=lambda phase: 94.2 if abbr == 'GB' else 6.8)
        with patch('trade_engine.evaluate',return_value=dict(a_gain=2,b_gain=2,accepted=True)), \
             patch('cap_accounting.trade_projection',side_effect=preview):
            result=VP._evaluate(self.L,'GB','NYG',['send1'],['incoming'])
        self.assertEqual(result['cap_after'],{'me':94.2,'them':6.8})

    def test_all_reasons_and_unknown_codes_have_safe_text(self):
        for reason in ('a_dead_money','b_dead_money','a_cannot_fit','b_cannot_fit','a_space','b_space','unknown_internal_reason'):
            with self.subTest(reason=reason):
                self.assertNotIn(reason,VP._cap_block_read(reason,'NYG'))

    def test_ask_counter_also_explains_cap_block(self):
        self.L.teams['GB'].cap_space=1
        result=VP.act_ask(self.L,'GB','NYG',[],['incoming'])
        self.assertFalse(result['ok'])
        self.assertEqual(result['adds'],[])
        self.assertEqual(result['why'],'Your team does not have enough cap space for this trade.')


if __name__=='__main__':unittest.main()

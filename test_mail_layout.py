import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import inbox as IB
import league_notes as LN
from league import League
from test_cap_accounting import fixture, player


class MailLayoutTests(unittest.TestCase):
    def test_digest_preserves_trade_pairs_and_other_transactions(self):
        import inbox_digest
        league = fixture()
        for a, b in [('GB', 'MIN'), ('KC', 'BUF')]:
            IB.post(league, 'league', f'{a} and {b} make a trade', '', payload=dict(
                mail_layout='trade', mail_sections=IB.trade_sections(a, b,
                    ['a 2032 second-round pick', 'a 2032 second-round pick'], ['Player (TE, 90)'])))
        IB.post(league, 'league', 'GB sign Player', 'A signing remains visible.')
        inbox_digest.consolidate(league, set())
        self.assertEqual({m['subject'] for m in league.inbox}, {'Trades', 'GB sign Player'})
        reloaded = League.load(league.save()).inbox
        saved = next(m for m in reloaded if m['subject'] == 'Trades')
        sections = IB.mail_layout(saved)['mail_sections']
        self.assertEqual([s.get('team') for s in sections[:4]], ['GB', 'MIN', 'KC', 'BUF'])
        self.assertEqual(sections[0]['trade_group'], sections[1]['trade_group'])
        self.assertNotEqual(sections[0]['trade_group'], sections[2]['trade_group'])
        self.assertEqual(len(sections[1]['rows']), 2)
        self.assertNotIn('make a trade', saved['body'])
        self.assertIn('A signing remains visible.', next(m for m in reloaded if m['subject'] == 'GB sign Player')['body'])

    def test_one_for_one_offer_has_both_teams_and_player_links(self):
        league=fixture(); league.user_team='GB'
        player(league,'a'); player(league,'b')
        msg=IB.post_trade_offer(league,'MIN','GB',['a'],['b'],'Roster upgrade.',7)
        layout=IB.mail_layout(msg)
        self.assertEqual(layout['mail_layout'],'trade')
        sections=layout['mail_sections']
        self.assertEqual([x['team'] for x in sections],['MIN','GB'])
        self.assertEqual([x['rows'][0][0]['mentions'][0]['id'] for x in sections],['b','a'])

    def test_saved_one_for_one_completion_is_split_without_mutating_mail(self):
        msg=dict(kind='trade_done',body='You send Alex Smith (WR) to MIN for Ben Jones (CB).',payload={},entities=[])
        original=copy.deepcopy(msg)
        layout=IB.mail_layout(msg)
        self.assertEqual(layout['mail_layout'],'trade')
        self.assertEqual([x['rows'][0][0]['text'] for x in layout['mail_sections']],['Alex Smith (WR)','Ben Jones (CB)'])
        self.assertEqual(msg,original)

    def test_saved_mixed_transaction_email_splits_on_reconcile(self):
        league = fixture()
        sections = IB.trade_sections('GB', 'MIN', ['Player A (WR, 80)'], ['2031 R1'])
        sections.append(IB.mail_section('Extensions', [['DAL extend Player B']]))
        old = IB.post(league, 'league', 'League Transactions', '',
                      payload={'mail_sections':sections})
        old['status'] = 'read'
        loaded = League.load(league.save())
        IB.reconcile(loaded)
        self.assertEqual({m['subject'] for m in loaded.inbox}, {'Trades', 'Extensions'})
        self.assertTrue(all(m['status'] == 'read' for m in loaded.inbox))
        reloaded = League.load(loaded.save())
        IB.reconcile(reloaded)
        self.assertEqual(len(reloaded.inbox), 2)

    def test_completed_cpu_trade_keeps_received_sides_and_links_after_reload(self):
        from league import DraftPick
        from cap_engine import Contract
        league=fixture(); league.user_team='KC'
        a=player(league,'a','GB',Contract(1,[2]))
        b=player(league,'b','MIN',Contract(1,[2]))
        a.name=b.name='Mike Smith'
        pick=DraftPick(2027,1,'GB','GB'); league.teams['GB'].picks.append(pick)
        league.trade('GB','MIN',['a',pick],['b'])
        saved=League.load(league.save())
        msg=saved.inbox[-1]; layout=IB.mail_layout(msg)
        self.assertEqual(layout['mail_layout'],'trade')
        gb, mn=layout['mail_sections']
        self.assertEqual((gb['team'],mn['team']),('GB','MIN'))
        self.assertEqual(gb['rows'][0][0]['mentions'][0]['id'],'b')
        self.assertEqual(mn['rows'][0][0]['mentions'][0]['id'],'a')
        self.assertEqual(len(mn['rows']),2)
        from views import draft_year
        self.assertIn(f'{draft_year(pick.year)} first-round pick',mn['rows'][1][0]['text'])
        self.assertFalse(IB.is_decision(msg))

    def test_small_cpu_trades_join_one_advance_digest(self):
        import inbox_digest
        from cap_engine import Contract
        league=fixture(); league.user_team='KC'
        for pid,team in [('a','GB'),('b','MIN'),('c','GB'),('d','MIN')]:
            p=player(league,pid,team,Contract(2,[2,2]))
            self.assertLess(p.ovr,85)
        league.trade('GB','MIN',['a'],['b'])
        league.trade('GB','MIN',['c'],['d'])
        inbox_digest.consolidate(league,set())
        self.assertEqual(len(league.inbox),1)
        saved=League.load(league.save()).inbox[0]
        sections=IB.mail_layout(saved)['mail_sections']
        self.assertEqual(len(sections),4)
        self.assertEqual(len({s['trade_group'] for s in sections}),2)
        ids={m['id'] for s in sections for r in s['rows'] for cell in r for m in cell['mentions']}
        self.assertEqual(ids,{'a','b','c','d'})

    def test_signings_extensions_and_tags_get_separate_advance_emails(self):
        import inbox_digest
        from cap_engine import Contract
        league=fixture(); league.user_team='KC'
        for pid in ('a','b','c'):
            p=player(league,pid,'GB',Contract(2,[2,2]))
            self.assertLess(p.ovr,85)
        league.transactions=[dict(kind=k,team='GB',pid=pid,years=2,apy=2.,price=2.)
                             for k,pid in [('sign','a'),('extension','b'),('franchise_tag','c')]]
        LN.transactions(league,1)
        IB.news(league,'Free agency, round 1: signings','Round signings.')
        inbox_digest.consolidate(league,set())
        self.assertEqual({m['subject'] for m in league.inbox},
                         {'Signings', 'GB extend b', 'GB tag c'})
        self.assertIn('Round signings.', next(m for m in league.inbox if m['subject'] == 'Signings')['body'])
        self.assertIn('extend', next(m for m in league.inbox if m['subject'] == 'GB extend b')['body'])
        self.assertIn('tag', next(m for m in league.inbox if m['subject'] == 'GB tag c')['body'])

    def test_old_cpu_trade_renders_sections_without_rewriting_mail(self):
        league=fixture(); a=player(league,'a'); a.name='Mike Smith'
        msg=IB.news(league,'GB and MIN make a trade',
            'GB send Mike Smith (QB, 85), a 2027 first-round pick to MIN for a 2028 second-round pick.')
        before=copy.deepcopy(msg)
        layout=IB.mail_layout(msg)
        gb, mn=layout['mail_sections']
        self.assertEqual(gb['rows'][0][0]['text'],'a 2028 second-round pick')
        self.assertEqual(len(mn['rows']),2)
        self.assertEqual(mn['rows'][0][0]['mentions'][0]['id'],'a')
        self.assertEqual(msg,before)
        msg['body']='An unexpected legacy format.'
        self.assertNotIn('mail_sections',IB.mail_layout(msg))

    def test_old_regression_hides_loss_column_without_mutating_save(self):
        league=fixture(); a=player(league,'a')
        msg=IB.post(league,'club','What age took','Summary',payload=dict(link='club:regression',
            mail_sections=[IB.mail_section('Regression',[[IB.player_name(a),'QB','-1.2']],['Player','Position','OVR lost'])]))
        before=copy.deepcopy(msg)
        section=IB.mail_layout(msg)['mail_sections'][0]
        self.assertEqual(section['columns'],['Player','Position'])
        self.assertEqual(len(section['rows'][0]),2)
        self.assertEqual(section['rows'][0][0]['mentions'][0]['id'],'a')
        self.assertEqual(msg,before)

    def test_new_regression_email_has_only_player_and_position(self):
        import ast
        from pathlib import Path
        league=fixture(); p=player(league,'a')
        league.regression={str(league.year):{'a':{'lost':1.2}}}
        tree=ast.parse(Path('session.py').read_text(encoding='utf-8'))
        method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='step_retire')
        report=next(n for n in method.body if isinstance(n,ast.Try))
        env=dict(self=NS(L=league,rng=None,user_team='GB'),IB=IB,inbox_player=IB.player_name,
                 RG=NS(run=lambda *a,**k:None))
        exec(compile(ast.Module(body=[report],type_ignores=[]),'regression-email','exec'),env)
        section=league.inbox[-1]['payload']['mail_sections'][0]
        self.assertEqual(section['columns'],['Player','Position'])
        self.assertEqual(len(section['rows'][0]),2)

    def test_structured_cells_keep_namesake_ids_and_utf16_offsets_after_load(self):
        league = fixture()
        a, b = player(league, 'a'), player(league, 'b')
        a.name = b.name = 'Mike Smith'
        sections = [IB.mail_section('Signings', [[IB.player_name(a), '$10.5m'],
                                               ['🏈 ' + IB.player_name(b), '$2.0m']], ['Player', 'Annual salary'])]
        original = copy.deepcopy(sections)
        msg = IB.post(league, 'league', 'Signings', 'Two players signed.', payload={'mail_sections': sections})
        self.assertEqual(sections, original)
        self.assertNotIn('\x1e', str(league.save()))
        restored = League.load(league.save()).inbox[-1]
        rows = restored['payload']['mail_sections'][0]['rows']
        self.assertEqual(rows[0][0]['mentions'][0]['id'], 'a')
        self.assertEqual(rows[1][0]['mentions'][0]['id'], 'b')
        self.assertEqual(rows[1][0]['mentions'][0]['start'], 3)
        self.assertIn('Mike Smith | $10.5m', restored['body'])
        self.assertEqual(msg['mentions'], restored['mentions'])

    def test_short_prose_stays_unchanged(self):
        league = fixture()
        body = 'Your claim was awarded. He is on your roster.'
        msg = IB.post(league, 'waiver_notice', 'Claim awarded', body)
        self.assertEqual(msg['body'], body)
        self.assertNotIn('mail_sections', msg['payload'])

    def test_all_pro_lists_separate_teams_and_rows(self):
        league = fixture(); league.user_team = 'GB'
        a, b = player(league, 'a'), player(league, 'b')
        LN.season_end(league, {'all_pro_1': [a], 'all_pro_2': [b]})
        msg = next(m for m in league.inbox if 'All-Pro' in m['subject'])
        first, second = msg['payload']['mail_sections']
        self.assertEqual([first['title'], second['title']], ['First team', 'Second team'])
        self.assertEqual(first['rows'][0][0]['mentions'][0]['id'], 'a')
        self.assertEqual(second['rows'][0][0]['mentions'][0]['id'], 'b')

    def test_multi_asset_offer_keeps_direction_and_action_payload(self):
        league = fixture(); league.user_team = 'GB'
        a, b, c = [player(league, x) for x in ['a', 'b', 'c']]
        msg = IB.post_trade_offer(league, 'MIN', 'GB', ['a', 'b'], ['c'], 'We need a receiver.', 7)
        send, receive = msg['payload']['mail_sections']
        self.assertEqual(send['rows'][0][0]['mentions'][0]['id'], 'c')
        self.assertEqual([row[0]['mentions'][0]['id'] for row in receive['rows']], ['a', 'b'])
        self.assertEqual(msg['payload']['sends'], ['a', 'b'])
        self.assertEqual(msg['payload']['gets'], ['c'])
        self.assertEqual(msg['expires_week'], 7)
        self.assertTrue(IB.is_decision(msg))

    def test_public_message_exposes_sections(self):
        from session import Session
        league = fixture(); league.user_team = 'GB'
        msg = IB.post(league, 'league', 'Digest', 'Summary', payload={'mail_sections': [IB.mail_section('Rows', ['A', 'B'])]})
        with patch.object(IB, 'reconcile'):
            view = Session.inbox_message(NS(L=league), msg['id'])
        self.assertEqual(view['mail_sections'], msg['payload']['mail_sections'])
        self.assertEqual(view['mail_intro']['text'], 'Summary')

    def test_fa_digest_aligns_terms_and_keeps_ratings(self):
        from session import Session
        league = fixture(); league.user_team = 'GB'
        p = player(league, 'a')
        offer = NS(years=3, apy=15.5)
        with patch('market.resolve_round', return_value=([('MIN', p, offer)], ['b'], [])):
            Session._fa_round(NS(L=league, rng=None, user_team='GB'), 2)
        section = league.inbox[-1]['payload']['mail_sections'][0]
        row = section['rows'][0]
        self.assertEqual(len(row), len(section['columns']))
        self.assertEqual([c['text'] for c in row][1:], [p.pos, str(round(p.ovr)), 'MIN', '3', '$15.5m'])

    def test_retention_groups_keep_prices_and_all_players(self):
        from session import Session
        league = fixture(); league.user_team = 'GB'
        p = player(league, 'a')
        row = dict(pid='a', name=p.name, pos=p.pos, ovr=80)
        sheet = dict(ufa=[dict(row, tag_price=18.5)], rfa=[dict(row, tender_price=3.2)], room=20)
        with patch('tags.user_resign_sheet', return_value=sheet):
            Session._resign_card(NS(L=league))
        sections = league.inbox[-1]['payload']['mail_sections']
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[0]['rows'][0][-1]['text'], '$18.5m')
        self.assertEqual(sections[1]['rows'][0][-1]['text'], '$3.2m')
        self.assertIn('Before advancing', sections[2]['title'])

    def test_injury_decision_has_readable_labels_and_player_links(self):
        import injury_status as IS
        league = fixture()
        p = player(league, 'a'); backup = player(league, 'b')
        p.name = 'Alex Starter'; backup.name = 'Ben Backup'
        backup.out_until = None
        p.xp_spent['_inj_kind'] = 'Ankle'
        team = NS(depth={p.pos: [p, backup]})
        text = IS.hurt_words(league, team, p, 'questionable', mentions=True)
        msg = IB.post(league, 'injury_decision', 'Play or sit?', text)
        rows = IB.body_rows(league, msg)
        self.assertEqual(len(rows), 4)
        self.assertEqual([row.split(':')[0] for row in rows], ['Status', 'On-field impact', 'Risk', 'Recommendation'])
        self.assertEqual([r['id'] for r in msg['mentions']['body']], ['a', 'b'])


if __name__ == '__main__': unittest.main()

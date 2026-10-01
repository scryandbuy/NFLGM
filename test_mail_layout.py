import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import inbox as IB
import league_notes as LN
from league import League
from test_cap_accounting import fixture, player


class MailLayoutTests(unittest.TestCase):
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
        sheet = dict(ufa=[dict(row, tag_price=18.5)], rfa=[dict(row, tender_price=3.2)], erfa=[row], room=20)
        with patch('tags.user_resign_sheet', return_value=sheet):
            Session._resign_card(NS(L=league))
        sections = league.inbox[-1]['payload']['mail_sections']
        self.assertEqual(len(sections), 4)
        self.assertEqual(sections[0]['rows'][0][-1]['text'], '$18.5m')
        self.assertEqual(sections[1]['rows'][0][-1]['text'], '$3.2m')
        self.assertIn('Exclusive rights', sections[2]['title'])

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

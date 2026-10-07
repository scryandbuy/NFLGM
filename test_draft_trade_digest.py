import unittest
from types import SimpleNamespace as N
import inbox as IB
import inbox_digest as D

class DraftDigest(unittest.TestCase):
    def setUp(self):
        self.L=N(year=2032,week=22,phase='free_agency',inbox=[],players={},teams={},league_notes_sent={'_draft_trade_mail_active':2031})
    def trade(self,team='MIN',kind='league'):
        return IB.post(self.L,kind,f'GB and {team} make a trade','',payload=dict(mail_layout='trade',mail_sections=IB.trade_sections('GB',team,['2032 first-round pick'],['2032 second-round pick','2033 first-round pick'])))
    def test_separate_clicks_and_user_trade_share_one_mail(self):
        first=self.trade();first['status']='open'
        before={first['id']}
        self.trade('PIT','trade_done');D.consolidate(self.L,before)
        self.assertEqual(len(self.L.inbox),1)
        self.assertEqual(first['subject'],'Draft Day Trades')
        self.assertEqual(first['status'],'unread')
        sections=first['payload']['mail_sections']
        self.assertEqual(len(sections),4)
        self.assertEqual(len({s['trade_group'] for s in sections}),2)
        self.assertEqual([s['team'] for s in sections],['GB','MIN','GB','PIT'])
    def test_after_draft_and_decisions_stay_separate(self):
        self.trade()
        IB.post(self.L,'trade_offer','Trade offer','Decision')
        self.L.league_notes_sent.pop('_draft_trade_mail_active')
        self.trade('PIT')
        self.assertEqual(len(self.L.inbox),3)
        self.assertEqual(self.L.inbox[1]['kind'],'trade_offer')
    def test_another_draft_gets_new_mail(self):
        self.trade();self.L.league_notes_sent['_draft_trade_mail_active']=2032
        self.trade('PIT');self.assertEqual(len(self.L.inbox),2)

if __name__=='__main__':unittest.main()

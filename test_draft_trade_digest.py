import unittest
from types import SimpleNamespace as N
import inbox as IB
import inbox_digest as D

class DraftDigest(unittest.TestCase):
    def setUp(self):
        self.L=N(year=2032,week=22,phase='free_agency',inbox=[],players={},teams={},league_notes_sent={'_draft_trade_mail_active':2031})
    def trade(self,team='MIN',kind='league'):
        return IB.post(self.L,kind,f'GB and {team} make a trade','',payload=dict(mail_layout='trade',mail_sections=IB.trade_sections('GB',team,['2032 first-round pick'],['2032 second-round pick','2033 first-round pick'])))
    def finish(self):
        from draft_day import Draft
        self.L.draft_pool=[];self.L.free_agents=[]
        d=Draft.__new__(Draft);d.L=self.L;d.year=2031;d.taken=set()
        d._finish()

    def test_delivered_only_at_draft_end_once(self):
        self.trade();self.trade('PIT','trade_done');D.consolidate(self.L,set())
        self.assertEqual(self.L.inbox,[])
        self.finish();self.finish()
        self.assertEqual(len(self.L.inbox),1)
        first=self.L.inbox[0]
        self.assertEqual(first['subject'],'Draft Day Trades')
        sections=first['payload']['mail_sections']
        self.assertEqual(len(sections),4)
        self.assertEqual(len({s['trade_group'] for s in sections}),2)
        self.assertEqual([s['team'] for s in sections],['GB','MIN','GB','PIT'])

    def test_queue_survives_serialization(self):
        import json
        self.trade()
        self.L.league_notes_sent=json.loads(json.dumps(self.L.league_notes_sent))
        self.trade('PIT');self.finish()
        self.assertEqual(len(self.L.inbox[0]['payload']['mail_sections']),4)

    def test_after_draft_and_decisions_stay_separate(self):
        self.trade();IB.post(self.L,'trade_offer','Trade offer','Decision')
        self.assertEqual(len(self.L.inbox),1)
        self.finish();self.trade('PIT')
        self.assertEqual(len(self.L.inbox),3)
        self.assertEqual(self.L.inbox[0]['kind'],'trade_offer')

    def test_no_trades_no_email(self):
        self.finish();self.assertEqual(self.L.inbox,[])

if __name__=='__main__':unittest.main()

import unittest
import inbox as IB
class TransactionTables(unittest.TestCase):
 def test_saved_and_new_terms_preserve_snapshot_and_link(self):
  for terms in ['2 years at $6.17m a year ($8.24m for the rest of this season)', 'a 2-year deal averaging $6.17m per year']:
   m=dict(kind='league',body=f'DAL sign Simeon Harris (CB, 82) for {terms}.',entities=[dict(kind='player',id='C1364',name='Simeon Harris')])
   row=IB.mail_layout(m)['mail_sections'][0]['rows'][0]
   self.assertEqual([c['text'] for c in row],['DAL','Simeon Harris','CB','82','2','—'])
   self.assertEqual(row[1]['mentions'][0]['id'],'C1364')
 def test_saved_digest_combines_rows_and_keeps_other_news(self):
  lines=['DAL sign Simeon Harris (CB, 82) for 2 years at $6.17m a year.', 'CAR sign Kelley Jones (CB, 81) for 1 year at $5.10m a year.', 'SF extend Mykel Williams (REDG, 85) for 4 years at $31.01m a year.', 'Other important news.']
  m=dict(kind='league',payload=dict(mail_sections=[dict(title='',columns=[],rows=[[dict(text=t,mentions=[])] for t in lines])]))
  sections=IB.mail_layout(m)['mail_sections']
  self.assertEqual([len(s['rows']) for s in sections],[2,1,1])
  self.assertEqual(sections[1]['title'],'Extensions')
  self.assertEqual(sections[2]['rows'][0][0]['text'],lines[-1])
 def test_nonmatching_mail_unchanged(self):
  m=dict(kind='league',body='Something else.',payload=dict(link='league'))
  self.assertEqual(IB.mail_layout(m),m['payload'])
 def test_signing_uses_recorded_cap_not_average_or_current_contract(self):
  from types import SimpleNamespace as NS
  from unittest.mock import patch
  import league_notes as LN
  player=NS(pid='P1',name='Test Player',pos='HB',ovr=80,team='SF')
  league=NS(year=2031,user_team='GB',transactions=[dict(kind='sign',team='SF',pid='P1',year=2031,years=2,apy=7.05,cap_hit_this_season=4.12)],player=lambda pid:player)
  with patch.object(LN,'_ledger',return_value={}), patch.object(LN,'inbox_player',return_value='Test Player'), patch.object(LN.IB,'news') as news:
   LN.transactions(league,5)
  section=news.call_args.kwargs['payload']['mail_sections'][0]
  self.assertEqual(section['columns'][-1],'2031 Cap Hit')
  self.assertEqual(section['rows'][0][-1],'$4.12m')
 def test_old_structured_average_is_not_mislabeled_as_cap(self):
  m=dict(kind='league',year=2031,payload=dict(mail_sections=[dict(title='Signings',columns=['Team','Player','Pos','OVR','Years','Annual Average'],rows=[['SF','Player','HB','80','1','$2.38m']])]))
  section=IB.mail_layout(m)['mail_sections'][0]
  self.assertEqual(section['columns'][-1],'2031 Cap Hit')
  self.assertEqual(section['rows'][0][-1]['text'],'—')
if __name__=='__main__':unittest.main()

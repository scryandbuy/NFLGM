import unittest
import inbox as IB
class TransactionTables(unittest.TestCase):
 def test_saved_and_new_terms_preserve_snapshot_and_link(self):
  for terms in ['2 years at $6.17m a year ($8.24m for the rest of this season)', 'a 2-year deal averaging $6.17m per year']:
   m=dict(kind='league',body=f'DAL sign Simeon Harris (CB, 82) for {terms}.',entities=[dict(kind='player',id='C1364',name='Simeon Harris')])
   row=IB.mail_layout(m)['mail_sections'][0]['rows'][0]
   self.assertEqual([c['text'] for c in row],['DAL','Simeon Harris','CB','82','2','$6.17m'])
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
if __name__=='__main__':unittest.main()

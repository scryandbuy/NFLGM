import unittest
import inbox as IB
class RosterUpdateTables(unittest.TestCase):
 def layout(self,kind,body,subject=''):
  return IB.mail_layout(dict(kind=kind,body=body,subject=subject,entities=[dict(kind='player',id='p1',name='Test Player')]))['mail_sections']
 def test_injury_preserves_absence_and_depth_warning(self):
  sections=self.layout('injury','Test Player (CB) is out 3 weeks (ankle); there is nobody behind him at the spot.\nThe depth chart has been updated.')
  row=sections[0]['rows'][0]
  self.assertEqual(row[3]['text'],'3 weeks')
  self.assertIn('nobody behind',row[2]['text'])
  self.assertEqual(row[0]['mentions'][0]['id'],'p1')
  self.assertEqual(sections[1]['rows'][0][0]['text'],'The depth chart has been updated.')
 def test_recovery_and_ir_details(self):
  self.assertEqual(self.layout('injury','Test Player (CB) is back from his injury and available at CB.')[0]['rows'][0][3]['text'],'Available')
  detail='has served his 4 weeks on injured reserve and is healthy. He can be activated. The club has 2 returns left.'
  self.assertEqual(self.layout('ir_ready','Test Player (CB, 80 overall) '+detail)[0]['rows'][0][2]['text'],detail)
 def test_saved_multiline_digest(self):
  body='Test Player (CB) is out 3 weeks (ankle).\nSecond Player (WR) is out for the season (knee).'
  m=dict(kind='club',subject='Injury Update',payload=dict(mail_sections=[dict(title='',columns=[],rows=[[dict(text=body,mentions=[])]])]))
  sections=IB.mail_layout(m)['mail_sections']
  self.assertEqual(len(sections[0]['rows']),2)
  self.assertEqual(sections[0]['rows'][1][3]['text'],'the season')
 def test_waiver_outcomes(self):
  cases=[('You were awarded Test Player (CB, 80) off waivers from DAL. He is on your roster with his contract, $3.0m a year.','Awarded'),('You claimed Test Player (CB) and DAL held the higher priority. He is theirs.','Claim lost'),('Test Player (CB) was signed by DAL before the wire cleared. Your claim did not go through.','Claim void'),('You waived Test Player for the practice squad and DAL claimed him off the wire. He is theirs.','Claimed'),('Test Player cleared waivers and is on your practice squad.','Cleared'),('Test Player cleared waivers but the squad had no room for him under its rules; he is a free agent.','Cleared')]
  for body,outcome in cases:
   with self.subTest(outcome=outcome):self.assertEqual(self.layout('waiver_notice',body)[0]['rows'][0][2]['text'],outcome)
  self.assertEqual(self.layout('waiver_notice','The inherited contract does not fit under your cap.','Claim failed: Test Player')[0]['rows'][0][0]['text'],'Test Player')
 def test_franchise_tag_and_unknown_text(self):
  sections=self.layout('league','DAL place the franchise tag on Test Player (CB, 80) at $20.0m.\nUnrelated news.')
  self.assertEqual([c['text'] for c in sections[0]['rows'][0]],['DAL','Test Player','CB','$20.0m'])
  self.assertEqual(sections[1]['rows'][0][0]['text'],'Unrelated news.')
if __name__=='__main__':unittest.main()

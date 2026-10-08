import copy
import unittest
from types import SimpleNamespace
import inbox
import views

class InboxPreview(unittest.TestCase):
    def test_structured_snapshot_wins_over_stale_prose(self):
        m=dict(id=1,kind='league',subject='PIT sign Michael Pittman',
            body='PIT sign Michael Pittman for $6.49m per year.',
            payload=dict(mail_intro=dict(text=''),mail_sections=[dict(title='Signings',
                columns=['Team','Player','Pos','OVR','Years','2032 Cap Hit'],
                rows=[[dict(text=v) for v in ['PIT','Michael Pittman','WR','83','1','$3.80m']]])]))
        before=copy.deepcopy(m)
        result=inbox.preview_text(m)
        self.assertIn('2032 Cap Hit: $3.80m',result)
        self.assertNotIn('6.49',result)
        self.assertEqual(m,before)
        row=views._inbox(SimpleNamespace(inbox=[m]))['rows'][0]
        self.assertEqual(row['body'],result)

    def test_plain_mail_and_word_boundary(self):
        m=dict(kind='club',body='One sentence. Another sentence with detail.',payload={})
        self.assertEqual(inbox.preview_text(m,None),m['body'])
        self.assertEqual(inbox.preview_text(m,20),'One sentence.…')

    def test_non_table_sections_and_intro(self):
        m=dict(kind='club',body='Old copy',payload=dict(mail_intro=dict(text='New report.'),
            mail_sections=[dict(title='Players',rows=[[dict(text='Player improved.')]])]))
        self.assertEqual(inbox.preview_text(m),'New report. Player improved.')

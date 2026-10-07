import copy
import unittest
from types import SimpleNamespace as N
import inbox as IB
import inbox_digest as D

class SigningMailDuplicates(unittest.TestCase):
    def setUp(self):
        self.L=N(year=2032,week=2,phase='regular',inbox=[],players={},teams={})
        self.cols=['Team','Player','Pos','OVR','Years','2032 Cap Hit']
    def post(self,team,name,cap):
        body=f'{team} sign {name} (CB, 79) for 1 year at $9.00m a year.'
        return IB.post(self.L,'league',body,body,payload=dict(mail_sections=[IB.mail_section('Signings',[[team,name,'CB','79','1',cap]],self.cols)]))
    def test_new_digest_has_one_row_per_signing_and_cap(self):
        self.post('DET','A','$8.63m');self.post('WAS','B','$10.03m');self.post('TEN','C','$9.88m')
        D.consolidate(self.L,set())
        layout=IB.mail_layout(self.L.inbox[0])
        self.assertEqual(len(layout['mail_sections']),1)
        rows=layout['mail_sections'][0]['rows']
        self.assertEqual(len(rows),3)
        self.assertEqual([r[-1]['text'] for r in rows],['$8.63m','$10.03m','$9.88m'])
    def test_saved_duplicate_tables_repaired_without_mutation(self):
        m=self.post('DET','A','$8.63m')
        missing=copy.deepcopy(m['payload']['mail_sections'][0]);missing['rows'][0][-1]['text']='—'
        m['payload']['mail_sections'].insert(0,missing)
        before=copy.deepcopy(m)
        layout=IB.mail_layout(m)
        self.assertEqual(len(layout['mail_sections']),1)
        self.assertEqual(len(layout['mail_sections'][0]['rows']),1)
        self.assertEqual(layout['mail_sections'][0]['rows'][0][-1]['text'],'$8.63m')
        self.assertEqual(m,before)
    def test_different_cap_terms_not_silently_deduplicated(self):
        m=self.post('DET','A','$8.63m');second=copy.deepcopy(m['payload']['mail_sections'][0])
        second['rows'][0][-1]['text']='$10m';m['payload']['mail_sections'].append(second)
        self.assertEqual(len(IB.mail_layout(m)['mail_sections'][0]['rows']),2)

if __name__=='__main__':unittest.main()

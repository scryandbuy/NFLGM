import unittest
from types import SimpleNamespace as NS
import inbox as IB
import inbox_digest as D

class AdvanceDigests(unittest.TestCase):
    def setUp(self):
        self.L=NS(year=2030,week=4,phase='regular',inbox=[],players={},teams={},user_team='GB')
    def post(self,subject,kind='league',payload=None):
        return IB.post(self.L,kind,subject,subject,sender='league',payload=payload)
    def test_separate_advances_same_week_preserve_old_digest(self):
        for n in range(2):
            before={m['id'] for m in self.L.inbox}
            self.post('GB and PIT make a trade')
            self.post('MIN and CAR make a trade')
            D.consolidate(self.L,before)
            self.assertEqual(len(self.L.inbox),n+1)
        self.assertTrue(all(m['subject']=='League Transactions' for m in self.L.inbox))
    def test_decisions_and_existing_mail_untouched(self):
        old=self.post('Old')
        offer=self.post('Trade offer',kind='trade_offer')
        self.post('Claim lost: A',kind='waiver_notice')
        self.post('Claim awarded: B',kind='waiver_notice')
        D.consolidate(self.L,{old['id']})
        self.assertIn(old,self.L.inbox); self.assertIn(offer,self.L.inbox)
        self.assertEqual(len(self.L.inbox),3)
    def test_trade_sides_preserved(self):
        for team in ('PIT','MIN'):
            self.post(f'GB and {team} make a trade',payload={'mail_layout':'trade','mail_sections':IB.trade_sections('GB',team,['Player A'],['2031 R1'])})
        D.consolidate(self.L,set())
        sections=self.L.inbox[0]['payload']['mail_sections']
        self.assertEqual(len(sections),6) # each original intro and both sides
        self.assertIn('2031 R1',self.L.inbox[0]['body'])
    def test_advance_boundary_calls_consolidation(self):
        from session import Session
        def advance():
            self.post('A cleared to play','injury'); self.post('B cleared to play','injury')
            return {'done':'Advanced'}
        fake=NS(L=self.L,_advance_once=advance)
        self.assertEqual(Session.advance(fake),{'done':'Advanced'})
        self.assertEqual(len(self.L.inbox),1)
        self.assertEqual(self.L.inbox[0]['subject'],'Injury Update')

    def test_contract_digest_stays_open_until_all_deals_resolve(self):
        self.L.players = {pid:NS(pid=pid,team='GB',retired=False,contract=NS(years=1)) for pid in ('a','b')}
        self.L.player = lambda pid:self.L.players.get(pid)
        for pid in ('a','b'):
            self.post(pid + ' enters his final year', 'contract_year', {'pid':pid})
        D.consolidate(self.L,set())
        message=self.L.inbox[0]
        IB.reconcile(self.L)
        self.assertTrue(IB.is_decision(message))
        self.L.players['a'].contract.years=3
        IB.reconcile(self.L)
        self.assertTrue(IB.is_decision(message))
        self.L.players['b'].contract.years=3
        IB.reconcile(self.L)
        self.assertFalse(IB.is_decision(message))

    def test_saved_final_year_notices_keep_contract_snapshots_in_one_table(self):
        for name, ovr, salary in (('Avery Stone', 84, 14.5), ('Riley Cole', 78, 8.2)):
            IB.post(self.L, 'contract_year', f'{name} enters his final year',
                    f'{name} (WR, {ovr}, age 27) is in the last year of his deal at ${salary:.1f}m. '
                    'He can be extended now; his agent will price him at the market.',
                    sender='GB', payload={'link': 'player:old-save'})
        D.consolidate(self.L, set())
        self.assertEqual(len(self.L.inbox), 1)
        layout = IB.mail_layout(self.L.inbox[0])
        self.assertEqual(len(layout['mail_sections']), 1)
        section = layout['mail_sections'][0]
        self.assertEqual(section['columns'], ['Player', 'Pos', 'OVR', 'Age', 'Annual Salary'])
        self.assertEqual([[cell['text'] for cell in row] for row in section['rows']],
                         [['Avery Stone', 'WR', '84', '27', '$14.5m'],
                          ['Riley Cole', 'WR', '78', '27', '$8.2m']])

if __name__=='__main__': unittest.main()

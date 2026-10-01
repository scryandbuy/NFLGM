import unittest
from unittest.mock import patch
from test_roster_advisor import fixture, player, row
from cap_engine import Contract
from league import League
import roster_advisor as RA
import inbox as IB


class ValueTests(unittest.TestCase):
    def test_full_young_room_rejects_redundant_rare(self):
        L=fixture(); t=L.teams['GB']
        t.roster=[p for p in t.roster if p.pos!='HB']
        for pid,grade,age in [('starter',89,25),('rookie',80,21),('reserve',72,22)]:
            p=player(pid,'HB',grade,'GB','star');p.age=age;p.contract=Contract(4,[1]*4)
            t.roster.append(p);L.players[pid]=p
        target=player('target','HB',84,None,'star');L.players[target.pid]=target
        L.free_agents=[target.pid]
        self.assertIsNone(RA.development_case(L,t,target,t.roster))
        with patch.object(RA,'_terms',return_value=(Contract(1,[1]),'Cheap')):
            self.assertNotIn(target.pid,[r['pid'] for r in RA.candidates(L,4)])

    def test_exceptional_rotation_prospect_and_unfilled_succession(self):
        L=fixture();t=L.teams['GB'];target=player('prospect','HB',83,None,'superstar')
        self.assertIsNotNone(RA.development_case(L,t,target,t.roster))
        target.dev='star';starter=L.player('GB-HB-0');starter.age=31
        self.assertIsNotNone(RA.development_case(L,t,target,t.roster))
        reserve=L.player('GB-HB-1');reserve.dev='star';reserve.age=21
        self.assertIsNone(RA.development_case(L,t,target,t.roster))

    def test_actual_pick_and_contract_change_hurdle(self):
        c=Contract(2,[1,1]);rental=Contract(1,[1])
        self.assertGreater(RA.investment_hurdle('trade',c,{'round':4},300),RA.investment_hurdle('trade',c,{'round':7},300))
        self.assertGreater(RA.investment_hurdle('trade',rental,{'round':4},300),RA.investment_hurdle('trade',c,{'round':4},300))

    def test_full_report_survives_real_save_reload(self):
        L=fixture();recommendation=row('GB-HB-0',pick={'round':4,'label':'Fourth'},release='GB-HB-1',dismissed=True)
        IB.post(L,'roster_report','Report','Body',payload={'recommendations':[recommendation]})
        restored=League.load(L.save())
        self.assertEqual(restored.inbox[-1]['payload']['recommendations'],[recommendation])
        restored.user_team='GB'
        self.assertEqual(RA.recommendations(restored,restored.inbox[-1])[0]['status'],'Dismissed')

    def test_damaged_legacy_report_is_safe(self):
        L=fixture();m=IB.post(L,'roster_report','Report','Body',payload={'recommendations':['GB-HB-0']})
        self.assertEqual(RA.recommendations(L,m),[])
        self.assertFalse(RA.dismiss(L,m['id'],'GB-HB-0')['ok'])

if __name__=='__main__':unittest.main()

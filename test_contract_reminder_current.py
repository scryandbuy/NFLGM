import unittest
from types import SimpleNamespace as N
from test_inbox_entity_lifecycle import league
import inbox as IB
import views
class ContractReminder(unittest.TestCase):
 def test_traded_and_extended_players_removed_from_open_digest(self):
  def player(pid,team,years):
   return N(pid=pid,name=pid,pos='TE',ovr=83,age=30,apy=10,team=team,retired=False,contract=N(years=years),fa_class='signed')
  players={p.pid:p for p in [player('Kraft','SF',1),player('Golden','GB',1),player('Extended','GB',3)]}
  L=league(players=players,teams={'GB':N(), 'SF':N()})
  m=IB.post(L,'contract_year','Expiring Contracts','Old body Kraft',payload=dict(digest_pids=list(players)))
  IB.reconcile(L)
  self.assertEqual(m['payload']['digest_pids'],['Golden'])
  self.assertNotIn('Kraft',m['body'])
  self.assertEqual(m['payload']['mail_sections'][0]['rows'][0][0]['text'],'Golden')
  self.assertEqual(views._desk(L,'GB')[0]['body'],'Golden: expiring contracts to review.')
  players['Golden'].team='SF';IB.reconcile(L)
  self.assertFalse(IB.is_decision(m))
if __name__=='__main__':unittest.main()

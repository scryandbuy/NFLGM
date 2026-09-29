import unittest
from types import SimpleNamespace
from unittest.mock import patch
import views, views_gameplan as VG, gameplan_week as GW
class OverviewTests(unittest.TestCase):
 def test_desk_keeps_all_and_prioritizes_blockers(self):
  msgs=[dict(id=i,kind='contract_year',status='open',subject='Contract',body='',payload={}) for i in range(1,7)]
  msgs.append(dict(id=7,kind='roster',status='unread',subject='Roster',body='',payload={}))
  with patch.object(views,'_desk_detail',return_value={}):
   result=views._desk(SimpleNamespace(inbox=msgs),'GB')
  self.assertEqual(len(result),7); self.assertEqual(result[0]['raw_kind'],'roster')
 def test_skip_survives_plan_edits_and_restore(self):
  league=SimpleNamespace(year=2026,user_week_plan=None)
  session=SimpleNamespace(stop=('week',1),_opponent=lambda w:('MIN',True))
  with patch.object(GW,'opponent_report',return_value={'suggestions':[{'text':'Run more','changes':{'pass_bias':-.05}}]}):
   self.assertTrue(VG.act_skip(session,league,'GB',0)['ok'])
   GW.set_user_plan(league,1,{'pass_bias':.1})
   self.assertEqual(VG._skipped(league,1),['Run more'])
   self.assertEqual(VG._skipped(league,2),[])
   VG.act_skip(session,league,'GB',0,False)
   self.assertEqual(VG._skipped(league,1),[])
 def test_accept_restores_skipped(self):
  league=SimpleNamespace(year=2026,user_week_plan=None)
  session=SimpleNamespace(stop=('week',1),_opponent=lambda w:('MIN',True))
  with patch.object(GW,'opponent_report',return_value={'suggestions':[{'text':'Run more','changes':{'pass_bias':-.05}}]}):
   VG.act_skip(session,league,'GB',0); VG.act_take(session,league,'GB',0)
  self.assertEqual(VG._skipped(league,1),[])
  self.assertEqual(VG._taken(league,1),['Run more'])
unittest.main()

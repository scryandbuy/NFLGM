import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import views
class PlayoffGameDay(unittest.TestCase):
 def setup_case(self,round=0):
  s=NS(stop=('playoffs',round),played=False,gameday=dict(week=18,scores=[],game=None),post_live=NS(alive={'AFC':{1:'GB'}},exit_round={}),_opponent=lambda w:None)
  return s,NS(phase='playoffs')
 def test_bye_replaces_week18(self):
  s,l=self.setup_case()
  with patch.object(views,'rail',return_value={}):v=views.gameday(s,l,'GB')
  self.assertEqual(v['week'],19);self.assertTrue(v['bye']);self.assertFalse(v['no_game']);self.assertIn('Wild Card',v['line'])
 def test_eliminated_not_bye(self):
  s,l=self.setup_case(1);s.post_live.exit_round={'GB':'WC'}
  with patch.object(views,'rail',return_value={}):v=views.gameday(s,l,'GB')
  self.assertEqual(v['week'],20);self.assertTrue(v['no_game'])
 def test_historical_and_completed_preserved(self):
  s,l=self.setup_case()
  with patch.object(views,'rail',return_value={}):v=views.gameday(s,l,'GB',gd=s.gameday)
  self.assertEqual(v['week'],18)
  s.played=True;s.gameday=dict(week=19,scores=[],game=None)
  with patch.object(views,'rail',return_value={}):v=views.gameday(s,l,'GB')
  self.assertEqual(v['week'],19);self.assertFalse(v['empty'])
 def test_playoff_matchup_preview(self):
  s,l=self.setup_case(1)
  with patch.object(views,'rail',return_value={}),patch.object(views,'_matchup',return_value={'bye':False}):v=views.gameday(s,l,'GB')
  self.assertEqual(v['week'],20);self.assertFalse(v['bye'])
if __name__=='__main__':unittest.main()

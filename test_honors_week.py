import unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
import club_notes as C
class HonorsWeek(unittest.TestCase):
 def league(self):
  p=NS(pid='rb',team='GB',name='Runner',pos='HB')
  return NS(year=2027,week=19,week_book={'rb':{'rush_yds':200}},game_stats={'2027-18-GB-CHI':{'rb':{'rush_yds':200}}},player=lambda pid:p)
 def test_bye_cannot_reuse_previous_week(self):
  l=self.league()
  with patch.object(C.IB,'post') as post:C._honors(l,NS(abbr='GB'),19)
  post.assert_not_called()
 def test_correct_week_still_awarded_and_sparse_td_safe(self):
  l=self.league();l.game_stats['2027-19-GB-CHI']={'rb':{'rush_yds':200,'rush_td':2}}
  with patch.object(C.IB,'post') as post,patch.object(C,'_once',return_value=True):C._honors(l,NS(abbr='GB'),19)
  self.assertEqual(post.call_count,1);self.assertIn('Wild Card',post.call_args.args[3]);self.assertNotIn('Week 19',post.call_args.args[3])
 def test_round_names(self):
  self.assertEqual([C._period(w) for w in range(18,23)],['Week 18','Wild Card','Divisional Round','Conference Championship','Championship Game'])
if __name__=='__main__':unittest.main()

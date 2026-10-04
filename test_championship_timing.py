import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import awards as A
from session import Session
class ChampionshipTiming(unittest.TestCase):
 def fixture(self):
  people={pid:N(pid=pid,name=pid,pos='QB',team=team) for pid,team in [('old','GB'),('final','GB')]}
  l=N(year=2028,awards={2028:{}},history={},awards_paid={},player=people.get,game_stats={'2028-2-GB-CA':{'old':{'pass_yds':999}},'2028-22-GB-CA':{'final':{'pass_yds':300,'pass_td':3}}})
  return l,N(champion='GB',games=[('SB','NFL','GB','CA',28,17)])
 def test_final_book_only(self):
  l,p=self.fixture();self.assertEqual(A.championship_game_mvp(l,p).pid,'final')
 def test_announces_and_rewards_once(self):
  l,p=self.fixture()
  with patch('xp.pay_awards') as pay,patch('morale.ensure',return_value=None),patch('inbox.post') as post,patch('inbox.player_name',side_effect=lambda p:p.name):
   A.announce_championship(l,p);A.announce_championship(l,p)
  self.assertEqual(pay.call_count,1);self.assertEqual(post.call_count,1)
  self.assertIn('final',post.call_args.args[3]);self.assertEqual(l.awards[2028]['sb_mvp'],'final')
 def test_missing_final_not_invented(self):
  l,p=self.fixture();l.game_stats.pop('2028-22-GB-CA');self.assertIsNone(A.announce_championship(l,p));self.assertFalse(l.history['2028'].get('championship_announced'))
 def test_finalize_before_firing(self):
  s=Session.__new__(Session);s.L=N(year=2028,teams={'GB':None});s.rng=None;calls=[]
  s.stop=('offseason',1);s.offseason_progress={'year':2028};s._offseason_trade_pass=lambda:None
  s.step_awards=lambda:calls.append('finalize');s.step_retire=lambda:calls.append('develop')
  def roll():calls.append('roll');s.L.year+=1
  s.step_roll=roll;s._black_monday=lambda teams,**kw:calls.append('fire') or []
  with patch('session.OC.team_context',return_value={}),patch('session.PA.offseason'),patch('session.STF.carousel',side_effect=lambda *a,**k:calls.append('hire')),patch('league_notes.coaching_summary'):
   s.step_development_roll();s.stop=('offseason',2);s._open_coaching()
  self.assertEqual(calls,['finalize','develop','roll','fire','hire'])
 def test_legacy_finalization_not_repeated(self):
  s=Session.__new__(Session);s.L=N(year=2028,history={'2028':{'awards':{'done':True}}});s.rng=None;s._recorded_votes=lambda:{'mvp':'old'}
  with patch('session.CP.season_prestige') as prestige:s.step_awards()
  prestige.assert_not_called()
if __name__=='__main__':unittest.main()

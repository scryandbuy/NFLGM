"""Return dates are the beginning of the named decision week."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import injury_status as IS
import game_availability as GA
from session import Session
from season import SeasonRunner


class InjuryReturnWeekTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = Session.new('GB', seed=23)

    def setUp(self):
        self.s = copy.deepcopy(self.base)
        self.L = self.s.L
        self.L.set_phase('regular')
        self.L.week = 9
        self.s.stop = ('week', 9)
        self.t = self.L.teams['GB']
        self.p = self.t.roster[0]
        self.p.out_until = 10
        self.t.ir = [self.p]
        self.p.xp_spent.update(_ir_week=6, _ir_return=True)
        self.t.ir_returns_used = 0

    def row(self):
        return next(r for r in self.s.club_roster()['ir'] if r['pid']==self.p.pid)

    def test_displayed_week_and_ir_action_agree_at_week_ten(self):
        self.assertFalse(self.row()['can_activate'])
        self.assertFalse(self.s.club_act('ir_activate',pid=self.p.pid)['ok'])
        self.s.stop = ('week',10)
        self.s._sync_week_health()
        self.assertEqual(self.L.week,10)
        self.assertIsNone(self.p.out_until)
        self.assertIn(self.p,self.t.ir)  # Health is separate from activation.
        self.assertTrue(self.row()['can_activate'])
        self.assertTrue(self.s.club_act('ir_activate',pid=self.p.pid)['ok'])
        self.assertIn(self.p,GA.dressed(self.t,None,10))

    def test_real_advance_opens_correct_week_without_waiting_for_practice(self):
        self.s.played = True
        runner = NS(live=None,desks={},roll_week=lambda week: None)
        self.s.runner = runner
        with patch.object(self.s,'blocking',return_value=[]), \
             patch.object(self.s,'_finish_live'), \
             patch('game_availability.settle_roster'), \
             patch('staff.resolve_references'):
            self.s.advance()
        self.assertEqual((self.s.stop,self.L.week),(('week',10),10))
        self.assertTrue(self.row()['can_activate'])
        self.assertIsNone(self.p.out_until)

    def test_loaded_week_ten_save_repairs_stale_week_and_medical_listing(self):
        self.s.stop = ('week',10)
        self.s.runner = SeasonRunner(self.L,self.s.rng)
        desk = self.s.runner.desks['GB']
        desk.status[self.p.pid] = 'questionable'
        desk.pending[self.p.pid] = 'questionable'
        self.s.runner._listed_week = 10
        import inbox as IB
        message = IB.post(self.L,'injury_decision','Play or sit?','',
                          payload=dict(pid=self.p.pid),expires_week=10)
        message['week'] = 10
        state = copy.deepcopy(self.s.rng.bit_generator.state)
        loaded = Session.load(self.s.save())
        player = loaded.L.player(self.p.pid)
        self.assertEqual(loaded.L.week,10)
        self.assertIsNone(player.out_until)
        self.assertNotIn(player.pid,loaded.runner.desks['GB'].pending)
        self.assertNotIn(player.pid,loaded.runner.desks['GB'].status)
        self.assertEqual(next(m for m in loaded.L.inbox if m['id']==message['id'])['status'],'done')
        self.assertEqual(state,loaded.rng.bit_generator.state)
        self.assertTrue(loaded.club_act('ir_activate',pid=player.pid)['ok'])
        self.assertNotIn(player,loaded.L.teams['GB'].ir)

    def test_weekly_listing_clears_user_cpu_and_bye_players(self):
        cpu = self.L.teams['CHI'].roster[0]
        cpu.out_until = 10
        future = self.t.roster[1]; future.out_until = 11
        season = self.t.roster[2]; season.out_until = 99
        self.L.schedule = []  # A bye does not defer recovery.
        runner = SeasonRunner(self.L,self.s.rng)
        runner.injury_week(10)
        self.assertIsNone(self.p.out_until)
        self.assertIsNone(cpu.out_until)
        self.assertEqual(future.out_until,11)
        self.assertEqual(season.out_until,99)
        self.assertNotIn(self.p.pid,runner.desks['GB'].pending)
        self.assertIn(cpu,GA.dressed(self.L.teams['CHI'],runner.desks['CHI'],10))

    def test_one_week_before_return_means_one_week_remaining(self):
        self.t.ir=[]
        desk=IS.InjuryDesk()
        with patch.object(IS,'designation',return_value='out') as designation:
            desk.set_week(self.L,self.t,9,self.s.rng)
        self.assertEqual(designation.call_args.args[0],1)
        self.assertEqual(self.p.out_until,10)
        desk.set_week(self.L,self.t,10,self.s.rng)
        self.assertIsNone(self.p.out_until)

    def test_ir_minimum_return_limit_and_season_placement_still_apply(self):
        self.s.stop=('week',10);self.s._sync_week_health()
        self.p.xp_spent['_ir_week']=8
        self.assertFalse(self.row()['can_activate'])
        self.assertIn('sit 4 weeks',self.row()['activate_reason'])
        self.p.xp_spent['_ir_week']=6
        self.t.ir_returns_used=8
        self.assertFalse(self.row()['can_activate'])
        self.assertIn('eight returns',self.row()['activate_reason'])
        self.t.ir_returns_used=0
        self.p.xp_spent['_ir_return']=False
        self.assertFalse(self.row()['can_activate'])
        self.assertIn('for the season',self.row()['activate_reason'])

    def test_playoff_return_week_and_live_game_guard(self):
        self.s.stop=('playoffs',0)
        self.p.out_until=19
        self.s._sync_week_health()
        self.assertEqual(self.L.week,19)
        self.assertIsNone(self.p.out_until)
        self.p.out_until=19
        self.s.runner=NS(live={'done':False})
        self.s._sync_week_health()
        self.assertEqual(self.p.out_until,19)


if __name__=='__main__': unittest.main()

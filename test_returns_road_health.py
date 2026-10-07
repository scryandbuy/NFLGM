import copy, unittest
from unittest.mock import patch
from types import SimpleNamespace as NS
import numpy as np
import game as G, plays as P, health as H, kick_returns as K, adjust as AD
from test_coaching_perspective import state, watch
from season import SeasonRunner

class FollowupTests(unittest.TestCase):
    def test_road_delay_defers_without_losing_evidence(self):
        st=state();watch(st,'defense');st.road_adjust_delay=1.21
        before=copy.deepcopy(st.memories['defense'].__dict__)
        with patch.object(AD,'detect',return_value=[]) as detect:
            st.adjust(rng=NS(random=lambda:.99),unit='defense');detect.assert_not_called()
            self.assertEqual(before,st.memories['defense'].__dict__)
            st.adjust(rng=NS(random=lambda:0),unit='defense');detect.assert_called_once()
    def test_neutral_delay_does_not_draw_or_defer(self):
        st=state();st.road_adjust_delay=1
        with patch.object(AD,'detect',return_value=[]),patch.object(AD,'respond',return_value=[]):
            st.adjust(rng=NS(random=lambda: self.fail('extra neutral roll')),unit='defense')
    def test_delay_survives_reload_and_legacy_defaults(self):
        st=state();st.road_adjust_delay=1.21
        d=SeasonRunner._state_data(st);other=state();SeasonRunner._restore_state(other,d)
        self.assertEqual(other.road_adjust_delay,1.21)
        del d['road_adjust_delay'];SeasonRunner._restore_state(other,d);self.assertEqual(other.road_adjust_delay,1)
    def test_special_injury_dedup_out_and_next_kicker(self):
        st=state();p=dict(pid='k',pos='K');backup=dict(pid='k2',pos='K')
        roster=dict(k=p,depth={'K':[p,backup]})
        with patch.object(H,'roll_injury',return_value=dict(player='k',kind='Ankle',weeks_out=1,season_ending=False)) as roll:
            result=G.special_injuries(st,[p,p],np.random.default_rng(1),P.rate,4)
            self.assertEqual(roll.call_count,1);self.assertEqual(roll.call_args.kwargs['risk_scale'],.1)
            self.assertEqual(result[0]['source'],'special_teams');self.assertIn('k',st.out)
            G.special_injuries(st,[p],np.random.default_rng(1),P.rate,4);self.assertEqual(roll.call_count,1)
        self.assertEqual(G.specialist_for(roster,st,'K',P.rate)['pid'],'k2')
    def test_scrimmage_reserves_risk_without_changing_severity(self):
        with patch.object(H,'roll_injury',return_value=None) as roll:
            state().hurt(dict(pid='a'), 'WR',1,np.random.default_rng(1),P.rate)
            self.assertEqual(roll.call_args.kwargs['risk_scale'],.96)
    def test_return_breakaway_uses_pursuit_and_bounds(self):
        r=dict(pid='r');cov=[dict(pid='a'),dict(pid='b')]
        rng=NS(random=lambda:0,integers=lambda n:0)
        with patch('events.fumble_check',return_value=None),patch.object(K,'_kickoff_breakaway',return_value=dict(yards=95,tackler=None,contacts=[])) as chase:
            out=K.resolve(95,25,r,rng,P.rate,cov)
            self.assertTrue(out['touchdown']);self.assertEqual(out['new_yardline'],0)
            self.assertEqual(len(chase.call_args.args[3]),2)
    def test_ordinary_return_no_extra_yards(self):
        rng=NS(random=lambda:1,integers=lambda n:0)
        with patch('events.fumble_check',return_value=None),patch.object(P,'resolve_yards_after') as chase:
            out=K.resolve(95,25,dict(pid='r'),rng,P.rate,[dict(pid='c')])
            chase.assert_not_called();self.assertEqual(out['ret'],25)
    def test_emergency_kicker_gets_epa_credit(self):
        import advanced_stats as AS
        book=G.StatBook();dr=NS(result='Field goal',togo=5,yardline=20)
        AS.book_special(book,dr,dict(type='field_goal',kicker_pid='backup',down=4,ydstogo=5,yardline=20),dict(k=dict(pid='injured')))
        self.assertIn('backup',book.p);self.assertNotIn('injured',book.p)

    def test_special_hazard_fits_reserved_budget(self):
        # Conservatively compare 25 full-unit kicking reps with 65 scrimmage
        # reps, same people/health: special contact is lower, not additive risk.
        for pos in ('HB','CB','C','WR','TE'):
            base=H.injury_chance({},pos,1,P.rate)
            special=H.injury_chance({},pos,.8,P.rate)
            self.assertLessEqual(65*base*.96+25*special*.1,65*base)

if __name__=='__main__':unittest.main()

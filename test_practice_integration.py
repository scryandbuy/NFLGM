import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game
import practice_integration as PI
from session import Session
from test_cap_accounting import fixture, player
from gm_engine import GM


class PracticeIntegrationTests(unittest.TestCase):
    def fixture(self):
        league=fixture()
        for t in league.teams.values(): t.gm=GM()
        for abbr in league.teams:
            for i in range(3): player(league,f'{abbr}{i}',abbr)
        league.schedule=[(1,'MIN','GB',None,None)]
        return Session(league,np.random.default_rng(123),'GB')

    def test_managed_game_keeps_condition_until_practice(self):
        st=game.TeamState({})
        st.defer_recovery=True
        st.cond.cond={'p':63.0}; st.snaps={'p':45}
        st.end_game(np.random.default_rng(1))
        self.assertEqual(st.cond.get('p'),63)
        self.assertEqual(st.last_snaps,{'p':45})
        self.assertGreater(st.jaded['p'],0)

    def test_legacy_migration_does_not_retrain_finished_week(self):
        s=self.fixture();s.played=True
        s.L.schedule=[(1,'MIN','GB',14,21)]
        PI.migrate(s,{})
        self.assertFalse(PI.pending(s))
        self.assertEqual(set(s.L.practice_state['recovery_already_applied']['2026:2']),{'GB','MIN'})
        self.assertTrue(PI.result(s.L,'GB',1)['legacy'])
        before=copy.deepcopy(s.L.practice_state)
        PI.migrate(s,{'practice_state':before})
        self.assertEqual(before,s.L.practice_state)

    def test_playoff_bye_alive_and_elimination(self):
        s=self.fixture();s.stop=('playoffs',0)
        s.L._post_ref=NS(champion=None,alive_now=lambda:{'GB'})
        self.assertTrue(PI.pending(s))
        self.assertFalse(PI.eligible(s.L,'MIN',19))
        s.L._post_ref.champion='GB'
        self.assertFalse(PI.pending(s))

    def test_manual_advance_stops_before_game(self):
        s=self.fixture();s.runner=NS()
        def resolved(*args,**kwargs):
            s.L.practice_state={'completed':{'2026:1':{'GB':{'players':[]}}}}
            return {'ok':True}
        with patch.object(s,'practice_act',side_effect=resolved) as run:
            result=s._advance()
        self.assertEqual(result['done'],'Practice complete')
        self.assertFalse(s.played)
        run.assert_called_once_with('run')
        self.assertFalse(PI.pending(s))

    def test_transfer_after_completed_practice_keeps_health(self):
        s=self.fixture()
        p=s.L.teams['GB'].roster[0]
        s.L.teams['GB'].roster.remove(p);s.L.teams['MIN'].roster.append(p);p.team='MIN'
        s.L.practice_state={'players':{p.pid:{'condition':73.,'jaded':.4,'last_team':'GB'}}}
        st=game.TeamState({})
        runner=NS(L=s.L,states={'MIN':st})
        PI.restore_transfers(runner,'MIN')
        self.assertEqual(st.cond.get(p.pid),73.)
        self.assertEqual(st.jaded[p.pid],.4)
        self.assertEqual(s.L.practice_state['players'][p.pid]['last_team'],'MIN')

    def test_batch_playoffs_prepare_all_alive_including_byes(self):
        from postseason import Postseason
        seeds={c:[f'{c}{i}' for i in range(1,8)] for c in ('AFC','NFC')}
        teams={a:NS(win_pct=.7) for sd in seeds.values() for a in sd}
        league=NS(year=2026,teams=teams,schedule=[],log=lambda *a,**k:None)
        counts=[]
        runner=NS(L=league,seeds=lambda:seeds,
                  play=lambda *a,**k:dict(home=21,away=14))
        runner.prepare_practice=lambda w:counts.append((w,sum(PI.eligible(league,a,w) for a in teams)))
        available=[]
        runner.require_available=lambda a,w,**kw:available.append((a,w))
        post=Postseason(runner)
        self.assertIsNotNone(post.run())
        self.assertEqual(counts,[(19,14),(20,8),(21,4),(22,2)])
        self.assertEqual(len(post.games),13)
        self.assertEqual(len(available),26)
        self.assertFalse(PI.eligible(league,post.champion,22))

    def test_real_plan_preview_run_and_replay(self):
        s=self.fixture()
        before=copy.deepcopy(s.rng.bit_generator.state)
        first=s.practice_view()
        self.assertIsNone(s.runner)
        self.assertEqual(before,s.rng.bit_generator.state)
        self.assertTrue(s.practice_act('save',json.dumps(first['plan']))['ok'])
        self.assertTrue(s.practice_act('run')['ok'])
        self.assertTrue(s.practice_view()['completed'])
        loaded=Session.load(s.save())
        rng=copy.deepcopy(loaded.rng.bit_generator.state)
        xp={pid:p.xp for pid,p in loaded.L.players.items()}
        self.assertTrue(loaded.practice_act('run')['ok'])
        self.assertEqual(rng,loaded.rng.bit_generator.state)
        self.assertEqual(xp,{pid:p.xp for pid,p in loaded.L.players.items()})
        self.assertEqual(len([m for m in loaded.L.inbox if m['kind']=='practice']),1)

    def test_practice_injury_reaches_game_medical_availability(self):
        s=self.fixture()
        with patch('practice.BASE_INJURY_RISK',100.):
            self.assertTrue(s.practice_act('run')['ok'])
        injured=[p for p in s.L.teams['GB'].roster if p.out_until is not None]
        self.assertTrue(injured)
        for p in injured:
            self.assertFalse(s.runner.desks['GB'].available(p,1))
            self.assertNotIn(p.pid,s.runner.desks['GB'].playing_hurt)
        self.assertTrue(PI.result(s.L,'GB',1)['injuries'])
        self.assertFalse(s.runner.states['GB'].injuries)  # no duplicate game injury accounting

    def test_saved_plans_and_completion_roundtrip(self):
        s=self.fixture()
        s.L.practice_state={'version':1,'auto':{'GB':True},'completed':{'2026:1':{'GB':{'players':[]}}},'participants':{'2026:1':{'GB0':'GB'}}}
        before=copy.deepcopy(s.L.practice_state)
        loaded=Session.load(s.save())
        self.assertEqual(before,loaded.L.practice_state)
        self.assertFalse(PI.pending(loaded))


if __name__=='__main__':unittest.main()

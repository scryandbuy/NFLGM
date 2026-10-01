"""Annual trait reviews: realistic decisions, stable ranks, persisted evidence."""
import copy
import inspect
import unittest
from unittest.mock import patch
from types import SimpleNamespace as N
import numpy as np
import targets as TG
import dev_roll as DR
import progression_engine as PE
import views_club as VC
from league import League, Player
from test_cap_accounting import fixture


def league_fixture():
    l=fixture()
    for i in range(4):
        p=Player(str(i),f'Player {i}','QB',33,
                 {k:70.+i*3 for k in TG.DEPTH_WEIGHTS['QB']},team='GB',
                 dev='superstar' if i==3 else 'normal')
        l.players[p.pid]=p;l.teams['GB'].roster.append(p)
    l.stats[l.year]={str(i):dict(score=3-i,confidence=1.,group='QB') for i in range(4)}
    return l


def assess(p,line):
    if line.get('insufficient'): return None
    return dict(score=line['score'],confidence=line.get('confidence',1.),
                group=line.get('group','QB'),credible=line.get('credible',True),opportunities=500)


def next_year(l):
    prior=l.year;l.year+=1
    l.stats[l.year]=copy.deepcopy(l.stats[prior])
    for p in l.players.values():p.age+=1


class DevReviewTests(unittest.TestCase):
    def setUp(self):
        self.scoring=patch.object(DR.DE,'assessment',side_effect=assess)
        self.scoring.start()
    def tearDown(self):self.scoring.stop()

    def test_ties_have_mean_ranks_and_order_does_not_matter(self):
        np.testing.assert_allclose(DR._pct([5,5,5,5]),[.5]*4)
        np.testing.assert_allclose(DR._pct([0,5,5,10]),[0,.5,.5,1])
        np.testing.assert_allclose(DR._pct([5]),[.5])
        a=league_fixture();b=League.load(a.save())
        b.stats[b.year]=dict(reversed(list(b.stats[b.year].items())))
        for l in (a,b):DR.run(l,{},np.random.default_rng(33))
        self.assertEqual({p.pid:p.xp_spent for p in a.players.values()},
                         {p.pid:p.xp_spent for p in b.players.values()})

    def test_two_poor_seasons_required_and_demotion_resets_evidence(self):
        l=league_fixture();rng=N(random=lambda:.9999);p=l.player('3')
        DR.run(l,{},rng)
        self.assertEqual(p.dev,'superstar')
        self.assertEqual(p.xp_spent['_dev_review'][-1]['chance_down'],0)
        next_year(l);DR.run(l,{},rng)
        self.assertEqual(p.dev,'star')
        record=p.xp_spent['_dev_review'][-1]
        self.assertGreater(record['chance_down'],0)
        self.assertEqual(record['poor_seasons'],0)
        self.assertIn('2 consecutive',record['reason'])
        next_year(l);DR.run(l,{},rng)
        self.assertEqual(p.dev,'star')

    def test_injury_small_sample_good_season_and_role_change_break_streak(self):
        for alteration in ('injury','missing','role','good','proxy'):
            with self.subTest(alteration=alteration):
                l=league_fixture();rng=N(random=lambda:.9999)
                DR.run(l,{},rng);next_year(l)
                row=l.stats[l.year]['3']
                if alteration=='injury':row['confidence']=.4
                elif alteration=='missing':row['insufficient']=True
                elif alteration=='role':row['group']='NEW ROLE'
                elif alteration=='good':row['score']=99
                elif alteration=='proxy':row['credible']=False
                DR.run(l,{},rng)
                self.assertEqual(l.player('3').dev,'superstar')
                next_year(l);l.stats[l.year]['3']=dict(score=0,confidence=1.,group='QB')
                DR.run(l,{},rng)
                self.assertEqual(l.player('3').dev,'superstar')

    def test_save_reload_repeated_call_and_evidence_bound(self):
        l=league_fixture();rng=np.random.default_rng(24)
        DR.run(l,{},rng);next_year(l)
        clone=League.load(l.save());clone_rng=np.random.default_rng()
        clone_rng.bit_generator.state=copy.deepcopy(rng.bit_generator.state)
        DR.run(l,{},rng);DR.run(clone,{},clone_rng)
        self.assertEqual([p.dev for p in l.players.values()],[p.dev for p in clone.players.values()])
        self.assertEqual(rng.bit_generator.state,clone_rng.bit_generator.state)
        before=clone.save();state=copy.deepcopy(clone_rng.bit_generator.state)
        self.assertEqual(DR.run(clone,{},clone_rng),[])
        self.assertEqual(clone.save(),before)
        self.assertEqual(clone_rng.bit_generator.state,state)
        for _ in range(6):next_year(l);DR.run(l,{},rng)
        self.assertTrue(all(len(p.xp_spent['_dev_review'])<=3 for p in l.players.values()))

    def test_majors_one_tier_no_sample_and_existing_top_tier_protected(self):
        l=league_fixture();p=l.player('0');l.stats[l.year]={}
        DR.run(l,{'mvp':p,'opoy':p},N(random=lambda:0.))
        self.assertEqual(p.dev,'star')
        self.assertEqual(len([x for x in l.transactions if x['kind']=='dev_trait']),1)
        next_year(l);p.dev='xfactor'
        DR.run(l,{'mvp':p},N(random=lambda:.9999))
        self.assertEqual(p.dev,'xfactor')

    def test_small_comparison_groups_reduce_confidence_not_arbitrarily_freeze(self):
        l=league_fixture();del l.stats[l.year]['3']
        DR.run(l,{},N(random=lambda:0.))
        self.assertEqual(l.player('0').dev,'star')
        self.assertLess(l.player('0').xp_spent['_dev_review'][-1]['confidence'],.75)

    def test_no_age_only_demotion_and_honors_protect(self):
        for age in (24,32,39):
            for production,expected in ((.85,.85),(1.,.85),(.6,.8)):
                self.assertEqual(PE.trait_move_chances('superstar',age,production,expected,
                                                     poor_seasons=3)[1],0)
        self.assertEqual(PE.trait_move_chances('superstar',32,.1,.85,{'all_pro_1'},poor_seasons=3)[1],0)
        self.assertEqual(PE.trait_move_chances('superstar',32,.1,.85,poor_seasons=3,confidence=.5)[1],0)
        self.assertGreater(PE.trait_move_chances('superstar',32,.1,.85,poor_seasons=2)[1],0)

    def test_upgrades_need_strong_performance_or_honors(self):
        self.assertEqual(PE.trait_move_chances('normal',22,.5,.15)[0],0)
        self.assertGreater(PE.trait_move_chances('normal',22,.9,.5)[0],0)
        self.assertGreater(PE.trait_move_chances('superstar',24,.9,.85,elite_seasons=2)[0],0)
        self.assertGreater(PE.trait_move_chances('normal',24,.5,.5,{'all_pro_1'})[0],0)

    def test_changes_are_readable_in_player_history_including_legacy(self):
        l=league_fixture();p=l.player('0')
        DR.run(l,{'mvp':p},N(random=lambda:.5))
        entry=VC._player_history(l,p)[0]['line']
        self.assertIn('Normal → Rare',entry)
        self.assertIn('MVP',entry)
        l.log('dev_trait',pid=p.pid,dev='normal',change='down')
        self.assertTrue(any('Development downgraded: Normal' in row['line'] for row in VC._player_history(l,p)))

    def test_calendar_evaluates_before_regression_and_batch_does_too(self):
        from session import Session
        from franchise import Franchise
        s=Session.__new__(Session);s.L=league_fixture();s.rng=np.random.default_rng(3)
        s.user_team='GB';s.votes={};calls=[]
        with patch('session.DR.run',side_effect=lambda *a,**k:calls.append('dev')), \
             patch('session.RG.run',side_effect=lambda *a,**k:calls.append('regression')), \
             patch('session.RT.run'),patch('session.AL.hall_vote'),patch('session.IB.post'),patch('league_notes.season_end'):
            s.step_retire()
        self.assertEqual(calls,['dev','regression'])
        source=inspect.getsource(Franchise.play_year)
        self.assertLess(source.index('DR.run'),source.index('RG.run'))


if __name__=='__main__':unittest.main()

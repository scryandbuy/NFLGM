import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import league as LG
import xp as XP
import regression as RG
import views_club as VC
from session import Session

class StructureTests(unittest.TestCase):
    def player(self):
        return LG.Player('test', 'Test Player', 'QB', 35, {'awareness_rating':85., 'throw_power_rating':88., 'throw_accuracy_short_rating':85.}, potential_range=(85,92), team='GB')

    def test_ceiling_read_is_pure_and_resolution_is_once(self):
        p=self.player(); rng=np.random.default_rng(22); before=copy.deepcopy(rng.bit_generator.state)
        self.assertIsNone(XP.ceiling(p,rng)); self.assertIsNone(p.potential)
        self.assertEqual(before,rng.bit_generator.state)
        XP.resolve_potential(p,rng); chosen=p.potential; after=copy.deepcopy(rng.bit_generator.state)
        XP.resolve_potential(p,rng)
        self.assertEqual(chosen,p.potential); self.assertEqual(after,rng.bit_generator.state)

    def test_legacy_migration_preserves_live_rng(self):
        p=self.player(); league=SimpleNamespace(players={p.pid:p}); rng=np.random.default_rng(22)
        before=copy.deepcopy(rng.bit_generator.state); Session(league,rng,'GB')
        self.assertIsNotNone(p.potential); self.assertEqual(before,rng.bit_generator.state)
        chosen=p.potential; Session(league,rng,'GB'); self.assertEqual(chosen,p.potential)

    def test_history_survives_changes_and_removal(self):
        p=self.player(); league=SimpleNamespace(players={p.pid:p},year=2026,log=lambda *a,**k:None)
        league.player=lambda pid:league.players.get(pid)
        def decline(p,rng):
            p.ratings['throw_power_rating']-=10
            return 3
        with patch.object(RG,'decline',decline): RG.run(league,np.random.default_rng(2),record_for='GB')
        saved=copy.deepcopy(league.regression)
        with patch('views.rail',return_value={}),patch('views.club',return_value={}):
            first=VC.regression(None,league,'GB')
            p.ratings['throw_power_rating']=99; p.name='Changed'; p.pos='HB'; p.team='CHI'
            second=VC.regression(None,league,'GB')
            league.players.clear(); third=VC.regression(None,league,'GB')
        self.assertTrue(first['rows'])
        for result in (second,third):
            self.assertEqual(first['rows'][0]['cols'],result['rows'][0]['cols'])
            self.assertEqual('Test Player',result['rows'][0]['name'])
        self.assertFalse(third['rows'][0]['available']); self.assertEqual(saved,league.regression)

    def test_legacy_history_uses_saved_attributes(self):
        p=self.player(); league=SimpleNamespace(year=2026,player=lambda pid:p,regression={'2026':{'test':dict(before=88,after=85,age=34,attrs={'throw_power_rating':[90,80]})}})
        with patch('views.rail',return_value={}),patch('views.club',return_value={}): row=VC.regression(None,league,'GB')['rows'][0]
        values=[a for c in row['cols'] for a in c['rows']]
        self.assertEqual([80],[a['v'] for a in values]); self.assertTrue(row['partial'])

if __name__=='__main__': unittest.main()

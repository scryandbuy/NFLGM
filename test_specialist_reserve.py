"""The LS street reserve survives cleanup and save/load without duplicating men."""
import copy
import csv
import hashlib
import json
import unittest
from unittest.mock import patch

import numpy as np
import league as LG
import newgens as NG
import specialist_reserve as SR
import franchise as F
from cap_engine import Contract


class SpecialistReserveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = LG.build_league(rng=np.random.default_rng(123))

    def setUp(self):
        self.L = copy.deepcopy(self.base)

    def pool(self):
        return [self.L.player(pid) for pid in self.L.free_agents
                if SR.eligible(self.L.player(pid))]

    def test_fifty_source_rows_have_actual_requested_ratings_and_unique_names(self):
        with SR.POOL_PATH.open(encoding='utf-8-sig', newline='') as handle:
            rows = [r for r in csv.DictReader(handle) if r['iteration'] == SR.SEED_MARKER]
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({r['player_id'] for r in rows}), 50)
        self.assertEqual(len({NG.normalize_name(r['full_name']) for r in rows}), 50)
        with open('original_player_name_hashes.json', encoding='utf-8') as handle:
            excluded = set(json.load(handle))
        for r in rows:
            self.assertEqual(r['madden_position'], 'LS')
            self.assertNotIn(hashlib.sha256(NG.normalize_name(r['full_name']).encode()).hexdigest(), excluded)
            self.assertTrue(22 <= float(r['age']) <= 25)
            self.assertTrue(55 <= float(r['awareness_rating']) <= 65)
            self.assertEqual(float(r['overall']), float(r['awareness_rating']))
        self.assertEqual(len(self.pool()), 50)
        for p in self.pool():
            self.assertIsNone(p.team)
            self.assertIsNone(p.contract)
            self.assertEqual(p.dev, 'normal')
            self.assertTrue(55 <= p.ovr <= 65)
            self.assertGreaterEqual(len(p.ratings), 50)

    def test_seed_addition_does_not_change_original_players_or_rng_draws(self):
        a, b = np.random.default_rng(321), np.random.default_rng(321)
        with patch.object(SR, 'ensure', return_value=[]):
            old = LG.build_league(rng=a)
        new = LG.build_league(rng=b)
        self.assertEqual(a.bit_generator.state, b.bit_generator.state)
        self.assertEqual(len(new.players) - len(old.players), 50)
        for pid, p in old.players.items():
            self.assertEqual(p.to_dict(), new.players[pid].to_dict())

    def test_idempotence_when_reserve_is_full(self):
        before = self.L.to_dict()
        self.assertEqual(SR.ensure(self.L), [])
        self.assertEqual(before, self.L.to_dict())

    def test_current_reload_does_not_replace_a_signed_player(self):
        p = self.pool()[0]
        self.L.sign(p.pid, 'GB', Contract(1, [1.0]))
        blob = self.L.save()
        restored = LG.League.load(blob)
        self.assertEqual(len(restored.players), len(self.L.players))
        self.assertEqual(restored.free_agents, self.L.free_agents)
        self.assertEqual(restored.player(p.pid).to_dict(), p.to_dict())
        self.assertEqual(len([pid for pid in restored.free_agents if SR.eligible(restored.player(pid))]), 49)

    def test_legacy_save_gets_supply_once_and_preserves_game_rng(self):
        data = self.L.to_dict()
        ids = {p.pid for p in self.pool()}
        for pid in ids:
            data['players'].pop(pid)
        data['free_agents'] = [pid for pid in data['free_agents'] if pid not in ids]
        data.pop('ls_reserve_version')
        data['rng_state'] = np.random.default_rng(765).bit_generator.state
        restored = LG.League.load(data)
        self.assertEqual(restored.rng_state, data['rng_state'])
        self.assertEqual(len([pid for pid in restored.free_agents if SR.eligible(restored.player(pid))]), 50)
        again = LG.League.load(restored.save())
        self.assertEqual(len(again.players), len(restored.players))
        self.assertEqual(again.free_agents, restored.free_agents)

    def test_replenishment_never_resurrects_or_overwrites_retired_or_signed_ids(self):
        a, b = self.pool()[:2]
        self.L.sign(a.pid, 'GB', Contract(1, [1.0]))
        b.retired = True
        self.L.free_agents.remove(b.pid)
        signed, retired = a.to_dict(), b.to_dict()
        added = SR.ensure(self.L)
        self.assertEqual(len(added), 2)
        self.assertEqual(len(self.pool()), 50)
        self.assertEqual(a.to_dict(), signed)
        self.assertEqual(b.to_dict(), retired)
        self.assertTrue(all(p.pid not in (a.pid, b.pid) for p in added))
        active_names = [NG.normalize_name(p.name) for p in self.L.players.values() if not p.retired]
        self.assertEqual(len(active_names), len(set(active_names)))

    def test_annual_cleanup_and_udfa_cleanup_retain_bank(self):
        self.L.year += 2
        for p in self.L.players.values():
            p.age += 2
        F.prune_pool(self.L, np.random.default_rng(22))
        self.assertEqual(len(self.pool()), 50)
        F.clear_undrafted(self.L, np.random.default_rng(23), keep=0)
        self.assertEqual(len(self.pool()), 50)

    def test_replenishment_is_deterministic_for_same_save(self):
        for p in self.pool()[:10]:
            p.retired = True
            self.L.free_agents.remove(p.pid)
        other = copy.deepcopy(self.L)
        a, b = SR.ensure(self.L), SR.ensure(other)
        self.assertEqual([p.to_dict() for p in a], [p.to_dict() for p in b])


if __name__ == '__main__':
    unittest.main()

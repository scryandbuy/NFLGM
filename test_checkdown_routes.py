"""A checkdown reads an existing outlet; it cannot shorten a vertical after selection."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import game as G
import plays as P
import rosters as R
import schemes as S
import targets as T


def option(pid, pos='WR', **route):
    return dict(receiver=dict(pid=pid, pos=pos), defender=dict(pid='d' + pid),
                separation=.42, **route)


class ReadDraw:
    """Control the read and sampled progression, leaving their weights observable."""
    def __init__(self, kind='checkdown', order=None):
        self.kind, self.order, self.weights = kind, order, None

    def choice(self, values, size=None, replace=True, p=None):
        if size is None:
            return self.kind
        self.weights = np.array(p)
        return np.array(self.order if self.order is not None else range(size))

    def integers(self, low, high=None):
        return low

    def random(self):
        return 1.0  # Do not replace a controlled read with an openness override.


class CheckdownRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.teams = R.load_league()

    def test_explicit_air_is_authoritative_over_position_role_and_depth(self):
        cases = [
            (option('short', route_air=6), True),
            (option('behind', route_air=-3), True),
            (option('deepback', 'HB', route_air=18, route_depth='short', concept_role='check'), False),
            (option('wrshort', route_depth='short'), True),
            (option('flat', concept_role='flat'), True),
            (option('backrole', concept_role='back'), True),
            (option('check', concept_role='check'), True),
            (option('legacyhb', 'HB'), True),
            (option('legacyfb', 'FB'), True),
            (option('vertical', route_depth='deep'), False),
        ]
        for row, expected in cases:
            with self.subTest(pid=row['receiver']['pid']):
                self.assertEqual(T.is_checkdown_option(row), expected)

    def test_checkdown_uses_only_real_outlets_and_sampled_order(self):
        rows = [option('deep', route_air=25), option('flat', route_air=2.6),
                option('underneath', route_depth='short')]
        for order, wanted in (([0, 2, 1], 'underneath'), ([0, 1, 2], 'flat')):
            got = T.select_target(rows, {}, 'four_verts', ReadDraw(order=order), P.rate)
            self.assertEqual((got[0]['pid'], got[2]), (wanted, 'checkdown'))

    def test_no_outlet_preserves_progression_without_checkdown_bonus(self):
        for rows, order, wanted, kind in (
                ([option('x', route_air=26), option('z', route_air=24)], [1, 0], 'x', 'second'),
                ([option('alone', route_air=26)], [0], 'alone', 'first')):
            got = T.select_target(rows, {}, 'four_verts', ReadDraw(order=order), P.rate)
            self.assertEqual((got[0]['pid'], got[2]), (wanted, kind))
            self.assertLessEqual(T.READ_MODIFIER[got[2]]['comp'], 1)
            self.assertGreater(next(p['route_air'] for p in rows if p['receiver'] is got[0]), 20)

    def test_fourth_down_does_not_make_long_check_role_an_outlet(self):
        rows = [option('sticks', route_air=17, concept_role='check'),
                option('emergency', 'HB', route_air=2.6)]
        got = T.select_target(rows, {}, 'dagger', ReadDraw(order=[0, 1]), P.rate,
                              down=4, ydstogo=16, pressure=1)
        self.assertEqual((got[0]['pid'], got[2]), ('emergency', 'checkdown'))
        self.assertEqual(rows[0]['route_air'], 17)

    def test_first_reads_keep_elite_and_coach_preferences_without_erasing_others(self):
        rows = [option('star', route_air=26), option('other', route_air=26),
                option('outlet', 'HB', route_air=2.6)]
        for row, grade in zip(rows, (98, 70, 70)):
            row['receiver'].update({key: grade for key in T.RECV_GRADE})
        weights = []
        for feature in (0, 1):
            rng = ReadDraw('first', [0, 1, 2])
            got = T.select_target(rows, {}, 'four_verts', rng, P.rate,
                                  plan=NS(target_priority={}, feature_receivers=feature))
            self.assertEqual((got[0]['pid'], got[2]), ('star', 'first'))
            self.assertTrue(all(rng.weights > 0))
            weights.append(rng.weights)
        self.assertGreater(weights[1][0], weights[0][0])

    def resolve(self, seed, *, fielded=True, depth='deep', concept='four_verts',
                down=1, need=10, protection=None, forced_read=None, forced_target=None, unavailable=()):
        rng = np.random.default_rng(seed)
        off, defense = self.teams['GB'], self.teams['DEN']
        if fielded:
            state = G.TeamState(off) if unavailable else None
            if state is not None:
                state.out.update(unavailable)
            off, _ = G.field_units(off, state, rng, True, '11')
            defense, _ = G.field_units(defense, None, rng, False, 'nickel', '3-4')
        call = dict(is_pass=True, personnel='11', depth=depth, concept=concept,
                    down=down, ydstogo=need, play_action=False, shotgun=True)
        dc = S.call_defense(call, down, need, rng, yards_to_endzone=80)
        dc.update(rushers=4, blitzers=0, sim_pressure=False)
        captured, separated = [], {}
        select, separate = T.select_target, P.resolve_man

        def record(pairs, qb, concept, draw, rate_fn, **kwargs):
            captured.extend(dict(p) for p in pairs)
            order = None
            if forced_target is not None:
                target = next(i for i, row in enumerate(pairs)
                              if row['receiver']['pid'] == forced_target)
                order = [target] + [i for i in range(len(pairs)) if i != target]
            return select(pairs, qb, concept, ReadDraw(forced_read, order) if forced_read else draw,
                          rate_fn, **kwargs)

        def separation(receiver, defender, route_depth, *args, **kwargs):
            separated[receiver['pid']] = route_depth
            return separate(receiver, defender, route_depth, *args, **kwargs)

        trace = []
        with ExitStack() as stack:
            stack.enter_context(patch.object(T, 'select_target', side_effect=record))
            stack.enter_context(patch.object(P, 'resolve_man', side_effect=separation))
            stack.enter_context(patch.object(P, 'PASS_TRACE', trace))
            if protection:
                stack.enter_context(patch.object(S, 'choose_protection', return_value=protection))
            out = P._pass_play(off, defense, call, dc, 80, rng)
        return out, captured, separated, trace, off

    def test_original_raw_roster_seed_uses_real_outlet_before_throw(self):
        out, rows, separated, trace, _ = self.resolve(1, fielded=False)
        self.assertEqual(out.get('read'), 'checkdown')
        target = next(p for p in rows if p['receiver']['pid'] == out['target'])
        self.assertTrue(T.is_checkdown_option(target))
        self.assertEqual((target['route_depth'], separated[out['target']], out['depth']),
                         ('short', 'short', 'short'))
        if 'route_air' in target:
            self.assertLessEqual(target['route_air'], 6)
        self.assertTrue(any(t.get('depth') == 'short' and t.get('rmod') == 1.29 for t in trace))

    def test_fielded_concept_outlets_have_geometry_before_separation(self):
        found = 0
        for seed in range(20):
            out, rows, separated, trace, off = self.resolve(seed, protection='five', forced_read='checkdown')
            for row in rows:
                if row.get('concept_role') in ('flat', 'back', 'check'):
                    found += 1
                    self.assertEqual(row['route_air'], 2.6)
                    self.assertEqual(row['route_depth'], 'short')
                    self.assertEqual(separated[row['receiver']['pid']], 'short')
            if out.get('read') == 'checkdown':
                self.assertEqual(out['depth'], 'short')
                self.assertIn(out['target'], [p['receiver']['pid'] for p in rows])
        self.assertGreater(found, 0)

    def test_max_protection_does_not_reintroduce_kept_back_or_tight_end(self):
        throws = 0
        for seed in range(20):
            out, rows, _, trace, off = self.resolve(seed, protection='seven', forced_read='checkdown')
            self.assertFalse(any(p['receiver']['pos'] in ('HB', 'FB', 'TE') for p in rows))
            if out.get('target'):
                throws += 1
                self.assertEqual(out['read'], 'second')
                self.assertEqual(out['depth'], 'deep')
                self.assertTrue(all(t.get('rmod') != 1.29 for t in trace))
        self.assertGreater(throws, 0)

    def test_injured_back_cannot_be_reintroduced_as_checkdown(self):
        unavailable = self.teams['GB']['rb']['pid']
        checked = 0
        for seed in range(10):
            out, rows, _, _, off = self.resolve(seed, unavailable=(unavailable,),
                protection='five', forced_read='checkdown')
            self.assertNotEqual((off.get('rb') or {}).get('pid'), unavailable)
            self.assertNotIn(unavailable, [p['receiver']['pid'] for p in rows])
            self.assertNotEqual(out.get('target'), unavailable)
            checked += bool(rows)
        self.assertGreater(checked, 0)

    def test_fourth_down_conversion_routes_survive_concept_outlet_labels(self):
        checked = 0
        for seed in range(10):
            out, rows, _, _, _ = self.resolve(seed, down=4, need=16,
                                              depth='medium', concept='dagger', protection='five')
            for row in rows:
                if row['receiver']['pos'] not in ('HB', 'FB') and not row.get('late'):
                    checked += 1
                    self.assertGreaterEqual(row['route_air'], 16)
                    self.assertFalse(T.is_checkdown_option(row))
        self.assertGreater(checked, 0)

    def test_fourth_down_delayed_tight_end_is_short_before_separation(self):
        _, rows, separated, _, _ = self.resolve(0, down=4, need=16,
            depth='medium', concept='dagger', protection='five')
        delayed = [row for row in rows if row.get('late') and row['receiver']['pos'] == 'TE']
        self.assertTrue(delayed, 'Controlled seed must exercise a real chip-and-release tight end')
        for row in delayed:
            self.assertEqual(row['route_air'], 2.6)
            self.assertEqual(row['route_depth'], 'short')
            self.assertEqual(separated[row['receiver']['pid']], 'short')

    def test_chip_release_underneath_tight_end_is_a_real_short_outlet(self):
        for concept, role in (('flood', 'flat'), ('dagger', 'check')):
            with self.subTest(concept=concept):
                out, rows, separated, trace, _ = self.resolve(0, concept=concept,
                    protection='five', forced_read='checkdown')
                delayed = [row for row in rows if row.get('late')
                           and row['receiver']['pos'] == 'TE']
                self.assertEqual(len(delayed), 1, 'Seed must exercise an actual TE chip and release')
                row = delayed[0]
                pid = row['receiver']['pid']
                self.assertEqual(row['concept_role'], role)
                self.assertEqual((row['route_air'], row['route_depth'], separated[pid]),
                                 (2.6, 'short', 'short'))
                self.assertTrue(T.is_checkdown_option(row))
                self.assertEqual((out.get('target'), out.get('read'), out.get('depth')),
                                 (pid, 'checkdown', 'short'))
                self.assertTrue(any(t.get('depth') == 'short' and t.get('rmod') == 1.29
                                    for t in trace))

    def test_chip_release_deeper_tight_end_keeps_normal_downfield_throw(self):
        out, rows, separated, _, _ = self.resolve(0, concept='scissors',
            protection='five', forced_read='checkdown')
        delayed = [row for row in rows if row.get('late') and row['receiver']['pos'] == 'TE']
        self.assertEqual(len(delayed), 1, 'Seed must exercise an actual TE chip and release')
        row = delayed[0]
        pid = row['receiver']['pid']
        self.assertEqual(row['concept_role'], 'support')
        self.assertEqual((row['route_depth'], separated[pid]), ('deep', 'deep'))
        self.assertNotIn('route_air', row)
        self.assertFalse(T.is_checkdown_option(row))
        self.assertNotEqual(out.get('target'), pid, 'A checkdown cannot select the delayed vertical')

        # The same released TE remains a legitimate downfield read. Control
        # only the sampled first read; keep real protection, chip, route and throw.
        deep, rows, separated, trace, _ = self.resolve(0, concept='scissors',
            protection='five', forced_read='first', forced_target=pid)
        chosen = next(p for p in rows if p['receiver']['pid'] == pid)
        self.assertTrue(chosen.get('late'))
        self.assertEqual((deep.get('target'), deep.get('read'), deep.get('depth')),
                         (pid, 'first', 'deep'))
        self.assertEqual(separated[pid], 'deep')
        throws = [t for t in trace if 'rmod' in t]
        self.assertTrue(throws, 'The controlled first read must reach the actual throw resolver')
        self.assertTrue(all(t['depth'] == 'deep' and t['rmod'] == 1.0 for t in throws))

    def test_screen_and_swing_keep_their_behind_line_identity(self):
        seen = set()
        for concept in ('screen', 'curl_flat'):
            for seed in range(35):
                out, _, _, _, _ = self.resolve(seed, depth='short', concept=concept, protection='five')
                if out.get('type') == 'complete' and (out.get('screen') or out.get('swing')):
                    self.assertEqual(out['depth'], 'short')
                    self.assertLess(out['air'], 0)
                    seen.add('screen' if out.get('screen') else 'swing')
        self.assertEqual(seen, {'screen', 'swing'})


if __name__ == '__main__':
    unittest.main()

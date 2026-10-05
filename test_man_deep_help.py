"""Called man deep help survives receiver assignments and actual pursuit."""
import copy
import unittest

import coverage as C
import defensive_rush as D
import pass_pursuit as PP
import plays as P
import zones as Z
from test_defensive_rush import unit, call


class Fixed:
    def random(self):
        return 0.  # Exercise the safety-first TE assignment alternative.


class ManDeepHelpTests(unittest.TestCase):
    def setup_play(self, name='cover_1', fourth=False, tight_end=False, reverse=False):
        c = dict(call('4-3', 'nickel'), coverage=name, shell=name,
                 under='man' if name in ('cover_0', 'cover_1', 'cover_1_robber', 'two_man') else 'zone')
        defense = unit('4-3', 'nickel')
        if reverse:
            for group in (*D.GROUPS, 'defensive_assignments'):
                defense[group].reverse()
        live = D.select_rush(defense, c)['coverage']
        aligned = [dict(player=dict(pid='X', pos='WR'), spot='X', side='L'),
                   dict(player=dict(pid='Z', pos='WR'), spot='Z', side='R'),
                   dict(player=dict(pid='slot', pos='WR'), spot='slot', side='L')]
        if fourth:
            aligned.append(dict(player=dict(pid='fourth', pos='WR'), spot='slot', side='R'))
        if tight_end:
            aligned.append(dict(player=dict(pid='TE', pos='TE'), spot='te', side='R'))
        pairs, _ = C.assign_coverage(aligned, live, c, Fixed(), P.rate, travel=False)
        return live, c, pairs

    def choose(self, data, target='X'):
        live, c, pairs = data
        pair = next(p for p in pairs if p['receiver']['pid'] == target)
        return PP.select(live, c, pair, pairs, pair['defender'], None,
                         'deep', .515, pair['man'])

    @staticmethod
    def ids(players):
        return [p['pid'] for p in players]

    def test_shared_helper_follows_only_the_called_man_shell(self):
        for name, expected in [('cover_1', ['FS']), ('cover_1_robber', ['FS']),
                               ('two_man', ['FS', 'SS']), ('cover_0', []),
                               ('cover_2', []), ('cover_3', []), ('cover_4', [])]:
            with self.subTest(name=name):
                live, c, pairs = self.setup_play(name)
                rows = D.man_deep_help(D.assignments(live, c), c)
                self.assertEqual(self.ids([a['player'] for a in rows]), expected)

    def test_fourth_receiver_does_not_consume_the_designated_post(self):
        for name in ('cover_1', 'cover_1_robber'):
            for fourth, tight_end in ((False, False), (True, False),
                                      (False, True), (True, True)):
                with self.subTest(name=name, fourth=fourth, tight_end=tight_end):
                    data = self.setup_play(name, fourth, tight_end)
                    live, c, pairs = data
                    self.assertEqual(self.ids(pairs[0]['_unit']['man_deep']), ['FS'])
                    self.assertNotIn('FS', self.ids([p['defender'] for p in pairs if p['man'] and p['defender']]))
                    self.assertEqual(self.ids(self.choose(data))[0], 'FS')
                    self.assertEqual(len(self.choose(data)), len(set(self.ids(self.choose(data)))))
                    if tight_end:
                        te = next(p for p in pairs if p['receiver']['pid'] == 'TE')
                        self.assertNotEqual(te['defender']['pid'], 'FS')
                        self.assertEqual(self.ids(self.choose(data, 'TE'))[0], 'FS')

    def test_two_man_reserves_both_halves_with_side_and_seam_help(self):
        data = self.setup_play('two_man', fourth=True, tight_end=True)
        live, c, pairs = data
        self.assertEqual(set(self.ids(pairs[0]['_unit']['man_deep'])), {'FS', 'SS'})
        self.assertFalse({'FS', 'SS'} & set(self.ids([p['defender'] for p in pairs if p['defender']])))
        self.assertEqual(self.ids(self.choose(data, 'X'))[0], 'SS')
        self.assertEqual(self.ids(self.choose(data, 'Z'))[0], 'FS')
        self.assertEqual(set(self.ids(self.choose(data, 'TE'))), {'FS', 'SS'})

    def test_five_receivers_get_distinct_underneath_men_with_post_reserved(self):
        for name in ('cover_1', 'cover_1_robber', 'two_man'):
            with self.subTest(name=name):
                data = self.setup_play(name, fourth=True, tight_end=True)
                live, c, pairs = data
                self.assertEqual(len(pairs), 5)
                self.assertTrue(all(p['man'] and p['defender'] for p in pairs))
                assigned = self.ids([p['defender'] for p in pairs])
                self.assertEqual(len(set(assigned)), 5, assigned)
                reserved = set(self.ids(pairs[0]['_unit']['man_deep']))
                self.assertFalse(reserved & set(assigned))
                te = next(p for p in pairs if p['receiver']['pid'] == 'TE')
                self.assertNotIn(te['defender']['pid'], reserved)
                pursuit = self.ids(self.choose(data, 'TE'))
                self.assertTrue(reserved.issubset(pursuit), (name, pursuit))

    def test_zero_high_does_not_invent_free_safety_help(self):
        data = self.setup_play('cover_0', fourth=True, tight_end=True)
        pairs = data[2]
        self.assertEqual(pairs[0]['_unit']['man_deep'], [])
        target = next(p for p in pairs if p['receiver']['pid'] == 'X')
        self.assertEqual(self.ids(self.choose(data)), [target['defender']['pid']])

    def test_named_coverage_without_legacy_flags_keeps_its_underneath_rule(self):
        for name in ('cover_1', 'cover_1_robber', 'two_man', 'cover_2'):
            with self.subTest(name=name):
                original = self.setup_play(name, fourth=True, tight_end=True)
                live, c, expected = original
                sparse = {k:v for k,v in c.items() if k not in ('under', 'man')}
                aligned = [dict(player=p['receiver'], spot=p['spot'], side=p['side']) for p in expected]
                pairs, _ = C.assign_coverage(aligned, live, sparse, Fixed(), P.rate, travel=False)
                signature = lambda rows: [(p['receiver']['pid'], p['defender']['pid'], p['man']) for p in rows]
                self.assertEqual(signature(pairs), signature(expected))
                if name == 'cover_2':
                    self.assertFalse(any(p['man'] for p in pairs))
                    self.assertEqual(pairs[0]['_unit']['man_deep'], [])
                else:
                    self.assertTrue(all(p['man'] for p in pairs))
                    self.assertEqual(len({p['defender']['pid'] for p in pairs}), 5)
                    reserved = set(self.ids(pairs[0]['_unit']['man_deep']))
                    self.assertFalse(reserved & {p['defender']['pid'] for p in pairs})
                    self.assertTrue(reserved.issubset(self.ids(self.choose((live, sparse, pairs), 'TE'))))

    def test_explicit_underneath_flags_override_named_coverage_defaults(self):
        live, c, old_pairs = self.setup_play('cover_1', fourth=True, tight_end=True)
        aligned = [dict(player=p['receiver'], spot=p['spot'], side=p['side']) for p in old_pairs]
        for flags in ({'under': 'zone'}, {'man': False}):
            explicit = {k:v for k,v in c.items() if k not in ('under', 'man')}
            explicit.update(flags)
            pairs, _ = C.assign_coverage(aligned, live, explicit, Fixed(), P.rate, travel=False)
            self.assertFalse(any(p['man'] for p in pairs))
            self.assertEqual(pairs[0]['_unit']['man_deep'], [])

    def test_explicit_empty_help_is_authoritative_for_direct_callers(self):
        data = self.setup_play('cover_1')
        live, c, pairs = data
        for p in pairs:
            p['_unit']['man_deep'] = []
        self.assertEqual(self.ids(self.choose(data)), [pairs[0]['defender']['pid']])

    def test_absent_or_busy_explicit_post_cannot_be_summoned(self):
        data = self.setup_play('cover_1')
        live, c, pairs = data
        post = next(p for p in live['db'] if p['pid'] == 'FS')
        absent = copy.deepcopy(data)
        absent[0]['db'] = [p for p in absent[0]['db'] if p['pid'] != 'FS']
        self.assertNotIn('FS', self.ids(self.choose(absent)))
        self.assertNotIn('SS', self.ids(self.choose(absent)))  # no replacement invented
        pairs.append(dict(receiver=dict(pid='direct_TE', pos='TE'),
                          defender=copy.deepcopy(post), man=True))
        self.assertNotIn('FS', self.ids(self.choose(data)))
        # Live-copy lookup uses IDs, not object identity.
        pairs.pop()
        for p in pairs:
            p['_unit']['man_deep'] = [copy.deepcopy(post)]
        selected = self.choose(data)
        self.assertEqual(selected[0]['pid'], 'FS')
        self.assertIs(selected[0], post)

    def test_storage_reordering_keeps_assignments_and_pursuit(self):
        for name in ('cover_1', 'cover_1_robber', 'two_man', 'cover_0', 'cover_3'):
            a = self.setup_play(name, fourth=True, tight_end=True)
            b = self.setup_play(name, fourth=True, tight_end=True, reverse=True)
            pairs = lambda data: [(p['receiver']['pid'], p['defender']['pid'] if p['defender'] else None,
                                  p['man']) for p in data[2]]
            self.assertEqual(pairs(a), pairs(b), name)
            for target in ('X', 'Z', 'TE'):
                self.assertEqual(self.ids(self.choose(a, target)), self.ids(self.choose(b, target)), name)

    def test_zone_unit_and_named_owners_remain_available(self):
        for name in ('cover_2', 'cover_3', 'cover_4', 'cover_6'):
            data = self.setup_play(name, fourth=True, tight_end=True)
            live, c, pairs = data
            self.assertFalse(any(p['man'] for p in pairs))
            unit_meta = pairs[0]['_unit']
            self.assertEqual(unit_meta.get('man_deep', []), [])
            self.assertEqual(set(self.ids(unit_meta['safs'])), {'FS', 'SS'})
            # Adding empty man-help metadata must not change the existing
            # zone owner map, which continues to use the whole dropped unit.
            legacy = {k:v for k,v in unit_meta.items() if k != 'man_deep'}
            owners = lambda u: {area:p['pid'] if p else None for area,p in Z.owners(name, u, [], P.rate).items()}
            self.assertEqual(owners(unit_meta), owners(legacy))
            self.assertTrue(any(owners(unit_meta).get(k) in ('FS', 'SS')
                                for k in ('deep_L', 'deep_M', 'deep_R')))


if __name__ == '__main__':
    unittest.main()

"""Paired rating changes at the live fumble/return/pass entry points."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import events as E
import game as G
import kick_returns as KR
import plays as P
from test_coverage_recording import offense
from test_defensive_rush import unit, call


class HitPowerTests(unittest.TestCase):
    def test_contact_actor_and_neutral_missing_context(self):
        off = offense()
        off['wr'].append(dict(pid='receiver', pos='WR'))
        defense = dict(dl=[dict(pid='rusher', hit_power_rating=95)],
                       lb=[dict(pid='tackler', hit_power_rating=30)], db=[])
        for kind, actor, expected in [('run', 'tackler', .46),
                                      ('complete', 'tackler', .46),
                                      ('scramble', 'tackler', .46),
                                      ('sack', 'rusher', .85),
                                      ('run', 'bench', .70)]:
            out = dict(type=kind, target='receiver', carrier_pid='H',
                       tackler=actor, by=actor, yards=3)
            with patch.object(E, 'fumble_check', return_value=None) as check:
                G._prepare_fumble(NS(yardline=65), out, off, defense,
                                  np.random.default_rng(4), P.rate)
            self.assertAlmostEqual(check.call_args.kwargs['hit_power'], expected)
            if kind == 'complete':
                self.assertEqual(check.call_args.args[0]['pid'], 'receiver')

    def test_hit_power_changes_live_fumbles_for_each_contact_type(self):
        totals = {}
        for kind in ('run', 'complete', 'sack', 'scramble'):
            for hit in (30, 70, 95):
                count = 0
                for seed in range(4000):
                    out = dict(type=kind, target='W0', tackler='D', by='D', yards=3)
                    G._prepare_fumble(NS(yardline=65), out, offense(),
                        dict(dl=[dict(pid='D', hit_power_rating=hit)]),
                        np.random.default_rng(seed), P.rate)
                    count += bool(out.get('fumble'))
                totals[kind, hit] = count
            self.assertLess(totals[kind, 30], totals[kind, 70])
            self.assertLess(totals[kind, 70], totals[kind, 95])

    def test_return_uses_same_contact_for_impact_and_credit(self):
        cover = [dict(pid='low', hit_power_rating=30),
                 dict(pid='high', hit_power_rating=95)]
        for event in ('kick_return', 'punt_return'):
            seen = set()
            for seed in range(12):
                with patch.object(E, 'fumble_check', return_value=dict(lost=True, forced=True)) as check:
                    result = KR.resolve(90, 25, dict(pid='R'),
                        np.random.default_rng(seed), P.rate, cover, event=event)
                seen.add(result['tackler'])
                self.assertAlmostEqual(check.call_args.kwargs['hit_power'],
                    .46 if result['tackler'] == 'low' else .85)
                self.assertEqual(result['recoverer'], result['tackler'])
                book = G.StatBook()
                KR.book_return(book, 'kr' if event == 'kick_return' else 'pr', result)
                self.assertEqual(book.p[result['tackler']]['ff'], 1)
                self.assertEqual(book.p['R']['fumbles_lost'], 1)
                self.assertFalse(result['touchdown'])
            self.assertEqual(seen, {'low', 'high'})

    def test_return_hit_power_changes_fumbles_not_untouched_distance(self):
        for event in ('kick_return', 'punt_return'):
            counts = []
            for hit in (30, 70, 95):
                rows = [KR.resolve(90, 25, dict(pid='R'), np.random.default_rng(seed),
                        P.rate, [dict(pid='D', hit_power_rating=hit)], event=event)
                        for seed in range(6000)]
                counts.append(sum(r['fumble'] for r in rows))
                # Ordinary returns retain their distance; the separately
                # modeled breakaway branch can legitimately add yards.
                self.assertTrue(all(r['ret'] == 25 for r in rows
                                    if not r['fumble'] and not r.get('breakaway_opportunity')))
                self.assertTrue(all(0 <= r['new_yardline'] <= 90 for r in rows))
            self.assertLess(counts[0], counts[1])
            self.assertLess(counts[1], counts[2])


class DefenderCatchTests(unittest.TestCase):
    def test_no_coverage_actor_cannot_receive_an_interception(self):
        import targets
        off = offense()
        dc = dict(call(), shell='cover_1', coverage='cover_1', man=True)
        oc = dict(is_pass=True, personnel='11', depth='medium')
        attempts = 0
        with patch.object(targets, 'select_target', return_value=(off['wr'][0], None, 'first', .4)), \
             patch.object(P, 'resolve_throw', return_value=dict(result='interception',
                 contested=True, p=.6, base=.5, int_roll=.01, p_int=.1)):
            for seed in range(30):
                result = P.resolve_play(off, unit(), oc, dc, 65, np.random.default_rng(seed))
                self.assertNotEqual(result['type'], 'interception')
                attempts += result['type'] == 'incomplete'
        self.assertGreater(attempts, 0)

    def test_paired_man_and_zone_hands_affect_only_failed_passes(self):
        for man in (False, True):
            dc = dict(call('4-3', 'nickel'), shell='cover_1' if man else 'cover_2',
                      coverage='cover_1' if man else 'cover_2', man=man)
            oc = dict(is_pass=True, personnel='11', depth='medium')
            totals = [0, 0, 0]
            for seed in range(900):
                outcomes = []
                for index, catch in enumerate((30, 70, 95)):
                    defense = unit('4-3', 'nickel')
                    for group in ('dl', 'lb', 'db'):
                        for player in defense[group]: player['catch_rating'] = catch
                    for assignment in defense['defensive_assignments']:
                        assignment['player']['catch_rating'] = catch
                    result = P.resolve_play(offense(), defense, oc, dc, 65,
                                            np.random.default_rng(seed))
                    outcomes.append(result)
                    totals[index] += result['type'] == 'interception'
                    if result['type'] == 'interception':
                        self.assertIn(result['by'], {row[0] for row in result['coverage_evidence']['drops']})
                        self.assertTrue(0 <= result['end_spot'] <= 100)
                if outcomes[1]['type'] in ('complete', 'drop', 'sack'):
                    self.assertEqual(outcomes[0], outcomes[1])
                    self.assertEqual(outcomes[1], outcomes[2])
                if outcomes[0]['type'] == 'interception':
                    self.assertEqual(outcomes[1]['type'], 'interception')
                    self.assertEqual(outcomes[2]['type'], 'interception')
                if outcomes[1]['type'] == 'interception' and outcomes[0]['type'] != 'interception':
                    self.assertEqual(outcomes[0]['type'], 'incomplete')
                    self.assertEqual(outcomes[0]['pass_def'], outcomes[1]['by'])
                    self.assertFalse(outcomes[0]['throwaway'])
            self.assertLess(totals[0], totals[1], (man, totals))
            self.assertLess(totals[1], totals[2], (man, totals))

    def test_missing_hands_is_identical_to_neutral_hands_and_rng(self):
        dc = dict(call(), shell='cover_1', coverage='cover_1', man=True)
        oc = dict(is_pass=True, personnel='11', depth='deep')
        for seed in range(100):
            defense = unit()
            rng = np.random.default_rng(seed)
            a = P.resolve_play(offense(), defense, oc, dc, 65, rng)
            state = copy.deepcopy(rng.bit_generator.state)
            for group in ('dl', 'lb', 'db'):
                for player in defense[group]: player['catch_rating'] = 70
            for assignment in defense['defensive_assignments']:
                assignment['player']['catch_rating'] = 70
            rng = np.random.default_rng(seed)
            b = P.resolve_play(offense(), defense, oc, dc, 65, rng)
            self.assertEqual(a, b)
            self.assertEqual(state, rng.bit_generator.state)


if __name__ == '__main__': unittest.main()

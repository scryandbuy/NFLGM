"""Final coverage responsibility is evidence, never a new outcome decision."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import advanced_stats as AS
import defensive_rush as R
import game as G
import league as LG
import plays as P
from test_defensive_rush import unit, call


METRICS = ('targets', 'completions', 'air_yards', 'td', 'explosive', 'pd', 'ints')


def offense():
    return dict(qb=dict(pid='Q', pos='QB'), rb=dict(pid='H', pos='HB'),
                wr=[dict(pid='W'+str(i), pos='WR') for i in range(3)] + [dict(pid='T', pos='TE')],
                ol=[dict(pid=p, pos=p) for p in ('LT', 'LG', 'C', 'RG', 'RT')])


def evidence(**kw):
    return dict(version=1, drops=[('CB', 'outside', 'man'), ('S', 'safety', 'zone')],
                primary='CB', helper='S', mode='man', hole=False) | kw


def outcome(**kw):
    return dict(type='complete', target='W', depth='short', air=4., yac=26., yards=30.,
                touchdown=False, tackler='S', coverage_evidence=evidence()) | kw


class CoverageRecordingTests(unittest.TestCase):
    def test_final_owner_overrides_provisional_pair(self):
        d = R.select_rush(unit('4-3', 'nickel'), call('4-3', 'nickel'))['coverage']
        players = {p['pid']:p for group in R.GROUPS for p in d[group]}
        pair = dict(defender=players['CBL'], spot='X', man=False)
        e = P._coverage_evidence(d, [pair], players['FS'], players['SS'])
        self.assertEqual((e['primary'], e['helper']), ('FS', 'SS'))
        self.assertNotIn('LE', {row[0] for row in e['drops']})
        self.assertIsNone(P._coverage_evidence(d, [pair], players['FS'], hole=True)['primary'])

    def test_actual_travel_matchup_gets_slot_exposure(self):
        d = R.select_rush(unit(), call())['coverage']
        cb = next(p for p in d['db'] if p['pid']=='CBL')
        e = P._coverage_evidence(d, [dict(defender=cb, spot='slot', man=True)], cb, cb, True)
        self.assertIn(('CBL', 'slot', 'man'), e['drops'])
        self.assertIsNone(e['helper'])

    def test_quarters_match_keeps_safety_help_in_zone(self):
        d = R.select_rush(unit(), call())['coverage']
        cb, safety = d['db'][0], d['db'][2]
        e = P._coverage_evidence(d, [], cb, safety, True)
        modes = {pid:mode for pid,role,mode in e['drops']}
        self.assertEqual(modes[cb['pid']], 'man')
        self.assertEqual(modes[safety['pid']], 'zone')

    def test_ambiguous_multi_assignment_does_not_depend_on_pair_order(self):
        d = R.select_rush(unit(), call())['coverage']
        cb = d['db'][0]
        pairs = [dict(defender=cb, spot=spot, man=True) for spot in ('X','slot')]
        a = P._coverage_evidence(d, pairs, cb, in_man=True)
        b = P._coverage_evidence(d, list(reversed(pairs)), cb, in_man=True)
        self.assertEqual(a, b)
        self.assertIn((cb['pid'], 'other', 'man'), a['drops'])

    def test_each_bucket_has_all_metrics_including_zeroes(self):
        b = G.StatBook()
        for mode in ('man', 'zone'):
            for depth in ('short', 'medium', 'deep'):
                b.record_coverage(outcome(type='incomplete', depth=depth, coverage_evidence=evidence(mode=mode)))
                prefix = 'cov_'+mode+'_'+depth+'_'
                self.assertEqual({k:b.p['CB'][prefix+k] for k in METRICS},
                                 dict(targets=1, completions=0, air_yards=0, td=0, explosive=0, pd=0, ints=0))
        self.assertEqual(b.p['CB']['cov_targets'], 6)

    def test_helper_is_not_charged_primary_target_or_completion(self):
        for kind, actor_key, credit in (('incomplete', 'pass_def', 'pd'), ('interception', 'by', 'ints')):
            b = G.StatBook()
            b.record_coverage(outcome(type=kind, **{actor_key:'S'}))
            self.assertEqual(b.p['CB']['cov_targets'], 1)
            self.assertEqual(b.p['CB']['cov_'+credit], 0)
            self.assertEqual(b.p['S']['cov_help_'+credit], 1)
            self.assertNotIn('cov_targets', b.p['S'])

    def test_primary_breakup_and_interception_credit(self):
        b = G.StatBook()
        b.record_coverage(outcome(type='incomplete', pass_def='CB'))
        b.record_coverage(outcome(type='interception', by='CB'))
        self.assertEqual((b.p['CB']['cov_pd'], b.p['CB']['cov_ints']), (1, 1))

    def test_uncovered_zone_has_no_individual_target_charge(self):
        b = G.StatBook()
        b.record_coverage(outcome(coverage_evidence=evidence(hole=True)))
        self.assertTrue(all('cov_targets' not in row for row in b.p.values()))
        self.assertEqual(b.p['CB']['cov_snaps'], 1)

    def test_yac_touchdown_and_explosive_are_separate(self):
        b = G.StatBook()
        b.record_coverage(outcome(touchdown=True))
        row = b.p['CB']
        self.assertEqual((row['cov_air_yards'], row['cov_yac_yards']), (4, 26))
        self.assertEqual((row['cov_td'], row['cov_explosive']), (0, 0))
        self.assertEqual((row['cov_receiving_td'], row['cov_receiving_explosive']), (1, 1))
        b.record_coverage(outcome(air=30, yac=0, touchdown=True, coverage_air_td=True))
        self.assertEqual((row['cov_td'], row['cov_explosive']), (1, 1))

    def test_negative_screen_air_is_preserved(self):
        b = G.StatBook()
        b.record_coverage(outcome(air=-3, yac=8, yards=5))
        self.assertEqual(b.p['CB']['cov_man_short_air_yards'], -3)

    def test_nullified_spike_throwaway_and_legacy_are_excluded(self):
        for kw in ({'nullified':True}, {'spike':True}, {'throwaway':True},
                   {'type':'spike'}, {'type':'run'}, {'coverage_evidence':None}):
            b = G.StatBook(); b.record_coverage(outcome(**kw))
            self.assertEqual(b.p, {})

    def test_sack_scramble_exposure_and_duplicate_guard(self):
        for kind in ('sack', 'scramble'):
            b = G.StatBook()
            e = evidence(drops=[('CB', 'outside', None)]*2)
            b.record_coverage(outcome(type=kind, coverage_evidence=e))
            self.assertEqual(b.p['CB']['cov_snaps'], 1)
            self.assertEqual(b.p['CB']['cov_unknown_snaps'], 1)
            self.assertNotIn('cov_targets', b.p['CB'])

    def test_live_drive_keeps_coverage_when_sack_becomes_scramble(self):
        import events
        from test_game_clock_decisions import ClockDecisions
        fixture = ClockDecisions(); fixture.setUp()
        e = evidence(drops=[('cb', 'outside', None)], primary=None, helper=None)
        with patch.object(events, 'scramble_chance', return_value=1), \
             patch.object(events, 'resolve_scramble', return_value=dict(type='scramble', yards=36, touchdown=True)):
            dr, book, _ = fixture.drive([dict(type='sack', yards=-4, by='cb', coverage_evidence=e)])
        snap = next(p for p in dr.log if p.get('type')=='scramble')
        self.assertEqual(snap['coverage_evidence'], e)
        self.assertEqual(book.p['cb']['cov_snaps'], 1)
        self.assertNotIn('cov_targets', book.p['cb'])

    def test_main_and_advanced_book_do_not_duplicate(self):
        b = G.StatBook(); off = offense(); defense = unit()
        o = outcome(); rng = np.random.default_rng(11)
        b.record(o, off, defense, rng)
        AS.book_play(b, o, off, defense, .2)
        self.assertEqual(b.p['CB']['cov_targets'], 1)

    def test_game_season_career_and_save_preserve_complete_buckets(self):
        b = G.StatBook(); b.record_coverage(outcome(type='incomplete'))
        league = LG.League(2027)
        league.players['CB'] = LG.Player('CB', 'Coverage Test', 'CB', 25, {}, team='GB')
        league.record_stats(2027, 'CB', b.p['CB'], game='2027-8-GB-DAL')
        restored = LG.League.load(league.save())
        for row in (restored.stats[2027]['CB'], restored.game_stats['2027-8-GB-DAL']['CB'],
                    restored.players['CB'].career[2027]):
            for metric in METRICS:
                self.assertEqual(row['cov_man_short_'+metric], b.p['CB']['cov_man_short_'+metric])
            self.assertEqual(row['cov_outside_snaps'], 1)

    def test_seeded_fronts_packages_and_calls_keep_rng_and_outcomes(self):
        kinds = set()
        off = offense()
        for front in ('3-4', '4-3'):
            for package in ('base', 'nickel', 'dime'):
                d = unit(front, package)
                for depth in ('short', 'medium', 'deep'):
                    for man in (False, True):
                        dc = dict(call(front, package), shell='cover_1' if man else 'cover_2',
                                  coverage='cover_1' if man else 'cover_2', man=man)
                        oc = dict(is_pass=True, personnel='11', depth=depth)
                        for seed in range(10):
                            rng = np.random.default_rng(seed)
                            recorded = P.resolve_play(off, d, oc, dc, 65, rng)
                            state = copy.deepcopy(rng.bit_generator.state)
                            rng = np.random.default_rng(seed)
                            with patch.object(P, '_coverage_evidence', return_value=None):
                                original = P.resolve_play(off, d, oc, dc, 65, rng)
                            self.assertEqual(state, rng.bit_generator.state)
                            e = recorded.pop('coverage_evidence')
                            original.pop('coverage_evidence')
                            self.assertEqual(recorded, original)
                            drops = {row[0] for row in e['drops']}
                            rush = {pid for pid, won in recorded['pr_reps']}
                            self.assertFalse(drops & rush)
                            self.assertEqual(len(drops | rush), 11)
                            if e['primary']: self.assertIn(e['primary'], drops)
                            kinds.add(recorded['type'])
        self.assertTrue({'complete', 'incomplete', 'sack'} <= kinds)


if __name__ == '__main__': unittest.main()

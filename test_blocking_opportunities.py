"""Contested protection evidence, including helpers and unmatched blockers."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import awards
import defensive_rush as D
import dev_evaluation as DE
import game as G
import league as LG
import plays as P
import xp
from test_defensive_rush import unit, call
from test_protection_pressure import blocker


class BlockingOpportunityTests(unittest.TestCase):
    def setUp(self):
        self.blockers = [blocker(p) for p in ('LT', 'LG', 'C', 'RG', 'RT')]
        self.defense = unit('4-3', 'base')

    def resolve(self, plan=None, **kw):
        plan = plan or D.select_rush(self.defense, call('4-3', 'base'))
        return P.resolve_protection(self.blockers, plan['rushers'],
            np.random.default_rng(5), assignments=plan['assignments'], **kw)

    def test_three_man_edge_blitz_does_not_award_unengaged_center(self):
        plan = D.select_rush(self.defense, call('4-3', 'base', 3, blitzer_ids=['LB0']))
        result = self.resolve(plan)
        self.assertEqual(dict(result['pb_opportunities'])['C'], 'unengaged')
        self.assertNotIn('C', dict(result['pb_reps']))
        self.assertEqual(len(result['pb_opportunities']), 5)
        self.assertEqual(len(result['pb_reps']), 4)

    def test_zero_rush_records_no_contested_wins(self):
        result = self.resolve(dict(rushers=[], assignments=[]))
        self.assertEqual(result['pb_reps'], [])
        self.assertEqual(dict(result['pb_opportunities']), {p['pid']: 'unengaged' for p in self.blockers})
        self.assertEqual((result['time'], result['pressure'], result['sack']), (6., 0., False))

    def test_helpers_and_primary_share_assisted_result_without_discount(self):
        plan = D.select_rush(self.defense, call('4-3', 'base'))
        pairs = D.protection_pairs(self.blockers, plan['assignments'])
        primary = {r['pid']: b['pid'] for r, b in zip(plan['rushers'], pairs) if b}
        result = self.resolve(plan)
        kinds, wins = dict(result['pb_opportunities']), dict(result['pb_reps'])
        self.assertTrue(result['pb_helpers'])
        for helper, rusher in result['pb_helpers']:
            self.assertEqual(kinds[helper], 'assisted')
            self.assertEqual(kinds[primary[rusher]], 'assisted')
            self.assertEqual(wins[helper], wins[primary[rusher]])
        self.assertIn('solo', kinds.values())

    def test_chip_marks_primary_assisted_without_fabricating_chipper_rep(self):
        plan = D.select_rush(self.defense, call('4-3', 'base'))
        pairs = D.protection_pairs(self.blockers, plan['assignments'])
        result = self.resolve(plan, chip=(blocker('TE'), 0))
        self.assertEqual(dict(result['pb_opportunities'])[pairs[0]['pid']], 'assisted')
        self.assertNotIn('TE', dict(result['pb_reps']))
        self.assertNotIn('TE', dict(result['pb_opportunities']))

    def test_all_outcomes_book_contested_and_unengaged_separately(self):
        for kind in ('complete', 'incomplete', 'drop', 'interception', 'sack', 'scramble'):
            with self.subTest(kind=kind):
                book = G.StatBook()
                out = dict(type=kind, yards=3, target='wr', by='edge', beaten='lt',
                    tackler='corner', pressured=True,
                    pb_reps=[('lt', False), ('lg', True), ('rt', True)],
                    pb_opportunities=[('lt', 'solo'), ('lg', 'assisted'),
                                      ('rt', 'assisted'), ('c', 'unengaged')])
                book.record(out, dict(qb={'pid': 'qb'}),
                            dict(dl=[{'pid': 'edge'}], lb=[], db=[{'pid': 'corner'}]),
                            np.random.default_rng(1))
                for pid, snaps, wins in (('lt', 1, 0), ('lg', 1, 1), ('rt', 1, 1), ('c', 0, 0)):
                    line = book.p[pid]
                    self.assertEqual((line['pb_snaps'], line['pb_wins']), (snaps, wins))
                    self.assertEqual(line['pb_solo_snaps'] + line['pb_assisted_snaps'], snaps)
                    self.assertEqual(line['pb_solo_wins'] + line['pb_assisted_wins'], wins)
                self.assertEqual(book.p['c']['pb_unengaged_snaps'], 1)
                self.assertEqual(book.p['c']['pressures_allowed'], 0)
                self.assertEqual(book.p['c']['sacks_allowed'], 0)

    def test_nullified_play_records_no_opportunity(self):
        book = G.StatBook()
        book.record(dict(type='sack', nullified=True, pb_reps=[('lt', False)],
                         pb_opportunities=[('lt', 'solo'), ('c', 'unengaged')]),
                    {}, {}, np.random.default_rng(1))
        self.assertEqual(book.p, {})

    def test_live_sack_to_scramble_keeps_opportunities_without_sack_charge(self):
        import events
        from test_game_clock_decisions import ClockDecisions
        fixture = ClockDecisions(); fixture.setUp()
        opportunities = [('lt', 'solo'), ('c', 'unengaged')]
        with patch.object(events, 'scramble_chance', return_value=1), \
             patch.object(events, 'resolve_scramble', return_value=dict(type='scramble', yards=36, touchdown=True)):
            dr, book, _ = fixture.drive([dict(type='sack', yards=-4, by='cb', beaten='lt',
                pb_reps=[('lt', False)], pb_opportunities=opportunities, pressured=True)])
        snap = next(p for p in dr.log if p.get('type') == 'scramble')
        self.assertEqual(snap['pb_opportunities'], opportunities)
        self.assertEqual(book.p['lt']['pb_solo_snaps'], 1)
        self.assertEqual(book.p['lt']['pressures_allowed'], 1)
        self.assertEqual(book.p['lt']['sacks_allowed'], 0)
        self.assertEqual(book.p['c']['pb_unengaged_snaps'], 1)
        self.assertEqual(book.p['c']['pb_snaps'], 0)

    def test_legacy_book_retains_aggregate_without_inventing_split(self):
        book = G.StatBook()
        book.record(dict(type='incomplete', pb_reps=[('lt', True)]),
                    dict(qb={'pid': 'qb'}), {}, np.random.default_rng(1))
        line = book.p['lt']
        self.assertEqual((line['pb_snaps'], line['pb_wins']), (1, 1))
        self.assertEqual((line['pb_solo_snaps'], line['pb_assisted_snaps'], line['pb_unengaged_snaps']), (0, 0, 0))

    def test_new_counters_add_to_legacy_totals_and_survive_save_load(self):
        league = LG.League(2027)
        league.players['lt'] = LG.Player('lt', 'Test Tackle', 'LT', 25, {}, team='GB')
        league.record_stats(2027, 'lt', dict(pb_snaps=200, pb_wins=180), game='2027-1-GB-DAL')
        line = dict(pb_snaps=3, pb_wins=2, pb_solo_snaps=1, pb_solo_wins=0,
                    pb_assisted_snaps=2, pb_assisted_wins=2, pb_unengaged_snaps=4)
        league.record_stats(2027, 'lt', line, game='2027-2-GB-DAL')
        restored = LG.League.load(league.save())
        for value in (restored.stats[2027]['lt'], restored.players['lt'].career[2027]):
            self.assertEqual((value['pb_snaps'], value['pb_wins']), (203, 182))
            for key in line:
                if key not in ('pb_snaps', 'pb_wins'):
                    self.assertEqual(value[key], line[key])
        saved_game = restored.game_stats['2027-2-GB-DAL']['lt']
        for key, value in line.items():
            self.assertEqual(saved_game.get(key, 0), value)

    def test_awards_development_and_xp_ignore_unengaged_time(self):
        p = SimpleNamespace(pos='C')
        idle = dict(pb_unengaged_snaps=600)
        self.assertIsNone(awards.Ballot.line_score(None, p, idle))
        self.assertIsNone(DE.assessment(p, idle))
        self.assertEqual(xp.event_xp(idle), 0)
        contested = dict(pb_snaps=200, pb_wins=180, rb_snaps=300, rb_wins=180,
                         sacks_allowed=1, pressures_allowed=10)
        extra = dict(contested, **idle)
        self.assertEqual(awards.Ballot.line_score(None, p, contested), awards.Ballot.line_score(None, p, extra))
        self.assertEqual(DE.assessment(p, contested), DE.assessment(p, extra))
        self.assertEqual(xp.event_xp(contested), xp.event_xp(extra))

    def test_live_pass_outcomes_preserve_protection_evidence_including_screens(self):
        import rosters
        import schemes
        teams = rosters.load_league()
        off, _ = G.field_units(teams['GB'], None, np.random.default_rng(0), True, '11')
        defense, _ = G.field_units(teams['BUF'], None, np.random.default_rng(0), False, 'nickel', '4-3')
        seen = set()
        for screen in (False, True):
            for seed in range(150):
                rng = np.random.default_rng(seed)
                oc = dict(is_pass=True, personnel='11', depth='short' if screen else 'deep',
                          concept='screen' if screen else 'four_verts', down=2, ydstogo=8,
                          play_action=False, shotgun=True)
                dc = schemes.call_defense(oc, 2, 8, rng)
                dc.update(front_family='4-3', personnel='nickel', rushers=4)
                with patch.object(P, 'resolve_protection', wraps=P.resolve_protection) as protect:
                    out = P._pass_play(off, defense, oc, dc, 50, rng)
                self.assertTrue(protect.called)
                self.assertEqual(len(out['pb_opportunities']), len(protect.call_args.args[0]))
                seen.add((out['type'], bool(out.get('screen'))))
        self.assertTrue({('sack', False), ('incomplete', False), ('interception', False),
                         ('drop', False), ('complete', False), ('complete', True)} <= seen, seen)


if __name__ == '__main__':
    unittest.main()

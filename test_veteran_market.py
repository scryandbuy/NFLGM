import copy
import unittest
from unittest.mock import patch

import numpy as np
import veteran_market as VM
import market as MK
import character_assessment as CA
from league import League
from test_draft_planning import fixture, set_grade


class VeteranMarketTests(unittest.TestCase):
    def setUp(self):
        self.L, self.t = fixture()
        self.L.week = 0
        self.rng = np.random.default_rng(511)
        self.addCleanup(patch.stopall)
        patch.object(MK.VAL, 'pool_from_league', return_value=None).start()
        patch.object(MK.VAL, 'value_player', return_value=dict(apy=8., years=1)).start()

    def candidate(self, pos='WR', grade=95, pid='veteran'):
        p = copy.deepcopy(self.t.by_pos(pos)[0])
        p.pid = p.name = pid
        p.team = p.contract = p.out_until = None
        p.fa_class = 'UFA'; p.tender_team = None; p.accrued = 5
        p.xp_spent = {}
        set_grade(p, grade)
        self.L.players[pid] = p; self.L.free_agents.append(pid)
        return p

    def test_paid_upgrade_keeps_53_and_caps_legal(self):
        p = self.candidate(); size = len(self.t.active())
        moves = VM.review(self.L, self.rng, 'wire')
        self.assertEqual(len(moves), 1)
        self.assertEqual(p.team, 'MIN')
        self.assertGreater(p.apy, 3.)
        self.assertEqual(len(self.t.active()), size)
        self.assertGreaterEqual(self.t.cap_space, 0)
        self.assertIsNotNone(moves[0][2])
        records = [tx for tx in self.L.transactions if tx.get('pid') == p.pid and tx['kind'] == 'sign']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['market_stage'], 'wire')
        self.assertTrue(records[0]['replacement_assessment']['approved'])
        self.assertIn('released_asset_value', records[0]['replacement_assessment'])

    def test_reviews_survive_save_reload_without_repeating(self):
        self.candidate()
        VM.review(self.L, self.rng, 'wire')
        loaded = League.load(self.L.save())
        state = copy.deepcopy(self.rng.bit_generator.state)
        tx = len(loaded.transactions)
        self.assertEqual(VM.review(loaded, self.rng, 'wire'), [])
        self.assertEqual(len(loaded.transactions), tx)
        self.assertEqual(self.rng.bit_generator.state, state)

    def test_recent_preseason_signing_is_not_cut_or_buried(self):
        for p in self.t.by_pos('WR'):
            self.L.transactions.append(dict(year=self.L.year, week=22,
                phase='free_agency', kind='sign', pid=p.pid, team='MIN'))
        before = [p.pid for p in self.t.active()]
        self.candidate()
        self.assertEqual(VM.review(self.L, self.rng, 'camp'), [])
        self.assertEqual([p.pid for p in self.t.active()], before)

    def test_recent_trade_counts_as_commitment(self):
        self.L.transactions.append(dict(year=self.L.year, week=22, phase='free_agency',
            kind='trade', a='MIN', b='GB', a_sends=[], b_sends=['WR0']))
        self.assertIn('WR0', VM.recent_commitments(self.L, self.t, 0))
        self.L.set_phase('regular')
        self.assertIn('WR0', VM.recent_commitments(self.L, self.t, 3))
        self.assertNotIn('WR0', VM.recent_commitments(self.L, self.t, 4))

    def test_camp_signing_does_not_disable_later_cutdown_claims(self):
        p = self.candidate(); self.L.week = 22
        self.assertTrue(VM.review(self.L, self.rng, 'camp'))
        self.assertNotEqual(getattr(self.t, '_moved_week', None), 0)
        self.L.week = 0
        self.assertIn(p.pid, VM.PS._recent_additions(self.L, self.t))
        self.L.transactions.append(dict(year=self.L.year, week=0, phase='free_agency',
            kind='waiver_claim', pid='WR1', team='MIN'))
        self.assertIn('WR1', VM.recent_commitments(self.L, self.t, 0))

    def test_commitments_survive_offseason_rollover_but_not_completed_season(self):
        self.L.set_phase('free_agency')
        self.L.transactions=[dict(year=self.L.year-1,week=22,phase='offseason',
            kind='trade',a='MIN',b='GB',a_sends=[],b_sends=['WR0'])]
        self.assertIn('WR0',VM.recent_commitments(self.L,self.t,0))
        self.assertIn('WR0',VM.PS._recent_additions(self.L,self.t))
        self.L.set_phase('regular');self.L.week=1
        self.assertIn('WR0',VM.recent_commitments(self.L,self.t,1))
        self.L.week=4
        self.assertNotIn('WR0',VM.recent_commitments(self.L,self.t,4))
        self.L.transactions.append(dict(year=self.L.year,week=18,phase='regular',kind='game'))
        self.L.set_phase('offseason')
        self.assertNotIn('WR0',VM.recent_commitments(self.L,self.t,0))

    def test_user_pending_waivers_injuries_and_talks_are_protected(self):
        p = self.candidate()
        self.assertEqual(VM.review(self.L, self.rng, 'camp', user_team='MIN'), [])
        self.L.notes_sent = {}
        self.L.waivers = [dict(pid=p.pid, year=self.L.year, week=0, claims=[], from_team='GB')]
        self.assertEqual(VM.review(self.L, self.rng, 'camp'), [])
        self.L.notes_sent = {}; self.L.waivers = []; p.out_until = 3
        self.assertEqual(VM.review(self.L, self.rng, 'camp'), [])
        self.L.notes_sent = {}; p.out_until = None
        with patch('negotiations._threads', return_value=[dict(pid=p.pid,team='GB',state='waiting')]):
            self.assertEqual(VM.review(self.L, self.rng, 'camp'), [])
        self.assertIsNone(p.team)

    def test_player_refusal_never_releases_incumbent(self):
        self.candidate(); before = [p.pid for p in self.t.active()]
        with patch('contract_offer.assess', return_value={'acceptable': False}):
            self.assertEqual(VM.review(self.L, self.rng, 'wire'), [])
        self.assertEqual(before, [p.pid for p in self.t.active()])

    def test_unfunded_move_never_releases_incumbent(self):
        self.candidate(); before = [p.pid for p in self.t.active()]
        self.t.sync_cap(); self.t.cap.dead += self.t.cap_space
        self.assertEqual(VM.review(self.L, self.rng, 'wire'), [])
        self.assertEqual(before, [p.pid for p in self.t.active()])

    def test_specialist_can_receive_market_contract(self):
        p = self.candidate('K'); set_grade(self.t.by_pos('K')[0], 60)
        with patch.object(MK.VAL, 'value_player', return_value=dict(apy=3.,years=1)):
            moves = VM.review(self.L, self.rng, 'wire')
        self.assertEqual(len(moves), 1)
        self.assertEqual(p.team, 'MIN')
        self.assertEqual(len(self.t.by_pos('K')), 1)

    def test_weekly_review_runs_in_its_calendar_window_only(self):
        p = self.candidate(); self.L.set_phase('regular')
        self.L.week = 3
        self.assertTrue(VM.review(self.L, self.rng, 'weekly', week=3))
        self.assertEqual(VM.review(self.L, self.rng, 'weekly', week=3), [])
        self.assertEqual(p.team, 'MIN')
        self.assertEqual(VM.review(self.L, self.rng, 'weekly', week=18), [])

    def test_native_depth_bonus_cannot_pay_for_a_worse_playing_lineup(self):
        p = self.candidate()
        before = VM.RN.assess(self.t)
        after = copy.copy(before)
        after['score'] += 4
        after['_package_scores'] = dict(before['_package_scores'])
        after['_package_scores']['offense'] -= 1
        with patch.object(VM.RN, 'assess', return_value=after), \
             patch.object(VM.PS, '_room_candidates', return_value=iter([self.t.by_pos('WR')[0]])):
            self.assertIsNone(VM._proposal(self.L, self.t, p, dict(apy=8,years=1),
                                          before, set(), {}, {}))


class ConfidentCharacterFlagTests(unittest.TestCase):
    def view(self, value, error):
        return {'character_assessments': {k: dict(value=value, error=error,
            source='Visit and references') for k in CA.KEYS}}

    def test_limited_and_moderate_reads_never_become_flags(self):
        for error in (18., 13., 7.1):
            for value in (0., 100.):
                view = self.view(value, error)
                self.assertEqual(CA.flags(view), [])
                self.assertNotEqual(CA.report(view)[0]['status'], 'unknown')

    def test_strong_read_needs_clear_distance_from_cutoff(self):
        self.assertEqual(CA.flags(self.view(34., 6.)), [])
        self.assertEqual(CA.flags(self.view(71., 7.)), [])
        self.assertEqual(CA.flags(self.view(10., 6.)),
                         ['Work ethic concern', 'Discipline concern'])
        self.assertEqual(CA.flags(self.view(90., 6.)),
                         ['Strong preparation', 'Plays under control'])

    def test_legacy_flags_cannot_bypass_confidence(self):
        view = dict(flags=['character'], character_read=10)
        self.assertEqual(CA.flags(view), [])


if __name__ == '__main__':
    unittest.main()

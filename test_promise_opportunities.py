"""Controlled club decisions through the real promise, offer and save paths."""
import copy
import json
import unittest

import contract_offer as CO
import market as MK
import morale as MO
import negotiations as NG
from cap_engine import Contract
from gm_engine import GM
from league import League
from session import Session
from test_cap_accounting import fixture, player


class PromiseOpportunities(unittest.TestCase):
    def setUp(self):
        self.L = fixture()
        self.L.user_team = 'GB'
        for t in self.L.teams.values(): t.gm = GM()
        self.p = player(self.L, 'candidate', contract=Contract(2, [10, 10]))
        self.other = player(self.L, 'incumbent', contract=Contract(2, [12, 12]))
        self.L.teams['GB'].set_depth_order('QB', [self.other.pid, self.p.pid])
        for pos in ('LT', 'LG', 'C', 'RG', 'RT', 'HB', 'TE', 'TE', 'WR', 'WR', 'WR'):
            q = player(self.L, pos + str(len(self.L.players)), contract=Contract(2, [1, 1]))
            q.pos = pos
        MO.ensure(self.p)

    def legacy(self, kind, source=None, status='open'):
        pr = dict(pid=self.p.pid, team='GB', kind=kind, made=self.L.year,
                  year=None, status=status, source=source, orig=[0, 2])
        self.L.promises = [pr]
        return pr

    def test_new_exit_promise_survives_playoffs_reload_and_waits_for_next_season(self):
        self.L.set_phase('playoffs'); self.L.week = 19
        pr = NG.record_promise(self.L, self.p.pid, 'GB', 'starting_role', source='exit')
        self.assertEqual(pr['opportunity_year'], self.L.year + 1)
        for week in (19, 20, 21, 22): self.assertEqual(NG.check_promises(self.L, week), [])
        loaded = League.load(self.L.save())
        self.assertEqual(loaded.promises[0], json.loads(json.dumps(pr)))
        loaded.year += 1; loaded.set_phase('regular')
        NG.check_promises(loaded, 3)
        self.assertEqual(loaded.promises[0]['status'], 'open')
        NG.check_promises(loaded, 4)
        self.assertEqual(loaded.promises[0]['status'], 'broken')
        self.assertAlmostEqual(loaded.player(self.p.pid).morale.trust, .65)

    def test_legacy_exit_timing_migrates_once_and_does_not_rewrite_broken_history(self):
        pr = self.legacy('starting_role', 'exit')
        self.L.set_phase('playoffs')
        NG.check_promises(self.L, 19)
        self.assertEqual(pr['status'], 'open')
        self.assertEqual(pr['opportunity_year'], self.L.year + 1)
        old = dict(pr, status='broken', made=self.L.year - 1)
        old.pop('opportunity_year'); self.L.promises.append(old)
        before = copy.deepcopy(old)
        loaded = League.load(self.L.save())
        NG.check_promises(loaded, 20)
        self.assertEqual(loaded.promises[1], before)
        self.assertEqual(loaded.promises[0]['opportunity_year'], self.L.year + 1)

    def test_next_camp_starter_is_kept_after_sustained_role_and_injury_defers(self):
        pr = self.legacy('starting_role', 'exit')
        self.L.year += 1; self.L.set_phase('regular')
        self.p.out_until = 7
        NG.check_promises(self.L, 4)
        self.assertEqual(pr['status'], 'open')
        self.p.out_until = None
        self.L.teams['GB'].set_depth_order('QB', [self.p.pid, self.other.pid])
        NG.check_promises(self.L, 7)
        self.assertEqual(pr['status'], 'open')
        NG.check_promises(self.L, 8)
        self.assertEqual(pr['status'], 'kept')

    def test_installed_offensive_package_and_pins_decide_multiple_starter_jobs(self):
        team = self.L.teams['GB']; team.gm.off_personnel = '11'
        receivers = team.depth['WR']; target = receivers[2]
        NG.record_promise(self.L, target.pid, 'GB', 'starting_role')
        NG.check_promises(self.L, 9)
        self.assertEqual(self.L.promises[-1]['status'], 'kept', 'WR3 is a base 11 starter')
        team.gm.off_personnel = '12'
        self.assertFalse(MO.has_starting_role(team, target))
        self.assertTrue(MO.has_starting_role(team, team.depth['TE'][1]))
        team.set_depth_order('WR', [target.pid, receivers[0].pid, receivers[1].pid])
        self.assertTrue(MO.has_starting_role(team, target))

    def test_defensive_front_recognizes_second_corner_and_multiple_interior_starters(self):
        team = self.L.teams['MIN']
        for i, pos in enumerate(('LEDG', 'DT', 'DT', 'DT', 'REDG', 'MIKE', 'WILL', 'SAM', 'CB', 'CB', 'CB', 'FS', 'SS')):
            q = player(self.L, 'def' + str(i), team='MIN'); q.pos = pos
        team.gm.def_front = '4-3'
        corners, tackles = team.depth['CB'], team.depth['DT']
        self.assertTrue(MO.has_starting_role(team, corners[1]))
        self.assertFalse(MO.has_starting_role(team, corners[2]))
        self.assertTrue(MO.has_starting_role(team, tackles[1]))
        self.assertFalse(MO.has_starting_role(team, tackles[2]))
        team.gm.def_front = '3-4'
        self.assertTrue(MO.has_starting_role(team, tackles[2]))
        tackles[2].accrued = 0
        self.L.set_phase('preseason')
        NG.record_promise(self.L, tackles[2].pid, 'MIN', 'captaincy')
        self.assertEqual(MO.review_captains(self.L, week=0), [tackles[2].pid])

    def test_inseason_addition_gets_opportunity_instead_of_instant_failure(self):
        self.L.week = 9
        pr = NG.record_promise(self.L, self.p.pid, 'GB', 'starting_role')
        NG.check_promises(self.L, 9)
        self.assertEqual(pr['status'], 'open')
        self.assertEqual(pr['evaluate_week'], 13)
        NG.check_promises(self.L, 13)
        self.assertEqual(pr['status'], 'broken')

    def test_late_season_and_postseason_use_next_opportunity(self):
        self.L.week = 16
        pr = NG.record_promise(self.L, self.p.pid, 'GB', 'starting_role')
        NG.check_promises(self.L, 18)
        self.assertEqual(pr['status'], 'open')
        self.assertEqual(pr['opportunity_year'], self.L.year + 1)

    def test_explicit_future_year_uses_camp_window_not_current_week(self):
        self.L.week = 10
        pr = NG.record_promise(self.L, self.p.pid, 'GB', 'starting_role', year=self.L.year+1)
        self.assertEqual((pr['evaluate_week'], pr['keep_week']), (4, 8))
        NG.check_promises(self.L, 18)
        self.assertEqual(pr['status'], 'open')

    def test_repeated_open_promise_preserves_opportunity_and_duplicate_does_not_double_penalize(self):
        pr = self.legacy('starting_role')
        NG.promise_opportunity(pr)
        self.assertIs(NG.record_promise(self.L, self.p.pid, 'GB', 'starting_role', year=self.L.year+2), pr)
        self.L.promises.append(copy.deepcopy(pr))
        NG.check_promises(self.L, 4)
        self.assertEqual([p['status'] for p in self.L.promises], ['broken', 'superseded'])
        self.assertEqual(self.p.morale.broken, ['starting_role'])

    def test_no_trade_still_breaks_immediately_after_transfer(self):
        pr = self.legacy('no_trade')
        self.p.team = 'MIN'
        self.L.set_phase('playoffs')
        NG.check_promises(self.L, 20)
        self.assertEqual(pr['status'], 'broken')

    def test_user_action_fulfills_only_own_captain_promise_and_cannot_farm_reward(self):
        pr = self.legacy('captaincy', 'exit')
        s = Session.__new__(Session); s.L = self.L; s.user_team = 'GB'
        self.assertTrue(s.club_act('captain', pid=self.p.pid)['ok'])
        self.assertEqual(pr['status'], 'kept')
        value = self.p.morale.value
        for on in (True, False, True, True):
            self.assertTrue(s.club_act('captain', pid=self.p.pid, on=on)['ok'])
            self.assertEqual(self.p.morale.value, value)
        loaded = League.load(self.L.save()); s.L = loaded
        self.assertTrue(s.club_act('captain', pid=self.p.pid)['ok'])
        self.assertEqual(loaded.player(self.p.pid).morale.value, value)
        outsider = player(loaded, 'outsider', team='MIN')
        self.assertFalse(s.club_act('captain', pid=outsider.pid)['ok'])
        self.assertFalse(MO.is_captain(outsider))
        self.assertEqual(sum(t['kind'] == 'promise_kept' for t in loaded.transactions), 1)

    def test_assignment_rejects_free_agent_practice_only_and_retired_allows_ir(self):
        for state in ('free', 'practice', 'retired'):
            p = player(self.L, state, team=None if state == 'free' else 'GB')
            if state == 'practice':
                self.L.teams['GB'].roster.remove(p); self.L.teams['GB'].practice_squad.append(p)
            if state == 'retired': p.retired = True
            self.assertFalse(MO.set_captain(self.L, 'GB', p.pid)['ok'])
        self.L.teams['GB'].ir.append(self.p); self.p.out_until = 19
        self.assertTrue(MO.set_captain(self.L, 'GB', self.p.pid)['ok'])

    def test_cpu_honors_own_veteran_commitments_without_quota_or_user_changes(self):
        self.legacy('captaincy')
        ids = []
        self.L.set_phase('free_agency')
        for i in range(3):
            p = player(self.L, 'veteran' + str(i), team='MIN')
            NG.record_promise(self.L, p.pid, 'MIN', 'captaincy')
            ids.append(p.pid)
        self.assertEqual(MO.review_captains(self.L), [])
        self.assertEqual(MO.review_captains(self.L, week=0), ids)
        self.assertFalse(MO.is_captain(self.p))
        self.assertEqual(MO.review_captains(self.L, week=0), [])
        self.assertEqual(self.L.promises[0]['status'], 'open')

    def test_cpu_does_not_retain_or_promote_young_backup_to_honor_promise(self):
        self.L.set_phase('preseason')
        p = player(self.L, 'young', team='MIN'); p.accrued = 0
        incumbent = player(self.L, 'min_starter', team='MIN')
        self.L.teams['MIN'].set_depth_order('QB', [incumbent.pid, p.pid])
        pr = NG.record_promise(self.L, p.pid, 'MIN', 'captaincy')
        self.assertEqual(MO.review_captains(self.L, week=0), [])
        self.L.set_phase('regular')
        NG.check_promises(self.L, 2)
        self.assertEqual(pr['status'], 'broken')
        self.assertEqual(self.L.teams['MIN'].depth['QB'][0].pid, incumbent.pid)

    def test_cpu_next_camp_promise_not_fulfilled_during_playoffs(self):
        p = player(self.L, 'cpu', team='MIN')
        self.L.set_phase('playoffs')
        pr = NG.record_promise(self.L, p.pid, 'MIN', 'captaincy', source='exit')
        self.assertEqual(MO.review_captains(self.L, week=0), [])
        NG.check_promises(self.L, 20)
        self.assertEqual(pr['status'], 'open')
        self.L.year += 1; self.L.set_phase('preseason')
        self.assertEqual(MO.review_captains(self.L, week=0), [p.pid])
        self.assertEqual(pr['status'], 'kept')

    def test_declining_captain_commitment_still_breaks_and_title_does_not_transfer(self):
        pr = self.legacy('captaincy')
        self.L.year += 1
        NG.check_promises(self.L, 2)
        self.assertEqual(pr['status'], 'broken')
        MO.set_captain(self.L, 'GB', self.p.pid)
        self.assertEqual(pr['status'], 'broken')
        self.p.team = 'MIN'
        self.assertFalse(MO.is_captain(self.p))

    def test_live_trust_overrides_cached_profile_after_reload_without_changing_preferences(self):
        before = CO.profile_for(self.p)
        self.p.morale.break_promise('starting_role')
        self.assertAlmostEqual(CO.profile_for(self.p)['trust'], .65)
        loaded = League.load(self.L.save()); p = loaded.player(self.p.pid)
        profile = CO.profile_for(p)
        self.assertAlmostEqual(profile['trust'], .65)
        self.assertEqual(profile['broken'], 1)
        self.assertEqual(profile['w'], before['w'])
        self.assertEqual(p.xp_spent['_negotiation_profile']['trust'], 1)

    def test_legacy_captain_load_anchors_club_without_reward_or_input_mutation(self):
        self.p.xp_spent['_captain'] = True
        raw = self.L.to_dict()
        loaded = League.load(raw)
        p = loaded.player(self.p.pid)
        self.assertNotIn('_captain_team', raw['players'][p.pid]['xp_spent'])
        self.assertTrue(MO.is_captain(p, 'GB'))
        value = p.morale.value
        MO.set_captain(loaded, 'GB', p.pid)
        self.assertEqual(p.morale.value, value)
        p.team = 'MIN'
        self.assertFalse(MO.is_captain(p, 'MIN'))
        self.assertEqual(p.morale.value, value)

    def test_manual_offer_discount_scales_with_actual_trust(self):
        self.p.morale.base = 60; self.p.morale.fast = 0; self.p.morale.slow = 0
        t = dict(team='GB', kind='extension', ask=10, years=2, discount=0)
        offer = dict(apy=10, years=2, promises=['captaincy'])
        floors = []
        for trust in (1, .65, 0):
            self.p.morale.trust = trust
            floors.append(NG._assessment(self.L, self.p, t, offer)['reference_package']['apy'])
        # Size reflects this player's existing preferences; credibility still
        # scales the concession linearly and zero trust buys no concession.
        self.assertLess(floors[0], floors[1]); self.assertLess(floors[1], floors[2])
        self.assertAlmostEqual(10 - floors[1], (10 - floors[0]) * .65)
        self.assertAlmostEqual(floors[2], 10)
        self.assertAlmostEqual(NG._assessment(self.L, self.p, t, dict(offer, promises=[]))['reference_package']['apy'], 10)

    def test_market_promise_utility_uses_current_trust_even_with_stale_profile(self):
        stale = CO.profile_for(self.p)
        plain = MK.Offer('GB', self.p.pid, 10, 2, bonus=5, front_load=.5)
        promised = MK.Offer('GB', self.p.pid, 10, 2, promises=['captaincy'], bonus=5, front_load=.5)
        gains = []
        for trust in (1, .65, 0):
            self.p.morale.trust = trust
            gains.append(MK.utility_of(self.L, self.p, promised, stale, 10) - MK.utility_of(self.L, self.p, plain, stale, 10))
        self.assertGreater(gains[0], 0)
        self.assertAlmostEqual(gains[1], gains[0] * .65)
        self.assertAlmostEqual(gains[2], 0)


if __name__ == '__main__': unittest.main()

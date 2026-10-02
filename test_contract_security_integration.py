import copy
import json
import unittest
from unittest.mock import patch
import numpy as np
from cap_engine import Contract, CAP
from league import League
from gm_engine import GM
from test_cap_accounting import fixture, player
import contract_offer as CO
import market as MK
import negotiations as NG
import extensions as EXT
import morale as MO
import views_personnel as VP


class SecurityIntegration(unittest.TestCase):
    def setUp(self):
        self.L = fixture(); self.L.user_team = 'GB'; self.L.set_phase('free_agency')
        for t in self.L.teams.values():
            t.gm = GM(); t.cap.cap = 500
        self.p = player(self.L, 'security-player', team=None)
        self.p.pos = 'WR'; self.p.age = 27
        self.p.ratings = {k: 85 for k in ('catch_rating', 'cit_rating', 'route_run_short_rating', 'speed_rating')}
        self.L.free_agents.append(self.p.pid)
        self.t = dict(id=1, pid=self.p.pid, team='GB', kind='fa_offseason', state='open', offers=[],
                      ask=20, years=2, patience=3, due=None, counter=None, rival=None, match_rounds=0)
        self.L.negotiations = [self.t]

    def test_preferences_survive_calls_and_reload_without_consuming_rng(self):
        rng = np.random.default_rng(16); state = copy.deepcopy(rng.bit_generator.state)
        profile = MK.profile_for(self.L, self.p, rng)
        for _ in range(10): self.assertEqual(profile, MK.profile_for(self.L, self.p, rng))
        restored = League.load(self.L.save()); restored.user_team = 'GB'
        self.assertEqual(profile, MK.profile_for(restored, restored.player(self.p.pid), rng))
        self.assertEqual(state, rng.bit_generator.state)
        profile['w']['years'] = -20
        self.assertGreater(MK.profile_for(self.L, self.p, rng)['w']['years'], 0)

    def test_offer_roundtrip_preserves_every_economic_field(self):
        offer = MK.Offer('MIN', self.p.pid, 19, 5, ['no_trade'], front_load=.85, bonus=40, planning_gain=7)
        self.assertEqual(offer.to_save(), MK.Offer.from_save(offer.to_save()).to_save())
        self.L.fa_bids = {self.p.pid: [offer.to_save()]}
        loaded = League.load(self.L.save())
        self.assertEqual(loaded.fa_bids, self.L.fa_bids)

    def test_match_after_reload_signs_exact_bonus_and_shape(self):
        NG.set_rival(self.L, self.p.pid, 'MIN', 19, 5, 40, .85, ['no_trade'])
        self.t['state'] = 'match_requested'
        self.t['offers'] = [dict(apy=18, years=2, bonus=3, front_load=.5)]
        expected = MK.signing_terms(self.L, self.p, self.L.teams['GB'], 19, 5, CAP[2026], .85, 40)
        self.L = League.load(self.L.save()); self.L.user_team = 'GB'; self.p = self.L.player(self.p.pid)
        with patch.object(MK.VAL, 'value_player', return_value={'apy':20, 'years':2}):
            result = VP.act_match(self.L, 'GB', 1)
        self.assertTrue(result['ok'], result)
        self.assertAlmostEqual(self.p.contract.sb, 40)
        self.assertEqual(self.p.contract.base, expected['base'])
        self.assertEqual([round(self.p.contract.cap_hit(i), 3) for i in range(5)], expected['cap_hits'])
        self.assertEqual(self.L.promises[0]['kind'], 'no_trade')

    def test_over_cap_match_is_atomic_and_keeps_request(self):
        NG.set_rival(self.L, self.p.pid, 'MIN', 19, 5, 40, .85)
        self.t['state'] = 'match_requested'; self.t['offers'] = [dict(apy=19, years=5)]
        self.L.teams['GB'].cap.cap = 0
        before = copy.deepcopy(self.p.contract)
        result = VP.act_match(self.L, 'GB', 1)
        self.assertFalse(result['ok'])
        self.assertEqual(self.t['state'], 'match_requested')
        self.assertEqual(self.p.contract, before)
        self.assertIsNone(self.p.team)
        self.assertNotIn('_contract_bargain', self.p.xp_spent)

    def test_preview_and_negotiation_use_same_assessment(self):
        offer = dict(apy=19, years=5, bonus=45, front_load=.5)
        preview = VP.act_offer_preview(self.L, 'GB', self.p.pid, **offer)
        result = NG._assessment(self.L, self.p, self.t, offer)
        self.assertTrue(preview['ok'])
        self.assertEqual(preview['interest']['acceptable'], result['acceptable'])
        self.assertAlmostEqual(preview['interest']['ratio'], result['ratio'])

    def test_preview_can_cross_browser_json_bridge_with_numpy_agent_price(self):
        self.t['ask'] = np.float64(20.)
        preview = VP.act_offer_preview(self.L, 'GB', self.p.pid, 19, 5, bonus=45, front_load=.5)
        restored = json.loads(json.dumps(preview))
        self.assertIsInstance(restored['interest']['acceptable'], bool)
        self.assertEqual(restored['interest'], preview['interest'])

    def test_full_package_can_beat_higher_annual_pay(self):
        profile = CO.profile_for(self.p); profile['w'].update(years=.32, total=.32)
        self.p.xp_spent['_negotiation_profile'] = profile
        secured = MK.Offer('GB', self.p.pid, 19, 5, bonus=45, front_load=.85)
        hollow = MK.Offer('MIN', self.p.pid, 21, 5, bonus=0, front_load=0)
        # Equal team contexts isolate compensation rather than contender luck.
        with patch.object(MK, 'team_context', return_value=dict(contender=.5, role_clarity=.5)):
            self.assertGreater(MK.utility_of(self.L, self.p, secured, profile, 20, 2),
                               MK.utility_of(self.L, self.p, hollow, profile, 20, 2))

    def test_counter_survives_reload_then_signs_preview(self):
        offer = dict(apy=18, years=5, bonus=5, front_load=.5, promises=[])
        self.t['offers'] = [offer]
        NG._answer(self.L, self.t, self.p, offer, 20)
        self.assertEqual(self.t['state'], 'countered')
        counter = copy.deepcopy(self.t['counter'])
        preview = VP.act_offer_preview(self.L, 'GB', self.p.pid, counter['apy'], counter['years'], counter['bonus'], counter['front_load'])
        self.L = League.load(self.L.save()); self.L.user_team = 'GB'; self.p = self.L.player(self.p.pid)
        with patch.object(MK.VAL, 'value_player', return_value={'apy':20, 'years':2}):
            result = VP.act_match_counter(self.L, 'GB', 1)
        self.assertTrue(result['ok'], result)
        self.assertAlmostEqual(sum(self.p.contract.base) + self.p.contract.sb, counter['apy'] * counter['years'])
        self.assertEqual([round(self.p.contract.cap_hit(i), 3) for i in range(counter['years'])], preview['hits'])

    def test_extension_preview_matches_cpu_and_user_decision(self):
        self.p.team = 'GB'; self.p.contract = Contract(1, [5], signing_bonus=3)
        self.L.teams['GB'].roster.append(self.p); self.L.teams['GB'].sync_cap()
        self.t.update(kind='extension', discount=.05)
        terms = dict(ask=20, years=2, discount=.05, offer=19)
        offer = dict(apy=19, years=5, bonus=45, front_load=.5)
        with patch.object(EXT, 'terms', return_value=terms):
            expected = NG._assessment(self.L, self.p, self.t, offer)['acceptable']
            before = EXT.build(self.p, 5, 19, CAP[2026], self.L.teams['GB'].gm, self.L, front_load=.5, bonus=45)
            result = EXT.extend(self.L, self.p.pid, by_ai=True, **offer)
        self.assertEqual(result['result']=='accepted', expected)
        if expected:
            self.assertEqual(self.p.contract.base, before.base)
            self.assertEqual(self.p.contract.bonus_schedule, before.bonus_schedule)

    def test_payment_rollover_not_new_underpayment_but_growth_can_be(self):
        self.p.team = 'GB'; self.L.teams['GB'].roster.append(self.p)
        self.p.contract = Contract(3, [15, 5, 5], signing_bonus=35, signed=2026)
        CO.remember(self.L, self.p, self.p.contract, 20, 20)
        self.p.contract.advance(); self.L.year = 2027
        self.L = League.load(self.L.save()); self.p = self.L.player(self.p.pid)
        mood = MO.ensure(self.p)
        with patch.dict(CAP, {2027:CAP[2026]}), patch.object(MK.VAL, 'pool_from_league', return_value=[]), \
             patch.object(MK.VAL, 'value_player', return_value={'apy':20}):
            MO.offseason_contracts(self.L, np.random.default_rng(1))
            self.assertEqual(getattr(mood, '_contract_drag', 0), 0)
        with patch.dict(CAP, {2027:CAP[2026]}), patch.object(MK.VAL, 'pool_from_league', return_value=[]), \
             patch.object(MK.VAL, 'value_player', return_value={'apy':32}):
            MO.offseason_contracts(self.L, np.random.default_rng(1))
            self.assertLess(mood._contract_drag, 0)

    def test_partial_season_only_prorates_base(self):
        self.L.set_phase('regular'); self.L.week = 10; self.L.teams['GB'].cap.paid_week = 9
        package = CO.canonical(self.L, self.p, self.L.teams['GB'], dict(apy=10, years=1, bonus=4, front_load=.5))
        cash = CO.cash(self.L, self.p, self.L.teams['GB'], package, 'fa_inseason')
        self.assertEqual(cash.bonus, 4)
        self.assertEqual(cash.base, (3,))

    def test_declining_match_preserves_rivals_bonus_and_shape(self):
        NG.set_rival(self.L, self.p.pid, 'MIN', 19, 5, 40, .85, ['no_trade'])
        self.t['state'] = 'match_requested'
        expected = MK.signing_terms(self.L, self.p, self.L.teams['MIN'], 19, 5, CAP[2026], .85, 40)
        result = NG.withdraw(self.L, 1)
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.p.team, 'MIN')
        self.assertEqual(self.p.contract.base, expected['base'])
        self.assertEqual(self.p.contract.sb, 40)

    def test_restricted_offer_sheet_survives_reload_and_matches_full_terms(self):
        self.p.team = 'GB'; self.p.fa_class = 'tendered'; self.p.tender_team = 'GB'
        self.p.contract = Contract(1, [3], signed=2026)
        self.L.teams['GB'].roster.append(self.p); self.L.teams['GB'].sync_cap()
        msg = MK.inbox_add(self.L, dict(kind='offer_sheet', pid=self.p.pid, team='GB',
            suitor='MIN', offer=19, years=5, bonus=40, front_load=.85, promises=['no_trade']))
        self.L = League.load(self.L.save()); self.L.user_team = 'GB'; self.p = self.L.player(self.p.pid)
        expected = MK.signing_terms(self.L, self.p, self.L.teams['GB'], 19, 5, CAP[2026], .85, 40)
        result = MK.answer_offer_sheet(self.L, msg['id'], 'match')
        self.assertEqual(result['outcome'], 'matched')
        self.assertEqual(self.p.contract.base, expected['base'])
        self.assertEqual(self.p.contract.sb, 40)
        self.assertEqual(self.L.promises[0]['kind'], 'no_trade')

    def test_existing_contract_is_unchanged_when_preferences_initialize(self):
        self.p.contract = Contract(3, [10, 11, 12], signing_bonus=8, signed=2026)
        before = copy.deepcopy(vars(self.p.contract))
        CO.profile_for(self.p)
        self.assertEqual(vars(self.p.contract), before)

    def test_firm_midseason_refusal_cannot_be_bought_out_with_security(self):
        self.L.set_phase('regular'); self.L.week = 9
        self.p.team = 'GB'; self.p.contract = Contract(1, [15], signed=2026)
        self.L.teams['GB'].roster.append(self.p); self.L.teams['GB'].sync_cap()
        self.L.negotiations = []
        situation = dict(in_season=True, star=True, final_year=True, money=.8, morale=60, loyalty=.2)
        with patch.object(NG, '_situation', return_value=situation), patch.object(NG, 'stable_seed', return_value=1), \
             patch.object(EXT, 'terms', return_value=dict(ask=20, years=2, discount=0)):
            opened = NG.open_talks(self.L, self.p.pid)
            self.assertFalse(opened['will_talk'])
            self.assertEqual(opened['mood'], 'deferring')
            self.assertEqual(self.p.contract.years, 1)
            self.assertEqual(self.L.negotiations, [])
            result = NG.make_offer(self.L, 9999, 20, 5, bonus=50, front_load=.5)
        self.assertFalse(result['ok'])

    def test_decision_to_leave_is_not_reopened_by_long_secure_offer(self):
        self.t['state'] = 'declined'
        result = NG.make_offer(self.L, self.t['id'], 25, 5, bonus=75, front_load=.85)
        self.assertFalse(result['ok'])
        self.assertEqual(self.t['state'], 'declined')
        self.assertEqual(self.t['offers'], [])
        self.assertIsNone(self.p.contract)

    def test_counters_meet_their_own_preview_with_morale_and_promises(self):
        MO.ensure(self.p).base = 15
        for shape in (0., .5, 1.):
            for promises in ([], ['no_trade']):
                offer = CO.canonical(self.L, self.p, self.L.teams['GB'],
                    dict(apy=18, years=5, bonus=0, front_load=shape, promises=promises))
                counter = NG._counter_package(self.L, self.p, self.t, offer)
                self.assertEqual(counter['promises'], promises)
                self.assertTrue(NG._assessment(self.L, self.p, self.t, counter)['acceptable'], counter)


if __name__ == '__main__': unittest.main()

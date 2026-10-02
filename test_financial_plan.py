"""Behavioral/accounting gates for shared CPU spending strategy."""
import copy
import unittest
from unittest.mock import patch

from cap_engine import CAP, Contract
from league import DraftPick, League, Team
from test_draft_planning import fixture, set_grade
import financial_plan as FP
import market
import contracts


class FinancialPlanTests(unittest.TestCase):
    def setUp(self):
        self.L,self.t=fixture()
        self.t.picks=[]
        self.L.set_phase('regular')

    def candidate(self, pid='candidate'):
        p=copy.deepcopy(self.t.roster[0]);p.pid=pid;p.team=None;p.contract=None
        return p

    def test_forecast_uses_own_cap_not_another_loaded_franchise(self):
        current = self.t.cap.cap
        with patch.dict(CAP, {self.L.year: 500., self.L.year+1: 900.}):
            before = FP.snapshot(self.L, self.t)
            self.assertAlmostEqual(before['years'][0]['injury_reserve'], current*.008)
            self.assertAlmostEqual(before['years'][1]['injury_reserve'], current*1.055*.008)
            loaded = League.load(self.L.save())
            self.assertEqual(before, FP.snapshot(loaded, loaded.teams[self.t.abbr]))

    def test_known_franchise_caps_override_forecast_and_global_cache(self):
        self.L.cap_history[self.L.year+1] = 360.
        self.L.cap_history[self.L.year] = 280.  # current ledger still wins
        with patch.dict(CAP, {self.L.year: 500., self.L.year+1: 900.}):
            self.assertEqual(FP._cap(self.L,self.t,self.L.year), self.t.cap.cap)
            self.assertEqual(FP._cap(self.L,self.t,self.L.year+1), 360.)
        self.assertEqual(FP._cap(self.L,self.t,2026), CAP[2026])

    def room(self, amount):
        self.t.sync_cap()
        self.t.cap.dead=self.t.cap.limit-self.t.cap.charges('season')+self.t.cap.dead-amount

    def test_negotiation_market_matches_uncached_projections(self):
        self.L.player('QB0').contract = Contract(1, [5])
        market_view = FP.retention_market(self.L)
        arrival = self.candidate(); arrival.pos = 'WR'; set_grade(arrival, 85)
        for picks in ([], [DraftPick(self.L.year, 1, 'MIN', 'MIN')]):
            kw = dict(additions=[(arrival, Contract(3, [4, 6, 8]))], gain=12, picks=picks)
            self.assertEqual(FP.evaluate(self.L, self.t, **kw),
                             FP.evaluate(self.L, self.t, market=market_view, **kw))

    def test_new_negotiation_refreshes_peer_pay_and_ratings(self):
        p = self.L.player('QB0'); p.contract = Contract(1, [1]); set_grade(p, 95)
        q = copy.deepcopy(p); q.pid = 'veteran'; q.contract = Contract(3, [30]*3)
        other = Team('DEN', 'Continental West', 'Continental'); other.league = self.L
        other.roster.append(q); self.L.teams['DEN'] = other
        previous = FP.retention_market(self.L)
        before = FP.snapshot(self.L, self.t, market=previous)
        q.contract = Contract(3, [12]*3); set_grade(q, 94)
        refreshed = FP.snapshot(self.L, self.t, market=FP.retention_market(self.L))
        self.assertEqual(refreshed, FP.snapshot(self.L, self.t))
        self.assertLess(refreshed['years'][1]['retention_reserve'], before['years'][1]['retention_reserve'])

    def test_marginal_purchase_rejected_but_major_upgrade_can_use_cushion(self):
        self.room(7)
        p=self.candidate();offer=Contract(1,[4])
        self.assertFalse(FP.evaluate(self.L,self.t,additions=[(p,offer)],gain=2)['approved'])
        r=FP.evaluate(self.L,self.t,additions=[(p,offer)],gain=40)
        self.assertTrue(r['approved'])
        self.assertEqual(r['reason'],'approved_exceptional_upgrade')

    def test_gm_preferences_change_same_purchase(self):
        self.room(9)
        p=self.candidate();c=Contract(1,[3])
        self.t.gm.patience=1;self.t.gm.risk=0;self.t.gm.aggression=0
        self.t.gm.job_security=1
        cautious=FP.evaluate(self.L,self.t,additions=[(p,c)],gain=2)
        self.t.gm.patience=0;self.t.gm.risk=1;self.t.gm.aggression=1
        self.t.gm.job_security=.1
        urgent=FP.evaluate(self.L,self.t,additions=[(p,c)],gain=2)
        self.assertFalse(cautious['approved'])
        self.assertTrue(urgent['approved'])

    def test_emergency_uses_soft_money_but_not_illegal_room(self):
        self.room(2);p=self.candidate()
        self.assertTrue(FP.evaluate(self.L,self.t,additions=[(p,Contract(1,[1]))],essential=True)['approved'])
        self.assertFalse(FP.evaluate(self.L,self.t,additions=[(p,Contract(1,[3]))],essential=True)['approved'])

    def test_future_vacancies_block_backloaded_deal(self):
        for p in self.t.roster: p.contract=Contract(1,[1])
        p=self.candidate();future=FP._cap(self.L,self.t,self.L.year+1)
        r=FP.evaluate(self.L,self.t,additions=[(p,Contract(2,[1,future-10]))],gain=100)
        self.assertFalse(r['approved']);self.assertEqual(r['reason'],'fund_required_roster')

    def test_pending_offers_share_budget_and_candidate_is_not_held_twice(self):
        self.room(14);a,b=self.candidate('a'),self.candidate('b');c=Contract(1,[5])
        self.assertTrue(FP.evaluate(self.L,self.t,additions=[(a,c)],gain=2)['approved'])
        self.assertFalse(FP.evaluate(self.L,self.t,additions=[(b,c)],pending=[(a,c)],gain=2)['approved'])
        alone=FP.snapshot(self.L,self.t,additions=[(a,c)])
        repeat=FP.snapshot(self.L,self.t,additions=[(a,c)],pending=[(a,c),(a,c)])
        self.assertEqual(alone['years'],repeat['years'])

    def test_rookies_displace_vacancy_and_signed_pick_is_not_reserved_again(self):
        self.t.roster=self.t.roster[:45]
        pk=DraftPick(self.L.year-1,7,'MIN','MIN',selection=220)
        self.t.picks=[pk]
        a=FP.snapshot(self.L,self.t)['years'][0]
        self.assertEqual(a['vacant_slots'],7)
        import draft
        p=self.candidate();p.contract=draft.rookie_contract(220,self.t.cap.cap)
        self.t.roster.append(p);pk.used_on=p.pid
        b=FP.snapshot(self.L,self.t)['years'][0]
        self.assertEqual(b['rookie_reserve'],0)
        self.assertAlmostEqual(a['funded_room'],b['funded_room'])

    def test_extension_replaces_named_retention_premium(self):
        p=self.L.player('QB0');p.contract=Contract(1,[15]);set_grade(p,90)
        before=FP.snapshot(self.L,self.t)
        after=FP.snapshot(self.L,self.t,additions=[(p,Contract(4,[15]*4))])
        self.assertGreater(before['years'][1]['retention_reserve'],0)
        self.assertEqual(after['years'][1]['retention_reserve'],0)
        self.assertEqual(before['years'][0]['raw_room'],after['years'][0]['raw_room'])

    def test_cheap_expiring_star_plans_for_raise_and_refreshes_from_veteran_pay(self):
        p=self.L.player('QB0');set_grade(p,95)
        p.contract=Contract(1,[1],signed=2024);p.draft_year=2024;p.draft_round=1
        other=Team('DEN','Continental West','Continental');other.league=self.L
        self.L.teams['DEN']=other
        for i,pay in enumerate((24.,30.,36.)):
            q=copy.deepcopy(p);q.pid='veteran-'+str(i);q.team='DEN';q.draft_year=2018
            q.contract=Contract(3,[pay]*3,signed=2026);set_grade(q,94+i)
            other.roster.append(q);self.L.players[q.pid]=q
        first=FP.snapshot(self.L,self.t)
        self.assertGreater(first['years'][1]['retention_reserve'],10.)
        # A low-value backloaded purchase cannot consume the raise allowance.
        arrival=self.candidate('unrelated-purchase')
        arrival.pos='WR';set_grade(arrival,70)
        price=first['years'][1]['funded_room']-8
        decision=FP.evaluate(self.L,self.t,additions=[(arrival,Contract(2,[1,price]))],gain=2)
        self.assertFalse(decision['approved'])
        self.assertEqual(decision['reason'],'preserve_retention')
        self.assertGreater(decision['after']['years'][1]['raw_room'],0.)
        # Once renewed, the placeholder is replaced by the actual commitment.
        renewed=FP.snapshot(self.L,self.t,additions=[(p,Contract(4,[30]*4))])
        self.assertEqual(renewed['years'][1]['retention_reserve'],0.)
        # No hidden quote cache: changes in peer contracts are visible immediately.
        for q in other.roster:q.contract=Contract(3,[12]*3,signed=2026)
        revised=FP.snapshot(self.L,self.t)
        self.assertLess(revised['years'][1]['retention_reserve'],first['years'][1]['retention_reserve'])
        saved=self.L.save();loaded=League.load(saved)
        self.assertEqual(revised,FP.snapshot(loaded,loaded.teams[self.t.abbr]))

    def test_original_rookie_deals_do_not_set_star_renewal_market(self):
        p=self.L.player('QB0');set_grade(p,95);p.contract=Contract(1,[1],signed=2024)
        p.draft_year=2024;p.draft_round=1
        before=FP.snapshot(self.L,self.t)['years'][1]['retention_reserve']
        q=copy.deepcopy(p);q.pid='other-rookie';q.contract=Contract(3,[20]*3,signed=2024)
        self.t.roster.append(q);self.L.players[q.pid]=q;set_grade(q,87)
        after=FP.snapshot(self.L,self.t)['years'][1]['retention_reserve']
        self.assertEqual(before,after)

    def test_rookie_forecast_displaces_minimum_slots_without_changing_legal_room(self):
        for p in self.t.roster: p.contract=Contract(1,[1])
        initial=FP.snapshot(self.L,self.t)['years'][0]
        self.t.picks=[DraftPick(self.L.year-1,r,'MIN','MIN',selection=(r-1)*32+16)
                      for r in range(1,8)]
        forecast=FP.snapshot(self.L,self.t)['years'][0]
        self.assertAlmostEqual(forecast['displacement_credit'],7)
        self.assertEqual(forecast['raw_room'],initial['raw_room'])
        self.assertAlmostEqual(forecast['funded_room'],initial['funded_room']-forecast['rookie_reserve']+7)

    def test_inspection_pure_and_save_load_identical(self):
        saved=self.L.save()
        first=FP.snapshot(self.L,self.t)
        self.assertEqual(saved,self.L.save())
        loaded=League.load(saved)
        self.assertEqual(first,FP.snapshot(loaded,loaded.teams[self.t.abbr]))

    def test_offseason_boundary_and_midseason_vacancy_cost(self):
        self.L.season_closed_year=self.L.year;self.L.set_phase('offseason')
        self.assertEqual(FP.snapshot(self.L,self.t)['cap_year'],self.L.year+1)
        self.L.set_phase('regular');self.t.roster=self.t.roster[:45]
        self.t.cap.paid_week=0;a=FP.snapshot(self.L,self.t)['vacancy_reserve']
        self.t.cap.paid_week=9;b=FP.snapshot(self.L,self.t)['vacancy_reserve']
        self.assertAlmostEqual(a/2,b)

    def test_top51_does_not_hide_full_season_cost(self):
        self.L.set_phase('free_agency')
        row=FP.snapshot(self.L,self.t)['years'][0]
        self.assertEqual(row['full_roster_adjustment'],2)

    def test_restructure_does_not_refill_discretionary_cushion(self):
        self.room(4);p=self.L.player('QB0');p.contract=Contract(4,[12]*4)
        self.room(4)
        previous=copy.deepcopy(p.contract.__dict__)
        contracts.run(self.L,None)
        self.assertEqual(previous,p.contract.__dict__)

    def test_user_strategy_never_vetoes_legal_actions(self):
        self.L.user_team=self.t.abbr;self.room(2)
        r=FP.evaluate(self.L,self.t,additions=[(self.candidate(),Contract(1,[1]))],gain=0)
        self.assertTrue(r['approved']);self.assertEqual(r['reason'],'user_control')

    def test_preview_matches_fa_installed_contract_pre_roll(self):
        p=self.candidate();self.L.players[p.pid]=p;self.L.free_agents.append(p.pid)
        self.L.set_phase('offseason');self.L.season_closed_year=self.L.year
        offer=market.Offer(self.t.abbr,p.pid,3,2,bonus=1,front_load=.5)
        c=market.offer_contract(self.L,p,offer)
        market.sign(self.L,p,offer,self.t.cap.cap,market_apy=3)
        self.assertEqual(c.__dict__,p.contract.__dict__)


if __name__=='__main__': unittest.main()

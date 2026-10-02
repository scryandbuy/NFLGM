import unittest, copy
from types import SimpleNamespace as N
from unittest.mock import patch
from cap_engine import Contract, TeamCap
from cap_accounting import settle_week, require_room, next_year_ledger, trade_projection
from league import League, Team, Player, contract_to_dict, contract_from_dict
import extensions, contract_structure as CS, practice_squad as PS, tags


def fixture():
    L=League(2026)
    for abbr in ('GB','MIN'):
        t=Team(abbr,'United North','United'); t.league=L; L.teams[abbr]=t
    L.set_phase('regular')
    L.week=1
    return L


def player(L,pid='p',team='GB',contract=None):
    p=Player(pid,pid,'QB',29,{},team=team,contract=contract,accrued=5)
    L.players[pid]=p
    if team: L.teams[team].roster.append(p); L.teams[team].sync_cap()
    return p


class CapAccountingTests(unittest.TestCase):
    def test_offseason_top51_survives_reload(self):
        L=fixture(); L.set_phase('free_agency')
        for i in range(53): player(L,pid=str(i),contract=Contract(1,[2]))
        before=L.teams['GB'].cap_space
        loaded=League.load(L.save())
        self.assertEqual(loaded.teams['GB'].phase,'free_agency')
        self.assertEqual(loaded.teams['GB'].cap_space,before)
        loaded.set_phase('regular')
        self.assertAlmostEqual(loaded.teams['GB'].cap_space,before-4)

    def test_practice_squad_pay_is_outside_cap_even_after_reload(self):
        L=fixture(); t=L.teams['GB']; t.cap.cap=.1; t.cap.rollover=0
        p=player(L,team=None); L.free_agents.append(p.pid)
        self.assertTrue(PS.sign_to_squad(L,'GB',p.pid))
        self.assertAlmostEqual(t.cap_space,.1)
        settle_week(L,9)
        self.assertGreater(t.cap.ps_earned,0)
        self.assertAlmostEqual(t.cap_space,.1)
        loaded=League.load(L.save())
        self.assertAlmostEqual(loaded.teams['GB'].cap_space,.1)

    def test_roster_to_squad_budget_counts_release_savings_and_dead_money(self):
        from cap_accounting import require_squad_room
        L=fixture(); t=L.teams['GB']
        t.cap.cap=7; t.cap.rollover=0
        p=player(L,contract=Contract(3,[.5]*3,signing_bonus=6))
        require_squad_room(L,t,p)
        t.cap.cap=5
        with self.assertRaises(ValueError): require_squad_room(L,t,p)

    def test_five_year_max_survives_advance(self):
        c=Contract(6,[1]*6,signing_bonus=50)
        charges=[]
        for _ in range(6): charges.append(c.annual_proration); c.advance()
        self.assertEqual(charges,[10,10,10,10,10,0])

    def test_extension_keeps_old_allocations_and_void_balance(self):
        L=fixture(); p=player(L,contract=Contract(2,[5,5],signing_bonus=20,void_years=2))
        with patch.object(extensions.CS,'structure',return_value={'base':[5]*3,'signing_bonus':10}):
            c=extensions.build(p,3,5,301.2,N(),L)
        self.assertEqual(c.bonus_schedule,[7,7,7,7,2])
        self.assertAlmostEqual(c.sb,30)

    def test_restructure_does_not_respread_old_bonus(self):
        c=Contract(2,[10,10],signing_bonus=20); c.void=2
        c.restructure(0,8,min_base=2)
        self.assertEqual(c.bonus_schedule,[12,12,2,2])
        self.assertAlmostEqual(sum(c.base)+c.sb,40)
        c.restructure(0,999,min_base=2)
        self.assertEqual(c.base[0],2)

    def test_expiry_posts_void_balance(self):
        L=fixture(); p=player(L,contract=Contract(1,[1],signing_bonus=30,void_years=2))
        L.advance_contracts()
        self.assertIsNone(p.contract)
        self.assertEqual(L.teams['GB'].cap.dead,20)

    def test_top51_retains_excluded_bonus(self):
        t=TeamCap(2026)
        t.contracts=[(str(i),Contract(1,[2]),0) for i in range(51)]
        t.contracts.append(('last',Contract(1,[.885],signing_bonus=.1),0))
        self.assertAlmostEqual(t.charges('camp'),102.1)
        self.assertAlmostEqual(t.charges(),102.985)

    def test_cash_matches_quote(self):
        for years in (1,2,5,6):
            for apy in (.971,1.3,10):
                d=CS.structure(apy,years,'QB',301.2,N(restructure_depth=.5))
                self.assertAlmostEqual(sum(d['base'])+d['signing_bonus'],apy*years,places=3)

    def test_weekly_pay_release_and_rollover(self):
        L=fixture(); p=player(L,contract=Contract(2,[18,18],signing_bonus=10))
        settle_week(L,9); settle_week(L,9)
        self.assertEqual(p.contract.earned_base,9)
        L.release('p')
        t=L.teams['GB']
        self.assertEqual(t.cap.earned,9)
        self.assertEqual(t.cap.dead,10)
        self.assertEqual(t.cap.charges(),19)
        self.assertEqual(t.cap.roll_forward(320).rollover,282.2)

    def test_offseason_departure_and_retirement_calendar(self):
        L=fixture(); p=player(L,contract=Contract(3,[18]*3,signing_bonus=30))
        L.set_phase('offseason'); L.season_closed_year=2026
        now,nxt,_=L.release('p')
        self.assertEqual((now,nxt),(10,20))
        self.assertEqual(L.teams['GB'].cap.earned,18)
        self.assertEqual(L.teams['GB'].cap.charges(),28)

    def test_trade_keeps_paid_salary_at_seller(self):
        L=fixture(); p=player(L,contract=Contract(2,[18,18],signing_bonus=10))
        settle_week(L,9)
        L.trade('GB','MIN',['p'],[])
        self.assertEqual(L.teams['GB'].cap.charges(),19)
        self.assertEqual(L.teams['MIN'].cap.charges(),9)
        self.assertEqual(p.contract.sb,0)
        settle_week(L,18)
        self.assertEqual(p.contract.earned_base,9)

    def test_trade_preview_matches_current_year_cap_after_exchange(self):
        L=fixture()
        player(L,'gb_player','GB',Contract(2,[18,18],signing_bonus=10))
        player(L,'min_player','MIN',Contract(2,[12,12],signing_bonus=6))
        settle_week(L,9)
        before={abbr:L.teams[abbr].cap_space for abbr in ('GB','MIN')}
        projected={
            'GB':trade_projection(L,'GB',['gb_player'],['min_player']).space('season'),
            'MIN':trade_projection(L,'MIN',['min_player'],['gb_player']).space('season'),
        }
        self.assertNotEqual(projected['GB'],before['GB'])
        self.assertNotEqual(projected['MIN'],before['MIN'])
        self.assertEqual(L.player('gb_player').team,'GB')
        self.assertEqual(L.player('min_player').team,'MIN')
        L.trade('GB','MIN',['gb_player'],['min_player'])
        for abbr in ('GB','MIN'):
            self.assertAlmostEqual(projected[abbr],L.teams[abbr].cap_space)

    def test_over_cap_trade_is_atomic(self):
        L=fixture(); p=player(L,contract=Contract(1,[10])); L.teams['MIN'].cap.cap=1
        with self.assertRaises(ValueError): L.trade('GB','MIN',['p'],[])
        self.assertEqual(p.team,'GB'); self.assertEqual(L.teams['GB'].cap.dead,0)

    def test_ordinary_guard_and_emergency_primitive(self):
        L=fixture(); t=L.teams['GB']; t.cap.cap=1
        c=Contract(1,[10])
        with self.assertRaises(ValueError): require_room(L,t,'new',c)
        p=player(L,'new',None)
        L.sign('new','GB',c)  # explicit emergency path remains usable
        self.assertEqual(t.cap_space,-9)

    def test_squad_earned_survives_release_and_late_signing(self):
        L=fixture(); t=L.teams['GB']; p=player(L,'ps',None); p.accrued=0
        PS.sign_to_squad(L,'GB','ps'); settle_week(L,9)
        PS.release_from_squad(L,'GB','ps')
        self.assertAlmostEqual(t.cap.ps_earned,.12375)
        self.assertEqual(t.cap.practice_squad,0)
        self.assertEqual(t.cap.charges(),0)
        PS.sign_to_squad(L,'GB','ps'); settle_week(L,18)
        self.assertAlmostEqual(t.cap.ps_earned,.2475)
        self.assertEqual(t.cap.charges(),0)

    def test_save_preserves_new_ledger_and_load_does_not_mutate_input(self):
        L=fixture(); p=player(L,contract=Contract(2,[18,18],signing_bonus=20))
        p.contract.void=2; p.contract.restructure(0,2,min_base=1)
        settle_week(L,9)
        d=contract_to_dict(p.contract); before=copy.deepcopy(d)
        self.assertEqual(contract_to_dict(contract_from_dict(d)),d)
        self.assertEqual(d,before)
        loaded=League.load(L.save())
        self.assertEqual(loaded.teams['GB'].cap.paid_week,9)
        self.assertEqual(loaded.player('p').contract.bonus_schedule,p.contract.bonus_schedule)
        self.assertEqual(loaded.teams['GB'].cap_space,L.teams['GB'].cap_space)

    def test_legacy_balance_preserved(self):
        c=contract_from_dict(dict(years=2,base=[5,5],signing_bonus=20,void_years=2,signed=2024))
        self.assertEqual(c.sb,20); self.assertEqual(c.bonus_schedule,[5,5,5,5])

    def test_tag_raise_applied_once_and_prior_retained(self):
        L=fixture(); p=player(L,contract=Contract(1,[50])); p.tag_count=1
        self.assertEqual(tags.tag_price(p,301.2),60)
        L.advance_contracts()
        self.assertEqual(tags.tag_price(p,301.2),60)

    def test_next_year_includes_void_expiry(self):
        L=fixture(); player(L,contract=Contract(1,[1],signing_bonus=30,void_years=2))
        limit,committed,roll,dead=next_year_ledger(L,L.teams['GB'])
        self.assertEqual((committed,dead),(20,20))

    def test_pre_roll_restructure_targets_next_year_and_matches_preview(self):
        import contracts
        L=fixture(); p=player(L,contract=Contract(3,[18,20,22],signing_bonus=12))
        settle_week(L,18); L.set_phase('offseason'); L.season_closed_year=L.year
        old=p.contract.cap_hit(0)
        pv=contracts.restructure_preview(L,p.pid,amount=5,void_years=2)
        self.assertEqual(pv['cap_year'],2027)
        done=contracts.restructure_user(L,p.pid,amount=5,void_years=2)
        self.assertTrue(done['done']); self.assertEqual(p.contract.cap_hit(0),old)
        self.assertEqual([round(p.contract.cap_hit(i),2) for i in range(3)],pv['hits_after'])

    def test_market_refusal_preserves_tender(self):
        import market
        L=fixture(); p=player(L,contract=Contract(1,[1])); p.fa_class='tendered'; L.teams['GB'].gm=N(restructure_depth=.5)
        L.teams['GB'].cap.cap=1
        old=p.contract
        with self.assertRaises(ValueError): market.sign(L,p,market.Offer('GB',p.pid,10,2),301.2)
        self.assertIs(p.contract,old); self.assertIn(p,L.teams['GB'].roster)
        self.assertEqual(p.team,'GB'); self.assertNotIn(p.pid,L.free_agents)

    def test_tender_replacement_has_no_fake_release_charge(self):
        import market
        L=fixture(); p=player(L,contract=Contract(1,[1])); p.fa_class='tendered'; L.teams['GB'].gm=N(restructure_depth=.5)
        market.sign(L,p,market.Offer('GB',p.pid,3,2),301.2)
        self.assertEqual(L.teams['GB'].roster.count(p),1)
        self.assertEqual(L.teams['GB'].cap.dead,0)
        self.assertFalse(any(x['kind']=='release' for x in L.transactions))

    def test_ps_callup_refusal_is_atomic_including_emergencies(self):
        L=fixture(); p=player(L,team=None); L.free_agents.append(p.pid)
        self.assertTrue(PS.sign_to_squad(L,'GB',p.pid))
        L.teams['GB'].cap.cap=.5
        self.assertFalse(PS.call_up(L,'GB',p.pid))
        self.assertIn(p,PS.squad(L.teams['GB'])); self.assertIsNone(p.contract)
        self.assertFalse(PS.call_up(L,'GB',p.pid,emergency=True))
        self.assertIn(p,PS.squad(L.teams['GB'])); self.assertIsNone(p.contract)
        self.assertAlmostEqual(L.teams['GB'].cap_space,.5)

    def test_waiver_contract_keeps_only_remaining_pay(self):
        import waivers
        L=fixture(); p=player(L,contract=Contract(2,[18,18],signing_bonus=10)); p.accrued=1
        settle_week(L,9); L.release(p.pid)
        self.assertAlmostEqual(p.contract.base[0],9)
        L.teams['MIN'].cap.cap=1
        entry=dict(pid=p.pid,from_team='GB')
        self.assertFalse(waivers.claim_fits(L,entry,'MIN'))
        self.assertIsNone(p.team)
        L.teams['MIN'].cap.cap=301.2
        self.assertTrue(waivers.claim_fits(L,entry,'MIN'))
        waivers.award(L,entry,'MIN')
        self.assertEqual(p.contract.base[0],9); self.assertEqual(p.contract.sb,0)
        self.assertEqual(L.teams['GB'].cap.earned,9)

    def test_pre_roll_trade_allows_future_cap_overage(self):
        L=fixture(); p=player(L,contract=Contract(2,[1,400]))
        player(L,'m','MIN',Contract(1,[290]))
        settle_week(L,18); L.set_phase('offseason'); L.season_closed_year=L.year
        L.trade('GB','MIN',[p.pid],[])
        self.assertEqual(p.team,'MIN')
        limit, committed, _, _ = next_year_ledger(L, L.teams['MIN'])
        self.assertGreater(committed, limit)

    def test_rollover_and_void_expiry_reconcile(self):
        import numpy as np
        L=fixture(); t=L.teams['GB']; player(L,contract=Contract(1,[18],signing_bonus=30,void_years=2))
        settle_week(L,18); expected=t.cap.space('season')
        L.roll_year(np.random.default_rng(2)); L.advance_contracts()
        self.assertAlmostEqual(t.cap.rollover,expected)
        self.assertEqual(t.cap.dead,20); self.assertEqual(t.cap.earned,0)
        self.assertEqual(t.cap.paid_week,0)
        loaded=League.load(L.save()); self.assertEqual(loaded.teams['GB'].cap_space,t.cap_space)

    def test_legacy_full_save_migrates_earned_pay(self):
        import json
        L=fixture(); p=player(L,contract=Contract(2,[18,18],signing_bonus=10))
        L.schedule=[(1,'GB','MIN',20,10),(2,'MIN','GB',None,None)]
        d=json.loads(L.save())
        for t in d['teams'].values():
            for key in ('cap_earned','cap_ps_earned','cap_paid_week'): t.pop(key,None)
        for pd in d['players'].values():
            if pd.get('contract'):
                for key in ('bonus_schedule','earned_base','earned_roster','pay_start'): pd['contract'].pop(key,None)
        loaded=League.load(json.dumps(d)); self.assertEqual(loaded.teams['GB'].cap.paid_week,1)
        self.assertAlmostEqual(loaded.player(p.pid).contract.earned_base,1)

    def test_pre_roll_free_agent_starts_in_upcoming_year(self):
        import market
        L=fixture(); L.teams['GB'].gm=N(restructure_depth=.5)
        p=player(L,team=None); L.free_agents.append(p.pid)
        settle_week(L,18); L.set_phase('offseason'); L.season_closed_year=L.year
        market.sign(L,p,market.Offer('GB',p.pid,5,1),301.2)
        self.assertEqual(p.cap_hit(0),0); self.assertAlmostEqual(p.cap_hit(1),5)
        self.assertEqual(p.apy,5)
        L.advance_contracts()
        self.assertIsNotNone(p.contract); self.assertEqual(p.contract.years,1)
        self.assertEqual(p.apy,5)


if __name__=='__main__': unittest.main()


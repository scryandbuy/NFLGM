"""Complete, funded CPU rosters and atomic in-season replacement decisions."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import contracts as CT
import cutdown as CD
import practice_squad as PS
import roster_needs as RN
import min_salary as MS
from cap_engine import CAP, Contract
from league import Team
from test_cap_accounting import fixture, player
from test_draft_planning import fixture as roster_fixture
from test_draft_planning import set_grade
from session import Session


class RecoveryTests(unittest.TestCase):
    def rng(self): return np.random.default_rng(19)

    def roster(self):
        L, t = roster_fixture()
        L.set_phase('offseason'); t.phase = 'season'
        keep = RN.select_cutdown(t, CD.rows_for(t), 53)
        t.roster = [p for p in t.roster if p.pid in keep]
        t.cap.cap = 300; t.sync_cap()
        self.assertEqual(len(t.active()), 53)
        self.assertFalse(RN.assess(t)['uncovered'])
        return L, t

    def test_reserve_grows_after_departure_and_prorates(self):
        L, t = self.roster()
        self.assertEqual(CT.roster_reserve(t, 301.2), 0)
        t.roster.pop()
        full = CT.roster_reserve(t, 301.2)
        t.cap.paid_week = 9
        self.assertAlmostEqual(CT.roster_reserve(t, 301.2), full / 2)
        t.roster.pop()
        self.assertAlmostEqual(CT.roster_reserve(t, 301.2), full)

    def test_final_funding_can_restructure_existing_older_deal(self):
        L, t = self.roster()
        p = t.by_pos('QB')[0]; p.age = 36
        p.contract = Contract(4, [20]*4)
        t.roster.pop(); t.sync_cap()
        t.cap.cap = t.cap.charges(t.phase) + .01
        years = p.contract.years
        CT.enforce(L, self.rng(), roster_target=53, target=0)
        self.assertEqual(len(t.active()), 52)
        self.assertIn(p, t.roster)
        self.assertEqual(p.contract.years, years)
        self.assertGreaterEqual(t.cap_space+.0005, CT.roster_reserve(t, CAP.get(L.year,301.2)))

    def short_cap_roster(self):
        """A 46-man club can fund its last seven spots with one surplus cut."""
        L,t=self.roster()
        for pos in ('CB','WR','DT','HB','TE','SS','SAM'):
            t.roster.remove(t.by_pos(pos)[-1])
        for p in t.active(): p.contract=Contract(1,[1.0])
        qb=t.by_pos('QB')[0]; reserve_qb=t.by_pos('QB')[1]
        lt=t.by_pos('LT')[-1]
        set_grade(qb, 91); set_grade(reserve_qb, 67)
        set_grade(t.by_pos('LT')[0], 87); set_grade(lt, 78)
        qb.contract=Contract(1,[42.48])
        lt.contract=Contract(1,[16.963])
        t.sync_cap(); t.cap.cap=t.cap.charges(t.phase)+1.104
        self.assertEqual(len(t.active()),46)
        return L,t,qb,lt

    def test_final_funding_cuts_redundant_tackle_before_starting_qb(self):
        L,t,qb,lt=self.short_cap_roster()
        before=RN.assess(t)['score']
        self.assertLess(RN.assess(t,[p for p in t.active() if p is not qb])['score'],before-15)
        self.assertAlmostEqual(RN.assess(t,[p for p in t.active() if p is not lt])['score'],before)
        with patch('trades.shop_cap_casualty',return_value=False):
            CT._fix_one(L,t,self.rng(),0,roster_target=53)
        self.assertIn(qb,t.active())
        self.assertNotIn(lt,t.active())
        self.assertGreaterEqual(t.cap_space+.0005,CT.roster_reserve(t,CAP.get(L.year,301.2)))

    def test_injured_backup_makes_starting_qb_more_important(self):
        L,t,qb,lt=self.short_cap_roster()
        t.by_pos('QB')[-1].out_until=8
        with patch('trades.shop_cap_casualty',return_value=False):
            CT._fix_one(L,t,self.rng(),0,roster_target=53)
        self.assertIn(qb,t.active())
        self.assertNotIn(lt,t.active())

    def test_credible_successor_allows_expensive_qb_release(self):
        L,t,qb,lt=self.short_cap_roster()
        qb.age=36
        set_grade(t.by_pos('QB')[-1],95)
        set_grade(t.by_pos('LT')[0],75)
        set_grade(lt,95)
        t.gm.contract_focus=1.0
        with patch('trades.shop_cap_casualty',return_value=False):
            CT._fix_one(L,t,self.rng(),0,roster_target=53)
        self.assertNotIn(qb,t.active())
        self.assertIn(lt,t.active())
        self.assertGreaterEqual(t.cap_space+.0005,CT.roster_reserve(t,CAP.get(L.year,301.2)))

    def test_cap_focus_changes_marginal_release_choice(self):
        low_small=CT.funded_release_value(7,17,1,0,0,contract_focus=.1)
        low_large=CT.funded_release_value(7,42,1,3,0,contract_focus=.1)
        high_small=CT.funded_release_value(7,17,1,0,0,contract_focus=1.)
        high_large=CT.funded_release_value(7,42,1,3,0,contract_focus=1.)
        self.assertGreater(low_small,low_large)
        self.assertGreater(high_large,high_small)

    def test_campbell_darrisaw_tackle_tradeoff_preserves_control(self):
        L,t,qb,old_tackle=self.short_cap_roster()
        young=t.by_pos('LT')[0]
        young.age=25; young.accrued=2; young.contract=Contract(3,[1.1]*3)
        old_tackle.age=32; set_grade(old_tackle,89)
        # The veteran has a slight present-day edge, but the young tackle's
        # cheap control and playable grade matter when funding the full club.
        t.sync_cap(); t.cap.cap=t.cap.charges(t.phase)+1.104
        with patch('trades.shop_cap_casualty',return_value=False):
            CT._fix_one(L,t,self.rng(),0,roster_target=53)
        self.assertIn(young,t.active())
        self.assertNotIn(old_tackle,t.active())

    def test_restructure_quote_matches_five_year_proration_limit(self):
        L = fixture(); p = player(L, contract=Contract(7, [20]*7))
        quote = CT.restructure_room(p, CAP[L.year])
        before = p.cap_hit(0)
        p.contract.restructure(0, min_base=MS.minimum_salary(p.accrued,CAP[L.year]))
        self.assertAlmostEqual(quote, before-p.cap_hit(0))

    def test_cannot_cut_minimums_to_fund_their_own_replacements(self):
        L, t = self.roster()
        for p in t.roster: p.contract = Contract(1, [MS.minimum_salary(0,CAP.get(L.year,301.2))])
        t.cap.cap = .1; before = list(t.roster)
        CT.enforce(L, self.rng(), roster_target=53, target=0)
        self.assertEqual(t.roster, before)
        self.assertTrue(CD.violations(L))

    def test_user_never_restructured_or_cut_by_final_recovery(self):
        L, t = self.roster(); L.user_team = t.abbr; t.cap.cap = .1
        before = [(p.pid, copy.deepcopy(p.contract.base)) for p in t.roster]
        CD.finalize(L, self.rng())
        self.assertEqual(before, [(p.pid,p.contract.base) for p in t.roster])

    def test_high_dead_cap_does_not_veto_needed_net_saving_cut(self):
        L,t=self.roster(); t.roster.pop()
        for p in t.roster: p.contract=Contract(1,[1])
        p=t.by_pos('QB')[0]; p.contract=Contract(1,[10],signing_bonus=20)
        t.sync_cap(); t.cap.cap=t.cap.charges(t.phase)-2
        self.assertFalse(CT.sensible_release(p,june1=True)[0])
        with patch('trades.shop_cap_casualty',return_value=False):
            CT.enforce(L,self.rng(),roster_target=53,target=0)
        self.assertNotIn(p,t.roster)
        self.assertAlmostEqual(t.cap.dead,20)
        self.assertGreaterEqual(t.cap_space,CT.roster_reserve(t,CAP.get(L.year,301.2)))

    def test_emergency_street_sign_refuses_before_releasing_anyone(self):
        L = fixture(); t = L.teams['GB']; L.user_team = 'MIN'
        for i in range(53): player(L, pid=str(i), contract=Contract(1,[1]))
        p = player(L,pid='new',team=None); L.free_agents.append(p.pid)
        t.cap.cap = 53; before = list(t.roster); transactions = list(L.transactions)
        self.assertFalse(PS.sign_minimum(L,'GB',p))
        self.assertEqual(t.roster, before)
        self.assertEqual(L.transactions, transactions)
        self.assertIn(p.pid,L.free_agents)

    def test_street_minimum_pays_only_remaining_weeks(self):
        L = fixture(); t = L.teams['GB']; t.cap.paid_week = 9
        p = player(L,team=None); L.free_agents.append(p.pid)
        salary = MS.minimum_salary(p.accrued,CAP[L.year])
        t.cap.cap = salary * .6
        self.assertTrue(PS.sign_minimum(L,'GB',p))
        self.assertAlmostEqual(p.contract.base[0], salary/2)
        self.assertEqual(p.contract.pay_start,9)
        self.assertGreaterEqual(t.cap_space,0)

    def test_pending_waiver_cannot_be_signed_as_street_fa(self):
        L = fixture(); p = player(L,contract=Contract(1,[1])); p.accrued=1
        L.release(p.pid)
        self.assertIn(p.pid,L.free_agents)
        self.assertFalse(PS.sign_minimum(L,'MIN',p))
        self.assertIsNone(p.team)

    def test_injured_ps_player_cannot_fill_healthy_role(self):
        L=fixture(); p=player(L,team=None); L.free_agents.append(p.pid)
        self.assertTrue(PS.sign_to_squad(L,'GB',p.pid)); p.out_until=8
        self.assertFalse(PS.call_up(L,'GB',p.pid,emergency=True))
        self.assertIn(p,PS.squad(L.teams['GB']))

    def test_weekly_refill_tries_affordable_rookie_after_costly_veteran(self):
        L,t=self.roster(); L.set_phase('regular')
        template=t.by_pos('QB')[0]
        t.roster=[p for p in t.roster if p.pos!='QB']
        candidates=[]
        for pid,accrued,grade in [('costly',10,90),('affordable',0,65)]:
            p=copy.deepcopy(template); p.pid=pid; p.team=None; p.contract=None
            p.accrued=accrued; p.ratings={k:grade for k in p.ratings}
            L.players[pid]=p; L.free_agents.append(pid); candidates.append(p)
        t.sync_cap()
        t.cap.cap=t.cap.charges(t.phase)+MS.minimum_salary(0,CAP.get(L.year,301.2))+.01
        PS.keep_groups_whole(L,self.rng(),1)
        self.assertIsNone(candidates[0].team)
        self.assertEqual(candidates[1].team,t.abbr)
        self.assertGreaterEqual(t.cap_space,-.0005)

    def test_missing_specialist_is_legally_poached_before_conversion(self):
        L,t=self.roster(); t.by_pos('LS')[0].pos='TE'
        other=Team('GB','United North','United'); other.league=L; L.teams['GB']=other
        p=copy.deepcopy(t.by_pos('TE')[0]); p.pid='ps-snapper'; p.pos='LS'
        p.team='GB'; p.contract=None; L.players[p.pid]=p; PS.squad(other).append(p)
        self.assertEqual(CD.repair_shape(L),1)
        self.assertEqual(p.team,t.abbr)
        self.assertNotIn(p,PS.squad(other))
        self.assertIn(p,t.roster)
        self.assertEqual(len(t.active()),53)
        self.assertFalse(RN.assess(t)['uncovered'])
        self.assertFalse(any(q.transition for q in t.roster))

    def test_missing_long_snapper_can_use_reserve_conversion(self):
        L,t=self.roster()
        snapper=t.by_pos('LS')[0]; snapper.pos='TE'
        before={p.pid:copy.deepcopy(p.ratings) for p in t.roster}
        self.assertIn('LS',RN.assess(t)['uncovered'])
        self.assertEqual(CD.repair_shape(L),1)
        self.assertFalse(RN.assess(t)['uncovered'])
        self.assertEqual(len(t.active()),53)
        self.assertEqual(before,{p.pid:p.ratings for p in t.roster})
        moved=[p for p in t.roster if p.transition]
        self.assertEqual(len(moved),1)
        self.assertEqual(moved[0].transition['to'],'LS')

    def test_impossible_final_roster_keeps_calendar_closed(self):
        L,t=self.roster(); L.teams={'MIN':t}
        for p in t.roster: p.contract=Contract(1,[1])
        t.cap.cap=.1
        s=Session(L,self.rng(),'GB'); s.stop=('wire',)
        with patch('waivers.process'), patch('practice_squad.fill_squads') as fill:
            self.assertFalse(s.step_clear_wire())
            fill.assert_not_called()
        self.assertIn('MIN',s._cpu_roster_block)
        self.assertNotEqual(L.phase,'regular')

    def test_new_compliance_waivers_keep_user_claim_opportunity(self):
        L,t=self.roster(); s=Session(L,self.rng(),'GB')
        import waivers as WV
        opening=dict(pid='opening-cut',claims=['GB'])
        new=dict(pid='new-cut',claims=[],user_notified=False)
        L.waivers=[opening]
        def new_cut(*args):
            if new not in L.waivers:L.waivers.append(new)
        def award(*args,entries):
            self.assertEqual(entries,[opening])
            for entry in entries:L.waivers.remove(entry)
            return []
        with patch.object(CD,'finalize',side_effect=new_cut), \
             patch.object(CD,'violations',return_value=[]), \
             patch.object(WV,'notify_user') as note, patch.object(WV,'process',side_effect=award) as process, \
             patch('veteran_market.review'), patch.object(PS,'fill_squads'), \
             patch('franchise.clear_undrafted'), patch('morale.review_captains'):
            self.assertIsNone(s.step_clear_wire())
            process.assert_called_once()
            note.assert_called_once_with(L,[new],1,digest=True)
        self.assertEqual(L.waivers,[new])
        self.assertEqual(new['claims'],[])
        self.assertEqual(L.phase,'regular')

    def test_already_valid_roster_is_unchanged(self):
        L,t=self.roster(); before=[(p.pid,copy.deepcopy(p.contract.base)) for p in t.roster]
        rng=self.rng(); state=copy.deepcopy(rng.bit_generator.state)
        self.assertEqual(CD.finalize(L,rng),([],0))
        self.assertEqual(before,[(p.pid,p.contract.base) for p in t.roster])
        self.assertEqual(state,rng.bit_generator.state)

    def test_batch_finalization_counts_every_contract(self):
        L,t=self.roster(); t.phase='camp'
        for p in t.roster: p.contract=Contract(1,[1])
        t.cap.cap=51.2
        self.assertGreater(t.cap_space,0)
        CD.finalize(L,self.rng())
        self.assertEqual(t.phase,'season')
        self.assertLess(t.cap_space,0)
        self.assertTrue(CD.violations(L))


if __name__=='__main__': unittest.main()

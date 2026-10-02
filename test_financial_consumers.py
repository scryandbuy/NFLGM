"""CPU budget boundaries: exact contracts, atomic refusals and human control."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

import extensions as EX
import practice_squad as PS
import trades as TR
import waivers as W
import tags as TAG
import financial_plan as FP
import cap_accounting as CA
import roster_needs as RN
from cap_engine import Contract
from league import Team, DraftPick, contract_to_dict
import test_roster_cap_recovery as recovery_fixture
import test_cpu_extension_counters as extension_fixture
from test_cap_accounting import fixture, player


class FinancialConsumerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = recovery_fixture.RecoveryTests().roster()[0]

    def roster(self):
        L = copy.deepcopy(self.base)
        L.set_phase('regular'); L.week = 9
        t = L.teams['MIN']; t.cap.paid_week = 9
        return L, t

    def arrival(self, L, t, source=None):
        p = copy.deepcopy(t.by_pos('WR')[-1])
        p.pid = 'financial-new'; p.name = 'New Receiver'; p.team = source
        p.contract = None; p.accrued = 2; p.out_until = None
        p.xp_spent = {}; p.ratings = {k: 95 for k in p.ratings}
        L.players[p.pid] = p
        if source:
            other = Team(source, 'United North', 'United'); other.league = L
            L.teams[source] = other; PS.squad(other).append(p)
        else:
            L.free_agents.append(p.pid)
        return p

    def test_extension_budget_receives_full_replacement_and_can_refuse_atomically(self):
        case = extension_fixture.CpuExtensionCounters(); case.setUp()
        L, p = case.L, case.p
        before = contract_to_dict(p.contract)
        with patch.object(EX, 'terms', return_value=case.quote), \
             patch.object(FP, 'evaluate', return_value=dict(approved=False, reason='preserve_flexibility')) as budget:
            result = EX.negotiate_ai(L, p, 20, 3, case.rng)
        self.assertEqual(result['result'], 'refused')
        self.assertEqual(result['why'], 'preserve_flexibility')
        self.assertEqual(contract_to_dict(p.contract), before)
        self.assertGreater(budget.call_count, 0)
        for call in budget.call_args_list:
            candidate, contract = call.kwargs['additions'][0]
            self.assertIs(candidate, p)
            self.assertEqual(contract.years, 4)
            self.assertGreater(contract.cap_hit(0), p.contract.cap_hit(0))
            self.assertNotIn('removals', call.kwargs)

    def test_user_extension_keeps_authoritative_rules_without_cpu_veto(self):
        case = extension_fixture.CpuExtensionCounters(); case.setUp(); case.L.user_team = 'MIN'
        with patch.object(EX, 'terms', return_value=case.quote), patch.object(FP, 'evaluate') as budget:
            result = EX.extend(case.L, case.p.pid, 20, 3, agreed=True)
        self.assertEqual(result['result'], 'accepted')
        budget.assert_not_called()

    def test_cpu_option_uses_preview_and_user_option_remains_available(self):
        L, t = self.roster(); p = t.by_pos('QB')[0]
        p.contract = Contract(1, [1]); p.draft_round = 1; p.draft_year = L.year - 3
        with patch.object(FP, 'evaluate', return_value=dict(approved=False, reason='preserve_retention')) as budget:
            self.assertFalse(EX.exercise_rookie_option(L, p.pid, by_ai=True)['ok'])
            self.assertEqual(p.contract.years, 1)
            self.assertEqual(budget.call_args.kwargs['additions'][0][1].years, 2)
            self.assertTrue(EX.exercise_rookie_option(L, p.pid)['ok'])
        self.assertEqual(p.contract.years, 2)
        self.assertEqual(budget.call_count, 1)

    def test_poach_budget_failure_keeps_both_rosters_and_source_contract(self):
        L, t = self.roster(); p = self.arrival(L, t, 'DEN')
        before = [q.pid for q in t.roster]
        with patch.object(FP, 'evaluate', return_value=dict(approved=False, reason='preserve_flexibility')) as budget:
            self.assertFalse(PS.poach(L, t.abbr, p.pid, 9))
        self.assertEqual([q.pid for q in t.roster], before)
        self.assertIn(p, PS.squad(L.teams['DEN']))
        self.assertEqual(p.team, 'DEN'); self.assertIsNone(p.contract)
        self.assertEqual(budget.call_args.kwargs['action'], 'ps_poach')
        self.assertLess(budget.call_args.kwargs['additions'][0][1].base[0], 1)

    def test_essential_callup_can_use_cushion_but_not_break_cap(self):
        L, t = self.roster(); p = self.arrival(L, t)
        L.free_agents.remove(p.pid); p.team = t.abbr; PS.squad(t).append(p)
        t.roster.remove(t.by_pos('WR')[-1]); t.sync_cap()
        cost = PS.minimum_contract(L, t, p).base[0]
        t.cap.cap = t.cap.charges(t.phase) + cost + .001
        self.assertLess(FP.snapshot(L, t)['discretionary_room'], 0)
        self.assertTrue(PS.call_up(L, t.abbr, p.pid, emergency=True))
        self.assertGreaterEqual(t.cap_space, -.0005)
        L, t = self.roster(); p = self.arrival(L, t)
        L.free_agents.remove(p.pid); p.team = t.abbr; PS.squad(t).append(p)
        t.roster.pop(); t.sync_cap(); t.cap.cap = t.cap.charges(t.phase)
        self.assertFalse(PS.call_up(L, t.abbr, p.pid, emergency=True))
        self.assertIn(p, PS.squad(t))

    def test_optional_upgrade_does_not_gain_emergency_status_from_its_own_cut(self):
        L, t = self.roster(); p = self.arrival(L, t)
        outgoing = t.by_pos('WR')[-1]
        with patch.object(FP, 'evaluate', return_value=dict(approved=True)) as budget:
            PS._cpu_move_budget(L, t, p, PS.minimum_contract(L, t, p), outgoing,
                               action='roster_upgrade')
        self.assertFalse(budget.call_args.kwargs['essential'])
        self.assertEqual(budget.call_args.kwargs['removals'], [outgoing.pid])

    def test_waiver_budget_refusal_never_releases_a_player(self):
        L, t = self.roster(); p = self.arrival(L, t)
        p.contract = Contract(1, [.3])
        entry = dict(pid=p.pid, from_team='DEN', claims=[])
        before = [q.pid for q in t.roster]
        with patch.object(PS, 'protected', return_value=False), \
             patch.object(FP, 'evaluate', return_value=dict(approved=False)) as budget:
            self.assertFalse(W.make_room(L, t.abbr, p, entry))
        self.assertEqual([q.pid for q in t.roster], before)
        self.assertTrue(budget.called)
        self.assertIsNone(p.team)

    def test_user_callup_never_consults_cpu_budget(self):
        L, t = self.roster(); L.user_team = t.abbr
        p = self.arrival(L, t); L.free_agents.remove(p.pid)
        p.team = t.abbr; PS.squad(t).append(p); t.roster.pop()
        with patch.object(FP, 'evaluate') as budget:
            self.assertTrue(PS.call_up(L, t.abbr, p.pid))
        budget.assert_not_called()

    def test_trade_proposals_price_both_sides_and_new_pick_inventory(self):
        L = fixture(); L.user_team = None; L.set_phase('offseason')
        a, b = L.teams['GB'], L.teams['MIN']
        p = player(L, 'from-a', 'GB', Contract(3, [4]*3, signing_bonus=6))
        q = player(L, 'from-b', 'MIN', Contract(2, [5]*2, signing_bonus=8))
        pk = DraftPick(2026, 1, 'GB', 'GB'); a.picks = [pk]
        before = [(x.team, contract_to_dict(x.contract)) for x in (p,q)]
        with patch.object(FP, 'evaluate', return_value=dict(approved=True)) as budget:
            self.assertTrue(TR._financial_trade(L, a, b, [p.pid, pk], [q.pid]))
        self.assertEqual(budget.call_count, 2)
        ca, cb = budget.call_args_list
        self.assertEqual(ca.kwargs['picks'], [])
        self.assertEqual(cb.kwargs['picks'], [pk])
        self.assertEqual(ca.kwargs['additions'][0][1].sb, 0)
        self.assertEqual(cb.kwargs['additions'][0][1].sb, 0)
        self.assertGreater(ca.kwargs['trial_cap'].dead, 0)
        self.assertEqual(before, [(x.team, contract_to_dict(x.contract)) for x in (p,q)])
        self.assertEqual(pk.owner, 'GB')

    def test_trade_financial_refusal_keeps_all_assets_in_place(self):
        L = fixture(); L.user_team = None; L.set_phase('offseason')
        a,b = L.teams['GB'], L.teams['MIN']
        p = player(L, 'target', 'MIN', Contract(1, [5]))
        pk = DraftPick(2026, 2, 'GB', 'GB'); a.picks = [pk]
        with patch.object(FP, 'evaluate', return_value=dict(approved=False)):
            self.assertFalse(TR._financial_trade(L, a, b, [pk], [p.pid]))
        self.assertEqual(pk.owner, 'GB'); self.assertIn(pk, a.picks)
        self.assertEqual(p.team, 'MIN'); self.assertIn(p,b.roster)

    def test_pick_alternatives_reuse_only_current_negotiation_roster_math(self):
        L=fixture(); L.user_team=None; L.set_phase('offseason')
        a,b=L.teams['GB'],L.teams['MIN']
        p=player(L,'target','MIN',Contract(1,[5]))
        picks=[DraftPick(2026,r,'GB','GB') for r in (1,2)]; a.picks=picks[:]
        cache={}
        with patch.object(RN,'assess',wraps=RN.assess) as assess, \
             patch.object(FP,'retention_market',wraps=FP.retention_market) as market, \
             patch.object(FP,'evaluate',return_value=dict(approved=True)) as budget:
            self.assertTrue(TR._financial_trade(L,a,b,[picks[0]],[p.pid],cache))
            count=assess.call_count
            self.assertTrue(TR._financial_trade(L,a,b,[picks[1]],[p.pid],cache))
            self.assertEqual(assess.call_count,count)
            self.assertEqual(market.call_count,1)
            self.assertEqual(budget.call_args_list[0].kwargs['picks'],[picks[1]])
            self.assertEqual(budget.call_args_list[2].kwargs['picks'],[picks[0]])
            self.assertTrue(TR._financial_trade(L,a,b,[picks[1]],[p.pid]))
            self.assertGreater(assess.call_count,count)
            self.assertEqual(market.call_count,2)

    def test_real_policy_rejects_discretionary_poach_when_only_reserve_remains(self):
        for room, expected in ((1., False), (30., True)):
            with self.subTest(room=room):
                L, t = self.roster(); p = self.arrival(L, t, 'DEN')
                for q in t.by_pos('WR'):
                    q.contract = Contract(1, [.05])
                t.sync_cap(); t.cap.cap = t.cap.charges(t.phase) + room
                before = [q.pid for q in t.roster]
                with patch.object(PS, 'protected', return_value=False):
                    result = PS.poach(L, t.abbr, p.pid, 9)
                self.assertEqual(result, expected)
                self.assertGreaterEqual(t.cap_space, -.0005)
                self.assertEqual(len(t.active()), 53)
                if expected:
                    self.assertIn(p,t.roster)
                    self.assertNotIn(p,PS.squad(L.teams['DEN']))
                    self.assertTrue(PS.locked(p, 10))
                else:
                    self.assertEqual([q.pid for q in t.roster],before)
                    self.assertIn(p,PS.squad(L.teams['DEN']))

    def test_real_trade_budget_changes_with_available_resources(self):
        for room, expected in ((4.5,False), (40.,True)):
            with self.subTest(room=room):
                L,t = self.roster(); L.user_team = None
                p = self.arrival(L,t,'DEN'); b=L.teams['DEN']
                PS.squad(b).remove(p); b.roster.append(p)
                p.contract=Contract(2,[5,5],signing_bonus=4)
                b.sync_cap(); t.sync_cap(); t.cap.cap=t.cap.charges(t.phase)+room
                pk=DraftPick(L.year+2,7,t.abbr,t.abbr); t.picks=[pk]
                with patch.object(PS, 'protected', return_value=False):
                    decision=TR._financial_trade(L,t,b,[pk],[p.pid])
                self.assertEqual(decision,expected)
                self.assertEqual(p.team,'DEN'); self.assertEqual(pk.owner,t.abbr)

    def test_tag_can_keep_major_player_but_respects_shared_funding(self):
        for room, expected in ((1., False), (50., True)):
            with self.subTest(room=room):
                L,t=self.roster(); L.set_phase('offseason'); t.cap.paid_week=0
                p=t.by_pos('WR')[0]; p.contract=None; p.accrued=6
                p.ratings={k:95 for k in p.ratings}
                t.sync_cap(); price=TAG.tag_price(p,t.cap.cap)
                t.cap.cap=t.cap.charges(t.phase)+price+room
                result=TAG.run(L,np.random.default_rng(12))
                self.assertEqual(bool(result['tagged']),expected)
                if expected:
                    self.assertEqual(p.fa_class,'tagged'); self.assertEqual(p.team,t.abbr)
                else:
                    self.assertIsNone(p.team); self.assertIn(p.pid,L.free_agents)

    def test_marginal_tender_declines_while_user_choice_and_erfa_are_preserved(self):
        for mode in ('cpu_rfa','user_rfa','erfa'):
            with self.subTest(mode=mode):
                L,t=self.roster(); L.set_phase('offseason'); t.cap.paid_week=0
                p=t.by_pos('WR')[-1]; p.contract=None
                p.accrued=2 if mode=='erfa' else 3
                t.sync_cap(); price=TAG.tender_price(p,t.cap.cap)
                t.cap.cap=t.cap.charges(t.phase)+price+.1
                if mode=='user_rfa': L.user_team=t.abbr; L.user_tenders=[p.pid]
                result=TAG.run(L,np.random.default_rng(12))
                if mode=='cpu_rfa':
                    self.assertEqual(result['tendered'],[]); self.assertIsNone(p.team)
                elif mode=='user_rfa':
                    self.assertEqual(result['tendered'][0][1],p)
                else:
                    self.assertEqual(result['reserved'][0][1],p)


if __name__ == '__main__': unittest.main()

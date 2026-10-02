import copy
import unittest
from unittest.mock import patch, PropertyMock
from types import SimpleNamespace
import numpy as np
from cap_engine import Contract, CAP
from gm_engine import GM
from league import League
from test_cap_accounting import fixture, player
import extensions as EXT
import negotiations as NG
import contract_offer as CO
import contract_structure as CS
import market as MK


class CpuExtensionCounters(unittest.TestCase):
    def setUp(self):
        self.L=fixture(); self.L.user_team='GB'; self.L.set_phase('free_agency')
        self.team=self.L.teams['MIN']; self.team.gm=GM(); self.team.gm.restructure_depth=.5
        self.team.cap.cap=500
        self.p=player(self.L,'cpu-extension',team='MIN',contract=Contract(1,[3],signed=2026))
        self.p.pos='WR'; self.p.age=27
        self.quote=dict(ask=20.,offer=20.,years=3,discount=0.)
        self.rng=np.random.default_rng(14)

    def test_complete_counter_can_be_accepted_at_its_exact_terms(self):
        with patch.object(EXT,'terms',return_value=dict(self.quote,ask=20.001)):
            result=EXT.extend(self.L,self.p.pid,19,3,bonus=0,front_load=.05)
            self.assertEqual(result['result'],'countered')
            counter=result['counter']
            self.assertEqual(counter['apy'],20.01)
            self.assertEqual(counter['front_load'],.5)
            self.assertGreater(counter['bonus'],0)
            expected=EXT.build(self.p,3,counter['apy'],CAP[2026],self.team.gm,self.L,
                bonus=counter['bonus'],front_load=counter['front_load'])
            signed=EXT.extend(self.L,self.p.pid,counter['apy'],counter['years'],
                bonus=counter['bonus'],front_load=counter['front_load'])
        self.assertEqual(signed['result'],'accepted')
        self.assertEqual(self.p.contract.base,expected.base)
        self.assertEqual(self.p.contract.bonus_schedule,expected.bonus_schedule)

    def test_cpu_solves_backloaded_offer_without_more_pay_or_years(self):
        state=copy.deepcopy(self.rng.bit_generator.state)
        original=copy.deepcopy(vars(self.p.contract))
        with patch.object(EXT,'terms',return_value=self.quote), patch.object(CS,'choose_shape',return_value=.05):
            rejected=EXT.extend(self.L,self.p.pid,20,3,by_ai=True)
            self.assertEqual(rejected['result'],'countered')
            self.assertEqual(vars(self.p.contract),original)
            result=EXT.negotiate_ai(self.L,self.p,20,3,self.rng)
        self.assertEqual(result['result'],'accepted')
        self.assertEqual(result['attempts'],2)
        self.assertEqual(result['apy'],20)
        self.assertEqual(result['years'],3)
        self.assertEqual(result['front_load'],.5)
        self.assertAlmostEqual(sum(self.p.contract.base[1:])+self.p.contract.sb,60)
        self.assertEqual(state,self.rng.bit_generator.state)
        loaded=League.load(self.L.save()).player(self.p.pid)
        self.assertEqual(loaded.contract.base,self.p.contract.base)

    def test_cpu_walks_when_counter_is_outside_its_budget(self):
        before=copy.deepcopy(vars(self.p.contract))
        with patch.object(EXT,'terms',return_value=self.quote), patch.object(CS,'choose_shape',return_value=.05):
            result=EXT.negotiate_ai(self.L,self.p,16,3,self.rng)
        self.assertEqual(result['result'],'countered')
        self.assertLessEqual(result['attempts'],5)
        self.assertEqual(vars(self.p.contract),before)

    def test_cpu_does_not_add_years_to_buy_acceptance(self):
        with patch.object(EXT,'terms',return_value=dict(self.quote,years=5)), patch.object(CS,'choose_shape',return_value=.05):
            result=EXT.negotiate_ai(self.L,self.p,16,2,self.rng)
        self.assertNotEqual(result['result'],'accepted')
        self.assertEqual(self.p.contract.years,1)

    def test_current_cap_blocks_every_alternative_without_mutation(self):
        self.team.cap.cap=0
        before=copy.deepcopy(vars(self.p.contract))
        with patch.object(EXT,'terms',return_value=self.quote):
            result=EXT.negotiate_ai(self.L,self.p,20,3,self.rng)
        self.assertEqual(result['attempts'],0)
        self.assertEqual(vars(self.p.contract),before)

    def test_future_cap_blocks_even_when_current_year_has_room(self):
        player(self.L,'future',team='MIN',contract=Contract(4,[1,1200,1,1]))
        before=copy.deepcopy(vars(self.p.contract))
        with patch.object(EXT,'terms',return_value=self.quote):
            result=EXT.negotiate_ai(self.L,self.p,20,3,self.rng)
        self.assertEqual(result['attempts'],0)
        self.assertEqual(vars(self.p.contract),before)

    def test_firm_refusal_blocks_cpu_and_direct_ai_signing(self):
        with patch.object(NG,'extension_defers',return_value=True), patch.object(EXT,'terms') as quote:
            self.assertEqual(EXT.negotiate_ai(self.L,self.p,100,7,self.rng)['result'],'refused')
            self.assertEqual(EXT.extend(self.L,self.p.pid,100,7,by_ai=True)['result'],'refused')
            quote.assert_not_called()
        self.assertEqual(self.p.contract.years,1)

    def test_closed_negotiation_stays_closed(self):
        self.L.negotiations=[dict(pid=self.p.pid,team='MIN',kind='extension',state='declined')]
        result=EXT.negotiate_ai(self.L,self.p,100,7,self.rng)
        self.assertEqual(result['result'],'refused')
        self.assertEqual(self.L.negotiations[0]['state'],'declined')
        self.assertEqual(self.p.contract.years,1)

    def test_original_acceptable_offer_keeps_gm_structure(self):
        with patch.object(EXT,'terms',return_value=self.quote), patch.object(CS,'choose_shape',return_value=.85):
            result=EXT.negotiate_ai(self.L,self.p,20,3,self.rng)
        self.assertEqual(result['result'],'accepted')
        self.assertEqual(result['attempts'],1)
        self.assertEqual(result['front_load'],.85)

    def test_cpu_cannot_negotiate_user_contracts(self):
        self.L.user_team='MIN'
        self.assertEqual(EXT.negotiate_ai(self.L,self.p,100,7,self.rng)['result'],'refused')
        self.assertEqual(self.p.contract.years,1)

    def test_bonus_concession_is_bounded_for_low_bonus_gm(self):
        self.team.gm.restructure_depth=0
        with patch.object(EXT,'terms',return_value=self.quote), patch.object(CS,'choose_shape',return_value=.05), \
             patch.object(EXT,'extend',wraps=EXT.extend) as offers:
            EXT.negotiate_ai(self.L,self.p,20,3,self.rng)
        self.assertGreater(offers.call_count,1)
        for call in offers.call_args_list:
            self.assertLessEqual(call.kwargs['bonus'],60*(.22+.10)+1e-9)
            self.assertLessEqual(call.args[2],20)
            self.assertEqual(call.args[3],3)

    def test_restricted_player_conversion_uses_the_same_counter_path(self):
        self.p.fa_class='tendered'; self.p.tender_team='MIN'
        self.L.free_agents.append(self.p.pid)
        with patch.object(EXT,'terms',return_value=self.quote), patch.object(CS,'choose_shape',return_value=.05), \
             patch.object(type(self.p),'ovr',new_callable=PropertyMock,return_value=85):
            converted=MK.convert_tenders(self.L,SimpleNamespace(random=lambda:0.),1,user_team='GB')
        self.assertEqual(converted,[self.p])
        self.assertEqual(self.p.fa_class,'under_contract')
        self.assertIsNone(self.p.tender_team)
        self.assertNotIn(self.p.pid,self.L.free_agents)
        self.assertEqual(self.p.contract.years,4)

    def test_weekly_cpu_extension_route_can_resolve_a_structure_counter(self):
        self.L.set_phase('regular'); self.L.week=5
        with patch.object(EXT,'terms',return_value=self.quote), patch.object(CS,'choose_shape',return_value=.05), \
             patch.object(type(self.p),'ovr',new_callable=PropertyMock,return_value=85):
            signed=EXT.in_season_round(self.L,SimpleNamespace(random=lambda:0.),5)
        self.assertEqual(len(signed),1)
        self.assertEqual(signed[0][0],'MIN')
        self.assertEqual(self.p.contract.years,4)

    def test_previous_week_number_does_not_create_an_offseason_refusal(self):
        self.L.week=10
        situation=dict(in_season=True,star=True,final_year=True,money=.9,morale=60,loyalty=.1)
        with patch.object(NG,'_situation',return_value=situation), patch.object(NG,'stable_seed',return_value=1):
            self.assertFalse(NG.extension_defers(self.L,self.p))
            self.L.set_phase('regular')
            self.assertTrue(NG.extension_defers(self.L,self.p))


if __name__=='__main__': unittest.main()

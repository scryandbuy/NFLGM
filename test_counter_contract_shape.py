import unittest
from unittest.mock import patch
from test_negotiation_stages import NegotiationStageTests
import negotiations as NG
import views_personnel as VP
import extensions as EXT
import contract_structure as CS
from cap_engine import Contract
from gm_engine import GM
from league import League


class CounterContractTests(unittest.TestCase):
    def test_counter_preserves_bonus_through_reload_and_accept(self):
        f=NegotiationStageTests();f.setUp();L,t,p=f.L,f.t,f.p
        t['rival']=None;t['state']='waiting'
        offer=dict(apy=19,years=3,bonus=12,front_load=.5,promises=[])
        t['offers']=[offer]
        NG._answer(L,t,p,offer,22)
        self.assertEqual(t['counter']['bonus'],12)
        L=League.load(L.save());L.user_team='GB'
        with patch.object(NG,'_floor',return_value=22), patch.object(NG,'_accept',return_value={'ok':True}) as accept:
            self.assertTrue(VP.act_match_counter(L,'GB',1)['ok'])
        self.assertEqual(accept.call_args.args[2]['bonus'],12)
        self.assertEqual(accept.call_args.args[2]['front_load'],.5)

    def test_legacy_counter_recovers_explicit_bonus(self):
        f=NegotiationStageTests();f.setUp();f.t['offers'][-1].update(bonus=12,front_load=.5)
        with patch.object(NG,'make_offer',return_value={'ok':True}) as offer:
            VP.act_match_counter(f.L,'GB',1)
        self.assertEqual(offer.call_args.kwargs['bonus'],12)

    def test_even_extension_keeps_old_charges_and_flat_new_base(self):
        f=NegotiationStageTests();f.setUp();p=f.p
        p.contract=Contract(1,[28],bonus_schedule=[13.2343])
        for bonus in (None,68):
            c=EXT.build(p,5,47.98,337,GM(),f.L,front_load=.5,bonus=bonus)
            self.assertEqual(c.base[0],28)
            self.assertLess(max(c.base[1:])-min(c.base[1:]),.005)
            self.assertAlmostEqual(sum(c.base[1:])+sum(c.bonus_schedule)-13.2343,239.9,places=3)
            if bonus is not None:self.assertAlmostEqual(sum(c.bonus_schedule)-13.2343,68)

    def test_explicit_shapes_are_monotonic(self):
        for shape in (0,.5,1):
            bases=CS.structure(40,5,'QB',337,GM(),front_load=shape)['base']
            if shape==.5:self.assertLess(max(bases)-min(bases),.005)
            else:self.assertEqual(list(bases),sorted(bases,reverse=shape==1))

if __name__=='__main__':unittest.main()

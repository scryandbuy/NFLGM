import unittest
from unittest.mock import patch
from types import SimpleNamespace as N
from cap_engine import Contract
from cap_accounting import settle_week, trade_projection, require_room
from league import League, Player, contract_to_dict, contract_from_dict
from test_cap_accounting import fixture, player
import tags, extensions, waivers

class TagGuaranteeTests(unittest.TestCase):
    def tagged(self, L):
        p=player(L, contract=tags._one_year(40.68, L.year, tagged=True))
        p.fa_class='tagged'; p.tagged_year=L.year; p.tag_count=1
        return p

    def test_cruz_three_week_release_keeps_entire_tag_cost(self):
        for june1 in (False, True):
            L=fixture(); p=self.tagged(L); t=L.teams['GB']
            settle_week(L,3); before=t.cap_space
            self.assertAlmostEqual(p.contract.earned_base,6.78)
            self.assertEqual(L.release(p.pid,june1=june1),(33.9,0.0,0.0))
            self.assertAlmostEqual(t.cap.earned,6.78)
            self.assertAlmostEqual(t.cap_space,before)
            self.assertAlmostEqual(League.load(L.save()).teams['GB'].cap_space,before)

    def test_release_cannot_fund_replacement_but_real_room_can(self):
        L=fixture(); p=self.tagged(L); t=L.teams['GB']
        t.cap.cap=40.68; t.cap.rollover=0
        with self.assertRaises(ValueError):
            require_room(L,t,'replacement',Contract(1,[2]),release_pid=p.pid)
        t.cap.cap=43
        require_room(L,t,'replacement',Contract(1,[2]),release_pid=p.pid)

    def test_trade_transfers_unpaid_guarantee_without_seller_dead_salary(self):
        L=fixture(); p=self.tagged(L); settle_week(L,3)
        trial=trade_projection(L,'GB',[p.pid],[])
        self.assertEqual(trial.dead,0)
        L.trade('GB','MIN',[p.pid],[])
        self.assertAlmostEqual(L.teams['GB'].cap.earned,6.78)
        self.assertEqual(L.teams['GB'].cap.dead,0)
        self.assertAlmostEqual(p.contract.tag_guarantee,33.9)
        self.assertAlmostEqual(p.contract.base[0],33.9)
        self.assertEqual(L.release(p.pid),(33.9,0.0,0.0))

    def test_projection_separates_trade_and_roster_release(self):
        L=fixture(); p=self.tagged(L); settle_week(L,3)
        cut=trade_projection(L,'GB',[],[],releases=[p.pid])
        self.assertAlmostEqual(cut.dead,33.9)

    def test_persistence_and_legacy_active_tag(self):
        L=fixture(); p=self.tagged(L); settle_week(L,3)
        d=p.to_dict()
        self.assertEqual(Player.from_dict(d).contract.tag_guarantee,40.68)
        d['contract'].pop('tag_guarantee')
        restored=Player.from_dict(d)
        self.assertEqual(restored.contract.release(0),(33.9,0.0,0.0))
        d['contract']['signed']+=1
        self.assertEqual(Player.from_dict(d).contract.tag_guarantee,0)

    def test_stale_tag_history_does_not_guarantee_a_new_deal(self):
        L=fixture(); p=self.tagged(L)
        p.contract=Contract(1,[12],signed=L.year)
        self.assertEqual(Player.from_dict(p.to_dict()).contract.release(0),(0.0,0.0,12.0))
        d=p.to_dict(); d['contract'].pop('tag_guarantee'); d['fa_class']='under_contract'
        self.assertEqual(Player.from_dict(d).contract.tag_guarantee,0)

    def test_extension_preserves_tag_year_only(self):
        L=fixture(); p=self.tagged(L); settle_week(L,3)
        with patch.object(extensions.CS,'structure',return_value={'base':[10,10],'signing_bonus':0}):
            c=extensions.build(p,2,10,301.2,N(),L)
        self.assertEqual(c.release(0),(33.9,0.0,0.0))
        self.assertEqual(contract_from_dict(contract_to_dict(c)).tag_guarantee,40.68)
        c.advance()
        self.assertEqual(c.tag_guarantee,0)
        self.assertEqual(c.release(0),(0.0,0.0,10.0))

    def test_expired_tag_and_paid_salary_do_not_create_extra_dead_money(self):
        L=fixture(); p=self.tagged(L); settle_week(L,18)
        self.assertEqual(p.contract.release(0),(0.0,0.0,0.0))
        p.contract.advance()
        self.assertEqual(p.contract.tag_guarantee,0)
        self.assertEqual(p.contract.release(0),(0.0,0.0,0.0))

    def test_tender_and_generic_contract_remain_unguaranteed(self):
        for c in (tags._one_year(5,2026),Contract(1,[5])):
            self.assertEqual(c.release(0),(0.0,0.0,5.0))

    def test_user_tag_creation_and_reload(self):
        L=fixture(); L.set_phase('offseason'); L.user_team='GB'
        p=player(L,contract=None)
        result=tags.user_tag(L,p.pid)
        self.assertTrue(result['ok'], result)
        self.assertEqual(p.contract.tag_guarantee,p.contract.base[0])
        restored=League.load(L.save()).player(p.pid)
        self.assertEqual(restored.contract.release(0)[2],0)

    def test_june1_splits_bonus_without_deferring_tag_salary(self):
        c=Contract(3,[40.68,10,10],signing_bonus=9,tag_guarantee=40.68,earned_base=6.78)
        self.assertEqual(c.release(0,True),(36.9,6.0,0.0))
        self.assertEqual(c.release(0,True,trade=True),(3.0,6.0,33.9))

    def test_waiver_pending_reload_and_later_claim_retains_intervening_pay(self):
        L=fixture(); p=self.tagged(L); L.week=10; settle_week(L,10)
        L.release(p.pid); L=League.load(L.save()); p=L.player(p.pid)
        settle_week(L,11)
        waivers.award(L,waivers.pending(L)[0],'MIN')
        self.assertAlmostEqual(L.teams['GB'].cap.dead,40.68/18,places=3)
        self.assertAlmostEqual(p.contract.tag_guarantee,40.68*7/18)

    def test_claim_transfers_only_remaining_tag_obligation(self):
        L=fixture(); p=self.tagged(L); L.week=10; settle_week(L,10)
        L.release(p.pid)
        entry=waivers.pending(L)[0]
        self.assertGreater(entry['tag_dead'],0)
        waivers.award(L,entry,'MIN')
        self.assertAlmostEqual(L.teams['GB'].cap.dead,0)
        self.assertAlmostEqual(p.contract.tag_guarantee,40.68*8/18)

if __name__=='__main__': unittest.main()

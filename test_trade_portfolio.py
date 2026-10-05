"""Remaining capital is a roster option, not a mandatory draft-pick floor."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from cap_engine import Contract
from league import DraftPick, League
from test_draft_planning import fixture, set_grade
import trade_portfolio as TP


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.L,self.t=fixture()
        self.t.picks=[]
        for p in self.t.roster:
            p.contract=Contract(1,[1.]);p.age=27.;p.dev='normal';p.potential_range=None
        self.t.record=[8,8,0]

    def pick(self,slot=23,offset=0,origin=None):
        p=DraftPick(self.L.year-1+offset,(slot-1)//32+1,origin or f'{slot}-{offset}',
                    self.t.abbr,selection=slot)
        self.t.picks.append(p)
        return p

    def incoming(self,pos='HB',grade=93,years=3,age=28):
        p=copy.deepcopy(self.t.by_pos(pos)[0]);p.pid='arrival';p.team='DEN'
        p.contract=Contract(years,[10.]*years);p.age=age;set_grade(p,grade)
        self.L.players[p.pid]=p
        return p

    def test_same_package_costs_more_from_depleted_than_rich_portfolio(self):
        sent=[self.pick(23),self.pick(27),self.pick(16,2)]
        p=self.incoming()
        depleted=TP.assess(self.L,self.t,sent,[p.pid])
        for offset in range(3):
            for slot in (48,80,112,144,176,208):self.pick(slot,offset)
        rich=TP.assess(self.L,self.t,sent,[p.pid])
        self.assertGreater(depleted['cost'],rich['cost'])
        self.assertGreater(depleted['cost'],0)
        self.assertAlmostEqual(sum(r['weight'] for r in depleted['after']),1.)

    def test_far_future_picks_cannot_cover_earlier_roster_exposure(self):
        sent=self.pick(23)
        distant=self.pick(48,3)
        late=TP.assess(self.L,self.t,[sent])
        self.assertEqual([r['capital'] for r in late['after'][:3]],[0.,0.,0.])
        distant.year-=3
        early=TP.assess(self.L,self.t,[sent])
        self.assertLess(early['cost'],late['cost'])

    def test_young_controlled_roster_needs_less_replenishment(self):
        sent=self.pick()
        exposed=TP.assess(self.L,self.t,[sent])
        for p in self.t.roster:p.age=23.;p.contract=Contract(5,[1.]*5)
        controlled=TP.assess(self.L,self.t,[sent])
        self.assertLess(controlled['cost'],exposed['cost'])
        self.assertEqual(controlled['cost'],0.)

    def test_true_vacancy_receives_more_cover_than_redundant_acquisition(self):
        sent=self.pick()
        p=self.incoming('QB',95,4,24)
        for q in self.t.by_pos('QB'):q.contract=Contract(4,[1.]*4);q.age=24
        redundant=TP.assess(self.L,self.t,[sent],[p.pid])
        self.t.roster=[q for q in self.t.roster if q.pos!='QB']
        vacancy=TP.assess(self.L,self.t,[sent],[p.pid])
        old=vacancy['before'][0]['exposure'];new=vacancy['after'][0]['exposure']
        self.assertLess(new,old)
        self.assertLess(vacancy['cost'],redundant['cost'])

    def test_exporting_starter_does_not_erase_the_vacant_role(self):
        sent=self.pick();qb=self.t.by_pos('QB')[0]
        self.t.roster=[p for p in self.t.roster if p.pos!='QB' or p is qb]
        keep=TP.assess(self.L,self.t,[sent])
        export=TP.assess(self.L,self.t,[sent,qb.pid])
        self.assertGreaterEqual(export['after'][0]['exposure'],keep['after'][0]['exposure'])
        self.assertGreaterEqual(export['cost'],keep['cost'])

    def test_retained_controlled_fallback_reduces_late_role_exposure(self):
        sent=self.pick();old=self.t.by_pos('HB')[0];old.age=24
        old.contract=Contract(4,[1.]*4);set_grade(old,82)
        p=self.incoming('HB',93,3,28)
        kept=TP.assess(self.L,self.t,[sent],[p.pid])
        lost=TP.assess(self.L,self.t,[sent,old.pid],[p.pid])
        kept_hb=next(r for r in kept['after'][3]['families'] if r['family']==['HB'])
        lost_hb=next(r for r in lost['after'][3]['families'] if r['family']==['HB'])
        self.assertGreater(kept_hb['successor_credit'],lost_hb['successor_credit'])
        self.assertLess(kept_hb['exposure'],lost_hb['exposure'])

    def test_patient_cautious_gm_prices_future_options_more(self):
        sent=self.pick()
        self.t.gm.patience=1.;self.t.gm.risk=0.;self.t.gm.aggression=0.;self.t.gm.job_security=1.
        patient=TP.assess(self.L,self.t,[sent])
        self.t.gm.patience=0.;self.t.gm.risk=1.;self.t.gm.aggression=1.;self.t.gm.job_security=.2
        urgent=TP.assess(self.L,self.t,[sent])
        self.assertGreater(patient['cost'],urgent['cost'])
        self.assertGreater(patient['after'][3]['weight'],urgent['after'][3]['weight'])

    def test_successive_equal_pick_sales_become_more_expensive(self):
        one=self.pick(23,origin='one');two=self.pick(23,origin='two');three=self.pick(23,origin='three')
        first=TP.assess(self.L,self.t,[one])
        self.t.picks.remove(one)
        second=TP.assess(self.L,self.t,[two])
        self.t.picks.remove(two)
        third=TP.assess(self.L,self.t,[three])
        self.assertLess(first['cost'],second['cost'])
        self.assertLess(second['cost'],third['cost'])

    def test_zero_pick_stock_and_no_pick_spending_do_not_ban_acquisition(self):
        p=self.incoming()
        read=TP.assess(self.L,self.t,(),[p.pid])
        self.assertEqual(read['cost'],0.)
        self.assertTrue(all(r['capital']==0 for r in read['after']))
        # Even spending the last pick is finite: a sufficiently worthwhile
        # package may overcome the preference through the caller's margin.
        sent=self.pick();cost=TP.assess(self.L,self.t,[sent],[p.pid])['cost']
        self.assertGreater(cost,0.)
        self.assertLess(cost,200.)

    def test_incoming_picks_replenish_same_inventory_symmetrically(self):
        sent=self.pick()
        received=copy.deepcopy(sent);received.original='DEN';received.owner='DEN'
        self.assertEqual(TP.assess(self.L,self.t,[sent],[received])['cost'],0.)
        spent=TP.assess(self.L,self.t,[sent])
        self.assertGreater(spent['cost'],0.)

    def test_early_picks_and_late_lottery_picks_are_not_equivalent_counts(self):
        sent=self.pick()
        late=[self.pick(208,origin=f'late-{i}') for i in range(2)]
        lottery=TP.assess(self.L,self.t,[sent])
        for p in late:p.round=1;p.selection=16
        early=TP.assess(self.L,self.t,[sent])
        self.assertLess(early['cost'],lottery['cost'])

    def test_existing_cash_is_not_an_invented_quality_replacement(self):
        sent=self.pick();before=TP.assess(self.L,self.t,[sent])
        self.t.cap.rollover+=200.
        self.assertEqual(TP.assess(self.L,self.t,[sent]),before)

    def test_spent_foreign_stale_and_duplicate_entries_are_not_extra_capital(self):
        sent=self.pick();base=TP.assess(self.L,self.t,[sent])
        self.t.picks.append(copy.deepcopy(sent))
        spent=self.pick(48);spent.used_on='drafted'
        foreign=self.pick(80);foreign.owner='DEN'
        stale=self.pick(112);stale.year-=2
        self.assertEqual(TP.assess(self.L,self.t,[sent]),base)

    def test_preroll_padding_and_pick_service_year_have_same_postroll_read(self):
        sent=self.pick()
        self.L.year-=1;self.L.set_phase('offseason');self.L.season_closed_year=self.L.year
        for p in self.t.roster:
            p.contract.base.insert(0,0.);p.contract.rb.insert(0,0.)
            p.contract.bonus_schedule.insert(0,0.);p.contract.years+=1;p.contract.start_offset=1
        before=TP.assess(self.L,self.t,[sent])
        for p in self.t.roster:p.contract.advance()
        self.L.year+=1;self.L.set_phase('free_agency')
        after=TP.assess(self.L,self.t,[sent])
        self.assertEqual(before,after)

    def test_immobility_reload_and_hidden_ceiling_independence(self):
        sent=self.pick();saved=self.L.save();first=TP.assess(self.L,self.t,[sent])
        self.assertEqual(self.L.save(),saved)
        loaded=League.load(saved)
        pk=next(p for p in loaded.teams[self.t.abbr].picks if p.original==sent.original)
        # Canonicalize the synthetic fixture's legacy age/attribute fields
        # once; migration is not an assessment side effect.
        canonical=TP.assess(loaded,loaded.teams[self.t.abbr],[pk])
        reloaded=League.load(loaded.save())
        again=next(p for p in reloaded.teams[self.t.abbr].picks if p.original==sent.original)
        self.assertEqual(TP.assess(reloaded,reloaded.teams[self.t.abbr],[again]),canonical)
        for p in self.t.roster:p.potential=99;p.longevity=10.
        self.assertEqual(TP.assess(self.L,self.t,[sent]),first)

    def test_caller_cache_reuses_roster_work_but_reprices_changed_pick_stock(self):
        one=self.pick();two=self.pick(48);cache={}
        original=TP.RN.assess
        with patch.object(TP.RN,'assess',wraps=original) as read:
            first=TP.assess(self.L,self.t,[one],cache=cache)
            self.assertEqual(read.call_count,1)
            same=TP.assess(self.L,self.t,[one],cache=cache)
            self.assertEqual(first,same);self.assertEqual(read.call_count,1)
            self.t.picks.remove(two)
            depleted=TP.assess(self.L,self.t,[one],cache=cache)
            self.assertGreater(depleted['cost'],first['cost'])
            self.assertEqual(read.call_count,1)
            self.t.roster[0].contract=Contract(4,[1.]*4)
            TP.assess(self.L,self.t,[one],cache=cache)
            self.assertEqual(read.call_count,2)

    def test_consumed_draft_target_is_not_both_pick_and_public_rookie(self):
        sent=self.pick(48)
        target=DraftPick(self.L.year-1,1,'DEN','DEN',selection=23)
        template=self.t.by_pos('QB')[0]
        observed=NS(pid='observed',pos='QB',ratings=dict(template.ratings),ovr=template.ovr,
                    out_until=None,retired=False)
        read=TP.assess(self.L,self.t,[sent],[target],prospect=observed,consumed_pick=target)
        self.assertTrue(all(not r['picks'] for r in read['after']))
        self.assertTrue(any(p['pid']=='observed' for f in read['after'][0]['families']
                            for p in f['incumbents']+f['successors']))

    def test_raw_unscouted_prospect_cannot_supply_hidden_roster_cover(self):
        sent=self.pick();p=self.incoming('QB',99,4,22)
        baseline=TP.assess(self.L,self.t,[sent])
        hidden=TP.assess(self.L,self.t,[sent],prospect=p)
        self.assertEqual(hidden,baseline)


if __name__=='__main__':unittest.main()

"""A staffing decision must survive the vacancy-filling part of the carousel."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import staff as ST
from test_staff_contracts import coach


class Rng:
    def __init__(self, draw):
        self.draw = draw
        self.rng = np.random.default_rng(42)
    def random(self):
        return self.draw
    def __getattr__(self, name):
        return getattr(self.rng, name)


def fixture(expired=True):
    incumbent = coach('Incumbent', rating=90, years=0 if expired else 3)
    incumbent.traits = dict(loyalty=50, financial_priority=50)
    replacement = coach('Available replacement', team=None, rating=62, years=0)
    team = NS(abbr='A', staff={r: coach(r,r,years=3) for r in ST.ROLES},
              gm=NS(name='Head coach',salary=8,prestige=50), owner_spend=.5,
              record=[8,9,0])
    team.staff['oc']=incumbent
    L = NS(year=2029, teams={'A':team}, staff_pool=[replacement], user_team=None,
           events=[])
    L.log=lambda kind, **kw: L.events.append(dict(kind=kind,**kw))
    return L, incumbent, replacement


def run(L, draw):
    # Candidate entrants are unrelated to the decision under test.
    with patch('coaching_pool.close_pending_hires'), patch.object(ST,'finalize_poaches'), \
         patch.object(ST,'POOL_SIZE',{r:0 for r in ST.ROLES}):
        return ST.carousel(L,Rng(draw))


class StaffCarouselDecisions(unittest.TestCase):
    def test_affordable_willing_coach_is_retained_at_actual_ask(self):
        L, old, replacement=fixture()
        run(L,.5)
        self.assertIs(L.teams['A'].staff['oc'],old)
        self.assertEqual(old.salary,ST.ask(old))
        self.assertGreater(old.years,0)
        self.assertFalse(any(x['kind']=='staff_out' for x in L.events))
        self.assertLessEqual(ST.payroll(L.teams['A']),ST.budget(L.teams['A']))

    def test_refusal_is_not_undone_by_immediately_rehiring_best_candidate(self):
        L, old, replacement=fixture()
        old.disgruntled=2028
        run(L,.5)
        self.assertIs(L.teams['A'].staff['oc'],replacement)
        self.assertEqual(old.team,None)
        departure=next(x for x in L.events if x['kind']=='staff_out')
        self.assertEqual(departure['why'],'contract up, walked')

    def test_bottom_eight_firing_cannot_be_undone_during_same_carousel(self):
        L, old, replacement=fixture(expired=False)
        old.unit_ranks=[30,29]
        old.unit_reviews=[dict(year=2028,rank=30),dict(year=2029,rank=29)]
        run(L,.1)
        self.assertIs(L.teams['A'].staff['oc'],replacement)
        self.assertEqual(next(x for x in L.events if x['kind']=='staff_out')['why'],
                         'unit bottom-eight two years running')

    def test_firing_remains_discretionary_and_short_stint_is_protected(self):
        for short,draw in [(False,.9),(True,.1)]:
            L,old,_=fixture(expired=False)
            old.unit_ranks=[30,29]
            old.unit_reviews=[dict(year=2028,rank=30),dict(year=2029,rank=None if short else 29)]
            run(L,draw)
            self.assertIs(L.teams['A'].staff['oc'],old)

    def test_empty_market_uses_new_entrant_instead_of_reversing_refusal(self):
        L,old,_=fixture()
        L.staff_pool=[];old.disgruntled=2028
        run(L,.5)
        self.assertIsNot(L.teams['A'].staff['oc'],old)
        self.assertEqual(L.teams['A'].staff['oc'].team,'A')

    def test_willing_but_unaffordable_coach_is_priced_out(self):
        L,old,replacement=fixture()
        L.teams['A'].gm.salary=15
        self.assertGreater(ST.ask(old),ST.room(L.teams['A'],without='oc'))
        run(L,.5)
        self.assertIs(L.teams['A'].staff['oc'],replacement)
        self.assertEqual(next(x for x in L.events if x['kind']=='staff_out')['why'],
                         'contract up, priced out')
        self.assertLessEqual(ST.payroll(L.teams['A']),ST.budget(L.teams['A']))

    def test_renewal_is_one_willingness_draw_and_truthful_reason(self):
        L,old,replacement=fixture()
        rng=Rng(.5)
        # The first draw declines. A second draw used to invent a budget refusal.
        with patch.object(rng,'random',side_effect=[.99,.1]) as draws, \
             patch('coaching_pool.close_pending_hires'),patch.object(ST,'finalize_poaches'), \
             patch.object(ST,'make',side_effect=lambda rng,role,**kw: coach('Entrant',role,team=None,years=0)), \
             patch.object(ST,'POOL_SIZE',{r:0 for r in ST.ROLES}):
            ST.carousel(L,rng)
        self.assertEqual(draws.call_count,1)
        self.assertEqual(next(x for x in L.events if x['kind']=='staff_out')['why'],
                         'contract up, walked')

    def test_loyalty_can_change_renewal_and_rival_can_hire_departure(self):
        for loyalty,retained in [(0,False),(100,True)]:
            L,old,replacement=fixture()
            old.traits['loyalty']=loyalty
            run(L,.7)
            self.assertEqual(L.teams['A'].staff['oc'] is old,retained)
        L,old,replacement=fixture()
        old.disgruntled=2028
        rival,_,_=fixture()
        t=rival.teams['A'];t.abbr='B';t.staff['oc']=None
        for c in t.staff.values():
            if c: c.years=3;c.team='B'
        L.teams['B']=t
        run(L,.5)
        self.assertIs(L.teams['A'].staff['oc'],replacement)
        self.assertIs(L.teams['B'].staff['oc'],old)
        self.assertEqual(old.team,'B')


if __name__=='__main__':unittest.main()

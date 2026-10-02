"""Roster decisions, including the 2028 HOU/PIT/BAL overstock patterns."""
import copy
import unittest
from cap_engine import Contract
from league import Player
import draft_plan as DP
import targets as TG
from test_draft_planning import fixture, set_grade


def room(L, team, pos, rows):
    team.roster = [p for p in team.roster if p.pos != pos]
    for i, (rating, age, years) in enumerate(rows):
        p = Player(f'room-{pos}-{i}', f'{pos} incumbent {i}', pos, age,
                   {k: rating for k in TG.DEPTH_WEIGHTS[pos]}, team=team.abbr,
                   contract=Contract(years, [2]*years))
        team.roster.append(p); L.players[p.pid] = p


def add_pick(L, team, pos, rating=76, ceiling=(80, 90), selection=160):
    p = Player(f'pick-{selection}', f'Pick {selection}', pos, 23,
               {k: rating for k in TG.DEPTH_WEIGHTS[pos]}, team=team.abbr,
               contract=Contract(4, [1]*4), potential_range=ceiling)
    p.draft_overall = selection
    team.roster.append(p); L.players[p.pid] = p
    return p


class DraftRedundancyTests(unittest.TestCase):
    def penalty(self, L, p, grade=77, gain=0):
        return DP.redundancy_penalty(DP.assess(L, 'MIN'), p, grade, gain)

    def test_houston_third_fourth_fifth_back_get_increasing_cost(self):
        L,t=fixture(); room(L,t,'HB',[(86.2,27.3,3),(83.7,30.9,3)])
        p=L.player('rookie-HB0')
        a=self.penalty(L,p)
        add_pick(L,t,'HB',78.5,selection=68)
        b=self.penalty(L,p)
        add_pick(L,t,'HB',73.9,selection=161)
        c=self.penalty(L,p)
        self.assertGreater(a,0); self.assertGreater(b,a); self.assertGreater(c,b)

    def test_pittsburgh_young_expiring_third_back_still_counts_some(self):
        L,t=fixture(); room(L,t,'HB',[(85.8,29.9,4),(84.7,29.5,2),(81.5,23.8,1)])
        p=L.player('rookie-HB0'); before=self.penalty(L,p)
        self.assertGreater(before,0)
        add_pick(L,t,'HB',75.3,selection=85)
        self.assertGreater(self.penalty(L,p),before)

    def test_baltimore_exceptional_first_dt_allowed_later_depth_discouraged(self):
        L,t=fixture(); room(L,t,'DT',[(79.5,24,3),(68.2,30.5,1),(74.7,25.5,2),
            (80.3,33.9,1),(80.3,28.5,2),(80.8,33.8,1),(79.6,24.9,1),(79.6,26.7,1)])
        p=L.player('rookie-DT0')
        self.assertEqual(self.penalty(L,p,grade=87,gain=5.75),0)
        add_pick(L,t,'DT',80,selection=14)
        second=self.penalty(L,p,grade=81,gain=.48)
        add_pick(L,t,'DT',77,selection=78)
        third=self.penalty(L,p,grade=77,gain=0)
        self.assertGreater(second,0); self.assertGreater(third,second)

    def test_two_missing_dt_jobs_allow_legitimate_double_dip(self):
        L,t=fixture(); room(L,t,'DT',[]); p=L.player('rookie-DT0')
        self.assertEqual(self.penalty(L,p),0)
        add_pick(L,t,'DT',79,selection=20)
        self.assertEqual(self.penalty(L,p),0)

    def test_expiring_veterans_leave_more_room_than_controlled_core(self):
        L,t=fixture(); p=L.player('rookie-HB0')
        room(L,t,'HB',[(84,27,3),(80,24,3),(78,25,3)])
        controlled=self.penalty(L,p)
        for q in t.roster:
            if q.pos=='HB': q.contract=Contract(1,[2])
        self.assertLess(self.penalty(L,p),controlled)

    def test_weak_depth_does_not_block_a_replacement(self):
        L,t=fixture(); room(L,t,'HB',[(60,24,3)]*4); p=L.player('rookie-HB0')
        self.assertEqual(self.penalty(L,p,grade=76),0)

    def test_package_roles_allow_more_tight_ends(self):
        L,t=fixture(); room(L,t,'TE',[(82,25,4),(79,24,4),(78,25,4)])
        p=L.player('rookie-TE0'); t.gm.off_personnel='11'
        ordinary=self.penalty(L,p,grade=78)
        t.gm.off_personnel='13'
        self.assertLess(self.penalty(L,p,grade=78),ordinary)

    def test_exceptional_scouted_upgrade_is_not_a_hard_position_ban(self):
        L,t=fixture(); room(L,t,'HB',[(80,25,4)]*4); p=L.player('rookie-HB0')
        ordinary=self.penalty(L,p,grade=78)
        self.assertGreater(ordinary,0)
        self.assertEqual(self.penalty(L,p,grade=96),0)
        self.assertEqual(self.penalty(L,p,grade=78,gain=8),0)

    def test_hidden_prospect_ceiling_does_not_change_penalty(self):
        L,t=fixture(); p=L.player('rookie-HB0'); before=self.penalty(L,p)
        p.potential=99; p.potential_range=(99,99); set_grade(p,99)
        self.assertEqual(self.penalty(L,p),before)

    def test_late_picks_resolve_succession_and_contract_exposure(self):
        L,t=fixture(); room(L,t,'QB',[(94,35,3),(58,25,1)])
        starter=next(p for p in t.roster if p.pos=='QB')
        starter.contract=Contract(3,[50]*3)
        for pos in ('WR','CB','LT'): L.player(pos+'0').contract=Contract(3,[100]*3)
        before=DP.assess(L,'MIN')['positions']['QB']
        self.assertGreater(before['contract'],0); self.assertGreater(before['succession'],0)
        add_pick(L,t,'QB',79,(84,90),selection=180)
        after=DP.assess(L,'MIN')['positions']['QB']
        self.assertLess(after['contract'],before['contract'])
        self.assertLess(after['succession'],before['succession'])

    def test_ir_returnees_count_but_expired_players_do_not(self):
        L,t=fixture(); room(L,t,'HB',[(84,26,3)]*3); p=L.player('rookie-HB0')
        before=self.penalty(L,p)
        incumbent=next(q for q in t.roster if q.pos=='HB')
        incumbent.out_until=99; t.ir=[incumbent]
        self.assertEqual(self.penalty(L,p),before)
        incumbent.contract=None
        self.assertLess(self.penalty(L,p),before)

    def test_assessment_and_penalty_do_not_change_save(self):
        L,t=fixture(); before=copy.deepcopy(L.save())
        self.penalty(L,L.player('rookie-HB0'))
        self.assertEqual(L.save(),before)


if __name__=='__main__': unittest.main()

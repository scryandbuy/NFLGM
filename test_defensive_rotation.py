"""Rotation follows condition, real depth quality and game situation for every team."""
import unittest
from types import SimpleNamespace as NS
import numpy as np
import defense_roles as DR
import health as H
import game
import rosters
from test_defensive_assignment import depth


def player(pid, grade=80, stamina=85, pos='REDG'):
    return dict(pid=pid, pos=pos, stamina_rating=stamina,
                finesse_moves_rating=grade, power_moves_rating=grade,
                accel_rating=grade, speed_rating=grade, block_shed_rating=grade)


class DefensiveRotationTests(unittest.TestCase):
    def choose(self, starter, backup, condition=100, context=None, seed=1):
        cond=H.Condition(); cond.cond={starter['pid']:condition,backup['pid']:100}
        state=NS(cond=cond,rotation_context=context or {})
        row=dict(player=starter,role='RE',group='dl')
        return DR.rotation_choice(row,[backup],state,np.random.default_rng(seed))

    def test_fresh_starter_is_not_randomly_removed(self):
        a,b=player('starter'),player('reserve',75)
        for seed in range(100): self.assertIs(self.choose(a,b,seed=seed),a)

    def test_real_quality_gap_changes_rest_tolerance(self):
        backup=player('reserve',75)
        elite,peer=player('elite',95),player('peer',77)
        # Quality matters near the breather decision, not at deep fatigue
        # where both players should rest regardless of reputation.
        elite_snaps=sum(self.choose(elite,backup,88,seed=i) is elite for i in range(200))
        peer_snaps=sum(self.choose(peer,backup,88,seed=i) is peer for i in range(200))
        self.assertGreater(elite_snaps,peer_snaps+40)

    def test_passing_down_priority_is_conditional(self):
        a,b=player('starter',95),player('reserve',75)
        count=lambda ctx: sum(self.choose(a,b,88,ctx,i) is a for i in range(200))
        neutral=count({'down':1,'to_go':10,'score_diff':0})
        important=count({'down':3,'to_go':8,'score_diff':0})
        blowout=count({'down':3,'to_go':8,'score_diff':24})
        short=count({'down':3,'to_go':1,'score_diff':0})
        self.assertGreater(important,neutral+10)
        self.assertEqual(blowout,neutral)
        self.assertEqual(short,neutral)

    def test_importance_does_not_force_exhausted_star_to_play(self):
        a,b=player('starter',99),player('reserve',60)
        rests=sum(self.choose(a,b,25,{'down':4,'to_go':10,'score_diff':0},i) is b for i in range(200))
        self.assertGreater(rests,180)

    def test_all_need_rest_uses_freshest_available(self):
        a,b,c=player('starter'),player('second'),player('third')
        condition={'starter':15,'second':40,'third':55}
        state=NS(cond=NS(get=lambda pid:condition[pid],needs_rest=lambda *args:True))
        selected=DR.rotation_choice(dict(player=a,role='RE'),[b,c],state,np.random.default_rng(1))
        self.assertIs(selected,c)

    def test_pinned_starter_stays_selected_while_fresh(self):
        a,b=player('pinned',65),player('better_reserve',95)
        for seed in range(50): self.assertIs(self.choose(a,b,seed=seed),a)

    def test_without_health_state_does_not_invent_fatigue(self):
        a,b=player('starter'),player('reserve')
        for seed in range(50):
            self.assertIs(DR.rotation_choice(dict(player=a,role='RE'),[b],None,np.random.default_rng(seed)),a)

    def test_high_stamina_can_sustain_more_snaps(self):
        def share(stamina):
            total=0
            for seed in range(30):
                a,b=player('starter',92,stamina),player('reserve',72,80)
                state=NS(cond=H.Condition()); rng=np.random.default_rng(seed)
                for snap in range(72):
                    chosen=DR.rotation_choice(dict(player=a,role='RE'),[b],state,rng)
                    total+=chosen is a
                    for p in (a,b):
                        if p is chosen: state.cond.play(p['pid'],p['pos'],p['stamina_rating'])
                        else: state.cond.rest(p['pid'])
                    if snap%6==5:
                        for _ in range(3):
                            for p in (a,b): state.cond.rest(p['pid'])
            return total/(30*72)
        self.assertGreater(share(95),share(55)+.08)
        self.assertLess(share(95),.98)

    def test_all_packages_keep_eleven_and_honor_injuries_through_rotation(self):
        for front in ('4-3','3-4'):
            roster=rosters._assemble(depth(),front=front)
            state=game.TeamState(roster); state.out={'REDG0'}
            rng=np.random.default_rng(5)
            for i in range(80):
                unit=DR.field(roster,('base','nickel','dime','heavy')[i%4],rng=rng,state=state)
                ids=[row['player']['pid'] for row in unit['defensive_assignments']]
                self.assertEqual(len(set(ids)),11)
                self.assertNotIn('REDG0',ids)
            self.assertGreater(state.snaps.get('REDG1',0),0)


if __name__=='__main__': unittest.main()

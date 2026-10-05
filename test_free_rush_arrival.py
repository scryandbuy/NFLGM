"""Free paths are races, not a fixed time or a roster-order sack award."""
import copy
import unittest
from unittest.mock import patch
import numpy as np
import plays as P
import rush_matchup as R
import blocking_evaluation as B


def player(pid, speed=80):
    return dict(pid=pid, pos='MIKE', speed_rating=speed, accel_rating=speed)


class FreeRushArrival(unittest.TestCase):
    def resolve(self, rows, blockers=(), seed=1):
        assignments = [dict(player=p, alignment=a, group='lb', role=p['pos']) for p,a in rows]
        return P.resolve_protection(blockers, [p for p,a in rows], np.random.default_rng(seed),
                                    assignments=assignments, _defer_award=True)

    def test_path_and_live_movement_determine_arrival_not_position_name(self):
        p = player('r')
        self.assertLess(R.free_arrival_mean(p, 'offball_middle'), R.free_arrival_mean(p, 'slot'))
        self.assertLess(R.free_arrival_mean(player('r',99), 'slot'), R.free_arrival_mean(player('r',40), 'slot'))
        self.assertEqual(R.free_arrival_mean(dict(p,pos='CB'), 'slot'), R.free_arrival_mean(p, 'slot'))
        self.assertGreater(R.free_arrival_mean(player('r',65), 'slot'), R.free_arrival_mean(p, 'slot'))

    def test_symmetric_alignment_race_preserves_both_winners_and_permutation(self):
        rows = [(player('left'),'offball_left'), (player('right'),'offball_right')]
        winners = []
        for seed in range(400):
            a=self.resolve(rows,seed=seed);b=self.resolve(rows[::-1],seed=seed)
            self.assertEqual(a,b)
            winners.append(a['beaten_by'])
            self.assertTrue(all(m>0 for m in a['pb_model']['means']))
        self.assertGreater(winners.count('left'),140)
        self.assertGreater(winners.count('right'),140)

    def test_faster_same_path_more_often_first_without_guaranteeing_every_race(self):
        rows=[(player('fast',99),'offball_left'),(player('slow',40),'offball_right')]
        winners=[self.resolve(rows,seed=s)['beaten_by'] for s in range(600)]
        self.assertGreater(winners.count('fast'),winners.count('slow'))
        self.assertGreater(winners.count('slow'),50)

    def test_slot_can_finish_before_middle_while_shorter_path_keeps_advantage(self):
        rows=[(player('middle'),'offball_middle'),(player('slot'),'slot')]
        winners=[self.resolve(rows,seed=s)['beaten_by'] for s in range(600)]
        self.assertGreater(winners.count('middle'),winners.count('slot'))
        self.assertGreater(winners.count('slot'),100)

    def test_blocked_rusher_can_beat_free_runner(self):
        edge=dict(player('edge',99),pos='REDG',power_moves_rating=99,finesse_moves_rating=99,
                  strength_rating=99,agility_rating=99,block_shed_rating=99)
        block=dict(pid='LT',pos='LT',pass_block_rating=35,pass_block_power_rating=35,
                   pass_block_finesse_rating=35,agility_rating=35,strength_rating=35)
        rows=[(edge,'right_edge'),(player('free',40),'slot')]
        outcomes=[self.resolve(rows,[block],s) for s in range(500)]
        winners={x['beaten_by'] for x in outcomes}
        self.assertEqual(winners,{'edge','free'})
        for out in outcomes:
            self.assertEqual(out['beaten'], 'LT' if out['beaten_by']=='edge' else None)

    def test_true_equal_times_do_not_always_award_first_id(self):
        rows=[(player('a'),'offball_left'),(player('b'),'offball_right')]
        class Tied:
            def __init__(self,seed):self.rng=np.random.default_rng(seed)
            def random(self):return self.rng.random()
            def lognormal(self,*args):return 1.
            def integers(self,*args):return self.rng.integers(*args)
        wins=[]
        for seed in range(100):
            assignments=[dict(player=p,alignment=a) for p,a in rows]
            wins.append(P.resolve_protection([], [p for p,a in rows],Tied(seed),
                         assignments=assignments,_defer_award=True)['beaten_by'])
        self.assertGreater(wins.count('a'),25);self.assertGreater(wins.count('b'),25)

    def test_expected_protection_loss_integrates_free_race_and_hot_answer(self):
        # Reference block is unusually difficult so it can beat the free runner.
        model=dict(means=[1.8,1.55],free=[1],evaluations=[('LT',0,1.8,True)],
                   qb_scale=1.,finish_scales=[1.,1.])
        cold=B.protection_evidence(model,2.5,sack_k=P.SACK_K,pressure_window=2.72)[0]
        hot=B.protection_evidence(model,2.5,sack_k=P.SACK_K,hot=True,pressure_window=2.72)[0]
        samples=np.random.default_rng(44).lognormal(0.,B.RUSH_SIGMA,(60000,2))*[1.8,1.55]
        first=samples.argmin(axis=1);time=np.round(samples.min(axis=1),2)
        ps=np.clip(P.SACK_K*np.exp(-2.4*time),0,.85)
        expected=float(np.mean(ps*(first==0)))
        self.assertAlmostEqual(cold[3],expected,delta=.004)
        self.assertAlmostEqual(hot[3],cold[3]*.35,places=10)
        self.assertGreater(cold[3],0.01)
        self.assertEqual(cold[1],hot[1])


if __name__=='__main__':unittest.main()

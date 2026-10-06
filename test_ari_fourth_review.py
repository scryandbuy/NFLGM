"""Useful goal-line kicks retain coach judgment; late leader can still gamble."""
import unittest
import game

class Draw:
    def __init__(self, value): self.value = value
    def random(self): return self.value

def go_rate(spot=5, distance=5, margin=-9, seconds=734, aggression=.5):
    # Deterministic quantiles measure decision probability without seed noise.
    return sum(game.fourth_down_decision(spot, distance, margin, seconds,
        Draw((i+.5)/200), aggression=aggression) == 'go' for i in range(200))/200

class FourthReview(unittest.TestCase):
    def test_useful_kick_restores_coach_choice(self):
        rates = [go_rate(aggression=a) for a in (.1,.5,.9)]
        self.assertTrue(all(0 < r < .85 for r in rates), rates)
        self.assertLess(rates[0], rates[1])
        self.assertLess(rates[1], rates[2])

    def test_other_score_reducing_kicks_also_keep_choice(self):
        for margin in (-10,-11,-17,-18,-19):
            self.assertLess(go_rate(margin=margin), .85)

    def test_nonbridging_kick_retains_td_urgency(self):
        self.assertGreaterEqual(go_rate(margin=-16), .85)

    def test_final_play_needing_td_still_goes(self):
        self.assertEqual(go_rate(seconds=5), 1.)

    def test_short_distance_still_matters(self):
        self.assertGreater(go_rate(distance=1), go_rate(distance=5))

    def test_late_leader_usually_kicks_but_can_gamble(self):
        rates = [go_rate(45,4,9,175,a) for a in (.1,.5,.9)]
        self.assertTrue(all(0 < r < .25 for r in rates), rates)
        self.assertLess(rates[0], rates[-1])

if __name__ == '__main__': unittest.main()

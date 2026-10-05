"""Individual rush contests; public attributes and on-field assignments only."""
import math

BASE = 3.591
SENSITIVITY = .90
REFERENCE_GAP = .05
HELP = .13


def arrival_mean(attack, block, base=BASE):
    return base * math.exp(-SENSITIVITY * (attack - block - REFERENCE_GAP))


def help_effect(helper, block_grade, attack, alignment, roll, layer=0, strength=HELP):
    # A back crossing the pocket has a harder job than an adjacent lineman.
    reach = .08 if helper.get('pos') in ('HB', 'FB') and 'edge' in alignment else 0.
    awareness = float(helper.get('awareness_rating', 70)) / 100.
    chance = max(.20, min(.90, .82 + .90 * (block_grade - attack)
                           + .25 * (awareness - .75) - reach))
    return strength * max(0., min(1., block_grade)) / (layer + 1) if roll < chance else 0.


def finish_scale(player):
    # Getting through the block and finishing against a moving QB are distinct.
    ability = sum(float(player.get(k, 70)) * w for k, w in (
        ('pursuit_rating', .40), ('tackle_rating', .35), ('speed_rating', .25))) / 100.
    return max(.65, min(1.35, 1. + 1.5 * (ability - .80)))

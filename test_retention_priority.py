"""Retain franchise value before filling cheap-to-replace empty slots."""
import unittest
from unittest.mock import patch

import numpy as np
import extensions as EXT
import retention_plan as RP
from test_draft_planning import fixture, set_grade


# Recorded CIN 2028 audit inputs, not a serialized pre-negotiation replay.
AUDIT = {
    'QB': (84.568, 1., 16.2266),
    'RG': (79.084, 1., 24.4782),
    'RT': (79.380, 1., 23.8419),
    'P': (75.332, 1., 42.),
}
ASKS = {'QB0': 73.04, 'RG0': 18.82, 'RT0': 15.78, 'P0': 3.05}


def old_priority(pos, grade, share, loss):
    return round(3.*loss + 12.*share + (grade-75.)*.7, 4)


def constrained_club(cap=140.):
    """Controlled same-state comparison with real package/cap/agent code."""
    L, t = fixture()
    L.set_phase('offseason'); t.cap.cap = cap; t.picks = []
    for pid, grade in [('QB0', 94.25), ('RG0', 86.48), ('RT0', 80.62), ('P0', 83.83)]:
        p = L.player(pid); set_grade(p, grade)
        p.contract = None; p.age = 30.8
    for pid in ('RG1', 'RT1'):
        set_grade(L.player(pid), 55.)
    t.sync_cap()
    return L, t


def quote(league, player, rng, pool=None):
    # Freeze prices to isolate review order. Actual negotiation, financial
    # reserves, contract shapes and cap enforcement remain enabled.
    apy = ASKS.get(player.pid, 10.)
    return dict(ask=apy, offer=apy, years=3, discount=.07)


class RetentionPriorityTests(unittest.TestCase):
    def test_recorded_cincinnati_order(self):
        old = sorted(AUDIT, key=lambda pos: -old_priority(pos, *AUDIT[pos]))
        new = sorted(AUDIT, key=lambda pos: -RP.retention_priority(pos, *AUDIT[pos]))
        self.assertEqual(old, ['P', 'RG', 'RT', 'QB'])
        self.assertEqual(new, ['QB', 'RT', 'RG', 'P'])

    def test_empty_specialist_slot_cannot_overwhelm_franchise_priority(self):
        quarterback = RP.retention_priority('QB', *AUDIT['QB'])
        for pos in ('K', 'P', 'LS'):
            self.assertLess(RP.retention_priority(pos, 1000., 10., 1e9), quarterback)
        for pos in ('QB', 'RG', 'LT', 'WR', 'CB', 'K', 'P', 'LS'):
            for grade, share, loss in ((-100., -1., -1.), (75., .5, 5.), (1000., 10., 1e9)):
                score = RP.retention_priority(pos, grade, share, loss)
                self.assertGreaterEqual(score, 0.)
                self.assertLessEqual(score, 100.)

    def test_qb_label_does_not_automatically_beat_better_starters(self):
        edge = RP.retention_priority('LEDG', 87.5, 1., 15.)
        self.assertLess(RP.retention_priority('QB', 70., 0., 3.), edge)
        self.assertLess(RP.retention_priority('QB', 65., 1., 3.), edge)
        self.assertGreater(RP.retention_priority('RG', 87.5, 1., 10.),
                           RP.retention_priority('RG', 75., 1., 10.))

    def test_same_club_budget_gives_qb_first_real_opportunity(self):
        outcomes = []
        for priority in (old_priority, RP.retention_priority):
            L, t = constrained_club()
            with patch.object(RP, 'retention_priority', side_effect=priority), \
                 patch.object(EXT, 'terms', side_effect=quote):
                self.assertTrue(RP.assess(L, t, L.player('QB0'))['affordable'])
                EXT.ai_round(L, np.random.default_rng(313))
            signed = [e['pid'] for e in L.transactions if e['kind'] == 'extension']
            outcomes.append(signed)
            self.assertGreaterEqual(t.cap_space, 0.)
        self.assertEqual(outcomes[0], ['P0', 'RG0', 'RT0'])
        self.assertEqual(outcomes[1][0], 'QB0')

    def test_unaffordable_qb_does_not_block_other_negotiations(self):
        L, t = constrained_club(cap=100.)
        with patch.object(EXT, 'terms', side_effect=quote):
            self.assertEqual(RP.candidates(L, t)[0][0].pid, 'QB0')
            self.assertFalse(RP.assess(L, t, L.player('QB0'))['affordable'])
            result = EXT.negotiate_ai(L, L.player('QB0'), ASKS['QB0'], 3,
                                      np.random.default_rng(313))
            self.assertEqual(result['result'], 'refused')
            self.assertEqual(result['attempts'], 0)
            EXT.ai_round(L, np.random.default_rng(313))
        self.assertIsNone(L.player('QB0').contract)
        self.assertIsNotNone(L.player('RG0').contract)
        self.assertGreaterEqual(t.cap_space, 0.)

    def test_priority_does_not_override_closed_agent(self):
        L, t = constrained_club()
        L.negotiations = [dict(pid='QB0', team=t.abbr, kind='extension', state='declined')]
        with patch.object(EXT, 'terms', side_effect=quote):
            EXT.ai_round(L, np.random.default_rng(313))
        self.assertIsNone(L.player('QB0').contract)
        self.assertIsNotNone(L.player('RG0').contract)
        self.assertGreaterEqual(t.cap_space, 0.)


if __name__ == '__main__':
    unittest.main()

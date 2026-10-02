import copy
import unittest

from cap_engine import Contract
import cutdown as CD
import game_availability as GA
import waivers as WV
import practice_squad as PS
import targets as TG
from league import Team
from test_draft_planning import set_grade
from test_roster_cap_recovery import RecoveryTests


class SpecialistAllocationTests(unittest.TestCase):
    def roster(self):
        L, t = RecoveryTests().roster()
        L.user_team = None
        L.week = 0
        return L, t

    def arrival(self, L, t, on_team=False):
        p = copy.deepcopy(t.by_pos('P')[0])
        p.pid = 'new-punter'; p.name = 'New Punter'; p.accrued = 1
        p.contract = Contract(1, [1]); p.out_until = None; p.xp_spent = {}
        set_grade(p, 95)
        p.team = t.abbr if on_team else None
        L.players[p.pid] = p
        if on_team:
            t.roster.append(p); t.sync_cap()
        else:
            L.free_agents.append(p.pid)
        return p

    def test_cutdown_frees_healthy_duplicate_using_normal_waivers(self):
        L, t = self.roster(); old = t.by_pos('P')[0]
        incoming = self.arrival(L, t, on_team=True)
        cuts = CD.trim_specialists(L)
        self.assertEqual([p.pid for _, p in cuts], [old.pid])
        self.assertEqual(t.by_pos('P'), [incoming])
        self.assertIn(old.pid, [e['pid'] for e in WV.pending(L)])
        self.assertEqual(CD.trim_specialists(L), [])

    def test_cutdown_preserves_injury_cover_and_user_roster(self):
        L, t = self.roster(); old = t.by_pos('P')[0]
        self.arrival(L, t, on_team=True); old.out_until = 3
        self.assertEqual(CD.trim_specialists(L), [])
        old.out_until = None; L.user_team = t.abbr
        self.assertEqual(CD.trim_specialists(L), [])

    def test_cutdown_does_not_release_protected_investment(self):
        L, t = self.roster(); old = t.by_pos('P')[0]
        old.contract = Contract(4, [2]*4, signing_bonus=16)
        self.arrival(L, t, on_team=True); t.sync_cap()
        self.assertEqual(CD.trim_specialists(L), [])

    def test_waiver_upgrade_replaces_punter_not_an_unrelated_player(self):
        L, t = self.roster(); old = t.by_pos('P')[0]
        p = self.arrival(L, t); before = {q.pid for q in t.active()}
        entry = dict(pid=p.pid, from_team='OTHER')
        self.assertTrue(WV.make_room(L, t.abbr, p, entry))
        WV.award(L, entry, t.abbr)
        self.assertEqual({q.pid for q in t.active()}, before - {old.pid} | {p.pid})
        self.assertEqual(t.by_pos('P'), [p])

    def test_locked_incumbent_does_not_create_second_healthy_punter(self):
        L, t = self.roster(); old = t.by_pos('P')[0]
        old.xp_spent['_poach_lock'] = 3
        p = self.arrival(L, t); before = {q.pid for q in t.active()}
        self.assertFalse(WV.make_room(L, t.abbr, p, dict(pid=p.pid, from_team='OTHER')))
        self.assertEqual(before, {q.pid for q in t.active()})

    def test_specialist_claim_does_not_churn_this_weeks_acquisition(self):
        L, t = self.roster(); old = t.by_pos('P')[0]
        L.log('sign', pid=old.pid, team=t.abbr)
        p = self.arrival(L, t); before = {q.pid for q in t.active()}
        self.assertFalse(WV.make_room(L, t.abbr, p, dict(pid=p.pid, from_team='OTHER')))
        self.assertEqual(before, {q.pid for q in t.active()})

    def test_full_offseason_roster_repairs_native_depth_without_churn(self):
        L, t = self.roster()
        L.set_phase('free_agency'); t.phase = 'season'
        tight_ends = list(t.by_pos('TE'))
        for p in tight_ends:
            t.roster.remove(p); p.team = None; L.free_agents.append(p.pid)
            replacement = copy.deepcopy(t.by_pos('WR')[0])
            replacement.pid = 'surplus-' + p.pid
            replacement.contract = Contract(1, [1]); replacement.xp_spent = {}
            L.players[replacement.pid] = replacement; t.roster.append(replacement)
        t.sync_cap()
        self.assertEqual(len(t.active()), 53)
        self.assertTrue(any(p['depth'].get('TE') for p in CD.violations(L)))
        self.assertGreater(CD.repair_depth(L), 0)
        self.assertEqual(PS.essential_depth(t)['shortages'], {})
        self.assertEqual(len(t.active()), 55)
        GA.settle_roster(L,t,L.week)
        self.assertEqual(len(t.active()), 53)
        self.assertGreaterEqual(t.cap_space, -.0005)
        acquired = {p.pid for p in t.by_pos('TE')}
        self.assertEqual(CD.repair_depth(L), 0)
        self.assertEqual({p.pid for p in t.by_pos('TE')}, acquired)

    def test_season_opening_gate_counts_long_absences_as_depth_shortages(self):
        L, t = self.roster()
        t.by_pos('QB')[0].out_until = 6
        self.assertEqual(PS.essential_depth(t)['shortages'], {})
        self.assertEqual(CD.violations(L)[0]['depth']['QB'], 1)

    def test_unaffordable_free_agent_does_not_hide_affordable_squad_backup(self):
        L, t = self.roster(); L.user_team = 'DEN'
        old = t.by_pos('QB')[-1]
        old.pos = 'RT'; old.ratings = {k:55 for k in TG.DEPTH_WEIGHTS['RT']}
        template = t.by_pos('QB')[0]
        donor = Team('DEN', 'United North', 'United'); donor.league = L
        L.teams['DEN'] = donor
        for pid, accrued, source in [('expensive-veteran',10,None), ('affordable-ps',0,'DEN')]:
            p = copy.deepcopy(template); p.pid = pid; p.name = pid; p.team = source
            p.contract = None; p.accrued = accrued; p.draft_year = None; p.draft_round = None
            p.xp_spent = {}; p.out_until = None; L.players[pid] = p
            if source: PS.squad(donor).append(p)
            else: L.free_agents.append(pid)
        t.sync_cap(); t.cap.cap = t.cap.charges(t.phase) + .01
        self.assertEqual(CD.repair_depth(L), 1)
        self.assertEqual(PS.essential_depth(t, week=L.week)['shortages'], {})
        self.assertEqual(L.player('affordable-ps').team, t.abbr)
        self.assertIsNone(L.player('expensive-veteran').team)
        GA.settle_roster(L,t,L.week)
        self.assertEqual(len(t.active()), 53)
        self.assertGreaterEqual(t.cap_space, -.0005)


if __name__ == '__main__':
    unittest.main()

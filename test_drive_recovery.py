"""Rest belongs to actual time off the field, once in regulation or overtime."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import game as G


def state():
    s=G.TeamState({})
    s.cond.cond.update(qb=70., dt=70., bench=70., hybrid=70., specialist=70.)
    return s


class DriveRecoveryTests(unittest.TestCase):
    def test_active_and_bench_accounting_excludes_extra_rest(self):
        s=state(); before=G._recovery_start(s)
        for _ in range(6):
            s.account_recovery_event()
            s.snap(dict(pid='qb'), 'QB')
            s.snap(dict(pid='bench'), 'QB', False)
        expected=dict(s.cond.cond)
        G._recovery_finish(before)
        self.assertEqual(s.cond.get('qb'),expected['qb'])
        self.assertEqual(s.cond.get('bench'),expected['bench'])
        self.assertAlmostEqual(s.cond.get('dt'),85.624)
        # A subsequent drive measures only new participation, not old totals.
        before=G._recovery_start(s)
        s.account_recovery_event()
        s.snap(dict(pid='dt'),'DT')
        dt=s.cond.get('dt');qb=s.cond.get('qb')
        G._recovery_finish(before)
        self.assertEqual(s.cond.get('dt'),dt)
        self.assertAlmostEqual(s.cond.get('qb'),qb+2.604)

    def test_zero_play_transition_does_not_create_recovery(self):
        s=state(); before=dict(s.cond.cond)
        G._recovery_finish(G._recovery_start(s))
        self.assertEqual(s.cond.cond,before)

    def test_hybrid_active_and_rest_events_not_double_counted(self):
        s=state(); before=G._recovery_start(s)
        p=dict(pid='hybrid')
        for _ in range(3):s.account_recovery_event()
        s.snap(p,'WR');s.snap(p,'CB');s.snap(p,'WR',False)
        condition=s.cond.get('hybrid')
        G._recovery_finish(before)
        self.assertEqual(s.cond.get('hybrid'),condition)
        self.assertEqual(s.snaps['hybrid'],2)

    def test_specialist_deduplicated_but_recovers_for_remaining_idle_time(self):
        for duration,expected in ((1,70.),(12,98.644)):
            s=state();before=G._recovery_start(s)
            p=dict(pid='specialist',pos='K')
            with patch.object(s,'hurt',return_value=None):
                G.special_injuries(s,[p,p],np.random.default_rng(1),lambda *a:.7,1)
            self.assertEqual(s.recovery_accounted['specialist'],1)
            for _ in range(duration-1):s.account_recovery_event()
            G._recovery_finish(before)
            self.assertAlmostEqual(s.cond.get('specialist'),expected)
            self.assertEqual(s.snaps,{})  # no invented extra special-teams load

    def test_overtime_live_and_instant_settle_both_inactive_units_once(self):
        outcomes=[]
        for live in (False,True):
            home,away=state(),state()
            def drive(*args,**kwargs):
                off,defense=args[13:15]
                for _ in range(3):
                    off.account_recovery_event();defense.account_recovery_event()
                    off.snap(dict(pid='qb'),'QB')
                    defense.snap(dict(pid='dt'),'DT')
                dr=NS(clock=0,points=0,result='Punt',plays=3,next_yardline=75,
                      log=[],quarter=5)
                yield ('snap',dr)
                return dr
            G.LAST_KICKOFF.clear()
            with patch.object(G,'drive_steps',side_effect=drive), \
                 patch.object(G,'kickoff_for',return_value=dict(new_yardline=75,touchback=True)), \
                 patch.object(G.PST,'record_defense'):
                args=({}, {}, {'home':0,'away':0},np.random.default_rng(2),None,None,None,lambda *a:.7)
                kwargs=dict(home_state=home,away_state=away,live=live)
                gen=G.overtime_steps(*args,**kwargs)
                while True:
                    try:next(gen)
                    except StopIteration:break
            self.assertAlmostEqual(home.cond.get('qb'),77.812)
            self.assertAlmostEqual(away.cond.get('dt'),77.812)
            self.assertLess(home.cond.get('dt'),70)
            self.assertLess(away.cond.get('qb'),70)
            outcomes.append((home.cond.cond,away.cond.cond))
        self.assertEqual(outcomes[0],outcomes[1])

    def test_same_physical_bench_time_regardless_of_official_play_count(self):
        # Official stats may exclude a live nullified snap; the committed
        # workload and sideline time still happened. No official count enters.
        s=state();before=G._recovery_start(s)
        for _ in range(11):
            pending=G._PendingSnap(s)
            pending.snap(dict(pid='qb'),'QB')
            pending.snap(dict(pid='bench'),'QB',False)
            pending.commit({})
        G._recovery_finish(before)
        self.assertAlmostEqual(s.cond.get('dt'),98.644)
        self.assertAlmostEqual(s.cond.get('bench'),98.644)

    def test_pending_presnap_selection_does_not_create_sideline_time(self):
        s=state();before=G._recovery_start(s);original=dict(s.cond.cond)
        pending=G._PendingSnap(s);pending.snap(dict(pid='qb'),'QB')
        G._recovery_finish(before)
        self.assertEqual(s.cond.cond,original)

    def test_idle_unit_receives_rest_before_switching_into_try_workload(self):
        s=state();s.cond.cond['qb']=98.;before=G._recovery_start(s)
        # The offense waits while its defense plays, then enters for a try.
        pending=G._PendingSnap(s);pending.snap(dict(pid='dt'),'DT');pending.commit({})
        G._recovery_finish(before)
        self.assertEqual(s.cond.get('qb'),100.)
        pending=G._PendingSnap(s);pending.snap(dict(pid='qb'),'QB');pending.commit({})
        after_work=s.cond.get('qb')
        self.assertLess(after_work,100.)
        G._recovery_finish(before)
        self.assertEqual(s.cond.get('qb'),after_work)
        settled=dict(s.cond.cond)
        G._recovery_finish(before)
        self.assertEqual(s.cond.cond,settled)

    def test_new_participant_does_not_receive_old_idle_credit_after_work(self):
        s=state();before=G._recovery_start(s)
        for _ in range(3):
            pending=G._PendingSnap(s);pending.snap(dict(pid='dt'),'DT');pending.commit({})
            G._recovery_finish(before)
        pending=G._PendingSnap(s);pending.snap(dict(pid='new'),'HB');pending.commit({})
        worked=s.cond.get('new')
        G._recovery_finish(before)
        self.assertEqual(s.cond.get('new'),worked)

    def test_late_knee_participant_event_precedes_its_workload(self):
        from test_designed_qb_runs import offense
        s=state();before=G._recovery_start(s)
        for _ in range(3):
            pending=G._PendingSnap(s);pending.snap(dict(pid='dt'),'DT');pending.commit({})
            G._recovery_finish(before)
        off=offense()
        G.field_units(off,s,np.random.default_rng(61),True,'11')
        worked=s.cond.get('QB')
        self.assertLess(worked,100)
        G._recovery_finish(before)
        self.assertEqual(s.cond.get('QB'),worked)


if __name__=='__main__':unittest.main()

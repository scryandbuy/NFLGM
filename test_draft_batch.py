"""Cooperative UI steps preserve bounded original draft commands and RNG."""
import unittest
import itertools
import json
from unittest.mock import patch
import session
import inbox
import test_draft_runtime as runtime_fixture


class DraftBatchTests(unittest.TestCase):
    def same_save(self,a,b):
        left,right=a.save(),b.save()
        if left!=right:
            def difference(x,y,path=''):
                if type(x)!=type(y):return path,repr(x)[:100],repr(y)[:100]
                if isinstance(x,dict):
                    if x.keys()!=y.keys():return path+'.keys',str(x.keys())[:100],str(y.keys())[:100]
                    for k in x:
                        if x[k]!=y[k]:return difference(x[k],y[k],path+'.'+str(k))
                if isinstance(x,list):
                    if len(x)!=len(y):return path+'.length',len(x),len(y)
                    for i,(u,v) in enumerate(zip(x,y)):
                        if u!=v:return difference(u,v,path+f'[{i}]')
                return path,repr(x)[:100],repr(y)[:100]
            self.fail(str(difference(json.loads(left),json.loads(right))))
    @classmethod
    def setUpClass(cls):
        runtime_fixture.DraftRuntimeTests.setUpClass()
        cls.initial = runtime_fixture.DraftRuntimeTests.initial

    def fresh(self):
        s = session.Session.load(self.initial)
        s.draft.auto = False
        # Two round-one CPU picks, one round-two CPU pick, then the user.
        s.draft.picks = [p for p in s.draft.picks if p.selection in (31,32,33,44)]
        for team in s.L.teams.values():
            team.picks=[p for p in team.picks if p.year!=s.draft.year or p in s.draft.picks]
        return s

    def message_ids(self,s):
        # Inbox IDs are a module-global counter; each independent replay
        # starts at the same saved value, just as separate process loads do.
        return patch.object(inbox,'_ids',itertools.count(max((m['id'] for m in s.L.inbox),default=0)+1))

    def test_bounded_commands_match_original_results_state_and_rng(self):
        for mode,expected in [('sim_to_me',3),('sim_round',2),('sim_draft',4)]:
            with self.subTest(mode=mode):
                original,chunked = self.fresh(),self.fresh()
                with self.message_ids(original): original.draft_act(mode)
                count=0
                with self.message_ids(chunked):
                    while True:
                        result=chunked.draft_batch_step(mode,round=1)
                        count+=result.get('picks',0)
                        if result['complete']:break
                self.assertEqual(count,expected)
                self.same_save(original,chunked)
                self.assertEqual(original.rng.bit_generator.state,chunked.rng.bit_generator.state)

    def test_current_user_pick_is_never_taken_by_to_me_or_round(self):
        s=self.fresh();s.draft.i=3
        before=s.save()
        for mode in ('sim_to_me','sim_round'):
            self.assertEqual(s.draft_batch_step(mode,round=2)['picks'],0)
        self.assertEqual(s.save(),before)
        self.assertTrue(s.draft_act('sim_pick_one')['ok'])
        self.assertIsNone(s.draft)

    def test_all_dnd_stops_full_auto_without_losing_completed_picks(self):
        original,chunked=self.fresh(),self.fresh()
        for s in (original,chunked):
            s.L.user_board={'dnd':[p.pid for p in s.L.draft_pool]}
        with self.message_ids(original): result=original.draft_act('sim_draft')
        with self.message_ids(chunked):
            while True:
                actual=chunked.draft_batch_step('sim_draft',round=1)
                if actual['complete']:break
        self.assertFalse(actual['ok']);self.assertFalse(result['ok'])
        self.assertEqual(chunked.draft.i,3)
        self.assertFalse(chunked.draft.auto)
        self.same_save(original,chunked)

    def test_error_restores_auto_and_completed_pick_can_be_saved_and_resumed(self):
        s=self.fresh();pick=s.draft.sim_pick
        def fail_after_pick():
            pick()
            raise RuntimeError('after completed selection')
        with patch.object(s.draft,'sim_pick',side_effect=fail_after_pick):
            with self.assertRaisesRegex(RuntimeError,'completed selection'):
                s.draft_batch_step('sim_draft',round=1)
        self.assertFalse(s.draft.auto)
        loaded=session.Session.load(s.save())
        self.assertEqual(len(loaded.draft.results),1)
        self.assertEqual(loaded.draft.current().selection,32)
        self.assertEqual(loaded.draft.results[0][2].pid,s.draft.results[0][2].pid)
        self.assertEqual(loaded.rng.bit_generator.state,s.rng.bit_generator.state)


if __name__=='__main__':unittest.main()

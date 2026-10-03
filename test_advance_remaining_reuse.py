"""Decision-batch lifetime and exact repair/save parity checks."""
import copy,json,unittest
from unittest.mock import patch
import numpy as np
import draft as D,draft_day as DD,roster_needs as RN,session
from test_package_roster_needs import team,player

class DraftReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s=session.Session.new('GB',seed=91);L=s.L
        L.year=2027;L.phase='offseason';L.season_closed_year=2026;s.stop=('offseason',12)
        L.draft_pool,L.next_class=L.next_class,[];order=sorted(L.teams)
        for t in L.teams.values():
            for pk in t.picks:
                if pk.year==2026:pk.selection=(pk.round-1)*32+order.index(pk.original)+1
        s.draft=DD.Draft(L,s.rng,2026,user_team='GB',auto_pick=True);cls.initial=s.save()
    def test_repeated_boards_owned_by_action_and_exception_cleanup(self):
        s=session.Session.load(self.initial);d=s.draft;real=D.board
        @DD._decision_batch
        def probe(d):
            first=d.board_for('KC');first.clear()
            second=d.board_for('KC');self.assertTrue(second)
            self.assertEqual(second,d.board_for('KC'))
            raise RuntimeError('stop')
        with patch.object(D,'board',wraps=real) as calls:
            with self.assertRaisesRegex(RuntimeError,'stop'):probe(d)
            self.assertEqual(calls.call_count,1)
            d.board_for('KC');self.assertEqual(calls.call_count,2)
        self.assertIsNone(d._board_cache);self.assertIsNone(d._draft_grade_cache)
    def test_round_matches_uncached_and_next_request_sees_new_evidence(self):
        a=session.Session.load(self.initial);b=session.Session.load(self.initial)
        class NoCache(dict):
            def __contains__(self,key):return False
            def __setitem__(self,key,val):pass
        b.draft._board_cache=NoCache();b.draft._draft_grade_cache=NoCache()
        with patch.object(a.draft,'_maybe_trade',return_value=None),patch.object(b.draft,'_maybe_trade',return_value=None):
            a.draft.sim_round();b.draft.sim_round()
        self.assertEqual(json.loads(a.save()),json.loads(b.save()))
        self.assertIsNone(a.draft._board_cache)
        target=a.draft.available()[0];a.L.scouting['GB'][target.pid]['ovr']+=10
        self.assertEqual(a.draft.board_for('GB'),D.board(a.L,'GB',a.draft.current().selection,a.draft.level,a.draft.taken,a.draft.scale))
    def test_trade_execution_invalidates_board_but_retains_evidence(self):
        s=session.Session.load(self.initial);d=s.draft;pk=d.current();buyer='DEN';seller=pk.owner
        offer={'a_sends':[]}
        @DD._decision_batch
        def probe(d):
            d.board_for(buyer);self.assertTrue(d._board_cache)
            evidence=d._draft_grade_cache.copy()
            with patch.object(d,'_package_valid',return_value=True),patch.object(s.L,'trade'):
                d._execute(buyer,seller,offer,pk)
            self.assertFalse(d._board_cache);self.assertEqual(evidence,d._draft_grade_cache)
        probe(d)

class PreparedRepairTests(unittest.TestCase):
    def test_every_swap_matches_full_report_and_coverage(self):
        for front,base in [('4-3','11'),('3-4','21'),('multiple','12')]:
            t=team(base,front);incoming=[player(pos,'new',84) for pos in ('QB','TE','CB','LEDG','LS')]
            prepared=RN.assessment_inputs(t,t.roster+incoming)
            for arrival in incoming:
                for departure in t.roster[::7]:
                    roster=[p for p in t.roster if p is not departure]+[arrival]
                    expected=RN.assess(t,roster);actual=RN.assess(t,roster,prepared=prepared)
                    for key in ('score','needs','uncovered','assignments','package_assignments','counts','package_demand'):
                        self.assertEqual(expected[key],actual[key],(front,arrival.pos,departure.pos,key))
                    self.assertEqual(RN.essential_coverage(t,report=actual),RN.essential_coverage(t,report=expected))
            with self.assertRaises(ValueError):RN.assess(team(),prepared=prepared)

class CompactSaveTests(unittest.TestCase):
    def test_whitespace_only_change_preserves_text_history_and_rng(self):
        import league
        s=session.Session(league.League(2026),np.random.default_rng(12),None)
        s.gameday={'note':'Keep spaces: a, b: c and \\n history','nested':[{'abc':123}]*40}
        raw=s.save();obj=json.loads(raw)
        self.assertLess(len(raw),len(json.dumps(obj)))
        self.assertEqual(obj['_gameday'],s.gameday)
        self.assertEqual(session.Session.load(raw).rng.bit_generator.state,s.rng.bit_generator.state)

if __name__=='__main__':unittest.main()

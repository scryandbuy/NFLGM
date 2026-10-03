import unittest
from unittest.mock import patch
from test_roster_advisor import fixture, player
from cap_engine import Contract
import roster_advisor as RA


class EvidenceTests(unittest.TestCase):
    def setup_case(self):
        league = fixture(); team = league.teams['GB']
        target = player('specialist','DT',79)
        old = player('reserve','DT',78,'GB')
        target.ratings['power_moves_rating'] = 92
        old.ratings['power_moves_rating'] = 75
        league.schedule = [(w,'MIN','GB',10,20) for w in range(1,4)]
        league.team_game_stats = {f'{league.year}-{w}-GB-MIN': {
            'GB':dict(dropbacks=30,sacks=1),
            'MIN':dict(dropbacks=30,pressures=2)} for w in range(1,4)}
        return league,team,target,old

    def test_measured_weakness_and_specific_attribute(self):
        l,t,p,old = self.setup_case()
        with patch.object(RA,'_grade',return_value=79):
            reason = RA.performance_case(l,t,p,old,[])
        self.assertIn('pass rush',reason)
        self.assertIn('power moves (92)',reason)
        self.assertNotIn('79.0',reason)

    def test_no_claim_from_missing_small_or_healthy_sample(self):
        for mode in ('missing','small','healthy'):
            l,t,p,old = self.setup_case()
            if mode == 'missing': l.team_game_stats = {}
            elif mode == 'small': l.schedule = l.schedule[:2]
            else:
                for game in l.team_game_stats.values(): game['MIN']['pressures']=10
            self.assertIsNone(RA.performance_case(l,t,p,old,[]))

    def test_internal_specialist_and_wrong_position(self):
        l,t,p,old = self.setup_case(); internal = player('internal','DT',79)
        internal.ratings['power_moves_rating']=91
        with patch.object(RA,'_grade',return_value=79):
            self.assertIsNone(RA.performance_case(l,t,p,old,[internal]))
            internal.pos='HB'
            self.assertIsNotNone(RA.performance_case(l,t,p,old,[internal]))

    def test_marginal_depth_and_expensive_rotation_rejected(self):
        for grade,cost in ((79,1),(83,10)):
            l=fixture();p=player('target','REDG',grade);l.players[p.pid]=p;l.free_agents=[p.pid]
            with patch.object(RA,'_terms',return_value=(Contract(1,[cost]),'Cost')):
                self.assertNotIn(p.pid,[r['pid'] for r in RA.candidates(l,14)])

    def test_duplicate_role_compares_correct_assignment(self):
        p=object()
        before={'assignments':[dict(role='DT',grade=90),dict(role='DT',grade=70)]}
        after={'assignments':[dict(role='DT',grade=91,player=p),dict(role='DT',grade=70,player=None)]}
        self.assertFalse(RA.role_improvement(before,after,p))

    def test_specialist_reaches_report_without_roster_mutation(self):
        l,t,_,_=self.setup_case()
        p=player('specialist','REDG',78);p.ratings['power_moves_rating']=92
        l.players[p.pid]=p;l.free_agents=[p.pid]
        before=[q.pid for q in t.roster]
        with patch.object(RA,'_terms',return_value=(Contract(1,[1]),'Estimated remaining cap cost: $1.00m.')):
            rows=RA.candidates(l,14)
        chosen=next(r for r in rows if r['pid']==p.pid)
        self.assertIn('pass rush',chosen['reason'])
        self.assertNotIn('Current room',chosen['reason'])
        self.assertEqual(before,[q.pid for q in t.roster])

if __name__ == '__main__': unittest.main()

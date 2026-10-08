"""Weekly search reuse must preserve action, restraint and fresh roster reads."""
import unittest
from unittest.mock import patch
import practice_squad as PS
import roster_advisor as RA
import roster_needs as RN
from test_roster_advisor import fixture, player
from cap_engine import Contract


class WeeklyEvaluationTests(unittest.TestCase):
    def test_room_review_matches_individual_reads_across_roles_and_coaches(self):
        outcomes = set()
        for front, personnel in [('4-3','11'), ('3-4','12'), ('multiple','21')]:
            league = fixture(); team = league.teams['GB']
            team.gm.def_front = front; team.gm.off_personnel = personnel
            league.player('GB-CB-0').out_until = 8
            review = PS.room_review(league, team)
            for pos in ('CB','FS','LT','HB','TE','K'):
                for grade in (60, 95):
                    arrival = player('arrival-'+pos, pos, grade)
                    for cost in (1., team.cap_space + 500.):
                        contract = Contract(1,[cost])
                        uncached = PS.room_candidate(league, team, arrival, contract)
                        cached = PS.room_candidate(league, team, arrival, contract, review=review)
                        a = getattr(uncached, 'pid', None); b = getattr(cached, 'pid', None)
                        self.assertEqual(a, b, (front, personnel, pos, grade, cost))
                        outcomes.add(b is not None)
        self.assertEqual(outcomes, {True, False})

    def test_new_review_sees_health_roster_and_coaching_changes(self):
        league = fixture(); team = league.teams['GB']
        before = PS.room_review(league, team)
        league.player('GB-CB-0').out_until = 10
        added = player('new-corner','CB',98,'GB'); team.roster.append(added)
        team.gm.def_front = '3-4'
        after = PS.room_review(league, team)
        self.assertNotIn(added, before['active']); self.assertIn(added, after['active'])
        self.assertEqual(after['before'], PS.essential_depth(team, team.active(), league.week))
        self.assertEqual(after['report']['score'], RN.assess(team)['score'])
        with self.assertRaises(ValueError):
            PS.room_candidate(league, league.teams['MIN'], added, review=after)

    def test_advice_skips_release_search_for_unavailable_opposing_starters(self):
        league = fixture(); team = league.teams['GB']
        while len(team.active()) < 53:
            p = player('filler-'+str(len(team.roster)), 'WR',65,'GB')
            team.roster.append(p); league.players[p.pid] = p
        seller = league.teams['MIN']
        starters = {a['player'].pid for a in RN.assess(seller, strict_roles=True)['assignments'] if a['player']}
        with patch.object(PS, 'room_candidate', wraps=PS.room_candidate) as room:
            RA.candidates(league, 5)
        evaluated = {c.args[2].pid for c in room.call_args_list}
        self.assertFalse(starters & evaluated)


if __name__ == '__main__': unittest.main()

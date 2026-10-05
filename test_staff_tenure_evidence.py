"""Annual credit follows the coach's games, with restraint for short stints."""
import copy
import json
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import numpy as np
import staff as ST


def coach(name, team):
    c = ST.Coach(name, 'dc', 65, 50, 'coverage', 48, 3, team)
    c.staff_traits = []; c.salary = 2
    return c


def fixture(hire_week=8):
    L = NS(year=2029, week=18, phase='offseason', teams={}, schedule=[],
           game_stats={}, transactions=[], staff_pool=[], user_team=None)
    L.log = lambda kind, **kw: L.transactions.append(dict(kind=kind, **kw))
    for i in range(32):
        a = f'T{i:02}'
        L.teams[a] = NS(abbr=a, staff={'dc':coach(a, a)}, gm=NS(prestige=50))
    old = L.teams['T00'].staff['dc']; old.team = None
    new = coach('Successor', 'T00'); L.teams['T00'].staff['dc'] = new; L.staff_pool = [old]
    for kind, name in [('staff_out', old.name), ('staff_in', new.name)]:
        L.transactions.append(dict(year=2029, week=hire_week, phase='regular',
            kind=kind, team='T00', role='dc', name=name, after_week=hire_week))
    for week in range(1, 18):
        for i in range(0, 32, 2):
            home, away = f'T{i:02}', f'T{i+1:02}'
            L.schedule.append((week, away, home, 17, 24))
            book = {}
            for a in (home, away):
                score = (-1 if week <= hire_week else 1) if a == 'T00' else int(a[1:])*.001
                book[a] = dict(team=a, def_epa=score*60, def_plays=60)
            L.game_stats[f'2029-{week}-{home}-{away}'] = book
    return L, old, new


class StaffTenureEvidence(unittest.TestCase):
    def test_predecessor_and_successor_receive_only_their_games(self):
        L, old, new = fixture()
        original = copy.deepcopy((L.game_stats, L.transactions))
        evidence = ST.coach_season_evidence(L, 2029)
        a, b = evidence[(old.name, 'dc')], evidence[(new.name, 'dc')]
        self.assertEqual([x['week'] for x in a['games']], list(range(1,9)))
        self.assertEqual([x['week'] for x in b['games']], list(range(9,18)))
        self.assertEqual(a['rank'], 32); self.assertEqual(b['rank'], 1)
        self.assertEqual((L.game_stats, L.transactions), original)
        ST.season_end(L, ST.unit_ranks(L, 2029))
        self.assertEqual(old.unit_ranks, [32]); self.assertEqual(new.unit_ranks, [1])
        saved = json.loads(json.dumps(ST.to_dict(L)))
        ST.from_dict(L, saved)
        self.assertEqual(L.staff_pool[0].unit_reviews[-1]['games'], a['games'])
        self.assertEqual(L.teams['T00'].staff['dc'].unit_reviews[-1]['rank'], 1)

    def test_short_stint_and_missing_book_do_not_create_bad_season(self):
        L, old, new = fixture(15)
        new.unit_ranks = [30, 31]
        ST.season_end(L, ST.unit_ranks(L, 2029))
        self.assertEqual(new.unit_ranks, [30, 31])
        self.assertIsNone(new.unit_reviews[-1]['rank'])
        L, old, new = fixture()
        del L.game_stats['2029-12-T00-T01']
        e = ST.coach_season_evidence(L, 2029)
        self.assertIsNone(e[(new.name, 'dc')]['rank'])
        self.assertEqual(e[(old.name, 'dc')]['rank'], 32)

    def test_career_year_combines_two_clubs_without_predecessor_games(self):
        L, old, new = fixture()
        other = L.teams['T02'].staff['dc']; other.team = None; L.staff_pool = [other]
        old.team = 'T02'; L.teams['T02'].staff['dc'] = old
        for kind, name in [('staff_out', other.name), ('staff_in', old.name)]:
            L.transactions.append(dict(year=2029, week=10, phase='regular', kind=kind,
                team='T02', role='dc', name=name, after_week=10))
        e = ST.coach_season_evidence(L, 2029)[(old.name, 'dc')]
        self.assertEqual(len(e['games']), 15)
        self.assertEqual([x['week'] for x in e['games'] if x['team']=='T02'], list(range(11,18)))
        ST.season_end(L, ST.unit_ranks(L, 2029))
        self.assertEqual(len(old.unit_reviews), 1)
        self.assertEqual(len(old.unit_ranks), 1)

    def test_explicit_pregame_boundary_and_legacy_postgame_fallback(self):
        L, old, new = fixture()
        for tx in L.transactions: tx['after_week'] = 7
        self.assertEqual(ST.coach_season_evidence(L,2029)[(new.name,'dc')]['games'][0]['week'],8)
        for tx in L.transactions: del tx['after_week']
        self.assertEqual(ST.coach_season_evidence(L,2029)[(new.name,'dc')]['games'][0]['week'],9)

    def test_pool_history_legacy_load_not_rewritten(self):
        c = coach('Legacy','T00'); c.unit_ranks = [29, 31]
        saved = c.to_dict(); del saved['unit_reviews']
        loaded = ST.Coach.from_dict(saved)
        self.assertEqual(loaded.unit_ranks, [29,31]); self.assertEqual(loaded.unit_reviews, [])

    def test_carousel_keeps_short_stint_but_can_act_on_consecutive_bad_seasons(self):
        from test_staff_contracts import league as contract_league, coach as candidate
        from unittest.mock import Mock
        for current_rank, previous_rank, previous_year, fired in [(None,30,2028,False),
                (31,None,2028,False), (31,30,2027,False), (31,30,2028,True)]:
            with self.subTest(current=current_rank, previous=previous_rank, year=previous_year):
                L = contract_league(); L.year = 2029; L.user_team = None
                L.staff_pool = [candidate('Affordable Upgrade', 'dc', team=None, rating=85, years=3)]
                for c in L.teams['A'].staff.values(): c.years = 3
                c = L.teams['A'].staff['dc']; c.unit_ranks = [30,31]
                c.unit_reviews = [dict(year=previous_year, rank=previous_rank), dict(year=2029, rank=current_rank)]
                rng = Mock(); rng.random.return_value=0.; rng.choice.return_value=3; rng.normal.return_value=0.
                def make(_rng, role, **kw): return candidate('Available '+role, role, team=None, rating=75, years=3)
                with patch.object(ST,'make',side_effect=make), patch.object(ST,'finalize_poaches'), \
                     patch('coaching_pool.close_pending_hires'):
                    ST.carousel(L,rng)
                self.assertEqual(L.teams['A'].staff['dc'] is not c, fired)


if __name__ == '__main__': unittest.main()

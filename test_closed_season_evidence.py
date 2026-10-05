"""Previous-season facts survive close, rollover and save/load."""
import copy
import unittest
from types import SimpleNamespace as NS

import firing_model as FM
import offseason_calendar as OC
from league import Team, League
from test_cap_accounting import fixture


class ClosedSeasonEvidence(unittest.TestCase):
    def team(self, old, new):
        L = fixture(); L.year = 2029
        t = L.teams['GB']; t.league = L; t.cap.year = 2029
        t.history = [dict(year=2027, win_pct=.5),
                     dict(year=2028, win_pct=old/17, record=[old, 17-old, 0])]
        t.record = [new, 17-new, 0]; t.tenure = 8; t.expected_cached = .5
        return L, t

    def test_declining_stable_and_improving_seasons_survive_close(self):
        for old, new in [(11, 3), (16, 8), (13, 7), (9, 9), (6, 13)]:
            with self.subTest(old=old, new=new):
                L, t = self.team(old, new)
                before = t.hist(); contender = t.contender
                t.history.append(dict(year=2029, win_pct=new/17, record=t.record[:]))
                L.season_closed_year = 2029
                self.assertEqual(t.prev_win_pct, old/17)
                self.assertEqual(t.hist()['win_pct'], before['win_pct'])
                self.assertEqual(t.hist()['prev_win_pct'], before['prev_win_pct'])
                self.assertEqual(t.contender, contender)
                self.assertEqual(OC.team_context(L)['histories']['GB'], t.hist())
                if new < old:
                    erased = dict(t.hist(), win_pct=new/17, prev_win_pct=new/17)
                    self.assertGreater(FM.fire_chance_offseason(t.hist()), FM.fire_chance_offseason(erased))

    def test_rollover_uses_just_finished_year_and_context_keeps_old_comparison(self):
        L, t = self.team(11, 3)
        t.history.append(dict(year=2029, win_pct=3/17, record=t.record[:]))
        context = OC.team_context(L)
        L.year = 2030; t.record = [0, 0, 0]
        self.assertEqual(t.prev_win_pct, 3/17)
        self.assertEqual(t.win_pct, 3/17)
        self.assertEqual(context['histories']['GB']['prev_win_pct'], 11/17)
        self.assertEqual(context['records']['GB'], [3, 14, 0])

    def test_reload_and_detached_team_cap_year(self):
        L, t = self.team(11, 3)
        t.history.append(dict(year=2029, win_pct=3/17, record=t.record[:]))
        loaded = League.load(L.save())
        self.assertEqual(loaded.teams['GB'].prev_win_pct, 11/17)
        del t.league
        self.assertEqual(t.prev_win_pct, 11/17)
        t.cap.year = 2030
        self.assertEqual(t.prev_win_pct, 3/17)

    def test_latest_earlier_year_not_blind_previous_list_entry(self):
        L, t = self.team(11, 3)
        t.history.reverse()
        t.history.extend([dict(year=2029, win_pct=3/17), dict(year=2029, win_pct=3/17)])
        self.assertEqual(t.prev_win_pct, 11/17)
        t.history = [dict(year=2029, win_pct=3/17)]
        self.assertEqual(t.prev_win_pct, .5)
        t.history = [dict(win_pct=.6)]
        self.assertEqual(t.prev_win_pct, .6)


if __name__ == '__main__': unittest.main()

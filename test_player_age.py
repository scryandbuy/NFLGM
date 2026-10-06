"""Birthday/calendar behavior through production persistence and age consumers."""
import copy
from datetime import date, timedelta
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import league as LG
import player_age as PA
import regression as RG
import retirement as RT
import xp as XP
import xp_spend as XS
from test_regression_aging import player


class Birthdays(unittest.TestCase):
    def make(self, born='2001-11-05', year=2028, pid='birthday-test', pos='HB'):
        L = LG.League(year)
        p = player(pid, pos, 26.8)
        p.birth_date = born
        p.potential = 95
        L.players[p.pid] = p
        L.ls_reserve_version = 1
        PA.initialize_player(p, L)
        return L, p

    def test_week_nine_birthday_changes_age_not_xp_prices_or_ratings(self):
        L, p = self.make()
        before = dict(p.ratings)
        PA.game_week(L, 8)
        self.assertEqual(int(p.age), 26)
        prices = [XP.cost_per_point(p, a) for a in ('speed_rating', 'awareness_rating', 'carry_rating')]
        unlock = XP.unlock_cost(p)
        seasonal = p.development_age
        PA.game_week(L, 9)
        self.assertEqual(int(p.age), 27)
        PA.game_week(L, 18)
        self.assertEqual(prices, [XP.cost_per_point(p, a) for a in ('speed_rating', 'awareness_rating', 'carry_rating')])
        self.assertEqual(unlock, XP.unlock_cost(p))
        self.assertEqual(seasonal, p.development_age)
        self.assertEqual(before, p.ratings)
        self.assertEqual(p.accrued, 0)

    def test_january_playoff_birthday_does_not_reset_development_year(self):
        L, p = self.make('2001-01-15')
        seasonal = p.development_age
        PA.game_week(L, 18)
        self.assertEqual(int(p.age), 27)
        PA.game_week(L, 21)
        self.assertEqual(int(p.age), 28)
        self.assertEqual(p.development_year, 2028)
        self.assertEqual(p.development_age, seasonal)
        self.assertEqual(L.year, 2028)

    def test_leap_day_and_non_leap_century(self):
        for year in (2028, 2029, 2100, 2104):
            birthday = PA.anniversary(date(2000, 2, 29), year)
            self.assertEqual(int(PA.age_on('2000-02-29', birthday - timedelta(days=1))), year - 2001)
            self.assertEqual(int(PA.age_on('2000-02-29', birthday)), year - 2000)

    def test_offseason_birthday_and_year_roll_update_season_age_once(self):
        L, p = self.make('2001-05-31')
        PA.offseason(L, 2)
        self.assertEqual(L.game_date, '2029-02-25')
        old = p.development_age
        old_age = p.age
        L.roll_year(np.random.default_rng(1))
        self.assertEqual(p.development_year, 2029)
        self.assertAlmostEqual(p.development_age - old, 1, delta=.003)
        self.assertLess(p.age - old_age, .1)
        PA.offseason(L, 11)
        self.assertEqual(int(p.age), 27)
        PA.offseason(L, 13)  # July camp is after this player's May birthday.
        self.assertEqual(int(p.age), 28)
        fixed = p.development_age
        PA.offseason(L, 13)
        self.assertEqual(fixed, p.development_age)

    def test_calendar_is_monotonic_and_repeated_steps_do_not_age_twice(self):
        L, p = self.make()
        PA.game_week(L, 10)
        current = (L.game_date, p.age, p.development_age)
        for _ in range(3):
            PA.game_week(L, 10)
            PA.game_week(L, 3)
        self.assertEqual(current, (L.game_date, p.age, p.development_age))

    def test_all_offseason_stops_monotonic_across_league_year_change(self):
        dates = [PA.stop_date(2028 if i <= 3 else 2029, ('offseason', i)) for i in range(14)]
        self.assertEqual(dates, sorted(set(dates)))
        self.assertGreater(dates[0], PA.week_date(2028, 22))
        self.assertLess(dates[-1], PA.week_date(2029, 1))

    def test_save_roundtrip_preserves_birthday_age_and_cost(self):
        L, p = self.make()
        PA.game_week(L, 11)
        L.phase = 'regular'; L.week = 11
        blob = L.save()
        restored = LG.League.load(blob)
        q = restored.player(p.pid)
        self.assertEqual(q.birth_date, p.birth_date)
        self.assertEqual(q.age, p.age)
        self.assertEqual(q.development_age, p.development_age)
        self.assertEqual(XP.cost_per_point(q), XP.cost_per_point(p))
        self.assertEqual(restored.game_date, L.game_date)

    def test_legacy_hall_repair_changes_neither_ratings_nor_experience(self):
        L, p = self.make(pid='P1978')
        p.birth_date = None; p.age = 26.3; p.draft_year = 2022; p.accrued = 6
        p.development_age = p.development_year = None
        p.xp = 1234
        saved = L.to_dict()
        for key in ('game_date', 'age_calendar_version', 'age_migration', 'regression_applied_years'):
            saved.pop(key, None)
        saved.update(phase='offseason', week=22, _stop=['offseason', 5])
        rng = np.random.default_rng(32)
        state = copy.deepcopy(rng.bit_generator.state)
        restored = LG.League.load(saved)
        q = restored.player(p.pid)
        self.assertEqual(q.birth_date, '2001-05-31')
        self.assertEqual(int(q.age), 26)  # March 2028, birthday still ahead.
        PA.offseason(restored, 13)  # July camp, after the May birthday.
        self.assertEqual(int(q.age), 27)
        self.assertEqual((q.ratings, q.xp, q.accrued), (p.ratings, 1234, 6))
        self.assertEqual(state, rng.bit_generator.state)
        self.assertEqual(restored.regression_applied_years, [2027])

    def test_unknown_legacy_birthdays_are_stable_and_keep_whole_age(self):
        L, p = self.make(pid='N2028HB001')
        p.birth_date = None; p.age = 22
        p.development_age = p.development_year = None
        PA.initialize_player(p, L, use_seed=True)
        self.assertEqual(int(p.age), 22)
        born = p.birth_date
        restored = LG.Player.from_dict(p.to_dict())
        PA.initialize_player(restored, L)
        self.assertEqual(restored.birth_date, born)

    def test_midseason_migration_preserves_xp_prices_but_corrects_review_age(self):
        L, p = self.make(pid='P1978', year=2027)
        p.birth_date = p.development_age = p.development_year = None
        p.age = 25.3
        price = XP.cost_per_point(p, 'speed_rating')
        saved = L.to_dict()
        for key in ('game_date', 'age_calendar_version', 'age_migration'):
            saved.pop(key)
        saved.update(phase='regular', week=14, _stop=['week', 15])
        restored = LG.League.load(saved)
        q = restored.player(p.pid)
        self.assertEqual(int(q.age), 26)
        self.assertEqual(XP.cost_per_point(q, 'speed_rating'), price)
        self.assertEqual(int(PA.review_age(q)), 26)
        PA.offseason(restored, 2)
        restored.roll_year(np.random.default_rng(1))
        self.assertGreater(XP.cost_per_point(q, 'speed_rating'), price)

    def test_auto_spend_retains_physical_choices_across_birthday(self):
        L, p = self.make('2002-11-05')
        PA.game_week(L, 8)
        gm = SimpleNamespace(dev_belief=.5)
        class EachOption:
            def __init__(self, index): self.index = index
            def choice(self, n, p): return self.index % n
        choices = [XS.choose_attr(p, gm, EachOption(i)) for i in range(60)]
        self.assertTrue(any(k in XP.PHYSICAL or k in XP.TOOLS for k in choices))
        PA.game_week(L, 10)
        self.assertGreater(p.age, 26)
        self.assertEqual(choices, [XS.choose_attr(p, gm, EachOption(i)) for i in range(60)])

    def test_reserve_age_limit_lasts_until_twenty_sixth_birthday(self):
        import specialist_reserve as SR
        L, p = self.make('2003-11-05', pos='LS')
        p.team = None
        p.ratings = {k: 60 for k in p.ratings}
        PA.game_week(L, 8)
        self.assertTrue(SR.eligible(p))
        PA.set_date(L, '2029-11-04')
        self.assertTrue(SR.eligible(p))
        PA.set_date(L, '2029-11-05')
        self.assertFalse(SR.eligible(p))

    def test_generated_birthday_survives_forty_calendar_years_without_drift(self):
        L, p = self.make(pid='N2028HB002')
        p.birth_date = None; p.age = 22.4
        PA.initialize_player(p, L)
        born = p.birth_date
        initial = p.age
        for year in range(2029, 2069):
            L.year = year
            PA.set_date(L, date(year, 8, 25))
            p = LG.Player.from_dict(p.to_dict()); L.players[p.pid] = p
        self.assertEqual(p.birth_date, born)
        self.assertAlmostEqual(p.age - initial, 40, delta=.003)
        self.assertEqual(p.development_year, 2068)

    def test_unknown_fractional_age_boundaries_keep_completed_years(self):
        L, p = self.make()
        for age in (21.00001, 21.99999, 22.00001, 22.99999):
            p.birth_date = None; p.age = age
            PA.initialize_player(p, L)
            self.assertEqual(int(p.age), int(age))

    def test_newgen_birthdays_do_not_change_class_ratings_or_rng(self):
        import newgens as NG
        a, b = LG.League(2058), LG.League(2058)
        r1, r2 = np.random.default_rng(51), np.random.default_rng(51)
        generated = NG.build(a, r1, draft_year=2059)
        with patch.object(PA, 'initialize_player'):
            control = NG.build(b, r2, draft_year=2059)
        self.assertGreater(len(generated), 300)
        self.assertEqual(r1.bit_generator.state, r2.bit_generator.state)
        self.assertEqual([(p.pid, p.ratings, p.potential) for p in generated],
                         [(p.pid, p.ratings, p.potential) for p in control])
        self.assertTrue(all(p.birth_date and p.development_year == 2058 for p in generated))
        restored = LG.League.load(a.save())
        self.assertEqual([p.birth_date for p in generated],
                         [restored.player(p.pid).birth_date for p in generated])

    def test_retirement_uses_season_age_not_birthday_or_review_date(self):
        L, p = self.make('1995-11-05')
        PA.game_week(L, 8)
        before = RT.chance(p, ovr=80)
        PA.offseason(L, 2)
        self.assertEqual(before, RT.chance(p, ovr=80))

    def test_regression_uses_calendar_age_once_and_preserves_prospects(self):
        L, p = self.make('1995-11-05')
        prospect = player('next', 'HB', 22)
        L.players['next'] = prospect; L.next_class = [prospect]
        original = dict(prospect.ratings)
        PA.offseason(L, 2)
        rng = np.random.default_rng(41)
        RG.run(L, rng, record_for='GB', tick_age=False)
        ratings = dict(p.ratings)
        state = copy.deepcopy(rng.bit_generator.state)
        self.assertEqual(prospect.ratings, original)
        RG.run(L, rng, record_for='GB', tick_age=False)
        self.assertEqual(p.ratings, ratings)
        self.assertEqual(state, rng.bit_generator.state)
        restored = LG.League.load(L.save())
        RG.run(restored, rng, tick_age=False)
        self.assertEqual(restored.player(p.pid).ratings, ratings)

    def test_annual_review_uses_current_age_not_upcoming_season_age(self):
        L, p = self.make('2001-11-05')
        PA.offseason(L, 2)
        expected = PA.age_on(p.birth_date, date.fromisoformat(L.game_date))
        with patch.object(RG, 'decline', return_value=0) as decline:
            RG.run(L, np.random.default_rng(1), tick_age=False)
        self.assertEqual(decline.call_args.kwargs['age'], expected)
        self.assertNotEqual(expected, PA.age_on(p.birth_date, date(2029, 9, 1)))

    def test_session_advance_updates_to_next_stop_without_award_age_tick(self):
        import session as SS
        L, p = self.make()
        s = SS.Session(L, np.random.default_rng(1), None)
        s.stop = ('week', 8)
        def move():
            s.stop = ('week', 9)
            return {'done': 'Week 8'}
        with patch.object(s, 'blocking', return_value=[]), patch.object(s, '_advance', side_effect=move), \
             patch.object(SS.STF, 'resolve_references'), patch.object(SS.IB, 'reconcile'):
            s.advance()
        self.assertEqual(int(p.age), 27)
        self.assertEqual(L.game_date, PA.week_date(2028, 9).isoformat())

    def test_staged_market_close_advances_calendar_without_batch_market_run(self):
        import market as MK
        L, p = self.make('2001-04-05')
        L.game_date = '2028-04-03'
        PA.set_date(L, L.game_date)
        seasonal = p.development_age
        self.assertEqual(int(p.age), 26)
        self.assertEqual(MK.close_market(L, np.random.default_rng(1)), [])
        self.assertEqual(L.game_date, '2028-04-10')
        self.assertEqual(int(p.age), 27)
        self.assertEqual(p.development_age, seasonal)

    def test_batch_and_live_preparation_use_the_same_calendar(self):
        import season as SN
        import practice_integration as PI
        L, p = self.make()
        runner = SN.SeasonRunner.__new__(SN.SeasonRunner)
        runner.L = L
        with patch.object(PI, 'prepare', return_value=None):
            runner.prepare_practice(9)
        self.assertEqual(int(p.age), 27)
        self.assertEqual(L.game_date, PA.week_date(2028, 9).isoformat())


if __name__ == '__main__':
    unittest.main()

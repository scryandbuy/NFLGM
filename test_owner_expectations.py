import copy
import unittest
from types import SimpleNamespace as NS

from views import _owner_assessment, _owner_mood
from test_cap_accounting import fixture
from league import League


class OwnerExpectations(unittest.TestCase):
    def team(self, record, expected=.5, patience=.5):
        return NS(abbr='GB', record=record, expected_pct=expected,
                  owner_patience=patience, league=NS(year=2029, standings_history={}))

    def test_same_record_differs_against_rebuild_and_contender_expectations(self):
        self.assertEqual(_owner_mood(self.team((8, 9, 0), .35)), 'Pleased')
        self.assertEqual(_owner_mood(self.team((8, 9, 0), .70)), 'Restless')

    def test_patient_owner_reserves_judgment_on_borderline_shortfall(self):
        self.assertEqual(_owner_mood(self.team((8, 9, 0), .56, .05)), 'Restless')
        self.assertEqual(_owner_mood(self.team((8, 9, 0), .56, .95)), 'Settled')

    def test_patience_does_not_excuse_severe_sustained_underperformance(self):
        for patience in (.05, .5, .95):
            self.assertEqual(_owner_mood(self.team((2, 15, 0), .65, patience)), 'Angry')

    def test_one_game_does_not_produce_angry_or_pleased_whiplash(self):
        for record in ((0, 1, 0), (1, 0, 0)):
            mood = _owner_mood(self.team(record, .5))
            self.assertEqual(mood, 'Settled')

    def test_ties_count_half_a_win_and_all_games(self):
        result = _owner_assessment(self.team((7, 7, 3)))
        self.assertEqual(result['actual_pct'], .5)
        self.assertEqual(result['games'], 17)
        self.assertEqual(result['evidence_wins'], 0)
        self.assertEqual(result['mood'], 'Settled')

    def test_champion_is_pleased_despite_disappointing_regular_record(self):
        t = self.team((9, 8, 0), .8)
        t.league.standings_history = {2029: {'GB': {'exit': 'SB_WIN'}}}
        self.assertEqual(_owner_mood(t), 'Pleased')
        t.league.year = 2030
        self.assertNotEqual(_owner_mood(t), 'Pleased')

    def test_no_games_reserves_judgment_and_does_not_use_last_year_title(self):
        for expected in (.25, .5, .8):
            result = _owner_assessment(self.team((0, 0, 0), expected))
            self.assertEqual(result['mood'], 'Settled')
            self.assertIn('No games played', result['reason'])

    def test_better_results_never_worsen_mood_for_fixed_owner_and_expectation(self):
        levels = {'Angry': 0, 'Restless': 1, 'Settled': 2, 'Pleased': 3}
        for expected in (.25, .5, .8):
            for patience in (.05, .5, .95):
                moods = [levels[_owner_mood(self.team((w, 17-w, 0), expected, patience))] for w in range(18)]
                self.assertEqual(moods, sorted(moods))

    def test_reload_preserves_owner_read_and_view_does_not_mutate_evidence(self):
        L = fixture(); L.user_team = 'GB'
        t = L.teams['GB']; t.record = (8, 9, 0); t.expected_cached = .56; t.owner_patience = .95
        before = copy.deepcopy(L.save())
        result = _owner_assessment(t)
        loaded = League.load(L.save())
        self.assertEqual(result, _owner_assessment(loaded.teams['GB']))
        self.assertEqual(before, L.save())


if __name__ == '__main__': unittest.main()

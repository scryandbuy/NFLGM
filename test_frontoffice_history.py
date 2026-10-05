import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from cap_engine import Contract
from league import League
from test_cap_accounting import fixture, player
import targets as TG
import views_frontoffice as VF


class FrontOfficeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture()
        self.L.year = 2029
        self.L.user_team = 'GB'
        self.L.phase = 'offseason'
        self.L.season_closed_year = 2029
        self.L.game_date = '2030-02-25'
        self.s = NS(user_team='GB')
        self.t = self.L.teams['GB']
        self.p = player(self.L, contract=Contract(2, [10, 10], signed=2029))
        self.p.name = 'Test Quarterback'
        self.p.ratings = {key: 90. for key in TG.DEPTH_WEIGHTS['QB']}
        self.addCleanup(patch.stopall)
        patch.object(VF, 'rail', return_value={}).start()

    def meeting(self, context=None):
        row = dict(pid=self.p.pid, kind='star', quote='Discuss my deal.',
                   options=[dict(key='spring', label='Extend', cost='promise:extension_by')],
                   answer='spring', said='Agreed.')
        if context is not None: row['context'] = context
        return row

    def test_owner_history_uses_saved_assessment_not_current_mood(self):
        self.t.history = [dict(year=2027, record=[4, 12, 1]), dict(year=2028, record=[15, 2, 0])]
        self.L.history = {'2028': {'review': dict(club={'abbr': 'GB'}, record='15–2',
                                               owner={'line': 'The saved verdict.'})}}
        before = copy.deepcopy(self.L.history)
        rows = VF._owner_review_history(self.L, self.t)
        self.assertEqual([r['year'] for r in rows], [2028, 2027])
        self.assertEqual(rows[0]['line'], 'The saved verdict.')
        self.assertEqual(rows[1]['record'], '4–12–1')
        self.assertIn('not recorded', rows[1]['line'])
        self.t.record = (0, 17, 0)
        self.assertEqual(rows, VF._owner_review_history(self.L, self.t))
        self.assertEqual(before, self.L.history)

    def test_other_club_does_not_borrow_user_owner_verdict(self):
        self.L.history = {'2028': {'review': dict(club={'abbr': 'GB'}, record='15–2',
                                               owner={'line': 'GB only.'})}}
        other = self.L.teams['MIN']
        other.history = [dict(year=2028, record=[5, 12, 0])]
        rows = VF._owner_review_history(self.L, other)
        self.assertEqual(rows[0]['record'], '5–12')
        self.assertNotEqual(rows[0]['line'], 'GB only.')

    def test_owner_legacy_snapshot_without_club_belongs_only_to_user(self):
        self.L.history = {'2028': {'review': dict(record='15–2', owner={'line': 'Saved user.'})}}
        self.assertEqual(VF._owner_review_history(self.L, self.t)[0]['line'], 'Saved user.')
        self.assertEqual(VF._owner_review_history(self.L, self.L.teams['MIN']), [])

    def test_owner_history_reuses_serialized_season_snapshots(self):
        self.L.history = {'2028': {'review': dict(club={'abbr': 'GB'}, record='13–4',
                                               owner={'line': 'Pleased that year.'})}}
        loaded = League.load(self.L.save())
        self.assertEqual(VF._owner_review_history(self.L, self.t),
                         VF._owner_review_history(loaded, loaded.teams['GB']))

    def test_new_meeting_captures_context_once_and_survives_reload(self):
        with patch('morale.wants_out', return_value=False), patch('morale.ensure', return_value=NS(value=60)):
            meetings = VF.build_exit_meetings(self.s, self.L, 'GB')
        self.assertEqual(len(meetings), 1)
        before = copy.deepcopy(meetings[0]['context'])
        self.p.age += 3
        self.p.contract = Contract(5, [20] * 5, signed=2030)
        self.p.ratings = {key: 50. for key in self.p.ratings}
        again = VF.build_exit_meetings(self.s, self.L, 'GB')
        self.assertEqual(again[0]['context'], before)
        loaded = League.load(self.L.save())
        self.assertEqual(loaded.exit_meetings['2029'][0]['context'], before)
        row = VF._exit_row(loaded, 'GB', loaded.exit_meetings['2029'][0], 2029, past=True)
        self.assertEqual((row['age'], row['years'], row['apy'], row['ovr']),
                         (before['age'], 2, 10.0, before['ovr']))

    def test_old_meeting_does_not_invent_age_contract_or_overall(self):
        self.p.career[2026] = {'pos': 'QB'}
        self.L.exit_meetings = {'2026': [self.meeting()]}
        before = copy.deepcopy(self.L.exit_meetings)
        row = VF.exit_interviews(self.s, self.L, 'GB', year=2026)['meetings'][0]
        self.assertEqual(row['pos'], 'QB')
        for key in ('age', 'ovr', 'years', 'apy', 'no'): self.assertIsNone(row[key])
        self.assertIn('not recorded', row['context_note'])
        self.assertEqual(self.L.exit_meetings, before)

    def test_old_current_year_meeting_labels_live_details_explicitly(self):
        row = VF._exit_row(self.L, 'GB', self.meeting(), 2029, past=False)
        self.assertEqual(row['years'], 2)
        self.assertIn('Current player details', row['context_note'])
        self.assertIn('not recorded', row['context_note'])

    def test_historical_snapshot_survives_missing_player_or_changed_position(self):
        context = VF._exit_context(self.L, 'GB', self.p)
        mt = self.meeting(context)
        self.p.pos = 'K'
        self.assertEqual(VF._exit_row(self.L, 'GB', mt, 2029, True)['pos'], 'QB')
        del self.L.players[self.p.pid]
        self.assertEqual(VF._exit_row(self.L, 'GB', mt, 2029, True)['name'], 'Test Quarterback')

    def test_cpu_meeting_slot_keeps_its_own_history(self):
        self.L.exit_meetings = {'2026': [self.meeting()], 'MIN-2026': [dict(self.meeting(), quote='MIN dialogue')]}
        view = VF.exit_interviews(self.s, self.L, 'MIN', year=2026)
        self.assertEqual(view['meetings'][0]['quote'], 'MIN dialogue')

    def test_meeting_grade_uses_users_evaluation_even_for_other_club(self):
        with patch('gm_engine.scheme_fit', side_effect=lambda ratings, pos, team:
                   2.0 if team.abbr == 'GB' else -3.0):
            row = VF._exit_context(self.L, 'MIN', self.p)
        self.assertEqual(row['ovr'], round(self.p.ovr + 2.0))

    def test_historical_unanswered_stays_unanswered_and_read_only(self):
        mt = self.meeting(); mt.update(answer=None, said=None)
        self.L.exit_meetings = {'2026': [mt]}
        view = VF.exit_interviews(self.s, self.L, 'GB', year=2026)
        self.assertTrue(view['past'])
        self.assertEqual(view['open'], 0)
        self.assertIsNone(view['meetings'][0]['answer'])


if __name__ == '__main__': unittest.main()

"""One elimination email per week, including legacy saved notices."""
import unittest
from unittest.mock import patch
import inbox as IB
import league_notes as LN
from league import League, Team


def fixture():
    league = League(2026)
    league.set_phase('regular'); league.week = 15; league.user_team = 'GB'
    for abbr, division in [('GB', 'United North'), ('MIN', 'United North'), ('DEN', 'Continental West')]:
        team = Team(abbr, division, division.split()[0]); team.league = league
        team.record = [3, 10, 1]; league.teams[abbr] = team
    return league


def advance(league, eliminated):
    flags = {a: dict(division=False, playoffs=False, bye=False, eliminated=a in eliminated)
             for a in league.teams}
    with patch.object(LN, 'clinch_status', return_value=flags):
        LN.standings(league, league.week)


def legacy(league, team, status='unread'):
    message = IB.post(league, 'result' if team == 'GB' else 'league',
        ('You' if team == 'GB' else team) + ' are eliminated from playoff contention',
        f'{team}: are eliminated from playoff contention. Record: 3–11.', sender='league',
        payload=dict(link='league:standings'))
    message['status'] = status
    return message


class EliminationDigestTests(unittest.TestCase):
    def test_one_weekly_email_across_conferences_including_user(self):
        league = fixture(); advance(league, {'GB', 'MIN', 'DEN'})
        self.assertEqual(len(league.inbox), 1)
        message = league.inbox[0]
        self.assertEqual(message['kind'], 'result')
        self.assertIn('3 teams', message['body'])
        rows = message['payload']['mail_sections'][0]['rows']
        self.assertEqual(len(rows), 3)
        self.assertTrue(any('your team' in row[0]['text'] for row in rows))
        self.assertTrue(all(row[1]['text'] == '3–10–1' for row in rows))

    def test_later_results_same_week_update_one_email(self):
        league = fixture(); advance(league, {'MIN'})
        first = league.inbox[0]; first['status'] = 'open'; identity = first['id']
        advance(league, {'MIN', 'DEN'})
        self.assertEqual(len(league.inbox), 1)
        self.assertEqual(first['id'], identity)
        self.assertEqual(first['status'], 'unread')
        self.assertEqual(len(first['payload']['eliminated']), 2)
        advance(league, {'MIN', 'DEN'})
        self.assertEqual(len(first['payload']['eliminated']), 2)

    def test_next_week_only_new_eliminations(self):
        league = fixture(); advance(league, {'MIN'})
        league.week += 1; advance(league, {'MIN', 'DEN'})
        self.assertEqual(len(league.inbox), 2)
        self.assertEqual([r['team'] for r in league.inbox[-1]['payload']['eliminated']], ['DEN'])

    def test_deleted_digest_stays_deleted_after_save_reload(self):
        league = fixture(); advance(league, {'MIN', 'DEN'}); league.inbox.clear()
        league = League.load(league.save()); advance(league, {'MIN', 'DEN'})
        self.assertEqual(league.inbox, [])

    def test_reconcile_combines_legacy_and_preserves_dates_records_unread(self):
        league = fixture()
        first = legacy(league, 'MIN', 'open'); identity = first['id']
        legacy(league, 'GB')
        other = IB.news(league, 'DEN clinch a playoff spot', 'A separate clinch notice.',
                        payload=dict(link='league:standings'))
        league.week = 16; legacy(league, 'DEN', 'open')
        league.year = 2027; league.week = 1
        IB.reconcile(league)
        self.assertEqual(len(league.inbox), 3)
        self.assertIn(other, league.inbox)
        self.assertEqual((first['id'], first['year'], first['week'], first['status']),
                         (identity, 2026, 15, 'unread'))
        self.assertTrue(all(r['record'] == '3–11' for r in first['payload']['eliminated']))
        snapshot = league.save(); IB.reconcile(league)
        self.assertEqual(league.save(), snapshot)

    def test_legacy_combines_with_existing_weekly_digest(self):
        league = fixture(); advance(league, {'MIN'}); identity = league.inbox[0]['id']
        legacy(league, 'DEN'); LN.combine_saved_eliminations(league)
        self.assertEqual(len(league.inbox), 1)
        self.assertEqual(league.inbox[0]['id'], identity)
        self.assertEqual(len(league.inbox[0]['payload']['eliminated']), 2)

    def test_read_legacy_mail_stays_read_and_is_not_reposted(self):
        league = fixture(); legacy(league, 'MIN', 'open'); legacy(league, 'DEN', 'open')
        LN.combine_saved_eliminations(league)
        self.assertEqual(league.inbox[0]['status'], 'open')
        advance(league, {'MIN', 'DEN'})
        self.assertEqual(len(league.inbox), 1)
        self.assertEqual(league.inbox[0]['status'], 'open')


if __name__ == '__main__':
    unittest.main()

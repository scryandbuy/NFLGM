"""Weekly clinch summaries, later upgrades, and saved per-team notices."""
import copy
import unittest
from unittest.mock import patch
import inbox as IB
import inbox_digest as ID
import league_notes as LN
from league import League
from test_elimination_digest import fixture
import test_standings_clinches as standings_tests


def advance(league, clinches):
    flags = {a: dict(division='div' in clinches.get(a, ()),
                    playoffs='po' in clinches.get(a, ()),
                    bye='bye' in clinches.get(a, ()), eliminated=False)
             for a in league.teams}
    before = {m['id'] for m in getattr(league, 'inbox', [])}
    with patch.object(LN, 'clinch_status', return_value=flags):
        LN.standings(league, league.week)
    ID.consolidate(league, before)


def legacy(league, team, notices='clinch a playoff spot', status='open'):
    m = IB.post(league, 'result' if team == league.user_team else 'league',
        ('You' if team == league.user_team else team) + ' ' + notices.split('; ')[0],
        f'{team}: {notices}. Record: 10–4–1.', sender='league', payload=dict(link='league:standings'))
    m['status'] = status
    return m


class ClinchDigestTests(unittest.TestCase):
    def test_both_conferences_user_and_multiple_honors_in_one_email(self):
        L = fixture()
        advance(L, {'GB': ('po', 'div', 'bye'), 'MIN': ('po',), 'DEN': ('po', 'div')})
        self.assertEqual(len(L.inbox), 1)
        m = L.inbox[0]
        self.assertEqual(m['kind'], 'result')
        self.assertEqual(len(m['payload']['clinched']), 3)
        rows = m['payload']['mail_sections'][0]['rows']
        gb = next(r for r in rows if 'your team' in r[0]['text'])
        self.assertEqual(gb[1]['text'], '3–10–1')
        self.assertEqual(gb[2]['text'], 'Playoff spot · United North title · No. 1 seed and first-round bye')

    def test_same_week_updates_existing_team_and_preserves_identity(self):
        L = fixture(); advance(L, {'GB': ('po',)})
        m = L.inbox[0]; identity = m['id']; m['status'] = 'open'
        advance(L, {'GB': ('po', 'div', 'bye'), 'DEN': ('po',)})
        self.assertEqual(len(L.inbox), 1)
        self.assertEqual(m['id'], identity); self.assertEqual(m['status'], 'unread')
        self.assertEqual(len(m['payload']['clinched']), 2)
        snapshot = L.save(); advance(L, {'GB': ('po', 'div', 'bye'), 'DEN': ('po',)})
        self.assertEqual(L.save(), snapshot)

    def test_later_week_contains_only_new_honors(self):
        L = fixture(); advance(L, {'GB': ('po',)})
        L.week += 1; advance(L, {'GB': ('po', 'div')})
        self.assertEqual(len(L.inbox), 2)
        self.assertEqual(L.inbox[-1]['payload']['clinched'][0]['clinches'], ['div'])

    def test_deleted_digest_does_not_reappear_after_load(self):
        L = fixture(); advance(L, {'GB': ('po',), 'DEN': ('po',)})
        L.inbox.clear(); L = League.load(L.save()); IB.reconcile(L)
        advance(L, {'GB': ('po',), 'DEN': ('po',)})
        self.assertEqual(L.inbox, [])

    def test_legacy_rows_merge_honors_preserve_dates_records_and_unread(self):
        L = fixture()
        first = legacy(L, 'GB'); identity = first['id']
        legacy(L, 'GB', "clinch the United North; clinch the United's 1 seed and a bye", 'unread')
        legacy(L, 'DEN')
        L.week = 16; legacy(L, 'MIN')
        L.year = 2027; L.week = 15; legacy(L, 'DEN')
        L.week = 1; IB.reconcile(L)
        self.assertEqual(len(L.inbox), 3)
        self.assertEqual((first['id'], first['year'], first['week'], first['status']),
                         (identity, 2026, 15, 'unread'))
        rows = first['payload']['clinched']
        self.assertEqual(len(rows), 2)
        self.assertEqual(next(r for r in rows if r['team'] == 'GB')['clinches'], ['po', 'div', 'bye'])
        self.assertTrue(all(r['record'] == '10–4–1' for r in rows))
        snapshot = L.save(); IB.reconcile(L); self.assertEqual(L.save(), snapshot)

    def test_legacy_combines_with_existing_digest_and_keeps_read_state(self):
        L = fixture(); advance(L, {'GB': ('po',)})
        first = L.inbox[0]; first['status'] = 'open'; identity = first['id']
        legacy(L, 'GB', 'clinch the United North'); legacy(L, 'DEN')
        IB.reconcile(L)
        self.assertEqual(len(L.inbox), 1)
        self.assertEqual((first['id'], first['status']), (identity, 'open'))
        advance(L, {'GB': ('po', 'div'), 'DEN': ('po',)})
        self.assertEqual(len(L.inbox), 1)
        self.assertEqual(first['status'], 'open')

    def test_unrelated_or_unrecognized_mail_untouched(self):
        L = fixture()
        legacy(L, 'MIN')
        other = IB.news(L, 'Playoff preview', 'GB clinch scenarios for next week.', payload=dict(link='league:standings'))
        LN.combine_saved_clinches(L)
        self.assertIn(other, L.inbox); self.assertEqual(len(L.inbox), 2)

    def test_completed_season_produces_one_clinch_and_one_elimination_digest(self):
        L = standings_tests.ClinchTests().completed(); L.user_team = next(iter(L.teams))
        LN.standings(L, 18)
        clinches = [m for m in L.inbox if (m.get('payload') or {}).get('clinched')]
        eliminations = [m for m in L.inbox if (m.get('payload') or {}).get('eliminated')]
        self.assertEqual(len(clinches), 1); self.assertEqual(len(eliminations), 1)
        self.assertEqual(len(clinches[0]['payload']['clinched']), 14)
        self.assertEqual(len(eliminations[0]['payload']['eliminated']), 18)
        snapshot = copy.deepcopy(L.inbox); LN.standings(L, 18); self.assertEqual(snapshot, L.inbox)


if __name__ == '__main__': unittest.main()

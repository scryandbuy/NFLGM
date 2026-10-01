"""Conference renaming preserves team membership, calendars and old franchises."""
import copy
import json
from collections import Counter
from pathlib import Path
import unittest

import competition_names as CN
import postseason
import schedule
from season import StandingsView
from session import Session


class CompetitionNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = Session.new('GB', seed=41)
        cls.snapshot = json.loads(cls.session.save())

    def test_new_franchise_conferences_and_divisions(self):
        teams = self.session.L.teams
        self.assertEqual(Counter(t.conf for t in teams.values()), {'Continental': 16, 'United': 16})
        self.assertEqual(teams['GB'].division, 'United North')
        self.assertEqual(teams['KC'].division, 'Continental West')
        self.assertEqual(set(Counter(t.division for t in teams.values()).values()), {4})
        self.assertEqual({t.division.split()[1] for t in teams.values()}, {'North','South','East','West'})
        seeds = StandingsView(self.session.L).seeds()
        self.assertEqual(set(seeds), {'Continental', 'United'})
        self.assertTrue(all(len(teams) == 7 for teams in seeds.values()))

    def test_future_schedule_rotations_keep_all_games_and_membership(self):
        div = {a:t.division for a,t in self.session.L.teams.items()}
        rank = {}
        for d in schedule.DIVS:
            rank.update({a:i+1 for i,a in enumerate(sorted(a for a,v in div.items() if v == d))})
        # One whole combined rotation, plus the user's distant-save horizon.
        for year in (*range(2026, 2038), 2066):
            with self.subTest(year=year):
                games = schedule.build_matchups(year, div, rank)
                self.assertEqual(len(games), 272)
                self.assertEqual(set(Counter(team for h,a,k in games for team in (h,a)).values()), {17})
                division_games = Counter(team for h,a,k in games if div[h] == div[a] for team in (h,a))
                self.assertEqual(set(division_games.values()), {6})

    def legacy_snapshot(self):
        raw = json.dumps(self.snapshot).replace('Continental', 'AFC').replace('United', 'NFC')
        old = json.loads(raw); old.pop('competition_names_version', None)
        old['_post_live'] = dict(seeds={'AFC':['KC','BUF'], 'NFC':['GB','MIN']},
            alive={'AFC':{'1':'KC','2':'BUF'}, 'NFC':{'1':'GB','2':'MIN'}},
            games=[['CONF','NFC','GB','MIN',28,21]], conf_champs={}, round_idx=2)
        old['inbox'].append(dict(id='legacy-final', subject='Super Bowl preview',
            body='NFC champion meets AFC champion in the Super Bowl.', payload={}))
        old['history']['2025'] = dict(standings=dict(conferences=[{'conf':'NFC'}, {'conf':'AFC'}]),
            headline='Super Bowl MVP', seeds={'NFC':['GB'], 'AFC':['KC']})
        old['_gamedays']['legacy'] = {'header':'AFC at NFC · Super Bowl'}
        return old

    def test_legacy_session_migrates_live_bracket_history_messages_and_caches(self):
        old = self.legacy_snapshot()
        restored = Session.load(json.dumps(old))
        self.assertEqual(restored.L.teams['GB'].conf, 'United')
        self.assertEqual(set(restored.post_live.seeds), {'Continental', 'United'})
        self.assertEqual(set(restored.post_live.alive), {'Continental', 'United'})
        self.assertEqual(restored.post_live.games[0][1], 'United')
        self.assertEqual({c for c,h,a in restored.post_live.matchups('CONF')}, {'Continental', 'United'})
        self.assertEqual(restored.gamedays['legacy']['header'], 'Continental at United · Championship Game')
        message = next(m for m in restored.L.inbox if m['id'] == 'legacy-final')
        self.assertEqual(message['subject'], 'Championship Game preview')
        self.assertIn('United champion meets Continental champion', message['body'])
        self.assertEqual(restored.L.history['2025']['headline'], 'Championship Game MVP')
        self.assertEqual(set(restored.L.players), set(old['players']))
        self.assertEqual(restored.rng.bit_generator.state, old['_rng_state'])
        saved = restored.save()
        self.assertIsNone(CN._LEGACY.search(saved))
        again = Session.load(saved)
        self.assertEqual(again.post_live.to_dict(), restored.post_live.to_dict())
        self.assertEqual(again.L.teams['GB'].division, 'United North')

    def test_direct_league_load_and_migration_are_nonmutating(self):
        from league import League
        old = self.legacy_snapshot(); original = copy.deepcopy(old)
        loaded = League.load(old)
        self.assertEqual(loaded.teams['KC'].conf, 'Continental')
        self.assertEqual(old, original)
        renamed = CN.migrate_save(old)
        self.assertIs(CN.migrate_save(renamed), renamed)
        self.assertEqual(renamed['_rng_state'], old['_rng_state'])

    def test_round_and_award_codes_stay_compatible_with_new_labels(self):
        self.assertEqual(postseason.Postseason.ROUND_NAMES['SB'], 'Championship Game')
        data = CN.migrate_save({'awards': {'sb_mvp':'P1234'}, 'round':'SB',
                                'label':'SB MVP', 'text':'SUPER BOWL; AFC North; NFC South'})
        self.assertEqual(data['awards'], {'sb_mvp':'P1234'})
        self.assertEqual(data['round'], 'SB')
        self.assertEqual(data['label'], 'Championship Game MVP')
        self.assertEqual(data['text'], 'Championship Game; Continental North; United South')

    def test_shipped_sources_and_data_have_no_old_visible_names(self):
        for path in [*Path('.').glob('*.py'), Path('docs/app.js'), Path('schedule_2026.csv'), *Path('ui').glob('*.html')]:
            if path.name.startswith('test_') or path.name == 'competition_names.py': continue
            with self.subTest(path=str(path)):
                self.assertIsNone(CN._LEGACY.search(path.read_text(encoding='utf-8')))


if __name__ == '__main__':
    unittest.main()

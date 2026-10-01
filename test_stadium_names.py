"""Venue labels stay generic across live pages, postseason and saved prose."""
import copy
import json
from pathlib import Path
import unittest

import competition_names as CN
import postseason
import stadium_names as SN
import views
from session import Session


class StadiumNamesTests(unittest.TestCase):
    def test_every_team_and_championship_host_uses_shared_generic_name(self):
        self.assertEqual(len(SN.STADIUM), 32)
        self.assertIs(views.STADIUM, SN.STADIUM)
        for team, name in views.CLUB_NAME.items():
            self.assertEqual(SN.STADIUM[team], name + ' Stadium')
        for year in range(2026, 2056):
            venue = postseason.sb_venue(None, year=year)
            self.assertEqual(venue['stadium'], SN.STADIUM[venue['abbr']])
        self.assertEqual(SN.STADIUM['LAC'], 'California Stadium')
        self.assertEqual(SN.STADIUM['NYJ'], 'New Jersey Stadium')

    def test_all_legacy_aliases_migrate_case_insensitively_and_idempotently(self):
        for old, team in SN.LEGACY_VENUES.items():
            with self.subTest(old=old):
                for text in (old, old.upper(), 'Next game at ' + old + '.'):
                    converted = SN.rename_venues(text)
                    self.assertIn(SN.STADIUM[team], converted)
                    self.assertIsNone(SN._PATTERN.search(converted))
                    self.assertEqual(SN.rename_venues(converted), converted)

    def test_shared_legacy_venues_honor_home_context(self):
        old = {'competition_names_version': 1, 'games': [
            {'home': 'LAC', 'venue': 'SoFi Stadium'},
            {'home_abbr': 'LA', 'venue': 'SoFi Stadium'},
            {'home': 'NYJ', 'venue': 'MetLife Stadium'},
            {'home': 'NYG', 'venue': 'MetLife Stadium'}],
            'message': 'Week 2 at New Jersey, MetLife Stadium'}
        original = copy.deepcopy(old)
        new = CN.migrate_save(old)
        self.assertEqual(old, original)
        self.assertEqual([g['venue'] for g in new['games']], [
            'California Stadium', 'Los Angeles Stadium', 'New Jersey Stadium', 'New York Stadium'])
        self.assertIn('New Jersey Stadium', new['message'])
        self.assertIs(CN.migrate_save(new), new)

    def test_old_session_reports_caches_and_history_upgrade_without_rng_changes(self):
        s = Session.new('GB', seed=41)
        d = json.loads(s.save())
        d['competition_names_version'] = 1
        d['inbox'].append({'id': 'old-venue', 'subject': 'At Lambeau Field',
                           'body': 'Then a trip to Arrowhead Stadium', 'payload': {}})
        d['history']['2025'] = {'venue': 'Caesars Superdome'}
        d['_gamedays']['cached'] = {'home': 'NYJ', 'header': 'At MetLife Stadium'}
        loaded = Session.load(json.dumps(d))
        self.assertEqual(loaded.rng.bit_generator.state, d['_rng_state'])
        self.assertEqual(set(loaded.L.players), set(d['players']))
        self.assertEqual(loaded.gamedays['cached']['header'], 'At New Jersey Stadium')
        self.assertEqual(loaded.L.history['2025']['venue'], 'New Orleans Stadium')
        saved = loaded.save()
        self.assertIsNone(SN._PATTERN.search(saved))
        self.assertEqual(json.loads(saved)['competition_names_version'], CN.VERSION)
        self.assertEqual(Session.load(saved).save(), saved)

    def test_no_legacy_venues_in_production_sources_except_migration_aliases(self):
        paths = [*Path('.').glob('*.py'), *Path('ui').glob('*.html'),
                 *Path('docs').glob('*.js'), *Path('docs').glob('*.html'),
                 *Path('.').glob('*.csv'), *Path('.').glob('*.json')]
        for path in paths:
            if path.name.startswith('test_') or path.name == 'stadium_names.py':
                continue
            with self.subTest(path=str(path)):
                self.assertIsNone(SN._PATTERN.search(path.read_text(encoding='utf-8-sig')))


if __name__ == '__main__':
    unittest.main()

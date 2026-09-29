import csv
import unittest
from pathlib import Path

from views import CLUB_NAME, club


ROOT = Path(__file__).resolve().parent


class LocationOnlyTeams(unittest.TestCase):
    def test_all_clubs_have_unique_location_labels(self):
        self.assertEqual(len(CLUB_NAME), 32)
        self.assertEqual(len(set(CLUB_NAME.values())), 32)
        self.assertEqual(len({club(abbr)['display_abbr'] for abbr in CLUB_NAME}), 32)
        for abbr, name in CLUB_NAME.items():
            self.assertEqual(club(abbr)['name'], name)
            self.assertEqual(club(abbr)['nick'], name.upper())
        for abbr, label, code in (
            ('LAC', 'California', 'CA'), ('LA', 'Los Angeles', 'LA'),
            ('NYG', 'New York', 'NY'), ('NYJ', 'New Jersey', 'NJ'),
        ):
            self.assertEqual((club(abbr)['name'], club(abbr)['display_abbr']), (label, code))

    def test_shipped_roster_labels_use_locations(self):
        locations = set(CLUB_NAME.values())
        for filename in ('league_seed_2026.csv', 'free_agent_pool.csv'):
            with (ROOT / filename).open(encoding='utf-8', newline='') as file:
                for row in csv.DictReader(file):
                    for field in ('team_name', 'team_short', 'draft_team'):
                        if field in row and row[field]:
                            self.assertIn(row[field], locations, (filename, field, row[field]))


if __name__ == '__main__':
    unittest.main()

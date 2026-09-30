"""Cosmetic home states: persistence, legacy bios, coverage, and UI payloads."""
import collections
import csv
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from league import League, Player
import player_background as PB
import scouting


class HomeStateTests(unittest.TestCase):
    def player(self, pid='legacy-p', school='Example University'):
        p = Player(pid, 'Alex Example', 'QB', 22, {'throw_power_rating': 80},
                   potential=88, draft_year=2027)
        p.college = school
        p.conference = 'SEC'
        return p

    def test_assignment_is_stable_across_names_teams_and_years(self):
        p = self.player()
        state = PB.home_state(p)
        p.name = 'New Name'; p.team = 'GB'; p.age = 40
        self.assertEqual(PB.home_state(p), state)
        self.assertEqual(PB.state_for(p.pid), state)
        self.assertEqual(PB.home_state(SimpleNamespace(pid=p.pid)), state)

    def test_all_fifty_states_and_weighting_in_forty_direct_class_draws(self):
        # ID-only draws, no seasons or simulation RNG involved.
        counts = collections.Counter(PB.state_for(f'N{year}QB{i:03d}')
                                     for year in range(2027, 2067) for i in range(482))
        self.assertEqual(set(counts), PB.STATES)
        self.assertEqual(len(PB.STATES), 50)
        for state in ('Texas', 'Florida', 'California'):
            self.assertGreater(counts[state], counts['Alaska'] * 10)

    def test_saved_state_survives_reload_even_if_different_from_default(self):
        p = self.player(); p.home_state = 'Alaska'; p.college = 'Alaska'
        L = League(); L.players[p.pid] = p
        for _ in range(3):
            L = League.load(L.save())
        self.assertEqual(L.players[p.pid].home_state, 'Alaska')

    def test_legacy_school_migration_preserves_all_gameplay_fields(self):
        p = self.player(); before = p.to_dict(); before.pop('home_state')
        after = Player.from_dict(before).to_dict()
        self.assertEqual(after.pop('home_state'), PB.state_for(p.pid))
        self.assertEqual(after.pop('college'), PB.state_for(p.pid))
        before.pop('college')
        self.assertEqual(before, after)
        self.assertTrue(scouting._power(Player.from_dict(before)))

    def test_state_named_school_is_still_randomized_and_missing_bio_stays_ineligible(self):
        for school in ('Texas', 'California', None, ''):
            p = self.player(school=school); data = p.to_dict(); data.pop('home_state')
            loaded = Player.from_dict(data)
            self.assertEqual(loaded.home_state, PB.state_for(p.pid))
            self.assertEqual(bool(loaded.college), bool(school))

    def test_legacy_news_and_inbox_migrate_without_rewriting_team_names(self):
        p = self.player(school='Michigan'); L = League(); L.players[p.pid] = p
        L.spring_news = [dict(pid=p.pid, college='Michigan', text='Alex Example (QB, Michigan) rises.')]
        L.inbox = [dict(id=1, body='Alex Example (QB, Michigan) was drafted. Michigan remains in this unrelated text.', payload={})]
        d = L.to_dict(); d['players'][p.pid].pop('home_state')
        loaded = League.load(d)
        state = PB.state_for(p.pid)
        self.assertEqual(loaded.spring_news[0]['home_state'], state)
        self.assertNotIn('college', loaded.spring_news[0])
        self.assertEqual(loaded.spring_news[0]['text'], f'Alex Example (QB, {state}) rises.')
        self.assertEqual(loaded.inbox[0]['body'], f'Alex Example (QB, {state}) was drafted. Michigan remains in this unrelated text.')
        self.assertEqual(d['spring_news'][0]['college'], 'Michigan')  # input not mutated
        self.assertEqual(json.loads(loaded.save())['players'][p.pid]['home_state'], state)

    def test_source_bios_are_states_and_duplicate_records_agree(self):
        by_name = {}
        for filename in ('league_seed_2026.csv', 'free_agent_pool.csv', 'rosters_2026.csv',
                         'player_valuations_2026.csv', 'cfb27_ratings.csv'):
            with Path(filename).open(encoding='utf-8', newline='') as f:
                for r in csv.DictReader(f):
                    state = r['home_state']
                    self.assertIn(state, PB.STATES)
                    if r.get('college'):
                        self.assertEqual(r['college'], state)
                    if filename == 'cfb27_ratings.csv':
                        self.assertEqual(r['team'], state)
                    else:
                        if r['full_name'] in by_name:
                            self.assertEqual(state, by_name[r['full_name']])
                        by_name[r['full_name']] = state

    def test_prospect_payload_uses_state_without_conference_name(self):
        import views_draft
        from unittest.mock import patch
        p = self.player(); L = League(); L.players[p.pid] = p
        L.scouting = {'GB': {p.pid: dict(ovr=75, pot_lo=80, pot_hi=90)}}
        L.consensus = {p.pid: dict(ovr=76, rank=20)}
        with patch.object(scouting, 'scheme_fit_view', return_value=0):
            row = views_draft._prospect(L, 'GB', p)
        self.assertEqual(row['home_state'], p.home_state)
        self.assertNotIn('college', row)
        self.assertNotIn('conference', row)


if __name__ == '__main__':
    unittest.main()

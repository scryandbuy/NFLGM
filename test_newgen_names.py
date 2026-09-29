"""Long-run naming safeguards without simulating seasons."""
import hashlib
import unittest
from unittest.mock import patch

import numpy as np
import newgens as NG
from league import League, Player


def player(pid, name, year=2026, retired=False):
    p = Player(pid, name, 'HB', 25, {'speed_rating': 70}, potential=85,
               draft_year=year, entry_year=year)
    p.retired = retired
    return p


class NewgenNameTests(unittest.TestCase):
    def allocator(self, league, year, first=None, last=None, blocked=()):
        catalog = (first or ['Mike', 'Alex'], last or ['Smith', 'Rivera'], set(blocked))
        with patch.object(NG, '_name_catalog', return_value=catalog):
            return NG.NameAllocator(league, year)

    def test_current_player_blocks_name_even_after_cooldown(self):
        L = League(2045); L.players['p'] = player('p', 'Mike Smith', 2026)
        self.assertFalse(self.allocator(L, 2045).available('Mike Smith'))
        L.players['p'].retired = True
        self.assertTrue(self.allocator(L, 2045).available('Mike Smith'))

    def test_repeat_allowed_after_fifteen_years_but_not_before(self):
        L = League(); self.allocator(L, 2030).reserve('Mike Smith', 'first')
        self.assertFalse(self.allocator(L, 2044).available('Mike Smith'))
        self.assertTrue(self.allocator(L, 2045).available('Mike Smith'))

    def test_at_most_two_uses_in_rolling_forty_years(self):
        L = League(); self.allocator(L, 2030).reserve('Mike Smith', 'first')
        self.allocator(L, 2045).reserve('Mike Smith', 'second')
        self.assertFalse(self.allocator(L, 2060).available('Mike Smith'))
        self.assertFalse(self.allocator(L, 2069).available('Mike Smith'))
        self.assertTrue(self.allocator(L, 2070).available('Mike Smith'))

    def test_new_class_reserves_each_name_before_player_is_created(self):
        L = League(); allocator = self.allocator(L, 2030)
        rng = np.random.default_rng(2)
        names = [allocator.draw(rng, str(i)) for i in range(4)]
        self.assertEqual(len(set(names)), 4)
        self.assertFalse(L.players)
        with self.assertRaisesRegex(RuntimeError, 'No eligible'):
            allocator.draw(rng, 'exhausted')

    def test_case_spacing_accents_and_punctuation_cannot_bypass_checks(self):
        L = League(); L.players['p'] = player('p', "José O'Neal")
        self.assertFalse(self.allocator(L, 2050).available('JOSE O NEAL'))
        blocked = hashlib.sha256(NG.normalize_name('Mike Smith').encode()).hexdigest()
        self.assertFalse(self.allocator(L, 2050, blocked=[blocked]).available('Mike-Smith'))

    def test_history_survives_removed_players_and_repeated_save_reload(self):
        L = League(); L.players['p'] = player('p', 'Mike Smith', 2030, retired=True)
        self.allocator(L, 2040)
        del L.players['p']
        for _ in range(3):
            L = League.load(L.save())
        self.assertEqual(L.player_name_history['mikesmith'], {'p': 2030})
        self.assertFalse(self.allocator(L, 2044).available('Mike Smith'))
        self.assertTrue(self.allocator(L, 2045).available('Mike Smith'))

    def test_legacy_save_reconstructs_player_history_without_renaming(self):
        L = League(); L.players['p'] = player('p', 'Mike Smith', 2030, retired=True)
        data = L.to_dict(); data.pop('player_name_history'); data.pop('newgen_name_cursor')
        resumed = League.load(data)
        self.assertEqual(resumed.players['p'].name, 'Mike Smith')
        self.assertEqual(resumed.player_name_history['mikesmith'], {'p': 2030})
        self.assertFalse(self.allocator(resumed, 2044).available('Mike Smith'))

    def test_name_history_does_not_double_count_each_year_or_load(self):
        L = League(); L.players['p'] = player('p', 'Mike Smith', 2030, retired=True)
        for year in (2031, 2032, 2033):
            self.allocator(L, year); L = League.load(L.save())
        self.assertEqual(len(L.player_name_history['mikesmith']), 1)

    def test_save_reload_preserves_fallback_order_and_rng_stream(self):
        L = League(); allocator = self.allocator(L, 2030)
        # Fill the weighted draw's pair to force the deterministic fallback.
        class FixedRng:
            def integers(self, n): return 0
        allocator.draw(FixedRng(), 'first')
        allocator.draw(FixedRng(), 'second')
        resumed = League.load(L.save())
        a = allocator.draw(FixedRng(), 'third')
        b = self.allocator(resumed, 2030).draw(FixedRng(), 'third')
        self.assertEqual(a, b)
        self.assertEqual(L.newgen_name_cursor, resumed.newgen_name_cursor)
        rng = np.random.default_rng(13); control = np.random.default_rng(13)
        self.allocator(League(), 2030).draw(rng, 'first')
        control.integers(2); control.integers(2)
        self.assertEqual(rng.bit_generator.state, control.bit_generator.state)

    def test_real_catalog_excludes_original_and_renamed_seed_names(self):
        import csv
        allocator = NG.NameAllocator(League(), 2050)
        self.assertGreater(allocator.capacity, 1_000_000)
        for filename in ('cfb27_ratings.csv', 'league_seed_2026.csv', 'free_agent_pool.csv'):
            with open(filename, encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
            for row in rows[::max(1, len(rows)//20)]:
                name = row.get('full_name') or row['first_name']+' '+row['last_name']
                self.assertFalse(allocator.available(name), (filename, name))
        self.assertFalse(allocator.available('Jordan Love'))

    def test_twenty_five_thousand_names_without_running_any_seasons(self):
        L = League(); allocator = NG.NameAllocator(L, 2030)
        rng = np.random.default_rng(71)
        names = [allocator.draw(rng, f'probe-{i}') for i in range(25000)]
        self.assertEqual(len({NG.normalize_name(n) for n in names}), 25000)
        self.assertEqual(len(L.player_name_history), 25000)
        resumed = League.load(L.save())
        self.assertEqual(resumed.player_name_history, L.player_name_history)
        self.assertEqual(resumed.newgen_name_cursor, L.newgen_name_cursor)

    def test_real_class_builder_registers_names_and_persists_them(self):
        L = League()
        players = NG.build(L, np.random.default_rng(93), 2028)
        self.assertGreater(len(players), 400)
        self.assertEqual(len({NG.normalize_name(p.name) for p in players}), len(players))
        for p in players:
            self.assertEqual(L.player_name_history[NG.normalize_name(p.name)][p.pid], 2028)
        resumed = League.load(L.save())
        self.assertEqual(resumed.player_name_history, L.player_name_history)
        self.assertEqual([p.name for p in resumed.next_class], [p.name for p in players])


if __name__ == '__main__':
    unittest.main()

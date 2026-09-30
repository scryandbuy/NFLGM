import copy
import unittest
from types import SimpleNamespace as NS
import player_roles as R


class FreeAgentRoleTests(unittest.TestCase):
    def test_edge_switches_front_without_becoming_coverage_or_interior_player(self):
        p = NS(pos='REDG', name='Micah Parsons', ratings={'finesse_moves_rating': 96})
        before = copy.deepcopy(p.__dict__)
        self.assertEqual(R.fa_position(p, NS(gm=NS(def_front='3-4'))), 'ROLB')
        self.assertEqual(set(R.fa_positions(p, '3-4')), {'LOLB', 'ROLB'})
        self.assertEqual(R.fa_position(p, '4-3'), 'REDG')
        self.assertEqual(p.__dict__, before)

    def test_interior_and_offball_roles_are_separate(self):
        self.assertEqual(set(R.fa_positions({'pos': 'DT'}, '3-4')), {'LE', 'NT', 'RE'})
        for pos in ('MIKE', 'WILL', 'SAM'):
            self.assertEqual(set(R.fa_positions({'pos': pos}, '3-4')), {'LILB', 'RILB'})
        self.assertEqual(R.fa_positions({'pos': 'MIKE'}, '4-3'), ('MLB',))

    def test_group_payload_and_multiple_front_follow_coach_chart(self):
        for box, expected in ((.7, 'NT'), (.3, 'DT')):
            filters = R.fa_position_filters({'gm': {'def_front': 'multiple', 'box': box}})
            self.assertEqual([g['group'] for g in filters], ['OL', 'DL', 'LB', 'DB'])
            self.assertIn(expected, [p['key'] for p in filters[1]['positions']])
            self.assertEqual([p['key'] for p in filters[0]['positions']], ['LT', 'LG', 'C', 'RG', 'RT'])

    def test_other_positions_and_saved_player_dicts_are_unchanged(self):
        for pos in ('QB', 'HB', 'FB', 'WR', 'TE', 'LT', 'LG', 'C', 'RG', 'RT', 'CB', 'FS', 'SS', 'K', 'P', 'LS'):
            for front in ('4-3', '3-4'):
                self.assertEqual(R.fa_positions({'pos': pos}, front), (pos,))

    def test_interior_profile_distinguishes_nose_from_penetrating_end(self):
        nose = NS(pos='DT', pid='nose', weight=330, ratings={'strength_rating': 92})
        end = NS(pos='DT', pid='end', weight=285, ratings={'strength_rating': 75, 'finesse_moves_rating': 90})
        anchor = NS(pos='DT', pid='anchor', weight=302, ratings={
            'strength_rating': 91, 'block_shedding_rating': 90, 'power_moves_rating': 75})
        self.assertEqual(R.fa_position(nose, '3-4'), 'NT')
        self.assertEqual(R.fa_position(anchor, '3-4'), 'NT')
        self.assertIn(R.fa_position(end, '3-4'), ('LE', 'RE'))
        self.assertNotIn('NT', R.fa_positions(end, '3-4'))


if __name__ == '__main__':
    unittest.main()

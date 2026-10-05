import unittest
from types import SimpleNamespace as NS
import character_assessment as CA

class OwnedCharacterReportTests(unittest.TestCase):
    def test_actual_values_override_wrong_scouting_read_without_mutating_it(self):
        p=NS(traits={'work_ethic':82,'discipline':24},xp_spent={'_character_observations':{'GB':{'work_ethic':{'value':20,'error':20}}}})
        own=CA.owned_player_report(p)
        self.assertEqual([r['value'] for r in own],[82,24])
        self.assertEqual([r['status'] for r in own],['strength','concern'])
        for row in own:
            self.assertIsNone(row['source']); self.assertIsNone(row['confidence'])
            self.assertEqual(row['explanation'],'')
        self.assertEqual(CA.player_report(p,'GB')[0]['status'],'concern')
        self.assertEqual(CA.player_report(p,'MIN')[0]['status'],'unknown')

    def test_neutral_values_are_known_not_unassessed(self):
        p=NS(traits={'work_ethic':50,'discipline':50},xp_spent={})
        for row in CA.owned_player_report(p):
            self.assertEqual(row['value'],50)
            self.assertEqual(row['status'],'neutral')
            self.assertNotIn('assess',row['summary'].lower())

if __name__=='__main__':unittest.main()

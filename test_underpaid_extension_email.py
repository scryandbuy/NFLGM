import unittest
from types import SimpleNamespace as N
from unittest.mock import patch

from cap_engine import Contract
from test_cap_accounting import fixture, player
import extensions as EXT
import morale as MO
import negotiations as NG
import inbox as IB


class UnderpaidExtensionEmailTests(unittest.TestCase):
    def setUp(self):
        self.league = fixture()
        self.league.user_team = 'GB'
        self.league.inbox = []
        self.league.teams['GB'].gm = N(restructure_depth=.5)
        self.player = player(self.league, contract=Contract(1, [5]))
        self.player.name = 'Test Player'
        self.player.ratings = {
            'throw_power_rating': 90, 'short_accuracy_rating': 90,
            'medium_accuracy_rating': 90, 'deep_accuracy_rating': 90,
            'awareness_rating': 90,
        }
        self.thread = dict(id=1, pid=self.player.pid, team='GB', kind='extension',
                           state='open', offers=[], counter=None, due=None)
        self.offer = dict(apy=15, years=2, promises=[])

    def accept(self, quiet=True):
        with patch.object(EXT, 'terms', return_value=dict(ask=15, discount=0,
                                                        offer=15, years=2)):
            return NG._accept(self.league, self.thread, self.offer, 'agreed', quiet=quiet)

    def test_underpaid_extension_sends_one_resolution_email_and_clears_request(self):
        mood = MO.ensure(self.player)
        mood.slow = -9
        mood._contract_drag = -9
        self.player.xp_spent['_contract_concern'] = True
        self.player.xp_spent['_request'] = dict(reason='contract', year=2026, years=1)
        self.assertTrue(self.accept()['ok'])
        self.assertEqual(len(self.league.inbox), 1)
        self.assertIn('concern about being underpaid is resolved', self.league.inbox[0]['body'])
        self.assertNotIn('_contract_concern', self.player.xp_spent)
        self.assertFalse(MO.wants_out(self.player))
        self.assertEqual(mood._contract_drag, 0)

    def test_old_save_underpaid_inbox_note_is_recognized(self):
        MO.ensure(self.player).slow = -16
        IB.post(self.league, 'morale', 'Test Player is unhappy',
                'He believes he is underpaid.', payload=dict(link=f'player:{self.player.pid}'))
        self.assertTrue(self.accept()['ok'])
        self.assertEqual(len(self.league.inbox), 2)
        self.assertIn('pleased with his new salary', self.league.inbox[-1]['body'])
        MO.ensure(self.player).slow = -30  # another problem can keep morale low
        self.assertFalse(MO.pay_concern(self.league, self.player))

    def test_routine_offseason_extension_does_not_add_an_email(self):
        self.assertTrue(self.accept()['ok'])
        self.assertEqual(self.league.inbox, [])

    def test_failed_extension_keeps_the_concern(self):
        self.player.xp_spent['_contract_concern'] = True
        with patch('cap_accounting.require_room', side_effect=ValueError('No cap room')):
            result = self.accept()
        self.assertFalse(result['ok'])
        self.assertTrue(self.player.xp_spent['_contract_concern'])
        self.assertEqual(self.league.inbox, [])


if __name__ == '__main__':
    unittest.main()

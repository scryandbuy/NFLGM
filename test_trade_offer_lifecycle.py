"""Incoming trade decisions must close mail, preserve assets, and survive saves."""
import unittest
from unittest.mock import patch

import inbox
import session
import views_personnel as VP


class TradeOfferLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.initial = session.Session.new('GB', seed=91).save()

    def setUp(self):
        self.s = session.Session.load(self.initial)
        self.L = self.s.L
        self.L.inbox = []
        for t in self.L.teams.values(): t.cap.cap = 10000
        self.player = self.L.teams['GB'].roster[-1]
        self.pick = self.L.teams['DEN'].picks[-1]
        self.m = inbox.post_trade_offer(self.L, 'DEN', 'GB', [self.pick], [self.player.pid], 'Depth.', 3)
        # These synthetic offers exercise mail state, not CPU roster selection.
        guard = patch('trades.cpu_trade_check', return_value={'approved':True})
        guard.start(); self.addCleanup(guard.stop)

    def reload(self):
        self.s = session.Session.load(self.s.save()); self.L = self.s.L
        self.m = next(m for m in self.L.inbox if m['id'] == self.m['id'])

    def assert_closed(self, status):
        self.assertEqual(self.m['status'], status)
        self.assertFalse(inbox.is_decision(self.m))
        self.assertFalse(any(b.get('id') == self.m['id'] and b['kind'] == 'trade_offer' for b in self.s.blocking()))

    def test_accept_moves_assets_once_and_survives_save(self):
        self.assertTrue(self.s.trade_offer_answer(self.m['id'], 'accept')['ok'])
        self.assert_closed('accepted')
        self.assertEqual(self.player.team, 'DEN'); self.assertEqual(self.pick.owner, 'GB')
        self.assertFalse(self.s.trade_offer_answer(self.m['id'], 'accept')['ok'])
        self.reload(); self.assert_closed('accepted')
        self.assertEqual(self.L.player(self.player.pid).team, 'DEN')
        self.assertTrue(any(p.year == self.pick.year and p.round == self.pick.round and p.original == self.pick.original for p in self.L.teams['GB'].picks))

    def test_decline_closes_only_original_and_persists(self):
        other = inbox.post_trade_offer(self.L, 'DEN', 'GB', [self.pick], [self.player.pid], 'Other.', 3)
        self.assertTrue(self.s.trade_offer_answer(self.m['id'], 'decline')['ok'])
        self.assert_closed('declined'); self.assertTrue(inbox.is_decision(other))
        self.assertFalse(self.s.trade_offer_answer(self.m['id'], 'decline')['ok'])
        self.reload(); self.assert_closed('declined')
        self.assertEqual(self.L.player(self.player.pid).team, 'GB')

    def test_failed_accept_leaves_offer_and_assets_unchanged(self):
        with patch.object(self.L, 'trade', side_effect=ValueError('cap room')):
            self.assertFalse(self.s.trade_offer_answer(self.m['id'], 'accept')['ok'])
        self.assertTrue(inbox.is_decision(self.m)); self.assertEqual(self.player.team, 'GB')
        self.assertEqual(self.pick.owner, 'DEN')

    def test_counter_closes_original_and_restores_edited_typed_package(self):
        result = self.s.trade_offer_answer(self.m['id'], 'counter')
        self.assertTrue(result['ok']); self.assert_closed('countered')
        self.assertFalse(self.s.trade_offer_answer(self.m['id'], 'accept')['ok'])
        self.assertEqual(result['counter']['a'], [dict(kind='player', id=self.player.pid)])
        extra = self.L.teams['GB'].picks[-1]
        a = result['counter']['a'] + [dict(kind='pick', id=f'{extra.year}-{extra.round}-{extra.original}')]
        b = result['counter']['b']
        self.assertTrue(self.s.personnel_act('save_trade_counter', msg_id=self.m['id'], other='DEN', a_sends=a, b_sends=b)['ok'])
        self.reload(); self.assert_closed('countered')
        draft = self.s.trade_offer_answer(self.m['id'], 'counter')['counter']
        self.assertEqual(draft['a'], a); self.assertEqual(draft['b'], b)
        self.assertEqual(self.L.player(self.player.pid).team, 'GB')
        self.assertEqual(self.s.trade_offer_view(self.m['id'])['counter'], draft)
        self.assertFalse(self.s.personnel_act('save_trade_counter', msg_id=self.m['id'], other='KC', a_sends=a, b_sends=b)['ok'])

    def test_declined_outgoing_trade_has_feedback_without_new_mail(self):
        draft = self.s.trade_offer_answer(self.m['id'], 'counter')['counter']
        before = len(self.L.inbox)
        with patch.object(VP, '_evaluate', return_value=dict(verdict='fair', read='Need more.')), patch('trades.will_accept', return_value=False):
            for counter_id in (None, self.m['id']):
                r = self.s.personnel_act('propose', other='DEN', a_sends=draft['a'], b_sends=draft['b'], counter_id=counter_id)
                self.assertTrue(r['ok']); self.assertFalse(r['done'])
                self.assertEqual(r['why'], 'We are not ready to accept this offer.')
        self.assertEqual(len(self.L.inbox), before)
        self.reload(); self.assert_closed('countered')
        self.assertEqual(self.m['payload']['counter']['state'], 'declined')

    def test_accepted_counter_preserves_result_and_cannot_be_resent(self):
        draft = self.s.trade_offer_answer(self.m['id'], 'counter')['counter']
        with patch.object(VP, '_evaluate', return_value=dict(verdict='fair', read='Fair.')), patch('trades.will_accept', return_value=True):
            r = self.s.personnel_act('propose', other='DEN', a_sends=draft['a'], b_sends=draft['b'], counter_id=self.m['id'])
        self.assertTrue(r['done']); self.assertEqual(self.player.team, 'DEN')
        self.reload(); self.assert_closed('countered')
        self.assertEqual(self.m['payload']['counter']['state'], 'accepted')
        self.assertFalse(self.s.trade_offer_answer(self.m['id'], 'counter')['ok'])


if __name__ == '__main__': unittest.main()

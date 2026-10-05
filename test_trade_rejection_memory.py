import unittest
import copy
import json
from types import SimpleNamespace as NS
import trades as T

class RejectionMemory(unittest.TestCase):
    def test_empty_repeated_reads_do_not_initialize_saved_state(self):
        for fields in ({}, {'league_notes_sent':None}, {'league_notes_sent':{}},
                       {'league_notes_sent':{'unrelated':True}}):
            with self.subTest(fields=fields):
                L=NS(year=2030,inbox=[],**copy.deepcopy(fields))
                saved=json.dumps(vars(L),sort_keys=True)
                for _ in range(3):
                    self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1'],['p2']))
                self.assertEqual(json.dumps(vars(L),sort_keys=True),saved)

    def test_legacy_mail_lookup_is_read_only_and_remember_persists_it(self):
        pick=dict(pick=True,year=2031,round=2,original='PIT',selection=45)
        L=NS(year=2030,league_notes_sent={'unrelated':True},inbox=[dict(
            kind='trade_offer',status='declined',year=2030,payload=dict(
                buyer='GB',user_team='PIT',sends=['p1',pick],gets=['p2']))])
        saved=json.dumps(vars(L),sort_keys=True)
        for _ in range(3):
            self.assertTrue(T.trade_was_rejected(L,'PIT','GB',['p2'],['2031-2-PIT','p1']))
        self.assertEqual(json.dumps(vars(L),sort_keys=True),saved)
        T.remember_trade_rejection(L,'GB','MIN',['p3'],['p4'])
        L.inbox=[]
        self.assertTrue(T.trade_was_rejected(L,'GB','PIT',['p1','2031-2-PIT'],['p2']))
        self.assertTrue(L.league_notes_sent['unrelated'])

    def test_annual_roll_occurs_only_when_recording_a_new_rejection(self):
        L=NS(year=2030,inbox=[])
        T.remember_trade_rejection(L,'GB','PIT',['p1'],['p2'])
        L.year=2031
        saved=json.dumps(vars(L),sort_keys=True)
        self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1'],['p2']))
        self.assertEqual(json.dumps(vars(L),sort_keys=True),saved)
        T.remember_trade_rejection(L,'GB','PIT',['p3'],['p4'])
        self.assertEqual(L.league_notes_sent['_rejected_trade_packages']['year'],2031)
        self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1'],['p2']))
        self.assertTrue(T.trade_was_rejected(L,'GB','PIT',['p3'],['p4']))

    def test_canonical_pick_forms_and_reversed_sides_preserve_identity(self):
        L=NS(year=2030)
        pick=NS(year=2031,round=2,original='PIT',selection=45)
        T.remember_trade_rejection(L,'GB','PIT',['p1',pick],['p2'])
        saved=json.dumps(vars(L),sort_keys=True)
        for variant in (pick,'2031-2-PIT',dict(year=2031,round=2,original='PIT'),
                        dict(kind='pick',obj=pick)):
            self.assertTrue(T.trade_was_rejected(L,'PIT','GB',
                [dict(kind='player',pid='p2')],[variant,'p1']))
        self.assertFalse(T.trade_was_rejected(L,'PIT','GB',['p2'],['2032-2-PIT','p1']))
        self.assertEqual(json.dumps(vars(L),sort_keys=True),saved)

    def test_exact_identity_order_direction_and_new_year(self):
        L=NS(year=2030)
        pick=NS(year=2031,round=2,original='PIT',selection=None)
        T.remember_trade_rejection(L,'GB','PIT',['p1',pick],['p2'])
        encoded=dict(pick=True,year=2031,round=2,original='PIT',selection=45)
        self.assertTrue(T.trade_was_rejected(L,'PIT','GB',['p2'],[encoded,'p1']))
        self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1'],['p2']))
        self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1',pick],['p3']))
        self.assertFalse(T.trade_was_rejected(L,'GB','MIN',['p1',pick],['p2']))
        L.year=2031
        self.assertFalse(T.trade_was_rejected(L,'GB','PIT',['p1',pick],['p2']))

if __name__=='__main__': unittest.main()

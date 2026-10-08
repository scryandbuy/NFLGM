import copy
import unittest
from unittest.mock import patch
import inbox as IB
import inbox_digest as ID
import waivers as WV
from league import League
from test_roster_advisor import fixture, player


class WeeklyWaiverMailTests(unittest.TestCase):
    def setUp(self):
        self.L = fixture(); self.L.week = 8; self.L.inbox = []

    def entries(self, n, offset=0):
        result=[]
        for i in range(offset,offset+n):
            p=player('waived-'+str(i), 'CB', 70+i%5)
            p.name='ArDarius Washington' if i==0 else 'Prospect '+str(i)
            self.L.players[p.pid]=p; self.L.free_agents.append(p.pid)
            result.append(dict(pid=p.pid,from_team='MIN',user_notified=False,claims=[]))
        return result

    def notify(self, entries):
        with patch.object(WV,'priority',return_value=['GB','MIN']), \
             patch('valuation.pool_from_league',return_value=None), \
             patch('valuation.value_player',return_value={}), \
             patch.object(WV,'reaches_user',side_effect=lambda l,e,w,**kw: e['pid']!='blocked'):
            WV.notify_user(self.L,entries,8)

    def test_large_weekly_table_keeps_every_player_and_explicit_link(self):
        entries=self.entries(15); self.notify(entries)
        self.assertEqual(len(self.L.inbox),1)
        m=self.L.inbox[0]; rows=m['payload']['mail_sections'][0]['rows']
        self.assertEqual(len(rows),15)
        self.assertEqual(rows[0][0]['mentions'][0]['id'],'waived-0')
        self.assertEqual(m['payload']['link'],'personnel:waivers')
        self.assertFalse(IB.is_decision(m))
        self.assertTrue(all(e['user_notified'] for e in entries))
        self.notify(entries); self.assertEqual(len(self.L.inbox),1)

    def test_later_notices_merge_same_week_but_not_other_weeks_or_closed(self):
        self.notify(self.entries(2)); self.L.inbox[0]['status']='read'
        self.notify(self.entries(1,2))
        self.assertEqual(len(self.L.inbox),1)
        self.assertEqual(self.L.inbox[0]['payload']['n'],3)
        self.assertEqual(self.L.inbox[0]['status'],'unread')
        self.L.inbox[0]['status']='closed'
        self.notify(self.entries(1,3)); self.assertEqual(len(self.L.inbox),2)
        self.L.week=9
        self.notify(self.entries(1,4)); self.assertEqual(len(self.L.inbox),3)

    def test_legacy_tables_use_saved_facts_and_leave_claim_results_alone(self):
        self.entries(2)
        for i in range(2):
            IB.post(self.L,'waiver_notice','Available on waivers: Name'+str(i),
                    f'Name{i}, CB, 68 overall, age 24, 0 accrued seasons, waived by MIN. Original text.',
                    payload=dict(pid='waived-'+str(i),cap_hit=1.25,years=2,priority=1),expires_week=9)
        outcome=IB.post(self.L,'waiver_notice','Claim awarded: Someone','Won the claim')
        ID.combine_saved_waiver_availability(self.L)
        self.assertEqual(len(self.L.inbox),2); self.assertIn(outcome,self.L.inbox)
        rows=self.L.inbox[0]['payload']['mail_sections'][0]['rows']
        self.assertEqual([c['text'] for c in rows[0]],['Name0','CB','68','24','MIN','2 yr · $1.25m this season'])
        before=copy.deepcopy(self.L.inbox)
        ID.combine_saved_waiver_availability(self.L); self.assertEqual(before,self.L.inbox)
        restored=League.load(self.L.save())
        ID.combine_saved_waiver_availability(restored); self.assertEqual(restored.inbox,before)

    def test_no_email_for_priority_blocked_player_and_claim_still_works(self):
        entries=self.entries(2)
        p=self.L.players.pop('waived-1'); p.pid='blocked'; self.L.players[p.pid]=p
        entries[1]['pid']=p.pid
        self.L.waivers=entries
        self.notify(entries)
        self.assertEqual(self.L.inbox[0]['payload']['digest_pids'],['waived-0'])
        self.assertTrue(WV.user_claim(self.L,'waived-0'))
        self.assertEqual(entries[0]['claims'],['GB'])


if __name__=='__main__':unittest.main()

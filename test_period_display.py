import unittest
from types import SimpleNamespace as NS
import gameday

class PeriodDisplay(unittest.TestCase):
 def render(self, kick_clock, quarter, explicit=False):
  league=NS(week=11,player=lambda pid:None,teams={t:NS(roster=[]) for t in ('GB','LAC')})
  rows=[dict(type='kickoff',clock=kick_clock,new_yardline=78,ret=18)]
  if explicit: rows.append(dict(type='period',quarter=quarter,clock=900))
  rows.append(dict(type='incomplete',clock=900 if quarter==4 else 1800,down=1,ydstogo=10,yardline=78))
  dr=NS(log=rows,off={},start=78,yardline=78,quarter=quarter,start_quarter=quarter,clock=894,plays=1,first_downs=0,result='Punt',points=0)
  result=dict(home=0,away=0,drives=[('away',dr)])
  return gameday.capture(league,[('GB','LAC',result,NS(p={}))],'GB')['game']['drives'][0]['plays']
 def test_kickoff_precedes_quarter_announcement(self):
  rows=self.render(902,4)
  self.assertEqual([r['type'] for r in rows],['kickoff','period','incomplete'])
  self.assertEqual([r['quarter'] for r in rows],[3,4,4])
 def test_halftime_announcement_precedes_second_half_kick(self):
  self.assertEqual([r['type'] for r in self.render(1800,3)],['period','kickoff','incomplete'])
 def test_existing_marker_not_duplicated(self):
  self.assertEqual([r['type'] for r in self.render(902,4,True)],['kickoff','period','incomplete'])
if __name__=='__main__':unittest.main()

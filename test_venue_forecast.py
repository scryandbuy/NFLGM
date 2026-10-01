import unittest
from types import SimpleNamespace as N
from unittest.mock import patch
import gameplan_week as G
class VenueForecast(unittest.TestCase):
 def test_atlanta_championship_indoor_for_both_designations(self):
  for home in ('GB','NYG'):
   f=G.game_forecast(N(year=2027),home,22)
   self.assertEqual(f['text'],'Indoors');self.assertEqual(f['weather_risk'],0)
 def test_regular_playoff_uses_home(self):
  with patch.object(G,'_forecast',return_value={}) as f:
   G.game_forecast(N(year=2027),'GB',21)
   f.assert_called_once_with('GB',21)
if __name__=='__main__':unittest.main()

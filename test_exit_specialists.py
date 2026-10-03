import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
import views_frontoffice as VF

class ExitSpecialists(unittest.TestCase):
    def fixture(self):
        players = [NS(pid=pos, pos=pos, ovr=95, age=28, contract=NS(years=2)) for pos in ('K', 'P', 'WR')]
        team = NS(active=lambda: players, depth={p.pos:[p] for p in players})
        league = NS(teams={'GB':team}, year=2028, user_team='GB', player=lambda pid: next((p for p in players if p.pid==pid),None))
        return league
    def test_new_meetings_exclude_specialists_without_displacing_receiver(self):
        league=self.fixture()
        with patch('morale.wants_out',return_value=False), patch('morale.ensure',return_value=NS(value=60)):
            meetings=VF.build_exit_meetings(None,league,'GB')
        self.assertEqual([m['pid'] for m in meetings],['WR'])
    def test_saved_meetings_excluded_and_cannot_be_answered(self):
        league=self.fixture()
        league.exit_meetings={'2028':[dict(pid=p,answer=None) for p in ('K','P','WR')]}
        self.assertEqual([m['pid'] for m in VF.build_exit_meetings(None,league,'GB')],['WR'])
        for pid in ('K','P'):
            self.assertFalse(VF.exit_answer(None,league,'GB',pid,'spring')['ok'])

if __name__=='__main__': unittest.main()

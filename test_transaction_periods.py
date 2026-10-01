import unittest
from unittest.mock import patch
from test_cap_accounting import fixture
from test_regression_aging import player
from league import League
from views import transaction_period, transaction_when
from views_club import _player_history
import views_league as VL


class TransactionPeriods(unittest.TestCase):
    def test_phase_overrides_stale_week_and_playoffs_use_round_names(self):
        for phase in ('offseason', 'free_agency', 'draft'):
            self.assertEqual(transaction_when(dict(year=2027,week=22,phase=phase)), 'Offseason 2027')
        self.assertEqual(transaction_period(dict(phase='preseason',week=22)), 'Preseason')
        for week, name in ((19,'Wild Card'),(20,'Divisional Round'),(21,'Conference Championship'),(22,'Super Bowl')):
            self.assertEqual(transaction_period(dict(phase='playoffs',week=week)),name)
        self.assertEqual(transaction_when(dict(year=2026,phase='regular',week=8)), '2026 · Week 8')

    def test_existing_saved_trade_history_and_feed_use_the_saved_phase(self):
        league=fixture();p=player('trade', 'QB', 25, 'GB');league.players[p.pid]=p
        league.set_phase('offseason');league.week=22
        league.log('trade',a='GB',b='MIN',a_sends=[p.pid],b_sends=[])
        league=League.load(league.save())
        event=dict(league.transactions[-1])
        # Viewing next year's regular season must not change an old event's date.
        league.year+=1;league.set_phase('regular');league.week=3
        rows=_player_history(league,league.players[p.pid])
        self.assertEqual(rows[-1]['when'],f"Offseason {event['year']}")
        with patch.object(VL,'rail',return_value={}):
            feed=VL.transactions(None,league,'GB')
        self.assertEqual(feed['rows'][0]['period'],'Offseason')
        self.assertEqual(league.transactions[-1],event)


if __name__=='__main__':unittest.main()

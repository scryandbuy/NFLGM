import unittest
from types import SimpleNamespace as NS
import league_notes as notes
import advanced_stats

class ContractDigests(unittest.TestCase):
    def test_accumulates_all_players_once_and_keeps_tags_separate(self):
        players = {str(i): NS(pid=str(i), name=f'Player {i}', pos='K' if i==1 else 'WR', ovr=70) for i in range(3)}
        league = NS(year=2030, week=0, phase='offseason', user_team='GB',
                    players=players, player=lambda pid: players.get(pid), inbox=[], teams={}, transactions=[])
        league.transactions = [dict(kind='extension',team='GB',pid='0',years=3,apy=4),
                               dict(kind='franchise_tag',team='PIT',pid='2',price=18)]
        notes.transactions(league,0,pre_fa=True)
        self.assertEqual(len(league.inbox),2)
        extension = next(m for m in league.inbox if m['subject'].startswith('Extensions'))
        identity = extension['id']
        league.transactions.append(dict(kind='extension',team='PIT',pid='1',years=2,apy=2))
        notes.transactions(league,0,pre_fa=True)
        notes.transactions(league,0,pre_fa=True)
        self.assertEqual(len(league.inbox),2)
        self.assertEqual(extension['id'],identity)
        self.assertEqual(len(extension['payload']['mail_sections'][0]['rows']),2)
        self.assertEqual(advanced_stats.DEF_EPA_NOTE,'')

if __name__ == '__main__': unittest.main()

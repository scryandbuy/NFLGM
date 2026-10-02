import copy
import json
import unittest

import league as LG
import rush_stats_migration as M


class CompactGameStats(unittest.TestCase):
    def test_preserves_negative_fractional_values_metadata_and_evidence(self):
        line=dict(pass_att=0,epa=-.37,sacks=.5,team='GB',pos='QB',
                  def_plays=0,flag=False,unknown=None)
        compact=LG.compact_game_line(line)
        self.assertNotIn('pass_att',compact)
        for key in ('epa','sacks','team','pos','def_plays','flag','unknown'):
            self.assertEqual(compact[key],line[key])
        self.assertEqual(M.pair(compact),M.pair(line))

    def test_record_stats_does_not_accumulate_zero_fields(self):
        league=LG.League(2027)
        player=LG.Player('p','Test Player','QB',25,{},team='GB')
        league.players['p']=player
        key='2027-1-GB-MIN'
        league.record_stats(2027,'p',dict(pass_att=1,pass_cmp=0,epa=-.25),game=key)
        league.record_stats(2027,'p',dict(pass_att=0,epa=.25),game=key)
        self.assertEqual(league.game_stats[key]['p'],dict(team='GB',pos='QB',pass_att=1))
        self.assertEqual(league.stats[2027]['p']['pass_cmp'],0)
        self.assertEqual(player.career[2027]['pass_cmp'],0)

    def test_legacy_load_compacts_and_roundtrip_keeps_every_game_and_player(self):
        league=LG.League(2027)
        data=league.to_dict()
        games={'2027-1-GB-MIN':{'p':dict(pass_att=4,pass_cmp=0,epa=-.25,team='GB'),
                                'empty':dict(snaps=0)},
               '2027-22-GB-KC':{'p':dict(pass_td=2,ints=0,team='GB')}}
        data['game_stats']=copy.deepcopy(games)
        restored=LG.League.load(json.dumps(data))
        again=LG.League.load(restored.save())
        self.assertEqual(restored.game_stats,again.game_stats)
        self.assertEqual(set(games),set(again.game_stats))
        for game,book in games.items():
            self.assertEqual(set(book),set(again.game_stats[game]))
            for pid,line in book.items():
                for key,value in line.items():
                    self.assertEqual(again.game_stats[game][pid].get(key,0),value)
        self.assertNotIn('pass_cmp',again.game_stats['2027-1-GB-MIN']['p'])


if __name__=='__main__': unittest.main()

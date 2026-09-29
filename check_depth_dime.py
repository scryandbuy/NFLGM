import rosters, defense_roles as DR, game
import numpy as np
teams=rosters.load_league()
for abbr,roster in teams.items():
 for front in ('4-3','3-4'):
  rows=DR.assign(roster['depth'],front,'Dime')
  players=[r['player']['pid'] for r in rows if r['player'] is not None]
  assert len(players)==len(set(players))==11,(abbr,front,players)
  assert DR.counts(front,'Dime')['db']==6
  unit,pos=game.field_units(roster,game.TeamState(roster),np.random.default_rng(8),False,'dime',front)
  assert len(pos)==11,(abbr,front,len(pos))
print('Dime: 64 team/front combinations passed, six DBs and 11 unique players')

"""Generate real view fixtures from a copied save for test_broadcast_gameday.cjs.

Usage: python audit_broadcast_gameday.py path/to/save.json [output-directory]
The supplied file is read only. One exhibition is played in memory; no save is written.
"""
import copy
import json
from pathlib import Path
import sys

from session import Session
from season import SeasonRunner
import views


def main():
    s = Session.load(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    out = Path(sys.argv[2] if len(sys.argv) > 2 else 'outputs/broadcast')
    out.mkdir(parents=True, exist_ok=True)
    def write(name, view):
        (out / (name + '.json')).write_text(json.dumps(view), encoding='utf-8')
    saved = next((gd for gd in reversed(list(s.gamedays.values())) if gd.get('game')), None)
    if saved is None: raise ValueError('Use a save containing a completed user game.')
    write('legacy', views.gameday(s, s.L, s.user_team, gd=saved))
    s.L.phase = 'regular'
    r = s.runner or SeasonRunner(s.L, s.rng)
    s.runner = r
    r.last_games = []
    home = s.user_team
    away = 'DET' if home != 'DET' else 'GB'
    week = min(18, max(1, int(s.L.week)))
    # Postseason recording avoids invoking the regular week's transaction/advance flow.
    r.open_live(home, away, week, playoffs=True)
    s.played = True
    for _ in range(8): r.live_step('play')
    before_rng = copy.deepcopy(s.rng.bit_generator.state)
    before_book = copy.deepcopy(r.live['book'].p)
    write('live', s.gameday_view())
    assert before_rng == s.rng.bit_generator.state and before_book == r.live['book'].p
    r.live_step('finish')
    assert r.live['halftime_open']
    write('halftime', s.gameday_view())
    while not r.live['done']:
        r.live_step('resume' if r.live['halftime_open'] else 'finish')
    s._capture_gameday(week)
    write('final', views.gameday(s, s.L, s.user_team, gd=s.gameday))
    print('Read-only view preserved RNG and StatBook. Final participant rows:')
    print({k:len(rows) for k,rows in s.gameday['game']['box'].items()})


if __name__ == '__main__': main()

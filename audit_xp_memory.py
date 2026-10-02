"""Exercise an existing save without changing it; write isolated audit artifacts."""
import copy
import gc
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

import league as LG
from session import Session


def stats_digest(games):
    digest=hashlib.sha256()
    for key,book in sorted(games.items()):
        digest.update(key.encode())
        for pid,line in sorted(book.items()):
            digest.update(pid.encode())
            digest.update(json.dumps(LG.compact_game_line(line),sort_keys=True).encode())
    return digest.hexdigest()


def xp_state(session):
    return {p.pid:dict(xp=p.xp,ratings=p.ratings,potential=p.potential,xp_spent=p.xp_spent)
            for p in session.L.teams[session.user_team].roster}


def main(source,destination):
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    with patch.object(LG,'compact_game_stats',lambda games:games):
        session=Session.load(Path(source).read_text(encoding='utf-8'))
    before=len(session.save().encode())
    digest=stats_digest(session.L.game_stats)
    counters=(len(session.L.game_stats),sum(len(book) for book in session.L.game_stats.values()))
    rng=copy.deepcopy(session.rng.bit_generator.state)
    LG.compact_game_stats(session.L.game_stats)
    after=len(session.save().encode())
    assert digest==stats_digest(session.L.game_stats)
    assert rng==session.rng.bit_generator.state
    (out/'progression.json').write_text(json.dumps(session.progression()),encoding='utf-8')
    (out/'browser-save.json').write_text(session.save(),encoding='utf-8')
    before_xp=copy.deepcopy(xp_state(session))
    players=list(session.L.teams[session.user_team].active())
    for i in range(100):
        result=session.club_act('spend_by_read',pid=players[i%len(players)].pid)
        assert result['ok']
        session.progression()
        saved=session.save()
        if i%20==19:
            expected=copy.deepcopy(xp_state(session))
            session=Session.load(saved)
            assert expected==xp_state(session),'XP or ratings changed on reload'
            assert digest==stats_digest(session.L.game_stats),'historical stats changed'
            assert rng==session.rng.bit_generator.state,'save/spend changed simulation RNG'
            gc.collect()
    changed=sum(before_xp[pid]!=state for pid,state in xp_state(session).items())
    assert changed>0,'fixture must exercise actual purchases'
    report=dict(before_bytes=before,after_bytes=after,reduction_pct=round(100*(before-after)/before,1),
                games=counters[0],player_game_lines=counters[1],spend_clicks=100,reloads=5,
                players_changed=changed,stats_preserved=True,xp_preserved=True,rng_preserved=True)
    (out/'engine-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__': main(*sys.argv[1:])

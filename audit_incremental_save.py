"""Read-only source save audit; mutations occur in an isolated loaded session."""
import copy
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

from session import Session
from test_incremental_save import apply, assemble


def run(source, destination):
    out=Path(destination);out.mkdir(parents=True,exist_ok=True)
    s=Session.load(Path(source).read_text(encoding='utf-8-sig'))
    store={};patches=[];checks=[]
    def capture(label, initial=False):
        before_rng=copy.deepcopy(s.rng.bit_generator.state)
        start=time.perf_counter();payload=s.save_incremental();elapsed=time.perf_counter()-start
        snap=json.loads(payload);apply(store,snap)
        expected=json.loads(s.save())
        assert assemble(store)==expected,label
        assert s.rng.bit_generator.state==before_rng,label
        checks.append(dict(action=label,seconds=elapsed,bytes=len(payload.encode()),records=len(snap['puts'])))
        print(checks[-1],flush=True)
        if initial:(out/'checkpoint.json').write_text(payload,encoding='utf-8')
        else:patches.append(snap)
    capture('initial checkpoint',True)
    eligible=next(r for r in s.progression()['rows'] if r['can_buy'])
    result=s.club_act('spend_by_read',pid=eligible['pid']);assert result['ok'] and result['spent']>0,result
    capture('Spend XP')
    result=s.club_act('auto_xp',pid=eligible['pid'],on=True);assert result['ok']
    capture('Auto XP toggle')
    s.plan_act('reopen')
    result=s.plan_act('set_depth',short=.4,medium=.4,deep=.2);assert result['ok'],result
    capture('Game plan changes')
    # An explicit pick swap exercises multi-team records, transactions and provenance.
    a,b=s.L.teams[s.user_team],next(t for t in s.L.teams.values() if t.abbr!=s.user_team)
    pa=next(p for p in a.picks if not p.used_on)
    pb=next(p for p in b.picks if not p.used_on)
    s.L.trade(a.abbr,b.abbr,[pa],[pb]);capture('Pick trade')
    from cap_engine import Contract
    p=next(s.L.player(pid) for pid in s.L.free_agents if s.L.player(pid) is not None)
    # Persistence check of the signing/release commit paths, not a CPU choice audit.
    s.L.sign(p.pid,a.abbr,Contract(1,[1.5]));capture('Signing')
    s.L.release(p.pid);capture('Release / waiver accounting')
    # Full export and reconstructed browser save go through exactly the same loader.
    text=json.dumps(assemble(store),separators=(',',':'))
    restored=Session.load(text);full_restored=Session.load(s.save())
    assert json.loads(restored.save())==json.loads(full_restored.save())
    assert restored.rng.bit_generator.state==full_restored.rng.bit_generator.state
    restored.resume_incremental(dict(epoch=s._browser_snapshot.epoch,
        revision=s._browser_snapshot.revision,marker=s._browser_snapshot.marker,
        hashes={key:value['hash'] for key,value in store.items()}))
    resumed_delta=restored.save_incremental()
    (out/'deltas.json').write_text(json.dumps(patches,separators=(',',':')),encoding='utf-8')
    full=s.save()
    (out/'expected.json').write_text(json.dumps(dict(sha256=hashlib.sha256(full.encode()).hexdigest(),
                                                   bytes=len(full.encode()))),encoding='utf-8')
    result=dict(checks=checks,full_export_reload_equal=True,rng_unchanged_by_saves=True,
                source_untouched=True,fingerprint_count=len(s._browser_snapshot.hashes),
                resumed_delta_bytes=len(resumed_delta.encode()),
                resumed_changed_records=len(json.loads(resumed_delta)['puts']))
    (out/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':run(*sys.argv[1:])

"""Measure the loaded franchise graph, not save encoding's temporary allocations."""
import gc
import hashlib
import json
import sys
import time
from pathlib import Path


def retained_size(root):
    seen = set()
    def walk(obj):
        key = id(obj)
        if key in seen: return 0
        seen.add(key)
        total = sys.getsizeof(obj)
        if isinstance(obj, dict):
            total += sum(walk(k) + walk(v) for k, v in obj.items())
        elif isinstance(obj, (list, tuple, set, frozenset)):
            total += sum(walk(v) for v in obj)
        elif hasattr(obj, '__dict__') and not isinstance(obj, type):
            total += walk(vars(obj))
        for cls in type(obj).__mro__:
            for name in getattr(cls, '__slots__', ()):
                if name not in ('__dict__', '__weakref__') and hasattr(obj, name):
                    total += walk(getattr(obj, name))
        return total
    return walk(root)


def run(source, destination, mode):
    import shared_json
    from session import Session
    from league import _session_json_default
    if mode == 'baseline':
        shared_json.load = json.load
        shared_json.loads = json.loads
    started = time.perf_counter()
    session = Session.load_file(source)
    seconds = time.perf_counter() - started
    gc.collect()
    retained = retained_size(session)
    digest = hashlib.sha256()
    for piece in json.JSONEncoder(default=_session_json_default, separators=(',', ':')).iterencode(session._save_data()):
        digest.update(piece.encode())
    report = dict(mode=mode, native_load_seconds=round(seconds, 3),
                  native_retained_session_mib=round(retained / 1048576, 3),
                  portable_export_sha256=digest.hexdigest(),
                  players=len(session.L.players), transactions=len(session.L.transactions),
                  archives=len(session.gamedays),
                  rng_sha256=hashlib.sha256(json.dumps(session.rng.bit_generator.state,
                      sort_keys=True).encode()).hexdigest())
    Path(destination).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__': run(*sys.argv[1:])

"""Read-only comparison of old/new exports on a supplied franchise copy."""
import gc
import gzip
import hashlib
import json
import sys
import threading
import time
from pathlib import Path
import ctypes
from session import Session


def resident_bytes():
    class Counters(ctypes.Structure):
        _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [
            (name, ctypes.c_size_t) for name in ('peak', 'working', 'paged_peak',
                'paged', 'nonpaged_peak', 'nonpaged', 'pagefile', 'pagefile_peak')]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
    if not query(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.working


def run(source, mode, destination):
    s = Session.load_file(source)
    gc.collect()
    baseline = resident_bytes()
    samples = [baseline]
    stopped = threading.Event()
    def sample():
        while not stopped.wait(.01):
            samples.append(resident_bytes())
    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    start = time.perf_counter()
    rng = json.dumps(s.rng.bit_generator.state, sort_keys=True)
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    if mode == 'old':
        text = s.save()
        samples.append(resident_bytes())
        size = len(text)
    else:
        s.export_file(output.with_suffix('.json.gz'))
        samples.append(resident_bytes())
        size = output.with_suffix('.json.gz').stat().st_size
    seconds = time.perf_counter() - start
    stopped.set()
    thread.join()
    h = hashlib.sha256()
    if mode == 'old':
        for i in range(0, len(text), 262144):
            h.update(text[i:i+262144].encode())
    else:
        with gzip.open(output.with_suffix('.json.gz'), 'rb') as f:
            while block := f.read(262144): h.update(block)
    assert json.dumps(s.rng.bit_generator.state, sort_keys=True) == rng
    report = dict(mode=mode, bytes=size, seconds=round(seconds, 2),
                  native_baseline_mib=round(baseline/1048576, 2),
                  native_export_peak_extra_mib=round((max(samples)-baseline)/1048576, 2),
                  uncompressed_sha256=h.hexdigest(), rng_unchanged=True)
    output.write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__': run(*sys.argv[1:])

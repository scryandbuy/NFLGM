"""Read-only measurement of checkpoint allocations using an exported franchise."""
import hashlib
import json
import sys
import time
import tracemalloc
from pathlib import Path
from incremental_save import Snapshot


def run(source, destination, mode):
    out = Path(destination)
    out.mkdir(parents=True, exist_ok=True)
    with open(source, encoding='utf-8-sig') as stream:
        data = json.load(stream)
    writer = Snapshot({'epoch':'memory-audit'})
    tracemalloc.start()
    start = time.perf_counter()
    chunks = total = largest = 0
    with (out / (mode + '.ndjson')).open('w', encoding='utf-8', newline='\n') as stream:
        transfer = ([writer.prepare(data, str)] if mode == 'legacy'
                    else writer.prepare_batches(data, str))
        for payload in transfer:
            stream.write(payload + '\n')
            chunks += 1
            total += len(payload)
            largest = max(largest, len(payload))
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    report = dict(mode=mode, seconds=round(time.perf_counter()-start, 2),
                  checkpoint_chars=total, batches=chunks, largest_batch_chars=largest,
                  encoder_peak_mib=round(peak/1048576, 2), records=len(writer.hashes))
    # Verify every encoded record without retaining a second reconstructed league.
    from incremental_save import records
    expected = dict(records(data))
    with (out / (mode + '.ndjson')).open(encoding='utf-8') as stream:
        for line in stream:
            batch = json.loads(line)
            for key, record in batch['puts'].items():
                assert json.loads(record['text']) == json.loads(json.dumps(expected.pop(key)))
    assert not expected
    report['every_record_equal'] = True
    canonical = json.dumps(data, separators=(',', ':'))
    (out / 'expected.json').write_text(json.dumps(dict(
        sha256=hashlib.sha256(canonical.encode()).hexdigest(), bytes=len(canonical.encode()))))
    (out / (mode + '-report.json')).write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    run(*sys.argv[1:])

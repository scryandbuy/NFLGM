"""Lossless JSON/gzip export in transfer-sized pieces, without a full save string."""
import json
import zlib

CHUNK_BYTES = 256 * 1024


def chunks(data, default):
    encoder = json.JSONEncoder(default=default, separators=(',', ':'))

    def fragments(value, depth=0):
        # Split the snapshot into records; use the fast C encoder inside each
        # record rather than walking every rating/statistic in Python.
        if depth < 2 and isinstance(value, dict):
            yield '{'
            for index, (key, item) in enumerate(value.items()):
                if index:
                    yield ','
                yield encoder.encode({key: None})[1:-6]
                yield ':'
                yield from fragments(item, depth + 1)
            yield '}'
        elif depth < 2 and isinstance(value, (list, tuple)):
            yield '['
            for index, item in enumerate(value):
                if index:
                    yield ','
                yield from fragments(item, depth + 1)
            yield ']'
        else:
            yield encoder.encode(value)

    compressor = zlib.compressobj(level=9, wbits=31)
    parts, size = [], 0
    for fragment in fragments(data):
        for offset in range(0, len(fragment), CHUNK_BYTES):
            part = fragment[offset:offset + CHUNK_BYTES]
            parts.append(part)
            size += len(part)
            if size >= CHUNK_BYTES:
                yield compressor.compress(''.join(parts).encode('utf-8'))
                parts, size = [], 0
    if parts:
        yield compressor.compress(''.join(parts).encode('utf-8'))
    yield compressor.flush()

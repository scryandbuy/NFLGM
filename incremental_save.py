"""Lossless, bounded-memory browser snapshots. Never unpickle external data.

Fingerprint each record using the fast binary encoder, then JSON-encode only
changed records. The cache holds digests, not a second copy of the franchise.
Every record is checked: persistence does not depend on an action allowlist.
"""
import hashlib
import json
import pickle
import uuid

LIST_BLOCK = 64
FORMAT = 1


def record_id(parts):
    return json.dumps(parts, ensure_ascii=False, separators=(',', ':'))


def json_key(key):
    if isinstance(key, str): return key
    if key is None: return 'null'
    if key is True: return 'true'
    if key is False: return 'false'
    return str(key)


def records(data):
    roots = []
    for name, value in data.items():
        if isinstance(value, dict):
            keys = [json_key(k) for k in value]
            roots.append([name, 'dict', keys])
            for key, item in value.items():
                yield record_id([name, json_key(key)]), item
        elif isinstance(value, (list, tuple)):
            blocks = (len(value) + LIST_BLOCK - 1) // LIST_BLOCK
            roots.append([name, 'list', blocks])
            for i in range(blocks):
                yield record_id([name, i]), value[i * LIST_BLOCK:(i + 1) * LIST_BLOCK]
        else:
            roots.append([name, 'value', None])
            yield record_id([name]), value
    yield '@roots', roots


class Snapshot:
    def __init__(self, resume=None):
        resume = resume or {}
        self.epoch = resume.get('epoch') or uuid.uuid4().hex
        self.revision = int(resume.get('revision', 0))
        self.hashes = dict(resume.get('hashes') or {})
        self.marker = resume.get('marker')

    def prepare(self, data, default):
        marker = json.dumps([data.get('year'), data.get('_stop')], separators=(',', ':'))
        reset = not self.revision or marker != self.marker
        puts, hashes = {}, {}
        for key, value in records(data):
            # This is an internal fingerprint only; persisted data stays JSON.
            digest = hashlib.sha256(pickle.dumps(value, protocol=4)).hexdigest()
            hashes[key] = digest
            if reset or self.hashes.get(key) != digest:
                puts[key] = dict(hash=digest, text=json.dumps(value, default=default, separators=(',', ':')))
        revision = self.revision + 1
        result = dict(format=FORMAT, epoch=self.epoch, base=self.revision,
                      revision=revision, marker=marker, reset=reset, puts=puts,
                      deletes=[] if reset else sorted(self.hashes.keys() - hashes.keys()))
        # Finish encoding before advancing the baseline, including encoder errors.
        encoded = json.dumps(result, separators=(',', ':'))
        self.hashes, self.revision, self.marker = hashes, revision, marker
        return encoded

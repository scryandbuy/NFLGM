"""Portable exports retain every field and resume using the existing loader."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from league import League
from session import Session


class CompressedExportTests(unittest.TestCase):
    def test_stream_preserves_json_key_types_unicode_and_large_records(self):
        import portable_export
        import league
        data = {'mixed': {1: 'é🏈', None: True, False: [np.int64(3), -0.0]},
                'records': [{str(i): 'history' * 100} for i in range(2000)],
                'long_note': 'a' * (1024 * 1024), 'empty': [{}, []]}
        encoded = b''.join(portable_export.chunks(data, league._session_json_default))
        self.assertEqual(gzip.decompress(encoded).decode(),
                         json.dumps(data, default=league._session_json_default, separators=(',', ':')))

    def test_export_never_constructs_a_compressed_temporary_file(self):
        s = Session(League(2033), np.random.default_rng(71), None)
        with patch('builtins.open', side_effect=AssertionError('temporary file')):
            blocks = list(s.export_chunks())
        self.assertEqual(gzip.decompress(b''.join(blocks)).decode(), s.save())

    def test_exact_save_bytes_and_rng(self):
        s = Session(League(2033), np.random.default_rng(71), None)
        s.gameday = {'name': 'René 🏈', 'flag': np.bool_(True),
                     'stats': np.array([17, 24]), 'archive': ['history' * 100] * 1000}
        expected = s.save()
        before = json.dumps(s.rng.bit_generator.state)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'save.json.gz'
            # Export must never fall back to the huge-string API.
            with patch.object(s, 'save', side_effect=AssertionError('whole save string')):
                s.export_file(target)
            with gzip.open(target, 'rt', encoding='utf-8') as f:
                actual = f.read()
            self.assertEqual(actual, expected)
            self.assertLess(target.stat().st_size, len(expected) / 5)
            restored = Session.load(actual)
        self.assertEqual(json.dumps(s.rng.bit_generator.state), before)
        self.assertEqual(restored.gameday, json.loads(expected)['_gameday'])
        self.assertEqual(restored.rng.bit_generator.state, s.rng.bit_generator.state)

    def test_snapshot_includes_live_pending_and_archives(self):
        s = Session(League(2033), np.random.default_rng(81), None)
        from types import SimpleNamespace
        s.runner = SimpleNamespace(save_state=lambda: {'week': 7}, live={
            'done': False, 'home': 'GB', 'away': 'DET', 'week': 7,
            'start': {'seed': 23}, 'actions': ['next_play']})
        s.gamedays = {'2032:6': {'score': [23, 21]}}
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'save.gz'
            s.export_file(target)
            with gzip.open(target, 'rt') as f:
                self.assertEqual(f.read(), s.save())


if __name__ == '__main__':
    unittest.main()

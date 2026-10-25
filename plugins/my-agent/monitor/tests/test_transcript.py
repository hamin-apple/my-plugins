import builtins
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from monitor import transcript
from monitor.transcript import TranscriptCache
from tests.fixtures.build_fixtures import CLAUDE, EXPECTED_MAIN

D = datetime(2026, 10, 24)
WINDOWS = [(D.replace(hour=15, minute=30), D.replace(hour=15, minute=31), 1),
           (D.replace(hour=15, minute=56), None, 5)]


class TranscriptTest(unittest.TestCase):
    def test_window_sum(self):
        got = TranscriptCache(CLAUDE).usage_by_window('s-cli', WINDOWS)
        self.assertEqual(got[1], {'claude-opus-5-5': EXPECTED_MAIN[1]})
        self.assertEqual(got[5], {'claude-opus-5-5': EXPECTED_MAIN[5]})

    def test_dedupe_message_id(self):
        got = TranscriptCache(CLAUDE).usage_by_window('s-cli', [(D.replace(hour=15, minute=56), D.replace(hour=16), 'x')])
        self.assertEqual(got['x']['claude-opus-5-5']['output_tokens'], 1000)

    def test_missing_session_returns_empty(self):
        self.assertEqual(TranscriptCache(CLAUDE).usage_by_window('nope', WINDOWS), {})
        self.assertEqual(TranscriptCache(Path('/nonexistent')).usage_by_window('s-cli', WINDOWS), {})

    def test_incremental_read(self):
        with tempfile.TemporaryDirectory() as d:
            shutil.copytree(CLAUDE, Path(d) / 'c')
            p = Path(d) / 'c/-x-claude-sessions/s-cli.jsonl'
            tc = TranscriptCache(Path(d) / 'c')
            tc.usage_by_window('s-cli', WINDOWS)
            size = p.stat().st_size
            with p.open('a', encoding='utf-8') as f:
                f.write(json.dumps({'type': 'assistant', 'timestamp': '2026-10-24T07:05:00.000Z',
                                    'message': {'id': 'm9', 'model': 'claude-opus-5-5',
                                                'usage': {'input_tokens': 1, 'output_tokens': 1}}}) + '\n')
            seeks, real_open = [], builtins.open

            def spy_open(*a, **kw):
                fh = real_open(*a, **kw)
                orig = fh.seek
                fh.seek = lambda off, *r: (seeks.append(off), orig(off, *r))[1]
                return fh
            with mock.patch.object(transcript, 'open', spy_open, create=True):
                got = tc.usage_by_window('s-cli', [(D, None, 'all')])
            self.assertEqual(seeks, [size])
            self.assertEqual(got['all']['claude-opus-5-5']['input_tokens'], 8000 + 20000 + 5000 + 10000 + 1)


if __name__ == '__main__':
    unittest.main()

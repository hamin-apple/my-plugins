"""The monitor reads Codex session records beside Claude transcripts and labels the Models table's main row with the
real main-model family (D9)."""
import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from monitor.registry import Registry
from tests.fixtures.build_fixtures import PROJECTS
from tests.test_taskview import write_transcript

import ma_usage

INDEX = Path(__file__).resolve().parent.parent / 'web' / 'index.html'
SESSION = '019a0000-0000-7000-8000-0000000000c1'
MODEL = 'gpt-6-luna'


def write_codex(root, task_dir, session=SESSION, model=MODEL):
    """A Codex record with one response 30 s after each step line of the task."""
    enter = ma_usage.step_enter(ma_usage.read_log(task_dir / 'run-log.md'))
    first = enter[0][0].astimezone().isoformat()
    rows = [{'timestamp': first, 'type': 'session_meta', 'payload': {'id': session, 'session_id': session}},
            {'timestamp': first, 'type': 'turn_context', 'payload': {'turn_id': 't1', 'model': model}}]
    for i, (ts, _n, _rev, _sess) in enumerate(enter):
        stamp = (ts + timedelta(seconds=30)).astimezone().isoformat()
        rows.append({'timestamp': stamp, 'type': 'token_usage_record', 'payload': {
            'thread_id': session, 'turn_id': 't1',
            'usage': {'input_tokens': 1000 * (i + 1), 'cached_input_tokens': 0, 'cache_write_input_tokens': 0,
                      'output_tokens': 10}}})
    path = Path(root) / '2026' / '10' / '23' / f'rollout-2026-10-23T00-00-00-{session}.jsonl'
    path.parent.mkdir(parents=True)
    path.write_text('\n'.join(json.dumps(r) for r in rows) + '\n', encoding='utf-8')


class CodexSessionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ('obsidian-notes', 'claude-sessions'):
            shutil.copytree(PROJECTS / name, self.root / name)
        self.claude_dir = self.root / 'obsidian-notes/docs/agent/261023-hooks-notify-note'
        self.codex_dir = self.root / 'claude-sessions/docs/agent/261024-cli-json-output'
        log = self.codex_dir / 'run-log.md'
        log.write_text(re.sub(r'session=\S+', f'session={SESSION}', log.read_text(encoding='utf-8')), encoding='utf-8')
        self.claude, self.codex = self.root / 'claude', self.root / 'codex'
        write_transcript(self.claude, self.claude_dir, ma_usage)
        patch = mock.patch.dict(os.environ, {'MA_TASK_DIR': 'docs/agent', 'MA_CODEX_SESSIONS': str(self.codex),
                                             'MA_TASKS_DIR': str(self.root / 'data')})
        patch.start()
        self.addCleanup(patch.stop)

    def registry(self, names=('obsidian-notes', 'claude-sessions')):
        p = self.root / 'projects.txt'
        p.write_text(''.join(f'{self.root / n}\n' for n in names), encoding='utf-8')
        return Registry(p, claude_root=self.claude)

    def task(self, r, tid):
        [t] = [t for t in r.list_tasks() if t['id'] == tid]
        return r.get_task(t['key'])

    def test_both_tools_appear_with_the_same_fields(self):
        write_codex(self.codex, self.codex_dir)
        r = self.registry()
        self.assertEqual({t['id'] for t in r.list_tasks()}, {'261023-hooks-notify-note', '261024-cli-json-output'})
        a, b = self.task(r, '261023-hooks-notify-note'), self.task(r, '261024-cli-json-output')
        self.assertEqual(set(a), set(b))
        for t in (a, b):
            self.assertTrue(t['main'] or t['mainR'])   # main-session usage found, from either tool

    def test_codex_usage_is_read_per_window(self):
        write_codex(self.codex, self.codex_dir)
        r = self.registry()
        self.task(r, '261024-cli-json-output')
        enter = ma_usage.step_enter(ma_usage.read_log(self.codex_dir / 'run-log.md'))
        wins = ma_usage.windows(enter, None, False)
        got = r.tcache.usage_by_window(SESSION, [(s, e, k) for ss, s, e, k in wins])
        self.assertEqual(sum(m[MODEL]['input_tokens'] for m in got.values()), sum(1000 * (i + 1) for i in range(len(enter))))

    def test_main_family_per_host(self):
        write_codex(self.codex, self.codex_dir)
        r = self.registry()
        self.assertEqual(self.task(r, '261024-cli-json-output')['mainFamily'], MODEL)
        self.assertEqual(self.task(r, '261023-hooks-notify-note')['mainFamily'], 'opus')

    def test_codex_family_from_snapshot_without_record(self):
        write_codex(self.codex, self.codex_dir)
        intake = self.codex_dir / 'intake.md'
        intake.write_text(intake.read_text(encoding='utf-8').replace('Status: active', 'Status: done'), encoding='utf-8')
        code, _ = ma_usage.write_snapshot(self.codex_dir, self.claude, datetime(2026, 10, 25))
        self.assertEqual(code, 0)
        shutil.rmtree(self.codex)
        self.assertEqual(self.task(self.registry(), '261024-cli-json-output')['mainFamily'], MODEL)

    def test_claude_only_data_unchanged(self):
        r = self.registry(('obsidian-notes',))
        [s] = r.list_tasks()
        t = r.get_task(s['key'])
        self.assertEqual(t['mainFamily'], 'opus')
        self.assertTrue(t['main'] or t['mainR'])

    def test_missing_codex_record_is_no_usage(self):
        t = self.task(self.registry(), '261024-cli-json-output')
        self.assertIsNone(t['main'])
        self.assertEqual(t['mainFamily'], 'opus')


class MainRowLabelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding='utf-8')

    def test_label_from_main_family(self):
        self.assertNotIn('opus · main', self.html)
        self.assertRegex(self.html, r"models\[\(t\.mainFamily \|\| 'opus'\) \+ ' · main'\]")


if __name__ == '__main__':
    unittest.main()

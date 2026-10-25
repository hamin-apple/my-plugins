"""ma_active.find_active (architecture 4.8.2 lookup order) and ma_logline.format_line (4.7.2 line format)."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from helpers import make_task, parse  # also puts lib/ on sys.path

import ma_active
import ma_logline


class FindActiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.tasks = self.root / 'agent-tasks'
        self.tasks.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_git_root(self):
        task_dir = make_task(self.root / 'repo')
        deep = self.root / 'repo' / 'src' / 'deep'
        deep.mkdir(parents=True)
        a = ma_active.find_active(str(deep), self.tasks)
        self.assertEqual(a.task, '261025-probe-task')
        self.assertEqual(a.task_dir, task_dir)
        self.assertEqual(a.log, task_dir / 'run-log.md')
        self.assertEqual((a.phase, a.session, a.started), ('1', 's-test', '2026-10-25 09:00'))

    def test_find_git_worktree_file(self):
        make_task(self.root / 'wt', git=False)
        (self.root / 'wt' / '.git').write_text('gitdir: /elsewhere/.git/worktrees/wt\n')
        self.assertEqual(ma_active.find_active(str(self.root / 'wt'), self.tasks).location, self.root / 'wt')

    def test_find_from_agent_worktree(self):
        """probe r2: an isolation:worktree agent runs in <main>/.claude/worktrees/agent-x with a .git file."""
        task_dir = make_task(self.root / 'main')
        (self.root / 'main' / '.git' / 'worktrees' / 'agent-x').mkdir(parents=True)
        wt = self.root / 'main' / '.claude' / 'worktrees' / 'agent-x'
        wt.mkdir(parents=True)
        (wt / '.git').write_text(f"gitdir: {self.root / 'main' / '.git' / 'worktrees' / 'agent-x'}\n")
        (wt / 'src').mkdir()
        a = ma_active.find_active(str(wt / 'src'), self.tasks)
        self.assertEqual(a.task_dir, task_dir)

    def test_find_non_git_location(self):
        """A location outside any git repo (e.g. ~/dev/agent-tasks) run from itself writes no index line."""
        task_dir = make_task(self.root / 'agent-tasks', git=False)
        (self.root / 'agent-tasks' / 'sub').mkdir()
        self.assertEqual(ma_active.find_active(str(self.root / 'agent-tasks'), self.tasks).task_dir, task_dir)
        self.assertEqual(ma_active.find_active(str(self.root / 'agent-tasks' / 'sub'), self.tasks).task_dir, task_dir)

    def test_git_root_without_active_does_not_climb(self):
        make_task(self.root / 'outer', git=False)
        (self.root / 'outer' / 'repo' / '.git').mkdir(parents=True)
        self.assertIsNone(ma_active.find_active(str(self.root / 'outer' / 'repo'), self.tasks))

    def test_find_via_index(self):
        make_task(self.root / 'loc', git=False)
        (self.root / 'home' / 'sub').mkdir(parents=True)
        (self.tasks / 'active-index.json').write_text(json.dumps({str(self.root / 'home'): str(self.root / 'loc')}))
        a = ma_active.find_active(str(self.root / 'home' / 'sub'), self.tasks)
        self.assertEqual(a.location, self.root / 'loc')

    def test_index_key_does_not_reach_a_repo_below_it(self):
        make_task(self.root / 'loc', git=False)
        (self.root / 'home' / 'projB' / '.git').mkdir(parents=True)
        (self.root / 'home' / 'notes').mkdir()
        (self.tasks / 'active-index.json').write_text(json.dumps({str(self.root / 'home'): str(self.root / 'loc')}))
        self.assertIsNone(ma_active.find_active(str(self.root / 'home' / 'projB'), self.tasks))
        self.assertEqual(ma_active.find_active(str(self.root / 'home' / 'notes'), self.tasks).location,
                         self.root / 'loc')
        (self.tasks / 'active-index.json').write_text(
            json.dumps({str(self.root / 'home' / 'projB'): str(self.root / 'loc')}))
        (self.root / 'home' / 'projB' / 'src').mkdir()
        self.assertEqual(ma_active.find_active(str(self.root / 'home' / 'projB' / 'src'), self.tasks).location,
                         self.root / 'loc')

    def test_find_stale_index(self):
        (self.root / 'home').mkdir()
        (self.tasks / 'active-index.json').write_text(json.dumps({str(self.root / 'home'): str(self.root / 'gone')}))
        self.assertIsNone(ma_active.find_active(str(self.root / 'home'), self.tasks))

    def test_find_none(self):
        (self.root / 'plain').mkdir()
        self.assertIsNone(ma_active.find_active(str(self.root / 'plain'), self.tasks))
        make_task(self.root / 'repo')
        (self.root / 'repo' / 'docs' / 'agent' / '.active').write_text('phase: 1\n')
        self.assertIsNone(ma_active.find_active(str(self.root / 'repo'), self.tasks))

    def test_bad_index_json_ignored(self):
        (self.root / 'plain').mkdir()
        (self.tasks / 'active-index.json').write_text('{not json')
        self.assertIsNone(ma_active.find_active(str(self.root / 'plain'), self.tasks))


class LineTest(unittest.TestCase):
    def test_roundtrip_hard_values(self):
        for q in ['npm i x', 'say "hi"', 'a\\b', "it's", 'two\nlines', '', 'plain', 'tab\there', '$HOME `x`']:
            with self.subTest(q=q):
                f = parse(ma_logline.format_line('ask', [('gate', 'G2'), ('q', q)]))
                self.assertEqual(f['q'], q.replace('\n', ' '))
                self.assertEqual(f['gate'], 'G2')

    def test_line_shape(self):
        line = ma_logline.format_line('step', [('n', 5), ('name', 'Execute'), ('rev', 0), ('session', None)],
                                      datetime(2026, 10, 25, 9, 0, 0))
        self.assertEqual(line, '2026-10-25 09:00:00 step: n=5 name=Execute rev=0 session=-')

    def test_bools(self):
        f = parse(ma_logline.format_line('call', [('background', True), ('x', False)]))
        self.assertEqual((f['background'], f['x']), ('true', 'false'))

    def test_append_and_log_error(self):
        with tempfile.TemporaryDirectory() as d:
            task_dir = make_task(d)
            a = ma_active.find_active(d, Path(d) / 'none')
            ma_logline.append(a.log, ma_logline.format_line('step', [('n', 1), ('name', 'Intake')]))
            ma_logline.log_error(a, 'subagent-log stop', ValueError('bad "x"'))
            lines = (task_dir / 'run-log.md').read_text().splitlines()
            self.assertEqual(len(lines), 2)
            f = parse(lines[1])
            self.assertEqual(f['where'], 'subagent-log stop')
            self.assertEqual(f['error'], 'ValueError: bad "x"')

    def test_log_error_never_raises(self):
        a = ma_active.Active(Path('/nonexistent'), 't', '1', 's', '', Path('/nonexistent/t'), Path('/nonexistent/t/run-log.md'))
        ma_logline.log_error(a, 'x', RuntimeError('y'))   # no exception


if __name__ == '__main__':
    unittest.main()

"""ma_data (data folder resolution) and data-dir.py: MA_TASKS_DIR > setting > ~/dev/log/my-agent, per-file overrides first."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from helpers import L4, run_script  # also puts lib/ on sys.path

import ma_data

SCRIPT = L4 / 'scripts' / 'data-dir.py'
VARS = ('MA_TASKS_DIR', 'CLAUDE_PLUGIN_OPTION_DATA_DIR', 'MA_PROJECTS_FILE', 'MA_FEEDBACK_FILE',
        'MA_GATE_REPORT_DIR', 'HOME', 'MA_TASK_DIR', 'CLAUDE_PLUGIN_OPTION_TASK_DIR')
PLACEHOLDER = '${user_config.data_dir}'


class DataDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / 'home'
        self.home.mkdir()
        self.saved = {k: os.environ.get(k) for k in VARS}
        for k in VARS:
            os.environ.pop(k, None)
        os.environ['HOME'] = str(self.home)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def test_default(self):
        self.assertEqual(ma_data.data_dir(), self.home / 'dev' / 'log' / 'my-agent')

    def test_plugin_json_default_matches_fallback(self):
        manifest = json.loads((L4.parent / '.claude-plugin' / 'plugin.json').read_text())
        default = manifest['userConfig']['data_dir']['default']
        self.assertEqual(default, '~/dev/log/my-agent')
        self.assertEqual(ma_data.data_dir(default), ma_data.data_dir())

    def test_order(self):
        a, b, c = self.root / 'a', self.root / 'b', self.root / 'c'
        os.environ['CLAUDE_PLUGIN_OPTION_DATA_DIR'] = str(c)
        self.assertEqual(ma_data.data_dir(), c)
        self.assertEqual(ma_data.data_dir(str(b)), b)
        os.environ['MA_TASKS_DIR'] = str(a)
        self.assertEqual(ma_data.data_dir(str(b)), a)

    def test_tilde_expanded(self):
        self.assertEqual(ma_data.data_dir('~/notes/agent'), self.home / 'notes/agent')
        os.environ['CLAUDE_PLUGIN_OPTION_DATA_DIR'] = '~/viaenv'
        self.assertEqual(ma_data.data_dir(), self.home / 'viaenv')

    def test_unset_values_fall_back(self):
        for value in ('', '  ', PLACEHOLDER):
            self.assertEqual(ma_data.data_dir(value), self.home / 'dev' / 'log' / 'my-agent', value)
            os.environ['CLAUDE_PLUGIN_OPTION_DATA_DIR'] = value   # hook path: no argument
            self.assertEqual(ma_data.data_dir(), self.home / 'dev' / 'log' / 'my-agent', value)

    def test_hook_path_env_only(self):
        os.environ['CLAUDE_PLUGIN_OPTION_DATA_DIR'] = '~/hook'
        self.assertEqual(ma_data.data_dir(), self.home / 'hook')

    def test_task_dir_default_and_unset_values(self):
        self.assertEqual(ma_data.task_dir(), '.my-agent')
        for value in ('', '  ', '${user_config.task_dir}'):
            self.assertEqual(ma_data.task_dir(value), '.my-agent', value)
            os.environ['CLAUDE_PLUGIN_OPTION_TASK_DIR'] = value   # hook path: no argument
            self.assertEqual(ma_data.task_dir(), '.my-agent', value)

    def test_task_dir_invalid_values_fall_back(self):
        for value in ('/x', '~/x', 'a/../b', '..', '/', '//', './', '.git', '.claude/x', '.GIT'):
            self.assertEqual(ma_data.task_dir(value), '.my-agent', value)

    def test_task_dir_normalized(self):
        for value, want in (('notes/agent/', 'notes/agent'), ('./x/', 'x'), ('docs//agent', 'docs/agent'),
                            ('Notes/Agent', 'Notes/Agent'), ('  docs/agent  ', 'docs/agent')):
            self.assertEqual(ma_data.task_dir(value), want, value)

    def test_task_dir_order(self):
        os.environ['CLAUDE_PLUGIN_OPTION_TASK_DIR'] = 'c'
        self.assertEqual(ma_data.task_dir(), 'c')
        self.assertEqual(ma_data.task_dir('b'), 'b')
        os.environ['MA_TASK_DIR'] = 'a'
        self.assertEqual(ma_data.task_dir('b'), 'a')

    def test_task_dir_invalid_argument_does_not_fall_to_the_next_source(self):
        os.environ['CLAUDE_PLUGIN_OPTION_TASK_DIR'] = 'docs/agent'
        self.assertEqual(ma_data.task_dir('/x'), '.my-agent')
        self.assertEqual(ma_data.task_dir(), 'docs/agent')

    def test_task_root(self):
        self.assertEqual(ma_data.task_root(Path('/L'), 'docs/agent'), Path('/L/docs/agent'))
        self.assertEqual(ma_data.task_root(Path('/L')), Path('/L/.my-agent'))

    def test_file_defaults_under_data_dir(self):
        d = self.root / 'd'
        self.assertEqual(ma_data.projects_file(str(d)), d / 'projects.txt')
        self.assertEqual(ma_data.feedback_file(str(d)), d / 'feedback.md')
        self.assertEqual(ma_data.report_dir(str(d)), d / 'gate-report')

    def test_file_overrides_win(self):
        d = self.root / 'd'
        os.environ['MA_PROJECTS_FILE'] = str(self.root / 'p.txt')
        os.environ['MA_FEEDBACK_FILE'] = str(self.root / 'fb.md')
        os.environ['MA_GATE_REPORT_DIR'] = str(self.root / 'rep')
        os.environ['MA_TASKS_DIR'] = str(self.root / 't')
        self.assertEqual(ma_data.projects_file(str(d)), self.root / 'p.txt')
        self.assertEqual(ma_data.feedback_file(str(d)), self.root / 'fb.md')
        self.assertEqual(ma_data.report_dir(str(d)), self.root / 'rep')

    def run_clean(self, *args, **env):
        base = {k: '' for k in VARS if k != 'HOME'}
        return run_script(SCRIPT, *args, env=dict(base, HOME=str(self.home), **env))

    def test_script_output(self):
        r = self.run_clean('--data-dir', '~/dev/agent-tasks')
        self.assertEqual((r.returncode, r.stdout), (0, f'{self.home}/dev/agent-tasks\n'))
        r = self.run_clean('--data-dir', PLACEHOLDER)
        self.assertEqual(r.stdout, f'{self.home}/dev/log/my-agent\n')
        r = self.run_clean('--data-dir', '')
        self.assertEqual(r.stdout, f'{self.home}/dev/log/my-agent\n')
        r = self.run_clean('--data-dir', '~/x', MA_TASKS_DIR='/tmp/t')
        self.assertEqual(r.stdout, '/tmp/t\n')

    def test_script_task_dir_second_line(self):
        want = (('', '.my-agent'), ('   ', '.my-agent'), ('${user_config.task_dir}', '.my-agent'),
                ('.my-agent', '.my-agent'), ('docs/agent', 'docs/agent'), ('notes/agent/', 'notes/agent'),
                ('./x/', 'x'), ('docs//agent', 'docs/agent'), ('Notes/Agent', 'Notes/Agent'),
                ('/x', '.my-agent'), ('~/x', '.my-agent'), ('a/../b', '.my-agent'), ('..', '.my-agent'),
                ('/', '.my-agent'), ('//', '.my-agent'), ('.git', '.my-agent'), ('.claude/x', '.my-agent'))
        for value, second in want:
            r = self.run_clean('--data-dir', '~/dev/agent-tasks', '--task-dir', value)
            self.assertEqual((r.returncode, r.stdout), (0, f'{self.home}/dev/agent-tasks\n{second}\n'), value)

    def test_script_task_dir_env_wins(self):
        r = self.run_clean('--data-dir', '~/d', '--task-dir', '.x', MA_TASK_DIR='docs/agent')
        self.assertEqual(r.stdout.splitlines()[1], 'docs/agent')
        r = self.run_clean('--data-dir', '~/d', '--task-dir', '/x', CLAUDE_PLUGIN_OPTION_TASK_DIR='docs/agent')
        self.assertEqual(r.stdout.splitlines()[1], '.my-agent')

    def test_script_without_task_dir_is_one_line(self):
        r = self.run_clean('--data-dir', '~/d', CLAUDE_PLUGIN_OPTION_TASK_DIR='docs/agent')
        self.assertEqual(len(r.stdout.splitlines()), 1)

    def test_plugin_json_task_dir_setting(self):
        manifest = json.loads((L4.parent / '.claude-plugin' / 'plugin.json').read_text())
        entry = manifest['userConfig']['task_dir']
        self.assertEqual((entry['default'], entry['required']), ('.my-agent', False))
        self.assertEqual(ma_data.task_dir(entry['default']), '.my-agent')


if __name__ == '__main__':
    unittest.main()

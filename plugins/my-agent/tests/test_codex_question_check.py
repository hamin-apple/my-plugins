"""build-codex.py --check-question-tool: reads the Codex flag default_mode_request_user_input (task 261105, u1).

Every case runs the script with PATH set to a temp folder holding a fake `codex`; the real codex and ~/.codex are never
used. The fake logs its arguments, so each case also shows that the check runs only `codex features list`.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import REPO

SCRIPT = REPO / 'l4-tools-guards' / 'scripts' / 'build-codex.py'
LIST_ON = ('collaboration_modes                      removed            true\n'
           'default_mode_request_user_input          under development  true\n'
           'hooks                                    stable             true\n')
LIST_OFF = LIST_ON.replace('under development  true', 'under development  false')
LIST_NONE = 'collaboration_modes                      removed            true\n'


class QuestionCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.log = self.tmp / 'argv.log'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake(self, output='', code=0, sleep=0):
        out = self.tmp / 'out.txt'
        out.write_text(output)
        script = self.bin / 'codex'
        script.write_text('#!/bin/sh\n'
                          f'echo "$@" >> "{self.log}"\n'
                          + (f'sleep {sleep}\n' if sleep else '')
                          + f'cat "{out}"\n'
                          f'exit {code}\n')
        script.chmod(0o755)

    def run_check(self, *extra):
        env = dict(os.environ, PATH=f'{self.bin}{os.pathsep}/bin{os.pathsep}/usr/bin')
        return subprocess.run([sys.executable, str(SCRIPT), '--check-question-tool', *extra],
                              capture_output=True, text=True, env=env, timeout=30)

    def assert_one_line(self, r, line, code):
        self.assertEqual(r.stdout, line + '\n', r.stderr)
        self.assertEqual(r.returncode, code)

    def assert_only_features_list(self):
        self.assertEqual(self.log.read_text().splitlines(), ['features list'])

    def test_flag_on(self):
        self.fake(LIST_ON)
        self.assert_one_line(self.run_check(), 'Codex question tool: flag on', 0)
        self.assert_only_features_list()

    def test_flag_off(self):
        self.fake(LIST_OFF)
        self.assert_one_line(self.run_check(), 'Codex question tool: flag off', 1)
        self.assert_only_features_list()

    def test_flag_not_listed(self):
        self.fake(LIST_NONE)
        self.assert_one_line(self.run_check(), 'Codex question tool: could not tell (flag not listed)', 3)
        self.assert_only_features_list()

    def test_codex_exits_non_zero(self):
        self.fake(LIST_ON, code=2)
        self.assert_one_line(self.run_check(), 'Codex question tool: could not tell (codex features list exited 2)', 3)
        self.assert_only_features_list()

    def test_codex_times_out(self):
        self.fake(LIST_ON, sleep=3)
        self.assert_one_line(self.run_check('--timeout', '1'),
                             'Codex question tool: could not tell (codex features list timed out)', 3)
        self.assert_only_features_list()

    def test_codex_not_found(self):
        self.assert_one_line(self.run_check(), 'Codex question tool: could not tell (codex not found)', 3)
        self.assertFalse(self.log.exists())

    def test_writes_nothing(self):
        self.fake(LIST_OFF)
        before = sorted(p.name for p in self.tmp.rglob('*'))
        self.run_check()
        after = sorted(p.name for p in self.tmp.rglob('*') if p != self.log)   # the fake's own argument log
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()

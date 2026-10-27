import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from monitor import registry
from monitor.registry import Registry
from tests.fixtures.build_fixtures import CLAUDE, PROJECTS, PROJECTS_TXT


def reg(projects_file):
    return Registry(projects_file, claude_root=CLAUDE)


class RegistryTest(unittest.TestCase):
    def test_lists_all_fixture_tasks(self):
        tasks = reg(PROJECTS_TXT).list_tasks()
        self.assertEqual(len(tasks), 5)
        self.assertEqual(set(tasks[0]), {'id', 'key', 'project', 'profile', 'status', 'step', 'title', 'waiting', 'elapsed'})
        self.assertEqual(tasks[0]['id'], '261024-cli-json-output')   # newest first

    def test_summary_elapsed_matches_detail_for_running(self):
        r = reg(PROJECTS_TXT)
        running = [t for t in r.list_tasks() if t['status'] == 'running']
        self.assertTrue(running)
        for t in running:
            self.assertIsNotNone(t['elapsed'])
            self.assertEqual(t['elapsed'], r.get_task(t['key'])['elapsed'])

    def test_registry_skips_missing_and_expands_home(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'projects.txt'
            p.write_text(f'~/nonexistent-ma-project  \n\n{PROJECTS / "work-notes"}   \n', encoding='utf-8')
            self.assertEqual([t['id'] for t in reg(p).list_tasks()], ['261022-weekly-report'])
            with mock.patch.dict(os.environ, {'HOME': str(PROJECTS)}):
                p.write_text('~/flight-search\n', encoding='utf-8')
                self.assertEqual([t['id'] for t in reg(p).list_tasks()], ['261021-flight-watch'])

    def test_missing_projects_file(self):
        self.assertEqual(reg(Path('/nonexistent/projects.txt')).list_tasks(), [])

    def test_rebuild_only_on_change(self):
        r = reg(PROJECTS_TXT)
        key = r.list_tasks()[0]['key']
        with mock.patch.object(registry, 'build_task', wraps=registry.build_task) as spy:
            r.get_task(key)
            r.get_task(key)
            self.assertEqual(spy.call_count, 0)
            log = PROJECTS / 'claude-sessions/docs/agent/261024-cli-json-output/run-log.md'
            st = log.stat()
            os.utime(log, (st.st_atime, st.st_mtime + 1))
            try:
                self.assertEqual(r.get_task(key)['id'], '261024-cli-json-output')
            finally:
                os.utime(log, (st.st_atime, st.st_mtime))
            self.assertEqual(spy.call_count, 1)
        self.assertIsNone(r.get_task('deadbeef/nope'))


if __name__ == '__main__':
    unittest.main()


class PricesFileTest(unittest.TestCase):
    def test_prices_override_used_when_present(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'MA_TASKS_DIR': d}):
            Path(d, 'prices.json').write_text('{"models": {}}')
            self.assertEqual(registry.default_prices_file(), Path(d, 'prices.json'))

    def test_prices_default_when_absent(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {'MA_TASKS_DIR': d}):
            self.assertEqual(registry.default_prices_file(), registry.ROOT / 'prices.json')

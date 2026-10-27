"""The menu bar app's Detail view selects a task through two things web/index.html already has.
Renaming either breaks the app, so this test fails first. Runs without swiftc."""
import unittest
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / 'web' / 'index.html'


class WebContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX.read_text(encoding='utf-8')

    def test_select_task_is_a_global_async_function(self):
        self.assertIn('async function selectTask(', self.html)

    def test_task_hash_is_read_at_load(self):
        self.assertIn('/^#task=(.+)$/', self.html)
        self.assertIn('decodeURIComponent(hashTask[1])', self.html)


if __name__ == '__main__':
    unittest.main()

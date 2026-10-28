"""hooks.json registers the hooks exactly as architecture 4.5.1 / 4.7.2 list them; the three blocking hooks (scope-guard, plan-approved-check, verdict-fresh-check) carry onFailure block."""
import json
import re
import unittest

from helpers import L4

GATES = {'scope-guard.py', 'plan-approved-check.py', 'verdict-fresh-check.py'}
EXPECTED = {
    ('PreToolUse', None, 'scope-guard.py'),
    ('PreToolUse', 'Agent', 'subagent-log.py call'),
    ('PreToolUse', 'Agent|Workflow|Edit|Write|NotebookEdit|Bash', 'plan-approved-check.py'),
    ('PreToolUse', 'Bash|Edit|Write|NotebookEdit', 'verdict-fresh-check.py'),
    ('SubagentStart', '^my-agent:', 'subagent-log.py start'),
    ('SubagentStop', '^my-agent:', 'subagent-log.py stop'),
    ('PermissionRequest', None, 'permission-log.py ask'),
    ('PostToolUse', None, 'permission-log.py answer'),
    ('SessionStart', 'startup|resume|clear|compact|fork', 'session-notice.py'),
}
PREFIX = 'python3 "${CLAUDE_PLUGIN_ROOT}"/l4-tools-guards/hooks/'


class HooksJsonTest(unittest.TestCase):
    def test_hooks_table(self):
        data = json.loads((L4 / 'hooks' / 'hooks.json').read_text())
        rows = set()
        for event, groups in data['hooks'].items():
            for g in groups:
                for h in g['hooks']:
                    self.assertEqual(h['type'], 'command')
                    self.assertTrue(h['command'].startswith(PREFIX), h['command'])
                    tail = h['command'][len(PREFIX):]
                    if tail.split()[0] in GATES:
                        self.assertEqual((h.get('onFailure'), h['timeout']), ('block', 30), tail)
                    else:
                        self.assertNotIn('onFailure', h)
                    self.assertTrue((L4 / 'hooks' / tail.split()[0]).is_file(), tail)
                    rows.add((event, g.get('matcher'), tail))
        self.assertEqual(rows, EXPECTED)


if __name__ == '__main__':
    unittest.main()

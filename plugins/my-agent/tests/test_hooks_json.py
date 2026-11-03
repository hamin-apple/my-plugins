"""hooks.json registers the hooks exactly as architecture 4.5.1 / 4.7.2 list them; the three blocking hooks (scope-guard, plan-approved-check, verdict-fresh-check) carry onFailure block."""
import json
import re
import unittest

from helpers import L4

GATES = {'scope-guard.py', 'plan-approved-check.py', 'verdict-fresh-check.py'}
EXPECTED = {
    ('PreToolUse', None, 'scope-guard.py'),
    ('PreToolUse', 'Agent|collaborationspawn_agent', 'subagent-log.py call'),
    ('PreToolUse', 'Agent|collaborationspawn_agent|Workflow|Edit|Write|NotebookEdit|apply_patch|Bash', 'plan-approved-check.py'),
    ('PreToolUse', 'Bash|Edit|Write|NotebookEdit|apply_patch', 'verdict-fresh-check.py'),
    ('SubagentStart', '^my-agent:|^my_agent_', 'subagent-log.py start'),
    ('SubagentStop', '^my-agent:|^my_agent_', 'subagent-log.py stop'),
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

    def _selected(self, event, name, search=False):
        data = json.loads((L4 / 'hooks' / 'hooks.json').read_text())
        match = re.search if search else re.fullmatch
        out = set()
        for g in data['hooks'][event]:
            m = g.get('matcher')
            if m is None or match(m, name):
                out |= {h['command'][len(PREFIX):] for h in g['hooks']}
        return out

    def test_claude_selection_unchanged(self):
        before = {
            'Agent': {'scope-guard.py', 'subagent-log.py call', 'plan-approved-check.py'},
            'Workflow': {'scope-guard.py', 'plan-approved-check.py'},
            'Edit': {'scope-guard.py', 'plan-approved-check.py', 'verdict-fresh-check.py'},
            'Write': {'scope-guard.py', 'plan-approved-check.py', 'verdict-fresh-check.py'},
            'NotebookEdit': {'scope-guard.py', 'plan-approved-check.py', 'verdict-fresh-check.py'},
            'Bash': {'scope-guard.py', 'plan-approved-check.py', 'verdict-fresh-check.py'},
            'Read': {'scope-guard.py'},
        }
        for name, hooks in before.items():
            self.assertEqual(self._selected('PreToolUse', name), hooks, name)
        for event, tail in (('SubagentStart', 'subagent-log.py start'), ('SubagentStop', 'subagent-log.py stop')):
            self.assertEqual(self._selected(event, 'my-agent:coder', True), {tail})
            self.assertEqual(self._selected(event, 'general-purpose', True), set())

    def test_codex_names_select_like_claude_counterparts(self):
        self.assertEqual(self._selected('PreToolUse', 'collaborationspawn_agent'), self._selected('PreToolUse', 'Agent'))
        self.assertEqual(self._selected('PreToolUse', 'apply_patch'), self._selected('PreToolUse', 'Edit'))
        for event, tail in (('SubagentStart', 'subagent-log.py start'), ('SubagentStop', 'subagent-log.py stop')):
            self.assertEqual(self._selected(event, 'my_agent_coder', True), {tail})
            self.assertEqual(self._selected(event, 'ma_probe_worker_a', True), set())


if __name__ == '__main__':
    unittest.main()

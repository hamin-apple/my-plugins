"""hosts.md: the Claude Code -> Codex name table of the shared text (task 261101-codex-port, u11)."""
import re
import unittest

import helpers
import ma_host

HOSTS = helpers.REPO / 'l1-orchestration' / 'hosts.md'
SKILL = helpers.REPO / 'SKILL.md'
SHARED = (sorted((helpers.REPO / 'l1-orchestration' / 'phases').glob('*.md'))
          + sorted((helpers.REPO / 'l1-orchestration' / 'profiles').glob('*.md'))
          + sorted((helpers.REPO / 'l2-design-judge' / 'agents').glob('*.md'))
          + sorted((helpers.REPO / 'l3-workers' / 'agents').glob('*.md')))


def rows():
    out = {}
    for line in HOSTS.read_text(encoding='utf-8').splitlines():
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if line.startswith('|') and len(cells) == 3 and cells[0] not in ('Claude Code', '---'):
            out[cells[0]] = cells
    return out


class HostsTest(unittest.TestCase):
    def find(self, word):
        hit = [r for k, r in rows().items() if word in k]
        self.assertTrue(hit, f'no row for {word}')
        return hit[0]

    def test_codex_names_match_ma_host(self):
        self.assertIn(f'`{ma_host.SPAWN_TOOL}`', self.find('`Agent`')[1])
        self.assertIn(f'`{ma_host.FILE_TOOL}`', self.find('`Edit`')[1])
        role = self.find('subagent_type')
        self.assertEqual(role[1], 'not available in Codex')
        self.assertIn(f'`{ma_host.CODEX_PREFIX}<role>`', role[2])
        self.assertEqual(ma_host.claude_agent(ma_host.codex_agent('my-agent:coder')), 'my-agent:coder')

    def test_skill_pointer(self):
        text = SKILL.read_text(encoding='utf-8')
        self.assertIn('- Codex: read `l1-orchestration/hosts.md`', text)
        self.assertLess(text.index('l1-orchestration/hosts.md'), 16000)
        self.assertLess(text.index('## Arguments'), 16000)

    def test_no_codex_text_in_shared_files(self):
        self.assertTrue(SHARED)
        for path in SHARED:
            self.assertNotIn('codex', path.read_text(encoding='utf-8').lower(), str(path))

    def test_no_fallback_wording(self):
        text = HOSTS.read_text(encoding='utf-8').lower()
        for word in ('fallback', 'workaround'):
            self.assertNotIn(word, text)

    def test_model_effort_and_identity_rows(self):
        self.assertEqual(self.find('`model`')[1], 'not available in Codex')
        self.assertIn('`effort`', self.find('`model`')[0])
        ident = self.find('Agent identity')
        self.assertIn('`agent_type`', ident[1])
        self.assertIn('`agent_id`', ident[1])

    def test_variable_rows_do_not_claim_expansion(self):
        for word in ('CLAUDE_PLUGIN_ROOT', 'CLAUDE_SKILL_DIR', 'user_config'):
            row = self.find(word)
            self.assertIn('literally, not expanded', ' '.join(row[1:]))

    def test_my_agent_row(self):
        row = self.find('`/my-agent`')
        self.assertEqual(row[1], 'not available in Codex')
        self.assertIn('Codex lists no plugin-root `SKILL.md`', row[2])
        self.assertIn('`my-agent:monitor` is listed', row[2])

    def test_role_row_is_not_available(self):
        row = self.find('`my-agent:<role>`')
        self.assertEqual(row[1], 'not available in Codex')
        self.assertIn('unknown agent_type', row[2])
        self.assertIn('`my_agent_<role>`', row[2])

    def test_question_row_names_the_codex_tool(self):
        row = self.find('AskUserQuestion')
        self.assertIn('`request_user_input`', row[1])
        self.assertIn('`request_user_input_async`', row[1])

    def test_rows_present(self):
        for word in ('AskUserQuestion', '`Workflow`', '`SendMessage`', 'hand-back', '`Bash`', 'WebFetch',
                     'CLAUDE_CODE_SESSION_ID', 'G2', '/my-agent:monitor', '.claude/worktrees', 'isolation',
                     'run_in_background'):
            self.find(word)
        self.assertNotRegex(HOSTS.read_text(encoding='utf-8'), re.compile('/Users/|/home/'))


if __name__ == '__main__':
    unittest.main()

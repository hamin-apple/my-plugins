"""The architecture doc (4.7.1) agrees with SKILL.md and the profile folder on the arguments."""
import json
import re
import unittest

from helpers import REPO
import ma_schema
from test_skill_md import SKILL, frontmatter

ARCH = REPO / 'docs' / 'build-guide' / 'my-agent-architecture.md'
PROFILES = REPO / 'l1-orchestration' / 'profiles'


def unquote(value):
    return value.strip().strip('\'"')


class ArchDocTest(unittest.TestCase):
    def setUp(self):
        self.text = ARCH.read_text(encoding='utf-8')

    def test_arch_doc_argument_hint_matches_skill_md(self):
        hints = re.findall(r'^argument-hint:(.*)$', self.text, re.M)
        self.assertEqual(len(hints), 1, hints)
        skill = frontmatter(SKILL.read_text(encoding='utf-8'))['argument-hint']
        self.assertEqual(unquote(hints[0]), unquote(skill))

    def test_arch_doc_names_every_flag(self):
        start = self.text.index('### 4.7.1 ')
        end = self.text.index('### 4.7.2 ')
        section = self.text[start:end]
        for path in sorted(PROFILES.glob('*.md')):
            self.assertIn(f'--{path.stem}', section)

    def test_arch_doc_states_flag_ignored_and_dev_fallback(self):
        start = self.text.index('**Profile flag (Q19):**')
        section = self.text[start:self.text.index('**Draft frontmatter**')]
        self.assertIn('If the person picks `Continue it` or `Cancel`, the flag is ignored.', section)
        self.assertIn('`Request:` keeps `--dev` as its first word while `Profile:` is general', section)
        self.assertIn('the label is `(set by you)` because the person chose general', section)

    def test_draft_frontmatter_has_no_hooks_key(self):
        start = self.text.index('**Draft frontmatter**')
        block = re.search(r'```yaml\n(.*?)```', self.text[start:], re.S).group(1)
        self.assertNotRegex(block, r'(?m)^hooks:')

    def test_plugin_hook_table_lists_the_gate_hooks_with_their_matchers(self):
        start = self.text.index('### 4.5.1 ')
        section = self.text[start:self.text.index('### 4.6 ')]
        for script, matcher in (('plan-approved-check.py', 'Agent\\|Workflow\\|Edit\\|Write\\|NotebookEdit\\|Bash'),
                                ('verdict-fresh-check.py', 'Bash\\|Edit\\|Write\\|NotebookEdit')):
            rows = [l for l in section.splitlines() if l.startswith('|') and script in l]
            self.assertEqual(len(rows), 1, script)
            self.assertIn(f'`{matcher}`', rows[0], script)

    def section(self, start, end):
        a = self.text.index(start)
        return self.text[a:self.text.index(end, a)]

    def test_g1b_section_says_ask_for_writes_and_deny_for_delegation(self):
        a = self.text.index('**G1b hard gate**')
        sec = self.text[a:self.text.index('- **Block when the hook fails:**', a)]
        self.assertNotIn('blocks **regardless of phase**', sec)
        self.assertNotIn('pre-approval write block', sec)
        self.assertIn('`permissionDecision: ask`', sec)
        self.assertIn('`permissionDecision: deny`', sec)

    def test_status_line_starts_with_v044(self):
        line = re.search(r'^- Status: .*$', self.text, re.M).group(0)
        self.assertTrue(line.startswith('- Status: design draft v0.44 ('), line[:60])
        self.assertIn('v0.43 (', line)
        self.assertIn('plugin 0.8.0', line)

    def test_preset_mechanism_is_described(self):
        section = self.section('### 4.5 ', '### 4.5.1 ')
        for word in ('`agent-models.json`', 'agent-models.py', 'agent-models.example.json',
                     'pass=', 'CLAUDE_CODE_EFFORT_LEVEL', 'beats'):
            self.assertIn(word, section, word)
        self.assertNotIn('does not pass an `effort` argument in calls', section)
        f13 = [l for l in self.text.splitlines() if l.startswith('| F13 |')][0]
        self.assertIn('preset', f13)
        self.assertIn('retry', f13)

    def test_preset_rules_in_intake_and_plan(self):
        for word in ('`Models:`', '`## Models`', 'presets --profile', '`Models` row'):
            self.assertIn(word, self.text, word)
        profile = [l for l in self.text.splitlines() if l.startswith('- **Profile change at the first gate')][0]
        self.assertIn('`Models:`', profile)
        self.assertIn('preset', profile)

    def test_run_log_section_names_the_models_line(self):
        section = self.section('### 4.7.2 ', '### 4.7.3 ')
        self.assertIn('`models:`', section)
        self.assertIn('preset=', section)
        self.assertIn('source=file', section)

    def test_retry_beats_the_preset(self):
        section = self.section('### 4.8 ', '### 4.8.1 ')
        self.assertIn('beats the preset', section)

    def test_monitor_section_names_report_tab_and_open_html(self):
        section = self.section('### 4.7.4 ', '### 4.8 ')
        for word in ('Report', '/api/tasks/<key>/report', 'open-html.py', 'monitor-up.py'):
            self.assertIn(word, section, word)

    def test_gate_reports_open_with_overview_and_takeaway(self):
        self.assertIn('### Overview', self.text)
        self.assertIn('### Takeaway', self.text)

    def test_prototype_is_a_local_file_opened_by_open_html(self):
        a = self.text.index('**What G1b shows: mock-up and prototype**')
        section = self.text[a:self.text.index('**What a prototype is**')]
        self.assertIn('open-html.py', section)
        for stale in ('claude.ai', 'private artifact', 'artifact link', 'publishes it'):
            self.assertNotIn(stale, section, stale)
        self.assertNotIn('prototype link', self.section('### 4.4 ', '### 4.5 '))

    def test_check_before_anything_leaves_has_two_places(self):
        a = self.text.index('**check before anything leaves**')
        section = self.text[a:self.text.index('### 4.13 ')]
        self.assertIn('two places', section)
        self.assertNotIn('three places', section)
        self.assertNotIn('prototype', section)
        self.assertNotIn('artifact', section)

    def test_decision_log_has_q26_to_q28(self):
        for q in ('Q26', 'Q27', 'Q28'):
            rows = [l for l in self.text.splitlines() if l.startswith(f'| {q} |')]
            self.assertEqual(len(rows), 1, q)
        q28 = [l for l in self.text.splitlines() if l.startswith('| Q28 |')][0]
        self.assertIn('open-html.py', q28)

    def test_run_log_kinds_name_the_guard_line(self):
        section = self.section('### 4.7.2 ', '### 4.7.3 ')
        self.assertIn('`guard:`', section)
        for field in ma_schema.GUARD_FIELDS:
            self.assertIn(f'`{field}=`', section, field)

    def test_g1b_section_says_a_sibling_task_folder_write_is_asked(self):
        a = self.text.index('**G1b hard gate**')
        sec = self.text[a:self.text.index('- **Block when the hook fails:**', a)]
        self.assertIn('sibling task folder', sec)
        self.assertRegex(sec, r'(?s)sibling task folder.{0,200}asked')

    def test_cost_only_texts(self):
        lines = self.text.splitlines()
        g3 = [x for x in lines if x.startswith('| **G3 Final acceptance**')]
        self.assertEqual(len(g3), 1)
        self.assertIn('cost (reference, 4.8)', g3[0])
        self.assertNotIn('tokens and cost', g3[0])
        deliver = [x for x in lines if x.startswith('[Deliver] (chat)')]
        self.assertEqual(len(deliver), 1)
        self.assertNotIn('tokens', deliver[0])
        snap = [x for x in lines if x.startswith('- **Usage snapshot:**')]
        self.assertEqual(len(snap), 1)
        self.assertIn('≈ $', snap[0])
        self.assertIn('ma_prices', self.section('**Price table**', '\n**'))

    def test_status_line_plugin_version_matches_plugin_json(self):
        line = self.text.splitlines()[3]
        found = re.search(r'plugin (\d+\.\d+\.\d+)', line)
        self.assertIsNotNone(found, line[:80])
        manifest = json.loads((REPO / '.claude-plugin' / 'plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(found.group(1), manifest['version'])

    def test_principles_name_the_assumption_principle_and_judge_misses(self):
        section = self.section('### 4.1 Principles', '### 4.1.1 ')
        self.assertIn('assumption about what the model cannot do alone', section)
        self.assertIn('Judge misses', section)
        self.assertIn('removal candidate', section)

    def test_maintenance_section_names_removal_candidate_review(self):
        section = self.section('### 4.11 ', '### 4.12 ')
        self.assertIn('removal candidate', section)
        self.assertIn('feedback review', section)
        self.assertIn('Judge misses', section)

    def test_security_section_names_the_environment_deny(self):
        section = self.section('### 4.12 ', '## 5. ')
        self.assertIn('may not read the environment', section)

    def test_decision_log_has_q23_row(self):
        rows = [l for l in self.text.splitlines() if l.startswith('| Q23 |')]
        self.assertEqual(len(rows), 1, rows)
        self.assertIn('2026-10-30', rows[0])

    def test_security_section_names_the_read_roots_and_git_mv(self):
        section = self.section('### 4.12 ', '## 5. ')
        for word in ('data folder', 'plugin folder', 'scratchpad', 'git mv'):
            self.assertIn(word, section)
        self.assertIn('may be approved without a dialog and without a G2 record', section)

    def test_resume_section_has_the_non_owner_notice(self):
        section = self.section('### 4.8.2 ', '### 4.9 ')
        self.assertIn('The original session is running my-agent task <id> (phase <n>). '
                      'To take it over in this session, run /my-agent continue; otherwise work as usual.', section)

    def test_gate_section_has_the_ask_texts(self):
        section = self.section('### 4.4 ', '### 4.5 ')
        for text in ('my-agent plan gate: write outside the task folder', 'my-agent verdict gate:',
                     'cannot parse the command'):
            self.assertIn(text, section)

    def test_decision_log_has_q24_row(self):
        rows = [l for l in self.text.splitlines() if l.startswith('| Q24 |')]
        self.assertEqual(len(rows), 1, rows)
        self.assertIn('2026-10-30', rows[0])

    def test_decision_log_has_q25_row(self):
        rows = [l for l in self.text.splitlines() if l.startswith('| Q25 |')]
        self.assertEqual(len(rows), 1, rows)
        self.assertIn('2026-10-31', rows[0])

    def test_host_layer_section(self):
        section = self.section('### 4.14 ', '## 5. ')
        self.assertIn('Host layer', section.splitlines()[0])
        for text in ('l1-orchestration/hosts.md', 'ma_host.py'):
            self.assertIn(text, section)
        a = section.index('**Host differences**')
        differences = section[a:].lower()
        for word in ('fallback', 'workaround'):
            self.assertNotIn(word, differences)
        self.assertIn('refuses `my_agent_<role>`', differences)
        self.assertIn('loads no agent definition', differences)

    def test_host_differences_name_the_question_tool(self):
        section = self.section('### 4.14 ', '## 5. ')
        self.assertIn('`request_user_input`', section[section.index('**Host differences**'):])

    def test_reference_articles_list_both_local_copies(self):
        ref = (REPO / 'docs' / 'reference.md').read_text(encoding='utf-8')
        articles = ref[ref.index('## Articles'):]
        for name in ('harness-design-long-running-apps.md', 'managed-agents.md'):
            self.assertIn(f'`{name}`', articles)


if __name__ == '__main__':
    unittest.main()

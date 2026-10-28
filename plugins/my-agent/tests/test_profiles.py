"""Profiles under l1-orchestration/profiles/ and the Router's choice (architecture 4.3, 4.13 "judge checks")."""
import json
import re
import unittest

from helpers import L4, REPO

PROFILES = REPO / 'l1-orchestration' / 'profiles'
SKILL = REPO / 'SKILL.md'
FIXTURES = REPO / 'tests' / 'judge-fixtures'


class ProfilesTest(unittest.TestCase):
    def test_profiles_exist(self):
        for name in ('general', 'research', 'dev'):
            self.assertTrue((PROFILES / f'{name}.md').is_file(), name)

    def test_router_names_every_profile(self):
        text = SKILL.read_text(encoding='utf-8')
        for name in ('general', 'research', 'dev'):
            self.assertIn(f'${{CLAUDE_SKILL_DIR}}/l1-orchestration/profiles/{name}.md', text)
            self.assertRegex(text, rf'`{name}`')
        self.assertIn('Profile: <', text)

    def test_research_rules_present(self):
        text = (PROFILES / 'research.md').read_text(encoding='utf-8')
        for word in ('Questions', 'Scope', 'Source criteria', 'Deliverable format', 'G1a', 'claim · source URL · quote', 'sub-questions',
                     'synthesis structure', 'sample paragraph', 'source bias', 'scope gaps', 'my-agent:researcher', 'my-agent:writer',
                     'deliverable/'):
            self.assertIn(word, text, word)
        self.assertRegex(text, r'Plan Review \| not skipped')

    def test_dev_rules_present(self):
        text = (PROFILES / 'dev.md').read_text(encoding='utf-8')
        for word in ('purpose and users', 'Completion criteria', 'hard constraints', 'exception cases', 'data', 'non-goals', 'UX preferences', 'G1a',
                     'small task', '3 files', 'SKIPPED small task', '`isolation: "worktree"`', 'first parallel group', 'base commit=',
                     'User cleans up first (Recommended)', 'Proceed as is', '`Run:`', 'git diff', 'git status',
                     'Commit (Recommended)', 'Rework', 'completion criterion number', '## Decisions', 'git apply'):
            self.assertIn(word, text, word)
        build = (REPO / 'l1-orchestration' / 'phases' / 'build.md').read_text(encoding='utf-8')
        accept = (REPO / 'l1-orchestration' / 'phases' / 'accept.md').read_text(encoding='utf-8')
        self.assertIn('User cleans up first (Recommended)', build)
        self.assertIn('Commit (Recommended)', accept)
        self.assertIn('deliver path=commit:', accept)

    def test_judge_fixtures(self):
        expected = json.loads((FIXTURES / 'expected.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(expected.values()).count('FAIL'), 3)
        self.assertIn('PASS', expected.values())
        for note in expected:
            self.assertTrue((FIXTURES / note).is_file(), note)
        self.assertTrue((FIXTURES / 'scope.md').is_file())
        script = (FIXTURES / 'run-judge-check.sh').read_text(encoding='utf-8')
        self.assertIn('my-agent:verifier', script)
        self.assertIn('--max-budget-usd', script)
        self.assertIn('JUDGE OK', script)

    def test_fixture_notes_use_the_note_format(self):
        line = re.compile(r'^- .+ · https?://\S+ · ".+"$|^- Not found: .+$')
        for note in ('note-good.md', 'note-criterion-miss.md', 'note-broken-citation.md'):
            items = [ln for ln in (FIXTURES / note).read_text(encoding='utf-8').splitlines() if ln.startswith('- ')]
            self.assertTrue(items, note)
            for ln in items:
                self.assertRegex(ln, line, note)


    def test_result_location_line_format(self):
        """plan-approved-check reads `- Deliverable location: `<path>`` / `- Save path: `<path>`` to let the deliver write through."""
        general = (PROFILES / 'general.md').read_text(encoding='utf-8')
        research = (PROFILES / 'research.md').read_text(encoding='utf-8')
        self.assertIn('`- Deliverable location: `', general)
        self.assertIn('`- Save path: `', research)

    def test_argument_hint_matches_profiles_and_phases(self):
        text = SKILL.read_text(encoding='utf-8')
        m = re.search(r'^argument-hint: (.+)$', text, re.M)
        self.assertIsNotNone(m)
        hint = m.group(1).strip().strip('\'"')
        flags = set(re.findall(r'--([a-z]+)', hint))
        self.assertEqual(flags, {p.stem for p in PROFILES.glob('*.md')} | {'auto'})
        for phase in (p.stem for p in (REPO / 'l1-orchestration' / 'phases').glob('*.md')):
            self.assertIn(phase, hint)
        self.assertIn('continue', hint)
        self.assertIn('status [all]', hint)

    def test_arguments_table_names_every_flag(self):
        text = SKILL.read_text(encoding='utf-8')
        args = text[text.index('## Arguments'):text.index('## Intake')]
        for p in PROFILES.glob('*.md'):
            self.assertIn(f'--{p.stem}', args)
        self.assertIn('Let the Router pick (Recommended)', args)
        self.assertIn('`Let the Router pick (Recommended)` / `Abort`', args)
        self.assertIn('`Type the request in Other (Recommended)` / `Abort`', args)
        intake = text[text.index('## Intake'):text.index('## status')]
        self.assertIn('`Proceed as general (Recommended)` / `Abort`', intake)
        self.assertIn('the flag is ignored', intake)
        self.assertIn('keeps `--dev` as its first word', intake)

    def test_findings_popup_lives_in_plan_phase(self):
        """Plan Review findings are handled the same in every profile: the popup text is in phases/plan.md, not only dev.md."""
        plan = (REPO / 'l1-orchestration' / 'phases' / 'plan.md').read_text(encoding='utf-8')
        self.assertIn('`Apply all (Recommended)` / `Approve without applying` / `Pick myself`', plan)
        dev = (PROFILES / 'dev.md').read_text(encoding='utf-8')
        self.assertNotIn('Apply all (Recommended)', dev)
        for name in ('dev', 'general', 'research'):
            row = next(l for l in (PROFILES / f'{name}.md').read_text(encoding='utf-8').splitlines() if l.startswith('| 4 Plan Review'))
            if name == 'dev':
                self.assertIn('Not skipped (except for a small task)', row)
            else:
                self.assertIn('`plan.md` step 4', row)


if __name__ == '__main__':
    unittest.main()

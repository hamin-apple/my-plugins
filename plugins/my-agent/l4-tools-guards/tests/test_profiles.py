"""Profiles under l1-orchestration/profiles/ and the Router's choice (architecture 4.3, 4.13 "judge checks")."""
import json
import re
import unittest

from helpers import L4, REPO

PROFILES = REPO / 'l1-orchestration' / 'profiles'
SKILL = REPO / 'SKILL.md'
FIXTURES = L4 / 'tests' / 'judge-fixtures'


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

if __name__ == '__main__':
    unittest.main()

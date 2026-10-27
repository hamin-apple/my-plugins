"""Profiles under l1-orchestration/profiles/ and the Router's choice (architecture 4.3, 4.13 판정자 점검)."""
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

    def test_router_has_no_fallback(self):
        text = SKILL.read_text(encoding='utf-8')
        self.assertNotIn('일반 프로파일로 진행', text)
        self.assertNotIn('아직 만들지', text)
        for name in ('general', 'research', 'dev'):
            self.assertIn(f'${{CLAUDE_SKILL_DIR}}/l1-orchestration/profiles/{name}.md', text)
            self.assertRegex(text, rf'`{name}`')
        self.assertIn('Profile: <', text)

    def test_research_rules_present(self):
        text = (PROFILES / 'research.md').read_text(encoding='utf-8')
        for word in ('질문', '범위', '출처 기준', '결과물 형식', 'G1a', '주장 · 출처 URL · 인용', '하위 질문',
                     '종합 구조', '샘플 단락', '출처 편향', '범위 누락', 'my-agent:researcher', 'my-agent:writer',
                     'deliverable/'):
            self.assertIn(word, text, word)
        self.assertRegex(text, r'Plan Review \| 생략하지 않습니다')

    def test_dev_rules_present(self):
        text = (PROFILES / 'dev.md').read_text(encoding='utf-8')
        for word in ('목적·사용자', '완료 기준', '강한 제약', '예외 경우', '데이터', '비목표', 'UX 선호', 'G1a',
                     '작은 작업', '3개', 'SKIPPED 작은 작업', '`isolation: "worktree"`', '첫 병렬 그룹', 'base commit=',
                     '사용자가 먼저 정리 (Recommended)', '그대로 두고 진행', '`Run:`', 'git diff', 'git status',
                     '커밋 (Recommended)', '재작업', '완료 기준 번호', '## Decisions', 'git apply'):
            self.assertIn(word, text, word)
        build = (REPO / 'l1-orchestration' / 'phases' / 'build.md').read_text(encoding='utf-8')
        accept = (REPO / 'l1-orchestration' / 'phases' / 'accept.md').read_text(encoding='utf-8')
        self.assertIn('사용자가 먼저 정리 (Recommended)', build)
        self.assertIn('커밋 (Recommended)', accept)
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
        line = re.compile(r'^- .+ · https?://\S+ · ".+"$|^- 찾지 못함: .+$')
        for note in ('note-good.md', 'note-criterion-miss.md', 'note-broken-citation.md'):
            items = [ln for ln in (FIXTURES / note).read_text(encoding='utf-8').splitlines() if ln.startswith('- ')]
            self.assertTrue(items, note)
            for ln in items:
                self.assertRegex(ln, line, note)


    def test_result_location_line_format(self):
        """plan-approved-check reads `- 결과물 위치: `<경로>`` / `- 저장 경로: `<경로>`` to let the deliver write through."""
        general = (PROFILES / 'general.md').read_text(encoding='utf-8')
        research = (PROFILES / 'research.md').read_text(encoding='utf-8')
        self.assertIn('`- 결과물 위치: `', general)
        self.assertIn('`- 저장 경로: `', research)

if __name__ == '__main__':
    unittest.main()

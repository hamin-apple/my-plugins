"""Runtime files carry no stage fallbacks and never point at my-dev (plan Global Constraints; user ruling
"my-agent 를 수행하면 my-agent 의 아키텍처 설계한대로 동작해야해. 예외는 없어.")."""
import unittest

from helpers import L4, REPO

RUNTIME = [REPO / 'SKILL.md', REPO / 'skills', REPO / 'l1-orchestration', REPO / 'l2-design-judge', REPO / 'l3-workers',
           L4 / 'hooks', L4 / 'scripts', L4 / 'lib', L4 / 'permissions']
BANNED = ['my-dev', '구현 4단계', '구현 1단계', '아직 만들지', '일반 프로파일로 진행', '아직 없습니다']


def files():
    for root in RUNTIME:
        paths = [root] if root.is_file() else sorted(p for p in root.rglob('*') if p.is_file())
        for p in paths:
            if p.suffix in ('.md', '.py', '.json', '.sh', '.txt') and '__pycache__' not in p.parts:
                yield p


class RuntimeTextTest(unittest.TestCase):
    def test_no_fallbacks_or_my_dev(self):
        seen = 0
        for p in files():
            text = p.read_text(encoding='utf-8')
            seen += 1
            for word in BANNED:
                self.assertNotIn(word, text, f'{p.relative_to(REPO)}: {word}')
        self.assertGreater(seen, 20)


if __name__ == '__main__':
    unittest.main()

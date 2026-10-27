"""Runtime files carry no stage fallbacks and never point at my-dev (plan Global Constraints; user ruling
"When my-agent runs, it must behave exactly as the my-agent architecture designs it. No exceptions.")."""
import unittest

from helpers import L4, REPO

RUNTIME = [REPO / 'SKILL.md', REPO / 'skills', REPO / 'l1-orchestration', REPO / 'l2-design-judge', REPO / 'l3-workers',
           L4 / 'hooks', L4 / 'scripts', L4 / 'lib', L4 / 'permissions']
BANNED = ['my-dev', 'build step']   # a note about build steps in a runtime file is a stage fallback


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

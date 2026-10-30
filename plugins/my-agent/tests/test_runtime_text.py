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

    def test_gate_texts_say_ask_or_block(self):
        skill = (REPO / 'SKILL.md').read_text(encoding='utf-8')
        plan = (REPO / 'l1-orchestration/phases/plan.md').read_text(encoding='utf-8')
        accept = (REPO / 'l1-orchestration/phases/accept.md').read_text(encoding='utf-8')
        for text in (skill, plan, accept):
            for old in ('blocks them as commands whose write target', 'blocks a relative path after',
                        'blocks a Bash write containing', 'blocks the G3 save and commit'):
                self.assertNotIn(old, text)

        def line(text, key):
            hits = [x for x in text.splitlines() if key in x]
            self.assertEqual(len(hits), 1, key)
            return hits[0]
        self.assertIn('asks (the G2 dialog)', line(skill, 'plan-approved-check.py'))
        self.assertIn('asks (the G2 dialog)', line(skill, 'the verdict hook cannot tell whether it is a commit'))
        commit = line(accept, 'git add <files>')
        self.assertIn('asks (the G2 dialog)', commit)
        self.assertNotIn('blocks it. If blocked, redo from Verify', commit)
        self.assertIn('blocks it. If blocked, redo from Verify', line(accept, 'Copy the final version'))

    def test_g3_report_says_cost_only(self):
        accept = (REPO / 'l1-orchestration/phases/accept.md').read_text(encoding='utf-8')
        self.assertNotIn('tokens used and cost', accept)
        self.assertGreaterEqual(accept.count('cost (reference)'), 2)


if __name__ == '__main__':
    unittest.main()

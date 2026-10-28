"""The architecture doc (4.7.1) agrees with SKILL.md and the profile folder on the arguments."""
import re
import unittest

from helpers import REPO
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


if __name__ == '__main__':
    unittest.main()

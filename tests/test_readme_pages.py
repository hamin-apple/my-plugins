"""Both READMEs name the architecture page and the feature pages correctly and agree with each other."""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
READMES = [REPO / 'README.md', REPO / 'README-ko.md']
PAGES_URL = 'https://hamin-apple.github.io/my-plugins/'


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


class ReadmePagesTest(unittest.TestCase):
    def test_architecture_page_is_named_and_linked(self):
        for path in READMES:
            text = read(path)
            self.assertIn('docs/architecture.html', text, path.name)
            self.assertIn(PAGES_URL + 'architecture.html', text, path.name)

    def test_feature_pages_have_file_list_entries(self):
        for path in READMES:
            text = read(path)
            for name in ('docs/index.html', 'docs/index-ko.html'):
                self.assertRegex(text, r'(?m)^- `%s`' % re.escape(name), '%s %s' % (path.name, name))

    def test_root_page_is_not_called_the_architecture_page(self):
        for path in READMES:
            lines = [l for l in read(path).splitlines() if 'docs/index.html' in l]
            self.assertTrue(lines, path.name)
            for line in lines:
                self.assertNotIn('architecture', line.lower(), path.name)
                self.assertNotIn('아키텍처', line, path.name)

    def test_page_paths_and_urls_match_between_the_twins(self):
        def pages(text):
            return re.findall(r'docs/[\w-]+\.html', text)

        def urls(text):
            return [u.rstrip('.,;)>') for u in re.findall(r'https://hamin-apple\.github\.io/[^\s>)`]*', text)]

        en, ko = read(READMES[0]), read(READMES[1])
        self.assertEqual(pages(en), pages(ko))
        self.assertEqual(urls(en), urls(ko))
        self.assertTrue(urls(en))


if __name__ == '__main__':
    unittest.main()

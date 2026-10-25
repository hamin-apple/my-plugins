"""lib/ma_bash: which paths a Bash command writes, reads, or copies from (architecture 4.4 "막는 대상")."""
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts lib/ on sys.path)
import ma_bash

CWD = Path('/p')


def P(s):
    return Path(s).resolve()


class WriteTargetsTest(unittest.TestCase):
    def test_bash_write_targets_table(self):
        table = [
            ('ls -la', []),
            ('cat a > out.txt', [P('/p/out.txt')]),
            ('echo x >> /tmp/l', [P('/tmp/l')]),
            ('cmd 2>&1 | tail -3', []),
            ('cmd >/dev/null 2>&1', []),
            ('cmd 2>/dev/null', []),
            ("sed -i '' 's/a/b/' f.md", [P('/p/f.md')]),
            ('sed -n 1,5p f.md', []),
            ('printf x | tee -a docs/agent/t/run-log.md', [P('/p/docs/agent/t/run-log.md')]),
            ('mkdir -p docs/agent/t && cp -pR a b/', [P('/p/docs/agent/t'), P('/p/b')]),
            ('rm -rf build', [P('/p/build')]),
            ('touch a; mv x y', [P('/p/a'), P('/p/y')]),
            ('dd if=/dev/zero of=img bs=1', [P('/p/img')]),
            ('git checkout -- x', None),
            ('git -C sub stash', None),
            ('git status --porcelain', []),
            ('git diff HEAD', []),
            ('python3 run-log.py step n=1', []),
            ('FOO=1 sudo rm x', [P('/p/x')]),
            ('find . -name "*.pyc" -delete', None),
            ('ls | xargs rm', None),
            ('echo hi > "$OUT"', None),
            ("cat > f.txt <<'EOF'\nrm -rf /\nEOF", [P('/p/f.txt')]),
            ('ls\nrm z', [P('/p/z')]),
            ('cat ~/notes.md', []),
        ]
        for cmd, expected in table:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.write_targets(cmd, CWD), expected)

    def test_unparseable_quotes_is_none(self):
        self.assertIsNone(ma_bash.write_targets('echo "unterminated > x', CWD))


class FinalReviewGapsTest(unittest.TestCase):
    """Forms the final review found the parser missed (I1, C3, I3, I4): each must name its target or give None."""

    def test_reserved_words_and_prefix_values(self):
        table = [
            ('if true; then rm -rf src; fi', [P('/p/src')]),
            ('for f in src/*.py; do sed -i "" s/a/b/ src/a.py; done', [P('/p/src/a.py')]),
            ('while read f; do rm src/a.py; done < list', [P('/p/src/a.py')]),
            ('{ rm -rf src; }', [P('/p/src')]),
            ('! rm src/a.py', [P('/p/src/a.py')]),
            ('sudo -u root rm src/a.py', [P('/p/src/a.py')]),
            ('nice -n 10 rm src/a.py', [P('/p/src/a.py')]),
            ('timeout 5 rm src/a.py', [P('/p/src/a.py')]),
        ]
        for cmd, expected in table:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.write_targets(cmd, CWD), expected)

    def test_nested_shells_are_parsed(self):
        self.assertEqual(ma_bash.write_targets('bash -c "rm -rf src"', CWD), [P('/p/src')])
        self.assertEqual(ma_bash.write_targets("sh -ec 'touch a'", CWD), [P('/p/a')])
        self.assertEqual(ma_bash.write_targets('eval "rm -rf src"', CWD), [P('/p/src')])
        self.assertIn(Path.home() / '.ssh/id_rsa', ma_bash.read_paths('bash -c "cat ~/.ssh/id_rsa"', CWD))

    def test_substitution_and_open_heredoc_fail_closed(self):
        for cmd in ['echo `rm -rf src`', 'echo "$(rm -rf src)"', 'echo "<<EOF"\nrm -rf src']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(ma_bash.write_targets(cmd, CWD))
                self.assertIsNone(ma_bash.read_paths(cmd, CWD))
        self.assertEqual(ma_bash.write_targets('cat <<< x\nrm -rf src', CWD), [P('/p/src')])

    def test_cd_is_followed(self):
        self.assertEqual(sorted(ma_bash.write_targets('cd src && touch docs/agent/x', CWD)),
                         sorted([P('/p/docs/agent/x'), P('/p/src/docs/agent/x')]))
        self.assertIn(P('/p/docs/agent/t/review.md'),
                      ma_bash.write_targets('cd docs && echo "BLOCKER 0" > agent/t/review.md', CWD))
        self.assertIsNone(ma_bash.read_paths('cd "$HOME" && cat .ssh/id_rsa', CWD))
        self.assertIsNone(ma_bash.write_targets('cd "$D" && touch x', CWD))
        self.assertIsNone(ma_bash.read_paths('cd "$D" && cat x', CWD))
        self.assertEqual(ma_bash.write_targets('cd src && pytest', CWD), [])

    def test_symlink_with_another_write_is_none(self):
        self.assertIsNone(ma_bash.write_targets('ln -s docs/agent/t x && echo 0 > x/review.md', CWD))
        self.assertEqual(ma_bash.write_targets('ln -s a b', CWD), [P('/p/b')])

    def test_variable_paths_make_reads_unknown(self):
        self.assertIsNone(ma_bash.read_paths('cat $HOME/.ssh/id_rsa', CWD))
        self.assertIsNone(ma_bash.read_paths('ln -s "$HOME/.zshrc" z', CWD))
        self.assertEqual(ma_bash.read_paths('echo $PATH', CWD), [])

    def test_git_allowlist(self):
        for cmd in ['git bisect start', 'git update-ref refs/heads/x HEAD', 'git notes add -m x', 'git fetch',
                    'git gc', 'git -c core.pager=x log', 'git diff --output=o.txt']:
            with self.subTest(cmd=cmd):
                self.assertTrue(ma_bash.git_mutates(cmd))
        for cmd in ['git status --porcelain', 'git diff HEAD', 'git log -3', 'git show x', 'git branch',
                    'git tag', 'git stash list', 'git -C sub rev-parse HEAD', 'git ls-files', 'git blame a']:
            with self.subTest(cmd=cmd):
                self.assertFalse(ma_bash.git_mutates(cmd))


class ReadPathsTest(unittest.TestCase):
    def test_read_paths(self):
        self.assertIn(Path.home() / '.ssh/id_rsa', ma_bash.read_paths('cat ~/.ssh/id_rsa', CWD))
        self.assertIn(P('/p/src'), ma_bash.read_paths('grep -rn foo src/', CWD))
        self.assertIn(P('/etc/hosts'), ma_bash.read_paths('head -n 3 --file=/etc/hosts', CWD))

    def test_patterns_are_not_paths(self):
        paths = ma_bash.read_paths("grep -rn '^/api' src/ && sed 's/a/b/' x/y https://e.com/a", CWD)
        self.assertNotIn(P('/api'), paths)
        self.assertEqual(sorted(paths), sorted([P('/p/src'), P('/p/x/y')]))

    def test_unparseable_is_none(self):
        self.assertIsNone(ma_bash.read_paths('cat "x', CWD))


class CopySourcesTest(unittest.TestCase):
    def test_copy_sources(self):
        self.assertEqual(ma_bash.copy_sources('cp -p docs/agent/t/work/note.md ~/notes/', CWD),
                         [P('/p/docs/agent/t/work/note.md')])
        self.assertEqual(ma_bash.copy_sources('mv a b c/', CWD), [P('/p/a'), P('/p/b')])
        self.assertEqual(ma_bash.copy_sources('ls a', CWD), [])


class GitSubcommandsTest(unittest.TestCase):
    def test_git_subcommands(self):
        self.assertEqual(ma_bash.git_subcommands('git add a && git -C x commit -m "m"; ls'), ['add', 'commit'])
        self.assertEqual(ma_bash.git_subcommands('echo "git commit"'), [])
        self.assertEqual(ma_bash.git_subcommands('git "unterminated'), ['?'])


class GitMutatesTest(unittest.TestCase):
    def test_git_mutates(self):
        for cmd in ('git commit -m x', 'git push', 'git -C a checkout b', 'git reset --hard', 'git add .',
                    'git branch -D x', 'git stash', 'ls && git restore f'):
            with self.subTest(cmd=cmd):
                self.assertTrue(ma_bash.git_mutates(cmd))
        for cmd in ('git status', 'git diff', 'git log --oneline', 'git branch', 'git show HEAD',
                    'git stash list', 'git rev-parse HEAD', 'ls'):
            with self.subTest(cmd=cmd):
                self.assertFalse(ma_bash.git_mutates(cmd))


if __name__ == '__main__':
    unittest.main()

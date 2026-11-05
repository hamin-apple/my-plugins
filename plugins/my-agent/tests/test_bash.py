"""lib/ma_bash: which paths a Bash command writes, reads, or copies from (architecture 4.4 "what is blocked")."""
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts lib/ on sys.path)
import ma_bash

CWD = Path('/p')


def P(s):
    return Path(s).resolve()


class WriteTargetsTest(unittest.TestCase):
    def test_read_paths_cd_checks_both_folders(self):
        got = ma_bash.read_paths('cd sub; cat ../x', CWD)
        self.assertIn(P('/p/x'), got)   # the cd worked
        self.assertIn(P('/x'), got)     # the cd failed

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
        self.assertEqual(ma_bash.write_targets('cd src && touch docs/agent/x', CWD), [P('/p/src/docs/agent/x')])
        self.assertEqual(sorted(ma_bash.write_targets('cd src; touch docs/agent/x', CWD)),
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


class SingleQuoteTest(unittest.TestCase):
    """Criterion 1: single-quoted `$(` and backticks are literal; unquoted and double-quoted ones stay unknown."""

    def test_single_quoted_substitution_is_text(self):
        for cmd in ["grep -rn 'foo$(bar' src/", "grep -n 'a`b' src/a.py", "grep -rn '\\$(x)' src/"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.write_targets(cmd, CWD), [])
                self.assertIn(P('/p/src'), ma_bash.read_paths(cmd, CWD) + [P('/p/src')])
        self.assertEqual(ma_bash.read_paths("grep -rn 'x$(y)' src/", CWD), [P('/p/src')])
        self.assertEqual(ma_bash.write_targets("grep 'x`y`' a > out.txt", CWD), [P('/p/out.txt')])

    def test_other_substitution_is_unknown(self):
        for cmd in ['echo "$(date)"', 'echo $(date)', 'echo `date`', 'echo "`date`"', "echo 'a' $(date)",
                    'echo "it\'s" $(date)', 'echo x | grep "$(cat f)"']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(ma_bash.write_targets(cmd, CWD))
                self.assertIsNone(ma_bash.read_paths(cmd, CWD))

    def test_nested_shell_strings_stay_unknown(self):
        self.assertIsNone(ma_bash.write_targets("bash -c 'echo $(date)'", CWD))
        self.assertIsNone(ma_bash.write_targets("eval 'rm `x`'", CWD))
        self.assertEqual(ma_bash.write_targets("bash -c 'grep \"a\" f'", CWD), [])


class HeredocTest(unittest.TestCase):
    """Criterion 2: any delimiter word closes at its matching line; the body is not read as commands."""

    def test_delimiter_words(self):
        for delim in ['EOF.txt', 'END-EXPLORE', "'EOF-1'", '"EOF.txt"', 'EOF', 'E1']:
            word = delim.strip('\'"')
            cmd = f'cat > f.txt <<{delim}\nrm -rf /\ngit commit -m x\n{word}\nls'
            with self.subTest(delim=delim):
                self.assertEqual(ma_bash.write_targets(cmd, CWD), [P('/p/f.txt')])
                self.assertEqual(ma_bash.git_subcommands(cmd), [])
        self.assertEqual(ma_bash.write_targets('cat <<-EOF.txt\n\trm x\n\tEOF.txt', CWD), [])

    def test_unclosed_still_fails_closed(self):
        for cmd in ["cat <<'EOF-1'\nbody", 'cat <<EOF.txt\nbody\nEOF']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(ma_bash.write_targets(cmd, CWD))
        self.assertEqual(ma_bash.git_subcommands("cat <<'EOF-1'\nbody"), [])

    def test_body_after_quoted_delimiter_not_commands(self):
        self.assertEqual(ma_bash.git_subcommands("cat <<'EOF-1'\ngit commit -m x\nEOF-1"), [])
        self.assertEqual(ma_bash.git_subcommands("cat <<'EOF-1' && git add a\nx\nEOF-1"), ['add'])


class HeredocExpansionTest(unittest.TestCase):
    """An unquoted heredoc expands its body in the current shell; a quoted one is literal."""

    def test_substitution_in_unquoted_body_is_unknown(self):
        for cmd in ['cat <<EOF\n$(rm x)\nEOF', 'cat <<EOF\n`rm x`\nEOF', 'cat <<-EOF\n\t$(rm x)\n\tEOF',
                    'cat <<EOF\nok\nEOF\ncat <<EOF2\n$(rm x)\nEOF2']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(ma_bash.write_targets(cmd, CWD))
                self.assertIsNone(ma_bash.read_paths(cmd, CWD))

    def test_quoted_delimiters_keep_the_body_literal(self):
        for delim in ["'EOF'", '"EOF"', '\\EOF']:
            cmd = f'cat <<{delim}\n$(rm x) `rm x` ${{D:=/etc}}\nEOF'
            with self.subTest(delim=delim):
                self.assertEqual(ma_bash.write_targets(cmd, CWD), [])

    def test_commit_with_heredoc_still_unparsed(self):
        for cmd in ['git commit -m "$(cat <<\'EOF\'\nfeat\nEOF\n)"', 'git commit -m "$(cat <<EOF\nfeat $x\nEOF\n)"',
                    'git commit -m "$(cat <<EOF\nfeat\nEOF\n)"']:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.git_subcommands(cmd), ['?'])


class CdTest(unittest.TestCase):
    """Criterion 4: `cd x &&` resolves against x only; anything else keeps the old folder as well."""

    def test_and_chain(self):
        self.assertEqual(ma_bash.write_targets('cd x && touch f', CWD), [P('/p/x/f')])
        self.assertEqual(ma_bash.write_targets('cd x && cd y && touch f', CWD), [P('/p/x/y/f')])
        self.assertEqual(ma_bash.write_targets('cd x && ( touch f )', CWD), [P('/p/x/f')])
        self.assertEqual(ma_bash.write_targets('cd x && bash -c "touch f"', CWD), [P('/p/x/f')])

    def test_not_replaced(self):
        both = sorted([P('/p/f'), P('/p/x/f')])
        for cmd in ['cd x; touch f', 'cd x || touch f', 'cd x\ntouch f', '( cd x && touch f ); touch f',
                    'cd x & touch f', 'cd x | touch f', 'false || cd x && touch f', 'if true; then cd x && true; fi; touch f']:
            with self.subTest(cmd=cmd):
                self.assertTrue(set(both) <= set(ma_bash.write_targets(cmd, CWD)))
        self.assertEqual(sorted(ma_bash.write_targets('cd x; touch f', CWD)), both)
        self.assertEqual(sorted(ma_bash.write_targets('cd x || touch f', CWD)), both)

    def test_after_the_and_chain_both_folders(self):
        both = sorted([P('/p/f'), P('/p/x/f')])
        for cmd in ['cd x && true; touch f', 'cd x && true || touch f', 'cd x && true\ntouch f',
                    'cd x && true & touch f']:
            with self.subTest(cmd=cmd):
                self.assertEqual(sorted(ma_bash.write_targets(cmd, CWD)), both)

    def test_unknown_stays_unknown(self):
        self.assertIsNone(ma_bash.write_targets('cd "$D" && touch f', CWD))
        self.assertIsNone(ma_bash.write_targets('cd - && touch f', CWD))

    def test_read_paths_follow_the_same_rule(self):
        self.assertEqual(ma_bash.read_paths('cd x && cat a/b', CWD), [P('/p/x/a/b')])
        self.assertEqual(sorted(ma_bash.read_paths('cd x; cat a/b', CWD)), sorted([P('/p/a/b'), P('/p/x/a/b')]))


class VariableTest(unittest.TestCase):
    """`NAME=literal` is followed only when one closed rule holds (architecture 4.4); every other use stays unknown."""

    def test_unfollowed_variable_paths_are_unknown(self):
        for cmd in ['P=/a; P=/b; cat $P/x', 'P=$(pwd); cat $P/x', 'cat $P/x; P=/a', 'P=/a cat $P/x', 'cat $HOME/x',
                    'P=~/x; cat $P/y', 'false && P=/a; cat $P/x', 'ls /y && P=/a; cat $P/x',
                    'true || P=/a; cat $P/x', '(P=/a); cat $P/x', 'P=/a; export P=/etc; cat $P/x',
                    'P=/a; read P; cat $P/x', 'P=/a; P+=b; cat $P/x', 'P=/a; printf -v P /etc; cat $P/x',
                    'P=/a; printf -vP /etc; cat $P/x', 'P="/a /etc"; cat $P/passwd', "P=/a; bash -c 'cat $P/x'",
                    'P=/a; eval "cat $P/x"', 'P=/a; cat ${P:-/etc}/x', "P=/a; cat '$P'/x", 'IFS=/; P=/a; cat $P/x',
                    'P=/a; cat \\$P/x', 'P=/a; export Q=1; cat $P/x', 'P=/a; for P in /etc; do cat $P/x; done',
                    'P=/a\ncat $P/x | head; P=/b', 'P=/a *; cat $P/x',
                    'P=a*; cat $P/x', 'P=/a; (cat $P/x)  ; unset P; cat $P/y', 'P=/a & cat $P/x',
                    'PWD=/tmp; cd /etc; cat $PWD/x', 'OLDPWD=/a; cd /b; cat $OLDPWD/x', 'PWD=/tmp; cat ${PWD}/x',
                    'RANDOM=1; cat $RANDOM/x', 'SECONDS=1; cat $SECONDS/x',
                    '_=/a; cat $_/x', 'BASH_ARGV0=/a; cat $BASH_ARGV0/x']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(ma_bash.read_paths(cmd, CWD))
        for cmd in ['P=/a; P=/b; echo hi > $P/x', 'false && P=/a; echo hi > $P/x', 'P=/a; export P=/etc; rm $P/x',
                    'echo hi > $HOME/x', 'D=~/x; echo hi > $D/f', 'D=/x; ls; cd $E && touch f']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(ma_bash.write_targets(cmd, CWD))

    def test_literal_variable_expands(self):
        for cmd in ['D=/x/y; cat $D/f', 'D=/x/y\ncat ${D}/f', 'D=/x/y; cat "$D/f"', "D='/x/y'; cat $D/f",
                    'D=/x/y; E=/z; cat $D/f']:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.read_paths(cmd, CWD), [P('/x/y/f')])
        self.assertEqual(ma_bash.read_paths('D=..; cat $D/f', CWD), [P('/f')])
        self.assertEqual(ma_bash.write_targets('D=/x/y; echo hi > $D/f', CWD), [P('/x/y/f')])
        self.assertEqual(ma_bash.write_targets('D=/x/y && echo hi > "${D}/f"', CWD), [P('/x/y/f')])
        self.assertEqual(ma_bash.write_targets('D=/x; E=/y; rm $D/a $E/b', CWD), [P('/x/a'), P('/y/b')])
        self.assertEqual(ma_bash.write_targets('D=/x; ls; cd $D && touch f', CWD), [P('/x/f')])
        self.assertEqual(ma_bash.copy_sources('D=/x; cp $D/a /y', CWD), [P('/x/a')])

    def test_cd_to_a_literal_variable(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp).resolve() / 'dir'
            d.mkdir()
            (d / 'x').write_text('')
            paths = ma_bash.read_paths(f'D={d} && cd "$D" && ls x', CWD)
            self.assertIn(d / 'x', paths)
            self.assertEqual(ma_bash.read_paths(f'P={d}; cat $P/x', CWD), [d / 'x'])
            self.assertEqual(ma_bash.read_paths(f'P={d}; cat ${{P}}/x', CWD), [d / 'x'])
            self.assertEqual(ma_bash.write_targets(f'P={d}; echo hi > $P/out', CWD), [d / 'out'])
            self.assertIsNone(ma_bash.read_paths(f'D={d} && cd "$E" && ls x', CWD))

    def test_hash_inside_a_word_is_not_a_comment(self):
        self.assertEqual(ma_bash.write_targets('echo ${#D}; rm /etc/x', CWD), [P('/etc/x')])
        self.assertEqual(ma_bash.write_targets('echo a#b; rm /etc/x', CWD), [P('/etc/x')])
        self.assertEqual(ma_bash.write_targets('echo a # b; rm /etc/x', CWD), [])


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


class SetsidTest(unittest.TestCase):
    def test_setsid_is_seen_through(self):
        self.assertEqual(ma_bash.write_targets('setsid cp a /etc/b', CWD), [P('/etc/b')])


class CopySourcesTest(unittest.TestCase):
    def test_copy_sources(self):
        self.assertEqual(ma_bash.copy_sources('cp -p docs/agent/t/work/note.md ~/notes/', CWD),
                         [P('/p/docs/agent/t/work/note.md')])
        self.assertEqual(ma_bash.copy_sources('mv a b c/', CWD), [P('/p/a'), P('/p/b')])
        self.assertEqual(ma_bash.copy_sources('ls a', CWD), [])

    def test_copy_sources_follow_cd(self):
        self.assertEqual(ma_bash.copy_sources('cd T && cp work/f ~/out', CWD), [P('/p/T/work/f')])
        self.assertEqual(sorted(ma_bash.copy_sources('cd T; cp work/f ~/out', CWD)),
                         sorted([P('/p/work/f'), P('/p/T/work/f')]))
        self.assertEqual(ma_bash.copy_sources('cd "$D" && cp work/f ~/out', CWD), [P('/p/work/f')])
        self.assertEqual(ma_bash.copy_sources('D=/t; cp $D/f ~/out', CWD), [P('/t/f')])   # a literal variable
        self.assertEqual(ma_bash.copy_sources('cp $D/f ~/out', CWD), [])                # an unknown one


class GitSubcommandsTest(unittest.TestCase):
    def test_git_subcommands(self):
        self.assertEqual(ma_bash.git_subcommands('git add a && git -C x commit -m "m"; ls'), ['add', 'commit'])
        self.assertEqual(ma_bash.git_subcommands('echo "git commit"'), [])
        self.assertEqual(ma_bash.git_subcommands('git "unterminated'), ['?'])

    def test_split_words_still_have_the_shape(self):
        for cmd in ['git "c"ommit -m "$(x)"', "git 'com'mit -m \"$(x)\"", 'git co\\\nmmit -m "$(x)"',
                    '"g"it commit -m "$(x)"', 'g\\\nit commit -m "$(x)"', 'git comm\\it -m "$(x)"']:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.git_subcommands(cmd), ['?'])

    def test_unparsed_text_is_a_commit_only_with_the_shape(self):
        for cmd in ['echo git is a word "unclosed', 'echo "HEAD=$(git rev-parse HEAD)" && git status --porcelain',
                    'echo "$(git log)" ; echo commit', 'git status; echo "$(x)" commit', 'echo `date`; git status',
                    'echo "it is git" "$(x)" ; commit', 'ls "$(x)" | git log']:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.git_subcommands(cmd), [])
        self.assertEqual(ma_bash.git_subcommands('git -c a="x;y" commit'), ['commit'])   # parses; commit counts
        for cmd in ['git -C x commit -m "unclosed', 'git -C "$(a && b)" commit -m y', 'git "unclosed',
                    'git commit -m "$(cat <<\'EOF\'\nfeat\nEOF\n)"', 'x=$(a); git -C x commit -m m',
                    'git -C "$(a; b" commit', 'echo hi && git `x` commit', '(git commit -m "$(x)")']:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.git_subcommands(cmd), ['?'])


class EnvReadsTest(unittest.TestCase):
    def test_env_reads_table(self):
        table = [
            ('env', ['env']), ('env -i', ['env -i']), ('printenv', ['printenv']), ('printenv HOME', ['printenv HOME']),
            ('env | grep KEY', ['env']), ('true && printenv', ['printenv']), ('ls; set', ['set']),
            ('/usr/bin/env', ['/usr/bin/env']), ('command env', ['command env']), ('exec printenv', ['exec printenv']),
            ('nohup env', ['nohup env']), ('timeout 5 env', ['timeout 5 env']), ('FOO=1 env', ['FOO=1 env']),
            ('false || export', ['export']), ('export -p', ['export -p']), ('declare', ['declare']),
            ('typeset -p', ['typeset -p']), ('launchctl getenv PATH', ['launchctl getenv PATH']),
            ('cat /proc/1/environ', ['cat /proc/1/environ']), ('cat /proc/self/environ', ['cat /proc/self/environ']),
            ('cat /proc/$$/environ', ['cat /proc/$$/environ']),
            ('xargs -0 < /proc/self/environ', ['xargs -0 < /proc/self/environ']),
            ("bash -c 'printenv'", ['printenv']), ('env VAR=x printenv', ['env VAR=x printenv']),
            ('env -u HOME', ['env -u HOME']), ('sudo env', ['sudo env']), ('nice -n 5 env', ['nice -n 5 env']),
            ('env FOO=1', ['env FOO=1']), ('cat /proc/self/task/1/environ', ['cat /proc/self/task/1/environ']),
            ('bash -c "cat /proc/self/environ"', ['bash -c cat /proc/self/environ', 'cat /proc/self/environ']),
            ('env nohup', []),
            ('env -i cmd', []), ('env VAR=x cmd', []), ('command env VAR=x cmd', []), ('timeout 5 env -i cmd', []),
            ('set -e', []), ('set -o pipefail', []), ('export VAR=x', []), ('declare -x VAR=1', []),
            ('declare -p HOME', []), ('ls $HOME/x', []), ('echo $HOME', []), ('cat /proc/cpuinfo', []),
            ('launchctl list', []), ('echo env printenv', []), ('ls', []), ('echo "unclosed', []),
            ('echo $(printenv)', ['printenv']), ('echo `env`', ['env']), ('echo "$(printenv)"', ['printenv']),
            ('echo $(echo $(printenv))', ['printenv']), ('echo $(printenv HOME)', ['printenv HOME']),
            ('printenv $(date)', ['printenv $(date)']), ('echo $(date); env', ['env']), ('setsid env', ['setsid env']),
            ('setsid -f printenv', ['setsid -f printenv']),
            ('python3 -c "import os;print(os.environ)"', ['python3 -c import os;print(os.environ)']),
            ('python -c \'import os; os.environ.get("X")\'', ['python -c import os; os.environ.get("X")']),
            ('python3 -c "from os import environ; print(environ)"',
             ['python3 -c from os import environ; print(environ)']),
            ('python3 -Ic "import os; os.getenv(\'X\')"', ["python3 -Ic import os; os.getenv('X')"]),
            ('python3.12 -c "import os; os.environb"', ['python3.12 -c import os; os.environb']),
            ('echo "a $(env) b"', ['env']), ('echo $(date) $(env -i ls) `printenv`', ['printenv']),
            ('echo $(date)', []), ('echo $((1+2))', []), ('echo $((1+$(date)))', []),
            ('echo $(( $(printenv) ))', ['printenv']), ('python3 -c "print(1)"', []), ('setsid ls', []),
            ("echo '$(printenv)'", []), ('python3 script.py -c os.environ', []),
            ('echo $(printenv', ['printenv']), ('echo $(date', []),
        ]
        for cmd, expected in table:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.env_reads(cmd), expected)


class EnvReadsHeredocTest(unittest.TestCase):
    """Criterion 12: the body of a quoted-delimiter heredoc is data (a note with a backticked `export`)."""
    BT = chr(96)

    def test_quoted_body_is_data(self):
        bt = self.BT
        cases = [
            f"cat > notes.md <<'EOF'\nuse {bt}export{bt} here\nEOF",
            "python3 - <<'EOF'\nexport\nEOF",
            f"cat << 'EOF'\n{bt}export{bt}\nEOF",
            f"cat <<-'EOF'\n\t{bt}export{bt}\n\tEOF",
            f'cat <<"EOF"\n{bt}export{bt}\nEOF',
            f"cat <<\\EOF\n{bt}export{bt}\nEOF",
            f"cat <<'EOF'\n$(printenv)\nEOF",
            f"cat <<'A' <<'B'\n{bt}export{bt}\nA\n{bt}env{bt}\nB",
            f"cat > a <<'EOF'\n{bt}export{bt}\nEOF\necho hi",
            f"python3 - <<'EOF'\nimport sys\nprint('{bt}export{bt}')\nEOF",
            f"cat <<'EOF' | wc -l\n{bt}export{bt}\nEOF",
        ]
        for cmd in cases:
            with self.subTest(cmd=cmd):
                self.assertEqual(ma_bash.env_reads(cmd), [])

    def test_commands_around_the_body_are_still_read(self):
        bt = self.BT
        self.assertEqual(ma_bash.env_reads(f"cat <<'EOF'\n{bt}export{bt}\nEOF\nenv"), ['env'])
        self.assertEqual(ma_bash.env_reads("env <<'EOF'\nx\nEOF"), ['env'])

    def test_unquoted_body_keeps_substitution(self):
        bt = self.BT
        self.assertEqual(ma_bash.env_reads("cat <<EOF\n$(printenv)\nEOF"), ['printenv'])
        self.assertEqual(ma_bash.env_reads(f"cat <<EOF\n{bt}env{bt}\nEOF"), ['env'])
        self.assertEqual(ma_bash.env_reads(f'cat <<"EOF"\n$(printenv)\nEOF'), [])

    def test_heredoc_inside_quotes_is_not_trusted(self):
        bt = self.BT
        self.assertNotEqual(ma_bash.env_reads(f'bash -c "cat <<\'EOF\'\n{bt}export{bt}\nEOF"'), [])
        self.assertNotEqual(ma_bash.env_reads(f"echo \"<<'EOF'\"\n{bt}export{bt}\nEOF"), [])

    def test_here_string_is_not_a_heredoc(self):
        self.assertEqual(ma_bash.env_reads("cat <<< '$(printenv)'"), [])
        self.assertEqual(ma_bash.env_reads('cat <<< "$(printenv)"'), ['printenv'])


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


class GitMvTest(unittest.TestCase):
    def test_targets(self):
        self.assertEqual(ma_bash.write_targets('git mv a b', CWD), [P('/p/a'), P('/p/b')])
        self.assertEqual(ma_bash.write_targets('cd src && git mv x y', CWD), [P('/p/src/x'), P('/p/src/y')])
        self.assertEqual(ma_bash.write_targets('export FOO=1; git mv a b', CWD), [P('/p/a'), P('/p/b')])

    def test_cannot_tell(self):
        for cmd in ('git mv a', 'git mv -k a b', 'git mv -- a b', 'git mv a b c', 'git mv $A b', 'git -C sub mv a b',
                    'echo docs/agent | xargs git mv a b', 'GIT_DIR=x git mv a b', 'GIT_WORK_TREE=/x git mv a b',
                    'env GIT_DIR=x git mv a b', 'env -C dir git mv a b', 'sudo git mv a b',
                    'export GIT_WORK_TREE=/outside; git mv a b', 'GIT_DIR=/x; git mv a b',
                    'declare -x GIT_DIR=/x && git mv a b', 'set -a; GIT_DIR=/x; git mv a b',
                    'typeset GIT_DIR=/x; git mv a b', '. ./env.sh; git mv a b',
                    'source env.sh && git mv a b'):
            with self.subTest(cmd=cmd):
                self.assertIsNone(ma_bash.write_targets(cmd, CWD))

    def test_unchanged(self):
        self.assertEqual(ma_bash.write_targets('echo x | xargs git status', CWD), [])
        self.assertTrue(ma_bash.git_mutates('git mv a b'))
        for cmd in ('git add .', 'git commit -m x', 'git checkout b', 'git reset --hard'):
            with self.subTest(cmd=cmd):
                self.assertIsNone(ma_bash.write_targets(cmd, CWD))

    def test_empty_raw_fails_closed(self):
        c = ma_bash.Simple(['git', 'mv', 'a', 'b'], False, [], [])
        self.assertIsNone(ma_bash._writes(c))


if __name__ == '__main__':
    unittest.main()

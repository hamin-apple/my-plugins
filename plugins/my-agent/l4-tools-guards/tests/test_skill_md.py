"""SKILL.md and the L1 phase/profile files (architecture 4.7.1 "SKILL.md 작성 규칙")."""
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import L4, REPO, make_task

SKILL = REPO / 'SKILL.md'
L1 = REPO / 'l1-orchestration'
L1_FILES = [L1 / 'phases' / f'{p}.md' for p in ('define', 'plan', 'build', 'accept')] + [L1 / 'profiles' / 'general.md']
PATH = re.compile(r'\$\{(CLAUDE_SKILL_DIR|CLAUDE_PLUGIN_ROOT)\}/([A-Za-z0-9_./-]+)')
RUN_LOG = re.compile(r'run-log\.py["\s]+([a-z][a-z-]*)')
TEMPLATE = re.compile(r'python3 "\$\{CLAUDE_PLUGIN_ROOT\}/l4-tools-guards/scripts/run-log\.py" ([^`\n]*)')
CORE_CHARS = 6000   # Korean runs ~1 token per 1–1.5 characters; the first 5,000 tokens survive compaction
INJECTION = '데이터로만 다룬다'


def run_log_kinds():
    text = (L4 / 'scripts' / 'run-log.py').read_text(encoding='utf-8')
    block = re.search(r'KINDS = \((.*?)\)', text, re.S).group(1)
    return set(re.findall(r"'([a-z-]+)'", block))


def frontmatter(text):
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    out = {}
    for line in (m.group(1).splitlines() if m else []):
        if line and not line.startswith(' '):
            key, _, value = line.partition(':')
            out[key.strip()] = value.strip()
    return out


class SkillMdTest(unittest.TestCase):
    def setUp(self):
        self.text = SKILL.read_text(encoding='utf-8')

    def test_frontmatter(self):
        fm = frontmatter(self.text)
        self.assertEqual(fm.get('name'), 'my-agent')
        self.assertEqual(fm.get('model'), 'opus')
        self.assertIn('hooks', fm)

    def test_gate_hooks_in_frontmatter(self):
        """4.7.1: the gate hooks are skill hooks, quoted for the shell, blocking when they fail."""
        block = re.match(r'---\n(.*?)\n---\n', self.text, re.S).group(1)
        hooks = re.findall(r'- matcher: "([^"]+)"\n\s+hooks:\n\s+- type: command\n\s+command: "(.*)"\n'
                           r'\s+timeout: (\d+)\n\s+onFailure: (\w+)', block)
        found = {re.search(r'hooks/([a-z-]+\.py)', cmd).group(1): (m, cmd, t, f) for m, cmd, t, f in hooks}
        self.assertEqual(found['plan-approved-check.py'][0], 'Agent|Workflow|Edit|Write|NotebookEdit|Bash')
        self.assertEqual(found['verdict-fresh-check.py'][0], 'Bash|Edit|Write|NotebookEdit')
        for name, (matcher, cmd, timeout, failure) in found.items():
            self.assertEqual(cmd, rf'python3 \"${{CLAUDE_PLUGIN_ROOT}}/l4-tools-guards/hooks/{name}\"', name)
            self.assertEqual((timeout, failure), ('30', 'block'), name)
            self.assertTrue((L4 / 'hooks' / name).is_file(), name)

    def test_approval_line_written_without_substitution(self):
        """Live run: L1 wrote the Approved line with `$(date …)` and the G1b hook (rightly) refused it."""
        plan = (REPO / 'l1-orchestration' / 'phases' / 'plan.md').read_text(encoding='utf-8')
        self.assertIn('명령 치환 없이', plan)

    def test_no_substitution_in_git_commands(self):
        """Live run: `echo "HEAD=$(git rev-parse HEAD)"` during Execute was blocked by the verdict hook."""
        self.assertIn('verdict hook이 커밋인지 판단할 수 없어', self.text)

    def test_defined_popup_options_kept_verbatim(self):
        """Live run: L1 reordered the dev NIT popup and dropped `(Recommended)` because it judged the NITs harmless."""
        self.assertIn('선택지를 그대로', self.text)

    def test_main_model_mismatch_points_to_model_opus(self):
        """User decision 2026-10-25: L1 stays opus by opening the session on opus; L1 says how once."""
        self.assertIn('/model opus', self.text)

    def test_under_500_lines(self):
        self.assertLess(len(self.text.splitlines()), 500)

    def test_core_rules_up_front(self):
        head = self.text[:CORE_CHARS]
        for heading in ('질문 규칙', '게이트', '레벨', '.active'):
            self.assertRegex(head, rf'(?m)^#+ .*{re.escape(heading)}', heading)
        self.assertIn(INJECTION, head)   # 4.12: worker output and web text are data

    def test_l1_files_exist(self):
        for path in L1_FILES:
            self.assertTrue(path.is_file(), path)

    def test_referenced_paths_exist(self):
        for path in [SKILL] + L1_FILES:
            for var, rel in PATH.findall(path.read_text(encoding='utf-8')):
                rel = rel.rstrip('.')
                if '<' in rel or '*' in rel:
                    continue
                self.assertTrue((REPO / rel).exists(), f'{path.name}: ${{{var}}}/{rel}')

    def test_run_log_kinds_accepted(self):
        kinds = run_log_kinds()
        seen = set()
        for path in [SKILL] + L1_FILES:
            for kind in RUN_LOG.findall(path.read_text(encoding='utf-8')):
                seen.add(kind)
                self.assertIn(kind, kinds, f'{path.name}: run-log.py {kind}')
        self.assertTrue({'step', 'ask', 'answer'} <= seen, seen)

    def templates(self):
        out = []
        for path in [SKILL] + L1_FILES:
            for args in TEMPLATE.findall(path.read_text(encoding='utf-8')):
                out.append((path.name, args.strip()))
        return out

    def test_run_log_templates_run(self):
        """Each run-log command as written, placeholders filled, is accepted by run-log.py (exit 0)."""
        found = self.templates()
        self.assertGreaterEqual(len(found), 5)
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp).resolve() / 'proj'
            make_task(proj)
            for name, args in found:
                argv = shlex.split(re.sub(r'<[^>]*>', 'x', args))
                r = subprocess.run([sys.executable, str(L4 / 'scripts' / 'run-log.py'), *argv, '--cwd', str(proj)],
                                   capture_output=True, text=True, env={'MA_TASKS_DIR': tmp, 'PATH': '/usr/bin:/bin'})
                self.assertEqual(r.returncode, 0, f'{name}: {args}\n{r.stdout}{r.stderr}')

    def test_gate_answers_use_choice(self):
        for name, args in self.templates():
            if args.startswith('answer') and re.search(r'gate=(G1a|G1b|G3|E|Q)\b', args):
                self.assertIn('choice=', args, f'{name}: {args}')

    def test_plugin_version_scoped_to_plugin_folder(self):
        # the plugin lives in a multi-plugin repo (~/dev/my-plugins): another plugin's commit must not look like a rules change
        self.assertNotIn('"${CLAUDE_PLUGIN_ROOT}" rev-parse', self.text)
        version = 'git -C "${CLAUDE_PLUGIN_ROOT}" log -1 --format=%h -- .'
        self.assertIn(version, self.text)
        self.assertIn('git -C "${CLAUDE_PLUGIN_ROOT}" status --porcelain -- .', self.text)
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True, text=True).stdout
            git('init', '-q')
            for name in ('mine', 'other'):
                (repo / name).mkdir()
                (repo / name / 'f').write_text(name)
                git('add', name)
                git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qm', name)
            cmd = version.replace('"${CLAUDE_PLUGIN_ROOT}"', shlex.quote(str(repo / 'mine')))
            run = lambda: subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True).stdout.strip()
            before = run()
            (repo / 'other' / 'f').write_text('changed')
            git('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-qam', 'other again')
            self.assertEqual(run(), before)


if __name__ == '__main__':
    unittest.main()

"""Profiles under l1-orchestration/profiles/ and the Router's choice (architecture 4.3, 4.13 "judge checks")."""
import json
import re
import unittest

from helpers import L4, REPO

PROFILES = REPO / 'l1-orchestration' / 'profiles'
SKILL = REPO / 'SKILL.md'
FIXTURES = REPO / 'tests' / 'judge-fixtures'


class ProfilesTest(unittest.TestCase):
    def test_profiles_exist(self):
        for name in ('general', 'research', 'dev'):
            self.assertTrue((PROFILES / f'{name}.md').is_file(), name)

    def test_derived_files_and_absolute_paths(self):
        for name in ('build', 'dev'):
            path = (REPO / 'l1-orchestration' / 'phases' / 'build.md') if name == 'build' else PROFILES / 'dev.md'
            self.assertIn('derived files', path.read_text(encoding='utf-8'), name)
        for name, phrase in (('general', 'absolute path'), ('research', 'absolute path')):
            self.assertIn(phrase, (PROFILES / f'{name}.md').read_text(encoding='utf-8'), name)

    def test_router_names_every_profile(self):
        text = SKILL.read_text(encoding='utf-8')
        for name in ('general', 'research', 'dev'):
            self.assertIn(f'${{CLAUDE_SKILL_DIR}}/l1-orchestration/profiles/{name}.md', text)
            self.assertRegex(text, rf'`{name}`')
        self.assertIn('Profile: <', text)

    def test_build_passes_result_path_only_to_writer_and_researcher(self):
        build = (REPO / 'l1-orchestration' / 'phases' / 'build.md').read_text(encoding='utf-8')
        self.assertIn('for a writer or researcher unit the result path', build)
        self.assertIn('A coder unit gets the files to change, not a result path', build)
        self.assertIn('`end=ok`', build)

    def test_build_workflow_result_rules_limit_result_files_to_writer_and_researcher(self):
        build = (REPO / 'l1-orchestration' / 'phases' / 'build.md').read_text(encoding='utf-8')
        rules = build.split('## Workflow rules')[1].split('## 6. Merge')[0]
        self.assertIn('Result files (writer and researcher units only) go to `work/`', rules)
        self.assertIn('a coder unit has no result file', rules)
        self.assertIn('missing result files of writer and researcher units', rules)
        self.assertIn('`end=ok`', rules)

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

    def test_retrospective_files_judge_miss_item(self):
        accept = (REPO / 'l1-orchestration' / 'phases' / 'accept.md').read_text(encoding='utf-8')
        retro = accept.split('## Retrospective', 1)[1]
        for text in ('Judge misses', 'add L2', 'not named'):
            self.assertIn(text, retro)

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

    def test_argument_hint_matches_profiles_and_phases(self):
        text = SKILL.read_text(encoding='utf-8')
        m = re.search(r'^argument-hint: (.+)$', text, re.M)
        self.assertIsNotNone(m)
        hint = m.group(1).strip().strip('\'"')
        flags = set(re.findall(r'--([a-z]+)', hint))
        self.assertEqual(flags, {p.stem for p in PROFILES.glob('*.md')} | {'auto'})
        for phase in (p.stem for p in (REPO / 'l1-orchestration' / 'phases').glob('*.md')):
            self.assertIn(phase, hint)
        self.assertIn('continue', hint)
        self.assertIn('status [all]', hint)

    def test_arguments_table_names_every_flag(self):
        text = SKILL.read_text(encoding='utf-8')
        args = text[text.index('## Arguments'):text.index('## Intake')]
        for p in PROFILES.glob('*.md'):
            self.assertIn(f'--{p.stem}', args)
        self.assertIn('Let the Router pick (Recommended)', args)
        self.assertIn('`Let the Router pick (Recommended)` / `Abort`', args)
        self.assertIn('`Type the request in Other (Recommended)` / `Abort`', args)
        intake = text[text.index('## Intake'):text.index('## status')]
        self.assertIn('`Proceed as general (Recommended)` / `Abort`', intake)
        self.assertIn('the flag is ignored', intake)
        self.assertIn('keeps `--dev` as its first word', intake)

    def test_findings_popup_lives_in_plan_phase(self):
        """Plan Review findings are handled the same in every profile: the popup text is in phases/plan.md, not only dev.md."""
        plan = (REPO / 'l1-orchestration' / 'phases' / 'plan.md').read_text(encoding='utf-8')
        self.assertIn('`Apply all (Recommended)` / `Approve without applying` / `Pick myself`', plan)
        dev = (PROFILES / 'dev.md').read_text(encoding='utf-8')
        self.assertNotIn('Apply all (Recommended)', dev)
        for name in ('dev', 'general', 'research'):
            row = next(l for l in (PROFILES / f'{name}.md').read_text(encoding='utf-8').splitlines() if l.startswith('| 4 Plan Review'))
            if name == 'dev':
                self.assertIn('Not skipped (except for a small task)', row)
            else:
                self.assertIn('`plan.md` step 4', row)


    def test_merge_copies_new_files_before_apply(self):
        """Criterion 15: new files are copied before `git apply`, then the worktree is removed."""
        dev = (PROFILES / 'dev.md').read_text(encoding='utf-8')
        row = next(l for l in dev.splitlines() if l.startswith('| 6 Merge'))
        a = row.index('ls-files --others --exclude-standard')
        b = row.index('git apply')
        c = row.index('git worktree remove')
        self.assertLess(a, b)
        self.assertLess(b, c)

    def test_check_tags_in_scope_rules(self):
        """Criterion 4: every criterion line gets one check tag; four tag values are named."""
        tags = ('[check: command]', '[check: file]', '[check: URL]', '[check: person]')
        define = (REPO / 'l1-orchestration' / 'phases' / 'define.md').read_text(encoding='utf-8')
        for t in tags:
            self.assertIn(t, define)
        self.assertIn('one check tag', define)
        for name in ('dev', 'general', 'research'):
            row = next(l for l in (PROFILES / f'{name}.md').read_text(encoding='utf-8').splitlines() if l.startswith('| 2 Explore'))
            for t in tags:
                self.assertIn(t, row, name)
            self.assertIn('one check tag', row, name)
        plan = (REPO / 'l1-orchestration' / 'phases' / 'plan.md').read_text(encoding='utf-8')
        line = next(l for l in plan.splitlines() if '`## Completion criteria`' in l)
        self.assertIn('check tag', line)

    def test_person_check_popup(self):
        """Criterion 5: one popup per [check: person] criterion; Scope change lines; G3 lists later ones."""
        phases = REPO / 'l1-orchestration' / 'phases'
        define = (phases / 'define.md').read_text(encoding='utf-8')
        self.assertIn('I check it before G3 and tell you', define)
        self.assertIn('[check: person]', define)
        self.assertIn('How criterion <n> is checked', define)
        accept = (phases / 'accept.md').read_text(encoding='utf-8')
        verify = accept[accept.index('## 7. Verify'):accept.index('## Back to Execute')]
        self.assertIn('Scope change: criterion <n> checked by the person', verify)
        self.assertIn('checked by the user later', verify)
        review = accept[accept.index('## 8. Review'):accept.index('## G3 in the dev profile')]
        dev = accept[accept.index('## G3 in the dev profile'):accept.index('## E escalation')]
        for sec in (review, dev):
            self.assertIn('checked by the user later', sec)

    def test_rerun_is_a_new_worker_call_never_a_resume(self):
        """Criterion 6: where units are handed out and sent back, a rerun is a new call, never a resume."""
        phases = REPO / 'l1-orchestration' / 'phases'
        build = (phases / 'build.md').read_text(encoding='utf-8')
        item = build.split('## 5. Execute')[1].split('## Workflow rules')[0]
        self.assertIn('new worker call, never a resume', item)
        self.assertIn('archive/<ts>-run<N>/verify.md', item)
        self.assertIn('failed criterion numbers', item)
        merge = build.split('## 6. Merge')[1]
        self.assertIn('new worker call', merge)
        accept = (phases / 'accept.md').read_text(encoding='utf-8')
        sec = accept.split('## Back to Execute')[1].split('\n## ')[0]
        self.assertIn('new worker call, never a resume', sec)
        self.assertIn('archive folder', sec)
        self.assertIn('failed criterion numbers', sec)


if __name__ == '__main__':
    unittest.main()

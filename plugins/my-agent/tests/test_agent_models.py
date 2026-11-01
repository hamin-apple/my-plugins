"""agent-models.py and ma_models: presets from <data folder>/agent-models.json over the agent definition values."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import L4, REPO, run_script

sys.path.insert(0, str(L4 / 'lib'))
import ma_models  # noqa: E402

SCRIPT = L4 / 'scripts' / 'agent-models.py'
EXAMPLE = REPO / 'docs' / 'agent-models.example.json'
AGENTS = ('architect', 'plan-reviewer', 'verifier', 'reviewer', 'gate-analyst', 'explorer', 'researcher', 'writer', 'coder')
DEFINITION = {'architect': ('opus', 'high'), 'plan-reviewer': ('sonnet', 'high'), 'verifier': ('opus', 'high'),
              'reviewer': ('sonnet', 'high'), 'gate-analyst': ('sonnet', 'high'), 'explorer': ('sonnet', 'low'),
              'researcher': ('sonnet', 'medium'), 'writer': ('sonnet', 'medium'), 'coder': ('sonnet', 'medium')}


def rows(stdout):
    """(header, {agent: (model, effort, pass)}) from a `show` output."""
    lines = stdout.splitlines()
    out = {}
    for line in lines[1:]:
        name, model, effort, pass_ = line.split()
        out[name] = (model.removeprefix('model='), effort.removeprefix('effort='), pass_.removeprefix('pass='))
    return lines[0], out


class AgentModelsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.file = self.data / 'agent-models.json'

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, obj):
        self.file.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding='utf-8')

    def use_example(self):
        self.file.write_text(EXAMPLE.read_text(encoding='utf-8'), encoding='utf-8')

    def run_cli(self, *args):
        return run_script(SCRIPT, *args, '--data-dir', str(self.data), drop=('MA_TASKS_DIR',))

    def show(self, profile, preset):
        r = self.run_cli('show', '--profile', profile, '--preset', preset)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, '')
        return rows(r.stdout)

    def assertRejected(self, r, text):
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertEqual(r.stdout, '')
        self.assertEqual(len(r.stderr.splitlines()), 1, r.stderr)
        self.assertTrue(r.stderr.startswith('agent-models: '), r.stderr)
        self.assertIn(text, r.stderr)

    def test_no_file_gives_definition_values(self):
        header, got = self.show('dev', 'standard')
        self.assertEqual(header, 'preset: dev/standard (no file: definition values)')
        self.assertEqual(list(got), list(AGENTS))
        self.assertEqual({a: v[:2] for a, v in got.items()}, DEFINITION)
        self.assertEqual({v[2] for v in got.values()}, {'-'})

    def test_exact_line_format(self):
        r = self.run_cli('show', '--profile', 'dev', '--preset', 'standard')
        self.assertEqual(r.stdout.splitlines()[1], 'architect      model=opus   effort=high    pass=-')
        self.assertEqual(r.stdout.splitlines()[2], 'plan-reviewer  model=sonnet effort=high    pass=-')

    def test_empty_and_braces_files_mean_no_file(self):
        for text in ('', '  \n', '{}'):
            self.write(text)
            _, got = self.show('dev', 'standard')
            self.assertEqual({a: v[:2] for a, v in got.items()}, DEFINITION, text)
            r = self.run_cli('presets', '--profile', 'dev')
            self.assertEqual((r.returncode, r.stdout), (0, 'none\n'), text)

    def test_profile_without_presets_is_no_file(self):
        self.write({'general': {'economy': {'coder': {'effort': 'low'}}}})
        r = self.run_cli('presets', '--profile', 'dev')
        self.assertEqual((r.returncode, r.stdout), (0, 'none\n'))
        self.assertEqual(self.show('dev', 'standard')[0], 'preset: dev/standard (no file: definition values)')

    def test_example_standard_equals_definition_for_all_profiles(self):
        self.use_example()
        for profile in ('general', 'research', 'dev'):
            header, got = self.show(profile, 'standard')
            self.assertEqual(header, f'preset: {profile}/standard (file {self.file})')
            self.assertEqual({a: v[:2] for a, v in got.items()}, DEFINITION, profile)
            self.assertEqual({v[2] for v in got.values()}, {'-'}, profile)

    def test_partial_entry_keeps_definition_model(self):
        self.write({'dev': {'lean': {'coder': {'effort': 'low'}}}})
        _, got = self.show('dev', 'lean')
        self.assertEqual(got['coder'], ('sonnet', 'low', 'effort'))
        self.assertEqual({a: v[:2] for a, v in got.items() if a != 'coder'},
                         {a: v for a, v in DEFINITION.items() if a != 'coder'})
        self.assertEqual({v[2] for a, v in got.items() if a != 'coder'}, {'-'})

    def test_economy_and_max_columns(self):
        self.use_example()
        header, got = self.show('dev', 'economy')
        self.assertEqual(header, f'preset: dev/economy (file {self.file})')
        self.assertEqual(got, {
            'architect': ('sonnet', 'medium', 'model,effort'), 'plan-reviewer': ('sonnet', 'medium', 'effort'),
            'verifier': ('sonnet', 'medium', 'model,effort'), 'reviewer': ('sonnet', 'medium', 'effort'),
            'gate-analyst': ('sonnet', 'medium', 'effort'), 'explorer': ('sonnet', 'low', '-'),
            'researcher': ('sonnet', 'medium', '-'), 'writer': ('sonnet', 'medium', '-'),
            'coder': ('sonnet', 'low', 'effort')})
        _, got = self.show('dev', 'max')
        for a in ('architect', 'plan-reviewer', 'verifier', 'reviewer', 'gate-analyst'):
            self.assertEqual(got[a][:2], ('opus', 'xhigh'), a)
        self.assertEqual(got['plan-reviewer'][2], 'model,effort')
        self.assertEqual(got['architect'][2], 'effort')
        self.assertEqual(got['coder'], ('sonnet', 'medium', '-'))

    def test_presets_lines(self):
        self.use_example()
        r = self.run_cli('presets', '--profile', 'dev')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, 'standard\neconomy: judges sonnet/medium, coder sonnet/low\nmax: judges opus/xhigh\n')

    def test_presets_ordering_and_counts(self):
        self.write({'dev': {'b': {'coder': {'effort': 'low'}}, 'standard': {}, 'a': {'writer': {'model': 'haiku'}}}})
        r = self.run_cli('presets', '--profile', 'dev')
        self.assertEqual(r.stdout.splitlines(), ['standard', 'b: coder sonnet/low', 'a: writer haiku/medium'])
        self.write({'dev': {'b': {'coder': {'effort': 'low'}}, 'a': {}}})
        self.assertEqual(self.run_cli('presets', '--profile', 'dev').stdout.splitlines(), ['b: coder sonnet/low', 'a'])
        self.write({'dev': {'only': {'coder': {'effort': 'low'}}}})
        self.assertEqual(self.run_cli('presets', '--profile', 'dev').stdout.splitlines(), ['only: coder sonnet/low'])

    def test_judges_not_grouped_when_they_differ(self):
        self.write({'dev': {'p': {'architect': {'effort': 'max'}, 'reviewer': {'model': 'haiku'}}}})
        self.assertEqual(self.run_cli('presets', '--profile', 'dev').stdout,
                         'p: architect opus/max, reviewer haiku/high\n')

    def test_rejections(self):
        cases = [
            ('{"dev": ', 'invalid JSON in'),
            ({'devv': {}}, 'unknown profile "devv" (profiles: general, research, dev)'),
            ({'dev': {'economy': {'codr': {}}}}, 'dev/economy: unknown agent "codr"'),
            ({'dev': {'economy': {'main': {}}}},
             'dev/economy: unknown agent "main" (the main session stays opus and has no entry)'),
            ({'dev': {'economy': {'coder': {'model': 'gpt'}}}},
             'dev/economy/coder: unknown model "gpt" (one of: opus, sonnet, haiku, fable)'),
            ({'dev': {'max': {'verifier': {'effort': 'ultra'}}}},
             'dev/max/verifier: unknown effort "ultra" (one of: low, medium, high, xhigh, max)'),
            ({'dev': {'economy': []}}, 'dev/economy: preset is not a dictionary'),
            ({'dev': {'economy': {'coder': 'low'}}}, 'dev/economy/coder: agent entry is not a dictionary'),
        ]
        for content, cause in cases:
            with self.subTest(cause=cause):
                self.write(content)
                self.assertRejected(self.run_cli('show', '--profile', 'dev', '--preset', 'standard'), cause)
                self.assertRejected(self.run_cli('presets', '--profile', 'dev'), cause)

    def test_unknown_preset_lists_presets(self):
        self.use_example()
        r = self.run_cli('show', '--profile', 'dev', '--preset', 'fast')
        self.assertRejected(r, 'dev has no preset "fast" (presets: standard, economy, max)')

    def test_bad_arguments_exit_2(self):
        self.assertEqual(self.run_cli('show', '--profile', 'dev').returncode, 2)
        self.assertEqual(self.run_cli('bogus').returncode, 2)

    def plan(self, body):
        p = self.data / 'plan.md'
        p.write_text(body, encoding='utf-8')
        return p

    def test_show_plan_table(self):
        p = self.plan('# Plan\n\n## Models\n\nPreset: economy\n\n| Agent | Model | Effort | Note |\n|---|---|---|---|\n'
                      '| architect | sonnet | medium | |\n| coder | sonnet | medium | change: effort low → medium |\n'
                      '\nRecommendation: x — y\n\n## Estimate\n- 1\n')
        r = self.run_cli('show', '--plan', str(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        header, got = rows(r.stdout)
        self.assertEqual(header, 'preset: economy (plan.md ## Models)')
        self.assertEqual(got['architect'], ('sonnet', 'medium', 'model,effort'))
        self.assertEqual(got['coder'], ('sonnet', 'medium', '-'))
        self.assertEqual(got['verifier'], ('opus', 'high', '-'))   # missing from the table: definition values
        self.assertEqual(list(got), list(AGENTS))

    def test_show_plan_rejects_bad_values(self):
        head = '## Models\n\nPreset: economy\n\n| Agent | Model | Effort | Note |\n|---|---|---|---|\n'
        for row, cause in (('| coder | gpt | low | |', 'unknown model "gpt"'),
                           ('| coder | sonnet | ultra | |', 'unknown effort "ultra"'),
                           ('| codr | sonnet | low | |', 'unknown agent "codr"')):
            with self.subTest(row=row):
                self.assertRejected(self.run_cli('show', '--plan', str(self.plan(head + row + '\n'))), cause)
        self.assertRejected(self.run_cli('show', '--plan', str(self.plan('# Plan\n'))), '## Models')
        self.assertRejected(self.run_cli('show', '--plan', str(self.data / 'missing.md')), 'missing.md')

    def test_example_file_loads(self):
        data = json.loads(EXAMPLE.read_text(encoding='utf-8'))
        self.assertEqual(list(data), ['general', 'research', 'dev'])
        for profile in data.values():
            self.assertEqual(list(profile), ['standard', 'economy', 'max'])
            self.assertEqual(list(profile['standard']), list(AGENTS))
        ma_models.validate(data)   # raises ModelsError on a bad file


if __name__ == '__main__':
    unittest.main()

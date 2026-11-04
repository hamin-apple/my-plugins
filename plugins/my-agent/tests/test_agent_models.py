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

    def use_example(self, inline=False):
        """The example file; by default without its `inline` presets (the 0.10.0 content)."""
        data = json.loads(EXAMPLE.read_text(encoding='utf-8'))
        if not inline:
            for profile, presets in data.items():
                for section in (presets.values() if profile == 'codex' else [presets]):
                    section.pop('inline', None)
        self.write(data)

    def run_cli(self, *args, host='claude'):
        return run_script(SCRIPT, *args, '--data-dir', str(self.data), env={'MA_HOST': host}, drop=('MA_TASKS_DIR',))

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
        self.assertEqual(list(data), ['general', 'research', 'dev', 'codex'])
        for profile in (data[k] for k in ('general', 'research', 'dev')):
            self.assertEqual(list(profile), ['standard', 'economy', 'max', 'inline'])
            self.assertEqual(list(profile['standard']), list(AGENTS))
        ma_models.validate(data)   # raises ModelsError on a bad file

    # --- Codex host: the `codex` section of the file ---

    def codex(self, *args):
        return self.run_cli(*args, host='codex')

    def codex_show(self, profile, preset):
        r = self.codex('show', '--profile', profile, '--preset', preset)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stderr, '')
        return r.stdout

    def test_codex_show_with_example_file(self):
        self.use_example()
        self.assertEqual(self.codex_show('dev', 'standard'), (
            f'preset: dev/standard (file {self.file}, codex section)\n'
            'architect      model=-          effort=high    pass=effort\n'
            'plan-reviewer  model=gpt-6-luna effort=high    pass=model,effort\n'
            'verifier       model=-          effort=high    pass=effort\n'
            'reviewer       model=gpt-6-luna effort=high    pass=model,effort\n'
            'gate-analyst   model=gpt-6-luna effort=high    pass=model,effort\n'
            'explorer       model=gpt-6-luna effort=low     pass=model,effort\n'
            'researcher     model=gpt-6-luna effort=medium  pass=model,effort\n'
            'writer         model=gpt-6-luna effort=medium  pass=model,effort\n'
            'coder          model=gpt-6-luna effort=medium  pass=model,effort\n'))

    def test_codex_without_section_is_no_override(self):
        for content in (None, '{}', {'dev': {'standard': {'coder': {'effort': 'low'}}}}):
            with self.subTest(content=content):
                if content is None:
                    self.file.unlink(missing_ok=True)
                else:
                    self.write(content)
                header, got = rows(self.codex_show('dev', 'standard'))
                self.assertEqual(header, 'preset: dev/standard (no codex section: no override)')
                self.assertEqual(list(got), list(AGENTS))
                self.assertEqual(set(got.values()), {('-', '-', '-')})
        r = self.codex('show', '--profile', 'dev', '--preset', 'fast')
        self.assertRejected(r, 'dev has no preset "fast" (presets: none)')
        self.assertEqual(self.codex('presets', '--profile', 'dev').stdout, 'none\n')

    def test_codex_rejects_unknown_models_and_efforts(self):
        cases = [
            ('gpt-9', 'codex/dev/economy/coder: unknown model "gpt-9" (one of: gpt-6-luna, gpt-5.6-terra, gpt-5.6-luna)'),
            ('codex-auto-review', 'codex/dev/economy/coder: unknown model "codex-auto-review"'),
            ('sonnet', 'codex/dev/economy/coder: unknown model "sonnet"'),
        ]
        for model, cause in cases:
            with self.subTest(model=model):
                self.write({'codex': {'dev': {'economy': {'coder': {'model': model}}}}})
                for host in ('codex', 'claude'):
                    self.assertRejected(self.run_cli('show', '--profile', 'dev', '--preset', 'standard', host=host), cause)
        self.write({'codex': {'dev': {'economy': {'coder': {'effort': 'ultra'}}}}})
        self.assertRejected(self.codex('presets', '--profile', 'dev'), 'codex/dev/economy/coder: unknown effort "ultra"')
        self.write({'codex': {'devv': {}}})
        self.assertRejected(self.codex('presets', '--profile', 'dev'), 'codex: unknown profile "devv"')
        self.write({'codex': {'dev': {'economy': {'codr': {}}}}})
        self.assertRejected(self.codex('presets', '--profile', 'dev'), 'codex/dev/economy: unknown agent "codr"')

    def test_claude_output_ignores_codex_section(self):
        self.use_example()
        with_section = json.loads(self.file.read_text(encoding='utf-8'))
        self.assertIn('codex', with_section)
        outs = {}
        for key, data in (('with', with_section), ('without', {k: v for k, v in with_section.items() if k != 'codex'})):
            self.write(data)
            outs[key] = [self.run_cli(*a).stdout for a in (
                ('show', '--profile', 'dev', '--preset', 'standard'), ('show', '--profile', 'general', '--preset', 'max'),
                ('presets', '--profile', 'dev'), ('presets', '--profile', 'research'))]
        self.assertEqual(outs['with'], outs['without'])
        self.assertTrue(all(outs['with']))

    def test_codex_show_plan(self):
        head = '## Models\n\nPreset: economy\n\n| Agent | Model | Effort | Note |\n|---|---|---|---|\n'
        p = self.plan(head + '| coder | gpt-6-luna | low | |\n| architect | - | high | |\n')
        r = self.codex('show', '--plan', str(p))
        self.assertEqual(r.returncode, 0, r.stderr)
        header, got = rows(r.stdout)
        self.assertEqual(header, 'preset: economy (plan.md ## Models)')
        self.assertEqual(got['coder'], ('gpt-6-luna', 'low', 'model,effort'))
        self.assertEqual(got['architect'], ('-', 'high', 'effort'))
        self.assertEqual(got['verifier'], ('-', '-', '-'))
        r = self.codex('show', '--plan', str(self.plan(head + '| coder | sonnet | low | |\n')))
        self.assertRejected(r, 'unknown model "sonnet" (one of: gpt-6-luna, gpt-5.6-terra, gpt-5.6-luna)')

    def test_codex_presets(self):
        self.use_example()
        r = self.codex('presets', '--profile', 'dev')
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual([x.split(':')[0] for x in lines], ['standard', 'economy', 'max'])
        self.assertTrue(all(': ' in x for x in lines), lines)
        self.write({'codex': {'dev': {'lean': {'coder': {'model': 'gpt-5.6-terra'}}}}, 'dev': {'x': {}}})
        self.assertEqual(self.codex('presets', '--profile', 'dev').stdout, 'lean: coder gpt-5.6-terra/-\n')
        self.assertEqual(self.codex('presets', '--profile', 'general').stdout, 'none\n')

    def test_example_codex_section_follows_the_rule(self):
        data = json.loads(EXAMPLE.read_text(encoding='utf-8'))
        section = data['codex']
        self.assertEqual(list(section), ['general', 'research', 'dev'])
        for profile, presets in data.items():
            if profile == 'codex':
                continue
            self.assertEqual(list(section[profile]), list(presets), profile)
            for preset, entries in presets.items():
                if preset == 'inline':
                    continue
                got = section[profile][preset]
                self.assertEqual(list(got), list(AGENTS), f'{profile}/{preset}')
                for agent in AGENTS:
                    model, effort = ma_models.merge(
                        {a: {'model': m, 'effort': e} for a, (m, e) in DEFINITION.items()}, entries)[agent]
                    want = {'effort': effort} if model == 'opus' else {'model': 'gpt-6-luna', 'effort': effort}
                    self.assertEqual(got[agent], want, f'{profile}/{preset}/{agent}')

    # --- the `inline` model value (criterion 9) ---

    def inline_lines(self, width):
        return [f'{a:<13}  model={"inline":<{width}} effort=-       pass=inline' for a in AGENTS]

    def test_example_inline_preset_in_every_profile_and_codex_section(self):
        data = json.loads(EXAMPLE.read_text(encoding='utf-8'))
        sections = [data[k] for k in ('general', 'research', 'dev')] + list(data['codex'].values())
        self.assertEqual(len(sections), 6)
        for section in sections:
            self.assertEqual(section['inline'], {a: {'model': 'inline'} for a in AGENTS})
        ma_models.validate(data)

    def test_show_inline_preset_on_both_hosts(self):
        self.use_example(inline=True)
        for host, width in (('claude', 6), ('codex', 10)):
            with self.subTest(host=host):
                r = self.run_cli('show', '--profile', 'dev', '--preset', 'inline', host=host)
                self.assertEqual(r.returncode, 0, r.stderr)
                where = f'file {self.file}' + (', codex section' if host == 'codex' else '')
                self.assertEqual(r.stdout.splitlines(), [f'preset: dev/inline ({where})'] + self.inline_lines(width))

    def test_show_inline_preset_exact_claude_text(self):
        self.use_example(inline=True)
        r = self.run_cli('show', '--profile', 'dev', '--preset', 'inline')
        self.assertEqual(r.stdout.splitlines()[1], 'architect      model=inline effort=-       pass=inline')

    def test_mixed_preset_and_presets_lines(self):
        for host, width, other in (('claude', 6, ('sonnet', 'sonnet')), ('codex', 10, ('gpt-6-luna', '-'))):
            with self.subTest(host=host):
                entries = {'architect': {'model': 'inline'}, 'verifier': {'model': 'inline'},
                           'coder': {'model': other[0]}}
                self.write({'dev': {'mixed': entries}} if host == 'claude' else {'codex': {'dev': {'mixed': entries}}})
                r = self.run_cli('show', '--profile', 'dev', '--preset', 'mixed', host=host)
                self.assertEqual(r.returncode, 0, r.stderr)
                lines = r.stdout.splitlines()
                self.assertEqual(lines[1], f'{"architect":<13}  model={"inline":<{width}} effort=-       pass=inline')
                self.assertEqual(lines[3], f'{"verifier":<13}  model={"inline":<{width}} effort=-       pass=inline')
                self.assertNotIn('inline', lines[2] + ''.join(lines[4:9]))
                self.assertEqual(lines[9].split()[1], f'model={other[0]}')
                out = self.run_cli('presets', '--profile', 'dev', host=host).stdout
                self.assertTrue(out.startswith('mixed: inline architect, verifier'), out)

    def test_presets_inline_summary(self):
        self.use_example(inline=True)
        for host in ('claude', 'codex'):
            out = self.run_cli('presets', '--profile', 'dev', host=host).stdout.splitlines()
            self.assertEqual(out[-1], 'inline: all roles inline', host)
        self.write({'dev': {'p': {'architect': {'model': 'inline'}, 'coder': {'effort': 'low'}}}})
        self.assertEqual(self.run_cli('presets', '--profile', 'dev').stdout, 'p: inline architect, coder sonnet/low\n')
        self.write({'dev': {'p': {a: {'model': 'inline'} for a in AGENTS[:5]}}})
        self.assertEqual(self.run_cli('presets', '--profile', 'dev').stdout, 'p: inline architect, plan-reviewer, '
                         'verifier, reviewer, gate-analyst\n')

    def test_inline_rejections(self):
        cases = [
            ({'dev': {'mixed': {'architect': {'model': 'inline', 'effort': 'high'}}}},
             'dev/mixed/architect: an inline role takes no effort (it runs in the main session)'),
            ({'codex': {'dev': {'mixed': {'coder': {'model': 'inline', 'effort': 'low'}}}}},
             'codex/dev/mixed/coder: an inline role takes no effort (it runs in the main session)'),
            ({'dev': {'mixed': {'coder': {'model': 'inlin'}}}},
             'dev/mixed/coder: unknown model "inlin" (one of: opus, sonnet, haiku, fable)'),
            ({'codex': {'dev': {'mixed': {'coder': {'model': 'inlin'}}}}},
             'codex/dev/mixed/coder: unknown model "inlin"'),
            ({'dev': {'mixed': {'main': {'model': 'inline'}}}},
             'dev/mixed: unknown agent "main" (the main session stays opus and has no entry)'),
            ({'codex': {'dev': {'mixed': {'main': {'model': 'inline'}}}}},
             'codex/dev/mixed: unknown agent "main" (the main session has no entry)'),
        ]
        for content, cause in cases:
            with self.subTest(cause=cause):
                self.write(content)
                for host in ('claude', 'codex'):
                    self.assertRejected(self.run_cli('presets', '--profile', 'dev', host=host), cause)

    def test_show_plan_inline_row(self):
        head = '## Models\n\nPreset: mixed\n\n| Agent | Model | Effort | Note |\n|---|---|---|---|\n'
        for host in ('claude', 'codex'):
            for effort in ('-', ''):
                with self.subTest(host=host, effort=effort):
                    p = self.plan(head + f'| architect | inline | {effort} | |\n')
                    r = self.run_cli('show', '--plan', str(p), host=host)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    _, got = rows(r.stdout)
                    self.assertEqual(got['architect'], ('inline', '-', 'inline'))
            self.assertRejected(self.run_cli('show', '--plan', str(self.plan(head + '| architect | inline | high | |\n')),
                                             host=host), 'an inline role takes no effort')

    def test_output_without_inline_equals_0_10_0(self):
        """A file without an inline value prints the 0.10.0 text (fixture captured from the 0.10.0 code)."""
        self.use_example()
        out = []
        for host in ('claude', 'codex'):
            for profile in ('general', 'research', 'dev'):
                cmds = [('show', '--profile', profile, '--preset', n) for n in ('standard', 'economy', 'max')]
                for cmd in cmds + [('presets', '--profile', profile)]:
                    r = self.run_cli(*cmd, host=host)
                    out += [f'$ MA_HOST={host} agent-models.py {" ".join(cmd)}', f'[exit {r.returncode}]',
                            r.stdout.replace(str(self.file), '<data>/agent-models.json').rstrip('\n')]
                    if r.stderr:
                        out.append(r.stderr.rstrip('\n'))
                    out.append('')
        want = (Path(__file__).parent / 'fixtures' / 'agent-models-0.10.0.txt').read_text(encoding='utf-8')
        self.assertEqual('\n'.join(out), want)


if __name__ == '__main__':
    unittest.main()

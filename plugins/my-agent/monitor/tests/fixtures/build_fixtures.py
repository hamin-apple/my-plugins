"""Builds the five mock-up tasks (webapp-v22.html TASKS) as real my-agent task folders.

Run-log lines and file shapes follow my-agent-architecture.md 4.7.2 and the agent definitions (C8). File mtimes are set to
the times the mock-up shows, so the whole tree is regenerated on every test run.
"""
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECTS = HERE / 'projects'
CLAUDE = HERE / 'claude-projects'
PROJECTS_TXT = HERE / 'projects.txt'

# main-session usage of 261024-cli-json-output per step window (tests/test_transcript.py)
EXPECTED_MAIN = {
    1: {'input_tokens': 8000, 'output_tokens': 1000, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 0},
    5: {'input_tokens': 15000, 'output_tokens': 3000, 'cache_creation_input_tokens': 0, 'cache_read_input_tokens': 2000},
}


def ts(day, hm):
    return datetime.strptime(f'{day} {hm}', '%Y-%m-%d %H:%M:%S' if hm.count(':') == 2 else '%Y-%m-%d %H:%M')


def q(v):
    """run-log value: double-quoted when it has spaces or quotes; `"` and `\\` escaped inside (shlex POSIX)."""
    v = str(v)
    if ' ' in v or '"' in v or not v:
        return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return v


class Task:
    def __init__(self, project, task_id, day):
        self.dir = PROJECTS / project / 'docs' / 'agent' / task_id
        self.project = PROJECTS / project
        self.day = day
        self.lines = [f'# run-log {task_id}']
        self.mtimes = {}

    def log(self, hm, kind, **f):
        t = ts(self.day, hm if hm.count(':') == 2 else hm + ':00')
        body = ' '.join(f'{k}={q(v)}' for k, v in f.items())
        self.lines.append(f'{t:%Y-%m-%d %H:%M:%S} {kind}:' + (' ' + body if body else ''))

    def agent(self, hm_call, hm_stop, agent, aid, configured, effort, actual=None, tokens=0, mins=0,
              result='DONE', end='ok', model='-', isolation='-', background='false', unit=None):
        u = {'unit': unit} if unit else {}
        self.log(hm_call, 'call', agent=f'my-agent:{agent}', model=model, effort='-', isolation=isolation, background=background, **u)
        self.log(hm_call, 'start', agent=f'my-agent:{agent}', id=aid, configured=configured, effort=effort)
        if hm_stop:
            i, o = int(tokens * .75), int(tokens * .15)
            self.log(hm_stop, 'stop', id=aid, **u, actual=actual or f'claude-{configured}-5-5', tokens=tokens,
                     **{'in': i, 'out': o, 'cw': int(tokens * .06), 'cr': tokens - i - o - int(tokens * .06)},
                     secs=mins * 60, result=result, end=end)

    def step(self, hm, n, name, rev=0, session='s'):
        self.log(hm, 'step', n=n, name=name, rev=rev, session=session)

    def popup(self, hm, gate, question, hm_answer=None, choice=None):
        self.log(hm, 'ask', gate=gate, q=question)
        if hm_answer:
            self.log(hm_answer, 'answer', gate=gate, choice=choice)

    def file(self, rel, text, hm, day=None):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding='utf-8')
        self.mtimes[p] = ts(day or self.day, hm)

    def done(self, runlog_hm):
        self.file('run-log.md', '\n'.join(self.lines) + '\n', runlog_hm)
        for p, t in sorted(self.mtimes.items(), key=lambda x: -len(x[0].parts)):
            os.utime(p, (t.timestamp(), t.timestamp()))
        for d in sorted([p for p in self.dir.rglob('*') if p.is_dir()], key=lambda p: -len(p.parts)):
            kids = [self.mtimes.get(c) for c in d.iterdir() if self.mtimes.get(c)]
            if kids:
                t = max(kids)
                self.mtimes[d] = t
                os.utime(d, (t.timestamp(), t.timestamp()))


def intake(task_id, status, location, profile, request, extra=''):
    return f'Status: {status}\nmy-agent: a3f91c2\nLocation: {location}\nProfile: {profile}\nTask: {task_id}\nRequest: {request}\n{extra}'


def cli_json_output():
    t = Task('claude-sessions', '261024-cli-json-output', '2026-10-24')
    S = 's-cli'
    t.step('15:30', 1, 'Intake', session=S)
    t.log('15:30:30', 'cost', session=S, usd='0.10')
    t.step('15:31', 2, 'Explore-Scope', session=S)
    t.agent('15:31:05', '15:34', 'explorer', 'ag-ex1', 'sonnet', 'low', tokens=38000, mins=3)
    t.popup('15:41', 'G1a', 'Confirm this scope?', '15:41:20', 'Confirm (Recommended)')
    t.step('15:42', 3, 'Plan', session=S)
    t.log('15:42:01', 'cost', session=S, usd='0.72')
    t.agent('15:42:05', '15:49', 'architect', 'ag-ar1', 'opus', 'high', tokens=61000, mins=7, result='DONE')
    t.step('15:50', 4, 'Plan-Review', session=S)
    t.agent('15:50:05', '15:53', 'plan-reviewer', 'ag-pr1', 'sonnet', 'high', tokens=29000, mins=3, result='READY FOR APPROVAL')
    t.popup('15:55', 'G1b', 'Proceed with this plan?', '15:55:30', 'Approve (Recommended)')
    t.step('15:56', 5, 'Execute', session=S)
    t.log('15:56:01', 'cost', session=S, usd='1.58')
    t.agent('15:56:05', None, 'coder', 'ag-c1', 'sonnet', 'medium', isolation='worktree', background='true')
    t.agent('15:56:06', '16:04', 'coder', 'ag-c2', 'sonnet', 'medium', tokens=84000, mins=8, isolation='worktree', background='true')
    t.log('16:01:15', 'ask', gate='G2', agent='my-agent:coder', id='ag-c2', tool='Bash', q='npm i fast-json-stable-stringify')
    t.log('16:01:30', 'answer', gate='G2', id='ag-c2', result='allowed')
    t.log('16:07:00', 'cost', session=S, usd='2.51')
    t.file('intake.md', intake('261024-cli-json-output', 'active', t.project, 'dev', 'Add a --json output option to the CLI'), '15:30')
    t.file('explore.md', '# Explore\n- Output: claude_sessions/view.py:render_table\n', '15:34')
    t.file('scope.md', '# Scope\n## Completion criteria\n1. With --json, a JSON array instead of a table\n2. Errors as JSON too\n## Non-goals\n- YAML output\n## Confirmation\nConfirmed 2026-10-24 15:41\n', '15:41')
    t.file('plan.md', '# Plan\n## Slices\n- Group A: slice 1 formatter · slice 2 CLI option\n## Estimate\n- Subagents: 6\n- Estimated tokens: 600k\n'
           '## Mock-up\nKind: CLI input/output\n$ tool list --json            (criterion 1)\n[{"name": "alpha", "size": 120}]\n'
           '## Approval\n- Approved 2026-10-24 15:55 G1b\n', '15:55')
    t.file('plan-review.md', 'READY FOR APPROVAL\nRun: 1\n', '15:53')
    t.file('work/slice-2.md', 'slice 2 notes\n', '16:04')
    t.done('16:07')
    return t


def hitl_survey():
    t = Task('agent-tasks', '261024-hitl-survey', '2026-10-24')
    S = 's-hitl'
    t.step('14:10', 1, 'Intake', session=S)
    t.step('14:11', 2, 'Explore-Scope', session=S)
    t.agent('14:11:05', '14:13', 'explorer', 'ag-ex1', 'sonnet', 'low', tokens=20000, mins=2)
    t.popup('14:20', 'G1a', 'Confirm this scope?', '14:20:20', 'Confirm (Recommended)')
    t.step('14:21', 3, 'Plan', session=S)
    t.agent('14:21:05', '14:27', 'architect', 'ag-ar1', 'opus', 'high', tokens=52000, mins=6, result='DONE')
    t.step('14:28', 4, 'Plan-Review', session=S)
    t.agent('14:28:05', '14:30', 'plan-reviewer', 'ag-pr1', 'sonnet', 'high', tokens=18000, mins=2, result='READY FOR APPROVAL')
    t.popup('14:31', 'G1b', 'Proceed with this plan?', '14:31:30', 'Approve (Recommended)')
    t.step('14:32', 5, 'Execute', session=S)
    for i, end in enumerate(['14:41', '14:43', '14:44'], 1):
        t.agent(f'14:32:0{i}', end, 'researcher', f'ag-r{i}', 'sonnet', 'medium', tokens=40000, mins=10, background='true')
    t.log('14:47:00', 'revision', rev=1, why='Added "cost control" to the sub-questions (user)', archive='archive/261024-144700-rev1/',
          invalidated='plan-review.md,plan.md ## Approval', keep='Existing work: work/q1~q3 keep', state='pending')
    t.log('14:47:30', 'revision', rev=1, state='done')
    t.step('14:48', 3, 'Plan', rev=1, session=S)
    t.agent('14:48:05', '14:52', 'architect', 'ag-ar2', 'opus', 'high', tokens=31000, mins=4, result='DONE')
    t.step('14:53', 4, 'Plan-Review', rev=1, session=S)
    t.agent('14:53:05', '14:55', 'plan-reviewer', 'ag-pr2', 'sonnet', 'high', tokens=15000, mins=2, result='READY FOR APPROVAL')
    t.popup('14:56', 'G1b', 'Proceed with the revised plan? (rev1)', '14:56:20', 'Approve (Recommended)')
    t.step('14:57', 5, 'Execute', rev=1, session=S)
    t.agent('14:57:05', None, 'researcher', 'ag-r4', 'sonnet', 'medium', background='true')
    t.file('intake.md', intake('261024-hitl-survey', 'active', t.project, 'research', 'Survey of HITL orchestration cases → comparison note'), '14:10')
    t.file('explore.md', '# Explore\n', '14:13')
    crit = '## Completion criteria\n1. Where the approval gates are\n2. Asynchronous notification\n3. Handing failures to a person\n'
    t.file('scope.md', '# Scope\n' + crit + '4. Cost control\n## Confirmation\nConfirmed 2026-10-24 14:20\n', '14:20')
    mock0 = 'Kind: note outline + sample paragraph\n# HITL orchestration compared\n1. Approval gate placement   (criterion 1)\n2. Async notification        (criterion 2)\n3. Failures to a person      (criterion 3)\n'
    mock1 = mock0 + '4. Cost control              (criterion 4)  ← added in rev1\n'
    t.file('plan.md', '# Plan (rev1)\n## Estimate\n- Estimated tokens: 450k\n## Mock-up\n' + mock1 +
           '## Existing work\n| work/q1~q3.md | keep | sub-questions unchanged |\n## Approval\n- Approved 2026-10-24 14:56 G1b\n## Revisions\n- rev1 2026-10-24 14:47 sub-question "cost control" added; archive archive/261024-144700-rev1/; back to ② Plan\n', '14:56')
    t.file('plan-review.md', 'READY FOR APPROVAL\nRun: 1\n', '14:55')
    for n, hm in [(1, '14:41'), (2, '14:43'), (3, '14:44'), (4, '15:03')]:
        t.file(f'work/q{n}.md', f'# q{n}\n', hm)
    a = 'archive/261024-144700-rev1/'
    t.file(a + 'intake.md', '# 261024-hitl-survey\n', '14:47')
    t.file(a + 'plan.md', '# Plan\n## Estimate\n- Estimated tokens: 400k\n## Mock-up\n' + mock0 + '## Approval\n- Approved 2026-10-24 14:31 G1b\n', '14:47')
    t.file(a + 'plan-review.md', 'READY FOR APPROVAL\nRun: 1\n', '14:47')
    t.done('14:57')
    return t


def hooks_notify_note():
    t = Task('obsidian-notes', '261023-hooks-notify-note', '2026-10-23')
    S = 's-hooks'
    t.step('14:02', 1, 'Intake', session=S)
    t.step('14:03', 2, 'Explore-Scope', session=S)
    t.agent('14:03:05', '14:05', 'explorer', 'ag-ex1', 'sonnet', 'low', tokens=22000, mins=2)
    t.popup('14:15', 'G1a', 'Confirm this scope?', '14:15:20', 'Confirm (Recommended)')
    t.step('14:16', 3, 'Plan', session=S)
    t.agent('14:16:05', '14:22', 'architect', 'ag-ar1', 'opus', 'high', tokens=48000, mins=6, result='DONE')
    t.step('14:23', 4, 'Plan-Review', session=S)
    t.agent('14:23:05', '14:25', 'plan-reviewer', 'ag-pr1', 'sonnet', 'high', tokens=19000, mins=2, result='READY FOR APPROVAL')
    t.popup('14:27', 'G1b', 'Proceed with this plan?', '14:27:30', 'Approve (Recommended)')
    t.step('14:28', 5, 'Execute', session=S)
    for i in range(1, 5):
        t.agent(f'14:28:0{i}', '14:42', 'researcher', f'ag-r{i}', 'sonnet', 'medium', tokens=41000, mins=14, background='true')
    t.log('14:35:00', 'ask', gate='G2', agent='my-agent:researcher', id='ag-r2', tool='WebFetch', q='WebFetch example-blog.dev')
    t.log('14:35:20', 'answer', gate='G2', id='ag-r2', result='allowed')
    t.agent('14:43:05', '14:48', 'writer', 'ag-w1', 'sonnet', 'medium', actual='claude-haiku-5-5', tokens=41000, mins=5)
    t.step('14:49', 6, 'Merge', session=S)
    t.step('14:50', 7, 'Verify', session=S)
    t.agent('14:50:05', '14:54', 'verifier', 'ag-v1', 'opus', 'high', tokens=37000, mins=4, result='Verdict: FAIL')
    t.agent('14:58:05', '15:01', 'verifier', 'ag-v2', 'opus', 'high', tokens=31000, mins=3, result='Verdict: ALL PASS')
    t.step('15:03', 8, 'Review-Deliver', session=S)
    t.agent('15:03:05', '15:05', 'reviewer', 'ag-rv1', 'sonnet', 'high', tokens=18000, mins=2, result='BLOCKER 0')
    t.popup('15:10', 'G3', 'Accept this note?', '15:10:40', 'Accept')
    t.log('15:14:00', 'deliver', path='docs/notes/claude-hooks-notify.md')
    t.file('intake.md', intake('261023-hooks-notify-note', 'done', t.project, 'research', 'How to send approval notifications with hooks → note',
                              'Delivered: docs/notes/claude-hooks-notify.md\n'), '15:14')
    t.file('explore.md', '# Explore\n', '14:05')
    t.file('scope.md', '# Scope\n## Completion criteria\n1. a\n2. b\n3. c\n4. d\n5. e\n## Confirmation\nConfirmed 2026-10-23 14:15\n', '14:15')
    t.file('plan.md', '# Plan\n## Estimate\n- Estimated tokens: 450k\n## Mock-up\nKind: note outline + sample paragraph\n1. Notification hook overview   (criterion 1)\n'
           '## Approval\n- Approved 2026-10-23 14:27 G1b\n', '14:27')
    t.file('plan-review.md', 'READY FOR APPROVAL\nRun: 1\n', '14:25')
    for n, hm in [(1, '14:40'), (2, '14:41'), (3, '14:39'), (4, '14:42')]:
        t.file(f'work/q{n}.md', f'# q{n}\n', hm)
    t.file('work/draft.md', '# draft\n', '14:48')
    t.file('verify.md', 'Verdict: ALL PASS\nRun: 2\n- 1. PASS checked\n- 2. PASS checked\n- 3. PASS checked\n- 4. PASS checked\n- 5. PASS checked\n', '15:01')
    t.file('review.md', 'BLOCKER 0\n', '15:05')
    t.done('15:14')
    note = t.project / 'docs' / 'notes' / 'claude-hooks-notify.md'
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text('x' * 6200, encoding='utf-8')
    return t


def weekly_report():
    t = Task('work-notes', '261022-weekly-report', '2026-10-22')
    S = 's-wk'
    t.step('09:10', 1, 'Intake', session=S)
    t.step('09:13', 3, 'Plan', session=S)
    t.popup('09:16', 'G1b', 'Approve the scope and plan?', '09:16:30', 'Approve')
    t.step('09:17', 5, 'Execute', session=S)
    t.agent('09:17:05', '09:21', 'writer', 'ag-w1', 'sonnet', 'medium', tokens=31000, mins=4)
    t.step('09:25', 7, 'Verify', session=S)
    t.agent('09:25:05', '09:27', 'verifier', 'ag-v1', 'opus', 'high', tokens=12000, mins=2, result='Verdict: ALL PASS')
    t.step('09:28', 8, 'Review-Deliver', session=S)
    t.agent('09:28:05', '09:30', 'reviewer', 'ag-rv1', 'sonnet', 'high', tokens=9000, mins=2, result='BLOCKER 0')
    t.popup('09:33', 'G3', 'Accept this report draft?', '09:33:30', 'Accept')
    t.log('09:34:00', 'deliver', path='reports/2026-w43.md')
    t.file('intake.md', intake('261022-weekly-report', 'done', t.project, 'general', '2 meeting notes → weekly report draft',
                              'Delivered: reports/2026-w43.md\n'), '09:34')
    t.file('plan.md', '# Plan\n## Completion criteria\n1. Decisions\n2. To-dos for next week\n3. Open questions\n## Estimate\n- Estimated tokens: 150k\n'
           '## Mock-up\nKind: report first page\n# Weekly report (10/20 ~ 10/24)\n## Approval\n- Approved 2026-10-22 09:16 G1b\n', '09:16')
    t.file('work/draft.md', '# draft\n', '09:22')
    t.file('verify.md', 'Verdict: ALL PASS\nRun: 2\n- 1. PASS\n- 2. PASS\n- 3. PASS\n', '09:27')
    t.file('review.md', 'BLOCKER 0\n', '09:30')
    t.done('09:34')
    return t


def flight_watch():
    t = Task('flight-search', '261021-flight-watch', '2026-10-21')
    S = 's-fl'
    t.step('20:40', 1, 'Intake', session=S)
    t.step('20:41', 2, 'Explore-Scope', session=S)
    t.agent('20:41:05', '20:45', 'explorer', 'ag-ex1', 'sonnet', 'low', tokens=25000, mins=4)
    t.popup('20:52', 'G1a', 'Confirm this scope?', '20:52:20', 'Confirm (Recommended)')
    t.step('20:53', 3, 'Plan', session=S)
    t.agent('20:53:05', '20:59', 'architect', 'ag-ar1', 'opus', 'high', tokens=50000, mins=6, result='DONE')
    t.step('21:00', 4, 'Plan-Review', session=S)
    t.agent('21:00:05', '21:01', 'plan-reviewer', 'ag-pr1', 'sonnet', 'high', tokens=15000, mins=1, result='READY FOR APPROVAL')
    t.popup('21:02', 'G1b', 'Proceed with this plan?', '21:02:20', 'Approve (Recommended)')
    t.step('21:03', 5, 'Execute', session=S)
    t.agent('21:03:05', '21:15', 'coder', 'ag-f1', 'sonnet', 'medium', tokens=120000, mins=12, result='PARTIAL maxTurns', end='partial', unit='u2')
    t.agent('21:15:30', '21:28', 'coder', 'ag-f2', 'opus', 'medium', model='opus', tokens=150000, mins=12, result='-', end='error', unit='u2')
    t.popup('21:30', 'E', 'Work unit u2 stopped twice (send notification)', '21:30:40', 'Abort')
    t.log('21:31:00', 'abort', why='E work unit stopped')
    t.file('intake.md', intake('261021-flight-watch', 'aborted 2026-10-21 21:31 E work unit stopped', t.project, 'dev', 'Add notifications to price watches'), '21:31')
    t.file('scope.md', '# Scope\n## Completion criteria\n1. a\n2. b\n3. c\n4. d\n## Confirmation\nConfirmed 2026-10-21 20:52\n', '20:52')
    t.file('plan.md', '# Plan\n## Estimate\n- Estimated tokens: 250k\n## Mock-up\nKind: CLI input/output\n$ flight watch add ICN-NRT --notify\n'
           '## Approval\n- Approved 2026-10-21 21:02 G1b\n', '21:02')
    t.done('21:31')
    return t


def transcript():
    """Main-session transcript of 261024-cli-json-output (session s-cli)."""
    p = CLAUDE / '-x-claude-sessions' / 's-cli.jsonl'
    p.parent.mkdir(parents=True, exist_ok=True)

    def entry(hm, mid, i, o, cr=0, model='claude-opus-5-5'):
        t = ts('2026-10-24', hm).astimezone().astimezone(timezone.utc)
        return json.dumps({'type': 'assistant', 'timestamp': t.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                           'message': {'id': mid, 'model': model, 'usage': {
                               'input_tokens': i, 'output_tokens': o, 'cache_creation_input_tokens': 0,
                               'cache_read_input_tokens': cr}}})
    rows = [entry('15:30:10', 'm1', 8000, 1000),
            json.dumps({'type': 'user', 'timestamp': '2026-10-24T06:31:00.000Z', 'message': {'content': 'hi'}}),
            entry('15:35:00', 'm2', 20000, 2000),
            entry('15:57:00', 'm3', 5000, 500),          # streamed twice: the last usage wins
            entry('15:57:01', 'm3', 5000, 1000),
            entry('16:02:00', 'm4', 10000, 2000, cr=2000)]
    p.write_text('\n'.join(rows) + '\n', encoding='utf-8')
    return p


def build():
    shutil.rmtree(PROJECTS, ignore_errors=True)
    shutil.rmtree(CLAUDE, ignore_errors=True)
    tasks = [cli_json_output(), hitl_survey(), hooks_notify_note(), weekly_report(), flight_watch()]
    transcript()
    PROJECTS_TXT.write_text(''.join(f'{t.project}\n' for t in tasks), encoding='utf-8')
    return tasks


if __name__ == '__main__':
    build()

"""Plays the rest of 261024-cli-json-output into a COPY of its task folder, for live testing.

Usage: python3 tools/feed-fixture.py <task-dir-copy> [--every 3]

Five batches (the mock-up's live queue, in run-log v0.19 format): coder-1 ends →
merge → coder-3 → verifier → reviewer and a G3 question. The very last line is
written in two chunks one second apart, so a poll can catch it half written.
Refuses to touch a folder that is not under a temp or scratch directory.
"""
import argparse
import sys
import time
from datetime import datetime
from pathlib import Path


def batches():
    agent = lambda a, i, m, e: [f'call: agent=my-agent:{a} model=- effort=- isolation=- background=false',
                                f'start: agent=my-agent:{a} id={i} configured={m} effort={e}']
    stop = lambda i, actual, tok, secs, res: (f'stop: id={i} actual={actual} tokens={tok} in={int(tok * .75)} out={int(tok * .15)} '
                                              f'cw={int(tok * .06)} cr={tok - int(tok * .75) - int(tok * .15) - int(tok * .06)} '
                                              f'secs={secs} result={res} end=ok')
    return [
        ([stop('ag-c1', 'claude-sonnet-5-5', 97000, 840, 'DONE')], None),
        (['step: n=6 name="Merge · Self-check" rev=0 session=s-cli'], None),
        (['step: n=5 name=Execute rev=0 session=s-cli'] + agent('coder', 'ag-c3', 'sonnet', 'medium'), None),
        ([stop('ag-c3', 'claude-sonnet-5-5', 52000, 300, 'DONE'), 'step: n=7 name=Verify rev=0 session=s-cli']
         + agent('verifier', 'ag-v1', 'opus', 'high'), None),
        ([stop('ag-v1', 'claude-opus-5-5', 33000, 180, '"ALL PASS"'), 'step: n=8 name="Review → Deliver" rev=0 session=s-cli']
         + agent('reviewer', 'ag-rv1', 'sonnet', 'high') + [stop('ag-rv1', 'claude-sonnet-5-5', 24000, 120, '"BLOCKER 0"'),
                                                            'ask: gate=G3 q="Commit this change?"'],
         'Verdict: ALL PASS\n- 1. PASS JSON array instead of a table\n- 2. PASS errors as JSON too\n'),
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('task_dir', type=Path)
    ap.add_argument('--every', type=float, default=3.0, help='seconds between batches')
    args = ap.parse_args(argv)
    d = args.task_dir.resolve()
    if not (d / 'run-log.md').exists():
        sys.exit(f'no run-log.md in {d}')
    if not any(part in ('tmp', 'T', 'scratchpad') or part.startswith('tmp') for part in d.parts):
        sys.exit(f'refusing to write outside a temp copy: {d}')
    log = d / 'run-log.md'
    all_batches = batches()
    for bi, (lines, verify) in enumerate(all_batches):
        time.sleep(args.every)
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        text = ''.join(f'{stamp} {l}\n' for l in lines)
        last = bi == len(all_batches) - 1
        with log.open('a', encoding='utf-8') as f:
            if last:
                cut = len(text) - 12          # the G3 question, cut inside its quotes
                f.write(text[:cut]); f.flush()
                print('half line written', flush=True)
                time.sleep(1)
                f.write(text[cut:])
            else:
                f.write(text)
        if verify:
            (d / 'verify.md').write_text(verify, encoding='utf-8')
        print(f'batch {bi + 1}/{len(all_batches)}: {len(lines)} line(s)', flush=True)


if __name__ == '__main__':
    main()

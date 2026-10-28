#!/usr/bin/env python3
"""Probe hook (architecture §6 step 0): append the raw hook input to ~/dev/labs/my-agent-sandbox/.probe/<event>.jsonl.

usage: probe-log.py <event-label> [extra args are recorded as given]
Only writes when the hook's cwd is inside ~/dev/labs/my-agent-sandbox (or always, into $PROBE_OUT_DIR when that is set). Always exits 0.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

SANDBOX = Path.home() / 'dev' / 'labs' / 'my-agent-sandbox'


def main():
    try:
        raw = sys.stdin.read()
        try:
            inp = json.loads(raw)
        except ValueError:
            inp = {'_raw': raw}
        cwd = Path(inp.get('cwd') or os.getcwd()).resolve() if isinstance(inp, dict) else Path(os.getcwd())
        override = os.environ.get('PROBE_OUT_DIR')
        if override:
            out = Path(override)
        elif SANDBOX.resolve() in (cwd, *cwd.parents):
            out = SANDBOX / '.probe'
        else:
            return 0
        out.mkdir(parents=True, exist_ok=True)
        label = sys.argv[1] if len(sys.argv) > 1 else 'unknown'
        rec = {'event': label, 'time': datetime.now().isoformat(timespec='seconds'), 'argv': sys.argv[2:],
               'env': {k: os.environ.get(k) for k in ('CLAUDE_PLUGIN_ROOT', 'CLAUDE_CODE_EFFORT_LEVEL',
                                                      'CLAUDE_PROJECT_DIR', 'CLAUDE_CODE_SESSION_ID',
                                                      'CLAUDE_PLUGIN_OPTION_DATA_DIR')},
               'input': inp}
        with open(out / f'{label}.jsonl', 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except BaseException:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())

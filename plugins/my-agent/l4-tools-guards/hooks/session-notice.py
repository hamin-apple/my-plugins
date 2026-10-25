#!/usr/bin/env python3
"""Plugin hook (SessionStart): remind a new, resumed, cleared, compacted or forked session of an
unfinished my-agent task (architecture 4.8.2 "새 세션 알림"). Prints nothing when no `.active` is found.
Always exits 0.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ma_active  # noqa: E402

NOTICE = ('미완료 my-agent 작업 `{task}`, phase `{phase}`. 다른 일을 하기 전에 `/my-agent continue`를 실행할 것. '
          '`plan.md`에 승인 줄이 없으면 위임과 쓰기를 하지 말 것.')
FORK = '원래 세션이 이 작업을 진행 중. 이 세션에서 이어받으려면 `/my-agent continue`'


def main() -> int:
    try:
        inp = json.loads(sys.stdin.read() or '{}')
        if not isinstance(inp, dict):
            return 0
        active = ma_active.find_active(inp.get('cwd') or os.getcwd())
        if active is None:
            return 0
        if inp.get('source') == 'fork' and active.session and active.session != inp.get('session_id'):
            msg = FORK
        else:
            msg = NOTICE.format(task=active.task, phase=active.phase or '-')
        print(json.dumps({'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': msg}},
                         ensure_ascii=False))
    except BaseException:   # the session starts as usual whatever happens
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())

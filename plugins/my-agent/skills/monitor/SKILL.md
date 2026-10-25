---
name: monitor
description: Start, check, or stop the my-agent monitor web page (local, read-only). Run only when called as /my-agent:monitor.
disable-model-invocation: true
argument-hint: '[status|stop]'
---

# my-agent monitor

The monitor is a read-only local web page that shows every my-agent task (architecture doc 4.7.4). Its starter script prints exactly one line and always exits 0.

Arguments: `$ARGUMENTS`

Run exactly one command, chosen by the arguments:

| Arguments | Command |
|---|---|
| (none) | `python3 "${CLAUDE_PLUGIN_ROOT}/monitor/monitor-up.py" --open` |
| `status` | `python3 "${CLAUDE_PLUGIN_ROOT}/monitor/monitor-up.py" status` |
| `stop` | `python3 "${CLAUDE_PLUGIN_ROOT}/monitor/monitor-up.py" stop` |
| anything else | run nothing; say the arguments are `status` and `stop` |

Then report the printed line to the user in Korean, in one sentence, keeping the URL as it is:

- `(started)`: 모니터를 띄우고 모니터 창을 열었다(설정이 tab이면 탭)
- `(running…)`: 이미 떠 있다 (no argument: 모니터 창을 열었다, 설정이 tab이면 탭)
- `not running`, `stopped <port>`, `nothing to stop`: as they say
- `not started (<reason>)`: 띄우지 못했다, with the reason

Do nothing else.

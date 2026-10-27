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

Then report the printed line to the user in their language, in one sentence, keeping the URL as it is:

- `(started)`: started the monitor and opened the monitor window (a tab if the setting is tab)
- `(running…)`: it is already running (no argument: opened the monitor window, a tab if the setting is tab)
- `not running`, `stopped <port>`, `nothing to stop`: as they say
- `not started (<reason>)`: could not start it, with the reason

Do nothing else.

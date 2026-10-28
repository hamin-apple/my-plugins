---
name: probe-skill
description: Probe skill for the my-agent §6 step 0 probe. Run only when called as /my-agent:probe-skill.
disable-model-invocation: true
hooks:
  PreToolUse:
    - hooks:
        - type: command
          command: "python3 \"$HOME/dev/my-plugins/plugins/my-agent/tests/probe/probe-log.py\" skill-pretool '${CLAUDE_PLUGIN_ROOT}' \"${CLAUDE_PLUGIN_ROOT}\""
          timeout: 10
---

Use the Agent tool exactly once with subagent_type `my-agent:probe-worker` and the prompt "Run: pwd". Then reply with the agent's last line and stop.

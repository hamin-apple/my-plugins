---
name: data-dir-probe
description: Probe skill for the data_dir setting (r11). Run only when called as /data-dir-probe:data-dir-probe.
disable-model-invocation: true
hooks:
  PreToolUse:
    - hooks:
        - type: command
          command: "python3 \"$PROBE_LOG\" skill-data-dir \"$CLAUDE_PLUGIN_OPTION_DATA_DIR\""
          timeout: 10
        - type: command
          command: "python3 \"$PROBE_LOG\" skill-placeholder '${user_config.data_dir}'"
          timeout: 10
---

Use the Bash tool exactly once with this command, unchanged, then reply DONE and stop:

echo 'BODY=[${user_config.data_dir}]'
